"""Actual owned child processes and TCP; synthetic frame, no native drawing."""
import os
from pathlib import Path
import sys
import time
import unittest
from unittest import mock

sys.modules.setdefault('cv2', mock.MagicMock())
sys.modules.setdefault('numpy', mock.MagicMock())
import manager
from staff_scene_manager import StaffSceneManager


class StaffProcessTests(unittest.TestCase):
    def test_real_process_enters_and_returns_without_orphans(self):
        fixture = str(Path(__file__).parent.resolve() / 'fixtures' / 'handshake_scene_acer.py')
        with mock.patch.dict(manager.CONFIG, {'TRANSITION_ENABLED': False, 'PRELOAD_COUNT': 0,
                                              'SCENE_READY_TIMEOUT': 5, 'SCENE_FIRST_FRAME_TIMEOUT': 5}):
            sm = StaffSceneManager(scenes=[fixture])
            sm.staff_scenes = {'minecraft': fixture}
            self.addCleanup(sm.cleanup)

            def wait_for(predicate):
                deadline = time.monotonic()+8
                while time.monotonic() < deadline:
                    sm.tick()
                    if predicate():
                        return
                    if sm.fatal_error:
                        self.fail(sm.fatal_error)
                    time.sleep(.01)
                self.fail(sm.operator_snapshot())

            sm.request_scene('next')
            wait_for(lambda: sm.is_scene_running() and not sm.switch_pending)
            old = sm.running_process
            self.assertTrue(sm.request_staff('minecraft'))
            self.assertIsNone(old.poll(), 'normal scene must survive pending startup')
            wait_for(lambda: sm.staff_mode == 'active')
            self.assertIsNotNone(old.poll())
            staff = sm.running_process
            self.assertTrue(sm.return_to_rotation())
            wait_for(lambda: sm.staff_mode == 'normal')
            self.assertIsNotNone(staff.poll())
            self.assertEqual(sm.running_scene_path, fixture)
            self.assertEqual(sm.scene_index, 1)
            self.assertTrue(sm.cleanup())
            self.assertIsNone(sm.running_process)
            self.assertIsNone(sm.preloaded_process)
