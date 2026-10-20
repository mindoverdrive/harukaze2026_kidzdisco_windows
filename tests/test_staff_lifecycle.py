"""Camera/GPU-free staff mode fault injection using existing navigation fixtures."""
import unittest
from unittest import mock
import test_scene_navigation
import manager


class StaffLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_scene_navigation.NavigationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        try:
            from staff_scene_manager import StaffSceneManager
        except ImportError:
            self.fail('staff lifecycle is not implemented')
        self.sm = self.fixture.sm
        self.sm.__class__ = StaffSceneManager
        self.sm.init_staff_state({'minecraft': 'minecraft_staff_acer.py'})
        self.overlay = self.fixture.overlay
        self.control = self.fixture.control
        self.sm._launch_scene_process.side_effect = lambda *args: mock.Mock(**{'poll.return_value': None})

    def promote(self):
        self.overlay.covered = True
        self.control.poll.return_value = 'FIRST_FRAME'
        self.sm.tick()
        self.overlay.busy = False
        self.overlay.covered = False
        self.sm.tick()

    def enter(self):
        self.assertTrue(self.sm.request_staff('minecraft'))
        self.promote()
        self.assertEqual(self.sm.staff_mode, 'active')

    def test_start_preserves_old_until_first_frame_and_does_not_advance_playlist(self):
        self.assertTrue(self.sm.request_staff('minecraft'))
        self.assertIs(self.sm.running_process, self.fixture.old)
        self.assertEqual(self.fixture.events, ['cover'])
        self.assertEqual(self.sm.preloaded_scene_path, 'minecraft_staff_acer.py')
        self.promote()
        self.assertEqual(self.sm.scene_index, 1)
        self.assertEqual(self.sm.all_scenes, ['a_acer.py', 'b_acer.py', 'c_acer.py'])

    def test_all_normal_requests_and_repeated_staff_requests_are_blocked(self):
        self.sm.request_staff('minecraft')
        for action in ('next', 'back', 'restart', 'select'):
            self.assertFalse(self.sm.request_scene(action, 'b_acer.py'))
        self.assertFalse(self.sm.request_staff('minecraft'))
        self.assertTrue(self.sm.return_to_rotation())
        self.assertTrue(self.sm.operator_snapshot()["staff"]["return_requested"])
        self.assertTrue(self.sm.staff_locked)

    def test_manual_return_restarts_interrupted_scene_and_resets_timer_generation(self):
        self.enter()
        self.assertTrue(self.sm.return_to_rotation())
        self.assertEqual(self.sm.preloaded_scene_path, 'a_acer.py')
        self.assertFalse(self.sm.request_scene('next'))
        self.promote()
        self.assertEqual(self.sm.staff_mode, 'normal')
        self.assertEqual(self.sm.scene_index, 1)
        self.assertGreater(self.sm.rotation_generation, 0)

    def test_window_close_or_crash_automatically_returns(self):
        self.enter()
        self.sm.running_process.poll.return_value = 7
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'returning')
        self.assertEqual(self.sm.preloaded_scene_path, 'a_acer.py')

    def test_startup_timeout_preserves_normal_scene(self):
        self.sm.request_staff('minecraft')
        self.overlay.covered = True
        self.control.poll.side_effect = manager.SceneControlError('FIRST_FRAME timeout')
        self.sm.tick()
        self.assertIs(self.sm.running_process, self.fixture.old)
        self.assertIsNone(self.sm.fatal_error)
        self.overlay.busy = False
        self.control.poll.side_effect = None
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'normal')

    def test_return_failure_preserves_ui_state_and_can_retry(self):
        self.enter()
        self.sm.return_to_rotation()
        self.control.poll.side_effect = manager.SceneControlError('injected return failure')
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'recovery_failed')
        self.assertIsNone(self.sm.fatal_error)
        self.assertIn('injected', self.sm.operator_snapshot()['staff']['error'])
        self.overlay.covered = True
        self.overlay.holding_cover = True
        self.control.poll.side_effect = None
        self.control.poll.return_value = 'READY'
        self.assertTrue(self.sm.return_to_rotation())
        self.promote()
        self.assertEqual(self.sm.staff_mode, 'normal')

    def test_stop_failure_retains_handle_and_never_spawns_over_it(self):
        self.enter()
        self.sm.return_to_rotation()
        candidate = self.sm.preloaded_process
        self.sm._kill_process.side_effect = None
        self.sm._kill_process.return_value = False
        self.control.poll.side_effect = manager.SceneControlError('timeout')
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'blocked')
        self.assertIs(self.sm.preloaded_process, candidate)
        count = self.sm._launch_scene_process.call_count
        self.assertFalse(self.sm.return_to_rotation())
        self.assertEqual(self.sm._launch_scene_process.call_count, count)

    def test_unknown_staff_identifier_is_rejected(self):
        with self.assertRaises(manager.ConfigurationError):
            self.sm.request_staff('../minecraft.py')
        self.sm._launch_scene_process.assert_not_called()

    def test_delayed_click_from_old_mode_revision_is_discarded(self):
        old = self.sm.mode_revision
        self.sm.request_staff('minecraft')
        for action in ('staff_start', 'staff_return', 'next', 'back', 'select'):
            self.assertIsNone(manager.revisioned_operator_action({'action': action, 'revision': old}, self.sm))
        self.assertEqual(manager.revisioned_operator_action({'action': 'next', 'revision': self.sm.mode_revision}, self.sm), 'next')
        self.assertIsNone(manager.revisioned_operator_action({'action': 'next', 'revision': 0}, None))

    def test_return_failure_without_any_live_scene_is_retryable(self):
        self.enter()
        self.sm.running_process.poll.return_value = 1
        self.sm.tick()
        self.control.poll.side_effect = manager.SceneControlError('READY timeout')
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'recovery_failed')
        self.assertIsNone(self.sm.fatal_error)

    def test_previous_scene_stop_failure_blocks_further_launches(self):
        self.sm.request_staff('minecraft')
        self.sm._kill_process.side_effect = lambda proc, *a, **kw: proc is not self.fixture.old
        self.promote()
        self.assertEqual(self.sm.staff_mode, 'blocked')
        launches = self.sm._launch_scene_process.call_count
        self.assertFalse(self.sm.return_to_rotation())
        self.assertEqual(self.sm._launch_scene_process.call_count, launches)

    def test_shared_camera_mismatch_never_promotes_staff(self):
        self.sm.camera_env = {'HARUKAZE_CAMERA_SHM': 'expected'}
        self.sm.request_staff('minecraft')
        self.promote()
        self.assertIs(self.sm.running_process, self.fixture.old)
        self.assertIn('different shared camera', self.sm.staff_error)

    def test_preload_is_discarded_before_staff_launch(self):
        old_preload = mock.Mock()
        self.sm.preloaded_process = old_preload
        self.sm.preloaded_scene_path = 'a_acer.py'
        self.sm.request_staff('minecraft')
        self.assertEqual(self.sm.preloaded_scene_path, 'minecraft_staff_acer.py')
        self.assertIsNot(self.sm.preloaded_process, old_preload)

    def test_no_preload_runs_during_active_staff(self):
        self.sm.preload_enabled = True
        self.enter()
        self.assertIsNone(self.sm.preloaded_process)

    def test_safe_cover_does_not_enable_normal_navigation(self):
        self.enter()
        self.sm.request_safe()
        self.overlay.holding_cover = True
        self.overlay.covered = True
        self.assertFalse(self.sm.request_scene('next'))
        self.assertTrue(self.sm.return_to_rotation())

    def test_overlay_failure_retains_ui_and_retry_stops_overlay_first(self):
        self.enter()
        self.overlay.error = 'overlay died'
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'blocked')
        self.overlay.close.return_value = False
        count = self.sm._launch_scene_process.call_count
        self.assertFalse(self.sm.return_to_rotation())
        self.assertEqual(self.sm._launch_scene_process.call_count, count)

    def test_retry_after_candidate_stop_failure_keeps_healthy_normal_predecessor(self):
        self.sm.request_staff('minecraft')
        self.control.poll.side_effect = manager.SceneControlError('timeout')
        self.sm._kill_process.side_effect = None
        self.sm._kill_process.return_value = False
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'blocked')
        self.sm._kill_process.return_value = True
        self.control.poll.side_effect = None
        self.control.poll.return_value = 'READY'
        self.overlay.covered = self.overlay.holding_cover = True
        self.assertTrue(self.sm.return_to_rotation())
        self.assertIs(self.sm.running_process, self.fixture.old)
        self.assertIsNone(self.fixture.old.poll())

    def test_exit_under_safe_cover_still_returns_to_interrupted_scene(self):
        self.enter()
        self.sm.request_safe()
        self.overlay.covered = self.overlay.holding_cover = True
        self.sm.running_process.poll.return_value = 0
        self.control.poll.return_value = 'READY'
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, 'returning')
        self.assertEqual(self.sm.preloaded_scene_path, 'a_acer.py')

    def test_minecraft_is_only_independent_entrypoint_without_changing_rotation(self):
        from staff_scene_manager import StaffSceneManager
        sm = StaffSceneManager(scenes=self.sm.all_scenes)
        self.assertEqual(list(sm.staff_scenes), ['minecraft'])
        self.assertTrue(sm.staff_scenes['minecraft'].endswith('minecraft_staff_acer.py'))
        self.assertEqual(sm.all_scenes, self.sm.all_scenes)
        labels = {item['id']: item['label'] for item in sm.operator_snapshot()['staff']['scenes']}
        self.assertEqual(labels, {'minecraft': 'マイクラ風'})

    def test_removed_independent_hand_draw_is_rejected_without_launching(self):
        with self.assertRaises(manager.ConfigurationError):
            self.sm.request_staff('hand_draw')
        self.sm._launch_scene_process.assert_not_called()
        self.assertEqual(self.sm.staff_mode, 'normal')

    def test_minecraft_keeps_existing_launch_environment_and_drawing_stays_normal(self):
        import os
        from staff_scene_manager import StaffSceneManager
        sm = StaffSceneManager(scenes=self.sm.all_scenes)
        config = manager.load_config(os.path.join(manager.BASE_DIR, 'configs', 'rebirth_operator_acer_xiaomi.json'))
        normal_path = next(path for path in manager.resolve_production_scenes(config)
                           if os.path.basename(path) == 'hand_drawing_acer.py')
        self.assertTrue(normal_path.endswith('hand_drawing_acer.py'))
        self.assertNotIn('hand_draw', sm.staff_scenes)
        sm.camera_env = {'HARUKAZE_CAMERA_SHM': 'same-camera', 'HARUKAZE_SHARED_CAMERA_REQUIRED': '1'}
        normal_env = sm._scene_env()
        sm._set_mode('active')
        sm.staff_scene_id = 'minecraft'
        self.assertEqual(sm._scene_env(), normal_env)
        self.assertIs(StaffSceneManager._launch_scene_process, manager.SceneManager._launch_scene_process)
        self.assertIs(StaffSceneManager._scene_env, manager.SceneManager._scene_env)


if __name__ == '__main__':
    unittest.main()
