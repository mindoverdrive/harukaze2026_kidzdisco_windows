"""Otedama's hand detector profile, without camera or inference ownership.

Keep scene-specific hand capacity and gesture/tracking logic. Handedness is a
side label, never a person ID. Tasks retains its local model and VIDEO mode.
"""
DETECTION_CONFIDENCE = 0.7
TRACKING_CONFIDENCE = 0.5
MODEL_COMPLEXITY = 1


def _capacity(value):
    if type(value) is not int or not 1 <= value <= 8:
        raise ValueError("Hand capacity must be an integer from 1 to 8")
    return value


def solutions_options(max_hands=6):
    return dict(static_image_mode=False, model_complexity=MODEL_COMPLEXITY,
                max_num_hands=_capacity(max_hands),
                min_detection_confidence=DETECTION_CONFIDENCE,
                min_tracking_confidence=TRACKING_CONFIDENCE)


def tasks_options(max_hands=6):
    return dict(num_hands=_capacity(max_hands),
                min_hand_detection_confidence=DETECTION_CONFIDENCE,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=TRACKING_CONFIDENCE)
