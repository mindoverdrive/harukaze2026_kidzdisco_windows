"""Bounded, spatial face/pose ownership for the skeleton scene."""

from collections import deque
from contextlib import ExitStack
from dataclasses import dataclass, field
import math


def person_roi(box, frame_width, frame_height):
    x, y, width, height = box
    face_x, face_y = int(x * frame_width), int(y * frame_height)
    face_w, face_h = max(1, int(width * frame_width)), max(1, int(height * frame_height))
    center_x = face_x + face_w // 2
    roi_w = int(face_w * 3.8)
    left = max(0, center_x - roi_w // 2)
    right = min(frame_width, center_x + roi_w // 2)
    top = max(0, face_y - int(face_h * 0.8))
    bottom = min(frame_height, face_y + int(face_h * 6.0))
    return (left, top, right, bottom) if right - left >= 32 and bottom - top >= 32 else None


@dataclass
class Body:
    track_id: int
    points: tuple
    velocities: tuple
    trail: tuple = ()


@dataclass
class _Person:
    track_id: int
    box: tuple
    pose: object
    last_seen: float
    previous: tuple = ()
    last_frame: int = -1
    last_trail_time: float = -math.inf
    trail: deque = field(default_factory=lambda: deque(maxlen=2))

    def break_motion(self):
        self.previous = ()
        self.trail.clear()
        self.last_frame = -1
        self.last_trail_time = -math.inf


class SkeletonPeople:
    """Own a separate Pose and two old poses per spatially tracked face.

    This is not identity recognition. Ambiguous close encounters are omitted
    instead of linking different bodies' motion histories.
    """

    def __init__(self, pose_factory, max_people=3, missing_timeout=1.0):
        self.pose_factory = pose_factory
        self.max_people = max(1, min(3, int(max_people)))
        self.missing_timeout = float(missing_timeout)
        self.tracks = {}
        self.next_id = 0
        self.frame_index = 0

    def _retire(self, track_ids):
        removed = [self.tracks.pop(track_id) for track_id in track_ids if track_id in self.tracks]
        with ExitStack() as closing:
            for track in removed:
                closing.callback(track.pose.close)

    def close(self):
        self._retire(tuple(self.tracks))

    def invalidate_motion(self):
        for track in self.tracks.values():
            track.break_motion()

    @staticmethod
    def _center(box):
        return box[0] + box[2] / 2, box[1] + box[3] / 2

    @classmethod
    def _observations(cls, detections, width, height):
        observations = []
        for detection in list(detections or ())[:12]:
            bbox = detection.location_data.relative_bounding_box
            box = (bbox.xmin, bbox.ymin, bbox.width, bbox.height)
            if not all(math.isfinite(value) for value in box) or box[2] <= 0 or box[3] <= 0:
                continue
            roi = person_roi(box, width, height)
            if roi is None:
                continue
            if any(math.dist(cls._center(box), cls._center(other[0])) < min(box[2], other[0][2]) * 0.25
                   for other in observations):
                continue
            observations.append((box, roi))
        return observations

    def update(self, rgb_frame, detections, now):
        self.frame_index += 1
        self._retire([key for key, track in self.tracks.items()
                      if now - track.last_seen >= self.missing_timeout])
        height, width = rgb_frame.shape[:2]
        observations = self._observations(detections, width, height)
        candidates = []
        for index, (box, _roi) in enumerate(observations):
            for key, track in self.tracks.items():
                distance = math.dist(self._center(box), self._center(track.box))
                ratio = box[2] / track.box[2]
                if 0.5 <= ratio <= 2.0 and distance <= max(0.055, min(0.18, track.box[2] * 0.9)):
                    candidates.append((distance + abs(math.log(ratio)) * 0.025, index, key))
        ambiguous_observations, ambiguous_tracks = set(), set()
        for group_index in (1, 2):
            groups = {}
            for candidate in candidates:
                groups.setdefault(candidate[group_index], []).append(candidate)
            for group in groups.values():
                group.sort()
                if len(group) > 1 and group[1][0] - group[0][0] < 0.025:
                    for _cost, index, key in group:
                        ambiguous_observations.add(index)
                        ambiguous_tracks.add(key)
        # Propagate ambiguity across the small candidate component: otherwise
        # an observation tied to an ambiguous owner could create a duplicate.
        changed = True
        while changed:
            changed = False
            for _cost, index, key in candidates:
                if index in ambiguous_observations or key in ambiguous_tracks:
                    if index not in ambiguous_observations or key not in ambiguous_tracks:
                        ambiguous_observations.add(index)
                        ambiguous_tracks.add(key)
                        changed = True
        matches, used = {}, set()
        for _cost, index, key in sorted(candidates):
            if (index not in matches and key not in used and index not in ambiguous_observations
                    and key not in ambiguous_tracks):
                matches[index] = key
                used.add(key)
        for key, track in self.tracks.items():
            if key not in used:
                track.break_motion()
        for index, (box, _roi) in enumerate(observations):
            if index in matches or index in ambiguous_observations:
                continue
            if len(self.tracks) >= self.max_people:
                absent = [track for key, track in self.tracks.items()
                          if key not in used and key not in ambiguous_tracks]
                if not absent:
                    continue
                self._retire([min(absent, key=lambda track: track.last_seen).track_id])
            pose = self.pose_factory()
            key = self.next_id
            self.next_id += 1
            self.tracks[key] = _Person(key, box, pose, now)
            matches[index] = key
            used.add(key)
        bodies = []
        for index, key in sorted(matches.items()):
            box, (x0, y0, x1, y1) = observations[index]
            track = self.tracks[key]
            track.box, track.last_seen = box, now
            result = track.pose.process(rgb_frame[y0:y1, x0:x1])
            landmarks = getattr(getattr(result, "pose_landmarks", None), "landmark", None)
            if not landmarks:
                track.break_motion()
                continue
            points = tuple(((x0 + landmark.x * (x1 - x0)) / width,
                            (y0 + landmark.y * (y1 - y0)) / height) for landmark in landmarks)
            if not all(math.isfinite(value) for point in points for value in point):
                track.break_motion()
                continue
            previous = track.previous if track.last_frame == self.frame_index - 1 else ()
            velocities = tuple(math.dist(point, old) for point, old in zip(points, previous))
            if len(velocities) != len(points):
                velocities = (0.0,) * len(points)
            if previous and max(velocities, default=0.0) > 0.005 and now - track.last_trail_time >= 0.10:
                track.trail.append((now, previous))
                track.last_trail_time = now
            while track.trail and now - track.trail[0][0] > 0.36:
                track.trail.popleft()
            track.previous, track.last_frame = points, self.frame_index
            bodies.append(Body(key, points, velocities, tuple(track.trail)))
        return bodies
