"""Bounded, time-based ink that breaks into light wisps before disappearing.

All times use the caller's monotonic clock. ``render`` returns a reused BGR
buffer on black; composite it immediately, or copy it if retaining a frame.
There is no particle history: wisp positions are derived from each segment's
age and seed, so rendering faster does not create more particles or extend life.
"""

from collections import deque
from dataclasses import dataclass
import heapq
import math
from numbers import Integral

import cv2
import numpy as np


# Appearance tuning, in camera-image pixels. Lifetime is set per FadingInk.
STROKE_WIDTH = 5
MIN_SEGMENT_LENGTH = 1.0
FRAGMENTS_PER_SEGMENT = 3
MAX_WISP_SEGMENTS = 96
WISPS_PER_SEGMENT = 2
WISP_DRIFT_PIXELS = 24.0
GLOW_SCALE = 4
GLOW_STRENGTH = 0.38
MIST_STRENGTH = 0.65
EFFECT_NAMES = ("Particles", "Smoke", "Drops", "Rise", "Swirl", "Wave", "Shards", "Wipe")


@dataclass(frozen=True, slots=True)
class InkSegment:
    start: tuple
    end: tuple
    color_bgr: tuple
    created_at: float
    serial: int
    seed: int
    effect_id: int = 0
    track_id: int = 0


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


class FadingInk:
    def __init__(self, width, height, hold_seconds=3.5, fade_seconds=3.0, max_segments=720):
        for name, value in (("width", width), ("height", height), ("max_segments", max_segments)):
            number = _finite(value)
            if number is None or number < 1 or number != int(number):
                raise ValueError(f"{name} must be a positive integer")
        hold, fade = _finite(hold_seconds), _finite(fade_seconds)
        if hold is None or hold < 0 or fade is None or fade <= 0:
            raise ValueError("hold_seconds must be nonnegative and fade_seconds must be positive")
        self.width, self.height = int(width), int(height)
        self.hold_seconds, self.fade_seconds = hold, fade
        self.max_segments = int(max_segments)
        self.segments = deque(maxlen=self.max_segments)
        self._serial = 0
        self._latest_at = float("-inf")
        self._ink = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self._glow = np.zeros_like(self._ink)
        self._output = np.zeros_like(self._ink)
        self._small_size = (max(1, self.width // GLOW_SCALE), max(1, self.height // GLOW_SCALE))
        self._small = np.zeros((self._small_size[1], self._small_size[0], 3), dtype=np.uint8)
        self._blur = np.zeros_like(self._small)
        self._mist = np.zeros_like(self._small)
        self._mist_used = False

    @property
    def lifetime(self):
        return self.hold_seconds + self.fade_seconds

    def _point(self, point):
        try:
            if len(point) != 2:
                return None
            x, y = _finite(point[0]), _finite(point[1])
        except (TypeError, IndexError):
            return None
        if x is None or y is None:
            return None
        return (round(min(self.width - 1, max(0., x))),
                round(min(self.height - 1, max(0., y))))

    def add_segment(self, start, end, color_bgr, now, *, effect_id=0, track_id=0):
        """Add a pixel-space segment; return False for invalid or stationary input.

        Coordinates/colors are clamped before drawing. New samples must arrive
        in timestamp order; an old sample cannot refresh or resurrect ink.
        Effect and track IDs are immutable metadata of this segment. Changing
        a hand's chosen effect affects only new ink. Existing calls use effect 0.
        """
        if (isinstance(effect_id, bool) or not isinstance(effect_id, Integral)
                or not 0 <= effect_id < len(EFFECT_NAMES)
                or isinstance(track_id, bool) or not isinstance(track_id, Integral)
                or track_id < 0):
            return False
        now = _finite(now)
        start, end = self._point(start), self._point(end)
        try:
            color = tuple(_finite(channel) for channel in color_bgr)
        except TypeError:
            return False
        if (now is None or start is None or end is None or len(color) != 3
                or any(channel is None for channel in color)
                or math.dist(start, end) < MIN_SEGMENT_LENGTH):
            return False
        if now < self._latest_at:
            return False
        color = tuple(round(min(255., max(0., channel))) for channel in color)
        self.advance(now)
        seed = (self._serial * 2654435761 ^ start[0] * 73856093 ^ start[1] * 19349663
                ^ end[0] * 83492791 ^ end[1] * 2971215073) & 0xFFFFFFFF
        self.segments.append(InkSegment(start, end, color, now, self._serial, seed,
                                        int(effect_id), int(track_id)))
        self._serial = (self._serial + 1) & 0xFFFFFFFF
        return True

    def advance(self, now):
        """Prune expired segments even when no hand is currently drawing."""
        now = _finite(now)
        if now is None:
            raise ValueError("now must be finite")
        self._latest_at = max(self._latest_at, now)
        while self.segments and self._latest_at - self.segments[0].created_at >= self.lifetime:
            self.segments.popleft()

    def clear(self):
        self.segments.clear()
        self._serial = 0
        self._latest_at = float("-inf")
        for buffer in (self._ink, self._glow, self._output, self._small, self._blur, self._mist):
            buffer.fill(0)
        self._mist_used = False

    def _dissolving_line(self, segment, progress):
        remaining = 1.0 - progress
        color = tuple(round(channel * remaining ** 1.45) for channel in segment.color_bgr)
        thickness = max(1, round(STROKE_WIDTH * (0.35 + 0.65 * remaining)))
        x, y = segment.start
        dx, dy = segment.end[0] - x, segment.end[1] - y
        length = math.hypot(dx, dy)
        nx, ny = -dy / length, dx / length
        # Small gaps open along the line, then its remaining pieces lift away.
        # Starting at zero makes the hold-to-dissolve boundary continuous.
        gap = progress ** 0.8 * 0.82
        for index in range(FRAGMENTS_PER_SEGMENT):
            seed_value = ((segment.seed >> (index * 7)) & 127) / 127.
            drift = (seed_value - 0.5) * 7.0 * progress ** 1.4
            start_t = (index + gap * 0.5) / FRAGMENTS_PER_SEGMENT
            end_t = (index + 1.0 - gap * 0.5) / FRAGMENTS_PER_SEGMENT
            a = (round(x + dx * start_t + nx * drift), round(y + dy * start_t + ny * drift))
            b = (round(x + dx * end_t + nx * drift), round(y + dy * end_t + ny * drift))
            cv2.line(self._ink, a, b, color, thickness, cv2.LINE_AA)

    def _wisps(self, segment, progress, track_bounds=None):
        # The particles are paler than the ink, then dim fully within the same
        # fade interval. No per-frame spawning, integration, or stored particles.
        envelope = math.sin(math.pi * progress) ** 1.2 * (1.0 - progress) ** 0.5
        color = tuple(round((channel * .48 + 255 * .52) * envelope * .85)
                      for channel in segment.color_bgr)
        tail_color = tuple(round(channel * .28) for channel in color)
        x, y = segment.start
        dx, dy = segment.end[0] - x, segment.end[1] - y
        length = math.hypot(dx, dy)
        nx, ny = -dy / length, dx / length
        for index in range(WISPS_PER_SEGMENT):
            random_part = ((segment.seed >> (index * 11)) & 2047) / 2047.
            along = (index + .25 + random_part * .5) / WISPS_PER_SEGMENT
            direction = -1.0 if index == 0 else 1.0
            drift = direction * WISP_DRIFT_PIXELS * (.65 + random_part * .7) * progress
            curl = math.sin(random_part * math.tau + progress * 4.0) * progress * 4.0
            px = round(x + dx * along + nx * drift + curl)
            py = round(y + dy * along + ny * drift - progress * (5.0 + random_part * 6.0))
            if segment.effect_id:
                self._styled_wisp(segment, progress, index, random_part,
                                  x + dx * along, y + dy * along, color, tail_color, track_bounds)
                continue
            if 0 <= px < self.width and 0 <= py < self.height:
                tail = (round(px - nx * direction * 4 * progress),
                        round(py - ny * direction * 4 * progress + 2 * progress))
                cv2.line(self._ink, tail, (px, py), tail_color, 1, cv2.LINE_AA)
                cv2.circle(self._ink, (px, py), max(1, round(2 * (1.0 - progress))),
                           color, -1, cv2.LINE_AA)

    def _move(self, effect_id, x, y, progress, track_bounds=None):
        """Continuous spatial fields keep neighboring stroke segments joined."""
        if effect_id == 1:  # Smoke curls upward and broadens.
            return (x + math.sin(x * .025 + progress * 4) * 13 * progress,
                    y - 42 * progress + math.sin(x * .018 + progress * 3) * 6 * progress)
        if effect_id == 2:  # Drops accelerate downward.
            return x, y + 80 * progress * progress
        if effect_id == 3:  # Fine light rises at a steady speed.
            return x + math.sin(y * .025) * 6 * progress, y - 68 * progress
        if effect_id == 4:  # Spiral locally around this hand's own artwork.
            cx = (track_bounds[0] + track_bounds[1]) / 2
            cy = (track_bounds[2] + track_bounds[3]) / 2
            dx, dy = x - cx, y - cy
            angle = progress * math.pi * 1.4
            scale = 1 - .55 * progress
            c, s = math.cos(angle) * scale, math.sin(angle) * scale
            return cx + dx * c - dy * s, cy + dx * s + dy * c
        if effect_id == 5:  # A traveling wave; intensity does not pulse.
            return x, y + math.sin(x * .035 - progress * 7) * 28 * math.sin(math.pi * progress)
        return x, y

    def _styled_line(self, segment, progress, wipe_bounds):
        effect = segment.effect_id
        if effect == 0:
            self._dissolving_line(segment, progress)
            return
        remaining = 1 - progress
        x, y = segment.start
        dx, dy = segment.end[0] - x, segment.end[1] - y
        if effect == 7:
            left, right = wipe_bounds[segment.track_id][:2]
            edge = left + (right - left) * progress
            a, b = segment.start, segment.end
            if max(a[0], b[0]) < edge:
                return
            if min(a[0], b[0]) < edge and dx:
                cut = (edge, y + dy * (edge - x) / dx)
                if a[0] < edge:
                    a = cut
                else:
                    b = cut
            color = tuple(round(channel * remaining ** .45) for channel in segment.color_bgr)
            cv2.line(self._ink, tuple(map(round, a)), tuple(map(round, b)), color, STROKE_WIDTH, cv2.LINE_AA)
            if dx and min(segment.start[0], segment.end[0]) <= edge <= max(segment.start[0], segment.end[0]):
                cut_y = y + dy * (edge - x) / dx
                tip_x = edge + min(4., max(a[0], b[0]) - edge)
                tip_y = cut_y + (tip_x - edge) * dy / dx
                pale = tuple(round((channel * .35 + 255 * .65) * remaining ** .45
                                   * min(1., progress * 5)) for channel in segment.color_bgr)
                cv2.line(self._ink, (round(edge), round(cut_y)), (round(tip_x), round(tip_y)),
                         pale, STROKE_WIDTH + 1, cv2.LINE_AA)
            return
        power = 1.85 if effect == 2 else 1.25
        color = tuple(round(channel * remaining ** power) for channel in segment.color_bgr)
        thickness = max(1, round(STROKE_WIDTH * (1 - .65 * progress)))
        if effect == 6:
            # Each existing line breaks into three rotating splinters; the
            # separately emitted diamond specks still use the shared budget.
            length = math.hypot(dx, dy)
            nx, ny = -dy / length, dx / length
            for index in range(FRAGMENTS_PER_SEGMENT):
                random_part = ((segment.seed >> (index * 7)) & 127) / 127.
                angle = (random_part - .5) * 4.8 * progress
                c, s = math.cos(angle), math.sin(angle)
                along = (index + .5) / FRAGMENTS_PER_SEGMENT
                outward = (random_part - .5) * 50 * progress
                cx, cy = x + dx * along + nx * outward, y + dy * along + ny * outward
                hx = dx / (2 * FRAGMENTS_PER_SEGMENT) * (1 - .7 * progress)
                hy = dy / (2 * FRAGMENTS_PER_SEGMENT) * (1 - .7 * progress)
                rx, ry = hx * c - hy * s, hx * s + hy * c
                cv2.line(self._ink, (round(cx - rx), round(cy - ry)),
                         (round(cx + rx), round(cy + ry)), color, thickness, cv2.LINE_AA)
            return
        count = FRAGMENTS_PER_SEGMENT if effect == 5 else 1
        for index in range(count):
            a = self._move(effect, x + dx * index / count, y + dy * index / count, progress,
                           wipe_bounds[segment.track_id])
            b = self._move(effect, x + dx * (index + 1) / count, y + dy * (index + 1) / count, progress,
                           wipe_bounds[segment.track_id])
            a, b = tuple(map(round, a)), tuple(map(round, b))
            if effect == 1:
                # A soft quarter-size mist layer avoids hard-edged smoke dots.
                # The crisp component smoothly transfers into it after hold.
                gain = max(0., 1 - progress * 3)
                if gain:
                    cv2.line(self._ink, a, b, tuple(round(c * gain) for c in color),
                             STROKE_WIDTH, cv2.LINE_AA)
                small_a, small_b = self._mist_point(a), self._mist_point(b)
                shade = tuple(round(c * min(1., progress * 4)) for c in color)
                cv2.line(self._mist, small_a, small_b, shade, max(1, round(1 + 3 * progress)), cv2.LINE_AA)
                self._mist_used = True
            else:
                cv2.line(self._ink, a, b, color, thickness, cv2.LINE_AA)

    def _mist_point(self, point):
        return (round(point[0] * self._small_size[0] / self.width),
                round(point[1] * self._small_size[1] / self.height))

    def _styled_wisp(self, segment, progress, index, random_part, x, y, color, tail_color, track_bounds):
        effect = segment.effect_id
        px, py = self._move(effect, x, y, progress, track_bounds)
        if effect == 1:
            px += math.sin(random_part * math.tau + progress * 3) * 12 * progress
            py -= 14 * progress * random_part
        elif effect == 2:
            py += 35 * progress * progress * random_part
        elif effect == 3:
            px += math.sin(progress * 4 + random_part * math.tau) * 9 * progress
            py -= 20 * progress * random_part
        elif effect == 4:
            px += math.sin(random_part * math.tau) * 14 * progress
            py += math.cos(random_part * math.tau) * 14 * progress
        elif effect == 5:
            py += (random_part - .5) * 16 * progress
        elif effect == 6:
            angle = random_part * math.tau
            px += math.cos(angle) * 48 * progress
            py += math.sin(angle) * 48 * progress
        px, py = round(px), round(py)
        if not (0 <= px < self.width and 0 <= py < self.height):
            return
        if effect == 1:
            cv2.ellipse(self._mist, self._mist_point((px, py)),
                        (max(1, round(1 + 2 * progress)), 1), 0, 0, 360,
                        tuple(round(c * .7) for c in color), -1, cv2.LINE_AA)
            self._mist_used = True
        elif effect == 2:
            cv2.line(self._ink, (px, round(py - 12 * progress)), (px, py), tail_color, 1, cv2.LINE_AA)
            cv2.ellipse(self._ink, (px, py), (1, 2), 0, 0, 360, color, -1, cv2.LINE_AA)
        elif effect == 3:
            cv2.line(self._ink, (px, round(py + 15 * progress)), (px, py), color, 1, cv2.LINE_AA)
        elif effect == 6:
            cv2.ellipse(self._ink, (px, py), (max(1, round(4 * (1 - progress))), 1),
                        random_part * 180 + progress * 100, 0, 360, color, -1, cv2.LINE_AA)
        else:
            cv2.circle(self._ink, (px, py), 1, color, -1, cv2.LINE_AA)

    def _render_plan(self, now):
        """Share 96 emission slots fairly across currently fading hands.

        Temporary lists reference at most max_segments existing objects. Fixed
        image buffers are shared by every effect. Seed ranking avoids the
        round-robin alias where serial % stride selects only one of eight hands.
        """
        groups, bounds = {}, {}
        for segment in self.segments:
            lo_x, hi_x = sorted((segment.start[0], segment.end[0]))
            lo_y, hi_y = sorted((segment.start[1], segment.end[1]))
            prior = bounds.get(segment.track_id, (lo_x, hi_x, lo_y, hi_y))
            bounds[segment.track_id] = (min(lo_x, prior[0]), max(hi_x, prior[1]),
                                       min(lo_y, prior[2]), max(hi_y, prior[3]))
            if segment.effect_id != 7 and now - segment.created_at > self.hold_seconds:
                groups.setdefault(segment.track_id, []).append(segment)
        selected = set()
        if groups:
            quota, extra = divmod(MAX_WISP_SEGMENTS, len(groups))
            for index, group in enumerate(groups.values()):
                chosen = heapq.nsmallest(quota + (index < extra), group, key=lambda segment: segment.seed)
                selected.update(segment.serial for segment in chosen)
        return selected, bounds

    def render(self, now):
        """Return current artwork on black, reusing fixed buffers every frame."""
        self.advance(now)
        now = self._latest_at
        self._ink.fill(0)
        self._mist.fill(0)
        self._mist_used = False
        if not self.segments:
            self._output.fill(0)
            return self._output
        selected, wipe_bounds = self._render_plan(now)
        for segment in self.segments:
            age = max(0., now - segment.created_at)
            if age <= self.hold_seconds:
                cv2.line(self._ink, segment.start, segment.end, segment.color_bgr,
                         STROKE_WIDTH, cv2.LINE_AA)
                continue
            progress = min(1., (age - self.hold_seconds) / self.fade_seconds)
            self._styled_line(segment, progress, wipe_bounds)
            if segment.serial in selected:
                self._wisps(segment, progress, wipe_bounds[segment.track_id])
        # A small blur at quarter resolution provides soft light without a
        # full-resolution Gaussian pass or per-particle image allocations.
        cv2.resize(self._ink, self._small_size, dst=self._small, interpolation=cv2.INTER_AREA)
        cv2.GaussianBlur(self._small, (0, 0), 1.1, dst=self._blur)
        if self._mist_used:
            cv2.GaussianBlur(self._mist, (0, 0), 1.35, dst=self._small)
            cv2.addWeighted(self._blur, GLOW_STRENGTH, self._small, MIST_STRENGTH, 0., dst=self._blur)
        cv2.resize(self._blur, (self.width, self.height), dst=self._glow, interpolation=cv2.INTER_LINEAR)
        cv2.addWeighted(self._ink, 1.0, self._glow, 1. if self._mist_used else GLOW_STRENGTH,
                        0., dst=self._output)
        return self._output
