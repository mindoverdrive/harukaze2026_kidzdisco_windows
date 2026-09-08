"""Harukaze-style wave geometry with bounded local hand elevation and flat lighting."""
import math
import numpy as np


class PolygonField:
    def __init__(self, width, height, cols=40, rows=30):
        self.width, self.height = width, height
        y, x = np.mgrid[0:rows + 1, 0:cols + 1].astype(np.float32)
        self.x = (x.ravel() / cols * 1.2 - .1) * width
        self.y = (y.ravel() / rows * 1.2 - .1) * height
        self.lift = np.zeros_like(self.x)
        self.faces = np.array([
            tri for row in range(rows) for col in range(cols)
            for a in [row * (cols + 1) + col]
            for tri in [(a, a + 1, a + cols + 1),
                        (a + 1, a + cols + 2, a + cols + 1)]], dtype=np.int32)
        self.face_x = self.x[self.faces].mean(axis=1)
        self.face_y = self.y[self.faces].mean(axis=1)
        self.ink = np.zeros(len(self.faces), dtype=np.float32)
        self.neighbors = np.repeat(np.arange(len(self.faces))[:, None], 3, axis=1)
        edges = {}
        for i, face in enumerate(self.faces):
            for slot in range(3):
                edge = tuple(sorted((int(face[slot]), int(face[(slot + 1) % 3]))))
                if edge in edges:
                    other, other_slot = edges[edge]
                    self.neighbors[i, slot] = other
                    self.neighbors[other, other_slot] = i
                else:
                    edges[edge] = (i, slot)

    def spread_color(self, points, dt):
        dt = min(max(dt, 0), .1)
        steps = max(1, math.ceil(dt * 60))
        h = dt / steps
        source = np.zeros(len(self.faces), dtype=bool)
        for px, py in points[:5]:
            if math.isfinite(px) and math.isfinite(py):
                source |= (self.face_x - px) ** 2 + (self.face_y - py) ** 2 < (self.height * .035) ** 2
        for _ in range(steps):
            # Convex, bounded exchange only across shared triangle edges.
            self.ink += (self.ink[self.neighbors].mean(axis=1) - self.ink) * (h * 24)
            self.ink *= math.exp(-h * .28)
            self.ink[source] += (1 - self.ink[source]) * (-math.expm1(-h * 18))

    def step(self, points, dt, now):
        self.spread_color(points, dt)
        target = np.zeros_like(self.x)
        radius = self.height * .17
        for px, py in points[:5]:
            if not (math.isfinite(px) and math.isfinite(py)):
                continue
            d2 = (self.x - px) ** 2 + (self.y - py) ** 2
            target += np.exp(-d2 / radius ** 2) * self.height * .17
        np.minimum(target, self.height * .25, out=target)
        self.lift += (target - self.lift) * (-math.expm1(-min(max(dt, 0), .1) * 8))
        # Reuse Harukaze's travelling sine/cosine relief and radial ripple.
        rx, ry = (self.x - self.width / 2) / self.height, (self.y - self.height / 2) / self.height
        z = (np.sin(rx * 3 + now * .5) * np.cos(ry * 2.5 + now * .3) * self.height * .055
             + np.sin(np.sqrt(rx * rx + ry * ry) * 10 - now * 2) * self.height * .012
             + self.lift)
        vertices = np.stack([self.x, self.y, z], axis=-1)
        triangles = vertices[self.faces]
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-6)
        light = np.array([.45 * math.sin(now * .21), -.6, 1.0])
        light /= np.linalg.norm(light)
        shade = np.clip(normals @ light, 0, 1)
        elevation = triangles[:, :, 2].mean(axis=1) / self.height
        phase = now * .22 + elevation * 9 + triangles[:, :, 0].mean(axis=1) / self.width * 2
        phase += np.sqrt(self.ink) * 6
        colors = np.stack([.5 + .5 * np.cos(phase + p) for p in (0, 2.09, 4.18)], axis=-1)
        colors = np.clip(colors * (.25 + shade[:, None] * .65) + shade[:, None] ** 16 * .18, 0, 1)
        # Shallow orthographic relief; the camera/landmark mapping stays unchanged.
        projected = vertices[:, :2].copy()
        projected[:, 1] -= z * .22
        return projected[self.faces].astype(np.int32), (colors * 255).astype(np.uint8)
