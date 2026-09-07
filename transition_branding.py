"""Alternate complete brand compositions without changing transition control."""

import math
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
    def __init__(self, size, rebirth_path=None, on_warning=None):
        import pygame

        self._pygame = pygame
        self.size = tuple(size)
        self.colony = CurtainLogo(size, on_warning=on_warning)
        self._cycle = None
        self.brand = "colony"
        self.rebirth = None
        try:
            path = Path(rebirth_path) if rebirth_path is not None else (
                Path(__file__).resolve().parent / "assets" / "rebirth_logo_source.jpg")
            source = pygame.image.load(str(path))
            # Preserve artwork; the user now requests transparent white paper.
            cutout = white_paper_to_alpha(source)
            scale = min(size[0] * .52 / source.get_width(), size[1] * .52 / source.get_height())
            self.rebirth = pygame.transform.smoothscale(cutout, (
                max(1, round(source.get_width() * scale)),
                max(1, round(source.get_height() * scale))))
        except Exception as exc:
            message = f"[TransitionBranding] Rebirth unavailable; using Colony: {type(exc).__name__}"
            if on_warning is not None:
                on_warning(message)
            else:
                print(message, flush=True)

    def draw(self, screen, rect, now, curtain):
        cycle = max(1, int(getattr(curtain, "cycle", 1)))
        if self._cycle is None or (curtain.state == "covering" and cycle != self._cycle):
            self._cycle = cycle
            self.brand = "colony" if cycle % 2 else "rebirth"
        if self.brand == "colony" or self.rebirth is None:
            # Keep all Colony typography/motion variants across its appearances.
            state = SimpleNamespace(state=curtain.state, level=curtain.level,
                                    cycle=(self._cycle + 1) // 2)
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
            position = (round((self.size[0] - self.rebirth.get_width()) / 2 + drift),
                        round((self.size[1] - self.rebirth.get_height()) / 2 + bob))
            self.rebirth.set_alpha(round(255 * fade))
            screen.blit(self.rebirth, position)
            return True
        finally:
            screen.set_clip(previous_clip)
