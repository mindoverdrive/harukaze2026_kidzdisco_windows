"""Continuous oblique sphere motion and a bounded, soft-particle renderer."""
import math

POINTS_PER_LAYER = 1200
LAYER_COUNT = 8
PALETTE_SIZE = 48
SHADE_COUNT = 10
DOT_RADII = (1.7, 2.3, 2.9, 3.5, 4.2, 4.8)


def fibonacci_points(samples=POINTS_PER_LAYER):
    if type(samples) is not int or samples < 2:
        raise ValueError("A sphere needs at least two integer samples")
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    points = []
    for index in range(samples):
        y = 1.0 - 2.0 * index / (samples - 1)
        radius = math.sqrt(max(0.0, 1.0 - y * y))
        angle = golden_angle * index
        points.append((math.cos(angle) * radius, y, math.sin(angle) * radius))
    return points


def sphere_axis(seconds, layer):
    # About 45 degrees in the picture plane, also tilted into its depth.
    # Gentle, bounded precession adds variation without flipping the axis.
    phase = layer * 0.61
    axis = (1.0 + 0.14 * math.sin(seconds * 0.021 + phase),
            1.0 + 0.14 * math.cos(seconds * 0.018 + phase),
            0.55 + 0.12 * math.sin(seconds * 0.016 + phase))
    length = math.sqrt(sum(component * component for component in axis))
    return tuple(component / length for component in axis)


def rotation_matrix(axis, angle):
    """Rodrigues rotation; the supplied axis must be a unit vector."""
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    k = 1.0 - c
    return ((c + x*x*k, x*y*k - z*s, x*z*k + y*s),
            (y*x*k + z*s, c + y*y*k, y*z*k - x*s),
            (z*x*k - y*s, z*y*k + x*s, c + z*z*k))


def sphere_rotation(seconds, layer):
    # Compute from elapsed seconds, never from frame count. No 50-second reset.
    speed = 0.12 * (1.0 + 0.12 * math.sin(layer * 1.7))
    angle = seconds * speed + layer * 0.37 + 0.18 * math.sin(seconds * 0.041 + layer)
    return rotation_matrix(sphere_axis(seconds, layer), angle)


class TipSmoother:
    """Short interpolation between camera updates, with no departed-hand trails."""
    def __init__(self):
        self.points = ()

    def update(self, targets, dt):
        targets = tuple(targets)
        if not targets:
            self.points = ()
            return self.points
        weight = -math.expm1(-35.0 * max(0.0, dt))
        # Match globally nearest pairs before admitting new hands. Detector order
        # can change when a second hand arrives; it must not steal a survivor.
        pairs = sorted((math.hypot(old[0] - target[0], old[1] - target[1]), old_id, target_id)
                       for old_id, old in enumerate(self.points)
                       for target_id, target in enumerate(targets))
        matched, used = {}, set()
        for _distance, old_id, target_id in pairs:
            if old_id not in used and target_id not in matched:
                matched[target_id] = self.points[old_id]
                used.add(old_id)
        points = []
        for target_id, target in enumerate(targets):
            old = matched.get(target_id, target)
            points.append((old[0] + (target[0] - old[0]) * weight,
                           old[1] + (target[1] - old[1]) * weight))
        self.points = tuple(points)
        return self.points


class SpheresField:
    def __init__(self, width, height, samples=POINTS_PER_LAYER):
        import numpy as np

        self.np = np
        self.width, self.height = int(width), int(height)
        self.points = np.asarray(fibonacci_points(samples), dtype=np.float32)
        self.phases = np.arange(samples, dtype=np.float32) * 0.61803399
        self.radius = min(width, height) / 3.0
        self.viewer = self.radius * (800.0 / 360.0)
        self.fov = min(width, height) * 0.8
        self.scale = min(width, height) / 1080.0
        self.particle_count = samples * LAYER_COUNT

    def project(self, seconds, tips=()):
        np = self.np
        positions, sprite_ids = [], []
        # One vectorized rotation per shell; no per-dot trigonometric calls.
        for layer in range(LAYER_COUNT):
            matrix = np.asarray(sphere_rotation(seconds, layer), dtype=np.float32)
            rotated = self.points @ matrix.T
            radius = self.radius * (1.0 - layer * 0.008)
            radius *= 1.0 + 0.012 * math.sin(seconds * 0.19 + layer * 0.55)
            depth = rotated[:, 2]
            perspective = self.fov / (depth * radius + self.viewer)
            x = rotated[:, 0] * radius * perspective + self.width * 0.5
            y = -rotated[:, 1] * radius * perspective + self.height * 0.5
            front = np.clip(-depth, 0.0, 1.0)
            # Dim rear particles keep the volume legible without an opaque shell.
            light = 0.12 + 0.72 * front
            light += 0.055 * (1.0 + np.sin(self.phases + seconds * 0.65 + layer)) * front
            influence = np.zeros(len(self.points), dtype=np.float32)
            offset_x = np.zeros_like(influence)
            offset_y = np.zeros_like(influence)
            reach = max(1.0, 150.0 * self.scale)
            for tip_x, tip_y in tips:
                dx, dy = x - tip_x, y - tip_y
                distance = np.hypot(dx, dy)
                envelope = np.exp(-((distance / reach) ** 2))
                wave = np.sin(distance / max(self.scale, 0.01) * 0.045 - seconds * 7.0)
                push = wave * envelope * 15.0 * self.scale / np.maximum(distance, 1.0)
                offset_x += dx * push
                offset_y += dy * push
                influence = np.maximum(influence, envelope)
            # Multiple hands strengthen the same field without unbounded displacement.
            x += np.clip(offset_x, -32.0 * self.scale, 32.0 * self.scale)
            y += np.clip(offset_y, -32.0 * self.scale, 32.0 * self.scale)
            light = np.clip(light + influence * 0.28, 0.0, 1.0)
            sizes = np.clip((front * 4.3 + influence * 1.2).astype(np.int32), 0, len(DOT_RADII) - 1)
            shades = np.clip((light * (SHADE_COUNT - 1)).astype(np.int32), 0, SHADE_COUNT - 1)
            palette = int(round((layer % 4) * 12 + 2.0 * math.sin(seconds * 0.035 + layer * 0.5))) % PALETTE_SIZE
            indices = (palette * SHADE_COUNT + shades) * len(DOT_RADII) + sizes
            visible = (x >= -12) & (x < self.width + 12) & (y >= -12) & (y < self.height + 12)
            positions.append(np.column_stack((x[visible], y[visible])))
            sprite_ids.append(indices[visible])
        return np.concatenate(positions), np.concatenate(sprite_ids)


class SphereRenderer:
    """A fixed sprite atlas; no new glow surfaces are allocated per frame."""
    def __init__(self, screen, samples=POINTS_PER_LAYER):
        import numpy as np
        import pygame

        self.pg = pygame
        self.field = SpheresField(*screen.get_size(), samples=samples)
        self.sprites = []
        self.half_sizes = []
        anchors = np.asarray(((190, 220, 255), (255, 55, 100),
                              (45, 145, 255), (255, 215, 50)), dtype=np.float32)
        kernels = []
        for radius in DOT_RADII:
            radius *= max(0.7, self.field.scale)
            half = max(3, math.ceil(radius * 3.0))
            axis = np.arange(-half, half + 1, dtype=np.float32)
            squared = axis[:, None] ** 2 + axis[None, :] ** 2
            kernel = (0.95 * np.exp(-squared / (radius * 0.82) ** 2)
                      + 0.20 * np.exp(-squared / (radius * 1.7) ** 2))
            kernels.append((kernel, half))
        for color_index in range(PALETTE_SIZE):
            segment, step = divmod(color_index, 12)
            mix = step / 12.0
            color = anchors[segment] * (1.0 - mix) + anchors[(segment + 1) % 4] * mix
            for shade in range(SHADE_COUNT):
                # Keep the far hemisphere subtle but visible.
                level = 0.08 + 0.92 * shade / (SHADE_COUNT - 1)
                for kernel, half in kernels:
                    pixels = np.clip(kernel[:, :, None] * color * level, 0, 255).astype(np.uint8)
                    sprite = pygame.Surface((half * 2 + 1, half * 2 + 1)).convert(screen)
                    pygame.surfarray.blit_array(sprite, pixels)
                    self.sprites.append(sprite)
                    self.half_sizes.append(half)

    def draw(self, screen, seconds, tips=()):
        positions, indices = self.field.project(seconds, tips)
        # Additive light is order independent, avoiding thousands of Python z-sort keys.
        # Convert once in NumPy, avoiding per-particle NumPy scalar allocations.
        points = positions.astype(self.field.np.int32).tolist()
        sprite_indices = indices.tolist()
        fblits = getattr(screen, "fblits", None)
        if callable(fblits):
            batch = [(self.sprites[index], (point[0] - self.half_sizes[index],
                                           point[1] - self.half_sizes[index]))
                     for point, index in zip(points, sprite_indices)]
            fblits(batch, self.pg.BLEND_RGB_ADD)
        else:
            batch = [(self.sprites[index], (point[0] - self.half_sizes[index],
                                           point[1] - self.half_sizes[index]),
                      None, self.pg.BLEND_RGB_ADD)
                     for point, index in zip(points, sprite_indices)]
            screen.blits(batch, doreturn=False)
        for x, y in tips:
            center = (round(x), round(y))
            radius = max(6, round((11.0 + math.sin(seconds * 3.0)) * self.field.scale))
            self.pg.draw.circle(screen, (190, 235, 255), center, radius, 1)
            self.pg.draw.circle(screen, (235, 250, 255), center, 2)
        return len(positions)
