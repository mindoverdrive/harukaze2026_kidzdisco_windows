import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from runtime_diagnostics import RuntimeDiagnostics, process_sample


class RuntimeDiagnosticsTests(unittest.TestCase):
    def _assert_spontaneous_exit_is_logged(self, launcher_exit_code):
        from unittest import mock
        from types import SimpleNamespace
        sys.modules.setdefault("cv2", mock.MagicMock())
        sys.modules.setdefault("numpy", mock.MagicMock())
        import manager
        process = SimpleNamespace(pid=456789, poll=lambda: launcher_exit_code)
        scene_manager = mock.Mock(
            running_process=process, current_scene_name="fixture_acer.py", switch_pending=False,
            fatal_error=None, completed_switches=1, last_switch_error=None,
        )
        scene_manager.is_scene_running.return_value = False
        scene_manager.cleanup.return_value = True
        relay = mock.Mock()
        relay.export_env.return_value = {}
        relay.thread.is_alive.return_value = True
        relay.close.return_value = True
        config = dict(manager.DEFAULT_CONFIG, CLAP_MONITOR_ENABLED=False)
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(manager, "CONFIG", config),
            mock.patch.object(manager, "resolve_production_scenes", return_value=["fixture_acer.py"]),
            mock.patch.object(manager, "SharedCameraRelay", return_value=relay),
            mock.patch.object(manager, "SceneManager", return_value=scene_manager),
            mock.patch.object(RuntimeDiagnostics, "sample"),
            mock.patch.object(manager.cv2, "waitKey", return_value=ord("q")),
            mock.patch.object(sys, "argv", ["manager.py", "--report-dir", directory]),
            mock.patch("builtins.print") as output,
        ):
            self.assertEqual(manager.main(), 0)
            records = [json.loads(line) for line in (Path(directory) / "runtime.jsonl").read_text(encoding="utf-8").splitlines()]
            exits = [record for record in records if record["event"] == "scene_exit"]
            self.assertEqual(len(exits), 1)
            self.assertEqual(exits[0]["scene"], "fixture_acer.py")
            self.assertEqual(exits[0]["launcher_pid"], process.pid)
            self.assertEqual(exits[0]["launcher_exit_code"], launcher_exit_code)
            self.assertIs(exits[0]["switch_pending"], False)
            self.assertTrue(any('"event": "scene_exit"' in str(call.args[0])
                                and f'"launcher_exit_code": {launcher_exit_code}' in str(call.args[0])
                                for call in output.call_args_list if call.args))
        # Initial launch plus the existing automatic next-scene request; logging
        # must not change how a normally or abnormally exited scene is handled.
        self.assertEqual(scene_manager.switch_scene.call_count, 2)
        scene_manager.cleanup.assert_called_once_with()
        relay.close.assert_called_once_with()

    def test_spontaneous_zero_exit_is_logged_before_launching_next(self):
        self._assert_spontaneous_exit_is_logged(0)

    def test_spontaneous_nonzero_exit_is_logged_before_launching_next(self):
        self._assert_spontaneous_exit_is_logged(23)

    def test_duration_trial_waits_for_first_frame_before_counting_time(self):
        from unittest import mock
        import time
        sys.modules.setdefault("cv2", mock.MagicMock())
        sys.modules.setdefault("numpy", mock.MagicMock())
        import manager
        fixture = Path(__file__).parent / "fixtures" / "handshake_scene_acer.py"
        relay = mock.Mock(shm_name="camera-free-test", frame_id=42, read_failures_total=0,
                          reopen_attempts=0, last_error=None, last_success_at=time.monotonic(), max_frame_gap=0)
        relay.export_env.return_value = {}
        relay.thread.is_alive.return_value = True
        config = dict(manager.DEFAULT_CONFIG, CLAP_MONITOR_ENABLED=False, PRELOAD_COUNT=0, TRANSITION_ENABLED=False)
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(manager, "CONFIG", config),
            mock.patch.object(manager, "resolve_production_scenes", return_value=[str(fixture)]),
            mock.patch.object(manager, "SharedCameraRelay", return_value=relay),
            mock.patch.object(manager.cv2, "waitKey", side_effect=lambda _: (time.sleep(0.005) or -1)),
            mock.patch.dict(os.environ, {"FIXTURE_READY_DELAY": "0.15"}),
            mock.patch.object(sys, "argv", ["manager.py", "--report-dir", directory, "--duration-seconds", "0.03"]),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(manager.main(), 0)
            records = [json.loads(line) for line in (Path(directory) / "runtime.jsonl").read_text(encoding="utf-8").splitlines()]
            end = next(record for record in records if record["event"] == "run_end")
            self.assertEqual(end["reason"], "duration_reached")
            self.assertGreaterEqual(end["trial_elapsed_s"], 0.03)
            self.assertFalse(any(record["event"] == "scene_exit" for record in records))
            self.assertTrue(any(record["event"] == "scene_control" and record["detail"]["event"] == "FIRST_FRAME"
                                for record in records))

    @unittest.skipUnless(os.name == "nt", "Windows process counters")
    def test_counter_sampling_returns_real_values_and_closes_query_handles(self):
        process_sample(os.getpid())
        gc.collect()
        baseline = process_sample(os.getpid())
        for _ in range(100):
            sample = process_sample(os.getpid())
            self.assertGreater(sample["private_bytes"], 0)
            self.assertGreaterEqual(sample["cpu_seconds"], 0)
        gc.collect()
        self.assertLessEqual(process_sample(os.getpid())["handles"], baseline["handles"] + 1)

    def test_child_output_is_drained_and_rotated_without_accumulating_reader_threads(self):
        with tempfile.TemporaryDirectory() as directory:
            diagnostics = RuntimeDiagnostics(directory, {}, max_bytes=1024, backups=2)
            proc = subprocess.Popen([sys.executable, "-m", "this"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            diagnostics.capture_stdout(proc)
            proc.wait(timeout=3)
            self.assertTrue(diagnostics.close())
            self.assertEqual(diagnostics.readers, {})
            paths = list(Path(directory).glob("*.jsonl*"))
            self.assertLessEqual(len(paths), 6)
            records = [json.loads(line) for path in paths for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(record["event"] == "scene_output_end" for record in records))
            self.assertTrue(any("The Zen of Python" in record.get("text", "") for record in records))

    def test_real_manager_trial_completes_switches_and_closes_log_readers(self):
        from unittest import mock
        import time
        sys.modules.setdefault("cv2", mock.MagicMock())
        sys.modules.setdefault("numpy", mock.MagicMock())
        import manager
        fixture = Path(__file__).parent / "fixtures" / "handshake_scene_acer.py"
        relay = mock.Mock(shm_name="camera-free-test", frame_id=42, read_failures_total=0,
                          reopen_attempts=0, last_error=None, last_success_at=time.monotonic(), max_frame_gap=0)
        relay.export_env.return_value = {}
        relay.thread.is_alive.return_value = True
        config = dict(manager.DEFAULT_CONFIG, CLAP_MONITOR_ENABLED=False, PRELOAD_COUNT=0, TRANSITION_ENABLED=False)
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(manager, "CONFIG", config),
            mock.patch.object(manager, "resolve_production_scenes", return_value=[str(fixture)]),
            mock.patch.object(manager, "SharedCameraRelay", return_value=relay),
            mock.patch.object(manager.cv2, "waitKey", side_effect=lambda _: (time.sleep(0.005) or -1)),
            mock.patch.object(sys, "argv", ["manager.py", "--report-dir", directory,
                                           "--switch-interval-seconds", "0.005", "--switch-count", "3"]),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(manager.main(), 0)
            records = [json.loads(line) for line in (Path(directory) / "runtime.jsonl").read_text(encoding="utf-8").splitlines()]
            end = next(record for record in records if record["event"] == "run_end")
            self.assertEqual(end["reason"], "switch_count_reached")
            self.assertEqual(end["completed_switches"], 3)
            self.assertTrue(end["human_check_required"])
            first_frames = [record for record in records if record["event"] == "scene_control"
                            and record["detail"]["event"] == "FIRST_FRAME"]
            self.assertEqual(len(first_frames), 4)
        relay.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
