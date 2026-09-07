"""Display-only capsule perimeter progress; no gesture timing or state mutation."""
import colorsys
import math


def capsule_point(rect, fraction):
    x, y, w, h = rect
    r = (h - 1) / 2
    left, right = x + r, x + w - 1 - r
    line = right - left
    distance = max(0, min(1, fraction)) * (2 * line + 2 * math.pi * r)
    if distance <= line / 2:
        return (x + (w - 1) / 2 + distance, y)
    distance -= line / 2
    if distance <= math.pi * r:
        a = -math.pi / 2 + distance / r
        return (right + r * math.cos(a), y + r + r * math.sin(a))
    distance -= math.pi * r
    if distance <= line:
        return (right - distance, y + h - 1)
    distance -= line
    if distance <= math.pi * r:
        a = math.pi / 2 + distance / r
        return (left + r * math.cos(a), y + r + r * math.sin(a))
    return (left + distance - math.pi * r, y)


def draw_charge(screen, pygame, rect, progress, now, offset=0):
    progress = max(0, min(1, progress))
    if progress <= 0:
        return
    segments = 128
    count = math.ceil(progress * segments)
    points = [capsule_point(rect, min(progress, i / segments)) for i in range(count + 1)]
    points = [(round(x), round(y)) for x, y in points]
    stroke = max(2, round(rect[3] / 40))
    pygame.draw.lines(screen, (10, 15, 26), False, points, stroke + 4)
    for i in range(count):
        hue = (offset + now * .035 + i / segments * .85) % 1
        color = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(hue, .68, 1))
        pygame.draw.line(screen, color, points[i], points[i + 1], stroke)
    pygame.draw.circle(screen, (246, 250, 255), points[-1], max(2, stroke // 2))
