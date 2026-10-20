"""Mock-only regressions for incomplete Windows scene containment."""
from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import manager
import windows_process
SOURCE = Path(manager.__file__).resolve().parent


class ContainmentRegressionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch("builtins.print"))
        self.kernel = mock.MagicMock()
        self.kernel.CreateJobObjectW.return_value = 10
        self.kernel.SetInformationJobObject.return_value = 1
        self.kernel.AssignProcessToJobObject.return_value = 1
        self.kernel.CloseHandle.return_value = 1
        self.stack.enter_context(mock.patch.object(windows_process, "_kernel", return_value=self.kernel))
        self.parents = self.stack.enter_context(mock.patch.object(
            windows_process, "_process_parents", return_value={}))
        self.stack.enter_context(mock.patch.object(
            windows_process.WindowsSceneJob, "_query_pids", return_value=[]))
        self.proc = mock.Mock(pid=123, _handle=456)
        self.proc.poll.return_value = 0
        self.spawn = self.stack.enter_context(mock.patch.object(
            manager.subprocess, "Popen", return_value=self.proc))
        self.taskkill = self.stack.enter_context(mock.patch.object(manager.subprocess, "run"))
        self.sm = manager.SceneManager(scenes=["fixture_acer.py"])
        self.stack.enter_context(mock.patch.object(self.sm, "_scene_env", return_value={}))
        self.addCleanup(self.release_known_job)

    def release_known_job(self):
        job = windows_process.get_scene_job(self.proc)
        if job is not None:
            job.close()

    def test_adoption_failure_retains_manager_owner_and_known_job(self):
        self.parents.side_effect = OSError("descendant enumeration/adoption failed")
        with self.assertRaises(OSError):
            self.sm._spawn_process(["fixture"], str(SOURCE))
        self.assertIs(self.sm.uncontained_process, self.proc)
        self.assertIsNotNone(self.sm.fatal_error)
        job = windows_process.get_scene_job(self.proc)
        self.assertIsNotNone(job)
        self.assertFalse(job.containment_complete)
        self.assertEqual(job._job_handles(), [10])
        self.kernel.CloseHandle.assert_not_called()
        with self.assertRaisesRegex(OSError, "uncontained"):
            self.sm._spawn_process(["second"], str(SOURCE))
        self.assertEqual(self.spawn.call_count, 1)

    def test_assignment_failure_with_dead_launcher_does_not_claim_tree_stopped(self):
        self.kernel.AssignProcessToJobObject.return_value = 0
        with mock.patch("ctypes.get_last_error", return_value=5):
            with self.assertRaises(OSError):
                self.sm._spawn_process(["fixture"], str(SOURCE))
        self.assertIs(self.sm.uncontained_process, self.proc)
        self.assertIsNotNone(self.sm.fatal_error)
        self.assertFalse(self.sm._kill_process(self.proc, "retry incomplete launch"))
        # An exited launcher's numeric PID must not be used as an unverified kill target.
        self.taskkill.assert_not_called()

    def test_known_owned_job_is_terminated_but_incomplete_containment_is_retained(self):
        self.proc.poll.return_value = None
        self.proc._scene_containment_incomplete = True
        job = mock.Mock(containment_complete=False)
        job.wait.return_value = True
        self.proc._scene_job = job
        self.assertFalse(self.sm._kill_process(self.proc, "incomplete launch"))
        job.terminate.assert_called_once()
        job.close.assert_not_called()

    def test_live_uncontained_root_cleanup_cannot_prove_descendant_absence(self):
        self.proc.poll.return_value = None
        self.proc._scene_containment_incomplete = True
        self.proc.wait.side_effect = [subprocess.TimeoutExpired("fixture", 0.1), None]
        self.assertFalse(self.sm._kill_process(self.proc, "uncontained launch"))
        self.taskkill.assert_not_called()
        self.proc.terminate.assert_called_once()
        self.proc.kill.assert_not_called()

    def test_successfully_contained_job_still_cleans_up_normally(self):
        proc = self.sm._spawn_process(["fixture"], str(SOURCE))
        self.assertIs(proc, self.proc)
        self.assertFalse(vars(proc).get("_scene_containment_incomplete", False))
        self.assertTrue(self.sm._kill_process(proc, "normal cleanup"))
        self.kernel.CloseHandle.assert_called_once_with(10)
        self.assertIsNone(self.sm.uncontained_process)

    def test_diagnostics_failure_after_containment_can_clear_confirmed_cleanup(self):
        self.sm.diagnostics = mock.Mock()
        self.sm.diagnostics.capture_stdout.side_effect = OSError("log unavailable")
        with self.assertRaises(OSError):
            self.sm._spawn_process(["fixture"], str(SOURCE))
        self.assertIsNone(self.sm.uncontained_process)
        self.assertIsNone(self.sm.fatal_error)


    def test_graceful_exit_of_incomplete_launcher_never_uses_numeric_pid(self):
        self.proc._scene_containment_incomplete = True
        self.proc.poll.return_value = None
        def exit_during_wait(**unused):
            self.proc.poll.return_value = 0
            return 0
        self.proc.wait.side_effect = exit_during_wait
        self.assertFalse(self.sm._kill_process(self.proc, "exit during graceful wait"))
        self.taskkill.assert_not_called()
        self.proc.terminate.assert_not_called()
        self.proc.kill.assert_not_called()

    def test_exit_during_graceful_signal_never_uses_numeric_pid(self):
        self.proc._scene_containment_incomplete = True
        self.proc.poll.return_value = None
        def exit_during_signal(*unused):
            self.proc.poll.return_value = 0
            raise ProcessLookupError("launcher exited")
        self.proc.send_signal.side_effect = exit_during_signal
        self.assertFalse(self.sm._kill_process(self.proc, "exit during signal"))
        self.taskkill.assert_not_called()
        self.proc.terminate.assert_not_called()
        self.proc.kill.assert_not_called()

    def test_stubborn_incomplete_root_uses_only_owned_handle_terminate_and_kill(self):
        self.proc._scene_containment_incomplete = True
        self.proc.poll.return_value = None
        self.proc.wait.side_effect = [
            subprocess.TimeoutExpired("graceful", 0.1),
            subprocess.TimeoutExpired("terminate", 0.1), None]
        self.assertFalse(self.sm._kill_process(self.proc, "stubborn owned root"))
        self.taskkill.assert_not_called()
        self.proc.terminate.assert_called_once()
        self.proc.kill.assert_called_once()
        self.assertEqual(self.proc.wait.call_count, 3)

    def test_owned_handle_terminate_error_still_attempts_owned_kill(self):
        self.proc._scene_containment_incomplete = True
        self.proc.poll.return_value = None
        self.proc.wait.side_effect = [subprocess.TimeoutExpired("graceful", 0.1), None]
        self.proc.terminate.side_effect = OSError("terminate failed")
        self.assertFalse(self.sm._kill_process(self.proc, "owned root terminate error"))
        self.taskkill.assert_not_called()
        self.proc.terminate.assert_called_once()
        self.proc.kill.assert_called_once()

    def test_legacy_no_job_launch_keeps_existing_tree_fallback(self):
        self.proc.poll.return_value = None
        self.proc.wait.side_effect = [subprocess.TimeoutExpired("graceful", 0.1), None]
        self.assertTrue(self.sm._kill_process(self.proc, "legacy no-job launcher"))
        self.taskkill.assert_called_once()

    def test_adoption_error_still_attempts_remaining_verified_descendants(self):
        self.parents.return_value = {200: 123, 300: 123}
        attempted = []
        failure = OSError("first descendant adoption failed")
        def adopt(job, pid):
            attempted.append(pid)
            if pid == 200:
                raise failure
            job._adopted_jobs.append(20)
            return True
        with mock.patch.object(windows_process.WindowsSceneJob, "adopt_scene_pid", new=adopt):
            with self.assertRaises(OSError) as raised:
                self.sm._spawn_process(["fixture"], str(SOURCE))
        self.assertIs(raised.exception, failure)
        self.assertEqual(attempted, [200, 300])
        self.assertIs(self.sm.uncontained_process, self.proc)
        job = windows_process.get_scene_job(self.proc)
        self.assertFalse(job.containment_complete)
        self.assertEqual(job._job_handles(), [10, 20])
        self.kernel.CloseHandle.assert_not_called()

    def test_exited_descendant_does_not_prevent_later_adoption_or_complete_containment(self):
        self.parents.return_value = {200: 123, 300: 123}
        attempted = []
        exited = OSError("descendant already exited")
        exited.winerror = 87
        def adopt(job, pid):
            attempted.append(pid)
            if pid == 200:
                raise exited
            return True
        with mock.patch.object(windows_process.WindowsSceneJob, "adopt_scene_pid", new=adopt):
            self.sm._spawn_process(["fixture"], str(SOURCE))
        self.assertEqual(attempted, [200, 300])
        self.assertTrue(windows_process.get_scene_job(self.proc).containment_complete)
        self.assertFalse(self.proc._scene_containment_incomplete)


if __name__ == "__main__":
    unittest.main()
