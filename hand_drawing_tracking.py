"""Bounded hand identities for drawing, independent of detector order or labels.

Palm motion and hand shape provide correspondence, not biometric identity. An
exact overlap of indistinguishable hands cannot guarantee identity. Ambiguous
matches keep their effect slots but break strokes instead of joining two hands.
No images, detector, drawing history, or camera resources are retained here.
"""
from dataclasses import dataclass
from functools import lru_cache
from itertools import islice
import math
import random


MAX_CONTINUOUS_SECONDS = 0.20
MAX_CONTINUOUS_PALM_STEP = 0.18
PREDICTION_SECONDS = 0.25
MAX_PALM_SPEED = 3.0
AMBIGUITY_MARGIN = 0.015
HANDEDNESS_STABLE_SECONDS = 0.18
PALM_IDS = (0, 5, 9, 13, 17)
SHAPE_WEIGHTS = tuple(1.0 if index in PALM_IDS else 0.25 for index in range(21))
UNMATCHED_COST = 0.18


@dataclass(frozen=True)
class TrackedHand:
    track_id: int
    effect_id: int
    hand: object
    handedness: str | None
    continuous: bool


@dataclass
class _TrackState:
    track_id: int
    effect_id: int
    center: tuple
    shape: tuple
    scale: float
    handedness: str | None
    last_seen: float
    velocity: tuple = (0.0, 0.0)
    velocity_ready: bool = False
    visible: bool = True
    can_continue: bool = True
    label_candidate: str | None = None
    label_since: float | None = None


@dataclass(frozen=True)
class _Observation:
    hand: object
    center: tuple
    shape: tuple
    scale: float
    handedness: str | None


def _observation(hand, handedness):
    try:
        landmarks = hand.landmark
        if len(landmarks) != 21:
            return None
        points = tuple((float(point.x), float(point.y)) for point in landmarks)
        if not all(math.isfinite(value) and abs(value) <= 4.0 for point in points for value in point):
            return None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None
    center = tuple(sum(points[i][axis] for i in PALM_IDS) / len(PALM_IDS)
                   for axis in (0, 1))
    scale = max(0.01, math.sqrt(sum(math.dist(points[i], center) ** 2
                                   for i in PALM_IDS) / len(PALM_IDS)))
    shape = tuple(((x - center[0]) / scale, (y - center[1]) / scale) for x, y in points)
    return _Observation(hand, center, shape, scale, handedness)


def _shape_distance(first, second):
    return math.sqrt(sum(weight * math.dist(a, b) ** 2
                         for a, b, weight in zip(first, second, SHAPE_WEIGHTS))
                     / sum(SHAPE_WEIGHTS))


def _cost(track, observed, now):
    elapsed = max(0.0, now - track.last_seen)
    horizon = min(elapsed, PREDICTION_SECONDS)
    predicted = tuple(position + speed * horizon
                      for position, speed in zip(track.center, track.velocity))
    distance = math.dist(predicted, observed.center)
    # Allow real movement and short occlusion, while refusing distant new hands.
    gate = 0.16 + min(elapsed, 0.25) * 0.9 + min(0.20, max(track.scale, observed.scale) * 1.25)
    if distance > gate:
        return math.inf
    shape = min(2.0, _shape_distance(track.shape, observed.shape))
    scale = min(1.0, abs(math.log(observed.scale / track.scale)))
    label_penalty = 0.008 if (track.handedness and observed.handedness
                              and track.handedness != observed.handedness) else 0.0
    return distance + 0.055 * shape + 0.035 * scale + label_penalty


def _assignment(costs, observation_count):
    """Global minimum including misses/new arrivals; O(n * m * 2**m), m <= 8."""
    @lru_cache(maxsize=None)
    def solve(row, used):
        if row == len(costs):
            return UNMATCHED_COST * (observation_count - used.bit_count()), ()
        remaining_cost, suffix = solve(row + 1, used)
        best = (UNMATCHED_COST + remaining_cost, (-1,) + suffix)
        for column, cost in enumerate(costs[row]):
            if used & (1 << column) or not math.isfinite(cost):
                continue
            remaining_cost, suffix = solve(row + 1, used | (1 << column))
            candidate = (cost + remaining_cost, (column,) + suffix)
            if candidate < best:
                best = candidate
        return best

    best_cost, assignment = solve(0, 0)
    # Prefix + edge + cached suffix gives the global minimum conditioned on
    # each possible correspondence. This catches ambiguous 3+ hand cycles and
    # newcomers, with the same bounded complexity instead of eight re-solves.
    ambiguous = set()
    prefixes = {0: 0.0}
    for row, row_costs in enumerate(costs):
        following = {}
        for used, prefix in prefixes.items():
            choices = [(-1, used, UNMATCHED_COST)]
            choices.extend((column, used | (1 << column), cost)
                           for column, cost in enumerate(row_costs)
                           if not used & (1 << column) and math.isfinite(cost))
            for column, next_used, cost in choices:
                next_prefix = prefix + cost
                total = next_prefix + solve(row + 1, next_used)[0]
                if column != assignment[row] and total <= best_cost + AMBIGUITY_MARGIN:
                    ambiguous.add(row)
                following[next_used] = min(following.get(next_used, math.inf), next_prefix)
        prefixes = following
    return assignment, ambiguous


def _overlapping_rows(observations, assignment):
    ambiguous = set()
    matched = [(row, column) for row, column in enumerate(assignment) if column >= 0]
    for position, (row, column) in enumerate(matched):
        for other_row, other_column in matched[position + 1:]:
            close_observations = (
                math.dist(observations[column].center, observations[other_column].center) < 0.025
                and _shape_distance(observations[column].shape, observations[other_column].shape) < 0.25)
            if close_observations:
                ambiguous.update((row, other_row))
    return ambiguous


class HandTracks:
    """Track up to eight hands, with unique effects reserved during brief absence.

    ``tracks`` is a bounded ``dict[track_id, state]`` for controller pruning.
    ``update`` returns only this frame's observations, ordered by track ID.
    Reservations last ``retain_seconds``; newcomers wait when all slots are
    reserved. Labels are a weak match cue; returned labels require 0.18 seconds
    of consistent change so a momentary flip cannot reverse thumb gestures.
    """

    def __init__(self, max_hands=8, retain_seconds=1.5, rng=None):
        if isinstance(max_hands, bool) or not isinstance(max_hands, int) or not 1 <= max_hands <= 8:
            raise ValueError("max_hands must be an integer from 1 to 8")
        if not math.isfinite(retain_seconds) or retain_seconds < 0:
            raise ValueError("retain_seconds must be finite and nonnegative")
        self.max_hands = max_hands
        self.retain_seconds = retain_seconds
        self.rng = rng if rng is not None else random.Random()
        self.reset()

    def reset(self):
        self.tracks = {}
        self._next_id = 1
        self._last_update = None

    def break_continuity(self):
        for track in self.tracks.values():
            track.can_continue = False
            track.label_candidate = track.label_since = None

    def update(self, results, now):
        if not math.isfinite(now):
            raise ValueError("Observation time must be finite")
        if self._last_update is not None and now <= self._last_update:
            self.break_continuity()
            if now < self._last_update:
                # Rebase reservations after a clock reset, keeping effect identity.
                shift = now - self._last_update
                for track in self.tracks.values():
                    track.last_seen += shift
                    track.velocity = (0.0, 0.0)
                    track.velocity_ready = False
        self._last_update = now
        self.tracks = {key: track for key, track in self.tracks.items()
                       if now - track.last_seen <= self.retain_seconds}
        labels = tuple(islice(getattr(results, "multi_handedness", None) or (), self.max_hands))
        observations = []
        for index, hand in enumerate(islice(getattr(results, "multi_hand_landmarks", None) or (),
                                           self.max_hands)):
            classes = getattr(labels[index], "classification", ()) if index < len(labels) else ()
            label = getattr(next(iter(classes or ()), None), "label", None)
            label = label if label in ("Left", "Right") else None
            observed = _observation(hand, label)
            if observed is not None:
                observations.append(observed)
        # Tie decisions and first arrivals do not depend on detector list ordering.
        observations.sort(key=lambda value: (value.center, value.shape, value.scale))
        states = sorted(self.tracks.values(), key=lambda value: value.track_id)
        costs = tuple(tuple(_cost(track, observed, now) for observed in observations) for track in states)
        assignment, ambiguous = _assignment(costs, len(observations))
        ambiguous.update(_overlapping_rows(observations, assignment))
        matched_columns = set()
        visible = []
        for row, track in enumerate(states):
            column = assignment[row]
            if column < 0:
                track.visible = False
                track.can_continue = False
                track.label_candidate = track.label_since = None
                continue
            observed = observations[column]
            elapsed = now - track.last_seen
            continuous = (track.visible and track.can_continue and row not in ambiguous
                          and 0 < elapsed <= MAX_CONTINUOUS_SECONDS
                          and math.dist(track.center, observed.center) <= MAX_CONTINUOUS_PALM_STEP)
            if row not in ambiguous:
                if 0 < elapsed <= MAX_CONTINUOUS_SECONDS and track.visible:
                    measured = tuple((new - old) / elapsed for new, old in zip(observed.center, track.center))
                    speed = math.hypot(*measured)
                    if speed > MAX_PALM_SPEED:
                        measured = tuple(value * MAX_PALM_SPEED / speed for value in measured)
                    track.velocity = (tuple(0.7 * new + 0.3 * old for new, old in zip(measured, track.velocity))
                                      if track.velocity_ready else measured)
                    track.velocity_ready = True
                else:
                    track.velocity = (0.0, 0.0)
                    track.velocity_ready = False
                track.shape, track.scale = observed.shape, observed.scale
                if elapsed > MAX_CONTINUOUS_SECONDS:
                    track.label_candidate = track.label_since = None
                if observed.handedness is None or observed.handedness == track.handedness:
                    track.label_candidate = track.label_since = None
                elif track.handedness is None:
                    track.handedness = observed.handedness
                elif observed.handedness != track.label_candidate:
                    track.label_candidate, track.label_since = observed.handedness, now
                elif now - track.label_since >= HANDEDNESS_STABLE_SECONDS:
                    track.handedness = observed.handedness
                    track.label_candidate = track.label_since = None
            else:
                track.label_candidate = track.label_since = None
            track.center = observed.center
            track.last_seen = now
            track.visible = True
            track.can_continue = row not in ambiguous
            visible.append(TrackedHand(track.track_id, track.effect_id, observed.hand,
                                       track.handedness, bool(continuous)))
            matched_columns.add(column)
        for column, observed in enumerate(observations):
            if column in matched_columns:
                continue
            if len(self.tracks) >= self.max_hands:
                continue
            used_effects = {track.effect_id for track in self.tracks.values()}
            effect = self.rng.choice([index for index in range(8) if index not in used_effects])
            track = _TrackState(self._next_id, effect, observed.center, observed.shape,
                                observed.scale, observed.handedness, now)
            self._next_id += 1
            self.tracks[track.track_id] = track
            visible.append(TrackedHand(track.track_id, track.effect_id, observed.hand,
                                       observed.handedness, False))
        return tuple(sorted(visible, key=lambda value: value.track_id))
