"""Manager contracts with actual CPU scenes/SHM and mocked native boundaries."""
from contextlib import ExitStack
import gc
import json
from multiprocessing import shared_memory
import os
from pathlib import Path
import random
import runpy
import struct
import sys
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import weakref

import cv2
import numpy as np
import display_utils
import hand_drawing_app as drawing
import hand_shapes_app as shapes
from hand_drawing_effects import FadingInk
from hand_drawing_feedback import draw_color_guidance
import scene_control
import scene_profile_runner as runner
import shared_camera
from test_hand_shapes_app import hand, result

ROOT = Path(__file__).resolve().parents[1]


class ManagedHandSceneTests(unittest.TestCase):
    def test_both_wrappers_wait_for_tcp_start_before_scene_code_and_restore_state(self):
        for source in ('hand_drawing_app.py', 'hand_shapes_app.py'):
            with self.subTest(source=source):
                events = []
                control = mock.Mock(first_frame_sent=True)
                control.wait_for_start.side_effect = lambda: events.append('START_ACK')
                argv = ['scene_acer.py', '--control-port', '12345', '--launch-id', 'fixture']
                def execute(path, run_name):
                    self.assertEqual(events, ['START_ACK'])
                    self.assertEqual(Path(path).name, source)
                    self.assertEqual(sys.argv, [str(ROOT / source)])
                    self.assertIs(scene_control._child_control, control)
                    events.append('scene')
                with mock.patch.object(sys, 'argv', argv), \
                        mock.patch.object(runner.scene_control, 'SceneChildControl', return_value=control), \
                        mock.patch.object(runner.runpy, 'run_path', side_effect=execute), \
                        mock.patch('builtins.print'):
                    before = scene_control._child_control
                    runner.run_scene(source, profile='acer')
                    self.assertIs(scene_control._child_control, before)
                    self.assertEqual(sys.argv, argv)
                control.close.assert_called_once_with()
                self.assertEqual(events, ['START_ACK', 'scene'])

    def test_both_managed_mains_use_audience_size_and_production_lifecycle(self):
        for module in (drawing, shapes):
            with self.subTest(module=module.__name__), \
                    mock.patch.object(scene_control, '_child_control', object()), \
                    mock.patch.object(display_utils, 'get_stage_size', return_value=(1280, 1024)), \
                    mock.patch.object(module, 'run_app') as run:
                module.main([])
                kw = run.call_args.kwargs
                self.assertEqual((kw['width'], kw['height'], kw['production']), (1280, 1024, True))
                if module is shapes:
                    self.assertEqual((kw['controller'].width, kw['controller'].height), (1280, 1024))

    def test_missing_or_optional_shared_camera_is_rejected_before_allocating_model(self):
        for env in ({}, {'HARUKAZE_CAMERA_SHM':'fixture'},
                    {'HARUKAZE_SHARED_CAMERA_REQUIRED':'true'}):
            with self.subTest(env=env), mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(drawing.mp.solutions.hands, 'Hands') as model, \
                    mock.patch.object(display_utils, 'open_camera') as camera:
                with self.assertRaisesRegex(RuntimeError, 'shared camera'):
                    drawing.run_app(production=True)
                model.assert_not_called()
                camera.assert_not_called()

    def test_production_window_uses_existing_audience_geometry_including_negative_offsets(self):
        with mock.patch.object(display_utils, 'get_second_monitor', return_value=(-1600, -200, 1280, 1024)), \
                mock.patch.object(cv2, 'namedWindow'), mock.patch.object(cv2, 'moveWindow') as move, \
                mock.patch.object(cv2, 'resizeWindow') as resize, mock.patch.object(cv2, 'setWindowProperty') as prop:
            drawing.setup_window(1280, 1024, window_name='hand-stage', production=True)
        move.assert_called_once_with('hand-stage', -1600, -200)
        resize.assert_called_once_with('hand-stage', 1280, 1024)
        prop.assert_called_once_with('hand-stage', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    def test_real_shared_memory_is_single_attachment_and_released_on_all_scene_exit_paths(self):
        width, height = 64, 48
        memory = shared_memory.SharedMemory(create=True, size=shared_camera.HEADER_SIZE + width*height*3)
        self.addCleanup(memory.unlink)
        self.addCleanup(memory.close)
        env = {'HARUKAZE_SHARED_CAMERA':'1', 'HARUKAZE_SHARED_CAMERA_REQUIRED':'true',
               'HARUKAZE_CAMERA_SHM':memory.name, 'HARUKAZE_CAMERA_WIDTH':str(width),
               'HARUKAZE_CAMERA_HEIGHT':str(height), 'HARUKAZE_CAMERA_CHANNELS':'3'}
        original_release = shared_camera.SharedMemoryCamera.release
        for module in (drawing, shapes):
            for failure in (None, 'infer', 'render', 'window', 'interrupt'):
                with self.subTest(scene=module.__name__, failure=failure), ExitStack() as stack:
                    struct.pack_into(shared_camera.HEADER_FORMAT, memory.buf, 0,
                                     shared_camera.MAGIC, width, height, 3, 2, 2, 1, time.monotonic())
                    memory.buf[shared_camera.HEADER_SIZE:] = bytes(width*height*3)
                    stack.enter_context(mock.patch.dict(os.environ, env))
                    physical = stack.enter_context(mock.patch.object(cv2, 'VideoCapture', side_effect=AssertionError('physical camera')))
                    attach = stack.enter_context(mock.patch.object(shared_camera.SharedMemoryCamera, 'from_env', wraps=shared_camera.SharedMemoryCamera.from_env))
                    release = stack.enter_context(mock.patch.object(shared_camera.SharedMemoryCamera, 'release', autospec=True, side_effect=original_release))
                    model = mock.Mock()
                    model.process.return_value = None
                    if failure == 'infer': model.process.side_effect = RuntimeError('infer')
                    stack.enter_context(mock.patch.object(drawing.mp.solutions.hands, 'Hands', return_value=model))
                    window = stack.enter_context(mock.patch.object(drawing, 'setup_window'))
                    if failure == 'window': window.side_effect = RuntimeError('window')
                    close = stack.enter_context(mock.patch.object(drawing, 'close_window'))
                    stack.enter_context(mock.patch.object(cv2, 'waitKey', side_effect=[0, ord('q')]))
                    stack.enter_context(mock.patch.object(cv2, 'getWindowProperty', return_value=1))
                    order = []
                    stack.enter_context(mock.patch.object(cv2, 'imshow', side_effect=lambda *a: order.append('present')))
                    control = mock.Mock()
                    control.first_frame.side_effect = lambda cap: order.append(('FIRST_FRAME',cap.last_read_frame_id,cap.shm_name))
                    stack.enter_context(mock.patch.object(scene_control, '_child_control', control))
                    ink_refs = []
                    def render(stage, ink, frame, layout, now):
                        ink_refs.append(weakref.ref(ink))
                        if failure == 'render': raise RuntimeError('render')
                        if failure == 'interrupt': raise KeyboardInterrupt()
                        return module.render_frame(stage, ink, frame, layout, now)
                    kwargs = dict(width=320, height=240, production=True, renderer=render)
                    if module is shapes: kwargs.update(controller=shapes.ShapeInput(320,240),hold_seconds=0)
                    if failure:
                        with self.assertRaises(KeyboardInterrupt if failure=='interrupt' else RuntimeError):
                            drawing.run_app(**kwargs)
                    else:
                        drawing.run_app(**kwargs)
                        self.assertEqual(order, ['present', ('FIRST_FRAME', 1, memory.name)])
                    physical.assert_not_called()
                    attach.assert_called_once_with()
                    release.assert_called_once()
                    self.assertTrue(release.call_args.args[0].closed)
                    model.close.assert_called_once_with()
                    close.assert_called_once()
                    gc.collect()
                    self.assertTrue(all(ref() is None for ref in ink_refs))

    def test_missing_shared_mapping_never_falls_back_to_physical_capture(self):
        env={'HARUKAZE_SHARED_CAMERA':'1','HARUKAZE_SHARED_CAMERA_REQUIRED':'true',
             'HARUKAZE_CAMERA_SHM':'nonexistent_hand_scene_test_mapping',
             'HARUKAZE_CAMERA_WIDTH':'64','HARUKAZE_CAMERA_HEIGHT':'48'}
        with mock.patch.dict(os.environ,env), \
                mock.patch.object(cv2,'VideoCapture',side_effect=AssertionError('physical camera')) as physical, \
                mock.patch.object(drawing.mp.solutions.hands,'Hands') as factory:
            with self.assertRaisesRegex(RuntimeError,'Camera unavailable'):
                drawing.run_app(production=True)
            physical.assert_not_called()
            factory.return_value.close.assert_called_once()


class ContinuousHandSceneTests(unittest.TestCase):
    def test_simulated_two_minutes_per_scene_keeps_history_tracks_and_image_buffers_bounded(self):
        width,height=320,240
        layout=display_utils.get_uniform_layout(width,height,width,height)
        for Scene in (drawing.DrawingInput,shapes.ShapeInput):
            with self.subTest(scene=Scene.__name__):
                controller=Scene(width,height,rng=random.Random(31))
                ink=FadingInk(width,height,0 if Scene is shapes.ShapeInput else 3.5,3,1920)
                arrays=[v for v in vars(ink).values() if isinstance(v,np.ndarray)]
                buffers={id(a):a.nbytes for a in arrays}
                for step in range(1800):  # 120 s synthetic time at 15 observations/s.
                    now=step/15
                    poses=[]
                    for index in range(8):
                        side='Left' if index%2 else 'Right'
                        # Repeated loss/re-entry and count changes exercise state eviction.
                        if (step//90+index)%13==0: continue
                        count=1+(step//30+index)%5
                        poses.append((hand(count,x=.12+(index%4)*.23,y=.30+(index//4)*.40,
                                           side=side,scale=.22,angle=.15),side))
                    observations=SimpleNamespace(multi_hand_landmarks=[p for p,_ in poses],
                        multi_handedness=[SimpleNamespace(classification=[SimpleNamespace(label=s)]) for _,s in poses])
                    if step%2: observations.multi_hand_landmarks.reverse(); observations.multi_handedness.reverse()
                    frame=controller.update(observations,layout,now)
                    for stroke in frame.strokes:
                        ink.add_segment(stroke.start,stroke.end,stroke.color_bgr,now,
                                        effect_id=stroke.effect_id,track_id=stroke.track_id)
                    ink.advance(now)
                    self.assertLessEqual(len(ink.segments),1920)
                    self.assertLessEqual(len(controller.tracker.tracks),8)
                    for key in ('colors','previous_tips','last_stroke_times','counts','poses','current'):
                        if hasattr(controller,key): self.assertLessEqual(len(getattr(controller,key)),8,key)
                    if step%150==0:
                        ink.render(now)
                        self.assertEqual({id(a):a.nbytes for a in vars(ink).values() if isinstance(a,np.ndarray)},buffers)
                empty=controller.update(None,now=124,layout=layout)
                for stroke in empty.strokes:
                    ink.add_segment(stroke.start,stroke.end,stroke.color_bgr,124,
                                    effect_id=stroke.effect_id,track_id=stroke.track_id)
                ink.render(132)
                self.assertFalse(ink.segments)
                self.assertEqual(len(controller.tracker.tracks),0)
                if hasattr(controller,'current'): self.assertFalse(controller.current)

    def test_shape_guide_avoids_navigation_like_drawing_and_keeps_input_markers_visible(self):
        from transition_overlay import navigation_regions
        image=np.full((720,1280,3),73,np.uint8)
        before=image.copy()
        items=tuple(drawing.HandInput(i+1,i,'Left' if i%2 else 'Right',(640,350),i%5+1,(640,350)) for i in range(8))
        draw_color_guidance(image,items,((640,350),),shape_outlines=shapes.CANONICAL_SHAPES)
        for x,y,w,h in navigation_regions(1280,720).values():
            np.testing.assert_array_equal(image[y:y+h,x:x+w],before[y:y+h,x:x+w])
        np.testing.assert_array_equal(image[332:368,622:658],before[332:368,622:658])


if __name__=='__main__': unittest.main()
