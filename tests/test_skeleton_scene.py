import ast
import atexit
import colorsys
from contextlib import ExitStack
import math
from pathlib import Path
import random
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

from skeleton_people import Body, SkeletonPeople, person_roi


ROOT = Path(__file__).resolve().parents[1]
scene = ModuleType("skeleton_scene_test_target")
scene.__dict__.update(ExitStack=ExitStack, colorsys=colorsys, math=math, random=random, sys=sys,
                      Body=Body, SkeletonPeople=SkeletonPeople, person_roi=person_roi,
                      atexit=mock.Mock(), pygame=mock.Mock(), cv2=mock.Mock(), mp=mock.Mock(),
                      display_utils=mock.Mock(), time=mock.Mock(), notify_first_frame=mock.Mock(),
                      notify_exit_request=mock.Mock())
source = ast.parse((ROOT / "skeleton_glitch.py").read_text(encoding="utf-8"))
definitions = [node for node in source.body if isinstance(node, (ast.Assign, ast.FunctionDef))]
exec(compile(ast.Module(body=definitions, type_ignores=[]), "skeleton_glitch.py", "exec"), scene.__dict__)


def face(center, y=0.2, width=0.14):
    box = SimpleNamespace(xmin=center-width/2, ymin=y, width=width, height=0.12)
    return SimpleNamespace(location_data=SimpleNamespace(relative_bounding_box=box))


class Frame:
    shape = (480, 640, 3)

    def __getitem__(self, key):
        return key


class Pose:
    def __init__(self):
        self.x = 0.5
        self.process = mock.Mock(side_effect=self.result)
        self.close = mock.Mock()

    def result(self, _crop):
        return SimpleNamespace(pose_landmarks=SimpleNamespace(
            landmark=[SimpleNamespace(x=self.x, y=0.5) for _ in range(33)]))


class PeopleTests(unittest.TestCase):
    def setUp(self):
        self.poses = []

        def factory():
            pose = Pose()
            self.poses.append(pose)
            return pose

        self.people = SkeletonPeople(factory)
        self.addCleanup(self.people.close)

    def test_three_independent_pose_instances_and_detection_order_preserve_ids(self):
        first = self.people.update(Frame(), [face(.2), face(.5), face(.8)], 0)
        second = self.people.update(Frame(), [face(.8), face(.2), face(.5)], .1)
        self.assertEqual([body.track_id for body in first], [0, 1, 2])
        self.assertEqual([body.track_id for body in second], [2, 0, 1])
        self.assertEqual(len(self.poses), 3)
        self.assertTrue(all(pose.process.call_count == 2 for pose in self.poses))
        self.assertTrue(all(max(body.velocities) == 0 for body in second))

    def test_no_face_and_camera_gap_break_velocity_and_trails(self):
        self.people.update(Frame(), [face(.5)], 0)
        self.poses[0].x = .55
        moving = self.people.update(Frame(), [face(.5)], .11)[0]
        self.assertGreater(max(moving.velocities), .005)
        self.assertEqual(len(moving.trail), 1)
        self.people.update(Frame(), [], .2)
        self.poses[0].x = .7
        returned = self.people.update(Frame(), [face(.5)], .3)[0]
        self.assertEqual(max(returned.velocities), 0)
        self.assertEqual(returned.trail, ())
        self.people.invalidate_motion()
        self.poses[0].x = .8
        returned = self.people.update(Frame(), [face(.5)], .4)[0]
        self.assertEqual(max(returned.velocities), 0)

    def test_expired_pose_closes_and_reentry_starts_fresh(self):
        self.people.update(Frame(), [face(.5)], 0)
        self.people.update(Frame(), [], 1.01)
        self.poses[0].close.assert_called_once()
        result = self.people.update(Frame(), [face(.5)], 1.1)
        self.assertEqual(result[0].track_id, 1)
        self.assertEqual(max(result[0].velocities), 0)

    def test_fourth_face_cannot_evict_visible_people(self):
        self.people.update(Frame(), [face(.15), face(.45), face(.75)], 0)
        result = self.people.update(Frame(), [face(.95), face(.15), face(.45), face(.75)], .1)
        self.assertEqual({body.track_id for body in result}, {0, 1, 2})
        self.assertEqual(len(self.poses), 3)

    def test_new_face_replaces_only_absent_reservation(self):
        self.people.update(Frame(), [face(.15), face(.45), face(.75)], 0)
        result = self.people.update(Frame(), [face(.45), face(.75), face(.95)], .1)
        self.assertEqual({body.track_id for body in result}, {1, 2, 3})
        self.poses[0].close.assert_called_once()
        self.assertEqual(max(next(body for body in result if body.track_id == 3).velocities), 0)

    def test_ambiguous_encounter_omits_pose_and_cuts_both_histories(self):
        self.people.update(Frame(), [face(.43), face(.57)], 0)
        self.assertEqual(self.people.update(Frame(), [face(.49), face(.53)], .1), [])
        self.assertTrue(all(not track.previous for track in self.people.tracks.values()))
        returned = self.people.update(Frame(), [face(.43), face(.57)], .2)
        self.assertTrue(all(max(body.velocities) == 0 for body in returned))

    def test_duplicate_face_boxes_create_one_pose(self):
        result = self.people.update(Frame(), [face(.5), face(.502)], 0)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(self.poses), 1)

    def test_two_trails_and_three_owners_remain_bounded(self):
        for index in range(200):
            for pose in self.poses:
                pose.x = .35 if index % 2 else .65
            self.people.update(Frame(), [face(.2), face(.5), face(.8)], index * .11)
            self.assertLessEqual(len(self.people.tracks), 3)
            self.assertTrue(all(len(track.trail) <= 2 for track in self.people.tracks.values()))
        self.assertEqual(len(self.poses), 3)

    def test_roi_offsets_are_mapped_back_to_full_camera(self):
        result = self.people.update(Frame(), [face(.2)], 0)[0]
        box = (.13, .2, .14, .12)
        x0, y0, x1, y1 = person_roi(box, 640, 480)
        self.assertAlmostEqual(result.points[0][0], (x0+(x1-x0)*.5)/640)
        self.assertAlmostEqual(result.points[0][1], (y0+(y1-y0)*.5)/480)

    def test_all_pose_cleanups_attempted_when_one_raises(self):
        self.people.update(Frame(), [face(.2), face(.5), face(.8)], 0)
        self.poses[1].close.side_effect = RuntimeError("close pose")
        with self.assertRaisesRegex(RuntimeError, "close pose"):
            self.people.close()
        self.assertTrue(all(pose.close.call_count == 1 for pose in self.poses))
        self.assertEqual(self.people.tracks, {})

    def test_failed_pose_detection_cuts_motion(self):
        self.people.update(Frame(), [face(.5)], 0)
        self.poses[0].process.side_effect = None
        self.poses[0].process.return_value = SimpleNamespace(pose_landmarks=None)
        self.assertEqual(self.people.update(Frame(), [face(.5)], .1), [])
        self.assertFalse(self.people.tracks[0].previous)


class Harness:
    def __init__(self, reads=None, events=None, times=None):
        self.trace = []
        self.cap = mock.Mock()
        self.cap.isOpened.return_value = True
        self.cap.last_read_frame_id = None
        self.cap.read.side_effect = reads or [(True, Frame())]
        self.cap.release.side_effect = lambda: self.trace.append("release")
        self.screen = mock.Mock()
        self.screen.get_size.return_value = (640, 480)
        self.face = mock.Mock()
        self.face.process.return_value = SimpleNamespace(detections=[])
        self.face.close.side_effect = lambda: self.trace.append("face.close")
        self.people = mock.Mock()
        self.people.update.return_value = []
        self.people.close.side_effect = lambda: self.trace.append("people.close")
        self.pygame = SimpleNamespace(QUIT=1, KEYDOWN=2, K_ESCAPE=3, K_q=4,
            init=mock.Mock(), quit=mock.Mock(side_effect=lambda: self.trace.append("quit")),
            display=SimpleNamespace(flip=mock.Mock(side_effect=lambda: self.trace.append("flip"))),
            event=SimpleNamespace(get=mock.Mock(side_effect=events or [[], [SimpleNamespace(type=1)]])),
            time=SimpleNamespace(Clock=mock.Mock(return_value=mock.Mock())))
        self.display = SimpleNamespace(setup_pygame_fullscreen=mock.Mock(return_value=(self.screen, (640, 480))),
            open_camera=mock.Mock(return_value=self.cap),
            prepare_camera_frame=mock.Mock(return_value=(Frame(), Frame(), mock.sentinel.layout)))
        self.cv2 = SimpleNamespace(COLOR_BGR2RGB=1, cvtColor=mock.Mock(return_value=Frame()))
        self.mp = SimpleNamespace(solutions=SimpleNamespace(
            face_detection=SimpleNamespace(FaceDetection=mock.Mock(return_value=self.face)),
            pose=SimpleNamespace(Pose=mock.Mock(), POSE_CONNECTIONS=((0,1),))))
        self.first = mock.Mock(side_effect=lambda *args, **kwargs: self.trace.append("first"))
        self.reason = mock.Mock()
        self.atexit = mock.Mock()
        self.time = SimpleNamespace(monotonic=mock.Mock(side_effect=times or [0]))
        self.draw = mock.Mock(side_effect=lambda *args: self.trace.append("draw"))

    def run(self):
        with ExitStack() as patches:
            for key, value in {"pygame":self.pygame, "display_utils":self.display, "cv2":self.cv2,
                               "mp":self.mp, "SkeletonPeople":mock.Mock(return_value=self.people),
                               "notify_first_frame":self.first, "notify_exit_request":self.reason,
                               "atexit":self.atexit, "time":self.time, "draw_skeletons":self.draw}.items():
                patches.enter_context(mock.patch.object(scene,key,value))
            scene.main()


class SceneTests(unittest.TestCase):
    def test_first_frame_after_draw_and_flip_then_all_cleanup(self):
        h=Harness(); h.run()
        self.assertEqual(h.trace, ["draw","flip","first","release","people.close","face.close","quit"])
        h.first.assert_called_once_with(h.cap, frame_processed=True)
        h.reason.assert_called_once_with("pygame_quit")
        h.display.open_camera.assert_called_once_with()
        h.display.prepare_camera_frame.assert_called_once()
        h.atexit.unregister.assert_called_once()

    def test_true_none_is_not_a_first_frame_and_recovers(self):
        h=Harness(reads=[(True,None),(True,Frame())], events=[[],[],[SimpleNamespace(type=1)]],times=[0,.1]); h.run()
        self.assertEqual([call.kwargs["frame_processed"] for call in h.first.call_args_list],[False,True])
        h.people.invalidate_motion.assert_called_once()

    def test_read_timeout_exits_and_closes_all(self):
        h=Harness(reads=[(False,None)]*2, events=[[],[]],times=[0,1.01]); h.run()
        h.reason.assert_called_once_with("camera_read_failed_timeout")
        self.assertEqual(h.first.call_args.kwargs["frame_processed"],False)
        h.cap.release.assert_called_once(); h.people.close.assert_called_once()

    def test_escape_during_read_grace_remains_responsive(self):
        h=Harness(reads=[(False,None)],events=[[],[SimpleNamespace(type=2,key=3)]],times=[0]); h.run()
        h.reason.assert_called_once_with("key_escape")

    def test_q_quits_before_camera_read(self):
        h=Harness(events=[[SimpleNamespace(type=2,key=4)]]); h.run()
        h.reason.assert_called_once_with("key_q")
        h.cap.read.assert_not_called(); h.first.assert_not_called()

    def test_duplicate_shared_frame_does_not_advance_pose_history(self):
        h=Harness(reads=[(True,Frame())]*2,events=[[],[],[SimpleNamespace(type=1)]],times=[0,.05])
        h.cap.last_read_frame_id=7; h.run()
        h.people.update.assert_called_once()
        self.assertEqual([call.kwargs["frame_processed"] for call in h.first.call_args_list],[True,False])

    def test_display_failure_cannot_emit_first_frame(self):
        h=Harness(); h.pygame.display.flip.side_effect=RuntimeError("flip failed")
        with self.assertRaisesRegex(RuntimeError,"flip failed"): h.run()
        h.first.assert_not_called(); h.cap.release.assert_called_once(); h.people.close.assert_called_once()

    def test_stale_duplicate_frame_times_out_without_new_pose_update(self):
        h=Harness(reads=[(True,Frame())]*2,events=[[],[]],times=[0,1.01])
        h.cap.last_read_frame_id=7; h.run()
        h.reason.assert_called_once_with("camera_read_failed_timeout")
        h.people.update.assert_called_once()
        h.first.assert_called_once_with(h.cap,frame_processed=True)

    def test_processing_failure_still_releases_all(self):
        h=Harness(); h.face.process.side_effect=RuntimeError("detect failed")
        with self.assertRaisesRegex(RuntimeError,"detect failed"): h.run()
        h.first.assert_not_called()
        self.assertEqual(h.trace,["release","people.close","face.close","quit"])

    def test_missing_camera_and_detector_constructor_failure_release_prior_resources(self):
        h=Harness(); h.display.open_camera.return_value=None
        with self.assertRaisesRegex(RuntimeError,"shared camera"): h.run()
        h.face.close.assert_called_once(); h.people.close.assert_called_once(); h.pygame.quit.assert_called_once()
        h=Harness(); h.mp.solutions.face_detection.FaceDetection.side_effect=RuntimeError("constructor")
        with self.assertRaisesRegex(RuntimeError,"constructor"): h.run()
        h.pygame.quit.assert_called_once(); h.atexit.unregister.assert_called_once()

    def test_body_and_multiple_cleanup_exceptions_keep_original_context(self):
        h=Harness(); h.face.process.side_effect=RuntimeError("original detect")
        h.cap.release.side_effect=RuntimeError("release failed")
        h.people.close.side_effect=RuntimeError("people close failed")
        with self.assertRaises(RuntimeError) as caught: h.run()
        messages=[]; current=caught.exception
        while current is not None:
            messages.append(str(current)); current=current.__context__
        self.assertIn("original detect",messages); self.assertIn("release failed",messages)
        h.face.close.assert_called_once(); h.pygame.quit.assert_called_once(); h.atexit.unregister.assert_called_once()

    def test_palette_and_trail_changes_are_slow_and_bounded(self):
        self.assertEqual(scene.glitch_palette(0),scene.glitch_palette(90))
        self.assertNotEqual(scene.glitch_palette(0),scene.glitch_palette(22.5))
        for second in range(90):
            self.assertTrue(.169 <= scene.trail_lifetime(second) <= .351)
            a,b=scene.glitch_palette(second),scene.glitch_palette(second+.016)
            self.assertLessEqual(max(abs(x-y) for c,d in zip(a,b) for x,y in zip(c,d)),1)


if __name__ == "__main__":
    unittest.main()
