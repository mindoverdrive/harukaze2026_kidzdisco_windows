"""Offline regressions for the manual three-logo preview.

Controller checks use synthetic time. Rendering uses CPU surfaces only; camera
checks inject a fake capture. No test starts a window or a physical camera.
"""

import sys
import socket
import struct
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

try:
    import numpy as np
    import pygame
    REAL_GRAPHICS = (
        isinstance(np, ModuleType) and isinstance(pygame, ModuleType)
        and isinstance(getattr(np, "__version__", None), str)
        and isinstance(getattr(pygame, "__file__", None), str)
        and not isinstance(getattr(pygame, "Surface", None), mock.Mock)
    )
except ImportError:
    np = pygame = None
    REAL_GRAPHICS = False

from scripts import preview_transition_logos as preview
from transition_overlay import TRANSPARENT_COLOR


class PreviewControllerTests(unittest.TestCase):
    def setUp(self):
        self.controller = preview.PreviewController(now=0.0)

    def present(self, now):
        self.controller.curtain.advance(now)
        ack = self.controller.curtain.presented()
        self.controller.presented(ack, now)
        return ack

    def cover(self):
        self.assertEqual(self.present(2.0), "COVERED")
        self.assertEqual(self.controller.curtain.state, "covered")

    def test_order_starts_with_asobi_and_fixed_choice_does_not_draw_randomly(self):
        self.assertEqual(preview.ORDER, (("asobi_tune", "あそびTUNE"),
                                        ("colony", "Colony"),
                                        ("tokyo_island", "TOKYO ISLAND")))
        self.assertEqual(self.controller.index, 0)
        self.assertEqual(self.controller.selector.brand, "asobi_tune")
        self.assertEqual(self.controller.curtain.state, "covering")
        self.assertEqual(self.controller.curtain.cover_duration, 1.2)
        self.assertEqual(self.controller.curtain.reveal_duration, 1.6)
        self.assertIsNone(self.controller.pending)
        self.assertTrue(self.controller.running)
        for brand, _label in preview.ORDER:
            self.controller.selector.brand = brand
            self.assertEqual(self.controller.selector.choices(
                ("colony", "tokyo_island", "asobi_tune"), weights=(1, 1, 2), k=1),
                [brand])

    def test_busy_actions_are_discarded_and_quit_remains_available(self):
        before = (self.controller.index, self.controller.selector.brand,
                  self.controller.pending, self.controller.curtain.cycle)
        for action in ("next", "back", "replay", "camera"):
            self.assertFalse(self.controller.action(action, 0.2), action)
            self.assertEqual((self.controller.index, self.controller.selector.brand,
                              self.controller.pending, self.controller.curtain.cycle), before)
        self.assertTrue(self.controller.action("quit", 0.3))
        self.assertFalse(self.controller.running)

    def test_next_keeps_current_brand_until_reveal_is_presented(self):
        self.cover()
        previous_cycle = self.controller.curtain.cycle
        self.assertTrue(self.controller.action("next", 3.0))
        self.assertEqual(self.controller.pending, 1)
        self.assertEqual(self.controller.curtain.state, "revealing")
        self.assertEqual(self.controller.index, 0)
        self.assertEqual(self.controller.selector.brand, "asobi_tune")
        self.assertIsNone(self.present(3.8))
        self.assertEqual(self.controller.index, 0)
        for action in ("next", "back", "replay", "camera"):
            self.assertFalse(self.controller.action(action, 3.9))
        self.assertEqual(self.controller.pending, 1)
        self.assertEqual(self.present(5.0), "REVEALED")
        self.assertEqual(self.controller.index, 1)
        self.assertEqual(self.controller.selector.brand, "colony")
        self.assertIsNone(self.controller.pending)
        self.assertEqual(self.controller.curtain.state, "covering")
        self.assertGreater(self.controller.curtain.cycle, previous_cycle)

    def test_boundaries_do_not_wrap_and_back_can_return_to_index_zero(self):
        self.cover()
        self.assertFalse(self.controller.action("back", 2.1))
        self.assertEqual(self.controller.curtain.state, "covered")
        for action_time, reveal_time, cover_time in ((3.0, 5.0, 7.0), (8.0, 10.0, 12.0)):
            self.assertTrue(self.controller.action("next", action_time))
            self.assertEqual(self.present(reveal_time), "REVEALED")
            self.assertEqual(self.present(cover_time), "COVERED")
        self.assertEqual(self.controller.index, 2)
        self.assertEqual(self.controller.selector.brand, "tokyo_island")
        self.assertFalse(self.controller.action("next", 12.1))
        self.assertEqual(self.controller.curtain.state, "covered")
        for action_time, reveal_time, cover_time in ((13.0, 15.0, 17.0), (18.0, 20.0, 22.0)):
            self.assertTrue(self.controller.action("back", action_time))
            self.assertEqual(self.present(reveal_time), "REVEALED")
            self.assertEqual(self.present(cover_time), "COVERED")
        self.assertEqual(self.controller.index, 0)
        self.assertEqual(self.controller.selector.brand, "asobi_tune")

    def test_replay_of_first_logo_treats_zero_as_a_pending_target(self):
        self.cover()
        cycle = self.controller.curtain.cycle
        self.assertTrue(self.controller.action("replay", 3.0))
        self.assertEqual(self.controller.pending, 0)
        self.assertEqual(self.present(5.0), "REVEALED")
        self.assertEqual(self.controller.index, 0)
        self.assertEqual(self.controller.selector.brand, "asobi_tune")
        self.assertEqual(self.controller.curtain.state, "covering")
        self.assertGreater(self.controller.curtain.cycle, cycle)

    def test_camera_reveals_to_idle_and_cover_preserves_the_selected_logo(self):
        self.cover()
        self.assertTrue(self.controller.action("camera", 3.0))
        self.assertIsNone(self.controller.pending)
        self.assertEqual(self.present(5.0), "REVEALED")
        self.assertEqual(self.controller.curtain.state, "idle")
        self.assertEqual(self.controller.index, 0)
        self.assertIsNone(self.present(20.0))
        self.assertEqual(self.controller.curtain.state, "idle")
        self.assertTrue(self.controller.action("camera", 21.0))
        self.assertEqual(self.controller.curtain.state, "covering")
        self.assertEqual(self.controller.index, 0)

    def test_idle_next_and_back_begin_the_requested_cover_immediately(self):
        self.cover()
        self.controller.action("camera", 3.0)
        self.present(5.0)
        self.assertFalse(self.controller.action("back", 5.1))
        self.assertEqual(self.controller.curtain.state, "idle")
        self.assertTrue(self.controller.action("next", 6.0))
        self.assertEqual(self.controller.index, 1)
        self.assertEqual(self.controller.selector.brand, "colony")
        self.assertEqual(self.controller.curtain.state, "covering")
        self.assertIsNone(self.controller.pending)
        self.present(8.0)
        self.controller.action("camera", 9.0)
        self.present(11.0)
        self.assertTrue(self.controller.action("back", 12.0))
        self.assertEqual(self.controller.index, 0)
        self.assertEqual(self.controller.curtain.state, "covering")

    def test_idle_replay_covers_the_same_logo(self):
        self.cover()
        self.controller.action("camera", 3.0)
        self.present(5.0)
        self.assertTrue(self.controller.action("replay", 6.0))
        self.assertEqual(self.controller.index, 0)
        self.assertEqual(self.controller.selector.brand, "asobi_tune")
        self.assertEqual(self.controller.curtain.state, "covering")


@unittest.skipUnless(REAL_GRAPHICS, "Real pygame and numpy required for CPU surface checks")
class PreviewRendererTests(unittest.TestCase):
    SIZE = (320, 180)

    def setUp(self):
        self.controller = preview.PreviewController(now=0.0)
        self.renderer = preview.Renderer(pygame, self.SIZE, self.controller)
        self.background = pygame.Surface(self.SIZE)
        self.background.fill((13, 47, 83))

    def assert_pixels_equal(self, actual, expected):
        self.assertEqual(pygame.image.tobytes(actual, "RGB"), pygame.image.tobytes(expected, "RGB"))

    def test_opacity_is_applied_once_without_mutating_stage_pixels(self):
        self.renderer.stage.fill((255, 255, 255))
        self.renderer.opacity.value = 128
        self.background.fill((0, 0, 0))
        before = pygame.image.tobytes(self.renderer.stage, "RGB")
        result = self.renderer.compose(self.background)
        for value in tuple(result.get_at((100, 100)))[:3]:
            self.assertTrue(127 <= value <= 129, value)
        self.assertIn(self.renderer.stage.get_alpha(), (None, 255))
        self.assertEqual(pygame.image.tobytes(self.renderer.stage, "RGB"), before)
        self.assertEqual(tuple(self.background.get_at((100, 100)))[:3], (0, 0, 0))

    def test_colorkey_holes_reveal_background_without_erasing_white_artwork(self):
        self.renderer.stage.fill(TRANSPARENT_COLOR)
        self.renderer.stage.set_at((10, 10), (255, 255, 255))
        self.renderer.opacity.value = 255
        result = self.renderer.compose(self.background)
        self.assertEqual(tuple(result.get_at((20, 20)))[:3], (13, 47, 83))
        self.assertEqual(tuple(result.get_at((10, 10)))[:3], (255, 255, 255))

    def test_zero_opacity_returns_the_background_with_no_logo_residue(self):
        self.renderer.stage.fill((240, 80, 20))
        self.renderer.opacity.value = 0
        self.assert_pixels_equal(self.renderer.compose(self.background), self.background)

    def test_missing_each_required_asset_is_reported_instead_of_silent_fallback(self):
        self.renderer.check_assets()
        for owner, attribute, unavailable in (
            (self.renderer.logo, "asobi", None),
            (self.renderer.logo, "tokyo", None),
            (self.renderer.logo.colony, "available", False),
            (self.renderer.particles, "available", False),
        ):
            with self.subTest(attribute=attribute), mock.patch.object(owner, attribute, unavailable):
                with self.assertRaises(RuntimeError):
                    self.renderer.check_assets()

    def test_next_brand_changes_only_after_revealed_pixels_are_flipped(self):
        self.renderer.draw(2.0, self.background, flip=lambda _surface: None)
        self.assertEqual(self.controller.curtain.state, "covered")
        self.controller.action("next", 3.0)
        seen = []

        def flip(surface):
            seen.append((self.controller.index, self.controller.selector.brand,
                         self.controller.curtain.state))
            self.assert_pixels_equal(surface, self.background)

        result = self.renderer.draw(5.0, self.background, flip=flip)
        self.assertEqual(seen, [(0, "asobi_tune", "revealing")])
        self.assert_pixels_equal(result, self.background)
        self.assertEqual(self.controller.index, 1)
        self.assertEqual(self.controller.selector.brand, "colony")
        self.assertEqual(self.controller.curtain.state, "covering")

    def test_failed_flip_keeps_old_brand_and_pending_target_until_retry(self):
        self.renderer.draw(2.0, self.background, flip=lambda _surface: None)
        self.controller.action("next", 3.0)
        with self.assertRaisesRegex(RuntimeError, "present failed"):
            self.renderer.draw(5.0, self.background,
                               flip=mock.Mock(side_effect=RuntimeError("present failed")))
        self.assertEqual(self.controller.index, 0)
        self.assertEqual(self.controller.selector.brand, "asobi_tune")
        self.assertEqual(self.controller.pending, 1)
        self.assertEqual(self.controller.curtain.state, "revealing")
        self.renderer.draw(5.1, self.background, flip=lambda _surface: None)
        self.assertEqual(self.controller.index, 1)
        self.assertEqual(self.controller.curtain.state, "covering")


class PreviewCameraSourceTests(unittest.TestCase):
    def setUp(self):
        self.capture = mock.Mock()
        self.capture.isOpened.return_value = True
        self.factory = mock.Mock(return_value=self.capture)
        self.clock = mock.Mock(return_value=10.0)
        self.source = preview.CameraSource(2, capture_factory=self.factory, clock=self.clock)
        self.native_capture = mock.Mock(side_effect=AssertionError("Physical capture forbidden"))
        self.cv2 = SimpleNamespace(CAP_DSHOW=700, VideoCapture=self.native_capture)

    def run_worker(self):
        with mock.patch.dict(sys.modules, {"cv2": self.cv2}):
            self.source._run()
        self.native_capture.assert_not_called()
        self.capture.set.assert_not_called()

    def test_construction_snapshot_and_close_do_not_open_a_camera(self):
        self.factory.assert_not_called()
        frame, status = self.source.snapshot(now=10.0)
        self.assertIsNone(frame)
        self.assertIsInstance(status, str)
        self.assertTrue(status)
        self.source.close()
        self.assertTrue(self.source._stop.is_set())
        self.factory.assert_not_called()
        self.capture.release.assert_not_called()

    def test_worker_publishes_a_copy_and_stale_or_future_frames_are_hidden(self):
        copied = object()
        frame = mock.Mock()
        frame.copy.return_value = copied

        def read_once():
            self.source._stop.set()
            return True, frame

        self.capture.read.side_effect = read_once
        self.run_worker()
        self.factory.assert_called_once_with(2, self.cv2.CAP_DSHOW)
        self.capture.read.assert_called_once()
        self.capture.release.assert_called_once()
        frame.copy.assert_called_once_with()
        fresh, status = self.source.snapshot(now=10.5)
        self.assertIs(fresh, copied)
        self.assertIsInstance(status, str)
        self.assertTrue(status)
        for now in (11.001, 9.9):
            with self.subTest(now=now):
                stale, status = self.source.snapshot(now=now)
                self.assertIsNone(stale)
                self.assertIsInstance(status, str)
                self.assertTrue(status)
        self.source.close()
        self.capture.release.assert_called_once()

    def test_unavailable_camera_is_released_without_reading_or_reopening(self):
        self.capture.isOpened.return_value = False
        self.run_worker()
        self.factory.assert_called_once_with(2, self.cv2.CAP_DSHOW)
        self.capture.read.assert_not_called()
        self.capture.release.assert_called_once()
        frame, status = self.source.snapshot(now=10.0)
        self.assertIsNone(frame)
        self.assertIsInstance(status, str)
        self.assertTrue(status)

    def test_read_failure_discards_a_previously_published_frame(self):
        frame = mock.Mock()
        frame.copy.return_value = object()
        self.capture.read.side_effect = [(True, frame), (False, None)]
        self.run_worker()
        self.assertEqual(self.capture.read.call_count, 2)
        self.factory.assert_called_once()
        self.capture.release.assert_called_once()
        result, status = self.source.snapshot(now=10.0)
        self.assertIsNone(result)
        self.assertIsInstance(status, str)
        self.assertTrue(status)

    def test_capture_construction_failure_is_reported_without_retry(self):
        self.factory.side_effect = OSError("injected capture failure")
        self.run_worker()
        self.factory.assert_called_once()
        self.capture.read.assert_not_called()
        self.capture.release.assert_not_called()
        frame, status = self.source.snapshot(now=10.0)
        self.assertIsNone(frame)
        self.assertIn("injected capture failure", status)

    def test_close_requests_owner_stop_and_uses_a_bounded_join(self):
        self.source._thread = mock.Mock()
        self.source._thread.is_alive.return_value = True
        self.source.close()
        self.assertTrue(self.source._stop.is_set())
        self.source._thread.join.assert_called_once()
        timeout = self.source._thread.join.call_args.kwargs["timeout"]
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 1.0)
        self.factory.assert_not_called()
        self.capture.release.assert_not_called()


    def test_snapshot_reads_clock_after_lock_so_a_new_publication_is_not_future(self):
        published = object()
        lock = mock.MagicMock()

        def publish_on_lock():
            self.source._frame = published
            self.source._stamp = 10.1
            self.source._status = "Camera live"
            self.clock.return_value = 10.2

        lock.__enter__.side_effect = publish_on_lock
        self.source._lock = lock
        frame, _status = self.source.snapshot()
        self.assertIs(frame, published)
        self.clock.assert_called_once_with()
        self.factory.assert_not_called()


@unittest.skipUnless(REAL_GRAPHICS, "Real pygame required for offscreen selector layout")
class PreviewCameraSelectionTests(unittest.TestCase):
    def test_click_before_first_layout_is_safe_and_selection_never_opens_capture(self):
        window = pygame.Surface((640, 480))
        font = mock.Mock()
        font.render.side_effect = lambda *_args: pygame.Surface((200, 20))
        events = [
            [SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(30, 120))],
            [SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_RETURN)],
        ]
        with (mock.patch.object(preview, "enumerate_cameras", return_value=["Fake camera"]),
              mock.patch.object(preview, "CameraSource") as source,
              mock.patch.object(preview, "ui_font", return_value=font),
              mock.patch.object(pygame.event, "get", side_effect=events),
              mock.patch.object(pygame.display, "flip") as flip):
            result = preview.select_camera(pygame, window, font, mock.Mock())
        self.assertEqual(result, (True, 0, "0: Fake camera"))
        source.assert_not_called()
        flip.assert_called_once()


class PreviewLiveFlowTests(unittest.TestCase):
    def run_mock_ui(self, selection, *, owner_active=False, camera_names=None, enumerate_failure=None,
                    clock_values=None):
        """The live function runs with every window, capture and Win32 call mocked."""
        constants = ("QUIT", "KEYDOWN", "MOUSEBUTTONDOWN", "K_RIGHT", "K_n", "K_RETURN",
                     "K_LEFT", "K_b", "K_SPACE", "K_r", "K_c", "K_ESCAPE", "K_q")
        pg = SimpleNamespace(**{name: index for index, name in enumerate(constants)})
        pg.display = mock.Mock()
        pg.time = SimpleNamespace(Clock=mock.Mock(return_value=mock.Mock()))
        pg.event = SimpleNamespace(get=mock.Mock(return_value=[]))
        user32 = mock.Mock()

        def work_area(_action, _size, pointer, _flags):
            rect = pointer._obj
            rect.left, rect.top, rect.right, rect.bottom = 0, 0, 1280, 900
            return True

        user32.SystemParametersInfoW.side_effect = work_area
        source = mock.Mock()
        source.snapshot.return_value = (None, "Camera unavailable")
        renderer = mock.Mock()
        controller_box = []

        def make_renderer(_pg, _size, controller):
            controller_box.append(controller)
            return renderer

        def draw_once(_now, _background, _flip):
            controller_box[0].running = False

        renderer.draw.side_effect = draw_once
        with (mock.patch("ctypes.windll", SimpleNamespace(user32=user32), create=True),
              mock.patch.object(preview, "select_camera", return_value=selection),
              mock.patch.object(preview, "production_camera_active", return_value=owner_active) as guard,
              mock.patch.object(preview, "enumerate_cameras", return_value=(
                  ["Other 0", "Other 1", "Fake"] if camera_names is None else camera_names),
                  side_effect=enumerate_failure) as enumerate_mock,
              mock.patch.object(preview, "CameraSource", return_value=source) as source_factory,
              mock.patch.object(preview, "Renderer", side_effect=make_renderer),
              mock.patch.object(preview, "checker", return_value=object()),
              mock.patch.object(preview, "ui_font", return_value=mock.Mock()),
              mock.patch.object(preview.time, "monotonic", return_value=0.0, side_effect=clock_values)):
            preview.run_live(pg)
        return SimpleNamespace(source=source, factory=source_factory, guard=guard,
                               enumeration=enumerate_mock, renderer=renderer, controllers=controller_box)

    def test_cancelled_selection_does_not_construct_a_camera_or_query_owner(self):
        result = self.run_mock_ui((False, None, ""))
        result.factory.assert_not_called()
        result.guard.assert_not_called()
        result.enumeration.assert_not_called()

    def test_existing_production_owner_keeps_preview_on_synthetic_background(self):
        result = self.run_mock_ui((True, 2, "2: Fake"), owner_active=True)
        result.guard.assert_called_once_with()
        result.factory.assert_not_called()
        result.source.start.assert_not_called()
        result.renderer.draw.assert_called_once()

    def test_confirmed_camera_uses_snapshot_current_time_and_closes_on_exit(self):
        result = self.run_mock_ui((True, 2, "2: Fake"))
        result.factory.assert_called_once_with(2)
        result.source.start.assert_called_once_with()
        # Passing the earlier UI-loop now would reintroduce the clock race.
        result.source.snapshot.assert_called_once_with()
        result.source.close.assert_called_once_with()

    def test_changed_device_list_does_not_open_the_old_index(self):
        result = self.run_mock_ui((True, 2, "2: Fake"), camera_names=["Other 0", "Other 1", "Changed"])
        result.enumeration.assert_called_once_with()
        result.factory.assert_not_called()
        result.renderer.draw.assert_called_once()

    def test_device_enumeration_failure_keeps_synthetic_preview_available(self):
        result = self.run_mock_ui((True, 2, "2: Fake"), enumerate_failure=OSError("unplugged"))
        result.enumeration.assert_called_once_with()
        result.factory.assert_not_called()
        result.renderer.draw.assert_called_once()

    def test_initial_cover_is_not_consumed_by_preparation_time(self):
        result = self.run_mock_ui((True, None, "Synthetic"), clock_values=[100.0, 100.016])
        drawn_at = result.renderer.draw.call_args.args[0]
        self.assertAlmostEqual(drawn_at, .016)
        self.assertLess(result.controllers[0].curtain.advance(drawn_at), .01)


class PreviewProductionGuardTests(unittest.TestCase):
    @staticmethod
    def table(*rows):
        return struct.pack("<I", len(rows)) + b"".join(struct.pack("<6I", *row) for row in rows)

    def test_tcp_table_requires_listen_state_and_the_network_order_production_port(self):
        listener = (2, 0, socket.htons(8766), 0, 0, 123)
        other_port = (2, 0, socket.htons(8765), 0, 0, 124)
        established = (5, 0, socket.htons(8766), 0, 0, 125)
        self.assertTrue(preview._table_has_production_listener(self.table(other_port, listener)))
        self.assertFalse(preview._table_has_production_listener(self.table(other_port, established)))
        self.assertFalse(preview._table_has_production_listener(self.table()))

    def test_truncated_tcp_table_is_rejected(self):
        listener = (2, 0, socket.htons(8766), 0, 0, 123)
        for data in (b"", self.table(listener)[:-1], struct.pack("<I", 2) + self.table(listener)[4:]):
            with self.subTest(length=len(data)), self.assertRaises((ValueError, struct.error)):
                preview._table_has_production_listener(data)

    def test_listener_guard_returns_before_querying_process_handles(self):
        with (mock.patch.object(preview, "_production_port_active", return_value=True),
              mock.patch("ctypes.WinDLL", side_effect=AssertionError("No kernel lookup expected"),
                         create=True) as native):
            self.assertTrue(preview.production_camera_active())
        native.assert_not_called()

    def test_unreadable_port_table_conservatively_blocks_camera_capture(self):
        for failure in (OSError("denied"), ValueError("truncated"), struct.error("header")):
            with self.subTest(failure=type(failure).__name__):
                with (mock.patch.object(preview, "_production_port_active", side_effect=failure),
                      mock.patch("ctypes.WinDLL", side_effect=AssertionError("No kernel lookup expected"),
                                 create=True)):
                    self.assertTrue(preview.production_camera_active())


if __name__ == "__main__":
    unittest.main()
