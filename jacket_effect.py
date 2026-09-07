"""Bounded, camera-free garment-color flow and stillness crystallization."""

import colorsys
from dataclasses import dataclass
import math
import cv2
import numpy as np


@dataclass(eq=False)
class _Body:
    center: tuple
    anchor: tuple
    color: np.ndarray
    area: float = 0.0
    energy: float = 0.0
    quiet: float = 0.0
    crystal: float = 0.0
    phase: float = 0.0
    motion_center: tuple = None
    age: float = 0.0


def flow_motifs(x, y, phase, age, energy):
    """Three interwoven fields with continuous, differently paced evolution."""
    drift = age * .19
    warp_x = x + (8 + 6 * energy) * np.sin(y * .025 + drift)
    warp_y = y + 10 * np.sin(x * .021 - drift * math.sqrt(2))
    ribbon = (.5 + .5 * np.sin(warp_x * .055 +
              np.sin(warp_y * .028 + phase) * 2.2 - phase * 3)) ** 5
    # Moving ring centers are bent by the ribbon field rather than stamped on top.
    cx = 36 * math.sin(drift * .73)
    cy = 28 * math.cos(drift * .91)
    radius = np.sqrt((warp_x - cx) ** 2 + (warp_y - cy) ** 2)
    rings = (.5 + .5 * np.sin(radius * .092 - drift * math.sqrt(3)
                             + ribbon * 1.8)) ** 7
    # Crossed diagonal threads form diamonds; rings open and close their weave.
    diagonal_a = np.sin((warp_x + warp_y) * .060 + drift * .83 + rings * 1.4)
    diagonal_b = np.sin((warp_x - warp_y) * .060 - drift * 1.13 - ribbon)
    weave = (.5 + .5 * diagonal_a * diagonal_b) ** 5
    return ribbon, rings, weave


class JacketFlow:
    MAX_BODIES = 4
    STILL_SECONDS = 2.0
    CRYSTAL_SECONDS = 3.0

    def __init__(self, size):
        self.size = tuple(map(int, size))
        if len(self.size) != 2 or min(self.size) <= 0 or max(self.size) > 640:
            raise ValueError("Jacket processing dimensions must be between 1 and 640")
        width, height = self.size
        self._y, self._x = np.mgrid[:height, :width].astype(np.float32)
        self.bodies = []
        self._previous_gray = None
        self._previous_mask = None
        self._last_time = None

    def clear(self):
        self.bodies = []
        self._previous_gray = None
        self._previous_mask = None
        self._last_time = None

    def render(self, frame, probability, now):
        """Return BGR pattern and alpha; absent/invalid masks leave live video intact."""
        width, height = self.size
        if frame.shape != (height, width, 3):
            raise ValueError("Jacket frame must match the processing size")
        color_layer = np.zeros_like(frame)
        alpha = np.zeros((height, width), dtype=np.float32)
        if probability is None or not math.isfinite(now):
            self.clear()
            return color_layer, alpha
        probability = np.asarray(probability, dtype=np.float32)
        if probability.shape != (height, width):
            raise ValueError("Jacket segmentation must match the camera frame")
        probability = np.nan_to_num(probability, nan=0.0, posinf=0.0, neginf=0.0)
        binary = (probability > .60).astype(np.uint8)
        count, labels, stats, centers = cv2.connectedComponentsWithStats(binary, connectivity=8)
        minimum_area = max(24, round(width * height * .008))
        selected = sorted((index for index in range(1, count) if stats[index, cv2.CC_STAT_AREA] >= minimum_area),
                          key=lambda index: int(stats[index, cv2.CC_STAT_AREA]), reverse=True)[:self.MAX_BODIES]
        if not selected:
            self.clear()
            return color_layer, alpha
        gap = None if self._last_time is None else now - self._last_time
        dt = min(.2, max(0.0, gap)) if gap is not None else 0.0
        if gap is not None and (gap < 0 or gap > .5):
            self.clear()
            dt = 0.0
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        difference = None if self._previous_gray is None else cv2.absdiff(gray, self._previous_gray)
        unmatched = list(self.bodies)
        current = []
        for index in selected:
            left, top, body_width, body_height, _area = map(int, stats[index])
            right, bottom = left + body_width, top + body_height
            center = tuple(map(float, centers[index]))
            component = labels[top:bottom, left:right] == index
            # Sample central upper torso pixels, excluding the surrounding scene.
            sx0, sx1 = left + body_width * 3 // 10, left + body_width * 7 // 10 + 1
            sy0, sy1 = top + body_height * 3 // 10, top + body_height * 6 // 10 + 1
            samples = frame[sy0:sy1, sx0:sx1][labels[sy0:sy1, sx0:sx1] == index]
            if samples.size == 0:
                samples = frame[top:bottom, left:right][component]
            garment = np.median(samples, axis=0).astype(np.float32)
            body = min(unmatched, key=lambda item: math.dist(item.center, center)) if unmatched else None
            if body is not None and math.dist(body.center, center) > max(20.0, width * .22):
                body = None
            if body is None:
                body = _Body(center, center, garment, area=float(_area))
                movement = 0.0
            else:
                unmatched.remove(body)
                # Segment boundaries jitter on a stationary person. Estimate speed
                # from a low-pass center, without changing the visible flow anchor.
                previous_motion_center = body.motion_center or body.center
                motion_blend = 1.0 - math.exp(-dt / .30)
                motion_center = tuple(old + (value - old) * motion_blend
                                      for old, value in zip(previous_motion_center, center))
                speed = math.dist(previous_motion_center, motion_center) / max(dt * width, 1e-6) if dt else 0.0
                body.motion_center = motion_center
                image_motion = (float(difference[top:bottom, left:right][component].mean())
                                if difference is not None else 0.0)
                mask_motion = (float(np.mean(binary[top:bottom, left:right] != self._previous_mask[top:bottom, left:right]))
                               if self._previous_mask is not None else 0.0)
                area_motion = abs(_area - body.area) / max(body.area, 1.0)
                movement = min(1.0, max(speed * 2.5, (image_motion - 2.5) / 22.0,
                                        mask_motion * 3.0, area_motion * 2.0, 0.0))
                body.color += (garment - body.color) * (1.0 - math.exp(-dt / .8))
            body.center = center
            if body.motion_center is None:
                body.motion_center = center
            body.area = float(_area)
            lag = 1.0 - math.exp(-dt / .42)
            body.anchor = tuple(old + (value - old) * lag for old, value in zip(body.anchor, center))
            body.energy += (movement - body.energy) * (1.0 - math.exp(-dt / (.16 if movement > body.energy else .7)))
            body.quiet = body.quiet + dt if movement < .08 else 0.0
            target = min(1.0, max(0.0, (body.quiet - self.STILL_SECONDS) / self.CRYSTAL_SECONDS))
            body.crystal += (target - body.crystal) * (1.0 - math.exp(-dt / (.55 if target > body.crystal else .24)))
            body.phase += dt * (.10 + 1.1 * body.energy) * (1.0 - .96 * body.crystal)
            # Keep continuous scalar time; wrapping mixed-frequency phases causes a jump.
            body.age += dt
            current.append(body)
            x = self._x[top:bottom, left:right] - body.anchor[0]
            y = self._y[top:bottom, left:right] - body.anchor[1]
            phase = body.phase
            ribbon, rings, weave = flow_motifs(x, y, phase, body.age, body.energy)
            weights = [ .55 + .35 * math.sin(body.age * rate + offset)
                        for rate, offset in ((.17, 0), (.17 * math.sqrt(2), 2.1),
                                             (.17 * math.sqrt(3), 4.2)) ]
            # All three remain present. Intersections brighten without an opaque fill.
            stream = 1 - ((1 - weights[0] * ribbon) * (1 - weights[1] * rings)
                          * (1 - weights[2] * weave))
            u, v = x * .065, y * .065
            a, b, c = u, u * .5 + v * .8660254, -u * .5 + v * .8660254
            edge_distance = np.minimum(np.minimum(np.abs(a - np.round(a)), np.abs(b - np.round(b))),
                                       np.abs(c - np.round(c)))
            edges = np.clip((.060 - edge_distance) / .060, 0, 1)
            facets = .5 + .5 * np.sin(np.floor(a) * 1.7 + np.floor(b) * 2.3)
            crystal = body.crystal
            pattern = stream * (1.0 - .85 * crystal) + (.35 * facets + .65 * edges) * (.85 * crystal)
            red, green, blue = map(float, body.color[::-1] / 255.0)
            hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
            tint = np.array(colorsys.hsv_to_rgb(hue, max(.28, saturation * .82), max(.72, value)),
                            dtype=np.float32)[::-1] * 255
            paint = tint[None, None, :] * (.64 + .36 * pattern[:, :, None])
            paint += (255 - paint) * (edges * crystal * .48)[:, :, None]
            painted = np.clip(paint, 0, 255).astype(np.uint8)
            color_layer[top:bottom, left:right][component] = painted[component]
            soft = np.clip((probability[top:bottom, left:right] - .60) / .30, 0, 1) * component
            # Fade over the upper head; retain at least 42% of every live pixel.
            torso = np.clip((self._y[top:bottom, left:right] - top) / max(1, body_height * .24), 0, 1)
            strength = np.minimum(.58, .14 + .31 * pattern + .13 * crystal * edges)
            alpha[top:bottom, left:right] = np.maximum(alpha[top:bottom, left:right], soft * torso * strength)
        self.bodies = current
        self._last_time = now
        self._previous_gray = gray
        self._previous_mask = binary
        return color_layer, alpha


def blend_on_stage(stage_frame, color_layer, alpha, layout):
    """Use the camera's exact placement; never recolor its letterbox padding."""
    if not np.any(alpha):
        return stage_frame
    width, height = layout["scaled_width"], layout["scaled_height"]
    x, y = layout["offset_x"], layout["offset_y"]
    pattern = cv2.resize(color_layer, (width, height), interpolation=cv2.INTER_LINEAR)
    opacity = cv2.resize(alpha, (width, height), interpolation=cv2.INTER_LINEAR)
    guard = cv2.resize((alpha > 0).astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST)
    opacity *= guard
    output = stage_frame.copy()
    live = stage_frame[y:y + height, x:x + width]
    # OpenCV blends uint8 images with single-channel weights in native code;
    # avoid several full-stage RGB float temporaries on the audience CPU.
    output[y:y + height, x:x + width] = cv2.blendLinear(live, pattern, 1.0 - opacity, opacity)
    return output
