"""Execute the real scene methods without importing display, camera or GPU code."""
import ast
import math
from contextlib import ExitStack
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest import mock

import numpy as np
import minecraft_reset as reset


ROOT = Path(__file__).resolve().parents[1]


class Mesh:
    def __init__(self, geometry=None, material=None):
        self.geometry = geometry
        self.material = material or NS(color=(0.2, 0.3, 0.4, 1))
        self.local = NS(position=(0, 0, 0), rotation=(0, 0, 0, 1), scale=(1, 1, 1))
        self.visible = True


class Scene:
    def __init__(self):
        self.children = []

    def add(self, mesh):
        self.children.append(mesh)

    def remove(self, mesh):
        self.children.remove(mesh)


def load_scene():
    path = Path(os.environ.get('MINECRAFT_TEST_SOURCE', ROOT / 'minecraft.py'))
    tree = ast.parse(path.read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    gfx = NS(Mesh=Mesh, box_geometry=mock.Mock(side_effect=lambda *args: object()),
             MeshBasicMaterial=lambda **kw: NS(**kw), MeshPhongMaterial=lambda **kw: NS(**kw))
    ns = dict(ExitStack=ExitStack, math=math, np=np, gfx=gfx, BLOCK_SIZE=3.0, INTERACTION_DISTANCE=40.0,
              COLORS=[(1, 0, 0, 1), (0, 1, 0, 1)], MAX_PARTICLES=reset.MAX_PARTICLES,
              RESET_SECONDS=reset.RESET_SECONDS, TwoHandReset=reset.TwoHandReset,
              reset_sample=reset.reset_sample, la=mock.Mock(), time=mock.Mock(),
              scene_control=mock.Mock(_child_control=object()), cv2=mock.Mock())
    ns['time'].monotonic.return_value = 1.0
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    return ns


class ResetEffectTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_scene()
        self.app = self.ns['MinecraftApp'].__new__(self.ns['MinecraftApp'])
        a = self.app
        a.scene = Scene()
        a.blocks = {}
        a.particles = []
        a._reset_remaining = 0.0
        a._reset_finished_this_frame = False
        a.cursor, a.camera = Mesh(), Mesh()
        a.current_color_idx = 1
        a.camera_rot_x, a.camera_rot_y = 0.5, 0.4
        a.grabbed_block_pos = (1, 2, 3)
        a.update_hud_color = mock.Mock()
        a.gesture_manager = mock.Mock(reset_trigger=False, color_cycle_trigger=False)
        a.hand_overlay = mock.Mock()
        a.gesture_manager.reset_gesture = reset.TwoHandReset()
        a.gesture_manager.cancel_reset.side_effect = a.gesture_manager.reset_gesture.cancel

    def add_blocks(self, count):
        for i in range(count):
            self.app.create_block((i, i % 4, 0))

    def finish(self):
        self.app.update_particles(reset.RESET_SECONDS + 0.001)

    def test_single_block_bursts_into_many_shared_geometry_cubes(self):
        self.add_blocks(1)
        self.app.clear_all()
        self.assertEqual(len(self.app.particles), 48)
        self.assertFalse(self.app.blocks)
        self.assertEqual(len({id(p.mesh.geometry) for p in self.app.particles}), 1)
        self.assertTrue(all(p.spin and p.life == reset.RESET_SECONDS for p in self.app.particles))
        self.assertTrue(all(np.isfinite(p.velocity).all() for p in self.app.particles))
        self.assertTrue(any(np.linalg.norm(p.velocity) > 25 for p in self.app.particles))

    def test_many_blocks_and_old_debris_share_a_fixed_total_budget(self):
        self.add_blocks(1000)
        self.app.remove_block((0, 0, 0))
        old = [p.mesh for p in self.app.particles]
        self.app.clear_all()
        self.assertEqual(len(self.app.particles), reset.MAX_PARTICLES)
        self.assertEqual(len(self.app.scene.children), reset.MAX_PARTICLES)
        self.assertFalse(any(p in self.app.scene.children for p in old))
        self.assertFalse(self.app.blocks)
        # Spatially distributed samples cover the end as well as the start.
        self.assertGreater(max(p.pos[0] for p in self.app.particles), 2900)

    def test_repeat_clear_does_not_restart_or_allocate(self):
        self.add_blocks(4)
        self.app.clear_all()
        self.app.update_particles(0.2)
        particles = tuple(self.app.particles)
        remaining = self.app._reset_remaining
        self.app.clear_all()
        self.assertEqual(tuple(self.app.particles), particles)
        self.assertEqual(self.app._reset_remaining, remaining)

    def test_finish_clears_state_then_blocks_can_be_built_again(self):
        self.add_blocks(5)
        self.app.clear_all()
        self.finish()
        self.assertFalse(self.app.particles)
        self.assertFalse(self.app.scene.children)
        self.assertIsNone(self.app.grabbed_block_pos)
        self.assertEqual(self.app.current_color_idx, 0)
        self.assertEqual((self.app.camera_rot_x, self.app.camera_rot_y), (0, 0))
        self.assertEqual(self.app.camera.local.position, (0, 0, 50))
        self.assertFalse(self.app.cursor.visible)
        self.assertFalse(self.app.gesture_manager.reset_gesture.armed)
        self.app.update_hud_color.assert_called_once()
        self.app.create_block((2, 3, 4))
        self.assertIn((2, 3, 4), self.app.blocks)
        self.app.clear_all()
        self.assertEqual(len(self.app.particles), 48)

    def test_empty_reset_finishes_cleanly(self):
        self.app.clear_all()
        self.assertFalse(self.app.particles)
        self.finish()
        self.assertEqual(self.app._reset_remaining, 0)

    def test_regular_erase_particles_are_also_capped_and_expire(self):
        self.add_blocks(40)
        for key in list(self.app.blocks):
            self.app.remove_block(key)
        self.assertEqual(len(self.app.particles), reset.MAX_PARTICLES)
        self.app.update_particles(1.01)
        self.assertFalse(self.app.scene.children)
        self.assertFalse(self.app.particles)

    def test_particle_motion_and_shrink_are_finite_after_a_slow_frame(self):
        self.add_blocks(1)
        self.app.clear_all()
        before = self.app.particles[0].pos.copy()
        self.app.update_particles(1.0)
        particle = self.app.particles[0]
        self.assertLess(np.linalg.norm(particle.pos - before), 4)
        self.assertLess(particle.mesh.local.scale[0], 1)
        self.assertTrue(np.isfinite(particle.pos).all())
        self.app.update_particles(0.3)
        self.assertFalse(self.app.particles)

    def frame_ready(self):
        a = self.app
        a.last_time = 0.95
        a._camera_failure_since = None
        a._last_frame_id = None
        a._last_fresh_at = 1
        a.cap = mock.Mock(last_read_frame_id=1)
        a.cap.read.return_value = (True, object())
        a.canvas, a.renderer, a.bg_tex = mock.Mock(), mock.Mock(), mock.MagicMock()
        a.update_camera = mock.Mock()
        a.get_world_pos_from_screen = mock.Mock(return_value=(0, 0, 0))
        a.gesture_manager.process.return_value = {
            'left_hand': {'pos': (0.9, 0.9)},
            'right_hand': {'pos': (0.5, 0.5), 'action': 'create'}}

    def test_reset_frame_and_animation_ignore_normal_inputs(self):
        self.add_blocks(2)
        self.frame_ready()
        self.app.gesture_manager.reset_trigger = True
        self.app.gesture_manager.color_cycle_trigger = True
        self.app._animate_frame()
        self.assertFalse(self.app.blocks)
        self.app.update_camera.assert_not_called()
        self.assertFalse(self.app.cursor.visible)
        self.assertEqual(self.app.current_color_idx, 1)
        self.app.gesture_manager.reset_trigger = False
        self.app.cap.last_read_frame_id = 2
        self.ns['time'].monotonic.return_value = 1.1
        self.app._animate_frame()
        self.assertFalse(self.app.blocks)
        self.assertFalse(self.app.gesture_manager.reset_gesture.armed)

    def test_armed_opening_suppresses_partial_pointing_without_reset(self):
        self.frame_ready()
        self.app.gesture_manager.reset_gesture.armed = True
        self.app._animate_frame()
        self.assertFalse(self.app.blocks)
        self.assertEqual(self.app._reset_remaining, 0)
        self.app.update_camera.assert_not_called()

    def test_read_failure_cancels_arm_and_no_detection_is_run(self):
        self.frame_ready()
        self.app.gesture_manager.reset_gesture.armed = True
        self.app.cap.read.return_value = (False, None)
        self.app._animate_frame()
        self.assertFalse(self.app.gesture_manager.reset_gesture.armed)
        self.app.gesture_manager.process.assert_not_called()

    def test_duplicate_shared_frame_does_not_advance_gesture(self):
        self.frame_ready()
        self.app._last_frame_id = 1
        self.app.gesture_manager.reset_gesture.armed = True
        self.app._animate_frame()
        self.app.gesture_manager.process.assert_not_called()
        self.assertTrue(self.app.gesture_manager.reset_gesture.armed)

    def test_completion_frame_ignores_inputs_then_normal_build_resumes(self):
        self.add_blocks(1)
        self.app.clear_all()
        self.frame_ready()
        self.app.last_time = 0
        self.ns['time'].monotonic.return_value = 2
        self.app._animate_frame()
        self.assertFalse(self.app.blocks)
        self.assertFalse(self.app.particles)
        self.app.cap.last_read_frame_id = 2
        self.ns['time'].monotonic.return_value = 2.03
        self.app._animate_frame()
        self.assertIn((0, 0, 0), self.app.blocks)

    def test_completion_waits_for_fresh_render_after_camera_wait(self):
        for missing in (False, True):
            with self.subTest(read_failure=missing):
                self.setUp()
                self.add_blocks(1)
                self.app.clear_all()
                self.frame_ready()
                self.app.last_time = 0
                self.app._last_frame_id = 1
                if missing:
                    self.app.cap.read.return_value = (False, None)
                self.ns['time'].monotonic.return_value = 2
                self.app._animate_frame()
                self.assertTrue(self.app._reset_finished_this_frame)
                # Only erase stale hand feedback; this is not a fresh input/render
                # acknowledgement and must not unlock the reset completion frame.
                self.app.hand_overlay.clear.assert_called_once()
                self.assertEqual(self.app.renderer.render.call_count, 2)
                self.ns['scene_control'].notify_first_frame.assert_not_called()
                self.app.cap.read.return_value = (True, object())
                self.app.cap.last_read_frame_id = 2
                self.ns['time'].monotonic.return_value = 2.03
                self.app._animate_frame()
                self.assertFalse(self.app.blocks)
                self.assertFalse(self.app._reset_finished_this_frame)


class GestureIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_scene()
        self.gm = self.ns['GestureManager'].__new__(self.ns['GestureManager'])
        self.gm.hands, self.gm.face_mesh = mock.Mock(), mock.Mock()
        self.gm.mouth_state = 'closed'
        self.gm.color_cycle_trigger = False
        self.gm.reset_trigger = False
        self.gm.reset_gesture = reset.TwoHandReset()
        self.gm.is_pointing = mock.Mock(return_value=False)
        self.gm.is_palm_open = mock.Mock(return_value=False)
        self.image = NS(shape=(480, 640, 3))

    @staticmethod
    def hand(x, shape):
        points = [NS(x=x, y=0.65, z=0) for _ in range(21)]
        points[9].y = 0.55
        for tip, pip in zip((8, 12, 16, 20), (6, 10, 14, 18)):
            points[pip].y = 0.50
            points[tip].y = 0.60 if shape == 'fist' else 0.35
        points[17].x = x + 0.06
        points[3].x = x - 0.01
        points[4].x = x + 0.02 if shape == 'fist' else x - 0.16
        return NS(landmark=points)

    def frame(self, now, shape, *, missing=False, reverse=False):
        hands = [self.hand(0.3, shape), self.hand(0.7, shape)]
        labels = [NS(classification=[NS(label=label, score=0.99)]) for label in ('Left', 'Right')]
        if reverse:
            hands.reverse()
            labels.reverse()
        if missing:
            hands, labels = hands[:1], labels[:1]
        self.gm.hands.process.return_value = NS(multi_hand_landmarks=hands, multi_handedness=labels)
        self.gm.face_mesh.process.return_value = NS(multi_face_landmarks=[
            NS(landmark=[NS(x=0.5, y=0.35, z=0) for _ in range(15)])])
        self.ns['time'].monotonic.return_value = now
        self.gm.process(self.image)
        return self.gm.reset_trigger

    def arm(self):
        for now in (0, 0.1, 0.2, 0.35):
            self.assertFalse(self.frame(now, 'fist', reverse=now == 0.2))

    def test_real_process_emits_one_event_and_detection_order_does_not_change_pair(self):
        self.arm()
        self.assertFalse(self.frame(0.4, 'palm', reverse=True))
        self.assertTrue(self.frame(0.52, 'palm'))
        self.assertFalse(self.frame(0.60, 'palm'))

    def test_short_hand_loss_in_real_process_invalidates_prior_fists(self):
        self.arm()
        self.assertFalse(self.frame(0.38, 'fist', missing=True))
        self.assertFalse(self.frame(0.4, 'palm'))
        self.assertFalse(self.frame(0.52, 'palm'))

    def test_camera_cancel_blocks_recovery_even_inside_sample_gap(self):
        self.arm()
        self.gm.cancel_reset()
        self.assertFalse(self.frame(0.4, 'palm'))
        self.assertFalse(self.frame(0.52, 'palm'))


if __name__ == '__main__':
    unittest.main()
