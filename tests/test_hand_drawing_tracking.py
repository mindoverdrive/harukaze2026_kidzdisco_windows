"""Pure synthetic tracking regressions: no MediaPipe, camera or window."""
import math
import random
from types import SimpleNamespace
import unittest

from hand_drawing_tracking import HandTracks, _assignment


def hand(name, x, y=.5, spread=1.0):
    shape = [(0, .075), (-.025, .05), (-.045, .035), (-.06, .015), (-.08, -.005),
             (-.035, .005), (-.035, -.04), (-.035, -.07), (-.035, -.10),
             (0, 0), (0, -.05), (0, -.08), (0, -.12),
             (.03, .005), (.03, -.04), (.03, -.07), (.03, -.10),
             (.055, .02), (.06, -.015), (.065, -.04), (.07, -.07)]
    return SimpleNamespace(name=name, landmark=[SimpleNamespace(x=x + dx * spread, y=y + dy)
                                                for dx, dy in shape])


def result(hands=(), labels=None):
    labels = ['Right'] * len(hands) if labels is None else labels
    return SimpleNamespace(
        multi_hand_landmarks=hands,
        multi_handedness=[SimpleNamespace(classification=[] if label is None else
                                         [SimpleNamespace(label=label)]) for label in labels])


def identity(observed):
    return {item.hand.name: (item.track_id, item.effect_id) for item in observed}


class HandTracksTests(unittest.TestCase):
    def test_eight_same_label_hands_keep_unique_random_effects_through_reorders(self):
        tracker = HandTracks(rng=random.Random(7))
        poses = [hand(str(i), .1 + (i % 4) * .25, .3 + (i // 4) * .35) for i in range(8)]
        first = tracker.update(result(poses), 0)
        expected = identity(first)
        self.assertEqual(set(item.effect_id for item in first), set(range(8)))
        self.assertEqual(set(item.track_id for item in first), set(range(1, 9)))
        self.assertFalse(any(item.continuous for item in first))
        self.assertEqual(first[0].effect_id, random.Random(7).choice(range(8)))
        shuffler = random.Random(11)
        for tick in range(1, 61):
            shuffler.shuffle(poses)
            observed = tracker.update(result(poses, ['Left' if tick % 2 else 'Right'] * 8), tick / 30)
            self.assertEqual(identity(observed), expected)
            self.assertTrue(all(item.continuous for item in observed))
            self.assertEqual(len(tracker.tracks), 8)

    def test_first_arrival_is_random_and_seed_is_reproducible(self):
        choices = []
        for seed in range(8):
            a, b = HandTracks(rng=random.Random(seed)), HandTracks(rng=random.Random(seed))
            observation = result([hand('a', .5)])
            self.assertEqual(identity(a.update(observation, 0)), identity(b.update(observation, 0)))
            choices.append(next(iter(a.tracks.values())).effect_id)
        self.assertGreater(len(set(choices)), 1)

    def test_order_on_first_arrival_does_not_choose_spatial_identity(self):
        hands = [hand('a', .2), hand('b', .8)]
        a, b = HandTracks(rng=random.Random(3)), HandTracks(rng=random.Random(3))
        self.assertEqual(identity(a.update(result(hands), 0)),
                         identity(b.update(result(list(reversed(hands))), 0)))

    def test_global_assignment_does_not_greedily_steal_another_tracks_only_candidate(self):
        assigned, _ambiguous = _assignment(((.10, .11), (.105, math.inf)), 2)
        self.assertEqual(assigned, (1, 0))

    def test_velocity_keeps_two_same_shape_hands_through_a_crossing(self):
        tracker = HandTracks(rng=random.Random(5))
        expected = None
        for tick in range(9):
            x = .25 + tick * .05
            poses = [hand('a', x), hand('b', 1 - x)]
            if tick % 2:
                poses.reverse()
            observed = tracker.update(result(poses), tick * .05)
            if expected is None:
                expected = identity(observed)
            if tick != 5:  # Identical exact overlap has no observable identity.
                self.assertEqual(identity(observed), expected)
            if tick in (5, 6):
                self.assertFalse(any(item.continuous for item in observed))
            if tick == 8:
                self.assertTrue(all(item.continuous for item in observed))

    def test_shape_disambiguates_matching_when_two_palm_positions_are_close(self):
        tracker = HandTracks(rng=random.Random(2))
        first = tracker.update(result([hand('narrow', .49, spread=.4),
                                       hand('wide', .51, spread=1.8)]), 0)
        observed = tracker.update(result([hand('wide', .49, spread=1.8),
                                          hand('narrow', .51, spread=.4)]), .05)
        self.assertEqual(identity(observed), identity(first))

    def test_newcomer_equally_close_to_old_hand_cannot_connect_to_old_stroke(self):
        for reverse in (False, True):
            tracker = HandTracks(rng=random.Random(1))
            first = tracker.update(result([hand('old', .4)]), 0)[0]
            candidates = [hand('a', .38), hand('b', .42)]
            if reverse:
                candidates.reverse()
            observed = tracker.update(result(candidates), .05)
            previous = next(item for item in observed if item.track_id == first.track_id)
            self.assertFalse(previous.continuous)

    def test_three_way_ambiguous_cycle_breaks_all_strokes(self):
        tracker = HandTracks(rng=random.Random(1))
        def triangle(rotation):
            return [hand(str(i), .5 + .1 * math.cos(i * math.tau / 3 + rotation),
                         .5 + .1 * math.sin(i * math.tau / 3 + rotation)) for i in range(3)]
        tracker.update(result(triangle(0), [None] * 3), 0)
        observed = tracker.update(result(triangle(math.pi / 3), [None] * 3), .05)
        self.assertEqual(len(observed), 3)
        self.assertFalse(any(item.continuous for item in observed))

    def test_short_occlusion_retains_effect_but_reentry_starts_a_new_stroke(self):
        tracker = HandTracks(rng=random.Random(4))
        initial = tracker.update(result([hand('a', .2), hand('b', .8)]), 0)
        tracker.update(result([hand('b', .8)]), .05)
        returned = tracker.update(result([hand('b', .8), hand('a', .21)]), .10)
        self.assertEqual(identity(returned), identity(initial))
        self.assertFalse(next(item for item in returned if item.hand.name == 'a').continuous)
        self.assertTrue(next(item for item in returned if item.hand.name == 'b').continuous)
        continued = tracker.update(result([hand('a', .22), hand('b', .8)]), .15)
        self.assertTrue(all(item.continuous for item in continued))

    def test_empty_updates_expire_long_absence_without_growing_state(self):
        tracker = HandTracks(rng=random.Random(2))
        old = tracker.update(result([hand('a', .5)]), 0)[0]
        self.assertEqual(tracker.update(result(), .5), ())
        self.assertIn(old.track_id, tracker.tracks)
        self.assertEqual(tracker.update(result(), 1.5001), ())
        self.assertEqual(tracker.tracks, {})
        new = tracker.update(result([hand('a', .5)]), 1.6)[0]
        self.assertNotEqual(new.track_id, old.track_id)
        self.assertFalse(new.continuous)

    def test_full_capacity_keeps_absent_reservation_until_it_expires(self):
        tracker = HandTracks(rng=random.Random(2))
        original = [hand(str(i), .1 + i * .1, .25) for i in range(8)]
        initial = identity(tracker.update(result(original), 0))
        newcomers = original[1:] + [hand('new', .5, .95)]
        observed = tracker.update(result(newcomers), .1)
        self.assertEqual(set(identity(observed)), {str(i) for i in range(1, 8)})
        restored = tracker.update(result(original), .2)
        self.assertEqual(identity(restored), initial)
        tracker.update(result(newcomers), .3)
        observed = tracker.update(result(newcomers), 1.71)
        self.assertIn('new', identity(observed))
        self.assertNotIn(initial['0'][0], tracker.tracks)
        self.assertEqual(len(tracker.tracks), 8)
        self.assertEqual(len({item.effect_id for item in observed}), 8)

    def test_break_continuity_and_large_time_gap_preserve_feasible_assignments(self):
        tracker = HandTracks(rng=random.Random(2))
        observation = result([hand('a', .5)])
        initial = identity(tracker.update(observation, 0))
        self.assertTrue(tracker.update(observation, .05)[0].continuous)
        tracker.break_continuity()
        self.assertFalse(tracker.update(observation, .10)[0].continuous)
        self.assertTrue(tracker.update(observation, .15)[0].continuous)
        self.assertFalse(tracker.update(observation, .5)[0].continuous)
        self.assertEqual(identity(tracker.update(observation, .55)), initial)

    def test_large_position_jump_does_not_connect_and_distant_arrival_gets_new_id(self):
        tracker = HandTracks(rng=random.Random(2))
        initial = tracker.update(result([hand('a', .1)]), 0)[0]
        moved = tracker.update(result([hand('a', .3)]), .1)[0]
        self.assertEqual(moved.track_id, initial.track_id)
        self.assertFalse(moved.continuous)
        far = tracker.update(result([hand('new', .9, .95)]), .15)[0]
        self.assertNotEqual(far.track_id, initial.track_id)
        self.assertFalse(far.continuous)

    def test_label_flip_and_missing_label_do_not_reverse_thumb_semantics_immediately(self):
        tracker = HandTracks()
        tracker.update(result([hand('a', .5)], ['Right']), 0)
        self.assertEqual(tracker.update(result([hand('a', .5)], ['Left']), .05)[0].handedness, 'Right')
        self.assertEqual(tracker.update(result([hand('a', .5)], [None]), .10)[0].handedness, 'Right')
        for now in (.15, .20, .25, .30):
            self.assertEqual(tracker.update(result([hand('a', .5)], ['Left']), now)[0].handedness, 'Right')
        self.assertEqual(tracker.update(result([hand('a', .5)], ['Left']), .35)[0].handedness, 'Left')

    def test_duplicate_or_backwards_time_breaks_strokes_but_preserves_assignment(self):
        tracker = HandTracks()
        observation = result([hand('a', .5)])
        original = identity(tracker.update(observation, 10))
        self.assertFalse(tracker.update(observation, 10)[0].continuous)
        self.assertFalse(tracker.update(observation, 2)[0].continuous)
        self.assertEqual(identity(tracker.update(observation, 2.1)), original)
        tracker.update(result(), 3.7)
        self.assertEqual(tracker.tracks, {})

    def test_invalid_inputs_and_more_than_eight_observations_are_bounded(self):
        tracker = HandTracks()
        malformed = [SimpleNamespace(landmark=[]), hand('nan', math.nan),
                     hand('huge', 1e300), None]
        self.assertEqual(tracker.update(result(malformed), 0), ())
        consumed = []
        def observations():
            for i in range(100):
                consumed.append(i)
                yield hand(str(i), .1 + i * .1)
        observed = tracker.update(SimpleNamespace(multi_hand_landmarks=observations()), .05)
        self.assertEqual(consumed, list(range(8)))
        self.assertEqual(len(observed), 8)
        self.assertEqual(len(tracker.tracks), 8)
        for tick in range(1, 101):
            tracker.update(result(), tick * 2)
            tracker.update(result([hand(str(tick), .5)]), tick * 2 + .1)
            self.assertLessEqual(len(tracker.tracks), 8)

    def test_reset_hard_clears_tracking_and_reservations(self):
        tracker = HandTracks()
        tracker.update(result([hand('a', .5)]), 0)
        tracker.reset()
        self.assertEqual(tracker.tracks, {})
        observed = tracker.update(result([hand('b', .5)]), 0)
        self.assertEqual(observed[0].track_id, 1)
        self.assertFalse(observed[0].continuous)

    def test_constructor_and_timestamp_validation(self):
        for count in (0, 9, -1, 1.5, True):
            with self.assertRaises(ValueError):
                HandTracks(max_hands=count)
        for duration in (-1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                HandTracks(retain_seconds=duration)
        for now in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                HandTracks().update(result(), now)


if __name__ == '__main__':
    unittest.main()
