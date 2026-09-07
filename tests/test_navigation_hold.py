import itertools
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from scene_control import SceneControlError
import transition_overlay as overlay


class NavigationHoldTests(unittest.TestCase):
    def setUp(self):
        self.hold = overlay.NavigationHold({"back": (0, 0, 100, 100), "next": (200, 0, 100, 100)},
                                           max_jump=30)

    def observe(self, points, stamp, **kwargs):
        return self.hold.update(points, stamp, stamp, **kwargs)

    def complete(self, point=(250, 50), start=0.0):
        actions = [self.observe([point], start + index / 10) for index in range(11)]
        self.assertEqual(actions[:-1], [None] * 10)
        return actions[-1]

    def test_one_second_of_new_observations_fires_once(self):
        self.assertEqual(self.complete(), "next")
        self.assertTrue(self.hold.latched)
        self.assertEqual(self.hold.progress, 1.0)
        for index in range(11, 30):
            self.assertIsNone(self.observe([(250, 50)], index / 10))

    def test_same_snapshot_does_not_advance_and_stale_snapshot_cancels(self):
        self.observe([(250, 50)], 0)
        self.hold.update([(250, 50)], 0, 0.2)
        self.assertEqual(self.hold.progress, 0)
        self.hold.update([(250, 50)], 0, 0.251)
        self.assertIsNone(self.hold.active)
        self.assertEqual(self.hold.progress, 0)

    def test_gap_between_observations_cannot_complete_a_hold(self):
        self.observe([(250, 50)], 0)
        self.assertIsNone(self.observe([(250, 50)], 1.1))
        self.assertEqual(self.hold.progress, 0)

    def test_departure_tracking_loss_and_conflict_cancel_immediately(self):
        for invalid in ([], [(150, 150)], [(50, 50), (250, 50)]):
            with self.subTest(points=invalid):
                self.observe([(250, 50)], 0)
                self.observe([(250, 50)], 0.2)
                self.assertGreater(self.hold.progress, 0)
                self.observe(invalid, 0.21)
                self.assertIsNone(self.hold.active)
                self.assertEqual(self.hold.progress, 0)

    def test_a_different_hand_cannot_inherit_progress_after_a_position_jump(self):
        self.observe([(210, 10)], 0)
        self.observe([(210, 10)], 0.2)
        self.observe([(290, 90)], 0.21)
        self.assertEqual(self.hold.progress, 0)

    def test_latch_survives_transition_and_tracking_loss_until_visible_departure(self):
        self.assertEqual(self.complete(), "next")
        self.observe([], 1.1, enabled=False)
        self.hold.update([(250, 50)], 1.1, 2.0, enabled=False)
        self.observe([(250, 50)], 2.0, enabled=False)
        self.observe([(50, 50)], 2.1, enabled=True)
        self.assertTrue(self.hold.latched)
        self.observe([(150, 150)], 2.2, enabled=False)
        self.assertFalse(self.hold.latched)
        self.assertEqual(self.complete((50, 50), 3.0), "back")

    def test_disabled_navigation_never_accumulates_a_hold(self):
        for index in range(20):
            self.assertIsNone(self.observe([(250, 50)], index / 10, enabled=False))
        self.assertEqual(self.hold.progress, 0)
        self.assertEqual(self.complete(start=2.0), "next")

    def test_two_regions_never_fire_simultaneously(self):
        for index in range(20):
            self.assertIsNone(self.observe([(50, 50), (250, 50)], index / 10))
        self.assertFalse(self.hold.latched)


class CurtainTests(unittest.TestCase):
    def setUp(self):
        self.screen = mock.Mock()
        self.screen.get_size.return_value = (1920, 1080)
        self.pygame = SimpleNamespace(draw=mock.Mock(), display=mock.Mock())
        self.curtain = overlay.Curtain()

    def test_cover_requires_successful_flip_and_never_auto_reveals(self):
        self.curtain.command("COVER", 1, 0)
        self.pygame.display.flip.side_effect = RuntimeError("present failed")
        with self.assertRaises(RuntimeError):
            overlay.present_frame(self.screen, self.pygame, self.curtain, 1)
        self.assertEqual(self.curtain.state, "covering")
        self.pygame.display.flip.side_effect = None
        self.assertEqual(overlay.present_frame(self.screen, self.pygame, self.curtain, 1), "COVERED")
        self.screen.fill.assert_called_with(overlay.COVER_COLOR)
        self.assertIsNone(overlay.present_frame(self.screen, self.pygame, self.curtain, 1000))
        self.assertEqual(self.curtain.level, 1)
        self.curtain.command("REVEAL", 1, 1000)
        self.assertEqual(overlay.present_frame(self.screen, self.pygame, self.curtain, 1001), "REVEALED")
        self.assertEqual(self.curtain.state, "idle")

    def test_failed_curtain_rejects_reveal(self):
        self.curtain.fail()
        with self.assertRaises(SceneControlError):
            self.curtain.command("REVEAL", 0, 1)
        self.assertEqual(overlay.present_frame(self.screen, self.pygame, self.curtain, 100), None)
        self.assertEqual(self.curtain.level, 1)

    def test_reveal_must_match_cycle_and_follow_cover_ack(self):
        self.curtain.command("COVER", 1, 0)
        with self.assertRaises(SceneControlError):
            self.curtain.command("REVEAL", 1, 0.1)
        overlay.present_frame(self.screen, self.pygame, self.curtain, 1)
        with self.assertRaises(SceneControlError):
            self.curtain.command("REVEAL", 2, 1)


class DetectionWorkerTests(unittest.TestCase):
    def fake_modules(self, cap):
        hands = mock.Mock()
        hands.process.return_value = SimpleNamespace(multi_hand_landmarks=[])
        cv2 = SimpleNamespace(COLOR_BGR2RGB=1, cvtColor=mock.Mock(return_value=object()))
        display = SimpleNamespace(prepare_camera_frame=mock.Mock(return_value=(object(), None, {})),
                                  normalized_to_stage=mock.Mock(), open_camera=mock.Mock())
        modules = {
            "cv2": cv2, "display_utils": display,
            "mediapipe": SimpleNamespace(solutions=SimpleNamespace(hands=SimpleNamespace(Hands=mock.Mock(return_value=hands)))),
            "shared_camera": SimpleNamespace(SharedMemoryCamera=SimpleNamespace(from_env=mock.Mock(return_value=cap))),
        }
        return modules, hands, display

    def test_no_shared_camera_fails_without_opening_a_physical_camera(self):
        worker = overlay.DetectionWorker(100, 100)
        modules, _hands, display = self.fake_modules(None)
        with mock.patch.dict(sys.modules, modules):
            worker._run()
        snapshot, error = worker.snapshot()
        self.assertEqual(snapshot, (None, ()))
        self.assertIn("Manager shared camera", error)
        display.open_camera.assert_not_called()

    def test_repeated_frame_id_is_not_redetected_or_given_a_new_timestamp(self):
        worker = overlay.DetectionWorker(100, 100)
        cap = mock.Mock(last_read_frame_id=10)
        calls = []

        def read():
            calls.append(1)
            if len(calls) == 3:
                worker._stop.set()
            return True, object()

        cap.read.side_effect = read
        modules, hands, _display = self.fake_modules(cap)
        with mock.patch.dict(sys.modules, modules):
            worker._run()
        hands.process.assert_called_once()
        cap.release.assert_called_once()
        hands.close.assert_called_once()
        self.assertIsNone(worker.snapshot()[1])

    def test_one_cleanup_failure_does_not_skip_shared_camera_release(self):
        worker = overlay.DetectionWorker(100, 100)
        worker._stop.set()
        cap = mock.Mock()
        modules, hands, _display = self.fake_modules(cap)
        hands.close.side_effect = RuntimeError("cleanup failed")
        with mock.patch.dict(sys.modules, modules):
            worker._run()
        cap.release.assert_called_once()
        self.assertIn("cleanup failed", worker.snapshot()[1])


class OverlayLoopTests(unittest.TestCase):
    def run_loop(self, batches, *, disconnect=False):
        trace = []
        screen = mock.Mock()
        screen.get_size.return_value = (100, 100)
        channel = mock.Mock(eof=False)
        channel.send.side_effect = lambda message: trace.append(message["event"])
        responses = iter(batches)

        def receive():
            try:
                return next(responses)
            except StopIteration:
                if disconnect:
                    channel.eof = True
                    return []
                return [{"command": "CLOSE", "token": "token"}]

        channel.receive.side_effect = receive
        pygame = SimpleNamespace(NOFRAME=1, HIDDEN=2, QUIT=3, init=mock.Mock(), quit=mock.Mock(),
                                 event=SimpleNamespace(get=mock.Mock(return_value=[])), draw=mock.Mock(),
                                 time=SimpleNamespace(Clock=mock.Mock()), font=mock.Mock(),
                                 display=mock.Mock())
        pygame.display.set_mode.return_value = screen
        pygame.display.flip.side_effect = lambda: trace.append("flip")
        worker = mock.Mock()
        worker.snapshot.return_value = ((None, ()), None)
        worker.camera_snapshot.return_value = (None, None)
        stamps = itertools.count(0.0, 2.0)
        with (mock.patch.dict(sys.modules, {"pygame": pygame}),
              mock.patch("stage_display.configure_audience_dpi"),
              mock.patch.object(overlay, "configure_overlay_window",
                                side_effect=lambda *_args: self.assertEqual(trace, ["flip"])),
              mock.patch.object(overlay, "DetectionWorker", return_value=worker),
              mock.patch.object(overlay, "NavigationStyle"),
              mock.patch("transition_logo.CurtainLogo"),
              mock.patch("transition_particles.ParticleCurtain"),
              mock.patch.object(overlay, "OverlayOpacity"),
              mock.patch.object(overlay.socket, "create_connection"),
              mock.patch.object(overlay, "JsonChannel", return_value=channel),
              mock.patch.object(overlay.time, "monotonic", side_effect=lambda: next(stamps))):
            overlay.run_overlay(1234, "token", (0, 0, 100, 100))
        worker.close.assert_called_once()
        self.assertEqual(pygame.display.set_mode.call_args.args[1], pygame.NOFRAME | pygame.HIDDEN)
        pygame.quit.assert_called_once()
        channel.close.assert_called_once()
        return trace, channel

    def test_real_loop_sends_acks_only_after_presenting_each_endpoint(self):
        trace, _channel = self.run_loop([
            [{"command": "COVER", "cycle": 1, "token": "token"}], [],
            [{"command": "REVEAL", "cycle": 1, "token": "token"}], [],
        ])
        self.assertEqual(trace, ["flip", "READY", "flip", "flip", "COVERED", "flip", "flip", "REVEALED"])

    def test_bad_command_forces_a_presented_cover_and_never_reveals(self):
        trace, _channel = self.run_loop([[{"command": "REVEAL", "cycle": 1, "token": "wrong"}], []])
        self.assertEqual(trace[:5], ["flip", "READY", "flip", "COVERED", "ERROR"])
        self.assertNotIn("REVEALED", trace)


@unittest.skipUnless(overlay.os.name == "nt", "Win32 API signature test")
class OverlayWindowTests(unittest.TestCase):
    def test_colorkey_not_zero_alpha_and_noactivate_clickthrough_styles(self):
        import ctypes

        user32 = mock.Mock()
        user32.GetWindowLongPtrW.return_value = 0
        user32.SetWindowLongPtrW.return_value = 0
        user32.SetLayeredWindowAttributes.return_value = True
        user32.SetWindowPos.return_value = True
        pygame = SimpleNamespace(display=SimpleNamespace(get_wm_info=lambda: {"window": 123}))
        with mock.patch.object(ctypes, "WinDLL", return_value=user32):
            overlay.configure_overlay_window(pygame, (-1920, 0, 1920, 1080))
        self.assertEqual(overlay.LWA_COLORKEY, 1)
        self.assertEqual(user32.SetLayeredWindowAttributes.call_args.args[-1], 1)
        style = user32.SetWindowLongPtrW.call_args.args[-1]
        for required in (overlay.WS_EX_LAYERED, overlay.WS_EX_TRANSPARENT, overlay.WS_EX_NOACTIVATE):
            self.assertEqual(style & required, required)
        placement = user32.SetWindowPos.call_args.args
        self.assertEqual(placement[1:6], (-1, -1920, 0, 1920, 1080))
        self.assertTrue(placement[-1] & overlay.SWP_NOACTIVATE)


if __name__ == "__main__":
    unittest.main()
