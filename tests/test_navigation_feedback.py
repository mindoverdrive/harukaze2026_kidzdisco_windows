"""Navigation feedback regressions using coordinates and fully mocked I/O.

No camera, worker thread, socket, or native window is started by these tests.
The nearby-hand case documents a current limitation of position-only input;
it is not an acceptance claim about tracking a person's identity.
"""

import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import transition_overlay as overlay


REGIONS = {"back": (0, 0, 100, 100), "next": (200, 0, 100, 100)}
BACK = (50, 50)
NEXT = (250, 50)
OUTSIDE = (150, 150)


class NavigationFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.hold = overlay.NavigationHold(REGIONS, max_jump=30)

    def observe(self, points, stamp, *, now=None, enabled=True):
        return self.hold.update(
            points, stamp, stamp if now is None else now, enabled=enabled
        )

    def complete(self):
        actions = [self.observe([NEXT], index / 10) for index in range(11)]
        self.assertEqual(actions, [None] * 10 + ["next"])

    def assert_cancelled(self, feedback, visible=()):
        self.assertEqual(self.hold.feedback, feedback)
        self.assertEqual(self.hold.visible_points, visible)
        self.assertIsNone(self.hold.active)
        self.assertIsNone(self.hold.point)
        self.assertEqual(self.hold.progress, 0.0)

    def test_fresh_finite_points_are_visible_before_entering_a_button(self):
        points = [OUTSIDE, (125, 125), (float("nan"), 1), (1, float("inf")), (1,)]
        self.assertIsNone(self.observe(points, 0.0))
        self.assert_cancelled("ready", (OUTSIDE, (125, 125)))
        self.assertIsInstance(self.hold.visible_points, tuple)
        self.assertFalse(self.hold.latched)

    def test_one_second_hold_shows_all_points_and_fires_once(self):
        for index in range(10):
            self.assertIsNone(self.observe([NEXT, OUTSIDE], index / 10))
            self.assertEqual(self.hold.feedback, "holding")
            self.assertEqual(self.hold.visible_points, (NEXT, OUTSIDE))
            self.assertEqual(self.hold.point, NEXT)
            self.assertAlmostEqual(self.hold.progress, index / 10)
        self.assertEqual(self.observe([NEXT, OUTSIDE], 1.0), "next")
        self.assertEqual(self.hold.feedback, "release")
        self.assertEqual(self.hold.progress, 1.0)
        self.assertEqual(self.hold.active, "next")
        self.assertTrue(self.hold.latched)
        self.assertIsNone(self.observe([NEXT, OUTSIDE], 1.1))
        self.assert_cancelled("release", (NEXT, OUTSIDE))

    def test_half_second_departure_discards_progress_immediately(self):
        for stamp in (0.0, 0.2, 0.4):
            self.assertIsNone(self.observe([NEXT], stamp))
        self.assertAlmostEqual(self.hold.progress, 0.4)
        self.assertIsNone(self.observe([OUTSIDE], 0.5))
        self.assert_cancelled("ready", (OUTSIDE,))
        self.observe([OUTSIDE], 0.7)
        self.observe([OUTSIDE], 0.9)
        for index in range(10):
            self.assertIsNone(self.observe([NEXT], 1.0 + index / 10))
        self.assertEqual(self.observe([NEXT], 2.0), "next")

    def test_same_snapshot_does_not_advance_progress_or_fire(self):
        for stamp in (0.0, 0.2, 0.4, 0.6):
            self.observe([NEXT], stamp)
        progress = self.hold.progress
        for now in (0.61, 0.7, 0.8):
            self.assertIsNone(self.observe([NEXT], 0.6, now=now))
            self.assertEqual(self.hold.progress, progress)
            self.assertEqual(self.hold.feedback, "holding")
            self.assertEqual(self.hold.visible_points, (NEXT,))

    def test_stale_missing_and_future_stamps_hide_points_and_cancel(self):
        cases = [(0.2, 0.451), (0.5, 0.4), (None, 0.4), (float("nan"), 0.4)]
        for stamp, now in cases:
            with self.subTest(stamp=stamp, now=now):
                self.hold = overlay.NavigationHold(REGIONS, max_jump=30)
                self.observe([NEXT], 0.0)
                self.observe([NEXT], 0.2)
                self.assertIsNone(self.observe([NEXT], stamp, now=now))
                self.assert_cancelled("stale")
                self.assertFalse(self.hold.latched)

    def test_a_fresh_observation_after_a_gap_restarts_the_hold(self):
        self.observe([NEXT], 0.0)
        self.observe([NEXT], 0.2)
        self.assertIsNone(self.observe([NEXT], 0.5))
        self.assertEqual(self.hold.feedback, "holding")
        self.assertEqual(self.hold.visible_points, (NEXT,))
        self.assertEqual(self.hold.progress, 0.0)

    def test_no_hand_and_conflict_are_distinct_and_cancel_progress(self):
        self.observe([NEXT], 0.0)
        self.observe([NEXT], 0.2)
        self.assertIsNone(self.observe([], 0.21))
        self.assert_cancelled("no_hand")
        self.observe([NEXT], 0.3)
        self.observe([NEXT], 0.5)
        self.assertIsNone(self.observe([BACK, NEXT], 0.6))
        self.assert_cancelled("conflict", (BACK, NEXT))
        self.assertFalse(self.hold.latched)
        self.assertIsNone(self.observe([NEXT], 0.7))
        self.assertEqual(self.hold.progress, 0.0)

    def test_zero_points_do_not_rearm_a_fired_action(self):
        self.complete()
        for stamp in (1.1, 1.3, 1.5):
            self.assertIsNone(self.observe([], stamp))
            self.assert_cancelled("no_hand")
            self.assertTrue(self.hold.latched)
        self.assertIsNone(self.observe([NEXT], 1.6))
        self.assert_cancelled("release", (NEXT,))
        self.assertTrue(self.hold.latched)

    def test_stale_departure_is_not_proof_of_leaving_the_buttons(self):
        self.complete()
        self.assertIsNone(self.observe([OUTSIDE], 1.1, now=1.4))
        self.assert_cancelled("stale")
        self.assertTrue(self.hold.latched)
        self.assertIsNone(self.observe([OUTSIDE], 1.5))
        self.assert_cancelled("ready", (OUTSIDE,))
        self.assertFalse(self.hold.latched)

    def test_another_point_in_either_button_keeps_the_latch(self):
        self.complete()
        for stamp, points in ((1.1, [OUTSIDE, NEXT]), (1.2, [OUTSIDE, BACK]),
                              (1.3, [BACK, NEXT])):
            self.assertIsNone(self.observe(points, stamp))
            self.assert_cancelled("release", tuple(points))
            self.assertTrue(self.hold.latched)
        outside_points = (OUTSIDE, (125, 125))
        self.assertIsNone(self.observe(outside_points, 1.4))
        self.assert_cancelled("ready", outside_points)
        self.assertFalse(self.hold.latched)
        for index in range(10):
            self.assertIsNone(self.observe([BACK], 2.0 + index / 10))
        self.assertEqual(self.observe([BACK], 3.0), "back")

    def test_disabled_feedback_hides_points_and_never_accumulates(self):
        for index in range(15):
            self.assertIsNone(self.observe([NEXT], index / 10, enabled=False))
            self.assert_cancelled("disabled")
        self.assertIsNone(self.observe([NEXT], 1.4, now=1.8, enabled=False))
        self.assert_cancelled("disabled")
        self.assertIsNone(self.observe([NEXT], 2.0))
        self.assertEqual(self.hold.progress, 0.0)
        self.assertEqual(self.hold.feedback, "holding")

    def test_disabled_navigation_still_rearms_on_a_fresh_visible_departure(self):
        self.complete()
        self.assertIsNone(self.observe([], 1.1, enabled=False))
        self.assert_cancelled("disabled")
        self.assertTrue(self.hold.latched)
        self.assertIsNone(self.observe([OUTSIDE, BACK], 1.2, enabled=False))
        self.assert_cancelled("disabled")
        self.assertTrue(self.hold.latched)
        self.assertIsNone(self.observe([OUTSIDE], 1.3, enabled=False))
        self.assert_cancelled("disabled")
        self.assertFalse(self.hold.latched)
        self.assertIsNone(self.observe([NEXT], 1.4))
        self.assertEqual(self.hold.progress, 0.0)

    def test_display_metadata_does_not_control_action_acceptance(self):
        # Presentation fields are outputs; they must not control acceptance.
        for index in range(11):
            self.hold.feedback = "conflict"
            self.hold.visible_points = (BACK, NEXT)
            action = self.observe([NEXT], index / 10)
            self.assertEqual(action, "next" if index == 10 else None)
        self.assertTrue(self.hold.latched)
        self.hold.feedback = "ready"
        self.hold.visible_points = (OUTSIDE,)
        self.assertIsNone(self.observe([NEXT], 1.1))
        self.assertTrue(self.hold.latched)

    def test_candidate_order_does_not_replace_the_nearest_hold_point(self):
        self.observe([(220, 50), (280, 50)], 0.0)
        self.observe([(280, 50), (222, 50)], 0.2)
        self.assertEqual(self.hold.point, (222, 50))
        self.assertAlmostEqual(self.hold.progress, 0.2)
        self.assertEqual(self.hold.visible_points, ((280, 50), (222, 50)))

    def test_position_only_input_cannot_identify_a_nearby_hand_replacement(self):
        # Known limitation preserved by this feedback-only change: a different
        # hand ten pixels away is indistinguishable from one hand moving there.
        for index in range(9):
            self.assertIsNone(self.observe([NEXT], index / 10))
        replacement = (260, 50)
        self.assertIsNone(self.observe([replacement], 0.9))
        self.assertAlmostEqual(self.hold.progress, 0.9)
        self.assertEqual(self.observe([replacement], 1.0), "next")


class OverlaySnapshotClockTests(unittest.TestCase):
    def run_clock_case(self, *, loop_now, observed_at, consumed_at):
        """Exercise real hold/curtain logic; every external I/O is a mock.

        Reuse the existing OverlayLoopTests harness pattern, with a mutable
        fake monotonic clock. snapshot() advances time after the loop's early
        clock read, so a fix must resample time rather than tolerate future data.
        """
        frames = [
            (0.0, None, 0.0, [{"command": "COVER", "cycle": 1, "token": "token"}]),
            (2.0, None, 2.0, []),
            (3.0, None, 3.0, [{"command": "REVEAL", "cycle": 1, "token": "token"}]),
            (5.0, None, 5.0, []),
        ]
        frames.extend((stamp, stamp, stamp, []) for stamp in (10.0, 10.2, 10.4, 10.6, 10.8))
        frames.extend([
            (loop_now, observed_at, consumed_at, []),
            (12.0, None, 12.0, [{"command": "CLOSE", "token": "token"}]),
        ])
        clock_state = {"index": 0, "now": 0.0}
        trace = []
        created_holds = []
        hold_type = overlay.NavigationHold

        def make_hold(*args, **kwargs):
            hold = hold_type(*args, **kwargs)
            created_holds.append(hold)
            return hold

        def receive():
            return frames[clock_state["index"]][3]

        def snapshot():
            _early, stamp, consumed, _messages = frames[clock_state["index"]]
            clock_state["now"] = consumed
            # At 100x100, NEXT occupies x=77..96, y=3..17.
            return ((stamp, ((90, 10),) if stamp is not None else ()), None)

        def tick(_fps):
            clock_state["index"] += 1
            clock_state["now"] = frames[clock_state["index"]][0]

        screen = mock.Mock()
        screen.get_size.return_value = (100, 100)
        channel = mock.Mock(eof=False)
        channel.receive.side_effect = receive
        channel.send.side_effect = lambda message: trace.append(dict(message))
        worker = mock.Mock()
        worker.snapshot.side_effect = snapshot
        worker.camera_snapshot.return_value = (None, None)
        pygame = SimpleNamespace(
            NOFRAME=1, HIDDEN=2, QUIT=3, init=mock.Mock(), quit=mock.Mock(),
            event=SimpleNamespace(get=mock.Mock(return_value=[])),
            draw=mock.Mock(), font=mock.Mock(), display=mock.Mock(),
            time=SimpleNamespace(Clock=mock.Mock(return_value=SimpleNamespace(tick=tick))),
        )
        pygame.display.set_mode.return_value = screen
        with (mock.patch.dict(sys.modules, {"pygame": pygame}),
              mock.patch("stage_display.configure_audience_dpi"),
              mock.patch.object(overlay, "configure_overlay_window"),
              mock.patch.object(overlay, "DetectionWorker", return_value=worker),
              mock.patch.object(overlay, "NavigationHold", side_effect=make_hold),
              mock.patch.object(overlay, "NavigationStyle"),
              mock.patch.object(overlay, "draw_navigation"),
              mock.patch("transition_branding.AlternatingCurtainLogo"),
              mock.patch("transition_particles.ParticleCurtain"),
              mock.patch.object(overlay, "OverlayOpacity"),
              mock.patch.object(overlay.socket, "create_connection"),
              mock.patch.object(overlay, "JsonChannel", return_value=channel),
              mock.patch.object(overlay.time, "monotonic", side_effect=lambda: clock_state["now"])):
            overlay.run_overlay(1234, "token", (0, 0, 100, 100))
        worker.close.assert_called_once()
        pygame.quit.assert_called_once()
        channel.close.assert_called_once()
        self.assertEqual([item["event"] for item in trace[:3]], ["READY", "COVERED", "REVEALED"])
        self.assertNotIn("ERROR", [item["event"] for item in trace])
        self.assertEqual(len(created_holds), 1)
        return trace, created_holds[0]

    def test_snapshot_published_after_loop_clock_can_complete_a_fresh_hold(self):
        trace, hold = self.run_clock_case(loop_now=10.98, observed_at=11.0, consumed_at=11.02)
        actions = [item["action"] for item in trace if item["event"] == "ACTION"]
        self.assertEqual(actions, ["next"])
        self.assertTrue(hold.latched)
        self.assertEqual(hold.feedback, "release")

    def test_snapshot_stale_at_consumption_cannot_complete_a_hold(self):
        trace, hold = self.run_clock_case(loop_now=11.2, observed_at=11.0, consumed_at=11.27)
        self.assertFalse(any(item["event"] == "ACTION" for item in trace))
        self.assertFalse(hold.latched)
        self.assertEqual(hold.feedback, "stale")
        self.assertEqual(hold.visible_points, ())
        self.assertEqual(hold.progress, 0.0)


if __name__ == "__main__":
    unittest.main()
