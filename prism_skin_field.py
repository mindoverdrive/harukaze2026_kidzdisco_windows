"""Bounded, low-resolution iridescent membrane, independent of camera ownership."""
import math
import numpy as np


class PrismSkin:
    def __init__(self, width=320, height=180):
        self.aspect = width / height
        self.y, self.x = np.mgrid[0:height, 0:width].astype(np.float32)
        self.x /= width - 1
        self.y /= height - 1
        self.pressure = np.zeros((height, width), dtype=np.float32)

    def update(self, points, dt):
        """Each normalized fingertip presses locally; release relaxes without resets."""
        target = np.zeros_like(self.pressure)
        for px, py in points[:5]:
            if not (math.isfinite(px) and math.isfinite(py)):
                continue
            distance = ((self.x - px) * self.aspect) ** 2 + (self.y - py) ** 2
            target += np.exp(-distance / .018)
        np.minimum(target, 1.6, out=target)
        blend = -math.expm1(-min(max(dt, 0), .1) * 9)
        self.pressure += (target - self.pressure) * blend

    def render(self, now):
        # Analytic background waves never accumulate energy or particle history.
        x, y = self.x * self.aspect, self.y
        height = (.13 * np.sin(x * 5 + now * .43)
                  + .10 * np.sin(y * 7 - now * .31)
                  + .07 * np.sin((x + y) * 8 + now * .19)
                  - self.pressure * .85)
        dy, dx = np.gradient(height, 1 / (y.shape[0] - 1), self.aspect / (x.shape[1] - 1))
        normal = np.sqrt(1 + dx * dx + dy * dy)
        reflection = np.clip((1.2 - dx * .55 - dy * .35) / normal, 0, 1)
        sheen = reflection ** 8
        phase = height * 10 + reflection * 5 + now * .13
        rgb = np.stack([.5 + .5 * np.cos(phase + shift)
                        for shift in (0, 2.094, 4.189)], axis=-1)
        rgb *= (.20 + reflection * .48)[..., None]
        rgb += (sheen * .38)[..., None]
        return (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
