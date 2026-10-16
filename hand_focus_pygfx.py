"""Transparent final-pass adapter for the shared hand feedback drawing.

The RGBA texture and pygame surface share memory. No camera, inference or
additional window is created here; scenes pass their existing landmarks/layout.
"""

import numpy as np
import pygame
import pygfx as gfx

from hand_focus_overlay import draw_pygame, stage_points


class PygfxHandOverlay:
    def __init__(self, width, height):
        self.size = (int(width), int(height))
        self.pixels = np.zeros((self.size[1], self.size[0], 4), dtype=np.uint8)
        self.surface = pygame.image.frombuffer(self.pixels, self.size, "RGBA")
        self.texture = gfx.Texture(self.pixels, dim=2)
        self.mesh = gfx.Mesh(
            gfx.plane_geometry(*self.size),
            gfx.MeshBasicMaterial(
                map=self.texture, depth_test=False, depth_write=False,
                alpha_mode="blend", render_queue=4999,
            ),
        )
        self.mesh.visible = False
        self.scene = gfx.Scene()
        self.scene.add(self.mesh)
        self.camera = gfx.OrthographicCamera(*self.size)
        self.camera.local.z = 100

    def clear(self):
        """Hide immediately on hand loss, missing camera or detector failure."""
        self.mesh.visible = False
        self.pixels.fill(0)

    def update(self, hands, *, layout=None, focus=(), active_points=(),
               palm_focus=False, palm_circles=None, cursor_colors=()):
        """Redraw from the current result, using the scene's exact stage layout.

        ``cursor_colors`` keeps an existing scene's gesture/hand-assignment hint
        in the small center of the index marker; its contrasting rings stay the
        same as the other renderers. All other drawing is shared.
        """
        self.clear()
        hands = tuple(hands or ())
        if not hands and not active_points:
            return
        draw_pygame(
            self.surface, hands, layout=layout, focus=focus,
            active_points=active_points, palm_focus=palm_focus,
            palm_circles=palm_circles,
        )
        for hand, color in zip(hands, cursor_colors):
            points = stage_points(hand, self.size, layout)
            if len(points) >= 21:
                radius = max(1, round(4 * max(.65, min(self.size) / 720)))
                pygame.draw.circle(self.surface, color, points[8], radius)
        self.texture.update_range((0, 0, 0), self.texture.size)
        self.mesh.visible = True
