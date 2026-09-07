"""Recolor persistent artwork without resampling or modifying its geometry."""
import math

import cv2
import numpy as np
import pygame


class ArtworkHueCycle:
    PERIOD_SECONDS = 120.0

    def __init__(self, size):
        self.surface = pygame.Surface(size, pygame.SRCALPHA, 32)
        self.surface.fill((0, 0, 0, 0))
        width, height = size
        # Walk display memory row by row; width-major copies cause cache misses.
        self._rgb = np.empty((height, width, 3), dtype=np.uint8)
        self._hsv = np.empty_like(self._rgb)
        self._output = np.empty_like(self._rgb)
        self._shift = None
        self._origin = None

    def refresh(self, original, now):
        if not math.isfinite(now):
            return self.surface
        if self._origin is None:
            self._origin = now
        shift = int(max(0.0, now - self._origin) * 256 / self.PERIOD_SECONDS) % 256
        if shift == self._shift:
            return self.surface
        self._shift = shift
        if shift == 0:
            # Exact original on a full cycle, with no accumulated color drift.
            self.surface.fill((0, 0, 0, 0))
            self.surface.blit(original, (0, 0))
        else:
            source = pygame.surfarray.pixels3d(original)
            try:
                np.copyto(self._rgb, source.swapaxes(0, 1))
            finally:
                del source
            cv2.cvtColor(self._rgb, cv2.COLOR_RGB2HSV_FULL, dst=self._hsv)
            np.add(self._hsv[:, :, 0], np.uint8(shift), out=self._hsv[:, :, 0])
            cv2.cvtColor(self._hsv, cv2.COLOR_HSV2RGB_FULL, dst=self._output)
            target = pygame.surfarray.pixels3d(self.surface)
            alpha = pygame.surfarray.pixels_alpha(self.surface)
            source_alpha = pygame.surfarray.pixels_alpha(original)
            try:
                np.copyto(target, self._output.swapaxes(0, 1))
                np.copyto(alpha, source_alpha)
            finally:
                del target, alpha, source_alpha
        return self.surface

    def display_color(self, color):
        if not self._shift:
            return color
        rgb = np.array([[[color.r, color.g, color.b]]], dtype=np.uint8)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL)
        hsv[0, 0, 0] = (int(hsv[0, 0, 0]) + self._shift) % 256
        shifted = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB_FULL)[0, 0]
        return pygame.Color(*(int(value) for value in shifted), color.a)
