"""Standalone hand-following shapes: 1 ring, 2 lens, 3 triangle, 4 square, 5 star."""
import argparse
from dataclasses import dataclass
import math

import cv2
import numpy as np

import display_utils
from hand_drawing_app import (
    CAMERA_BRIGHTNESS, DEFAULT_HEIGHT, DEFAULT_WIDTH, DrawingStroke,
    MAX_HANDS, MAX_INPUT_GAP_SECONDS, run_app,
)
from hand_drawing_effects import EFFECT_NAMES
from hand_drawing_gestures import COLOR_STABLE_SECONDS, FINGER_COLORS_BGR, StableFingerCount, finger_states
from hand_drawing_tracking import HandTracks
from hand_focus_overlay import draw_cv2 as draw_hand_overlay


WINDOW_NAME = "Hand Shapes App"
SHAPE_NAMES = {1: "Ring", 2: "Lens", 3: "Triangle", 4: "Square", 5: "Star"}
FOLLOW_SECONDS = .065
SHRINK_SECONDS = .14
HAND_PADDING = 1.10
SHAPE_FILL_ALPHA = .12
DEFAULT_HOLD_SECONDS = 0.0
DEFAULT_FADE_SECONDS = 3.0
DEFAULT_MAX_SEGMENTS = 1920


def _canonical_shape(count):
    if count == 1:
        return tuple((math.cos(i * math.tau / 40), math.sin(i * math.tau / 40)) for i in range(40))
    if count == 2:
        # Two opposed arcs meet at the fingertips-facing and wrist-facing ends.
        # The pointed lens remains visibly different from the circular ring.
        edge = [(1.3 * 2 * (i / 20) * (1 - i / 20), 2 * i / 20 - 1) for i in range(21)]
        return tuple(edge + [(-x, y) for x, y in edge[-2:0:-1]])
    if count == 3:
        return tuple((math.cos(math.pi / 2 + i * math.tau / 3),
                      math.sin(math.pi / 2 + i * math.tau / 3)) for i in range(3))
    if count == 4:
        return ((-1., -1.), (1., -1.), (1., 1.), (-1., 1.))
    if count == 5:
        return tuple(((1. if i % 2 == 0 else .52) * math.cos(math.pi / 2 + i * math.pi / 5),
                      (1. if i % 2 == 0 else .52) * math.sin(math.pi / 2 + i * math.pi / 5))
                     for i in range(10))
    raise ValueError("Shape count must be 1 through 5")


CANONICAL_SHAPES = {count: _canonical_shape(count) for count in SHAPE_NAMES}


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _required_scale(local_points, polygon):
    """Scale a star-shaped outline to enclose every projected hand landmark."""
    required = 18.
    for point in local_points:
        distance = math.hypot(*point)
        if distance < 1e-8:
            continue
        ray = (point[0] / distance, point[1] / distance)
        crossings = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            edge = (b[0] - a[0], b[1] - a[1])
            denominator = _cross(ray, edge)
            if abs(denominator) < 1e-10:
                continue
            along_ray = _cross(a, edge) / denominator
            along_edge = _cross(a, ray) / denominator
            if along_ray > 1e-8 and -1e-8 <= along_edge <= 1 + 1e-8:
                crossings.append(along_ray)
        if crossings:
            required = max(required, distance / min(crossings))
    return required * HAND_PADDING


@dataclass(frozen=True)
class ShapePose:
    center: tuple
    angle: float
    scale: float


@dataclass(frozen=True)
class HandShape:
    track_id: int
    effect_id: int
    handedness: str | None
    selected_count: int
    color_bgr: tuple
    pose: ShapePose
    points: tuple
    direction_tick: tuple
    palm: tuple

    @property
    def edges(self):
        outline = tuple(zip(self.points, self.points[1:] + self.points[:1]))
        return outline + ((self.direction_tick,) if self.direction_tick else ())


@dataclass(frozen=True)
class ShapeFrame:
    hands: tuple
    active_points: tuple
    strokes: tuple
    shapes: tuple


def shape_geometry(hand, layout, count, previous=None, dt=0.):
    """Pixel-space palm basis preserves the camera's aspect ratio and mirror."""
    points = tuple(display_utils.normalized_to_stage(point.x, point.y, layout)
                   for point in hand.landmark)
    wrist, middle = points[0], points[9]
    palm = ((wrist[0] + middle[0]) / 2, (wrist[1] + middle[1]) / 2)
    dx, dy = middle[0] - wrist[0], middle[1] - wrist[1]
    angle = math.atan2(dy, dx) if math.hypot(dx, dy) > 1e-6 else (
        previous.angle if previous is not None else -math.pi / 2)
    up = (math.cos(angle), math.sin(angle))
    right = (-up[1], up[0])
    local = [((x - palm[0]) * right[0] + (y - palm[1]) * right[1],
              (x - palm[0]) * up[0] + (y - palm[1]) * up[1]) for x, y in points]
    middle_x = (min(p[0] for p in local) + max(p[0] for p in local)) / 2
    middle_y = (min(p[1] for p in local) + max(p[1] for p in local)) / 2
    center = (palm[0] + right[0] * middle_x + up[0] * middle_y,
              palm[1] + right[1] * middle_x + up[1] * middle_y)
    if previous is not None and dt > 0:
        weight = -math.expm1(-dt / FOLLOW_SECONDS)
        center = tuple(old + (new - old) * weight for old, new in zip(previous.center, center))
        angle = previous.angle + math.atan2(math.sin(angle - previous.angle),
                                           math.cos(angle - previous.angle)) * weight
    up, right = (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))
    local = [((x - center[0]) * right[0] + (y - center[1]) * right[1],
              (x - center[0]) * up[0] + (y - center[1]) * up[1]) for x, y in points]
    canonical = CANONICAL_SHAPES[count]
    scale = _required_scale(local, canonical)
    if previous is not None and dt > 0:
        # Grow immediately enough to cover the current hand; shrink gently.
        scale = max(scale, previous.scale + (scale - previous.scale) * -math.expm1(-dt / SHRINK_SECONDS))
    pose = ShapePose(center, angle, scale)
    outline = tuple((center[0] + scale * (right[0] * x + up[0] * y),
                     center[1] + scale * (right[1] * x + up[1] * y)) for x, y in canonical)
    tick = (tuple(center[a] + up[a] * scale * .89 for a in (0, 1)),
            tuple(center[a] + up[a] * scale * 1.13 for a in (0, 1))) if count == 1 else ()
    return pose, outline, tick, palm


class ShapeInput:
    """At most eight live outlines; only transitions enter the shared fade history."""
    def __init__(self, width, height, stable_seconds=COLOR_STABLE_SECONDS, rng=None):
        if (not isinstance(width, int) or not isinstance(height, int)
                or width < 1 or height < 1):
            raise ValueError("Shape dimensions must be positive integers")
        StableFingerCount(stable_seconds)
        self.width, self.height, self.stable_seconds = width, height, stable_seconds
        self.tracker = HandTracks(max_hands=MAX_HANDS, rng=rng)
        self.counts, self.poses, self.current = {}, {}, {}
        self.last_update = None

    def reset(self):
        """Break interpolation, retaining outlines until update can retire them once."""
        self.poses.clear()
        for count in self.counts.values():
            count.reset_candidate()
        self.tracker.break_continuity()
        self.last_update = None

    def _retire(self, key, strokes):
        shape = self.current.pop(key, None)
        if shape is not None:
            for start, end in shape.edges:
                # Clip like the live OpenCV outline. Ink's endpoint clamping
                # alone would turn wholly off-screen edges into false borders.
                visible, a, b = cv2.clipLine((0, 0, self.width, self.height),
                                            tuple(map(round, start)), tuple(map(round, end)))
                if visible and a != b:
                    strokes.append(DrawingStroke(a, b, shape.color_bgr, shape.effect_id, shape.track_id))

    def update(self, results, layout, now):
        if not math.isfinite(now):
            raise ValueError("Observation time must be finite")
        dt = None if self.last_update is None else now - self.last_update
        if dt is None or dt <= 0 or dt > MAX_INPUT_GAP_SECONDS:
            self.reset()
            dt = 0.
        self.last_update = now
        tracked = self.tracker.update(results if layout is not None else None, now)
        visible = {item.track_id for item in tracked}
        strokes = []
        for key in tuple(self.current):
            if key not in visible:
                self._retire(key, strokes)
                self.poses.pop(key, None)
        retained = set(self.tracker.tracks)
        self.counts = {key: count for key, count in self.counts.items() if key in retained}
        self.poses = {key: pose for key, pose in self.poses.items() if key in visible}
        for key, count in self.counts.items():
            if key not in visible:
                count.reset_candidate()
        for item in tracked:
            key = item.track_id
            count = self.counts.setdefault(key, StableFingerCount(self.stable_seconds))
            if not item.continuous:
                count.reset_candidate()
                self.poses.pop(key, None)
            chosen = count.update(sum(finger_states(item.hand, item.handedness)), now)
            old = self.current.get(key)
            if old is not None and old.selected_count != chosen:
                self._retire(key, strokes)
            if not chosen:
                self.poses.pop(key, None)
                continue
            previous = self.poses.get(key)
            pose, outline, tick, palm = shape_geometry(item.hand, layout, chosen, previous, dt)
            self.poses[key] = pose
            self.current[key] = HandShape(key, item.effect_id, item.handedness, chosen,
                                         FINGER_COLORS_BGR[chosen], pose, outline, tick, palm)
        shapes = tuple(self.current[key] for key in sorted(self.current))
        return ShapeFrame(tuple(item.hand for item in tracked), tuple(shape.palm for shape in shapes),
                          tuple(strokes), shapes)


def render_frame(stage, ink, feedback, layout, now):
    image = cv2.convertScaleAbs(stage, alpha=CAMERA_BRIGHTNESS)
    cv2.add(image, ink.render(now), dst=image)
    shapes = getattr(feedback, "shapes", ())
    if shapes:
        tinted = image.copy()
        for shape in shapes:
            polygon = np.rint(shape.points).astype(np.int32)
            cv2.fillPoly(tinted, [polygon], shape.color_bgr, cv2.LINE_AA)
        cv2.addWeighted(tinted, SHAPE_FILL_ALPHA, image, 1 - SHAPE_FILL_ALPHA, 0, dst=image)
        for shape in shapes:
            polygon = np.rint(shape.points).astype(np.int32)
            cv2.polylines(image, [polygon], True, (10, 15, 20), 8, cv2.LINE_AA)
            cv2.polylines(image, [polygon], True, shape.color_bgr, 5, cv2.LINE_AA)
            bright = tuple(round(channel * .45 + 255 * .55) for channel in shape.color_bgr)
            cv2.polylines(image, [polygon], True, bright, 1, cv2.LINE_AA)
            if shape.direction_tick:
                a, b = (tuple(map(round, point)) for point in shape.direction_tick)
                cv2.line(image, a, b, (10, 15, 20), 8, cv2.LINE_AA)
                cv2.line(image, a, b, bright, 3, cv2.LINE_AA)
    draw_hand_overlay(image, feedback.hands, layout=layout, focus=(), active_points=feedback.active_points)
    for count, name in SHAPE_NAMES.items():
        x = round(14 + (count - 1) * min(117, (image.shape[1] - 28) / 5))
        text_scale = min(.43, max(.23, (image.shape[1] - 28) / 1400))
        cv2.putText(image, f"{count}: {name.upper()}", (x, 28), cv2.FONT_HERSHEY_SIMPLEX,
                    text_scale, FINGER_COLORS_BGR[count], 1, cv2.LINE_AA)
    for shape in shapes:
        x, y = map(round, shape.palm)
        origin = (max(5, min(image.shape[1] - 175, x - 55)),
                  max(54, min(image.shape[0] - 38, y + 30)))
        label = f"H{shape.track_id} {shape.selected_count}: {EFFECT_NAMES[shape.effect_id]}"
        cv2.putText(image, label, origin, cv2.FONT_HERSHEY_SIMPLEX, .36, (8, 10, 12), 3, cv2.LINE_AA)
        cv2.putText(image, label, origin, cv2.FONT_HERSHEY_SIMPLEX, .36, shape.color_bgr, 1, cv2.LINE_AA)
    hint = ("1-5: SHAPES   FIST: FADE   ESC/Q: EXIT" if image.shape[1] < 600 else
            "1-5 FINGERS: SHAPES   FIST: FADE   UP TO 8 HANDS   ESC/Q: EXIT")
    cv2.putText(image, hint, (14, image.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX,
                .35 if image.shape[1] < 600 else .42, (210, 220, 225), 1, cv2.LINE_AA)
    return image


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--hold-seconds", type=float, default=DEFAULT_HOLD_SECONDS)
    parser.add_argument("--fade-seconds", type=float, default=DEFAULT_FADE_SECONDS)
    parser.add_argument("--max-segments", type=int, default=DEFAULT_MAX_SEGMENTS)
    parser.add_argument("--count-stable-ms", type=float, default=COLOR_STABLE_SECONDS * 1000)
    args = parser.parse_args(argv)
    if not (320 <= args.width <= 3840 and 240 <= args.height <= 2160):
        parser.error("Preview size must be 320..3840 by 240..2160")
    controller = ShapeInput(args.width, args.height, args.count_stable_ms / 1000)
    run_app(width=args.width, height=args.height, fullscreen=args.fullscreen,
            hold_seconds=args.hold_seconds, fade_seconds=args.fade_seconds,
            max_segments=args.max_segments, stable_seconds=args.count_stable_ms / 1000,
            controller=controller, renderer=render_frame, window_name=WINDOW_NAME)


if __name__ == "__main__":
    main()
