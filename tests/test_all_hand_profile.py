"""Common profile and scene coverage, without native detection or windows."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
import pygame
import hand_input_profile as profile
import hand_focus_overlay as overlay
from test_hand_focus_overlay import synthetic_hand

ROOT = Path(__file__).resolve().parents[1]


class AllHandProfileTests(unittest.TestCase):
    def test_profile_keeps_capacity_and_otedama_thresholds(self):
        for count in range(1, 9):
            solutions = profile.solutions_options(count)
            tasks = profile.tasks_options(count)
            self.assertEqual(solutions['max_num_hands'], count)
            self.assertEqual(tasks['num_hands'], count)
            self.assertEqual(solutions['model_complexity'], 1)
            self.assertFalse(solutions['static_image_mode'])
            self.assertEqual(solutions['min_detection_confidence'], .7)
            self.assertEqual(tasks['min_hand_detection_confidence'], .7)
            self.assertEqual(solutions['min_tracking_confidence'], .5)
            self.assertEqual(tasks['min_tracking_confidence'], .5)
        self.assertEqual(profile.solutions_options()['max_num_hands'], 6)
        for value in (0, 9, True, 2.5, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                profile.solutions_options(value)

    def test_actual_playlist_and_staff_sources_have_detector_and_overlay_routes(self):
        config = json.loads((ROOT/'configs/rebirth_operator_acer_xiaomi.json').read_text())
        expected = {
            'fractal_moving_2.py', 'finger_mandala_3.py', 'colorfull_wave_dots.py',
            'colorfull_tree.py', 'skeleton_glitch.py', 'particle_storm_2.py',
            'colorfull_dots_spheres.py', 'finger_colorfull_dots_2.py', 'spider_cursor_2.py',
            'finger_grid_interaction_2.py', 'saturn_particles_2.py', 'prism_skin.py',
            'polygon_vibes_stage.py', 'kaleidoscope_camera.py', 'polygon_face_stage.py',
            'living_mosaic.py', 'modern_otedama.py', 'earth.py', 'hand_drawing_app.py',
            'hand_shapes_app.py', 'minecraft.py'}
        actual = set()
        for entry in config['PRODUCTION_SCENES'] + ['minecraft_staff_acer.py']:
            tree = ast.parse((ROOT/entry).read_text(encoding='utf-8-sig'))
            target = next(n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call)
                          and isinstance(n.func, ast.Name) and n.func.id == 'run_scene')
            actual.add(target)
            text = (ROOT/target).read_text(encoding='utf-8-sig')
            self.assertIn('hand_', text, target)
            if target not in {'skeleton_glitch.py', 'colorfull_dots_spheres.py',
                              'kaleidoscope_camera.py', 'polygon_face_stage.py',
                              'living_mosaic.py', 'hand_shapes_app.py'}:
                self.assertIn('_options(', text, target)
        self.assertEqual(actual, expected)
        for dependency in ('spheres_camera.py', 'hand_focus_overlay.py'):
            self.assertIn('solutions_options(', (ROOT/dependency).read_text())
        self.assertIn('MAX_HANDS, MAX_INPUT_GAP_SECONDS, run_app,', (ROOT/'hand_shapes_app.py').read_text())
        self.assertNotIn("'hand_draw':", (ROOT/'staff_scene_manager.py').read_text())
        self.assertNotIn('face_morph_acer.py', config['PRODUCTION_SCENES'])

    def test_legacy_hand_capacities_are_not_reduced_or_expanded(self):
        capacities = {'fractal_moving_2.py': 4, 'finger_mandala_3.py': 6,
                      'colorfull_wave_dots.py': 5, 'colorfull_tree.py': 2,
                      'finger_colorfull_dots_2.py': 2, 'spider_cursor_2.py': 2,
                      'finger_grid_interaction_2.py': 5, 'prism_skin.py': 5,
                      'polygon_vibes_stage.py': 5, 'minecraft.py': 3,
                      'spheres_camera.py': 6, 'earth.py': 2,
                      'saturn_particles_2.py': 2, 'particle_storm_2.py': 2}
        for filename, capacity in capacities.items():
            with self.subTest(filename=filename):
                tree = ast.parse((ROOT/filename).read_text(encoding='utf-8-sig'))
                calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Name)
                         and n.func.id in {'solutions_options', 'tasks_options'}]
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0].args[0].value, capacity)
        for filename, capacity in (('hand_drawing_app.py', 8), ('modern_otedama.py', 6)):
            tree = ast.parse((ROOT/filename).read_text(encoding='utf-8-sig'))
            self.assertTrue(any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name)
                            and t.id == 'MAX_HANDS' for t in n.targets)
                            and isinstance(n.value, ast.Constant) and n.value.value == capacity
                            for n in tree.body))

    def test_index_ring_is_distinct_even_when_all_five_tips_are_active(self):
        hand = synthetic_hand()
        for background in ((0, 0, 0), (255, 255, 255)):
            surface = pygame.Surface((1280, 720))
            surface.fill(background)
            overlay.draw_pygame(surface, [hand], focus=(4, 8, 12, 16, 20))
            x, y = overlay.stage_points(hand, surface.get_size())[8]
            self.assertEqual(tuple(surface.get_at((x+13, y)))[:3], overlay.INDEX_COLOR)
            self.assertEqual(tuple(surface.get_at((x+20, y)))[:3], overlay.DARK)
            mx, my = overlay.stage_points(hand, surface.get_size())[12]
            self.assertNotEqual(tuple(surface.get_at((mx+13, my)))[:3], overlay.INDEX_COLOR)
            pixels = pygame.surfarray.array3d(surface)
            self.assertLess(np.count_nonzero(np.any(pixels != background, axis=-1)), 1280*720*.06)

    def test_reorder_cross_occlusion_and_reentry_have_no_display_history(self):
        hands = []
        for dx in (-.25, .25):
            hand = synthetic_hand()
            for p in hand.landmark:
                p.x += dx
            hands.append(hand)
        def render(items):
            surface = pygame.Surface((1280, 720))
            surface.fill((0, 0, 0))
            overlay.draw_pygame(surface, items)
            return pygame.surfarray.array3d(surface)
        np.testing.assert_array_equal(render(hands), render(hands[::-1]))
        self.assertTrue(render([hands[0]]).any())
        self.assertFalse(render([]).any())
        np.testing.assert_array_equal(render(hands), render(hands[::-1]))
        crossed = synthetic_hand()
        np.testing.assert_array_equal(render([crossed, crossed]), render([crossed]))

    def test_all_eight_hands_get_bounded_index_rings_in_both_renderers(self):
        hands = []
        for index in range(8):
            hand = synthetic_hand()
            for p in hand.landmark:
                p.x = p.x*.2 + .05 + (index%4)*.24
                p.y = p.y*.3 + .04 + (index//4)*.48
            hands.append(hand)
        surface = pygame.Surface((1280, 720))
        frame = np.zeros((720, 1280, 3), np.uint8)
        overlay.draw_pygame(surface, hands)
        overlay.draw_cv2(frame, hands)
        for hand in hands:
            x, y = overlay.stage_points(hand, surface.get_size())[8]
            self.assertEqual(tuple(surface.get_at((x+13, y)))[:3], overlay.INDEX_COLOR)
            blue, green, red = map(int, frame[y, x+13])
            self.assertGreater(red, blue+100)
            self.assertGreater(green, blue+100)

    def test_invalid_points_are_not_drawn_and_recovery_is_current_frame_only(self):
        hand = synthetic_hand()
        hand.landmark[8].x = float('nan')
        surface = pygame.Surface((1280, 720))
        overlay.draw_pygame(surface, [hand])
        self.assertFalse(pygame.surfarray.array3d(surface).any())
        overlay.draw_pygame(surface, [synthetic_hand()])
        self.assertTrue(pygame.surfarray.array3d(surface).any())

    def test_minecraft_reuses_same_result_and_final_pass_precedes_first_frame(self):
        tree = ast.parse((ROOT/'minecraft.py').read_text(encoding='utf-8'))
        frame = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                     and n.name == '_animate_frame')
        text = ast.get_source_segment((ROOT/'minecraft.py').read_text(encoding='utf-8'), frame)
        self.assertLess(text.index('hand_overlay.update'), text.index('render(self.hand_overlay.scene'))
        self.assertLess(text.index('render(self.hand_overlay.scene'), text.index('notify_first_frame'))
        self.assertEqual(text.count('gesture_manager.process('), 1)
        self.assertNotIn('VideoCapture', text)
        self.assertNotIn('draw_cv2', text)

    def test_passive_detector_failure_drops_old_result_and_reuses_one_model(self):
        import mediapipe as mp
        hand = synthetic_hand()
        model = mock.Mock()
        model.process.side_effect = [SimpleNamespace(multi_hand_landmarks=[hand]),
                                     RuntimeError('injected'),
                                     SimpleNamespace(multi_hand_landmarks=[])]
        with mock.patch.object(mp.solutions.hands, 'Hands', return_value=model) as make:
            detector = overlay.PassiveHandDetector()
        frame = np.zeros((12, 16, 3), np.uint8)
        with mock.patch.object(overlay.time, 'monotonic', side_effect=[1., 2., 3.]):
            self.assertEqual(detector.detect(frame), (hand,))
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                detector.detect(frame)
            self.assertFalse(detector.cached)
            self.assertEqual(detector.detect(frame), ())
        make.assert_called_once_with(**profile.solutions_options(2))
        detector.close()
        model.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
