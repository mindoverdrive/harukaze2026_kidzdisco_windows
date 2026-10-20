"""Shared, steady feedback for detected hands and the inputs a scene actually uses."""
import math
import time

HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)
DARK = (12, 17, 23)
MUTED = (157, 172, 182)
WHITE = (255, 255, 255)
CYAN = (0, 225, 245)
INDEX_COLOR = (255, 214, 36)


def stage_points(hand, size, layout=None):
    """Accept Solutions, Tasks, or immutable worker-snapshot normalized points.

    Frames are already mirrored by their scene. Never mirror a second time.
    """
    points = getattr(hand, "landmark", hand)
    coords = [(float(p.x), float(p.y)) if hasattr(p, "x")
              else (float(p[0]), float(p[1])) for p in points]
    if not all(math.isfinite(x) and math.isfinite(y) for x, y in coords):
        return ()
    if layout is not None:
        from display_utils import normalized_to_stage
        return tuple(normalized_to_stage(x, y, layout) for x, y in coords)
    width, height = size
    return tuple((round(x * (width - 1)), round(y * (height - 1))) for x, y in coords)


def _geometry(hands, size, layout, focus, palm_circles):
    circles = iter(palm_circles) if palm_circles is not None else None
    for hand in hands or ():
        points = stage_points(hand, size, layout)
        explicit = next(circles, None) if circles is not None else None
        if len(points) < 21:
            continue
        wrist, middle = points[0], points[9]
        center = ((wrist[0] + middle[0]) // 2, (wrist[1] + middle[1]) // 2)
        radius = max(15, round(math.dist(wrist, middle) * 0.6))
        if explicit is not None:
            x, y, radius = explicit
            center = (round(x), round(y))
            radius = max(1, round(radius))
        indices = focus(hand) if callable(focus) else focus
        active = [points[i] for i in indices if 0 <= i < len(points)]
        yield points, center, radius, active


def _marker(draw_circle, center, scale):
    center = tuple(round(v) for v in center)
    for radius, color in ((17, DARK), (14, WHITE), (10, CYAN), (4, DARK)):
        draw_circle(color, center, max(1, round(radius * scale)), 0)


def _draw(size, hands, layout, focus, active_points, palm_focus, palm_circles,
          line, circle):
    scale = max(0.65, min(size) / 720)
    index_points = []
    for points, center, radius, active in _geometry(hands, size, layout, focus, palm_circles):
        index_points.append(points[8])
        for start, end in HAND_CONNECTIONS:
            line(DARK, points[start], points[end], max(3, round(3 * scale)))
            line(MUTED, points[start], points[end], max(1, round(scale)))
        circle(DARK, center, radius, max(3, round(4 * scale)))
        circle(MUTED, center, radius, max(1, round(scale)))
        if palm_focus:
            circle(WHITE, center, radius, max(3, round(3 * scale)))
            circle(CYAN, center, radius, max(1, round(scale)))
            _marker(circle, center, scale)
        for point in active:
            _marker(circle, point, scale)
    for point in active_points:
        _marker(circle, point, scale)
    # Draw last so another active fingertip or palm marker cannot hide the ring.
    # Hollow center preserves each scene's existing state/hand-assignment color.
    index_scale = min(scale, 1.75)
    for point in index_points:
        for radius, color, width in ((21, DARK, 7), (18, WHITE, 3),
                                     (14, INDEX_COLOR, 4)):
            circle(color, point, max(1, round(radius * index_scale)),
                   max(1, round(width * index_scale)))


def draw_focus_points(screen, points):
    """Mark explicit filtered hand inputs, or non-hand controls such as the mouth."""
    import pygame
    scale = max(0.65, min(screen.get_size()) / 720)
    for point in points:
        _marker(lambda color, center, radius, width:
                pygame.draw.circle(screen, color, center, radius, width), point, scale)


def draw_pygame(screen, hands, *, layout=None, focus=(), active_points=(),
                palm_focus=False, palm_circles=None):
    """Detected indices get yellow rings; cyan retains scene-specific inputs."""
    import pygame
    _draw(screen.get_size(), hands, layout, focus, active_points, palm_focus, palm_circles,
          lambda color, a, b, width: pygame.draw.line(screen, color, a, b, width),
          lambda color, center, radius, width:
          pygame.draw.circle(screen, color, center, radius, width))


def draw_cv2(stage_bgr, hands, *, layout=None, focus=(), active_points=(),
             palm_focus=False, palm_circles=None):
    """Equivalent BGR rendering for camera remaps and texture consumers."""
    import cv2
    _draw((stage_bgr.shape[1], stage_bgr.shape[0]), hands, layout, focus, active_points,
          palm_focus, palm_circles,
          lambda color, a, b, width: cv2.line(stage_bgr, a, b, color[::-1], width, cv2.LINE_AA),
          lambda color, center, radius, width:
          cv2.circle(stage_bgr, center, radius, color[::-1], width or -1, cv2.LINE_AA))


class PassiveHandDetector:
    """At most one 15 Hz hand detector, reusing the scene's existing camera frame."""

    def __init__(self, max_hands=2, interval=1 / 15):
        from hand_input_profile import solutions_options
        import mediapipe as mp
        self.hands = mp.solutions.hands.Hands(**solutions_options(max_hands))
        self.interval = interval
        self.last_at = None
        self.cached = ()

    def detect(self, camera_bgr):
        if camera_bgr is None:
            self.cached = ()
            self.last_at = None
            return self.cached
        now = time.monotonic()
        if self.last_at is None or now - self.last_at >= self.interval:
            import cv2
            self.cached = ()
            result = self.hands.process(cv2.cvtColor(camera_bgr, cv2.COLOR_BGR2RGB))
            self.cached = tuple(getattr(result, "multi_hand_landmarks", None) or ())
            self.last_at = now
        return self.cached

    def close(self):
        self.cached = ()
        self.hands.close()
