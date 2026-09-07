import argparse
import atexit
from contextlib import ExitStack
import json
import math
import socket
import sys
import time

import cv2
import mediapipe as mp
import pygame

import display_utils
from mandala_colors import ArtworkHueCycle
from mandala_motion import ArtworkOutwardDrift
from scene_control import notify_exit_request, notify_first_frame


PARTICIPANT_HUE_OFFSETS = (0, 120, 240)


class ParticipantTracker:
    """Keep up to six hands in three spatial participant groups."""

    def __init__(self, max_people=3, max_missing_frames=30):
        self.max_people = max_people
        self.max_missing_frames = max_missing_frames
        self.frame_index = 0
        self.next_track_id = 0
        self.tracks = []

    def update(self, detections, stage_width):
        self.frame_index += 1
        self.tracks = [track for track in self.tracks
                       if self.frame_index - track["last_frame"] <= self.max_missing_frames]
        detections = self._deduplicate(detections, stage_width)
        matches = {}
        used_tracks = set()
        limit = max(90.0, stage_width * 0.24)
        candidates = []
        for detection_index, detection in enumerate(detections):
            for track_index, track in enumerate(self.tracks):
                if detection.get("label") and track.get("label") and detection["label"] != track["label"]:
                    continue
                distance = math.dist(detection["anchor"], track["anchor"])
                if distance <= limit:
                    candidates.append((distance, detection_index, track_index))
        for _distance, detection_index, track_index in sorted(candidates):
            if detection_index not in matches and track_index not in used_tracks:
                matches[detection_index] = track_index
                used_tracks.add(track_index)

        active = []
        occupied = {}
        for detection_index, track_index in matches.items():
            detection = detections[detection_index]
            track = self.tracks[track_index]
            previous = track["tip"] if track["last_frame"] == self.frame_index - 1 else None
            track.update(anchor=detection["anchor"], tip=detection["tip"],
                         label=detection.get("label"), last_frame=self.frame_index)
            occupied.setdefault(track["participant"], set()).add(detection.get("label"))
            active.append(self._result(track, previous))

        unmatched = [index for index in range(len(detections)) if index not in matches]
        groups = []
        remaining = []
        for detection_index in unmatched:
            group = (detection_index,)
            participant = self._existing_participant_for_group(
                group, detections, occupied, stage_width)
            if participant is None:
                remaining.append(detection_index)
            else:
                groups.append((group, participant))
                occupied.setdefault(participant, set()).add(
                    detections[detection_index].get("label"))
        for group in self._pair_new_hands(remaining, detections, stage_width):
            participant = self._participant_for_group(group, detections, occupied, stage_width)
            if participant is None:
                continue
            groups.append((group, participant))
            occupied.setdefault(participant, set()).update(
                detections[index].get("label") for index in group)

        for group, participant in groups:
            for detection_index in group:
                detection = detections[detection_index]
                track = {
                    "track_id": self.next_track_id,
                    "participant": participant,
                    "anchor": detection["anchor"],
                    "tip": detection["tip"],
                    "label": detection.get("label"),
                    "last_frame": self.frame_index,
                }
                self.next_track_id += 1
                self.tracks.append(track)
                active.append(self._result(track, None))
        return sorted(active, key=lambda item: item["track_id"])

    def _deduplicate(self, detections, stage_width):
        unique = []
        threshold = max(45.0, stage_width * 0.04)
        for detection in detections:
            is_duplicate = any(
                (not detection.get("label") or not existing.get("label")
                 or detection.get("label") == existing.get("label"))
                and math.dist(detection["anchor"], existing["anchor"]) < threshold
                and math.dist(detection["tip"], existing["tip"]) < threshold
                for existing in unique
            )
            if not is_duplicate:
                unique.append(detection)
        return unique

    @staticmethod
    def _pair_new_hands(indices, detections, stage_width):
        remaining = set(indices)
        groups = []
        pair_limit = max(180.0, stage_width * 0.65)
        while True:
            pairs = []
            for left in remaining:
                for right in remaining:
                    if left >= right:
                        continue
                    labels = {detections[left].get("label"), detections[right].get("label")}
                    distance = math.dist(detections[left]["anchor"],
                                         detections[right]["anchor"])
                    if labels == {"Left", "Right"} and distance <= pair_limit:
                        pairs.append((distance, left, right))
            if not pairs:
                break
            _distance, left, right = min(pairs)
            groups.append((left, right))
            remaining.remove(left)
            remaining.remove(right)
        groups.extend((index,) for index in sorted(remaining))
        return groups

    def _existing_participant_for_group(self, group, detections, occupied, stage_width):
        centers = {}
        participant_labels = {}
        for track in self.tracks:
            if self.frame_index - track["last_frame"] <= self.max_missing_frames:
                centers.setdefault(track["participant"], []).append(track["anchor"])
                participant_labels.setdefault(track["participant"], set()).add(track.get("label"))
        labels = {detections[index].get("label") for index in group}
        anchor = (sum(detections[index]["anchor"][0] for index in group) / len(group),
                  sum(detections[index]["anchor"][1] for index in group) / len(group))
        compatible = []
        for participant, points in centers.items():
            used_labels = participant_labels.get(participant, set()) | occupied.get(participant, set())
            if len(used_labels) + len(group) > 2 or labels.intersection(used_labels):
                continue
            cx = sum(point[0] for point in points) / len(points)
            cy = sum(point[1] for point in points) / len(points)
            distance = math.dist(anchor, (cx, cy))
            if distance <= stage_width * 0.24:
                compatible.append((distance, participant))
        if compatible:
            return min(compatible)[1]
        return None

    def _participant_for_group(self, group, detections, occupied, stage_width):
        existing = self._existing_participant_for_group(
            group, detections, occupied, stage_width)
        if existing is not None:
            return existing
        anchor = (sum(detections[index]["anchor"][0] for index in group) / len(group),
                  sum(detections[index]["anchor"][1] for index in group) / len(group))
        preferred = min(self.max_people - 1, max(0, int(anchor[0] * self.max_people / stage_width)))
        used = set(occupied) | {track["participant"] for track in self.tracks}
        if preferred not in used:
            return preferred
        free = [participant for participant in range(self.max_people) if participant not in used]
        if free:
            return min(free, key=lambda value: abs(value - preferred))

        # All colors are reserved. Reuse only an absent participant's oldest
        # reservation; never overwrite a participant visible in this frame.
        reusable = [participant for participant in range(self.max_people)
                    if participant not in occupied]
        if not reusable:
            return None
        latest_frame = {
            participant: max(track["last_frame"] for track in self.tracks
                             if track["participant"] == participant)
            for participant in reusable
        }
        participant = min(reusable, key=lambda value: (latest_frame[value], value))
        self.tracks = [track for track in self.tracks
                       if track["participant"] != participant]
        return participant

    @staticmethod
    def _result(track, previous):
        return {"track_id": track["track_id"], "participant": track["participant"],
                "previous": previous, "current": track["tip"]}


def draw_mandala(canvas, previous, current, center, color, axis_angle=0.0):
    """Keep the existing twelve rotations and their mirrored strokes."""
    cx, cy = center
    for index in range(12):
        angle = axis_angle + math.tau * index / 12
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        for mirror in (1, -1):
            end = (
                current[0] * mirror * cos_a - current[1] * sin_a + cx,
                current[0] * mirror * sin_a + current[1] * cos_a + cy,
            )
            if previous is None:
                pygame.draw.circle(canvas, color, (round(end[0]), round(end[1])), 2)
            else:
                start = (
                    previous[0] * mirror * cos_a - previous[1] * sin_a + cx,
                    previous[0] * mirror * sin_a + previous[1] * cos_a + cy,
                )
                pygame.draw.line(canvas, color, start, end, 2)


def main():
    resources = ExitStack()
    atexit.register(resources.close)
    try:
        resources.callback(pygame.quit)
        pygame.init()
        screen, _pg_size = display_utils.setup_pygame_fullscreen()
        w, h = screen.get_size()
        clock = pygame.time.Clock()

        hands = mp.solutions.hands.Hands(
            model_complexity=1,
            max_num_hands=6,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5,
        )
        resources.callback(hands.close)
        cap = display_utils.open_camera()
        if cap is not None:
            resources.callback(cap.release)
        if cap is None or not cap.isOpened():
            raise RuntimeError("The shared camera could not be attached")

        # Artwork persists; only the separate cursor layer is cleared each frame.
        canvas = pygame.Surface((w, h), pygame.SRCALPHA)
        canvas.fill((0, 0, 0, 0))
        cursor_layer = pygame.Surface((w, h), pygame.SRCALPHA)
        artwork_colors = ArtworkHueCycle((w, h))
        artwork_drift = ArtworkOutwardDrift((w, h))
        hue = 0
        tracker = ParticipantTracker(max_people=3)
        camera_failure_since = None
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    notify_exit_request("pygame_quit")
                    running = False
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                    notify_exit_request("key_escape" if event.key == pygame.K_ESCAPE else "key_q")
                    running = False
            if not running:
                break

            ret, frame = cap.read()
            if not ret:
                # Do not connect strokes across a missing camera observation.
                tracker.update([], w)
                now = time.monotonic()
                if camera_failure_since is None:
                    camera_failure_since = now
                if now - camera_failure_since >= 1.0:
                    notify_exit_request("camera_read_failed_timeout")
                    break
                clock.tick(60)
                continue
            camera_failure_since = None

            frame, stage_frame, camera_layout = display_utils.prepare_camera_frame(frame, w, h)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            stage_rgb = cv2.cvtColor(stage_frame, cv2.COLOR_BGR2RGB)
            camera_surface = pygame.image.frombuffer(stage_rgb.tobytes(), (w, h), "RGB")
            results = hands.process(rgb_frame)

            cursor_layer.fill((0, 0, 0, 0))
            hue = (hue + 1) % 360
            labels = []
            for handedness in getattr(results, "multi_handedness", None) or ():
                classifications = getattr(handedness, "classification", None) or ()
                labels.append(classifications[0].label if classifications else None)
            detections = []
            for index, hand in enumerate(results.multi_hand_landmarks or ()):
                fingertip, wrist = hand.landmark[8], hand.landmark[0]
                tip = display_utils.normalized_to_stage(fingertip.x, fingertip.y, camera_layout)
                anchor = display_utils.normalized_to_stage(wrist.x, wrist.y, camera_layout)
                detections.append({"tip": tip, "anchor": anchor,
                                   "label": labels[index] if index < len(labels) else None})
            tracked_hands = tracker.update(detections, w)
            axis_angle = pygame.time.get_ticks() / 1000.0 * 0.035
            artwork_now = pygame.time.get_ticks() / 1000.0
            artwork_drift.advance(canvas, artwork_colors.surface, artwork_now)
            colored_canvas = artwork_colors.refresh(canvas, artwork_now)
            for tracked in tracked_hands:
                participant = tracked["participant"]
                color = pygame.Color(0)
                color.hsva = ((hue + PARTICIPANT_HUE_OFFSETS[participant]) % 360, 100, 100, 100)
                current = tracked["current"]
                current_pos = (current[0] - w // 2, current[1] - h // 2)
                previous = tracked["previous"]
                previous_pos = None if previous is None else (
                    previous[0] - w // 2, previous[1] - h // 2)
                draw_mandala(canvas, previous_pos, current_pos, (w // 2, h // 2), color, axis_angle)

                # New strokes appear immediately; recoloring older ink is cached.
                shown_color = artwork_colors.display_color(color)
                draw_mandala(colored_canvas, previous_pos, current_pos, (w // 2, h // 2), shown_color, axis_angle)

                cursor_pos = (round(current[0]), round(current[1]))
                cursor_color = (shown_color.r, shown_color.g, shown_color.b)
                pygame.draw.circle(cursor_layer, (*cursor_color, 65), cursor_pos, 15)
                pygame.draw.circle(cursor_layer, (*cursor_color, 210), cursor_pos, 11, 2)
                pygame.draw.circle(cursor_layer, (255, 255, 255, 255), cursor_pos, 4)

            screen.blit(camera_surface, (0, 0))
            screen.blit(colored_canvas, (0, 0))
            screen.blit(cursor_layer, (0, 0))
            pygame.display.flip()
            notify_first_frame(cap, frame_processed=True)
            clock.tick(120)
    finally:
        try:
            resources.__exit__(*sys.exc_info())
        finally:
            atexit.unregister(resources.close)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", action="store_true", help="Wait for START signal via UDP")
    parser.add_argument("--port", type=int, default=0, help="UDP port to listen on for START signal")
    args, _ = parser.parse_known_args()
    if args.wait and args.port > 0:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", args.port))
            print(f"[Scene] Started in PRELOAD mode. Waiting for START command on port {args.port}...")
            while True:
                data, _ = sock.recvfrom(1024)
                try:
                    message = json.loads(data.decode("utf-8"))
                    if message.get("cmd") == "START":
                        break
                except (ValueError, UnicodeError):
                    continue
    main()
