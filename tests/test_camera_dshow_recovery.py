import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.modules.setdefault('cv2', mock.MagicMock())
sys.modules.setdefault('numpy', mock.MagicMock())
import shared_camera as camera


class BlackFrame:
    shape = (2, 2, 3)
    def copy(self):
        return self
    def tobytes(self):
        return bytes(12)


class DShowRecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for patch in (
            mock.patch.multiple(camera.cv2, CAP_PROP_BACKEND=42, CAP_DSHOW=700),
            mock.patch.object(camera, 'SESSION_INFO_PATH', str(Path(directory.name)/'session.json')),
            mock.patch.object(camera, 'choose_camera_index', return_value=1),
            mock.patch.object(camera.np, 'ascontiguousarray', side_effect=lambda frame: frame),
            mock.patch('builtins.print'),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def capture(self):
        cap = mock.Mock()
        cap.get.return_value = 700
        cap.isOpened.return_value = True
        cap.grab.return_value = True
        cap.retrieve.return_value = (True, BlackFrame())
        return cap

    def relay(self):
        relay = camera.SharedCameraRelay(1, 2, 2, 30)
        self.addCleanup(relay.close)
        relay.controls.apply_pending = mock.Mock(return_value={})
        return relay

    def test_nonempty_failed_retrieve_is_not_a_success(self):
        cap = self.capture()
        cap.retrieve.return_value = (False, BlackFrame())
        self.assertEqual(camera._read_physical_frame(cap), (False, None))
        cap.read.assert_not_called()

    def test_failed_grab_does_not_retrieve(self):
        cap = self.capture()
        cap.grab.return_value = False
        self.assertEqual(camera._read_physical_frame(cap), (False, None))
        cap.retrieve.assert_not_called()

    def test_successful_dark_frame_is_accepted(self):
        cap = self.capture()
        ok, frame = camera._read_physical_frame(cap)
        self.assertTrue(ok)
        self.assertEqual(frame.tobytes(), bytes(12))

    def test_other_backend_uses_existing_read(self):
        cap = self.capture()
        cap.get.return_value = 1400
        expected = (True, BlackFrame())
        cap.read.return_value = expected
        self.assertEqual(camera._read_physical_frame(cap), expected)
        cap.grab.assert_not_called()

    def test_startup_control_confirmation_rejects_nonempty_failed_retrieve(self):
        relay = self.relay()
        relay.exposure = -4
        relay.cap = self.capture()
        relay.cap.retrieve.return_value = (False, BlackFrame())
        with self.assertRaisesRegex(RuntimeError, 'first frame unavailable'):
            relay._confirm_first_frame_controls()
        relay.cap.set.assert_not_called()

    def test_fps_diagnostic_does_not_count_failed_retrieve(self):
        cap = self.capture()
        cap.retrieve.return_value = (False, BlackFrame())
        with mock.patch.object(camera.time, 'perf_counter', side_effect=[0, 0, .75, 2]):
            self.assertEqual(camera._measure_capture_fps(cap, 2), (0.0, 0))

    def test_slow_failures_reopen_before_thirty_attempts_and_keep_shared_memory(self):
        relay = self.relay()
        first, recovered = self.capture(), self.capture()
        relay.cap = first
        relay._create_capture = mock.Mock(return_value=recovered)
        original_shm = relay.shm_name
        clock = [100.0]
        def failed():
            clock[0] += 1.0
            return False, BlackFrame()
        def success():
            relay.running = False
            return True, BlackFrame()
        first.retrieve.side_effect = failed
        recovered.retrieve.side_effect = success
        relay.running = True
        with mock.patch.object(camera.time, 'monotonic', side_effect=lambda: clock[0]):
            relay._capture_loop()
        self.assertEqual(first.retrieve.call_count, 5)
        self.assertEqual(relay.read_failures_total, 5)
        self.assertEqual(relay.reopen_attempts, 1)
        self.assertEqual(relay.frame_id, 1)
        self.assertEqual(relay.shm_name, original_shm)
        first.release.assert_called_once()
        recovered.release.assert_called_once()

    def test_success_resets_failure_duration_without_reopen(self):
        relay = self.relay()
        relay.cap = self.capture()
        relay._create_capture = mock.Mock()
        clock = [100.0]
        results = iter([False, False, True, False, False, True])
        calls = [0]
        def retrieve():
            clock[0] += 2.0
            calls[0] += 1
            if calls[0] == 6:
                relay.running = False
            return next(results), BlackFrame()
        relay.cap.retrieve.side_effect = retrieve
        relay.running = True
        with mock.patch.object(camera.time, 'monotonic', side_effect=lambda: clock[0]):
            relay._capture_loop()
        self.assertEqual(relay.frame_id, 2)
        self.assertEqual(relay.reopen_attempts, 0)
        relay._create_capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
