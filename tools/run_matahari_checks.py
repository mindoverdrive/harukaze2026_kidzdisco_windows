"""Headless regression runner; blocks physical input, model inference, GUI."""
import argparse
from contextlib import ExitStack
import importlib
import json
import os
from pathlib import Path
import sys
import unittest
import tempfile
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / 'test_reports/headless'
OUT.mkdir(parents=True, exist_ok=True)
root = BASE
tempfile.tempdir = str(OUT)
os.environ['PYGFX_DISABLE_SYSTEM_FONTS'] = '1'
os.environ.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', PYTHONDONTWRITEBYTECODE='1')
sys.path[:0] = [str(root), str(root/'tests'), str(BASE/'tests')]
os.environ['MINECRAFT_TEST_ROOT'] = str(root)
os.environ['MATAHARI_MODE_ACER_SOURCE'] = str(root/'tools/start_hand_play.py')
import cv2, numpy, pygame, mediapipe, pygfx
import glfw
from mediapipe.tasks.python import vision

modules = '''test_windows_containment test_staff_safe_regressions test_external_test_entry test_minecraft_projection test_launch_production test_audience_launch test_matahari_modes test_all_hand_profile test_hand_focus_overlay test_hand_focus_pygfx
test_hand_overlay_grid test_passive_hand_scenes test_hand_field_scenes
test_hand_drawing_app test_hand_drawing_effects test_hand_drawing_feedback
test_hand_drawing_tracking test_hand_finger_feedback test_hand_shapes_app
test_hand_shapes_motion test_hand_scene_integration test_fractal_feedback
test_mandala3_scene test_mandala_motion test_wave_dots_scene test_tree_scene
test_particle_storm_camera_extent test_particle_storm_depth test_saturn_projection
test_saturn_navigation_coordinates test_prism_skin test_living_mosaic
test_spheres_camera test_spheres_scene test_spider_camera_recovery
test_modern_otedama_production test_otedama_multi_hand test_earth_production
test_minecraft_lifecycle test_minecraft_reset_gesture test_minecraft_reset_effect
test_face_morph test_face_morph_diagnostics test_face_morph_lifecycle
test_face_morph_test_input test_navigation_charge test_navigation_hold
test_staff_lifecycle test_camera_coordinates test_first_frame_render
test_runner_finalization test_scene_resources test_scene_timing
test_face_scale_double test_minecraft_return_ui'''.split()

def denied(*a, **kw):
    raise AssertionError('Native camera/window/model start forbidden by regression runner')

suffix = 'current'
for name in (f'tests-{suffix}.log', f'summary-{suffix}.json'):
    path = OUT/name
    if path.exists():
        attempt = 1
        while (OUT/f'attempt-{attempt}-{name}').exists():
            attempt += 1
        path.rename(OUT/f'attempt-{attempt}-{name}')
with ExitStack() as guards:
    for obj, name in [(cv2,'VideoCapture'), (cv2,'imshow'), (cv2,'namedWindow'),
                      (cv2,'waitKey'), (pygame.display,'set_mode'), (glfw,'create_window'),
                      (mediapipe.solutions.hands,'Hands'),
                      (mediapipe.solutions.face_mesh,'FaceMesh'),
                      (mediapipe.solutions.pose,'Pose'),
                      (vision.HandLandmarker, 'create_from_options')]:
        guards.enter_context(mock.patch.object(obj, name, side_effect=denied))
    suite = unittest.TestSuite()
    for name in modules:
        module = importlib.import_module(name)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    with (OUT/f'tests-{suffix}.log').open('w', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   skipped=len(result.skipped), camera_opened=False, window_opened=False,
                   native_detector_opened=False,
                   problems=[dict(test=str(t), error=e) for t,e in result.failures+result.errors])
    (OUT/f'summary-{suffix}.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({**summary, 'problems': [dict(test=p['test'], error=p['error'].splitlines()[-1][:300])
                                            for p in summary['problems']]}, indent=2))
    raise SystemExit(not result.wasSuccessful())
