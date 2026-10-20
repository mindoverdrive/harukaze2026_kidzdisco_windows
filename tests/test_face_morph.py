import math
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import numpy as np
from face_morph_field import Face,FaceMorphField,Settings,FORMS,local_mesh,stage_mesh,face_from_landmarks


def crowd(n=5,opening=0):
    return [Face(.12+i*.19,.55,.11,.23,opening) for i in range(n)]


def hold(field, opening, seconds, people=1, fps=30):
    for _ in range(round(seconds*fps)):
        now=(field.previous_time if field.previous_time is not None else -1/fps)+1/fps
        field.step(crowd(people,opening),now)


class MorphStateTests(unittest.TestCase):
    def invariants(self,field):
        shapes=[s for t in field.tracks.values() for s in (t.shape,t.previous_shape) if s is not None]
        self.assertEqual(len(shapes),len(set(shapes)))
        self.assertLessEqual(len(field.tracks),5)
        self.assertLessEqual(len(shapes),10)

    def test_five_people_simultaneous_cycles_and_reservations_seeded(self):
        fields=[FaceMorphField(seed=4),FaceMorphField(seed=4)]
        seen=[]
        for frame in range(900):
            now=frame/30
            opening=1. if now%1.4<.7 else 0.
            for field in fields:
                field.step(crowd(5,opening),now);self.invariants(field)
            self.assertEqual([(t.shape,t.previous_shape) for t in fields[0].tracks.values()],
                             [(t.shape,t.previous_shape) for t in fields[1].tracks.values()])
            seen.append(tuple(t.shape for t in fields[0].tracks.values()))
        self.assertGreater(fields[0].changes,15)
        self.assertEqual(fields[0].changes,sum(t.changes for t in fields[0].tracks.values()))
        self.assertGreater(len(set(seen)),3)

    def test_one_to_five_entry_exit_release(self):
        f=FaceMorphField()
        for n in range(1,6):f.step(crowd(n),n*.1);self.invariants(f)
        self.assertEqual(len(f.tracks),5)
        f.step([],3)
        self.assertFalse(f.reserved())
        self.assertFalse(f.tracks)

    def test_detection_order_is_not_identity(self):
        f=FaceMorphField();f.step(crowd(),0)
        before={round(t.face.x,2):t.shape for t in f.tracks.values()}
        f.step(list(reversed(crowd())),.03)
        self.assertEqual(before,{round(t.face.x,2):t.shape for t in f.tracks.values()})

    def test_distant_equidistant_newcomer_can_join(self):
        f=FaceMorphField()
        original=[Face(.3,.4,.1,.2,0),Face(.5,.4,.1,.2,0)]
        newcomer=Face(.4,.8,.1,.2,0)
        f.step(original,0)
        shapes=[t.shape for t in f.tracks.values()]
        for frame in range(1,121):
            f.step(original+[newcomer],frame/30)
            self.invariants(f)
            self.assertEqual(len(f.tracks),3)
            self.assertTrue(all(t.visible for t in f.tracks.values()))
        self.assertEqual(shapes,[f.tracks[i].shape for i in range(2)])
        self.assertEqual((f.last_observation_count,f.last_ambiguous_count,f.last_suppressed_count),(3,0,0))

    def test_uncertain_tracks_only_suppress_nearby_newcomers(self):
        f=FaceMorphField()
        f.step([Face(.4,.5,.12,.2,0),Face(.6,.5,.12,.2,0)],0)
        f.step([Face(.49,.5,.12,.2,0),Face(.51,.5,.12,.2,0)],.03)
        self.assertTrue(all(t.uncertain for t in f.tracks.values()))
        self.assertEqual((f.last_observation_count,f.last_ambiguous_count,f.last_suppressed_count),(2,2,2))
        f.step([Face(.05,.9,.08,.16,0),Face(.95,.9,.08,.16,0)],.06)
        self.invariants(f)
        self.assertEqual(len(f.tracks),4)
        self.assertEqual(sum(t.visible for t in f.tracks.values()),2)
        self.assertFalse(f.tracks[0].visible or f.tracks[1].visible)
        self.assertEqual({t.face.x for t in f.tracks.values() if t.visible},{.05,.95})
        self.assertEqual((f.last_observation_count,f.last_ambiguous_count,f.last_suppressed_count),(2,0,0))

    def test_match_uses_a_candidate_inside_its_own_size_gate(self):
        f=FaceMorphField()
        f.step([Face(.3,.5,.04,.1,0),Face(.5,.5,.2,.3,0)],0)
        shape=f.tracks[1].shape
        f.step([Face(.38,.5,.04,.1,0)],.03)
        self.assertEqual(len(f.tracks),2)
        self.assertFalse(f.tracks[0].visible)
        self.assertTrue(f.tracks[1].visible)
        self.assertEqual(f.tracks[1].shape,shape)
        self.assertEqual(f.tracks[1].face.x,.38)

    def test_crossing_ambiguity_suppresses_instead_of_transferring(self):
        f=FaceMorphField();f.step([Face(.4,.5,.12,.2,0),Face(.6,.5,.12,.2,0)],0)
        original=[t.shape for t in f.tracks.values()]
        for frame in range(1,12):
            f.step([Face(.49,.5,.12,.2,1),Face(.51,.5,.12,.2,1)],frame*.03)
            self.assertFalse(any(t.visible for t in f.tracks.values()))
            self.invariants(f)
        self.assertEqual(original,[t.shape for t in f.tracks.values()])
        self.assertEqual(f.changes,0)
        f.step([Face(.6,.5,.12,.2,1),Face(.4,.5,.12,.2,1)],.4)
        self.assertFalse(any(t.visible for t in f.tracks.values()))

    def test_occlusion_preserves_shape_open_state_and_no_false_close(self):
        f=FaceMorphField()
        for i in range(15):f.step(crowd(1,1),i*.03)
        t=f.tracks[0];shape=t.shape
        self.assertTrue(t.opened)
        f.step([],.6)
        self.assertTrue(t.opened)
        for i in range(25):f.step(crowd(1,0),.7+i*.03)
        self.assertEqual(t.shape,shape);self.assertEqual(t.changes,0)
        self.assertTrue(t.armed)

    def test_hold_open_jitter_fast_cycles_never_transform(self):
        for mode in ('open','jitter','fast'):
            f=FaceMorphField()
            for i in range(900):
                opening=1 if mode=='open' else (.27 if i%2 else .29) if mode=='jitter' else i%2
                f.step(crowd(1,opening),i/30)
            self.assertEqual(f.changes,0)

    def test_single_missed_frame_cannot_count_a_close(self):
        f=FaceMorphField()
        for i in range(15):f.step(crowd(1,1),i/30)
        f.step([], .5)
        for i in range(20):f.step(crowd(1,0),.53+i/30)
        self.assertEqual(f.tracks[0].changes,0)

    def test_pool_exhaustion_waits_and_resumes(self):
        f=FaceMorphField();hold(f,0,.4,people=5)
        for index,t in enumerate(f.tracks.values()):t.shape=index
        with mock.patch('face_morph_field.FORMS',FORMS[:5]):hold(f,1,.4,people=5)
        self.assertEqual(f.changes,0)
        self.assertTrue(all(t.pending_open for t in f.tracks.values()))
        hold(f,1,1/30,people=5);self.invariants(f)
        self.assertEqual(f.changes,5)

    def test_each_stable_open_changes_immediately_without_three_cycles_or_four_seconds(self):
        f=FaceMorphField();hold(f,0,.4);t=f.tracks[0];old=t.shape
        self.assertTrue(t.armed)
        hold(f,1,.3)
        self.assertEqual(f.changes,1);self.assertNotEqual(t.shape,old)
        self.assertEqual(t.previous_shape,old)
        hold(f,1,.7);self.assertEqual(f.changes,1)
        hold(f,0,.4);second=t.shape
        hold(f,1,.3)
        self.assertEqual(f.changes,2);self.assertNotEqual(t.shape,second)
        self.assertLess(f.previous_time,4)

    def test_hysteresis_band_or_brief_close_cannot_rearm(self):
        f=FaceMorphField();hold(f,.20,.5);hold(f,1,.4)
        self.assertEqual(f.changes,0)
        hold(f,0,.4);hold(f,1,.4);self.assertEqual(f.changes,1)
        hold(f,0,.1);hold(f,1,.5);self.assertEqual(f.changes,1)
        hold(f,.20,.5);hold(f,1,.4);self.assertEqual(f.changes,1)

    def test_armed_threshold_jitter_never_fires(self):
        f=FaceMorphField();hold(f,0,.4)
        for i in range(300):
            hold(f,.27 if i%2 else .29,1/30)
        self.assertEqual(f.changes,0)
        hold(f,1,.4);self.assertEqual(f.changes,1)

    def test_return_open_or_stalled_input_requires_fresh_closed_state(self):
        for lost in (True,False):
            f=FaceMorphField();hold(f,0,.4)
            if lost:f.step([],f.previous_time+1/30)
            else:f.step(crowd(1,1),f.previous_time+.3)
            hold(f,1,.7)
            self.assertEqual(f.changes,0)
            hold(f,0,.4);hold(f,1,.4)
            self.assertEqual(f.changes,1)

    def test_second_open_during_morph_is_consumed_once_after_completion(self):
        f=FaceMorphField();hold(f,0,.3,fps=120)
        hold(f,1,.16,fps=120);self.assertEqual(f.changes,1)
        first_start=f.tracks[0].morph_start
        hold(f,0,.23,fps=120);hold(f,1,.16,fps=120)
        self.assertLess(f.previous_time-first_start,f.settings.morph_seconds)
        self.assertTrue(f.tracks[0].pending_open)
        self.assertEqual(f.changes,1)
        hold(f,1,1.,fps=120)
        self.assertEqual(f.changes,2);self.invariants(f)

    def test_pending_open_cancels_on_loss_or_stable_close(self):
        for cancel in ('lost','closed'):
            f=FaceMorphField(settings=Settings(morph_seconds=1.5))
            hold(f,0,.4);hold(f,1,.3);hold(f,0,.4);hold(f,1,.3)
            self.assertTrue(f.tracks[0].pending_open)
            if cancel=='lost':
                f.step([],f.previous_time+1/30);hold(f,1,1.)
            else:hold(f,0,1.)
            self.assertFalse(f.tracks[0].pending_open)
            self.assertEqual(f.changes,1)

    def test_large_dt_no_face_invalid_inputs_and_close(self):
        f=FaceMorphField();f.step(crowd(5,1),0)
        f.step([Face(float('nan'),0,.1,.2,1)],10)
        self.assertFalse(f.tracks)
        f.step(crowd(),11);self.invariants(f)
        f.close();f.close();self.assertFalse(f.reserved())
        self.assertEqual((f.last_observation_count,f.last_ambiguous_count,f.last_suppressed_count),(0,0,0))


class GeometryTests(unittest.TestCase):
    def test_double_maximum_scale_preserves_closed_size_and_caps_close_faces(self):
        import display_utils
        f=FaceMorphField();f.step([Face(.5,.5,.06,.12,0)],0);t=f.tracks[0]
        layout=display_utils.get_uniform_layout(1280,720,1280,720)
        # Hold silhouette and angle constant to measure only requested scale.
        vertices=np.array([[-1.,0],[1.,0],[0,-1.],[0,1.]])
        with mock.patch('face_morph_field.local_mesh',return_value=(vertices,np.array([[0,1,2]]))):
            closed,_=stage_mesh(t,0,layout)
            t.expansion=1.
            opened,_=stage_mesh(t,0,layout)
            self.assertAlmostEqual(np.ptp(opened[:,0])/np.ptp(closed[:,0]),2.72,delta=.03)
            self.assertAlmostEqual(np.ptp(opened[:,1])/np.ptp(closed[:,1]),2.72,delta=.03)
            for width,height in ((1280,720),(800,1280),(640,480)):
                layout=display_utils.get_uniform_layout(1280,720,width,height)
                t.face=replace(t.face,width=3,height=3,angle=.7)
                points,_=stage_mesh(t,0,layout)
                self.assertLessEqual(max(np.ptp(points[:,0]),np.ptp(points[:,1])),min(width,height)*.6+2)

    def test_expansion_is_time_based_smoothed_and_bounded(self):
        values=[]
        for fps in (30,60,120):
            f=FaceMorphField();hold(f,0,.3,fps=fps)
            hold(f,1,.1,fps=fps)
            values.append(f.tracks[0].expansion)
            self.assertGreater(values[-1],.6);self.assertLess(values[-1],.65)
            hold(f,1,1.,fps=fps)
            self.assertLessEqual(f.tracks[0].expansion,1.)
        self.assertLess(max(values)-min(values),1e-10)

    def test_twelve_geometries_are_distinct_bounded_fixed_topology(self):
        signatures=[]
        for form in range(12):
            closed,tri=local_mesh(form,0,1.)
            opened,_=local_mesh(form,1,1.)
            signatures.append(closed.round(3).tobytes())
            self.assertEqual(closed.shape,(193,2));self.assertEqual(tri.shape,(336,3))
            self.assertLessEqual(np.linalg.norm(opened,axis=1).max(),1.00001)
            self.assertFalse(np.allclose(closed,opened))
        self.assertEqual(len(set(signatures)),12)

    def test_resolution_changes_and_morph_continuity(self):
        import display_utils
        f=FaceMorphField();f.step(crowd(1),0);t=f.tracks[0]
        for width,height in [(1280,720),(1920,1080),(800,1280),(640,480)]:
            layout=display_utils.get_uniform_layout(1280,720,width,height)
            points,_=stage_mesh(t,0,layout)
            t.previous_shape=t.shape;t.shape=(t.shape+1)%12;t.morph_start=0
            start,_=stage_mesh(t,0,layout)
            np.testing.assert_array_equal(points,start)
            finish,_=stage_mesh(t,.45,layout)
            self.assertTrue(np.isfinite(finish).all())
            self.assertGreaterEqual(finish.min(),0)
            self.assertTrue((finish[:,0]<width).all() and (finish[:,1]<height).all())
            t.previous_shape=None

    def test_landmark_ratio_uses_existing_scale_and_pixel_aspect(self):
        lm=[SimpleNamespace(x=.5,y=.5) for _ in range(468)]
        lm[10].y=.2;lm[152].y=.8;lm[13].y=.45;lm[14].y=.55
        lm[234].x=.3;lm[454].x=.7
        a=face_from_landmarks(lm,1280,720);b=face_from_landmarks(lm,640,360)
        self.assertAlmostEqual(a.opening,b.opening)
        self.assertGreater(a.opening,.28)

    def test_new_candidate_not_in_rotation_or_staff(self):
        root=Path(__file__).resolve().parents[1]
        self.assertNotIn('face_morph',(root/'configs/rebirth_operator_acer_xiaomi.json').read_text())
        self.assertNotIn('face_morph',(root/'staff_scene_manager.py').read_text(encoding='utf-8'))

    def test_renderer_preserves_navigation_corners(self):
        import display_utils
        from face_morph_app import draw_meshes
        field=FaceMorphField();field.step([Face(.05,.1,.2,.3,1)],0)
        image=np.zeros((720,1280,3),dtype=np.uint8)
        draw_meshes(image,field,1,display_utils.get_uniform_layout(1280,720,1280,720))
        self.assertFalse(image[:130,:230].any())
        self.assertFalse(image[:130,-230:].any())


if __name__=='__main__':unittest.main()
