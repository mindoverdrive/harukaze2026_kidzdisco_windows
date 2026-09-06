import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import shared_camera as camera


class FirstReadCapture:
    """Model the observed C922 control reset after its first successful read."""

    def __init__(self, backend=700, exposure=-5, zoom=180, drifts=None, failed_read=None):
        self.values = {42: backend, 15: exposure, 27: zoom, 3: 2, 4: 2, 5: 30, 6: 0}
        self.drifts = drifts or {}
        self.failed_read = failed_read
        self.read_count = 0
        self.set_calls = []
        self.release_count = 0
        self.on_read = None
        self.reject = None

    def isOpened(self):
        return self.release_count == 0

    def get(self, prop):
        return self.values.get(prop, -1)

    def set(self, prop, value):
        self.set_calls.append((self.read_count, prop, value))
        if prop == self.reject:
            return False
        self.values[prop] = value
        return True

    def read(self):
        self.read_count += 1
        self.values.update(self.drifts.get(self.read_count, {}))
        if self.on_read is not None:
            self.on_read()
        return (False, None) if self.read_count == self.failed_read else (True, object())

    def release(self):
        self.release_count += 1


class FirstFrameControlTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.worker = mock.Mock()
        self.worker.is_alive.return_value = False
        for patch in (
            mock.patch.multiple(camera.cv2, CAP_PROP_BACKEND=42, CAP_DSHOW=700, CAP_MSMF=1400,
                                CAP_PROP_EXPOSURE=15, CAP_PROP_ZOOM=27, CAP_PROP_FRAME_WIDTH=3,
                                CAP_PROP_FRAME_HEIGHT=4, CAP_PROP_FPS=5, CAP_PROP_FOURCC=6),
            mock.patch.object(camera, "choose_camera_index", return_value=1),
            mock.patch.object(camera, "SESSION_INFO_PATH", str(Path(directory.name) / "session.json")),
            mock.patch.object(camera, "_measure_capture_fps", return_value=(30.0, 2)),
            mock.patch.object(camera.threading, "Thread", return_value=self.worker),
            mock.patch("builtins.print"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def relay(self, exposure=-5, zoom=None):
        relay = camera.SharedCameraRelay(1, 2, 2, 30, backend_preference="dshow",
                                        exposure=exposure, zoom=zoom)
        self.addCleanup(relay.close)
        return relay

    def test_start_corrects_only_first_read_drift_then_observes_confirmed_values(self):
        relay = self.relay(zoom=180)
        cap = FirstReadCapture(drifts={1: {15: -4, 27: 100}})
        cap.on_read = lambda: self.assertIs(relay.cap, cap)
        with mock.patch.object(camera, "_open_with_backends", return_value=cap):
            relay.start()
        self.assertEqual(cap.read_count, 2)
        self.assertEqual(cap.set_calls, [(1, 15, -5), (1, 27, 180)])
        self.assertEqual(relay.controls.snapshot()["actual"], {"exposure": -5.0, "zoom": 180.0})
        self.assertTrue(relay.close())
        self.assertEqual(cap.release_count, 1)

    def test_matching_controls_are_verified_without_reapplying_them(self):
        relay = self.relay(zoom=180)
        cap = FirstReadCapture()
        with mock.patch.object(camera, "_open_with_backends", return_value=cap):
            relay.start()
        self.assertEqual(cap.read_count, 2)
        self.assertEqual(cap.set_calls, [])

    def test_missing_first_or_confirmation_frame_fails_start_and_releases_capture(self):
        for missing in (1, 2):
            with self.subTest(missing=missing):
                relay = self.relay()
                cap = FirstReadCapture(drifts={1: {15: -4}}, failed_read=missing)
                with mock.patch.object(camera, "_open_with_backends", return_value=cap):
                    with self.assertRaisesRegex(RuntimeError, "frame"):
                        relay.start()
                self.assertEqual(cap.read_count, missing)
                self.assertEqual(cap.release_count, 1)
                self.assertIsNone(relay.cap)
                self.assertIsNone(relay.shm)
                self.assertEqual(relay.controls.snapshot()["actual"], {})

    def test_repeated_drift_or_rejected_correction_fails_without_retry_loop(self):
        for reject in (False, True):
            with self.subTest(reject=reject):
                relay = self.relay()
                cap = FirstReadCapture(drifts={1: {15: -4}, 2: {15: -4}})
                cap.reject = 15 if reject else None
                with mock.patch.object(camera, "_open_with_backends", return_value=cap):
                    with self.assertRaisesRegex(RuntimeError, "exposure"):
                        relay.start()
                self.assertEqual(cap.set_calls, [(1, 15, -5)])
                self.assertLessEqual(cap.read_count, 2)
                self.assertEqual(cap.release_count, 1)
                self.assertIsNone(relay.cap)

    def test_unrequested_controls_and_other_backends_are_not_changed(self):
        for backend, exposure, zoom, expected_reads, expected_sets in (
            (700, None, None, 0, []),
            (1400, -5, 180, 0, []),
            (700, -5, None, 2, [(1, 15, -5)]),
            (700, None, 180, 2, [(1, 27, 180)]),
        ):
            with self.subTest(backend=backend, exposure=exposure, zoom=zoom):
                relay = self.relay(exposure, zoom)
                cap = FirstReadCapture(backend=backend, drifts={1: {15: -4, 27: 100}})
                with mock.patch.object(camera, "_open_with_backends", return_value=cap):
                    relay.start()
                self.assertEqual(cap.read_count, expected_reads)
                self.assertEqual(cap.set_calls, expected_sets)

    def test_reconnect_uses_same_confirmation_before_exposing_actual_values(self):
        for repeat_drift in (False, True):
            with self.subTest(repeat_drift=repeat_drift):
                relay = self.relay()
                old = FirstReadCapture()
                relay.cap = old
                drifts = {1: {15: -4}}
                if repeat_drift:
                    drifts[2] = {15: -4}
                recovered = FirstReadCapture(drifts=drifts)
                recovered.on_read = lambda: self.assertIs(relay.cap, recovered)
                with mock.patch.object(camera, "_open_with_backends", return_value=recovered):
                    self.assertIs(relay._reopen_capture(), not repeat_drift)
                self.assertEqual(old.release_count, 1)
                self.assertEqual(recovered.read_count, 2)
                self.assertEqual(recovered.set_calls, [(1, 15, -5)])
                if repeat_drift:
                    self.assertIsNone(relay.cap)
                    self.assertEqual(recovered.release_count, 1)
                    self.assertIn("exposure", relay.last_error)
                    self.assertEqual(relay.controls.snapshot()["actual"], {})
                else:
                    self.assertEqual(relay.controls.snapshot()["actual"]["exposure"], -5.0)
                    self.assertTrue(relay.close())
                    self.assertEqual(recovered.release_count, 1)

    def test_stop_after_first_read_does_not_correct_or_request_another_frame(self):
        relay = self.relay()
        cap = FirstReadCapture(drifts={1: {15: -4}})
        cap.on_read = relay.stop_event.set
        with mock.patch.object(camera, "_open_with_backends", return_value=cap):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                relay.start()
        self.assertEqual(cap.read_count, 1)
        self.assertEqual(cap.set_calls, [])
        self.assertEqual(cap.release_count, 1)
        self.assertIsNone(relay.cap)


if __name__ == "__main__":
    unittest.main()
