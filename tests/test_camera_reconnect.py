import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import shared_camera as camera


class Frame:
    shape = (2, 2, 3)

    def copy(self):
        return self

    def tobytes(self):
        return bytes(range(12))


class CameraReconnectTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for patch in (
            mock.patch.object(camera, "SESSION_INFO_PATH", str(Path(self.directory.name) / "session.json")),
            mock.patch.object(camera, "enumerate_camera_devices", return_value=["C922"]),
            mock.patch.object(camera.np, "ascontiguousarray", side_effect=lambda frame: frame),
            mock.patch.object(camera, "DEFAULT_READ_FAILURE_REOPEN_THRESHOLD", 1),
            mock.patch.object(camera, "RECONNECT_INITIAL_DELAY", 0.001, create=True),
            mock.patch.object(camera, "RECONNECT_MAX_DELAY", 0.005, create=True),
            mock.patch.object(camera, "CAPTURE_JOIN_TIMEOUT", 0.02, create=True),
            mock.patch("builtins.print"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def relay(self):
        relay = camera.SharedCameraRelay(0, 2, 2, 30, camera_name_hint=["c922"], require_name_match=True)
        self.addCleanup(relay.close)
        return relay

    def test_reader_rejects_empty_stale_unavailable_and_invalid_frame_headers(self):
        relay = self.relay()
        reader = camera.SharedMemoryCamera(relay.shm_name, 2, 2)
        self.addCleanup(reader.release)
        for status, frame_id, timestamp, width in [
            (0, 0, 0.0, 2), (2, 1, time.monotonic() - 10, 2),
            (0, 2, time.monotonic(), 2), (2, 2, time.monotonic(), 10000),
        ]:
            with self.subTest(status=status, frame_id=frame_id, width=width):
                struct.pack_into(camera.HEADER_FORMAT, relay.shm.buf, 0,
                                 camera.MAGIC, width, 2, 3, status, 2, frame_id, timestamp)
                self.assertEqual(reader.read(), (False, None))
                self.assertEqual(reader.last_read_frame_id, 0)

    def test_failed_reopen_retries_and_recovers_without_changing_shared_memory(self):
        relay = self.relay()
        first = mock.Mock()
        first.read.return_value = (False, None)
        recovered = mock.Mock()
        recovered.read.side_effect = lambda: (time.sleep(0.002) or True, Frame())
        relay.cap = first
        relay._create_capture = mock.Mock(side_effect=[None, recovered])
        original_shm = relay.shm_name
        relay.running = True
        errors = []

        def run():
            try:
                relay._capture_loop()
            except BaseException as exc:
                errors.append(exc)

        relay.thread = threading.Thread(target=run)
        relay.thread.start()
        deadline = time.monotonic() + 1
        while relay.frame_id == 0 and relay.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.002)
        frame_id = relay.frame_id
        self.assertTrue(relay.close())
        self.assertEqual(errors, [])
        self.assertGreater(frame_id, 0)
        self.assertEqual(relay.shm_name, original_shm)
        self.assertEqual(relay._create_capture.call_count, 2)
        first.release.assert_called_once()
        recovered.release.assert_called_once()

    def test_stop_during_native_read_or_reopen_keeps_resources_until_worker_exits(self):
        for operation in ("read", "reopen"):
            with self.subTest(operation=operation):
                relay = self.relay()
                entered, finish = threading.Event(), threading.Event()
                cap = mock.Mock()

                def block():
                    entered.set()
                    finish.wait(timeout=2)
                    return (True, Frame()) if operation == "read" else cap

                if operation == "read":
                    relay.cap = cap
                    cap.read.side_effect = block
                else:
                    relay._create_capture = mock.Mock(side_effect=block)
                relay.running = True
                relay.thread = threading.Thread(target=relay._capture_loop)
                relay.thread.start()
                try:
                    self.assertTrue(entered.wait(timeout=1))
                    self.assertFalse(relay.close())
                    cap.release.assert_not_called()
                    self.assertIsNotNone(relay.shm)
                finally:
                    finish.set()
                    relay.thread.join(timeout=1)
                self.assertTrue(relay.close())
                cap.release.assert_called_once()
                self.assertEqual(relay.frame_id, 0)

    def test_manager_reader_does_not_return_old_frame_after_capture_stalls(self):
        relay = self.relay()
        relay.latest_frame = Frame()
        relay.latest_timestamp = time.monotonic() - 10
        self.assertEqual(relay.read(), (False, None))

    def test_session_names_are_unique_and_cleanup_preserves_another_owner(self):
        first, second = self.relay(), self.relay()
        self.assertNotEqual(first.shm_name, second.shm_name)
        first.write_session_file()
        second.write_session_file()
        self.assertTrue(first.close())
        payload = json.loads(Path(camera.SESSION_INFO_PATH).read_text(encoding="utf-8"))
        self.assertEqual(payload["shm_name"], second.shm_name)
        self.assertTrue(second.close())
        self.assertFalse(Path(camera.SESSION_INFO_PATH).exists())

    def test_failed_camera_property_setup_releases_the_candidate_handle(self):
        cap = mock.Mock()
        cap.set.side_effect = RuntimeError("driver rejected properties")
        with (mock.patch.object(camera.cv2, "VideoCapture", return_value=cap),
              mock.patch.object(camera, "_backend_order", return_value=[123])):
            result = camera._open_with_backends(0, 2, 2, 30, "MJPG", "dshow", False, True)
        self.assertIsNone(result)
        cap.release.assert_called_once()

    def test_start_retains_candidate_when_setup_and_release_both_fail(self):
        relay = self.relay()
        cap = mock.Mock()
        cap.set.side_effect = RuntimeError("driver rejected properties")
        cap.release.side_effect = RuntimeError("driver release failed")
        try:
            with (mock.patch.object(camera.cv2, "VideoCapture", return_value=cap) as physical_open,
                  mock.patch.object(camera, "_backend_order", return_value=[123, 456])):
                with self.assertRaises(RuntimeError):
                    relay.start()
                self.assertIs(relay.cap, cap)
                self.assertIn("driver release failed", relay.release_error)
                self.assertIsNone(relay.shm)
                self.assertFalse(relay.close())
                self.assertIs(relay.cap, cap)
                with self.assertRaises(RuntimeError):
                    relay.start()
                self.assertIs(relay.cap, cap)
                physical_open.assert_called_once()
            cap.release.side_effect = None
            self.assertTrue(relay.close())
            self.assertIsNone(relay.cap)
            self.assertIsNone(relay.release_error)
        finally:
            cap.release.side_effect = None

    def test_reconnect_retries_retained_candidate_release_before_another_open(self):
        relay = self.relay()
        cap = mock.Mock()
        cap.set.side_effect = RuntimeError("driver rejected properties")
        cap.release.side_effect = RuntimeError("driver release failed")
        recovered = mock.Mock()
        recovered.get.return_value = 0
        try:
            with (mock.patch.object(camera.cv2, "VideoCapture", side_effect=[cap, recovered]) as physical_open,
                  mock.patch.object(camera, "_backend_order", return_value=[123, 456])):
                self.assertFalse(relay._reopen_capture())
                self.assertIs(relay.cap, cap)
                self.assertIn("driver release failed", relay.release_error)
                self.assertFalse(relay._reopen_capture())
                self.assertIs(relay.cap, cap)
                physical_open.assert_called_once()

                def release():
                    physical_open.assert_called_once()

                cap.release.side_effect = release
                self.assertTrue(relay._reopen_capture())
                self.assertIs(relay.cap, recovered)
                self.assertIsNone(relay.release_error)
                self.assertEqual(physical_open.call_count, 2)
                self.assertTrue(relay.close())
                recovered.release.assert_called_once()
        finally:
            cap.release.side_effect = None

    def test_reconnect_retains_failed_candidate_from_each_native_open_probe(self):
        for operation in ("isOpened", "set", "get", "not_opened"):
            with self.subTest(operation=operation):
                relay = self.relay()
                cap = mock.Mock()
                if operation == "not_opened":
                    cap.isOpened.return_value = False
                else:
                    getattr(cap, operation).side_effect = RuntimeError(f"{operation} failed")
                cap.release.side_effect = RuntimeError("driver release failed")
                try:
                    with (mock.patch.object(camera.cv2, "VideoCapture", return_value=cap) as physical_open,
                          mock.patch.object(camera, "_backend_order", return_value=[123, 456])):
                        self.assertFalse(relay._reopen_capture())
                        self.assertIs(relay.cap, cap)
                        self.assertIn("driver release failed", relay.release_error)
                        self.assertIn("driver release failed", relay.last_error)
                        if operation != "not_opened":
                            self.assertIn(f"{operation} failed", relay.last_error)
                        self.assertFalse(relay._reopen_capture())
                        physical_open.assert_called_once()
                finally:
                    cap.release.side_effect = None
                    self.assertTrue(relay.close())

    def test_clean_candidate_release_allows_next_backend(self):
        first, recovered = mock.Mock(), mock.Mock()
        first.set.side_effect = RuntimeError("driver rejected properties")
        recovered.get.return_value = 0

        def open_capture(index, backend):
            if backend == 123:
                return first
            first.release.assert_called_once()
            return recovered

        with (mock.patch.object(camera.cv2, "VideoCapture", side_effect=open_capture) as physical_open,
              mock.patch.object(camera, "_backend_order", return_value=[123, 456])):
            result = camera._open_with_backends(0, 2, 2, 30, "MJPG", "dshow", False)
        self.assertIs(result, recovered)
        self.assertEqual(physical_open.call_args_list, [mock.call(0, 123), mock.call(0, 456)])
        recovered.release.assert_not_called()

    def test_stop_during_candidate_setup_prevents_backend_fallback(self):
        relay = self.relay()
        cap = mock.Mock()

        def fail_setup(*args):
            relay.stop_event.set()
            raise RuntimeError("driver rejected properties")

        cap.set.side_effect = fail_setup
        with (mock.patch.object(camera.cv2, "VideoCapture", return_value=cap) as physical_open,
              mock.patch.object(camera, "_backend_order", return_value=[123, 456])):
            self.assertFalse(relay._reopen_capture())
        physical_open.assert_called_once()
        cap.release.assert_called_once()
        self.assertIsNone(relay.cap)

    def test_stop_during_native_open_keeps_cleanup_ownership_without_setup(self):
        relay = self.relay()
        cap = mock.Mock()
        cap.release.side_effect = RuntimeError("driver release failed")

        def open_capture(*args):
            relay.stop_event.set()
            return cap

        try:
            with (mock.patch.object(camera.cv2, "VideoCapture", side_effect=open_capture) as physical_open,
                  mock.patch.object(camera, "_backend_order", return_value=[123, 456])):
                self.assertFalse(relay._reopen_capture())
                self.assertIs(relay.cap, cap)
                self.assertIn("driver release failed", relay.release_error)
                self.assertFalse(relay._reopen_capture())
                physical_open.assert_called_once()
                cap.isOpened.assert_not_called()
                cap.set.assert_not_called()
                cap.get.assert_not_called()
        finally:
            cap.release.side_effect = None
            self.assertTrue(relay.close())

    def test_standalone_success_transfers_capture_ownership_to_caller(self):
        first, second = mock.Mock(), mock.Mock()
        first.get.return_value = second.get.return_value = 0
        with (mock.patch.object(camera.cv2, "VideoCapture", side_effect=[first, second]),
              mock.patch.object(camera, "_backend_order", return_value=[123])):
            self.assertIs(camera._open_with_backends(0, 2, 2, 30, "MJPG", "dshow", False), first)
            first.release.assert_not_called()
            first.release()
            self.assertIs(camera._open_with_backends(0, 2, 2, 30, "MJPG", "dshow", False), second)
            first.release.assert_called_once()
            second.release.assert_not_called()
            second.release()

    def test_standalone_source_retries_failed_release_before_another_open(self):
        cap, recovered = mock.Mock(), mock.Mock()
        cap.set.side_effect = RuntimeError("driver rejected properties")
        cap.release.side_effect = RuntimeError("driver release failed")
        recovered.get.return_value = 0
        with (mock.patch.object(camera.SharedMemoryCamera, "from_env", return_value=None),
              mock.patch.object(camera.SharedMemoryCamera, "from_session_file", return_value=None),
              mock.patch.dict(camera.os.environ, {camera.ENV_REQUIRED: "0"}),
              mock.patch.object(camera.cv2, "VideoCapture", side_effect=[cap, recovered]) as physical_open,
              mock.patch.object(camera, "_backend_order", return_value=[123, 456])):
            try:
                with self.assertRaisesRegex(RuntimeError, "driver release failed"):
                    camera.open_camera_source(0, 2, 2, 30)
                with self.assertRaisesRegex(RuntimeError, "driver release failed"):
                    camera.open_camera_source(0, 2, 2, 30)
                physical_open.assert_called_once()

                def release():
                    physical_open.assert_called_once()

                cap.release.side_effect = release
                self.assertIs(camera.open_camera_source(0, 2, 2, 30), recovered)
                self.assertEqual(physical_open.call_count, 2)
                recovered.release.assert_not_called()
            finally:
                cap.release.side_effect = None

    def test_shared_reader_accepts_only_a_complete_fresh_snapshot(self):
        relay = self.relay()
        reader = camera.SharedMemoryCamera(relay.shm_name, 2, 2)
        self.addCleanup(reader.release)
        payload = Frame().tobytes()
        relay.shm.buf[camera.HEADER_SIZE:] = payload
        relay.write_seq, relay.frame_id = 2, 7
        relay._write_header(2, time.monotonic())
        decoded = mock.Mock()
        decoded.reshape.return_value.copy.return_value = payload
        with mock.patch.object(camera.np, "frombuffer", return_value=decoded) as decode:
            self.assertEqual(reader.read(), (True, payload))
        self.assertEqual(decode.call_args.args[0], payload)
        self.assertEqual(reader.last_read_frame_id, 7)
        relay._mark_unavailable()
        self.assertEqual(reader.read(), (False, None))

    def test_failed_shared_memory_close_keeps_reference_for_retry(self):
        relay = self.relay()
        real_shm = relay.shm
        self.addCleanup(real_shm.close)
        self.addCleanup(real_shm.unlink)
        relay.shm = mock.Mock()
        failed_shm = relay.shm
        failed_shm.close.side_effect = [BufferError("still exported"), None]
        self.assertFalse(relay.close())
        self.assertIs(relay.shm, failed_shm)
        self.assertTrue(relay.close())
        self.assertIsNone(relay.shm)


if __name__ == "__main__":
    unittest.main()
