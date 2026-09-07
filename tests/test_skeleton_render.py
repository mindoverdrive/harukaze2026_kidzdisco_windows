import ast
import colorsys
import math
from pathlib import Path
import random
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

from skeleton_people import Body

try:
    import numpy as np
    if not isinstance(np, ModuleType):
        raise ImportError("Real numpy required")
    import pygame
    REAL_GRAPHICS = isinstance(getattr(pygame, "__file__", None), str) and not isinstance(pygame.Surface, mock.Mock)
except ImportError:
    REAL_GRAPHICS = False


@unittest.skipUnless(REAL_GRAPHICS, "Real pygame/numpy are required for pixel tests")
class PixelTests(unittest.TestCase):
    def setUp(self):
        self.scene = ModuleType("skeleton_pixel_target")
        self.scene.__dict__.update(math=math, colorsys=colorsys, random=random, pygame=pygame,
                                  display_utils=SimpleNamespace(normalized_to_stage=lambda x,y,layout:
                                      (round(layout[0]+x*layout[2]),round(layout[1]+y*layout[3]))))
        path=Path(__file__).resolve().parents[1]/"skeleton_glitch.py"
        tree=ast.parse(path.read_text(encoding="utf-8"))
        nodes=[node for node in tree.body if isinstance(node,(ast.Assign,ast.FunctionDef))]
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),"exec"),self.scene.__dict__)
        self.surface=pygame.Surface((640,480))
        self.layout=(0,0,640,480)

    def test_still_body_has_exact_gray_two_pixel_line_white_points_and_black_background(self):
        body=Body(0,((.25,.5),(.75,.5)),(0,0))
        self.scene.draw_skeletons(self.surface,[body],self.layout,((0,1),),0)
        pixels=pygame.surfarray.array3d(self.surface)
        self.assertEqual(tuple(pixels[320,240]),(200,200,200))
        self.assertEqual(int(np.all(pixels[320]==(200,200,200),axis=1).sum()),2)
        self.assertEqual(tuple(pixels[160,240]),(255,255,255))
        self.assertEqual(tuple(pixels[480,240]),(255,255,255))
        self.assertEqual(tuple(pixels[0,0]),(0,0,0))
        self.scene.draw_skeletons(self.surface,[body],self.layout,((0,1),),22.5)
        np.testing.assert_array_equal(pixels,pygame.surfarray.array3d(self.surface))

    def test_ghost_is_dim_expires_and_cannot_obscure_current_line(self):
        body=Body(0,((.25,.5),(.75,.5)),(0,0),((0,((.25,.4),(.75,.4))),))
        self.scene.draw_skeletons(self.surface,[body],self.layout,((0,1),),.05)
        pixels=pygame.surfarray.array3d(self.surface)
        self.assertTrue(0 < max(pixels[320,192]) <= 48)
        self.assertEqual(tuple(pixels[320,240]),(200,200,200))
        self.scene.draw_skeletons(self.surface,[body],self.layout,((0,1),),.5)
        self.assertEqual(tuple(pygame.surfarray.array3d(self.surface)[320,192]),(0,0,0))

    def test_motion_glitch_is_colored_and_stage_layout_is_used(self):
        body=Body(0,((.25,.5),(.75,.5)),(.03,.03))
        self.scene.draw_skeletons(self.surface,[body],(100,40,400,300),((0,1),),0,random.Random(1))
        pixels=pygame.surfarray.array3d(self.surface)
        self.assertGreater(int(np.any(pixels[:,:,0]!=pixels[:,:,1],axis=0).sum()),0)
        self.assertTrue(np.any(pixels[170:430,170:210]))
        self.assertFalse(np.any(pixels[:100]))


if __name__ == "__main__":
    unittest.main()
