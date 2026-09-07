import unittest
from unittest import mock

from transition_overlay import CurtainCamera


class CurtainCameraTests(unittest.TestCase):
    def test_camera_appears_only_after_cover_and_fades_in(self):
        layer = CurtainCamera()
        pygame, frame = mock.MagicMock(), mock.MagicMock()
        for state in ("idle", "covering"):
            layer.update(pygame, (1.0, frame), state, 1.0)
            self.assertEqual(layer.opacity, 0)
        pygame.surfarray.make_surface.assert_not_called()
        layer.update(pygame, (1.05, frame), "covered", 1.05)
        self.assertGreater(layer.opacity, 0)
        self.assertLess(layer.opacity, 96)
        for tick in range(2, 11):
            stamp = 1.0 + tick * .05
            layer.update(pygame, (stamp, frame), "covered", stamp)
        self.assertEqual(layer.opacity, 96)

    def test_reveal_fades_out_and_idle_releases_image(self):
        layer = CurtainCamera()
        pygame, frame = mock.MagicMock(), mock.MagicMock()
        layer.opacity, layer.last_tick = 96, 1.0
        layer.update(pygame, (1.05, frame), "revealing", 1.05)
        self.assertGreater(layer.opacity, 0)
        self.assertLess(layer.opacity, 96)
        layer.update(pygame, (1.1, frame), "idle", 1.1)
        self.assertEqual(layer.opacity, 0)
        self.assertIsNone(layer.surface)

    def test_stale_or_missing_camera_never_leaves_a_frozen_image(self):
        for snapshot in ((1.0, mock.MagicMock()), (None, None)):
            layer = CurtainCamera()
            layer.opacity, layer.surface = 96, mock.Mock()
            layer.update(mock.Mock(), snapshot, "covered", 2.0)
            self.assertEqual(layer.opacity, 0)
            self.assertIsNone(layer.surface)

    def test_same_snapshot_reuses_surface_and_drawing_restores_clip(self):
        layer = CurtainCamera()
        pygame, frame = mock.MagicMock(), mock.MagicMock()
        layer.last_tick = 1.0
        layer.update(pygame, (1.05, frame), "covered", 1.05)
        layer.update(pygame, (1.05, frame), "covered", 1.1)
        pygame.surfarray.make_surface.assert_called_once()
        screen = mock.Mock()
        screen.blit.side_effect = RuntimeError("draw failed")
        with self.assertRaises(RuntimeError):
            layer.draw(screen, (0, 0, 100, 100))
        self.assertEqual(screen.set_clip.call_args.args, (screen.get_clip.return_value,))
