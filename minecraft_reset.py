"""Bounded reset gesture for the staff Minecraft scene; no camera/renderer imports.

Handedness and short spatial continuity are NOT person identity. The observation
gate rejects visible extra hands/faces, but this scene still requires one player:
an off-camera person's hand cannot be assigned to its owner by Hands/FaceMesh.
"""
from dataclasses import dataclass
import math

FIST_HOLD_SECONDS = 0.35
OPEN_WINDOW_SECONDS = 0.65
PALM_HOLD_SECONDS = 0.12
MAX_SAMPLE_GAP_SECONDS = 0.20
MAX_PARTICLES = 192
RESET_SECONDS = 1.25


@dataclass(frozen=True)
class ResetSample:
    left: str
    right: str
    left_wrist: tuple
    right_wrist: tuple
    face_center: tuple


def _point(landmark):
    point = (float(landmark.x), float(landmark.y))
    if not all(math.isfinite(v) and -0.1 <= v <= 1.1 for v in point):
        raise ValueError("Invalid landmark")
    return point


def _shape(hand):
    points = [_point(p) for p in hand.landmark]
    if len(points) != 21 or math.dist(points[0], points[9]) < 0.025:
        raise ValueError("Unreliable hand size")
    ratios = [math.dist(points[0], points[tip]) /
              max(math.dist(points[0], points[pip]), 1e-6)
              for tip, pip in zip((8, 12, 16, 20), (6, 10, 14, 18))]
    thumb_ratio = math.dist(points[4], points[17]) / max(math.dist(points[3], points[17]), 1e-6)
    if all(r < 0.88 for r in ratios) and thumb_ratio < 1.0:
        return "fist"
    thumb_open = thumb_ratio > 1.10
    if all(r > 1.18 for r in ratios) and thumb_open:
        return "palm"
    return "other"


def reset_sample(hands, faces):
    """Fail closed on incomplete, low-confidence or visibly multi-player input."""
    try:
        found = hands.multi_hand_landmarks or ()
        labels = hands.multi_handedness or ()
        visible_faces = faces.multi_face_landmarks or ()
        if len(found) != 2 or len(labels) != 2 or len(visible_faces) != 1:
            return None
        pair = {}
        for hand, handedness in zip(found, labels):
            label = handedness.classification[0]
            if (label.label not in {"Left", "Right"} or label.label in pair
                    or not math.isfinite(label.score) or label.score < 0.8):
                return None
            pair[label.label] = (_shape(hand), _point(hand.landmark[0]))
        left, right = pair["Left"], pair["Right"]
        face = _point(visible_faces[0].landmark[1])
        if (math.dist(left[1], right[1]) < 0.12
                or any(math.dist(wrist, face) > 0.75 for wrist in (left[1], right[1]))):
            return None
        return ResetSample(left[0], right[0], left[1], right[1], face)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, OverflowError):
        return None


class TwoHandReset:
    """Fresh stable fists -> bounded opening -> stable palms -> single event."""
    def __init__(self):
        self.cancel()

    def cancel(self):
        self.last_time = None
        self.previous = None
        self.fist_since = None
        self.armed = False
        self.opening_since = None
        self.palm_since = None

    def update(self, sample, now):
        if sample is None or not math.isfinite(now):
            self.cancel()
            return False
        if any(len(point) != 2 or not all(math.isfinite(v) for v in point)
               for point in (sample.left_wrist, sample.right_wrist, sample.face_center)):
            self.cancel()
            return False
        if self.last_time is not None:
            gap = now - self.last_time
            previous = self.previous
            discontinuous = (gap <= 0 or gap > MAX_SAMPLE_GAP_SECONDS + 1e-9
                             or math.dist(sample.left_wrist, previous.left_wrist) > 0.12
                             or math.dist(sample.right_wrist, previous.right_wrist) > 0.12
                             or math.dist(sample.face_center, previous.face_center) > 0.08
                             or ((sample.left_wrist[0] - sample.right_wrist[0]) *
                                 (previous.left_wrist[0] - previous.right_wrist[0]) < 0))
            if discontinuous:
                self.cancel()
        self.last_time, self.previous = now, sample
        fists = sample.left == sample.right == "fist"
        palms = sample.left == sample.right == "palm"
        if not self.armed:
            if fists:
                if self.fist_since is None:
                    self.fist_since = now
                if now - self.fist_since + 1e-9 >= FIST_HOLD_SECONDS:
                    self.armed = True
            else:
                self.fist_since = None
            return False
        if fists:
            # A failed opening attempt requires a new complete fist hold.
            if self.opening_since is not None:
                self.cancel()
                self.last_time, self.previous, self.fist_since = now, sample, now
            return False
        if self.opening_since is None:
            self.opening_since = now
        if now - self.opening_since > OPEN_WINDOW_SECONDS + 1e-9:
            self.cancel()
            return False
        if palms:
            if self.palm_since is None:
                self.palm_since = now
            if now - self.palm_since + 1e-9 >= PALM_HOLD_SECONDS:
                self.cancel()
                return True
        else:
            self.palm_since = None
        return False
