"""Exercise the actual scene loop with deterministic camera and UI events."""
import ast
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock


class SpiderCameraRecoveryTests(unittest.TestCase):
    def run_scene(self, reads, times, events):
        source = Path(__file__).resolve().parents[1] / 'spider_cursor_2.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        pygame = MagicMock()
        pygame.QUIT, pygame.KEYDOWN, pygame.K_ESCAPE = 1, 2, 3
        pygame.event.get.side_effect = events
        screen = MagicMock()
        screen.get_size.return_value = (1920, 1080)
        cap = Mock()
        cap.read.side_effect = reads
        hands = Mock()
        hands.process.return_value = SimpleNamespace(multi_hand_landmarks=None)
        display = Mock()
        display.setup_pygame_fullscreen.return_value = (screen, None)
        display.open_camera.return_value = cap
        display.prepare_camera_frame.return_value = (Mock(), Mock(), None)
        first, reason = Mock(), Mock()
        env = dict(ExitStack=ExitStack, atexit=Mock(), pygame=pygame, display_utils=display,
                   mp=SimpleNamespace(solutions=SimpleNamespace(hands=SimpleNamespace(Hands=Mock(return_value=hands)))),
                   Spider=MagicMock(), Bug=Mock(), random=SimpleNamespace(random=lambda:1),
                   cv2=MagicMock(), time=SimpleNamespace(monotonic=Mock(side_effect=times)),
                   notify_first_frame=first, notify_exit_request=reason)
        exec(compile(ast.Module(body=[main], type_ignores=[]), str(source), 'exec'), env)
        env['main']()
        cap.release.assert_called_once()
        hands.close.assert_called_once()
        pygame.quit.assert_called_once()
        return cap, first, reason

    def test_transient_failure_recovers_and_renders_before_quit(self):
        cap, first, reason = self.run_scene([(False,None),(True,object())], [0],
                                           [[],[],[SimpleNamespace(type=1)]])
        self.assertEqual(cap.read.call_count,2)
        first.assert_called_once()
        reason.assert_called_once_with('pygame_quit')

    def test_persistent_failure_is_bounded_and_releases_resources(self):
        cap, first, reason = self.run_scene([(False,None)]*3,[0,.5,1.01],[[],[],[]])
        first.assert_not_called()
        reason.assert_called_once_with('camera_read_failed_timeout')

    def test_escape_remains_responsive_while_camera_unavailable(self):
        cap, first, reason = self.run_scene([(False,None)],[0],[[],[SimpleNamespace(type=2,key=3)]])
        self.assertEqual(cap.read.call_count,1)
        reason.assert_called_once_with('escape_key')
