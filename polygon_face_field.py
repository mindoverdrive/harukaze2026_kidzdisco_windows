"""Low-resolution mouth-driven relief inspired by Harukaze's face polygon."""
import math
import numpy as np
from polygon_vibes_field import PolygonField


def mouth_openness(landmarks):
    face_height = math.hypot(landmarks[10].x - landmarks[152].x,
                             landmarks[10].y - landmarks[152].y)
    gap = math.hypot(landmarks[13].x - landmarks[14].x,
                     landmarks[13].y - landmarks[14].y)
    return min(1., max(0., (gap / max(face_height, 1e-6) - .02) * 6))


class FaceField:
    def __init__(self, width, height):
        self.grid = PolygonField(width, height)
        self.opening = 0.
        self.center = np.array([width / 2, height / 2], dtype=np.float32)

    def step(self, mouth, opening, dt, now):
        blend = -math.expm1(-min(max(dt, 0), .1) * 8)
        self.opening += ((opening if mouth is not None else 0) - self.opening) * blend
        if mouth is not None:
            self.center += (np.asarray(mouth) - self.center) * blend
        g = self.grid
        distance = np.hypot(g.x - self.center[0], g.y - self.center[1]) / g.height
        z = (np.sin(distance * 28 - now * 5) * np.exp(-distance * 1.1)
             * self.opening * g.height * .10)
        z += np.sin(g.x / g.height * 3 + now * .25) * g.height * .008
        vertices = np.stack([g.x, g.y, z], axis=-1)
        triangles = vertices[g.faces]
        normal = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-6)
        light = np.array([.3, -.6, 1.])
        light /= np.linalg.norm(light)
        shade = np.clip(normal @ light, 0, 1)
        phase = now * .15 + self.opening * 3 + triangles[:, :, 2].mean(axis=1) / g.height * 15
        rgb = np.stack([.5 + .5 * np.cos(phase + p) for p in (0, 2.09, 4.18)], axis=-1)
        rgb = np.clip(rgb * (.2 + shade[:, None] * .7) + shade[:, None] ** 12 * .12, 0, 1)
        projected = vertices[:, :2].copy()
        projected[:, 1] -= z * .22
        return projected[g.faces].astype(np.int32), (rgb * 255).astype(np.uint8)
