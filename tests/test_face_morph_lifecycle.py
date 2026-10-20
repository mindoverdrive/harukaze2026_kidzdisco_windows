import os
import unittest
from unittest import mock
from face_morph_app import main


class FaceMorphLifecycle(unittest.TestCase):
    def runtime(self):
        pg,cv,mp,display,control=[mock.MagicMock() for _ in range(5)]
        pg.QUIT,pg.KEYDOWN,pg.K_ESCAPE=1,2,27
        pg.event.get.side_effect=[[],[mock.Mock(type=1)]]
        screen=mock.Mock();screen.get_size.return_value=(1280,720)
        display.setup_pygame_fullscreen.return_value=(screen,None)
        cap=mock.Mock(last_read_frame_id=1);cap.isOpened.return_value=True
        cap.read.return_value=(True,mock.Mock())
        display.open_camera.return_value=cap
        display.prepare_camera_frame.return_value=(mock.Mock(shape=(720,1280,3)),mock.Mock(),{})
        mp.solutions.face_mesh.FaceMesh.return_value.__enter__.return_value.process.return_value.multi_face_landmarks=[]
        modules={'pygame':pg,'cv2':cv,'mediapipe':mp,'display_utils':display,'scene_control':control,
                 'shared_camera':mock.Mock(ENV_REQUIRED='HARUKAZE_SHARED_CAMERA_REQUIRED')}
        return modules,cap

    def test_successful_first_draw_then_window_close_cleans_all(self):
        modules,cap=self.runtime();order=[]
        modules['pygame'].display.flip.side_effect=lambda:order.append('render')
        modules['scene_control'].notify_first_frame.side_effect=lambda *a,**k:order.append('first')
        with mock.patch.dict('sys.modules',modules),mock.patch.dict(os.environ,{'HARUKAZE_SHARED_CAMERA_REQUIRED':'1'}),mock.patch('face_morph_app.draw_meshes'):
            main()
        self.assertEqual(order,['render','first'])
        cap.release.assert_called_once();modules['pygame'].quit.assert_called_once()
        modules['mediapipe'].solutions.face_mesh.FaceMesh.return_value.__exit__.assert_called_once()
        self.assertEqual(modules['mediapipe'].solutions.face_mesh.FaceMesh.call_args.kwargs['max_num_faces'],5)

    def test_failed_draw_never_announces_and_releases(self):
        modules,cap=self.runtime()
        modules['pygame'].display.flip.side_effect=RuntimeError('render failed')
        with mock.patch.dict('sys.modules',modules),mock.patch.dict(os.environ,{'HARUKAZE_SHARED_CAMERA_REQUIRED':'1'}),mock.patch('face_morph_app.draw_meshes'):
            with self.assertRaisesRegex(RuntimeError,'render failed'):main()
        modules['scene_control'].notify_first_frame.assert_not_called()
        cap.release.assert_called_once();modules['pygame'].quit.assert_called_once()

    def test_no_manager_allocates_no_window_or_camera(self):
        modules,cap=self.runtime()
        with mock.patch.dict('sys.modules',modules),mock.patch.dict(os.environ,{'HARUKAZE_SHARED_CAMERA_REQUIRED':''}):
            with self.assertRaisesRegex(RuntimeError,'requires'):main()
        modules['pygame'].init.assert_not_called()
        modules['display_utils'].open_camera.assert_not_called()

    def test_detector_initialization_failure_releases_camera_window(self):
        modules,cap=self.runtime()
        modules['mediapipe'].solutions.face_mesh.FaceMesh.side_effect=RuntimeError('model failed')
        with mock.patch.dict('sys.modules',modules),mock.patch.dict(os.environ,{'HARUKAZE_SHARED_CAMERA_REQUIRED':'1'}):
            with self.assertRaisesRegex(RuntimeError,'model failed'):main()
        cap.release.assert_called_once();modules['pygame'].quit.assert_called_once()

    def test_frozen_frame_expires_without_first_frame(self):
        modules,cap=self.runtime();cap.last_read_frame_id=0
        with mock.patch.dict('sys.modules',modules),mock.patch.dict(os.environ,{'HARUKAZE_SHARED_CAMERA_REQUIRED':'1'}),mock.patch('face_morph_app.time.monotonic',side_effect=[0.,4.]):
            with self.assertRaisesRegex(RuntimeError,'stalled'):main()
        modules['scene_control'].notify_first_frame.assert_not_called()
        cap.release.assert_called_once();modules['pygame'].quit.assert_called_once()


if __name__=='__main__':unittest.main()
