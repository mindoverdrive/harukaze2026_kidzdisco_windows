"""Hand-following shapes, standalone or managed: ring, lens, triangle, square, star."""
import argparse
from dataclasses import dataclass
import math

import cv2
import numpy as np

import display_utils
import scene_control
from hand_drawing_app import (
    CAMERA_BRIGHTNESS, DEFAULT_HEIGHT, DEFAULT_WIDTH, DrawingStroke, HandInput,
    MAX_HANDS, MAX_INPUT_GAP_SECONDS, run_app,
)
from hand_drawing_effects import EFFECT_NAMES
from hand_drawing_gestures import COLOR_STABLE_SECONDS, FINGER_COLORS_BGR, StableFingerCount, finger_states
from hand_drawing_tracking import HandTracks
from hand_focus_overlay import draw_cv2 as draw_hand_overlay
from hand_drawing_feedback import draw_color_guidance


WINDOW_NAME = "Hand Shapes App"
SHAPE_NAMES = {1: "Ring", 2: "Lens", 3: "Triangle", 4: "Square", 5: "Star"}
FOLLOW_SECONDS = .065
SHRINK_SECONDS = .14
HAND_PADDING = 1.10
SHAPE_FILL_ALPHA = .12
DEFAULT_HOLD_SECONDS = 0.0
DEFAULT_FADE_SECONDS = 3.0
DEFAULT_MAX_SEGMENTS = 1920
MORPH_SECONDS = .32
MORPH_POINTS = 80


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


def radial_outline(polygon):
    """Corresponding rays avoid twists when polygons have different vertex counts."""
    output = []
    for index in range(MORPH_POINTS):
        angle = math.tau * index / MORPH_POINTS
        ray = (math.cos(angle), math.sin(angle))
        hits = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            edge = (b[0] - a[0], b[1] - a[1])
            denominator = _cross(ray, edge)
            if abs(denominator) < 1e-10:
                continue
            distance, along = _cross(a, edge) / denominator, _cross(a, ray) / denominator
            if distance > 0 and -1e-8 <= along <= 1 + 1e-8:
                hits.append(distance)
        radius = min(hits)
        output.append((ray[0] * radius, ray[1] * radius))
    return tuple(output)


RADIAL_SHAPES = {count: radial_outline(polygon) for count, polygon in CANONICAL_SHAPES.items()}


@dataclass(frozen=True)
class ShapeMorph:
    source: tuple
    target_count: int
    started_at: float

    def outline(self, now):
        progress = min(1., max(0., (now - self.started_at) / MORPH_SECONDS))
        weight = progress * progress * (3 - 2 * progress)
        # A single damped squash/stretch, never an ongoing pulse.
        bounce = math.sin(math.tau * progress) * (1 - progress) ** 2
        sx, sy = 1 + .12 * bounce, 1 - .08 * bounce
        return tuple(((a[0] + (b[0] - a[0]) * weight) * sx,
                      (a[1] + (b[1] - a[1]) * weight) * sy)
                     for a, b in zip(self.source, RADIAL_SHAPES[self.target_count]))


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
    retirement_points: tuple = ()
    finger_mask: tuple = ()

    @property
    def edges(self):
        points = self.retirement_points or self.points
        outline = tuple(zip(points, points[1:] + points[:1]))
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


def morph_geometry(hand, layout, pose, polygon):
    """Keep the animated outline covering the hand even during a squash."""
    up = (math.cos(pose.angle), math.sin(pose.angle))
    right = (-up[1], up[0])
    points = [display_utils.normalized_to_stage(p.x, p.y, layout) for p in hand.landmark]
    local = [((x - pose.center[0]) * right[0] + (y - pose.center[1]) * right[1],
              (x - pose.center[0]) * up[0] + (y - pose.center[1]) * up[1]) for x, y in points]
    scale = _required_scale(local, polygon)
    return tuple((pose.center[0] + scale * (right[0] * x + up[0] * y),
                  pose.center[1] + scale * (right[1] * x + up[1] * y)) for x, y in polygon)


class ShapeInput:
    """Eight live morphing outlines; fist/loss enter the bounded fade history."""
    def __init__(self, width, height, stable_seconds=COLOR_STABLE_SECONDS, rng=None):
        if (not isinstance(width, int) or not isinstance(height, int)
                or width < 1 or height < 1):
            raise ValueError("Shape dimensions must be positive integers")
        StableFingerCount(stable_seconds)
        self.width, self.height, self.stable_seconds = width, height, stable_seconds
        self.tracker = HandTracks(max_hands=MAX_HANDS, rng=rng)
        self.counts, self.poses, self.current = {}, {}, {}
        self.morphs = {}
        self.layout_signature = None
        self.last_update = None

    def reset(self):
        """Break interpolation, retaining outlines until update can retire them once."""
        self.poses.clear()
        self.morphs.clear()
        for count in self.counts.values():
            count.reset_candidate()
        self.tracker.break_continuity()
        self.last_update = None

    def close(self):
        """Release scene-owned animation/tracking data after the shared runner exits."""
        self.morphs.clear()
        self.counts.clear()
        self.poses.clear()
        self.current.clear()
        self.tracker.reset()
        self.last_update = self.layout_signature = None

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
        if layout is not None:
            signature = tuple(layout[k] for k in ('stage_width', 'stage_height', 'base_width', 'base_height'))
            if self.layout_signature is not None and signature != self.layout_signature:
                # Never interpolate or retire stale pixel coordinates into a new stage.
                self.poses.clear()
                self.current.clear()
            self.width, self.height = layout['stage_width'], layout['stage_height']
            self.layout_signature = signature
        tracked = self.tracker.update(results if layout is not None else None, now)
        visible = {item.track_id for item in tracked}
        strokes = []
        for key in tuple(self.current):
            if key not in visible:
                self._retire(key, strokes)
                self.poses.pop(key, None)
        retained = set(self.tracker.tracks)
        self.counts = {key: count for key, count in self.counts.items() if key in retained}
        self.morphs = {key: morph for key, morph in self.morphs.items()
                       if key in retained and now - morph.started_at < MORPH_SECONDS}
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
            prior = count.selected_count
            states = finger_states(item.hand, item.handedness)
            chosen = count.update(sum(states), now)
            if chosen != prior:
                if chosen:
                    source = (self.morphs[key].outline(now) if key in self.morphs else RADIAL_SHAPES[prior or chosen])
                    self.morphs[key] = ShapeMorph(source, chosen, now)
                else:
                    self.morphs.pop(key, None)
            old = self.current.get(key)
            if old is not None and not chosen:
                self._retire(key, strokes)
            if not chosen:
                self.poses.pop(key, None)
                continue
            previous = self.poses.get(key)
            pose, outline, tick, palm = shape_geometry(item.hand, layout, chosen, previous, dt)
            self.poses[key] = pose
            retirement = outline
            if key in self.morphs:
                outline = morph_geometry(item.hand, layout, pose, self.morphs[key].outline(now))
            self.current[key] = HandShape(key, item.effect_id, item.handedness, chosen,
                                         FINGER_COLORS_BGR[chosen], pose, outline, tick, palm, retirement,
                                         tuple(states))
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
    inputs = tuple(HandInput(s.track_id, s.effect_id, s.handedness, s.palm,
                             s.selected_count, s.palm, s.finger_mask) for s in shapes)
    draw_color_guidance(image, inputs, feedback.active_points, shape_outlines=CANONICAL_SHAPES)
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
    production = scene_control._child_control is not None
    width, height = display_utils.get_stage_size() if production else (args.width, args.height)
    controller = ShapeInput(width, height, args.count_stable_ms / 1000)
    try:
        run_app(width=width, height=height, fullscreen=args.fullscreen,
                hold_seconds=args.hold_seconds, fade_seconds=args.fade_seconds,
                max_segments=args.max_segments, stable_seconds=args.count_stable_ms / 1000,
                controller=controller, renderer=render_frame, window_name=WINDOW_NAME,
                production=production)
    finally:
        controller.close()


if __name__ == "__main__":
    main()
