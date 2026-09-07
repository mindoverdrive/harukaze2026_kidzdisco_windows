"""Slow outward transport of painted ink; camera and live cursor are excluded."""
import math
import sys

import cv2
import numpy as np
import pygame


class ArtworkOutwardDrift:
    INTERVAL = .125
    EXPANSION_PER_SECOND = .012
    ALPHA_PER_SECOND = 2.0

    def __init__(self, size):
        self.size = tuple(size)
        width, height = size
        self._target = np.empty((height, width, 4), dtype=np.uint8)
        self._last = None
        self._fade_remainder = 0.0

    def advance(self, original, colored, now):
        if not math.isfinite(now):
            return False
        if self._last is None or now < self._last:
            self._last = now
            return False
        elapsed = now - self._last
        if elapsed < self.INTERVAL:
            return False
        self._last = now
        # A stalled frame must not suddenly empty or fling the existing drawing.
        elapsed = min(.25, elapsed)
        scale = math.exp(self.EXPANSION_PER_SECOND * elapsed)
        cx, cy = (self.size[0] - 1) / 2, (self.size[1] - 1) / 2
        matrix = np.array(((scale, 0, cx * (1 - scale)),
                           (0, scale, cy * (1 - scale))), dtype=np.float32)
        self._fade_remainder += elapsed * self.ALPHA_PER_SECOND
        fade = int(self._fade_remainder)
        self._fade_remainder -= fade
        # Transport both surfaces identically; hue refresh remains at its own cadence.
        for surface in (original, colored):
            # Warp the Surface's native packed bytes directly. Channel order does
            # not matter for geometry; only the alpha byte needs its format shift.
            buffer = surface.get_buffer()
            pixels = np.ndarray((self.size[1], self.size[0], 4), dtype=np.uint8,
                                buffer=buffer, strides=(surface.get_pitch(), 4, 1))
            try:
                cv2.warpAffine(pixels, matrix, self.size, dst=self._target,
                               flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                               borderValue=(0, 0, 0, 0))
                np.copyto(pixels, self._target)
                if fade:
                    channel = surface.get_shifts()[3] // 8
                    if sys.byteorder != "little":
                        channel = 3 - channel
                    alpha = pixels[:, :, channel]
                    np.subtract(alpha, np.minimum(alpha, fade), out=alpha)
                    del alpha
            finally:
                del pixels, buffer
        return True
