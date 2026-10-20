import unittest
from unittest import mock

import cv2
import numpy as np

from face_morph_field import FaceMorphField, face_from_landmarks, stage_mesh
from face_morph_test_input import LOOP_SECONDS, SyntheticCapture, SyntheticLandmarkDetector


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class SyntheticLandmarkTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.detector = SyntheticLandmarkDetector(clock=self.clock)
        self.rgb = np.zeros((360, 640, 3), dtype=np.uint8)

    def observations(self, now):
        self.clock.now = now
        result = self.detector.process(self.rgb)
        return [face_from_landmarks(f.landmark, 640, 360) for f in result.multi_face_landmarks]

    def test_program_population_mouth_scale_and_loop(self):
        for now, expected_count, phase in [(0, 1, 'single_face'), (7, 2, 'two_faces'),
                (8.5, 3, 'three_faces'), (10, 4, 'four_faces'), (12, 5, 'five_face_cycles'),
                (26.2, 4, 'short_occlusion'), (26.6, 5, 'short_regain'),
                (31, 4, 'long_exit'), (33, 5, 'long_regain'), (LOOP_SECONDS, 1, 'single_face')]:
            observations = self.observations(now)
            self.assertEqual(len(observations), expected_count)
            self.assertEqual(self.detector.phase, phase)
        self.clock.now = .2
        points = self.detector.process(self.rgb).multi_face_landmarks[0].landmark
        self.assertEqual(len(points), 468)
        a = face_from_landmarks(points, 640, 360)
        b = face_from_landmarks(points, 1920, 1080)
        self.assertAlmostEqual(a.opening, .78)
        self.assertAlmostEqual(a.opening, b.opening)
        self.assertAlmostEqual(self.observations(.9)[0].opening, 0.0)

    def test_real_controller_full_program_uniqueness_transform_and_geometry(self):
        import display_utils
        field = FaceMorphField()
        layout = display_utils.get_uniform_layout(640, 360, 1280, 720)
        before_reversal = None
        peak_simultaneous_changes = peak_reservations = 0
        for frame in range(int(LOOP_SECONDS * 20)):
            now = frame / 20
            previous_changes = {id(t): t.changes for t in field.tracks.values()}
            field.step(self.observations(now), now)
            shapes = [s for t in field.tracks.values() for s in (t.shape, t.previous_shape) if s is not None]
            self.assertEqual(len(shapes), len(set(shapes)))
            self.assertLessEqual(len(field.tracks), 5)
            self.assertLessEqual(len(shapes), 10)
            peak_reservations = max(peak_reservations, len(shapes))
            peak_simultaneous_changes = max(peak_simultaneous_changes,
                sum(t.changes > previous_changes.get(id(t), 0) for t in field.tracks.values()))
            if frame == 6 * 20:
                self.assertEqual(len(field.tracks), 1)
                self.assertGreater(field.changes, 0)
            if frame == 19 * 20:
                self.assertEqual(sum(t.visible for t in field.tracks.values()), 5)
                self.assertTrue(all(t.changes > 0 for t in field.tracks.values()))
                for track in field.tracks.values():
                    points, triangles = stage_mesh(track, now, layout)
                    self.assertEqual(points.shape, (193, 2))
                    self.assertEqual(triangles.shape, (336, 3))
                    self.assertTrue((points >= 0).all())
                    self.assertTrue((points[:, 0] < 1280).all() and (points[:, 1] < 720).all())
            if frame == 399:
                before_reversal = dict(field.tracks)
            if frame == 400:
                self.assertTrue(all(field.tracks[k] is t for k, t in before_reversal.items()))
            if frame == 450:
                self.assertGreaterEqual(field.last_ambiguous_count, 2)
                self.assertLessEqual(sum(t.visible for t in field.tracks.values()), 3)
        self.assertEqual(peak_simultaneous_changes, 5)
        self.assertEqual(peak_reservations, 10)

    def test_short_occlusion_preserves_identity_without_a_false_close(self):
        field = FaceMorphField()
        for frame in range(498, 520):
            now = frame / 20
            field.step(self.observations(now), now)
        original = field.tracks[0]
        self.assertTrue(original.opened)
        self.assertFalse(original.armed)
        self.assertEqual(original.changes, 0)
        for frame in range(520, 550):
            now = frame / 20
            field.step(self.observations(now), now)
        self.assertIs(field.tracks[0], original)
        self.assertTrue(original.visible)
        self.assertFalse(original.opened)
        self.assertEqual(original.changes, 0)
        self.assertTrue(original.armed)

    def test_long_exit_releases_slot_before_new_identity_returns(self):
        field = FaceMorphField()
        field.step(self.observations(29.5), 29.5)
        original = field.tracks[4]
        for frame in range(591, 640):
            now = frame / 20
            field.step(self.observations(now), now)
        self.assertNotIn(4, field.tracks)
        self.assertNotIn(original.shape, field.reserved())
        field.step(self.observations(32), 32)
        self.assertIn(4, field.tracks)
        self.assertIsNot(field.tracks[4], original)
        self.assertEqual(field.tracks[4].changes, 0)

    def test_detector_context_closes_without_external_input(self):
        with mock.patch.object(cv2, 'VideoCapture', side_effect=AssertionError('physical input')):
            with SyntheticLandmarkDetector(clock=self.clock) as detector:
                self.assertEqual(len(detector.process(self.rgb).multi_face_landmarks), 1)
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                detector.process(self.rgb)


class SyntheticCaptureTests(unittest.TestCase):
    def test_source_labels_keep_their_orientation_after_production_mirror(self):
        import display_utils
        clock = FakeClock()
        capture = SyntheticCapture(320, 180, 24, clock=clock, sleep=clock.sleep)
        capture._background = np.zeros((180, 320, 3), dtype=np.uint8)
        capture._background[10:20, 10:20] = 255
        ok, source = capture.read()
        self.assertTrue(ok)
        self.assertEqual(source[10, 309].tolist(), [255, 255, 255])
        camera, _, _ = display_utils.prepare_camera_frame(source, 320, 180)
        self.assertEqual(camera[10, 10].tolist(), [255, 255, 255])
        self.assertEqual(camera[10, 309].tolist(), [0, 0, 0])
        capture.release()

    def test_capture_paces_generates_frames_and_releases(self):
        clock = FakeClock()
        with mock.patch.object(cv2, 'VideoCapture', side_effect=AssertionError('physical input')):
            capture = SyntheticCapture(640, 360, 24, clock=clock, sleep=clock.sleep)
            frames = []
            for _ in range(4):
                ok, frame = capture.read()
                self.assertTrue(ok)
                self.assertEqual(frame.shape, (360, 640, 3))
                self.assertEqual(frame.dtype, np.uint8)
                frames.append(frame)
            self.assertEqual(len(clock.sleeps), 3)
            self.assertTrue(all(0 < delay <= 1 / 24 for delay in clock.sleeps))
            self.assertAlmostEqual(clock.now, 3 / 24)
            self.assertFalse(np.array_equal(frames[0], frames[-1]))
            self.assertEqual(capture.get(cv2.CAP_PROP_FPS), 24)
            self.assertTrue(capture.set(cv2.CAP_PROP_FRAME_WIDTH, 320))
            self.assertTrue(capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 180))
            self.assertEqual(capture.read()[1].shape, (180, 320, 3))
            capture.release()
            capture.release()
            self.assertFalse(capture.isOpened())
            self.assertEqual(capture.read(), (False, None))
            self.assertFalse(capture.set(cv2.CAP_PROP_FPS, 30))

    def test_invalid_capture_configuration_is_rejected(self):
        for width, height, fps in [(0, 360, 24), (640, -1, 24), (640, 360, 0), (640, 360, float('nan'))]:
            with self.assertRaises(ValueError):
                SyntheticCapture(width, height, fps)


if __name__ == '__main__':
    unittest.main()
