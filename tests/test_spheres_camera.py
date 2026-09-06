"""Camera feed contracts, exercised without native cameras, models, or windows."""

import ast
from contextlib import ExitStack
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
from queue import Empty, Queue
from types import SimpleNamespace
import sys
import threading
import time
import unittest
from unittest import mock

from spheres_camera import CameraSnapshot, SpheresCameraFeed


class NativeFakes:
    def __init__(self):
        self.frames = Queue()
        self.reading = threading.Event()
        self.calls = []
        self.clock = 20.0
        self.camera = mock.Mock(last_read_frame_id=0, shm_name="fake-manager-camera")
        self.camera.isOpened.return_value = True
        self.camera.read.side_effect = self.read
        self.camera.release.side_effect = lambda: self.record("camera.release")
        self.hands = mock.Mock()
        self.hands.process.return_value = SimpleNamespace(multi_hand_landmarks=[])
        self.hands.close.side_effect = lambda: self.record("hands.close")
        self.make_hands = mock.Mock(return_value=self.hands)
        self.camera_image = object()
        self.stage_image = object()
        self.layout = object()
        self.camera_rgb = mock.Mock()
        self.stage_rgb = mock.Mock()
        self.stage_rgb.tobytes.return_value = b"RGB stage pixels"
        self.cv2 = mock.Mock(COLOR_BGR2RGB=4)
        self.cv2.cvtColor.side_effect = self.convert
        self.display = mock.Mock()
        self.display.open_camera.return_value = self.camera
        self.display.prepare_camera_frame.return_value = (
            self.camera_image, self.stage_image, self.layout)

    def record(self, name):
        self.calls.append((name, threading.get_ident()))

    def read(self):
        self.record("camera.read")
        self.reading.set()
        try:
            item = self.frames.get(timeout=0.01)
        except Empty:
            return False, None
        if callable(item):
            item = item()
        if isinstance(item, BaseException):
            raise item
        frame_id, frame = item
        self.camera.last_read_frame_id = frame_id
        return frame is not None, frame

    def convert(self, frame, conversion):
        if frame is self.camera_image:
            return self.camera_rgb
        if frame is self.stage_image:
            return self.stage_rgb
        raise AssertionError("Unexpected image conversion")

    def load(self):
        self.record("load")
        return self.display, self.cv2, self.make_hands

    def feed(self, **kwargs):
        return SpheresCameraFeed(100, 60, _native_loader=self.load,
                                 _clock=lambda: self.clock, **kwargs)

    def hold_read(self):
        entered, gate = threading.Event(), threading.Event()

        def hold():
            entered.set()
            if not gate.wait(2.0):
                raise AssertionError("Test did not release the fake native read")
            return 0, None

        self.frames.put(hold)
        return entered, gate


class SpheresCameraTests(unittest.TestCase):
    def await_snapshot(self, feed):
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            snapshot = feed.latest()
            if snapshot is not None:
                return snapshot
            time.sleep(0.001)
        self.fail("Worker did not publish a frame")

    def await_error(self, feed):
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            try:
                feed.latest()
            except RuntimeError as error:
                return error
            time.sleep(0.001)
        self.fail("Worker error did not reach latest()")

    def test_read_failure_invalidates_the_frame_then_recovery_publishes_only_the_latest(self):
        native = NativeFakes()
        native.frames.put((1, object()))
        first_entered, first_gate = native.hold_read()
        failed_entered, failed_gate = native.hold_read()
        native.frames.put((2, object()))
        native.frames.put((3, object()))
        recovered_entered, recovered_gate = native.hold_read()
        feed = native.feed().start()
        try:
            self.assertTrue(first_entered.wait(1.0))
            first = self.await_snapshot(feed)
            first_gate.set()  # The held read returns (False, None).
            self.assertTrue(failed_entered.wait(1.0))
            self.assertIsNone(feed.latest())
            native.clock = 20.1
            failed_gate.set()
            self.assertTrue(recovered_entered.wait(1.0))
            latest = self.await_snapshot(feed)
            self.assertEqual(latest.last_read_frame_id, 3)
            self.assertEqual(first.last_read_frame_id, 1)
            self.assertEqual(native.hands.process.call_count, 3)
        finally:
            first_gate.set()
            failed_gate.set()
            recovered_gate.set()
            feed.close()

    def test_camera_and_tips_use_the_same_letterbox_layout(self):
        native = NativeFakes()
        native.layout = dict(offset_x=10, offset_y=0, scaled_width=80, scaled_height=60)
        native.display.prepare_camera_frame.return_value = (
            native.camera_image, native.stage_image, native.layout)
        # Reuse the real pure projection helper without importing native dependencies.
        path = Path(__file__).resolve().parents[1] / "display_utils.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        projection = next(node for node in tree.body
                          if isinstance(node, ast.FunctionDef) and node.name == "normalized_to_stage")
        namespace = {}
        exec(compile(ast.Module(body=[projection], type_ignores=[]), str(path), "exec"), namespace)
        native.display.normalized_to_stage.side_effect = namespace["normalized_to_stage"]
        hands = [SimpleNamespace(landmark=[None] * 8 + [SimpleNamespace(x=x, y=y)])
                 for x, y in ((0.0, 0.0), (1.0, 1.0))]
        native.hands.process.return_value = SimpleNamespace(multi_hand_landmarks=hands)
        native.frames.put((1, object()))
        entered, gate = native.hold_read()
        feed = native.feed().start()
        try:
            self.assertTrue(entered.wait(1.0))
            snapshot = self.await_snapshot(feed)
            self.assertEqual(snapshot.tips, ((10, 0), (89, 59)))
            for call in native.display.normalized_to_stage.call_args_list:
                self.assertIs(call.args[2], native.layout)
            self.assertEqual(snapshot.rgb_bytes, b"RGB stage pixels")
            native.hands.process.assert_called_once_with(native.camera_rgb)
        finally:
            gate.set()
            feed.close()

    def test_slow_inference_does_not_block_latest_or_make_an_old_frame_fresh(self):
        native = NativeFakes()
        entered, gate = threading.Event(), threading.Event()

        def process(_image):
            entered.set()
            if not gate.wait(2.0):
                raise AssertionError("Test did not release fake inference")
            return SimpleNamespace(multi_hand_landmarks=[])

        native.hands.process.side_effect = process
        native.frames.put((1, object()))
        next_read, next_gate = native.hold_read()
        feed = native.feed().start()
        try:
            self.assertTrue(entered.wait(1.0))
            self.assertIsNone(feed.latest())
            native.clock = 20.5
            gate.set()
            self.assertTrue(next_read.wait(1.0))
            self.assertIsNone(feed.latest())
        finally:
            gate.set()
            next_gate.set()
            feed.close()

    def test_startup_and_runtime_errors_propagate_and_release_all_acquired_resources(self):
        for boundary in ("open", "is_open", "hands", "read", "process"):
            with self.subTest(boundary=boundary):
                native = NativeFakes()
                failure = ValueError(f"injected {boundary} failure")
                if boundary == "open":
                    native.display.open_camera.side_effect = failure
                elif boundary == "is_open":
                    native.camera.isOpened.side_effect = failure
                elif boundary == "hands":
                    native.make_hands.side_effect = failure
                elif boundary == "read":
                    native.frames.put(failure)
                else:
                    native.hands.process.side_effect = failure
                    native.frames.put((1, object()))
                feed = native.feed().start()
                try:
                    self.assertIs(self.await_error(feed).__cause__, failure)
                finally:
                    feed.close()  # latest() already reported this failure.
                self.assertEqual(native.camera.release.call_count, int(boundary != "open"))
                self.assertEqual(native.hands.close.call_count, int(boundary in {"read", "process"}))

    def test_cleanup_failure_still_releases_camera_and_preserves_the_processing_error(self):
        native = NativeFakes()
        primary = ValueError("injected processing failure")
        processing_failed = threading.Event()

        def process(_image):
            processing_failed.set()
            raise primary

        native.frames.put((1, object()))
        native.hands.process.side_effect = process
        native.hands.close.side_effect = RuntimeError("injected Hands cleanup failure")
        feed = native.feed().start()
        try:
            self.assertTrue(processing_failed.wait(1.0))
        finally:
            with self.assertRaises(RuntimeError) as closing:
                feed.close()
        self.assertIs(closing.exception.__cause__, primary)
        self.assertIn("injected Hands cleanup failure", " ".join(primary.__notes__))
        native.camera.release.assert_called_once_with()

    def test_reported_worker_error_is_not_replaced_during_context_cleanup(self):
        native = NativeFakes()
        native.frames.put(ValueError("injected read failure"))
        original = None
        with self.assertRaises(RuntimeError) as caught:
            with ExitStack() as resources:
                feed = native.feed().start()
                resources.callback(feed.close)
                original = self.await_error(feed)
                raise original
        self.assertIs(caught.exception, original)
        native.hands.close.assert_called_once_with()
        native.camera.release.assert_called_once_with()

    def test_new_cleanup_failure_is_reported_after_latest_reported_the_worker_failure(self):
        native = NativeFakes()
        primary = ValueError("injected processing failure")
        cleanup_error = ValueError("injected new cleanup failure")
        entered, gate = threading.Event(), threading.Event()

        def close_hands():
            entered.set()
            if not gate.wait(2.0):
                raise AssertionError("Test did not release Hands cleanup")
            raise cleanup_error

        native.hands.process.side_effect = primary
        native.hands.close.side_effect = close_hands
        native.frames.put((1, object()))
        feed = native.feed().start()
        try:
            self.assertTrue(entered.wait(1.0))
            self.assertIs(self.await_error(feed).__cause__, primary)
        finally:
            gate.set()
            with self.assertRaises(RuntimeError) as closing:
                feed.close()
        self.assertIs(closing.exception.__cause__, cleanup_error)
        feed.close()  # This cleanup failure has now also been reported.
        native.camera.release.assert_called_once_with()

    def test_close_is_bounded_and_never_releases_resources_during_a_native_call(self):
        for boundary in ("open", "hands", "read", "process"):
            with self.subTest(boundary=boundary):
                native = NativeFakes()
                entered, gate = threading.Event(), threading.Event()
                owners = []

                def blocked(*_args, **_kwargs):
                    owners.append(threading.current_thread())
                    entered.set()
                    if not gate.wait(2.0):
                        raise AssertionError("Test did not release the blocked native call")
                    return {
                        "open": native.camera, "hands": native.hands,
                        "read": (1, object()),
                        "process": SimpleNamespace(multi_hand_landmarks=[]),
                    }[boundary]

                if boundary == "open":
                    native.display.open_camera.side_effect = blocked
                elif boundary == "hands":
                    native.make_hands.side_effect = blocked
                elif boundary == "read":
                    native.frames.put(blocked)
                else:
                    native.hands.process.side_effect = blocked
                    native.frames.put((1, object()))
                feed = native.feed(_close_timeout=0.02).start()
                try:
                    self.assertTrue(entered.wait(1.0))
                    self.assertIsNone(feed.latest())
                    started = time.monotonic()
                    with self.assertRaisesRegex(RuntimeError, "native resources remain"):
                        feed.close()
                    self.assertLess(time.monotonic() - started, 0.5)
                    native.camera.release.assert_not_called()
                    native.hands.close.assert_not_called()
                    self.assertTrue(owners[0].daemon)
                finally:
                    gate.set()
                    feed.close()
                self.assertFalse(owners[0].is_alive())
                native.camera.release.assert_called_once_with()
                if boundary == "open":
                    native.make_hands.assert_not_called()
                else:
                    native.hands.close.assert_called_once_with()

    def test_missing_shared_required_setting_refuses_to_open_a_physical_camera(self):
        display = mock.Mock()
        with mock.patch.dict(os.environ, {"HARUKAZE_SHARED_CAMERA_REQUIRED": "0"}), \
                mock.patch.dict(sys.modules, {"display_utils": display, "cv2": None,
                                              "mediapipe": None, "pygame": None}):
            feed = SpheresCameraFeed(100, 60).start()
            try:
                self.assertIn("requires the Manager shared camera", str(self.await_error(feed)))
            finally:
                feed.close()
        display.open_camera.assert_not_called()

    def test_default_loader_uses_the_shared_helper_and_does_not_import_pygame(self):
        native = NativeFakes()
        mp = SimpleNamespace(solutions=SimpleNamespace(hands=SimpleNamespace(Hands=native.make_hands)))
        native.frames.put((1, object()))
        entered, gate = native.hold_read()
        with mock.patch.dict(os.environ, {"HARUKAZE_SHARED_CAMERA_REQUIRED": "1"}), \
                mock.patch.dict(sys.modules, {"display_utils": native.display, "cv2": native.cv2,
                                              "mediapipe": mp, "pygame": None}):
            feed = SpheresCameraFeed(100, 60, _clock=lambda: native.clock).start()
            try:
                self.assertTrue(entered.wait(1.0))
                self.assertEqual(self.await_snapshot(feed).shm_name, "fake-manager-camera")
            finally:
                gate.set()
                feed.close()
        native.display.open_camera.assert_called_once_with()

    def test_start_and_close_are_idempotent_and_closed_feed_cannot_restart(self):
        native = NativeFakes()
        feed = native.feed()
        self.assertIsNone(feed.latest())
        try:
            self.assertIs(feed.start(), feed)
            self.assertTrue(native.reading.wait(1.0))
            self.assertIs(feed.start(), feed)
        finally:
            feed.close()
        feed.close()
        native.display.open_camera.assert_called_once_with()
        native.camera.release.assert_called_once_with()
        native.hands.close.assert_called_once_with()
        with self.assertRaisesRegex(RuntimeError, "closed"):
            feed.start()

    def test_thread_start_failure_does_not_break_close_or_open_native_resources(self):
        native = NativeFakes()
        feed = native.feed()
        with mock.patch("spheres_camera.threading.Thread.start", side_effect=RuntimeError("injected start failure")):
            with self.assertRaisesRegex(RuntimeError, "injected start failure"):
                feed.start()
        feed.close()
        native.display.open_camera.assert_not_called()

    def test_interrupted_start_keeps_a_started_worker_owned_until_close(self):
        native = NativeFakes()
        entered, gate = threading.Event(), threading.Event()
        owners = []

        def open_camera():
            owners.append(threading.current_thread())
            entered.set()
            if not gate.wait(2.0):
                raise AssertionError("Test did not release camera initialization")
            return native.camera

        native.display.open_camera.side_effect = open_camera
        actual_start = threading.Thread.start

        def start_then_interrupt(worker):
            actual_start(worker)
            if not entered.wait(1.0):
                raise AssertionError("Worker did not enter camera initialization")
            raise KeyboardInterrupt()

        feed = native.feed(_close_timeout=0.02)
        try:
            with mock.patch("spheres_camera.threading.Thread.start", start_then_interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    feed.start()
            with self.assertRaisesRegex(RuntimeError, "native resources remain"):
                feed.close()
            native.camera.release.assert_not_called()
        finally:
            gate.set()
            feed.close()
            for worker in owners:
                worker.join(1.0)
        native.camera.release.assert_called_once_with()

    def test_stop_during_dependency_loading_does_not_open_resources(self):
        native = NativeFakes()
        entered, gate = threading.Event(), threading.Event()

        def load():
            entered.set()
            if not gate.wait(2.0):
                raise AssertionError("Test did not release dependency loading")
            return native.load()

        feed = SpheresCameraFeed(100, 60, _native_loader=load, _close_timeout=0.02).start()
        try:
            self.assertTrue(entered.wait(1.0))
            with self.assertRaisesRegex(RuntimeError, "did not stop"):
                feed.close()
        finally:
            gate.set()
            feed.close()
        native.display.open_camera.assert_not_called()
        native.make_hands.assert_not_called()

    def test_cleanup_errors_are_visible_and_do_not_skip_the_other_release(self):
        for boundary in ("hands", "camera"):
            with self.subTest(boundary=boundary):
                native = NativeFakes()
                failure = ValueError(f"injected {boundary} close failure")
                callback = native.hands.close if boundary == "hands" else native.camera.release
                callback.side_effect = failure
                feed = native.feed().start()
                self.assertTrue(native.reading.wait(1.0))
                with self.assertRaises(RuntimeError) as closing:
                    feed.close()
                self.assertIs(closing.exception.__cause__, failure)
                native.camera.release.assert_called_once_with()
                native.hands.close.assert_called_once_with()

    def test_close_waits_for_worker_cleanup_and_reports_a_blocked_cleanup(self):
        native = NativeFakes()
        entered, gate = threading.Event(), threading.Event()

        def close_hands():
            entered.set()
            if not gate.wait(2.0):
                raise AssertionError("Test did not release Hands cleanup")

        native.hands.close.side_effect = close_hands
        feed = native.feed(_close_timeout=0.02).start()
        try:
            self.assertTrue(native.reading.wait(1.0))
            with self.assertRaisesRegex(RuntimeError, "did not stop"):
                feed.close()
            self.assertTrue(entered.wait(1.0))
            native.camera.release.assert_not_called()
        finally:
            gate.set()
            feed.close()
        native.hands.close.assert_called_once_with()
        native.camera.release.assert_called_once_with()

    def test_stop_during_frame_processing_skips_further_native_work(self):
        for boundary in ("prepare", "convert", "process"):
            with self.subTest(boundary=boundary):
                native = NativeFakes()
                entered, gate = threading.Event(), threading.Event()

                def blocked(*_args, **_kwargs):
                    entered.set()
                    if not gate.wait(2.0):
                        raise AssertionError("Test did not release frame processing")
                    return {
                        "prepare": (native.camera_image, native.stage_image, native.layout),
                        "convert": native.camera_rgb,
                        "process": SimpleNamespace(multi_hand_landmarks=[]),
                    }[boundary]

                if boundary == "prepare":
                    native.display.prepare_camera_frame.side_effect = blocked
                elif boundary == "convert":
                    native.cv2.cvtColor.side_effect = blocked
                else:
                    native.hands.process.side_effect = blocked
                native.frames.put((1, object()))
                feed = native.feed(_close_timeout=0.02).start()
                try:
                    self.assertTrue(entered.wait(1.0))
                    with self.assertRaisesRegex(RuntimeError, "did not stop"):
                        feed.close()
                finally:
                    gate.set()
                    feed.close()
                if boundary != "process":
                    native.hands.process.assert_not_called()
                native.stage_rgb.tobytes.assert_not_called()

    def test_latest_expires_at_half_a_second_while_camera_read_is_blocked(self):
        native = NativeFakes()
        native.frames.put((1, object()))
        entered = threading.Event()
        gate = threading.Event()

        def blocked_read():
            entered.set()
            gate.wait(2.0)
            return 0, None

        native.frames.put(blocked_read)
        feed = native.feed().start()
        try:
            self.assertTrue(entered.wait(1.0))
            snapshot = self.await_snapshot(feed)
            native.clock += 0.499
            self.assertIs(feed.latest(), snapshot)
            native.clock = 20.5
            self.assertIsNone(feed.latest())
        finally:
            gate.set()
            feed.close()

    def test_repeated_shared_frame_does_not_repeat_detection_or_refresh_its_age(self):
        native = NativeFakes()
        native.frames.put((7, object()))

        def same_shared_frame():
            native.clock = 20.2
            return 7, object()

        native.frames.put(same_shared_frame)
        entered, gate = native.hold_read()
        feed = native.feed().start()
        try:
            self.assertTrue(entered.wait(1.0))
            snapshot = self.await_snapshot(feed)
            self.assertEqual(snapshot.timestamp, 20.0)
            native.hands.process.assert_called_once_with(native.camera_rgb)
            native.clock = 20.5
            self.assertIsNone(feed.latest())
        finally:
            gate.set()
            feed.close()

    def test_start_publishes_an_immutable_snapshot_and_close_releases_on_worker(self):
        native = NativeFakes()
        frame = object()
        native.frames.put((17, frame))
        # Hold the next read so a failed read cannot invalidate the observed frame.
        gate = threading.Event()
        native.frames.put(lambda: (gate.wait(2.0), None))
        feed = native.feed()
        try:
            self.assertIs(feed.start(), feed)
            snapshot = self.await_snapshot(feed)
            self.assertIsInstance(snapshot, CameraSnapshot)
            self.assertEqual(snapshot.timestamp, 20.0)
            self.assertEqual(snapshot.rgb_bytes, b"RGB stage pixels")
            self.assertEqual(snapshot.size, (100, 60))
            self.assertEqual(snapshot.tips, ())
            self.assertEqual(snapshot.last_read_frame_id, 17)
            self.assertEqual(snapshot.shm_name, "fake-manager-camera")
            with self.assertRaises(FrozenInstanceError):
                snapshot.timestamp = 0
            native.hands.process.assert_called_once_with(native.camera_rgb)
            native.display.prepare_camera_frame.assert_called_once_with(frame, 100, 60)
            native.make_hands.assert_called_once_with(
                model_complexity=1, max_num_hands=6,
                min_detection_confidence=0.7, min_tracking_confidence=0.5)
        finally:
            gate.set()
            feed.close()
        self.assertIsNone(feed.latest())
        native.camera.release.assert_called_once_with()
        native.hands.close.assert_called_once_with()
        owner_threads = {ident for _name, ident in native.calls}
        self.assertEqual(len(owner_threads), 1)
        self.assertNotIn(threading.get_ident(), owner_threads)


if __name__ == "__main__":
    unittest.main()
