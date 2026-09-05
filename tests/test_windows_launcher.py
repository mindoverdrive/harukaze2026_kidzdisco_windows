import os
import select
import subprocess
from pathlib import Path
import sys
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


if __name__ == "__main__":
    unittest.main()
