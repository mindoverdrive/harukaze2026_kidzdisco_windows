"""Run guarded lifecycle regressions without cameras, windows, or real children."""
import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import ctypes
import importlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
camera = None
scene_control = None


class InMemorySocket:
    """Socket-shaped byte transport; no operating-system network I/O."""
    def __init__(self):
        self.incoming = bytearray()
        self.peer = None

    def setblocking(self, value):
        pass

    def settimeout(self, value):
        pass

    def sendall(self, data):
        self.peer.incoming.extend(data)

    def recv(self, count):
        if not self.incoming:
            raise BlockingIOError()
        data = bytes(self.incoming[:count])
        del self.incoming[:count]
        return data

    def close(self):
        pass


def in_memory_protocol_setup(test):
    listener = mock.Mock()
    listener.getsockname.return_value = ("127.0.0.1", 0)
    with mock.patch.object(scene_control.socket, "socket", return_value=listener):
        test.control = scene_control.SceneLaunchControl(
            ready_timeout=1, ack_timeout=1, frame_timeout=2)
    test.addCleanup(test.control.close)
    test.peer, server = InMemorySocket(), InMemorySocket()
    test.peer.peer, server.peer = server, test.peer
    test.control.channel = scene_control.JsonChannel(server)
    test.addCleanup(test.peer.close)
    test.proc = mock.Mock(pid=123, returncode=None)
    test.proc.poll.return_value = None


class SupplementaryCameraTests(unittest.TestCase):
    def test_c922_hint_matches_c922n_and_excludes_integrated_and_virtual(self):
        devices = ["Integrated Camera", "Virtual C922", "Logitech C922n Pro Stream Webcam"]
        with mock.patch.object(camera, "enumerate_camera_devices", return_value=devices):
            self.assertEqual(camera.choose_camera_index(
                0, ["c922"], ["virtual", "integrated"], require_name_match=True), 2)
            with self.assertRaises(RuntimeError):
                camera.choose_camera_index(
                    0, ["c922"], ["virtual", "integrated"], explicit_index=0,
                    require_name_match=True)

    def test_strict_dshow_failure_never_opens_another_backend_or_index(self):
        cap = mock.Mock()
        cap.isOpened.return_value = False
        with mock.patch.object(camera.cv2, "CAP_DSHOW", 700), \
             mock.patch.object(camera.cv2, "VideoCapture", return_value=cap) as opening:
            self.assertIsNone(camera._open_with_backends(
                2, 1280, 720, 30, "MJPG", "dshow", False, strict_backend=True))
        opening.assert_called_once_with(2, 700)
        cap.release.assert_called_once()

    def test_missing_enumeration_cannot_choose_integrated_by_fallback(self):
        with mock.patch.object(camera, "enumerate_camera_devices", return_value=[]):
            with self.assertRaises(RuntimeError):
                camera.choose_camera_index(0, ["c922"], require_name_match=True)
            with self.assertRaises(RuntimeError):
                camera.choose_camera_index(0, ["c922"], explicit_index=0, require_name_match=True)

    def test_drifted_frame_size_is_normalized_before_shared_publish(self):
        class Frame:
            def __init__(self, shape):
                self.shape = shape

            def tobytes(self):
                return bytes(self.shape[0] * self.shape[1] * self.shape[2])

            def copy(self):
                return self

        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(camera, "SESSION_INFO_PATH", str(Path(temporary) / "session.json")), \
             mock.patch.object(camera, "choose_camera_index", return_value=2):
            relay = camera.SharedCameraRelay(2, 4, 2, 30)
            try:
                relay.cap = mock.Mock()
                relay.running = True
                source, normalized = Frame((8, 16, 3)), Frame((2, 4, 3))

                def next_frame(*unused):
                    relay.running = False
                    return True, source

                with mock.patch.object(camera, "_read_physical_frame", side_effect=next_frame), \
                     mock.patch.object(camera.cv2, "resize", return_value=normalized) as resize, \
                     mock.patch.object(camera.np, "ascontiguousarray", side_effect=lambda frame: frame):
                    relay._capture_loop()
                resize.assert_called_once_with(source, (4, 2), interpolation=camera.cv2.INTER_LINEAR)
                self.assertEqual(relay.frame_id, 1)
                self.assertEqual(relay.read_failures_total, 0)
                self.assertEqual(relay.frame_bytes, 24)
            finally:
                relay.close()


MODULES = (
    "test_camera_profile", "test_camera_dshow_recovery", "test_camera_first_frame_controls",
    "test_camera_reconnect", "test_camera_coordinates", "test_cleanup",
    "test_scene_navigation", "test_staff_lifecycle", "test_staff_protocol",
    "test_launch_production", "test_windows_containment", "test_staff_safe_regressions",
)
WINDOWS_MOCK_CASES = (
    "test_failed_job_close_keeps_only_failed_handle_and_retries",
    "test_termination_failure_still_attempts_each_owned_job",
    "test_rejected_separate_job_assignment_is_not_reported_as_owned",
    "test_constructor_adoption_failure_retains_all_known_jobs_for_cleanup",
)


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main(argv=None):
    global camera, scene_control
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "test_reports" / "lifecycle-headless")
    parser.add_argument("--dependency-root", type=Path,
                        help="Optional unchanged checkout fallback when testing a partial candidate directory")
    args = parser.parse_args(argv)
    report = args.report_dir.resolve()
    fixture_temp = report / "fixture-temp"
    fixture_temp.mkdir(parents=True, exist_ok=True)
    previous_temp = tempfile.tempdir
    previous_path = sys.path[:]
    dependency_root = args.dependency_root.resolve() if args.dependency_root else ROOT
    sys.path[:0] = [str(ROOT), str(ROOT / "tests"),
                   str(dependency_root), str(dependency_root / "tests")]
    tempfile.tempdir = str(fixture_temp)
    log = io.StringIO()
    result = None
    try:
        with ExitStack() as stack, redirect_stdout(log), redirect_stderr(log):
            stack.enter_context(mock.patch.dict(sys.modules, {
                "cv2": mock.MagicMock(name="NO_NATIVE_CV2"),
                "numpy": mock.MagicMock(name="NO_NATIVE_NUMPY"),
            }))
            stack.enter_context(mock.patch.object(
                subprocess, "Popen", side_effect=AssertionError("NO_REAL_PROCESS_SPAWN")))
            stack.enter_context(mock.patch.object(
                subprocess, "run", side_effect=AssertionError("NO_REAL_SUBPROCESS_COMMAND")))
            stack.enter_context(mock.patch.object(
                socket, "socket", side_effect=AssertionError("NO_REAL_SOCKET")))
            stack.enter_context(mock.patch.object(
                socket, "create_connection", side_effect=AssertionError("NO_REAL_NETWORK")))
            if hasattr(ctypes, "WinDLL"):
                stack.enter_context(mock.patch.object(
                    ctypes, "WinDLL", side_effect=AssertionError("NO_REAL_WINDOWS_LIBRARY")))
            camera = importlib.import_module("shared_camera")
            windows_process = importlib.import_module("windows_process")
            scene_control = importlib.import_module("scene_control")
            stack.enter_context(mock.patch.object(
                windows_process, "_kernel", side_effect=AssertionError("NO_NATIVE_KERNEL")))
            stack.enter_context(mock.patch.object(
                windows_process, "_process_parents", side_effect=AssertionError("NO_PROCESS_ENUMERATION")))
            manager = importlib.import_module("manager")
            # Candidate runs use unchanged scene/config assets from the supplied checkout.
            if args.dependency_root:
                manager.BASE_DIR = str(dependency_root)
                manager.CONFIG_PATH = str(dependency_root / "config.json")
                manager.CONFIG = manager.load_config(manager.CONFIG_PATH)
            loader = unittest.TestLoader()
            suite = unittest.TestSuite()
            for name in MODULES:
                module = importlib.import_module(name)
                if name == "test_staff_protocol":
                    stack.enter_context(mock.patch.object(
                        module.StaffProtocolTests, "setUp", in_memory_protocol_setup))
                suite.addTests(loader.loadTestsFromModule(module))
            switching = importlib.import_module("test_scene_switch")
            suite.addTests(case for case in flatten(loader.loadTestsFromModule(switching))
                           if "test_real_manager_can_repeat_fixture_scene_switches" not in case.id())
            for name in WINDOWS_MOCK_CASES:
                suite.addTests(loader.loadTestsFromName("test_windows_launcher.WindowsLauncherTests." + name))
            suite.addTests(loader.loadTestsFromTestCase(SupplementaryCameraTests))
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    finally:
        tempfile.tempdir = previous_temp
        sys.path[:] = previous_path
        (report / "tests.txt").write_text(log.getvalue(), encoding="utf-8")
    summary = {
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "success": result.wasSuccessful(),
        "camera_and_array_libraries": "mocked",
        "process_kernel_and_network_calls": "blocked except individually scoped test mocks",
        "protocol_transport": "in-memory bytes using real JsonChannel and SceneLaunchControl",
        "shared_memory": "owned synthetic fixture segments",
        "excluded": "Real camera, models, drawing, subprocess/Windows Job integration, process enumeration, TCP",
    }
    (report / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Detailed results: " + str(report / "tests.txt"))
    if not result.wasSuccessful():
        print(log.getvalue()[-12000:])
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
