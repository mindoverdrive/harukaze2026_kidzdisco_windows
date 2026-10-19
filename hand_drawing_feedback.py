"""Presentation-only color guidance, keyed by the existing per-hand tracks."""
import math

import cv2

from hand_drawing_gestures import FINGER_COLORS_BGR
from transition_overlay import navigation_regions


DARK = (22, 18, 15)
WHITE = (239, 244, 248)
MUTED = (174, 181, 190)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _scale(size):
    return max(.62, min(1.5, size[0] / 1280, size[1] / 720))


def _overlap(a, b):
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
            and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def legend_rect(size):
    scale = _scale(size)
    margin = round(14 * scale)
    width, height = round(358 * scale), round(66 * scale)
    return margin, size[1] - height - round(35 * scale), width, height


def layout_badges(size, inputs, active_points=()):
    """Place compact labels without changing tracking, gestures, or hit areas.

    Stable track order makes detector reordering irrelevant. Prefer the wrist;
    crowded wrists can use the nearest free cell with a connecting hairline.
    """
    width, height = size
    scale = _scale(size)
    margin, gap = max(4, round(10 * scale)), max(3, round(6 * scale))
    bw, bh = round(100 * scale), round(34 * scale)
    top, bottom = round(height * .20) + margin, height - round(28 * scale)
    forbidden = [*navigation_regions(width, height).values(), legend_rect(size)]
    radius = round(20 * scale)
    markers = [(x - radius, y - radius, radius * 2, radius * 2)
               for x, y in active_points]
    used, placed = [], []
    grid = [(x, y) for y in range(top, bottom - bh + 1, bh + gap)
            for x in range(margin, width - margin - bw + 1, bw + gap)]
    for hand in sorted(inputs, key=lambda item: item.track_id):
        x, y = hand.anchor
        preferred = [(x + round(22 * scale), y + round(8 * scale)),
                     (x - bw - round(22 * scale), y + round(8 * scale)),
                     (x - bw // 2, y + round(25 * scale)),
                     (x - bw // 2, y - bh - round(24 * scale))]
        candidates = [(max(margin, min(width - margin - bw, int(cx))),
                       max(top, min(bottom - bh, int(cy))), bw, bh)
                      for cx, cy in preferred + grid]
        available = [rect for rect in candidates
                     if not any(_overlap(rect, other) for other in forbidden + markers + used)]
        if not available:
            # Never obscure navigation or another hand just to force a label.
            continue
        rect = min(available, key=lambda r:
                   math.hypot(r[0] + r[2] / 2 - x, r[1] + r[3] / 2 - y))
        used.append(rect)
        placed.append((hand, rect))
    return tuple(placed)


def _panel(image, rect, border):
    x, y, width, height = rect
    roi = image[y:y + height, x:x + width]
    background = roi.copy()
    background[:] = DARK
    cv2.addWeighted(roi, .18, background, .82, 0, dst=roi)
    cv2.rectangle(image, (x, y), (x + width - 1, y + height - 1), border, 1, cv2.LINE_AA)


def _hand_icon(image, origin, count, scale):
    x, y = origin
    # Four upright fingers; the thumb opens only for the existing count five.
    for index, length in enumerate((12, 16, 14, 10), 1):
        px = x + round((index - 1) * 5 * scale)
        length = length if count >= index else 3
        cv2.line(image, (px, y), (px, y - round(length * scale)), WHITE,
                 max(1, round(2 * scale)), cv2.LINE_AA)
    palm = (x, y, max(1, round(15 * scale)), max(1, round(9 * scale)))
    cv2.rectangle(image, (palm[0], palm[1]),
                  (palm[0] + palm[2], palm[1] + palm[3]), WHITE, 1, cv2.LINE_AA)
    if count == 5:
        cv2.line(image, (x, y + round(7 * scale)),
                 (x - round(7 * scale), y - round(3 * scale)), WHITE,
                 max(1, round(2 * scale)), cv2.LINE_AA)


def draw_color_guidance(image, inputs, active_points=()):
    """Use the stabilized count that actually selects each hand's ink color."""
    height, width = image.shape[:2]
    size, scale = (width, height), _scale((width, height))
    blocked = [*navigation_regions(width, height).values(), legend_rect(size)]
    radius = round(20 * scale)
    blocked.extend((x - radius, y - radius, radius * 2, radius * 2)
                   for x, y in active_points)
    for hand, rect in layout_badges(size, inputs, active_points):
        x, y, bw, bh = rect
        color = FINGER_COLORS_BGR[hand.selected_count]
        anchor = (max(0, min(width - 1, round(hand.anchor[0]))),
                  max(0, min(height - 1, round(hand.anchor[1]))))
        target = (max(x, min(x + bw - 1, anchor[0])),
                  max(y, min(y + bh - 1, anchor[1])))
        if not any(cv2.clipLine(tuple(map(int, area)), anchor, target)[0] for area in blocked):
            cv2.line(image, anchor, target, DARK, max(2, round(3 * scale)), cv2.LINE_AA)
            cv2.line(image, anchor, target, color, 1, cv2.LINE_AA)
        _panel(image, rect, color)
        cv2.circle(image, (x + round(15 * scale), y + bh // 2),
                   max(3, round(7 * scale)), color, -1, cv2.LINE_AA)
        cv2.putText(image, str(hand.selected_count),
                    (x + round(30 * scale), y + round(24 * scale)), FONT,
                    .66 * scale, WHITE, max(1, round(2 * scale)), cv2.LINE_AA)
        label = f"H{hand.track_id} {(hand.handedness or '?')[0]}"
        cv2.putText(image, label, (x + round(53 * scale), y + round(22 * scale)),
                    FONT, .36 * scale, WHITE, 1, cv2.LINE_AA)

    rect = legend_rect(size)
    _panel(image, rect, MUTED)
    x, y, _, _ = rect
    cv2.putText(image, 'FINGERS  ->  COLOR', (x + round(10 * scale), y + round(15 * scale)),
                FONT, .36 * scale, WHITE, 1, cv2.LINE_AA)
    for index, (count, color) in enumerate(FINGER_COLORS_BGR.items()):
        left, baseline = x + round((12 + index * 70) * scale), y + round(47 * scale)
        _hand_icon(image, (left, baseline), count, scale)
        cv2.putText(image, str(count), (left + round(20 * scale), baseline + round(6 * scale)),
                    FONT, .45 * scale, WHITE, 1, cv2.LINE_AA)
        cv2.circle(image, (left + round(45 * scale), baseline),
                   max(3, round(7 * scale)), color, -1, cv2.LINE_AA)
    hint = ('INDEX: DRAW | 1-5: COLOR' if width < 600 else
            'EACH HAND: 1-5 FINGERS = COLOR | INDEX: DRAW | ESC/Q: EXIT')
    cv2.putText(image, hint, (round(14 * scale), height - round(12 * scale)),
                FONT, .42 * scale, WHITE, 1, cv2.LINE_AA)
