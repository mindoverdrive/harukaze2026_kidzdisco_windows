"""Numeric maximum-scale and renderer limits, no camera, model or window."""
from dataclasses import replace
import math
import unittest
from unittest.mock import patch

import cv2
import numpy as np
import display_utils
import face_morph_field as field
from face_morph_app import draw_meshes

COMPASS = np.array([[-1.,0.],[1.,0.],[0.,-1.],[0.,1.]])
TRIANGLES = np.array([[0,1,2]])

class MaximumScaleTests(unittest.TestCase):
    def track(self, size=(.06,.12)):
        return field.Track(field.Face(.5,.5,*size,0),0,0,0)

    def points(self, track, width=1280, height=720):
        return field.stage_mesh(track,0,display_utils.get_uniform_layout(1280,720,width,height))[0]

    def test_maximum_total_scale_is_doubled_without_doubling_the_closed_mesh(self):
        self.assertAlmostEqual(1+field.OPEN_EXPANSION_GAIN,2.72)
        track = self.track()
        with patch.object(field,'local_mesh',return_value=(COMPASS,TRIANGLES)):
            closed = self.points(track)
            with patch.object(field,'OPEN_EXPANSION_GAIN',.36):
                np.testing.assert_array_equal(self.points(track),closed)
                track.expansion=1
                previous = self.points(track)
            current = self.points(track)
        for axis in (0,1):
            self.assertAlmostEqual(np.ptp(current[:,axis])/np.ptp(previous[:,axis]),2.,delta=.03)
            self.assertAlmostEqual(np.ptp(current[:,axis])/np.ptp(closed[:,axis]),2.72,delta=.03)

    def test_partial_opening_interpolates_from_the_same_closed_size(self):
        track = self.track()
        with patch.object(field,'local_mesh',return_value=(COMPASS,TRIANGLES)):
            closed = self.points(track)
            track.expansion=.5
            partial = self.points(track)
        self.assertAlmostEqual(np.ptp(partial[:,0])/np.ptp(closed[:,0]),1.86,delta=.03)

    def test_large_face_hits_the_same_viewport_cap_instead_of_covering_the_screen(self):
        track = self.track((3.,3.))
        track.expansion=1
        for width,height in ((1280,720),(800,1280),(640,480)):
            layout = display_utils.get_uniform_layout(1280,720,width,height)
            center = np.array(display_utils.normalized_to_stage(.5,.5,layout))
            track.face=replace(track.face,angle=.7)
            with patch.object(field,'OPEN_EXPANSION_GAIN',.36):
                previous=self.points(track,width,height)
            current=self.points(track,width,height)
            np.testing.assert_array_equal(current,previous)
            self.assertLessEqual(np.linalg.norm(current-center,axis=1).max(),min(width,height)*.30+2)

    def test_expansion_keeps_existing_smoothing_at_30_60_and_120_fps(self):
        values=[]
        for fps in (30,60,120):
            f=field.FaceMorphField()
            for i in range(round(.3*fps)):
                f.step([field.Face(.5,.5,.06,.12,0)],i/fps)
            for i in range(1,round(.1*fps)+1):
                f.step([field.Face(.5,.5,.06,.12,1)],.3-1/fps+i/fps)
            expansion=f.tracks[0].expansion
            self.assertAlmostEqual(expansion,1-math.exp(-1),places=8)
            scale=1+field.OPEN_EXPANSION_GAIN*expansion
            self.assertGreater(scale,1.)
            self.assertLess(scale,2.72)
            values.append(scale)
        self.assertLess(max(values)-min(values),1e-10)

    def test_neighbour_envelope_remains_46_percent_of_distance(self):
        f=field.FaceMorphField()
        f.step([field.Face(.43,.5,.2,.3,1),field.Face(.57,.5,.2,.3,1)],0)
        self.assertEqual(len(f.tracks),2)
        for track in f.tracks.values():track.expansion=1
        captured=[]
        original=cv2.polylines
        def capture(image,polygons,*args,**kwargs):
            captured.append(np.concatenate(polygons,axis=0))
            return original(image,polygons,*args,**kwargs)
        layout=display_utils.get_uniform_layout(1280,720,1280,720)
        with patch.object(cv2,'polylines',side_effect=capture):
            draw_meshes(np.zeros((720,1280,3),np.uint8),f,0,layout)
        self.assertEqual(len(captured),2)
        radius=(.57-.43)*1280*.46
        for track,points in zip(f.tracks.values(),captured):
            center=np.array([track.face.x*1279,track.face.y*719])
            self.assertLessEqual(np.linalg.norm(points-center,axis=1).max(),radius+2)

if __name__=='__main__':unittest.main()
