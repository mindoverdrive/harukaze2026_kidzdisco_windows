import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
import pygfx as gfx
import display_utils


class SaturnProjectionTests(unittest.TestCase):
    def test_landmark_projects_to_navigation_pixel(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'saturn_particles_2.py').read_text(encoding='utf-8-sig'))
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_landmark_to_world')
        namespace=dict(np=np, math=math, display_utils=display_utils,WINDOW_WIDTH=1920,WINDOW_HEIGHT=1080,CAMERA_FOV=70.)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<projection>','exec'),namespace)
        camera=gfx.PerspectiveCamera(70,1920/1080)
        camera.local.z=1200
        camera.set_view_size(1920,1080)
        instance=SimpleNamespace(camera=camera)
        layout=display_utils.get_uniform_layout(1280,720,1920,1080)
        for x,y in ((.1,.1),(.5,.5),(.9,.1),(.9,.9)):
            world,expected=namespace['_landmark_to_world'](instance,SimpleNamespace(x=x,y=y,z=-.1),layout)
            clip=camera.projection_matrix @ np.array([world[0],world[1],world[2]-1200,1])
            ndc=clip[:2]/clip[3]
            pixel=((ndc[0]+1)*960,(1-ndc[1])*540)
            np.testing.assert_allclose(pixel,expected,atol=.01)
