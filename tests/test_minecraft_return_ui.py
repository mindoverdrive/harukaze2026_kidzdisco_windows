"""Current MATAHARI staff return with mock ownership, no camera/window."""
import unittest
from unittest.mock import Mock
import manager
import test_staff_lifecycle


class ReturnUITests(unittest.TestCase):
    setUp = test_staff_lifecycle.StaffLifecycleTests.setUp
    enter = test_staff_lifecycle.StaffLifecycleTests.enter
    promote = test_staff_lifecycle.StaffLifecycleTests.promote

    def test_return_while_entering_is_one_queued_request_and_keeps_old_scene(self):
        self.sm.request_staff('minecraft')
        candidate = self.sm.preloaded_process
        launches = self.sm._launch_scene_process.call_count
        for _ in range(20):
            self.assertTrue(self.sm.return_to_rotation())
        self.assertEqual(self.sm.staff_mode, 'entering')
        self.assertIs(self.sm.preloaded_process, candidate)
        self.assertIs(self.sm.running_process, self.fixture.old)
        self.assertEqual(self.sm._launch_scene_process.call_count, launches)
        self.assertTrue(self.sm.operator_snapshot()['staff']['return_requested'])

    def test_queued_return_uses_same_first_frame_gate_and_original_scene_then_unlocks(self):
        self.sm.request_staff('minecraft')
        self.sm.return_to_rotation()
        self.overlay.covered = True
        self.control.poll.return_value = 'FIRST_FRAME'
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'active')
        staff = self.sm.running_process
        self.overlay.busy = self.overlay.covered = False
        self.control.poll.return_value = 'READY'
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'returning')
        self.assertEqual(self.sm.preloaded_scene_path, 'a_acer.py')
        self.assertIs(self.sm.running_process, staff)
        self.assertFalse(self.sm.request_scene('next'))
        self.promote()
        self.assertEqual(self.sm.staff_mode, 'normal')
        self.assertEqual(self.sm.scene_index, 1)
        self.assertEqual(self.sm.running_scene_path, 'a_acer.py')
        self.assertFalse(self.sm.operator_snapshot()['staff']['return_requested'])
        self.assertGreater(self.sm.rotation_generation, 0)

    def test_active_reveal_accepts_return_without_overlapping_a_transition(self):
        self.enter()
        self.control.poll.return_value = 'READY'  # The return has its own fresh candidate.
        self.overlay.busy = True
        self.overlay.covered = True  # Remains set until the real REVEALED acknowledgement.
        self.overlay.holding_cover = False
        launches = self.sm._launch_scene_process.call_count
        self.assertTrue(self.sm.return_to_rotation())
        self.assertEqual(self.sm.staff_mode, 'active')
        self.assertEqual(self.sm._launch_scene_process.call_count, launches)
        self.overlay.busy = False
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'returning')

    def test_queued_return_progresses_when_safe_is_holding_a_complete_cover(self):
        self.sm.request_staff('minecraft')
        self.sm.return_to_rotation()
        self.sm.request_safe()
        self.overlay.covered = self.overlay.holding_cover = True
        self.control.poll.side_effect = lambda *_: 'FIRST_FRAME' if self.sm.staff_mode == 'entering' else 'READY'
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'returning')
        self.assertFalse(self.sm.operator_snapshot()['staff']['return_requested'])
        self.assertEqual(self.sm.preloaded_scene_path, 'a_acer.py')

    def test_failed_entry_clears_return_reservation_after_normal_scene_recovers(self):
        self.sm.request_staff('minecraft')
        self.sm.return_to_rotation()
        self.control.poll.side_effect = manager.SceneControlError('FIRST_FRAME timeout')
        self.sm.tick()
        self.assertIs(self.sm.running_process, self.fixture.old)
        self.control.poll.side_effect = None
        self.overlay.busy = False
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'normal')
        self.assertFalse(self.sm.operator_snapshot()['staff']['return_requested'])

    def test_blocked_stop_clears_reservation_so_return_retry_stays_available(self):
        self.sm.request_staff('minecraft')
        self.sm.return_to_rotation()
        self.sm._kill_process.side_effect = None
        self.sm._kill_process.return_value = False
        self.control.poll.side_effect = manager.SceneControlError('timeout')
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'blocked')
        self.assertFalse(self.sm.operator_snapshot()['staff']['return_requested'])
        launches = self.sm._launch_scene_process.call_count
        self.assertFalse(self.sm.return_to_rotation())
        self.assertEqual(self.sm._launch_scene_process.call_count, launches)

    def test_return_clicks_during_return_do_not_launch_more_candidates(self):
        self.enter()
        self.sm.return_to_rotation()
        launches = self.sm._launch_scene_process.call_count
        for _ in range(20):
            self.assertFalse(self.sm.return_to_rotation())
        self.assertEqual(self.sm._launch_scene_process.call_count, launches)

    def test_shared_camera_and_launch_ownership_paths_are_inherited_unchanged(self):
        from staff_scene_manager import StaffSceneManager
        self.assertIs(StaffSceneManager._scene_env, manager.SceneManager._scene_env)
        self.assertIs(StaffSceneManager._launch_scene_process, manager.SceneManager._launch_scene_process)
        self.sm.camera_env = {'HARUKAZE_SHARED_CAMERA_REQUIRED': '1', 'HARUKAZE_CAMERA_SHM': 'same'}
        env = self.sm._scene_env()
        self.sm.request_staff('minecraft')
        self.assertEqual(self.sm._scene_env(), env)


if __name__ == '__main__':
    unittest.main()
