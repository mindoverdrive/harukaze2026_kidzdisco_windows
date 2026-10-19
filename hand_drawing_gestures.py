"""Shared upright mirrored-hand gestures for the standalone hand scenes."""
import math

from hand_tracker import HandTracker


COLOR_STABLE_SECONDS = .18
FINGER_COLORS_BGR = {
    1: (245, 220, 0),
    2: (70, 215, 255),
    3: (160, 90, 255),
    4: (110, 240, 95),
    5: (255, 135, 150),
}


def valid_hand(hand):
    points = getattr(hand, "landmark", ())
    return len(points) == 21 and all(math.isfinite(p.x) and math.isfinite(p.y) for p in points)


def finger_states(hand, handedness="Right"):
    """Existing TIP/PIP rule in palm-local coordinates, plus each side's thumb.

    Labels are stabilized by HandTracks, not used as participant identities.
    An unknown side has no reliable thumb direction; only its four fingers count.
    """
    if not valid_hand(hand):
        return (False,) * 5
    points = hand.landmark
    wrist, middle = points[0], points[9]
    ux, uy = middle.x - wrist.x, middle.y - wrist.y
    length = math.hypot(ux, uy)
    ux, uy = (ux / length, uy / length) if length > 1e-6 else (0., -1.)
    # Local up follows the palm; x points screen-right for an upright hand.
    # This keeps a rotated open hand from becoming a fist in the shape scene.
    positions = [(i, (p.x - wrist.x) * -uy + (p.y - wrist.y) * ux,
                  -(p.x - wrist.x) * ux - (p.y - wrist.y) * uy)
                 for i, p in enumerate(points)]
    thumb = (positions[4][1] < positions[3][1] if handedness == "Right" else
             positions[4][1] > positions[3][1] if handedness == "Left" else False)
    return (thumb, *(HandTracker.finger_up(positions, tip, tip - 2) for tip in (8, 12, 16, 20)))


class StableFingerCount:
    def __init__(self, stable_seconds=COLOR_STABLE_SECONDS, *, initial=0, include_zero=True):
        if not math.isfinite(stable_seconds) or stable_seconds < 0:
            raise ValueError("Finger stability time must be finite and nonnegative")
        self.stable_seconds = stable_seconds
        self.selected_count = initial
        self.include_zero = include_zero
        self.reset_candidate()

    def reset_candidate(self):
        self.candidate = None
        self.candidate_since = None

    def update(self, count, now):
        allowed = range(0 if self.include_zero else 1, 6)
        if count not in allowed:
            self.reset_candidate()
        elif count != self.candidate or self.candidate_since is None or now < self.candidate_since:
            self.candidate, self.candidate_since = count, now
            if self.stable_seconds == 0:
                self.selected_count = count
        elif now - self.candidate_since >= self.stable_seconds:
            self.selected_count = count
        return self.selected_count


class StableFingerColor(StableFingerCount):
    def __init__(self, stable_seconds=COLOR_STABLE_SECONDS):
        super().__init__(stable_seconds, initial=1, include_zero=False)
