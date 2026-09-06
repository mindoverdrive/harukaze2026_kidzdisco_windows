import os
import json
import select
import subprocess
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import manager
from scene_control import SceneLaunchControl
from windows_process import WindowsSceneJob


@unittest.skipUnless(os.name == "nt", "Windows process ownership")
class WindowsLauncherTests(unittest.TestCase):
    def launch(self, late_job=False):
        control = SceneLaunchControl(ready_timeout=3)
        scene_manager = manager.SceneManager(scenes=["fixture_acer.py"])
        fixture = Path(__file__).parent / "fixtures" / "handshake_launcher_acer.py"
        argv = [sys.executable, str(fixture), *control.argv()]
        if late_job:
            proc = subprocess.Popen(argv, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            proc = scene_manager._spawn_process(argv, str(fixture.parent))
        self.addCleanup(scene_manager._kill_process, proc, "owned redirector fixture")
        self.addCleanup(control.close)
        if late_job:
            self.assertTrue(select.select([control.listener], [], [], 3)[0])
            proc._scene_job = WindowsSceneJob(proc)
            self.assertGreaterEqual(len(proc._scene_job.active_pids()), 2)
        deadline = time.monotonic() + 3
        while control.poll(proc) != "FIRST_FRAME" and time.monotonic() < deadline:
            if control.state == "READY":
                control.start()
            time.sleep(0.005)
        self.assertEqual(control.state, "FIRST_FRAME")
        self.assertNotEqual(control.first_frame["pid"], proc.pid)
        return scene_manager, control, proc

    def test_redirector_child_identity_is_accepted_only_for_owned_descendants(self):
        scene_manager, control, proc = self.launch()
        self.assertFalse(proc._scene_job.adopt_scene_pid(os.getpid()))
        self.assertTrue(scene_manager._kill_process(proc, "redirector"))
        self.assertIsNotNone(proc.poll())

    def test_dead_launcher_does_not_hide_a_surviving_scene_process(self):
        scene_manager, control, proc = self.launch()
        job = proc._scene_job
        proc.terminate()  # Kill only our fixture redirector, leaving its child for Manager to reap.
        proc.wait(timeout=3)
        self.assertTrue(job.is_alive())
        self.assertTrue(scene_manager._kill_process(proc, "orphaned owned scene"))
        self.assertFalse(job.is_alive())

    def test_job_handle_close_stops_owned_children(self):
        scene_manager, control, proc = self.launch()
        proc._scene_job.close()
        proc.wait(timeout=3)
        self.assertFalse(proc._scene_job.is_alive())

    def test_child_started_before_job_assignment_is_verified_and_adopted(self):
        scene_manager, control, proc = self.launch(late_job=True)
        self.assertIn(control.child_pid, proc._scene_job.active_pids())
        self.assertTrue(scene_manager._kill_process(proc, "early interpreter"))

    def test_preexisting_private_job_child_is_owned_and_reaped(self):
        from windows_process import _kernel

        with tempfile.TemporaryDirectory() as directory:
            ready = Path(directory) / "ready.json"
            fixture = Path(__file__).parent / "fixtures" / "nested_job_launcher.py"
            proc = subprocess.Popen([sys.executable, str(fixture), str(ready)],
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            scene_manager = manager.SceneManager(scenes=["fixture_acer.py"])
            self.addCleanup(scene_manager._kill_process, proc, "private job fixture")
            deadline = time.monotonic() + 3
            while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "fixture did not assign its private job")
            child_pid = json.loads(ready.read_text(encoding="utf-8"))["child_pid"]
            kernel = _kernel()
            child_handle = kernel.OpenProcess(0x100000, False, child_pid)
            self.assertTrue(child_handle)
            self.addCleanup(kernel.CloseHandle, child_handle)
            proc._scene_job = WindowsSceneJob(proc)
            self.assertIn(child_pid, proc._scene_job.active_pids())
            self.assertFalse(proc._scene_job.adopt_scene_pid(os.getpid()))
            proc._scene_job.close()
            proc.wait(timeout=3)
            self.assertEqual(kernel.WaitForSingleObject(child_handle, 3000), 0,
                             "closing all owned jobs left a child process alive")

    def test_failed_job_close_keeps_only_failed_handle_and_retries(self):
        job = WindowsSceneJob.__new__(WindowsSceneJob)
        job.handle, job._adopted_jobs = 10, [20, 30]
        job.kernel = mock.MagicMock()
        self.addCleanup(job.close)
        job.kernel.CloseHandle.side_effect = lambda handle: handle != 20
        with mock.patch("ctypes.get_last_error", return_value=5):
            with self.assertRaises(PermissionError):
                job.close()
        self.assertIsNone(job.handle)
        self.assertEqual(job._adopted_jobs, [20])
        self.assertEqual(job.kernel.CloseHandle.call_args_list,
                         [mock.call(30), mock.call(20), mock.call(10)])
        job.kernel.CloseHandle.side_effect = None
        job.kernel.CloseHandle.return_value = 1
        job.close()
        self.assertEqual(job._job_handles(), [])
        self.assertFalse(job.adopt_scene_pid(os.getpid()))
        job.kernel.OpenProcess.assert_not_called()

    def test_termination_failure_still_attempts_each_owned_job(self):
        job = WindowsSceneJob.__new__(WindowsSceneJob)
        job.handle, job._adopted_jobs = 10, [20, 30]
        job.kernel = mock.MagicMock()
        job.kernel.CloseHandle.return_value = 1
        self.addCleanup(job.close)
        job.kernel.TerminateJobObject.side_effect = lambda handle, code: handle != 10
        with mock.patch("ctypes.get_last_error", return_value=5):
            with self.assertRaises(PermissionError):
                job.terminate()
        self.assertEqual(job.kernel.TerminateJobObject.call_args_list,
                         [mock.call(10, 1), mock.call(20, 1), mock.call(30, 1)])
        self.assertEqual(job._job_handles(), [10, 20, 30])

    def test_rejected_separate_job_assignment_is_not_reported_as_owned(self):
        from ctypes import wintypes as wt
        import ctypes

        job = WindowsSceneJob.__new__(WindowsSceneJob)
        job.handle, job._adopted_jobs = 10, []
        job.root_pid = 1
        job.kernel = mock.MagicMock()
        self.addCleanup(job.close)
        job.kernel.OpenProcess.return_value = 100
        job.kernel.WaitForSingleObject.return_value = 258
        job.kernel.CreateJobObjectW.return_value = 20
        job.kernel.SetInformationJobObject.return_value = 1
        job.kernel.CloseHandle.return_value = 1
        job.kernel.AssignProcessToJobObject.return_value = 0

        def membership(process, handle, value):
            ctypes.cast(value, ctypes.POINTER(wt.BOOL))[0] = handle is None
            return 1

        job.kernel.IsProcessInJob.side_effect = membership
        with mock.patch("windows_process._is_descendant", return_value=True), \
                mock.patch("ctypes.get_last_error", return_value=5):
            with self.assertRaises(PermissionError):
                job.adopt_scene_pid(123)
        self.assertEqual(job._job_handles(), [10])
        self.assertEqual(job.kernel.AssignProcessToJobObject.call_args_list,
                         [mock.call(10, 100), mock.call(20, 100)])
        job.kernel.CloseHandle.assert_any_call(20)
        job.kernel.CloseHandle.assert_any_call(100)

    def test_constructor_double_failure_keeps_job_on_launched_process(self):
        from types import SimpleNamespace
        import windows_process

        proc = SimpleNamespace(pid=100, _handle=100)
        kernel = mock.MagicMock()
        kernel.CreateJobObjectW.return_value = 10
        kernel.SetInformationJobObject.return_value = 1
        kernel.AssignProcessToJobObject.return_value = 1
        kernel.CloseHandle.side_effect = lambda handle: handle != 20
        retained = []
        failure = RuntimeError("later descendant adoption failed")

        def adopt(job, pid):
            if not retained:
                retained.append(job)
                self.addCleanup(job.close)
                job._adopted_jobs.append(20)
                return True
            raise failure

        try:
            with mock.patch.object(windows_process, "_kernel", return_value=kernel), \
                    mock.patch.object(windows_process, "_process_parents", return_value={200: 100, 300: 100}), \
                    mock.patch.object(WindowsSceneJob, "adopt_scene_pid", new=adopt), \
                    mock.patch("ctypes.get_last_error", return_value=5):
                with self.assertRaises(RuntimeError) as raised:
                    WindowsSceneJob(proc)
            self.assertIs(raised.exception, failure)
            self.assertIs(proc._scene_job, retained[0])
            self.assertEqual(proc._scene_job._job_handles(), [20])
        finally:
            kernel.CloseHandle.side_effect = None
            kernel.CloseHandle.return_value = 1
        proc._scene_job.close()
        self.assertEqual(proc._scene_job._job_handles(), [])


if __name__ == "__main__":
    unittest.main()
