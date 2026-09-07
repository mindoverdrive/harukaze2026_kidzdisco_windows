"""Scene requests share cover/first-frame/cleanup ordering, including failures."""
import unittest
import sys
from unittest import mock

sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import manager
from scene_control import SceneControlError


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.config = mock.patch.dict(manager.CONFIG, {"TRANSITION_ENABLED": True, "PRELOAD_COUNT": 0})
        self.config.start()
        self.addCleanup(self.config.stop)
        self.quiet = mock.patch("builtins.print")
        self.quiet.start()
        self.addCleanup(self.quiet.stop)
        self.events = []
        self.overlay = mock.Mock(covered=False, busy=False, error=None, process=object())
        self.overlay.consume_action.return_value = None
        self.overlay.begin.side_effect = self.begin
        self.overlay.reveal.side_effect = lambda: self.events.append("reveal") or True
        self.factory = mock.patch.object(manager, "TransitionManager", return_value=self.overlay)
        self.factory.start()
        self.addCleanup(self.factory.stop)
        self.sm = manager.SceneManager(scenes=["a_acer.py", "b_acer.py", "c_acer.py"])
        self.old = mock.Mock()
        self.old.poll.return_value = None
        self.sm.running_process = self.old
        self.sm.running_scene_path = "a_acer.py"
        self.sm.current_scene_name = "a_acer.py"
        self.sm.scene_index = 1
        self.control = mock.Mock(child_pid=123, first_frame={"shm_name": "camera"})
        self.control.poll.return_value = "READY"
        self.control.start.side_effect = lambda: self.events.append("start")
        self.sm._kill_process = mock.Mock(side_effect=lambda *args, **kw: self.events.append("stop") or True)
        self.sm._launch_scene_process = mock.Mock(return_value=mock.Mock())
        self.control_factory = mock.patch.object(manager, "SceneLaunchControl", return_value=self.control)
        self.control_factory.start()
        self.addCleanup(self.control_factory.stop)

    def begin(self):
        self.events.append("cover")
        self.overlay.busy = True
        return True

    def test_cover_ack_gates_start_and_first_frame_gates_stop_and_reveal(self):
        self.assertTrue(self.sm.request_scene("next"))
        self.assertEqual(self.events, ["cover"])
        self.overlay.covered = True
        self.sm.tick()
        self.assertEqual(self.events, ["cover", "start"])
        self.control.poll.return_value = "START_ACK"
        self.sm.tick()
        self.assertEqual(self.events, ["cover", "start"])
        self.control.poll.return_value = "FIRST_FRAME"
        self.sm.tick()
        self.assertEqual(self.events, ["cover", "start", "stop", "reveal"])
        self.assertEqual(self.sm.running_scene_path, "b_acer.py")
        self.assertEqual(self.sm.scene_index, 2)
        self.assertEqual(self.sm.completed_switches, 1)

    def test_back_wrap_and_explicit_selection_use_same_path(self):
        self.assertTrue(self.sm.request_scene("back"))
        self.assertEqual(self.sm.preloaded_scene_path, "c_acer.py")
        self.assertEqual(self.events, ["cover"])
        self.assertFalse(self.sm.request_scene("select", "a_acer.py"))
        self.assertEqual(self.sm.preloaded_scene_path, "c_acer.py")
        self.sm.switch_pending = False
        self.overlay.busy = False
        self.assertTrue(self.sm.launch_scene("b_acer.py"))
        self.assertEqual(self.sm.preloaded_scene_path, "b_acer.py")

    def test_rejected_selection_does_not_launch_or_hide_scene(self):
        with self.assertRaises(manager.ConfigurationError):
            self.sm.request_scene("select", "../foreign_acer.py")
        self.assertEqual(self.events, [])
        self.sm._launch_scene_process.assert_not_called()

    def test_no_duplicate_request_until_revealed_ack(self):
        self.sm.request_scene("next")
        self.overlay.covered = True
        self.control.poll.return_value = "FIRST_FRAME"
        self.sm.tick()
        self.assertFalse(self.sm.switch_pending)
        self.assertFalse(self.sm.request_scene("back"))
        self.overlay.busy = False
        self.assertTrue(self.sm.request_scene("back"))

    def test_start_failure_discards_candidate_before_uncovering_previous_scene(self):
        self.sm.request_scene("next")
        candidate = self.sm.preloaded_process
        self.overlay.covered = True
        self.control.poll.side_effect = SceneControlError("FIRST_FRAME timeout")
        self.sm.tick()
        self.assertIs(self.sm.running_process, self.old)
        self.assertEqual(self.events, ["cover", "stop", "reveal"])
        self.sm._kill_process.assert_called_once_with(candidate, "b_acer.py", reason="candidate_discard")
        self.assertIsNone(self.sm.fatal_error)

    def test_failed_candidate_cleanup_keeps_cover_and_handles(self):
        self.sm.request_scene("next")
        self.overlay.covered = True
        self.sm._kill_process.return_value = False
        self.sm._kill_process.side_effect = None
        self.control.poll.side_effect = SceneControlError("camera failed")
        self.sm.tick()
        self.overlay.reveal.assert_not_called()
        self.assertIsNotNone(self.sm.fatal_error)
        self.assertIsNotNone(self.sm.preloaded_process)

    def test_cover_failure_never_starts_or_stops_current_scene(self):
        self.sm.request_scene("next")
        self.overlay.error = "COVERED timeout"
        self.sm.tick()
        self.control.start.assert_not_called()
        self.assertIs(self.sm.running_process, self.old)
        self.overlay.reveal.assert_not_called()
        self.assertIn("COVERED timeout", self.sm.fatal_error)

    def test_cleanup_retains_cover_until_all_owned_scenes_stop(self):
        self.sm.transition = self.overlay
        self.sm.transition_process = self.overlay.process
        for failed in ("_discard_preloaded", "kill_current"):
            with self.subTest(failed=failed), mock.patch.object(self.sm, failed, return_value=False):
                self.assertFalse(self.sm.cleanup())
                self.overlay.close.assert_not_called()
                self.overlay.fail_closed.assert_called_with("Scene cleanup incomplete")
        self.assertTrue(self.sm.cleanup())
        self.overlay.close.assert_called_once()

    def test_cleanup_failed_uncontained_child_also_retains_cover(self):
        self.sm.transition = self.overlay
        self.sm.uncontained_process = mock.Mock()
        self.sm._kill_process.side_effect = lambda process, *a, **k: process is not self.sm.uncontained_process
        self.assertFalse(self.sm.cleanup())
        self.overlay.close.assert_not_called()
        self.assertIsNotNone(self.sm.uncontained_process)

    def test_initial_start_also_waits_for_cover(self):
        self.sm.running_process = None
        self.sm.running_scene_path = None
        self.sm.scene_index = 0
        self.sm.request_scene("next")
        self.control.start.assert_not_called()
        self.overlay.covered = True
        self.control.poll.return_value = "FIRST_FRAME"
        self.sm.tick()
        self.assertEqual(self.sm.completed_switches, 0)
        self.assertEqual(self.sm.running_scene_path, "a_acer.py")
