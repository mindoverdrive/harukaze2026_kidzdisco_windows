"""Verify feedback against the grid's real stage-space pinch/control rules."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[1] / "finger_grid_interaction_2.py"


def make_hand(index_x, thumb_x):
    points = [SimpleNamespace(x=.5, y=.6) for _ in range(21)]
    points[8] = SimpleNamespace(x=index_x, y=.4)
    points[4] = SimpleNamespace(x=thumb_x, y=.4)
    return SimpleNamespace(landmark=points)


class GridHandFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.layout = dict(offset_x=80, offset_y=0, scaled_width=481, scaled_height=361)
        self.frame = object()
        self.stage = object()
        self.hands = Mock()
        self.overlay = Mock()
        display = SimpleNamespace(
            prepare_camera_frame=Mock(return_value=(self.frame, self.stage, self.layout)),
            normalized_to_stage=Mock(side_effect=lambda x, y, layout:
                                    (80 + round(x * 480), round(y * 360))))
        self.env = dict(W=640, H=360, display_utils=display,
                        hands=self.hands, cv2=SimpleNamespace(cvtColor=Mock(), COLOR_BGR2RGB=1),
                        mp_hands=SimpleNamespace(HandLandmark=SimpleNamespace(INDEX_FINGER_TIP=8, THUMB_TIP=4)),
                        draw_hand_overlay=self.overlay)
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(SOURCE), "exec"), self.env)

    def test_index_always_active_and_thumb_only_when_actual_stage_pinch_is_true(self):
        observed = [make_hand(.4, .1), make_hand(.7, .68)]
        self.hands.process.return_value = SimpleNamespace(multi_hand_landmarks=observed)
        data, stage = self.env["get_hands_data"](self.frame)
        self.env["draw_hand_feedback"](Mock(), data)
        self.assertIs(stage, self.stage)
        self.assertEqual([item['pinching'] for item in data], [False, True])
        self.assertEqual([item['pos'] for item in data], [(272, 144), (416, 144)])
        self.assertEqual([call.kwargs['focus'] for call in self.overlay.call_args_list], [(8,), (8, 4)])
        self.assertTrue(all(call.kwargs['layout'] is self.layout for call in self.overlay.call_args_list))
        self.assertEqual([call.args[1][0] for call in self.overlay.call_args_list], observed)
        self.hands.process.assert_called_once()

    def test_missing_frame_and_missing_detection_never_reuse_a_previous_hand(self):
        self.hands.process.return_value = SimpleNamespace(multi_hand_landmarks=None)
        for frame in (self.frame, None):
            data, _stage = self.env["get_hands_data"](frame)
            self.env["draw_hand_feedback"](Mock(), data)
            self.assertEqual(data, [])
        self.overlay.assert_not_called()
        self.hands.process.assert_called_once()


if __name__ == "__main__":
    unittest.main()
