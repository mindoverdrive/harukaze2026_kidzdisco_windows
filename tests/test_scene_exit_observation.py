"""Observe actual scene exit branches without cameras, windows, or control sockets."""
import ast
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import manager
import scene_control
import scene_profile_runner
from test_scene_resources import namespace, run_exit_callbacks

ROOT = Path(__file__).resolve().parents[1]


def lifecycle_records(output):
    prefix = "[SceneLifecycle] "
    return [json.loads(line[len(prefix):]) for line in output.splitlines() if line.startswith(prefix)]


class SceneExitObservationTests(unittest.TestCase):
    def run_scene_body(self, filename, trigger, *, broken_output=False):
        ns = namespace()
        pg = ns["pygame"]
        cap = ns["display_utils"].open_camera.return_value
        cap.read.return_value = (trigger != "camera_unavailable", object())
        ns["display_utils"].prepare_camera_frame.return_value = (object(), object(), object())
        ns["mp"].solutions.hands.Hands.return_value.process.return_value = SimpleNamespace(multi_hand_landmarks=None)
        ns["notify_first_frame"] = mock.Mock()
        ns["notify_exit_request"] = getattr(scene_control, "notify_exit_request", mock.Mock())
        pg.time.get_ticks.return_value = 0
        pg.mouse.get_pos.return_value = (0, 0)
        event = SimpleNamespace(type=pg.QUIT) if trigger == "QUIT" else SimpleNamespace(
            type=pg.KEYDOWN, key=pg.K_ESCAPE if trigger == "ESC" else pg.K_q)
        pg.event.get.return_value = [event]
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        program = compile(tree, filename, "exec")

        def run_body(*_args, **_kwargs):
            exec(program, ns)
            return ns

        output = io.StringIO()
        control = mock.Mock()
        try:
            with (
                mock.patch.object(sys, "argv", [filename, "--control-port", "1", "--launch-id", "observed-launch"]),
                mock.patch.object(scene_control, "SceneChildControl", return_value=control),
                mock.patch.object(scene_profile_runner.runpy, "run_path", side_effect=run_body),
                redirect_stdout(output),
            ):
                if broken_output:
                    with mock.patch("builtins.print", side_effect=BrokenPipeError("closed output")):
                        scene_profile_runner.run_scene(filename, profile="stage")
                else:
                    scene_profile_runner.run_scene(filename, profile="stage")
        finally:
            run_exit_callbacks(ns)
        control.close.assert_called_once()
        cap.release.assert_called_once()
        pg.quit.assert_called_once()
        return lifecycle_records(output.getvalue())

    def test_actual_pygame_exit_branches_report_distinct_correlated_reasons(self):
        for filename in ("finger_colorfull_dots_2.py", "finger_mandala_2.py"):
            for trigger, reason in (("QUIT", "pygame_quit"), ("ESC", "key_escape"), ("q", "key_q")):
                with self.subTest(scene=filename, trigger=trigger):
                    records = self.run_scene_body(filename, trigger)
                    requests = [record for record in records if record["event"] == "exit_request"]
                    self.assertEqual(len(requests), 1, f"MISSING_EXIT_REASON: {filename} {trigger}")
                    self.assertEqual(requests[0]["reason"], reason)
                    end = next(record for record in records if record["event"] == "runner_end")
                    self.assertEqual(end["outcome"], "return")
                    self.assertEqual(end["exit_request_reason"], reason)
                    for record in records:
                        self.assertEqual(record["scene"], filename)
                        self.assertEqual(record["launch_id"], "observed-launch")
                        self.assertEqual(record["pid"], os.getpid())

    def test_mandala_camera_failure_remains_normal_return_with_observed_reason(self):
        records = self.run_scene_body("finger_mandala_2.py", "camera_unavailable")
        end = next(record for record in records if record["event"] == "runner_end")
        self.assertEqual(end["outcome"], "return")
        self.assertEqual(end["exit_request_reason"], "camera_read_failed")

    def test_runner_preserves_return_system_exit_exception_and_interrupt(self):
        cases = [(None, "return"), (SystemExit(0), "system_exit"), (SystemExit(7), "system_exit"),
                 (SystemExit("message"), "system_exit"), (RuntimeError("injected"), "exception"),
                 (KeyboardInterrupt(), "keyboard_interrupt")]
        for failure, outcome in cases:
            with self.subTest(outcome=outcome, failure=str(failure)):
                output = io.StringIO()
                control = mock.Mock()
                control.send.side_effect = BrokenPipeError("startup control already closed")
                with (
                    mock.patch.object(sys, "argv", ["fixture_acer.py", "--control-port", "1", "--launch-id", "after-promotion"]),
                    mock.patch.object(scene_control, "SceneChildControl", return_value=control),
                    mock.patch.object(scene_profile_runner.runpy, "run_path", side_effect=failure, return_value={}),
                    redirect_stdout(output),
                ):
                    if failure is None:
                        scene_profile_runner.run_scene("finger_colorfull_dots_2.py")
                    else:
                        with self.assertRaises(type(failure)) as caught:
                            scene_profile_runner.run_scene("finger_colorfull_dots_2.py")
                        self.assertIs(caught.exception, failure)
                records = lifecycle_records(output.getvalue())
                ends = [record for record in records if record["event"] == "runner_end"]
                self.assertEqual(len(ends), 1)
                self.assertEqual(ends[0]["outcome"], outcome)
                self.assertEqual(ends[0]["launch_id"], "after-promotion")
                self.assertIsNone(ends[0]["exit_request_reason"])
                if isinstance(failure, SystemExit):
                    self.assertEqual(ends[0]["system_exit_code"], failure.code)
                control.close.assert_called_once()

    def test_lifecycle_output_failure_does_not_prevent_scene_return_or_cleanup(self):
        self.assertEqual(self.run_scene_body("finger_colorfull_dots_2.py", "QUIT", broken_output=True), [])

    def test_lifecycle_output_failure_does_not_mask_the_original_exception(self):
        failure = RuntimeError("original scene failure")
        control = mock.Mock()
        control.send.side_effect = BrokenPipeError("startup connection closed")
        with (
            mock.patch.object(sys, "argv", ["fixture_acer.py", "--control-port", "1", "--launch-id", "failed-scene"]),
            mock.patch.object(scene_control, "SceneChildControl", return_value=control),
            mock.patch.object(scene_profile_runner.runpy, "run_path", side_effect=failure),
            mock.patch("builtins.print", side_effect=BrokenPipeError("output closed")),
        ):
            with self.assertRaises(RuntimeError) as caught:
                scene_profile_runner.run_scene("finger_colorfull_dots_2.py")
        self.assertIs(caught.exception, failure)
        control.close.assert_called_once()

    def test_manager_records_stop_reason_and_identity_before_sending_signal(self):
        diagnostics = mock.Mock()
        events = []
        diagnostics.record.side_effect = lambda *_args, **_kwargs: events.append("record")
        sm = manager.SceneManager(scenes=["fixture_acer.py"], diagnostics=diagnostics)
        proc = mock.Mock(pid=12345)
        proc._scene_launch_id, proc._scene_pid = "observed-launch", 23456
        proc.poll.return_value = None
        proc.wait.return_value = 0
        sm.running_process, sm.current_scene_name = proc, "fixture_acer.py"
        sm.shutdown_reason = "operator_quit"

        proc.send_signal.side_effect = lambda _signal: events.append("signal")
        with mock.patch("builtins.print"):
            self.assertTrue(sm.kill_current())
        self.assertEqual(events, ["record", "signal"])
        diagnostics.record.assert_called_once()
        self.assertEqual(diagnostics.record.call_args.args, ("scene_stop_request",))
        fields = diagnostics.record.call_args.kwargs
        self.assertEqual(fields["reason"], "operator_quit")
        self.assertEqual(fields["launcher_pid"], 12345)
        self.assertEqual(fields["scene_pid"], 23456)
        self.assertEqual(fields["launch_id"], "observed-launch")

    def test_manager_stop_still_runs_when_observation_outputs_fail(self):
        diagnostics = mock.Mock()
        diagnostics.record.side_effect = OSError("diagnostic disk unavailable")
        sm = manager.SceneManager(scenes=["fixture_acer.py"], diagnostics=diagnostics)
        proc = mock.Mock(pid=12345)
        proc.poll.return_value = None
        proc.wait.return_value = 0
        with mock.patch("builtins.print", side_effect=BrokenPipeError("closed output")):
            self.assertTrue(sm._kill_process(proc, "fixture_acer.py"))
        proc.send_signal.assert_called_once()

    def test_stop_timeout_still_escalates_when_stdout_is_closed(self):
        sm = manager.SceneManager(scenes=["fixture_acer.py"])
        proc = mock.Mock(pid=12345)
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired("fixture", 0.01), 0]
        with (
            mock.patch("builtins.print", side_effect=BrokenPipeError("closed output")),
            mock.patch.object(manager.subprocess, "run") as force_stop,
        ):
            self.assertTrue(sm._kill_process(proc, "fixture_acer.py"))
        if os.name == "nt":
            force_stop.assert_called_once()
        else:
            proc.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
