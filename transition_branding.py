"""Choose weighted brand compositions without changing transition control."""

import math
import random
from pathlib import Path
from types import SimpleNamespace

from transition_logo import CurtainLogo


def white_paper_to_alpha(source):
    """Runtime matte only: source file and logo geometry remain untouched."""
    import numpy as np
    import pygame

    rgb = pygame.surfarray.array3d(source).astype(np.float32)
    light = rgb.mean(axis=2)
    dark = light < 80
    ink_level = float(np.median(light[dark])) if np.any(dark) else 0.0
    coverage = np.clip((250.0 - light) / max(1.0, 250.0 - ink_level), 0.0, 1.0)
    # Remove white matte from antialiased edge colors to prevent a pale fringe.
    foreground = np.clip((rgb - 255.0 * (1.0 - coverage[:, :, None])) /
                         np.maximum(coverage[:, :, None], .001), 0, 255).astype(np.uint8)
    result = pygame.Surface(source.get_size(), pygame.SRCALPHA, 32)
    pixels = pygame.surfarray.pixels3d(result)
    alpha = pygame.surfarray.pixels_alpha(result)
    try:
        pixels[:] = foreground
        alpha[:] = np.rint(coverage * 255).astype(np.uint8)
    finally:
        del pixels, alpha
    return result


class AlternatingCurtainLogo:
    """Legacy entry point; pick one logo once per transition, with weights 1:1:2."""

    BRANDS = ("colony", "tokyo_island", "asobi_tune")
    WEIGHTS = (1, 1, 2)

    def __init__(self, size, tokyo_path=None, on_warning=None, asobi_path=None, rng=None):
        import pygame

        self._pygame = pygame
        self.size = tuple(size)
        self.colony = CurtainLogo(size, on_warning=on_warning)
        self._cycle = None
        self._colony_cycle = 0
        self._rng = random if rng is None else rng
        self.brand = "colony"
        assets = Path(__file__).resolve().parent / "assets"
        self.tokyo = self._load_color_logo(
            Path(tokyo_path) if tokyo_path is not None else assets / "tokyo_island_2026_logo.webp",
            "Tokyo Island", on_warning)
        self.asobi = self._load_color_logo(
            Path(asobi_path) if asobi_path is not None else assets / "asobi_tune_logo.png",
            "Asobi Tune", on_warning)

    def _load_color_logo(self, path, label, on_warning):
        pygame = self._pygame
        try:
            source = pygame.image.load(str(path))
            # RGB and per-pixel alpha are the artwork, including white details.
            # Do not apply the old white-paper matte to either color logo.
            scale = min(self.size[0] * .52 / source.get_width(), self.size[1] * .52 / source.get_height())
            return pygame.transform.smoothscale(source, (
                max(1, round(source.get_width() * scale)),
                max(1, round(source.get_height() * scale))))
        except Exception as exc:
            message = f"[TransitionBranding] {label} unavailable; using Colony: {type(exc).__name__}"
            if on_warning is not None:
                on_warning(message)
            else:
                print(message, flush=True)
            return None

    def draw(self, screen, rect, now, curtain):
        cycle = max(1, int(getattr(curtain, "cycle", 1)))
        if self._cycle is None or (curtain.state == "covering" and cycle != self._cycle):
            self._cycle = cycle
            self.brand = self._rng.choices(self.BRANDS, weights=self.WEIGHTS, k=1)[0]
            if (self.brand == "colony"
                    or (self.brand == "tokyo_island" and self.tokyo is None)
                    or (self.brand == "asobi_tune" and self.asobi is None)):
                self._colony_cycle += 1
        artwork = self.tokyo if self.brand == "tokyo_island" else self.asobi
        if self.brand == "colony" or artwork is None:
            # Keep all Colony typography/motion variants across its appearances.
            state = SimpleNamespace(state=curtain.state, level=curtain.level,
                                    cycle=self._colony_cycle)
            return self.colony.draw(screen, rect, now, state)
        fade = CurtainLogo._fade(curtain)
        if fade <= 0 or not math.isfinite(now):
            return False
        previous_clip = screen.get_clip()
        clip = previous_clip.clip(self._pygame.Rect(rect)).clip(screen.get_rect())
        if clip.width <= 0 or clip.height <= 0:
            return False
        try:
            screen.set_clip(clip)
            # Whole lockup floats/fades together; no replacement type or recoloring.
            drift = math.sin(now * .28) * min(4, self.size[0] * .002)
            bob = math.sin(now * .35) * min(5, self.size[1] * .004)
            position = (round((self.size[0] - artwork.get_width()) / 2 + drift),
                        round((self.size[1] - artwork.get_height()) / 2 + bob))
            artwork.set_alpha(round(255 * fade))
            screen.blit(artwork, position)
            return True
        finally:
            screen.set_clip(previous_clip)
