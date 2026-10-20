"""All models, processes and transports are mocked; transition state is real."""
import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import sys
sys.modules.setdefault("cv2", mock.MagicMock())
sys.modules.setdefault("numpy", mock.MagicMock())
import manager
import test_scene_navigation
from staff_scene_manager import StaffSceneManager
from transition_manager import TransitionManager


class StaffSafeRegressionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_scene_navigation.NavigationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.sm = self.fixture.sm
        self.sm.__class__ = StaffSceneManager
        self.sm.init_staff_state({"minecraft": "minecraft_staff_acer.py"})
        self.control = self.fixture.control
        self.sm._launch_scene_process.side_effect = lambda *args: mock.Mock(**{"poll.return_value": None})
        self.overlay = TransitionManager(mock.Mock(), mock.Mock(), (0, 0, 1920, 1080))
        self.overlay.process = mock.Mock(**{"poll.return_value": None})
        self.overlay._channel = mock.Mock(eof=False)
        self.overlay._channel.receive.return_value = []
        self.overlay._phase = "idle"
        self.sm.transition = self.overlay

    def ack(self, event):
        self.overlay._receive({
            "token": self.overlay.token, "cycle": self.overlay.cycle, "event": event})

    def enter(self):
        self.assertTrue(self.sm.request_staff("minecraft"))
        self.ack("COVERED")
        self.control.poll.return_value = "FIRST_FRAME"
        self.sm.tick()
        self.ack("REVEALED")
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "active")

    def held(self):
        if self.overlay._phase != "covered":
            self.overlay._phase = "covered"
            self.overlay.covered = self.overlay.busy = True
            self.overlay._deadline = None
        self.sm.safe_requested = True

    def test_recovery_failed_cannot_resume_uncertain_scene(self):
        self.enter()
        self.control.poll.return_value = "READY"
        self.sm.return_to_rotation()
        self.ack("COVERED")
        self.control.poll.side_effect = manager.SceneControlError("return failed")
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "recovery_failed")
        self.assertTrue(self.overlay.holding_cover)
        self.assertFalse(self.sm.resume_safe())
        self.assertTrue(self.overlay.holding_cover)
        self.assertTrue(self.sm.safe_requested)

    def test_blocked_cannot_resume_uncertain_scene(self):
        self.enter()
        self.control.poll.return_value = "READY"
        self.sm.return_to_rotation()
        self.ack("COVERED")
        self.sm._kill_process.side_effect = None
        self.sm._kill_process.return_value = False
        self.control.poll.side_effect = manager.SceneControlError("return failed")
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "blocked")
        self.assertTrue(self.sm.request_safe())
        self.assertFalse(self.sm.resume_safe())
        self.assertTrue(self.overlay.holding_cover)
        self.assertTrue(self.sm.safe_requested)

    def test_healthy_staff_safe_and_resume_stay_available(self):
        self.enter()
        self.assertTrue(self.sm.request_safe())
        self.ack("COVERED")
        self.assertTrue(self.sm.resume_safe())
        self.ack("REVEALED")
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "active")
        self.assertFalse(self.sm.safe_requested)

    def test_safe_during_return_is_resumable_and_finishes_normal(self):
        self.enter()
        self.control.poll.return_value = "READY"
        self.assertTrue(self.sm.return_to_rotation())
        self.assertTrue(self.sm.request_safe())
        self.ack("COVERED")
        self.control.poll.return_value = "FIRST_FRAME"
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "return_reveal")
        self.assertTrue(self.sm.operator_snapshot()["covered"])
        self.assertTrue(self.sm.resume_safe())
        self.ack("REVEALED")
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "normal")

    def test_safe_requested_before_entry_failure_holds_cover_until_resume(self):
        self.assertTrue(self.sm.request_staff("minecraft"))
        self.ack("COVERED")
        self.assertTrue(self.sm.request_safe())
        self.control.poll.side_effect = manager.SceneControlError("entry failed after Safe")
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "entry_failed")
        self.assertTrue(self.sm.safe_requested)
        self.assertTrue(self.overlay.holding_cover)
        self.assertTrue(self.sm.operator_snapshot()["covered"])
        self.assertIs(self.sm.running_process, self.fixture.old)
        self.assertTrue(self.sm.resume_safe())
        self.ack("REVEALED")
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "normal")
        self.assertFalse(self.sm.safe_requested)

    def test_safe_during_entry_failed_is_resumable_and_finishes_normal(self):
        self.assertTrue(self.sm.request_staff("minecraft"))
        self.ack("COVERED")
        self.control.poll.side_effect = manager.SceneControlError("entry failed")
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "entry_failed")
        self.assertEqual(self.overlay._phase, "revealing")
        self.assertTrue(self.sm.request_safe())
        self.ack("REVEALED")
        self.sm.tick()
        self.assertEqual(self.overlay._phase, "covering")
        self.ack("COVERED")
        self.assertTrue(self.sm.operator_snapshot()["covered"])
        self.assertTrue(self.sm.resume_safe())
        self.ack("REVEALED")
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "normal")

    def test_recovery_retry_still_uses_staff_return(self):
        self.enter()
        self.control.poll.return_value = "READY"
        self.sm.return_to_rotation()
        self.ack("COVERED")
        self.control.poll.side_effect = manager.SceneControlError("return failed")
        self.sm.tick()
        self.control.poll.side_effect = None
        self.control.poll.return_value = "READY"
        self.assertTrue(self.sm.return_to_rotation())
        self.control.poll.return_value = "FIRST_FRAME"
        self.sm.tick()
        self.ack("REVEALED")
        self.sm.tick()
        self.assertEqual(self.sm.staff_mode, "normal")


def compile_exit_branch(source):
    tree = ast.parse(source)
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    branch = next(node for node in ast.walk(main) if isinstance(node, ast.If)
                  and node.body and isinstance(node.body[0], ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "exited_launcher"
                          for target in node.body[0].targets))
    return compile(ast.fix_missing_locations(ast.Module(body=[branch], type_ignores=[])),
                   "<actual manager scene-exit branch>", "exec")


class SceneExitGateTests(unittest.TestCase):
    source = None

    def fixture(self, busy, held):
        scene = mock.Mock(pid=12)
        scene.poll.return_value = 0
        sm = SimpleNamespace(
            staff_locked=False, safe_requested=False, switch_pending=False,
            transition_busy=busy, transition=SimpleNamespace(holding_cover=held),
            running_process=scene, current_scene_name="fixture_acer.py",
            is_scene_running=lambda: False)
        def switch():
            if sm.transition_busy and not sm.transition.holding_cover:
                return False
            sm.switch_pending = True
            return True
        sm.switch_scene = mock.Mock(side_effect=switch)
        diagnostics = mock.Mock()
        return sm, diagnostics

    def execute(self, sm, diagnostics, count=1):
        program = compile_exit_branch(self.source or Path(manager.__file__).read_text(encoding="utf-8"))
        with redirect_stdout(io.StringIO()):
            for _ in range(count):
                exec(program, {"manager": sm, "diagnostics": diagnostics, "json": json})

    def test_reveal_busy_does_not_repeat_exit_record_or_rejected_switch(self):
        sm, diagnostics = self.fixture(True, False)
        self.execute(sm, diagnostics, 3)
        self.assertEqual(diagnostics.record.call_count, 0)
        self.assertEqual(sm.switch_scene.call_count, 0)
        sm.transition_busy = False
        self.execute(sm, diagnostics, 3)
        self.assertEqual(diagnostics.record.call_count, 1)
        self.assertEqual(sm.switch_scene.call_count, 1)

    def test_cover_hold_can_start_recovery_without_waiting_for_idle(self):
        sm, diagnostics = self.fixture(True, True)
        self.execute(sm, diagnostics, 3)
        self.assertEqual(diagnostics.record.call_count, 1)
        self.assertEqual(sm.switch_scene.call_count, 1)
