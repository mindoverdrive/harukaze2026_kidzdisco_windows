import math
from pathlib import Path
from types import ModuleType
import unittest
from unittest import mock

try:
    import numpy as np
    import cv2
    if not isinstance(np, ModuleType) or not isinstance(getattr(np, "__version__", None), str):
        raise ImportError("Real numpy is required")
    if not isinstance(cv2, ModuleType) or isinstance(getattr(cv2, "resize", None), mock.Mock):
        raise ImportError("Real OpenCV is required")
    from jacket_effect import JacketFlow, blend_on_stage, flow_motifs
    import display_utils
    REAL_ARRAYS = True
except ImportError:
    REAL_ARRAYS = False


def body_frame(size=(240, 180), shift=0, color=(45, 70, 185)):
    width, height = size
    frame = np.full((height, width, 3), (31, 43, 52), dtype=np.uint8)
    mask = np.zeros((height, width), dtype=np.float32)
    x0, x1 = width // 4 + shift, width * 3 // 4 + shift
    cv2.rectangle(mask, (x0, height // 5), (x1, height - 6), 1.0, -1)
    cv2.circle(mask, (width // 2 + shift, height // 5), height // 7, 1.0, -1)
    frame[mask > 0] = color
    cv2.circle(frame, (width // 2 + shift, height // 5), height // 7, (135, 166, 192), -1)
    return frame, mask


@unittest.skipUnless(REAL_ARRAYS, "Real numpy and OpenCV are required")
class JacketEffectTests(unittest.TestCase):
    def setUp(self):
        self.frame, self.mask = body_frame()
        self.flow = JacketFlow((240, 180))

    def settle(self, seconds=7.0):
        result = None
        for step in range(round(seconds * 20) + 1):
            result = self.flow.render(self.frame, self.mask, step / 20)
        return result

    def test_pattern_stays_in_body_and_live_video_is_never_blacked_out(self):
        original = self.frame.copy()
        pattern, alpha = self.flow.render(self.frame, self.mask, 0.0)
        output = blend_on_stage(self.frame, pattern, alpha, display_utils.get_uniform_layout(240, 180, 240, 180))
        np.testing.assert_array_equal(self.frame, original)
        np.testing.assert_array_equal(output[self.mask == 0], original[self.mask == 0])
        self.assertGreater(float(alpha.max()), .2)
        self.assertLessEqual(float(alpha.max()), .580001)
        self.assertTrue(np.all(output[self.mask > 0].astype(float) >= original[self.mask > 0] * .419 - 1))
        self.assertTrue(np.any(output[self.mask > 0] != original[self.mask > 0]))

    def test_clothing_color_is_sampled_per_person(self):
        frame = np.full((180, 240, 3), 220, dtype=np.uint8)
        mask = np.zeros((180, 240), dtype=np.float32)
        for left, color in ((15, (25, 40, 195)), (150, (195, 40, 25))):
            mask[20:170, left:left + 70] = 1
            frame[20:170, left:left + 70] = color
        pattern, alpha = self.flow.render(frame, mask, 0.0)
        self.assertEqual(len(self.flow.bodies), 2)
        self.assertGreater(float(pattern[90, 45, 2]), float(pattern[90, 45, 0]))
        self.assertGreater(float(pattern[90, 180, 0]), float(pattern[90, 180, 2]))
        self.assertEqual(float(alpha[90, 120]), 0.0)

    def test_stillness_gradually_crystallizes_after_a_hold(self):
        self.settle(1.9)
        self.assertEqual(self.flow.bodies[0].crystal, 0.0)
        for step in range(39, 141):
            self.flow.render(self.frame, self.mask, step / 20)
        self.assertGreater(self.flow.bodies[0].crystal, .95)

    def test_internal_motion_unravels_crystal_with_an_unchanged_mask_and_centroid(self):
        self.settle()
        center = self.flow.bodies[0].center
        moving = self.frame.copy()
        for step in range(1, 13):
            moving[65:140, 70:170] = (240, 240, 240) if step % 2 else (15, 15, 15)
            self.flow.render(moving, self.mask, 7 + step / 20)
        body = self.flow.bodies[0]
        self.assertEqual(body.center, center)
        self.assertLess(body.crystal, .12)
        self.assertGreater(body.energy, .2)
        energy = body.energy
        self.flow.render(moving, self.mask, 7.65)
        self.assertGreater(self.flow.bodies[0].energy, 0)
        self.assertLess(self.flow.bodies[0].energy, energy)
        for step in range(154, 194):
            self.flow.render(moving, self.mask, step / 20)
        self.assertLess(self.flow.bodies[0].energy, energy * .15)

    def test_stationary_video_with_one_pixel_mask_jitter_still_crystallizes(self):
        # Segmentation edges move even when the camera image/person is stationary.
        self.frame[:] = 90
        for step in range(161):
            jitter = -1 if step % 2 else 1
            mask = np.roll(self.mask, jitter, axis=1)
            self.flow.render(self.frame, mask, step / 20)
        self.assertGreater(self.flow.bodies[0].crystal, .95)

    def test_sustained_translation_still_unravels_after_center_filtering(self):
        self.frame[:] = 90
        self.settle()
        for step in range(1, 17):
            mask = np.roll(self.mask, step * 2, axis=1)
            self.flow.render(self.frame, mask, 7 + step / 20)
        self.assertLess(self.flow.bodies[0].crystal, .12)

    def test_small_camera_noise_does_not_prevent_crystallization(self):
        rng = np.random.default_rng(7)
        for step in range(161):
            noise = rng.integers(-2, 3, size=self.frame.shape, dtype=np.int16)
            frame = np.clip(self.frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            self.flow.render(frame, self.mask, step / 20)
        self.assertGreater(self.flow.bodies[0].crystal, .95)

    def test_three_distinct_motifs_evolve_continuously_over_long_times(self):
        y, x = np.mgrid[-90:90, -120:120].astype(np.float32)
        for age in (0, 30, 120, 3600, 43200):
            fields = flow_motifs(x, y, 1.4, age, .2)
            nearby = flow_motifs(x, y, 1.4001, age + .001, .2)
            later = flow_motifs(x, y, 1.4, age + 12, .2)
            self.assertEqual(len(fields), 3)
            for index, field in enumerate(fields):
                self.assertTrue(np.isfinite(field).all())
                self.assertGreaterEqual(float(field.min()), 0)
                self.assertLessEqual(float(field.max()), 1.00001)
                self.assertGreater(float(field.std()), .10)
                self.assertLess(float(np.abs(field - nearby[index]).mean()), .005)
                self.assertGreater(float(np.abs(field - later[index]).mean()), .03)
                self.assertGreater(float(np.abs(field - fields[(index + 1) % 3]).mean()), .05)

    def test_crystal_keeps_a_small_evolving_flow_without_resetting_stillness(self):
        pattern, _ = self.settle(8)
        first = pattern.copy()
        for step in range(161, 241):
            pattern, _ = self.flow.render(self.frame, self.mask, step / 20)
        self.assertGreater(self.flow.bodies[0].crystal, .99)
        self.assertGreater(float(np.abs(first.astype(float) - pattern).mean()), .1)

    def test_mask_shape_change_unravels_even_when_live_pixels_do_not_change(self):
        self.frame[:] = 90
        self.mask[:] = 0
        self.mask[25:155, 70:170] = 1
        self.settle()
        center = self.flow.bodies[0].center
        for step in range(1, 13):
            changed = np.zeros_like(self.mask)
            if step % 2:
                changed[40:140, 55:185] = 1
            else:
                changed[25:155, 70:170] = 1
            self.flow.render(self.frame, changed, 7 + step / 20)
        self.assertEqual(self.flow.bodies[0].center, center)
        self.assertLess(self.flow.bodies[0].crystal, .12)

    def test_flow_anchor_lags_then_catches_up_without_leaving_the_mask(self):
        self.flow.render(self.frame, self.mask, 0)
        frame, mask = body_frame(shift=18)
        _pattern, alpha = self.flow.render(frame, mask, .05)
        body = self.flow.bodies[0]
        self.assertLess(body.anchor[0], body.center[0])
        first_gap = body.center[0] - body.anchor[0]
        self.assertTrue(np.all(alpha[mask == 0] == 0))
        for step in range(2, 42):
            self.flow.render(frame, mask, step / 20)
        self.assertLess(body.center[0] - body.anchor[0], first_gap * .05)

    def test_missing_masks_and_time_gaps_clear_state_without_darkening_video(self):
        self.settle()
        for missing in (None, np.zeros_like(self.mask), np.full_like(self.mask, np.nan)):
            pattern, alpha = self.flow.render(self.frame, missing, 7.05)
            output = blend_on_stage(self.frame, pattern, alpha, display_utils.get_uniform_layout(240, 180, 240, 180))
            np.testing.assert_array_equal(output, self.frame)
            self.assertEqual(self.flow.bodies, [])
        self.flow.render(self.frame, self.mask, 10)
        self.assertEqual(self.flow.bodies[0].crystal, 0)

    def test_stage_compositing_uses_camera_mirror_and_letterbox_placement(self):
        raw = np.full((180, 240, 3), (18, 36, 54), dtype=np.uint8)
        raw[:, :60] = (70, 80, 90)
        mirrored, stage, layout = display_utils.prepare_camera_frame(raw, 640, 360)
        pattern = np.full_like(mirrored, (30, 200, 250))
        alpha = np.zeros((180, 240), dtype=np.float32)
        alpha[60:120, 180:220] = .5
        output = blend_on_stage(stage, pattern, alpha, layout)
        np.testing.assert_array_equal(output[:, :80], stage[:, :80])
        np.testing.assert_array_equal(output[:, 560:], stage[:, 560:])
        self.assertTrue(np.any(output[140:200, 450:500] != stage[140:200, 450:500]))
        np.testing.assert_array_equal(output[140:200, 150:200], stage[140:200, 150:200])
        self.assertEqual(tuple(mirrored[90, 200]), (70, 80, 90))
        allowed = cv2.resize((alpha > 0).astype(np.uint8), (480, 360), interpolation=cv2.INTER_NEAREST) > 0
        np.testing.assert_array_equal(output[:, 80:560][~allowed], stage[:, 80:560][~allowed])

    def test_fragmented_masks_have_a_bounded_track_count_and_finite_pixels(self):
        mask = np.zeros_like(self.mask)
        for row in range(3):
            for col in range(5):
                mask[row * 55 + 5:row * 55 + 40, col * 45 + 5:col * 45 + 35] = 1
        for step in range(40):
            pattern, alpha = self.flow.render(self.frame, mask, step / 20)
            self.assertLessEqual(len(self.flow.bodies), 4)
            self.assertTrue(np.all(np.isfinite(alpha)))
            self.assertEqual(pattern.dtype, np.uint8)


def render_preview(path):
    import pygame
    pygame.font.init()
    try:
        frame, mask = body_frame((640, 360), color=(48, 79, 177))
        flow = JacketFlow((640, 360))
        layout = display_utils.get_uniform_layout(640, 360, 640, 360)
        panels = [("LIVE CAMERA / SYNTHETIC INPUT", frame.copy())]
        for step in range(161):
            pattern, alpha = flow.render(frame, mask, step / 20)
            if step in (12, 70, 160):
                panels.append(({12: "FLOW", 70: "STILLNESS / FORMING", 160: "HELD STILL / CRYSTAL"}[step],
                               blend_on_stage(frame, pattern, alpha, layout)))
        sheet = pygame.Surface((1280, 810))
        sheet.fill((13, 22, 31))
        font = pygame.font.SysFont("Arial", 21)
        for index, (label, pixels) in enumerate(panels):
            x, y = index % 2 * 640, index // 2 * 405
            sheet.blit(font.render(label, True, (215, 230, 240)), (x + 18, y + 13))
            rgb = cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB)
            sheet.blit(pygame.image.frombuffer(rgb.tobytes(), (640, 360), "RGB"), (x, y + 45))
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(sheet, str(destination))
    finally:
        pygame.font.quit()


if __name__ == "__main__":
    unittest.main()
