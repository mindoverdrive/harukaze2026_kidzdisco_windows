"""Managed skeleton scene with separate pose ownership and restrained trails."""

import argparse
import atexit
import colorsys
from contextlib import ExitStack
import json
import math
import random
import socket
import sys
import time

import cv2
import mediapipe as mp
import pygame

import display_utils
from scene_control import notify_exit_request, notify_first_frame
from skeleton_people import Body, SkeletonPeople, person_roi


CAMERA_FAILURE_TIMEOUT_SECONDS = 1.0
VELOCITY_THRESHOLD = 0.005
GLITCH_INTENSITY = 10
NOISE_DENSITY = 0.1


def _person_roi_from_detection(detection, frame_w, frame_h):
    box = detection.location_data.relative_bounding_box
    return person_roi((box.xmin, box.ymin, box.width, box.height), frame_w, frame_h)


def glitch_palette(now):
    shift = math.sin(now * math.tau / 90.0) * 0.045
    return tuple(tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb((hue + shift) % 1, 1, 1))
                 for hue in (0.5, 5 / 6, 1 / 6))


def trail_lifetime(now):
    return 0.26 + 0.09 * math.sin(now * math.tau / 70.0)


def draw_skeletons(screen, bodies, camera_layout, connections, now, rng=random):
    screen.fill((0, 0, 0))
    palette = glitch_palette(now)
    lifetime = trail_lifetime(now)

    def stage(points):
        return tuple(display_utils.normalized_to_stage(x, y, camera_layout) for x, y in points)

    # All current bodies follow all trails, including other people's trails.
    for body in bodies:
        for stamp, old_points in body.trail:
            remaining = max(0.0, 1.0 - max(0.0, now - stamp) / lifetime)
            if remaining <= 0:
                continue
            color = tuple(round(channel * remaining) for channel in (29, 38, 48))
            points = stage(old_points)
            for start, end in connections:
                if start < len(points) and end < len(points):
                    pygame.draw.line(screen, color, points[start], points[end], 1)
    for body in bodies:
        points = stage(body.points)
        for start, end in connections:
            if start >= len(points) or end >= len(points):
                continue
            first, last = points[start], points[end]
            speed = (body.velocities[start] + body.velocities[end]) / 2
            if speed <= VELOCITY_THRESHOLD:
                pygame.draw.line(screen, (200, 200, 200), first, last, 2)
                continue
            factor = min(speed * 100, 5)
            for color in palette:
                dx = int(rng.randint(-GLITCH_INTENSITY, GLITCH_INTENSITY) * factor)
                dy = int(rng.randint(-GLITCH_INTENSITY // 2, GLITCH_INTENSITY // 2) * factor)
                pygame.draw.line(screen, color, (first[0] + dx, first[1] + dy),
                                 (last[0] + dx, last[1] + dy), rng.randint(1, 4))
            if rng.random() < NOISE_DENSITY * min(speed * 50, 5.0):
                cx, cy = (first[0] + last[0]) // 2, (first[1] + last[1]) // 2
                rect = (cx + rng.randint(-50, 50), cy + rng.randint(-50, 50),
                        rng.randint(20, 100), rng.randint(1, 4))
                pygame.draw.rect(screen, rng.choice(((255, 255, 255), *palette)), rect)
        for index, point in enumerate(points):
            if body.velocities[index] > VELOCITY_THRESHOLD:
                radius = rng.randint(3, 8)
                for color in palette[:2]:
                    pygame.draw.circle(screen, color,
                                       (point[0] + rng.randint(-5, 5), point[1] + rng.randint(-5, 5)), radius, 1)
            else:
                pygame.draw.circle(screen, (255, 255, 255), point, 4)


def main():
    resources = ExitStack()
    atexit.register(resources.close)
    try:
        resources.callback(pygame.quit)
        pygame.init()
        screen, _size = display_utils.setup_pygame_fullscreen()
        width, height = screen.get_size()
        clock = pygame.time.Clock()
        face_detector = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)
        resources.callback(face_detector.close)
        people = SkeletonPeople(lambda: mp.solutions.pose.Pose(
            min_detection_confidence=0.5, min_tracking_confidence=0.5, model_complexity=2))
        resources.callback(people.close)
        cap = display_utils.open_camera()
        if cap is not None:
            resources.callback(cap.release)
        if cap is None or not cap.isOpened():
            raise RuntimeError("The shared camera could not be attached")
        failure_since = None
        camera_layout = None
        last_frame_id = None
        last_fresh_time = None
        bodies = []
        running = True
        connections = tuple(mp.solutions.pose.POSE_CONNECTIONS)
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
            now = time.monotonic()
            ret, frame = cap.read()
            frame_processed = False
            if not ret or frame is None:
                people.invalidate_motion()
                bodies = [Body(body.track_id, body.points, (0.0,) * len(body.points)) for body in bodies]
                if failure_since is None:
                    failure_since = now
                if now - failure_since >= CAMERA_FAILURE_TIMEOUT_SECONDS:
                    notify_exit_request("camera_read_failed_timeout")
                    break
            else:
                failure_since = None
                frame_id = getattr(cap, "last_read_frame_id", None)
                duplicate = type(frame_id) is int and frame_id == last_frame_id
                if duplicate and last_fresh_time is not None and now - last_fresh_time >= CAMERA_FAILURE_TIMEOUT_SECONDS:
                    notify_exit_request("camera_read_failed_timeout")
                    break
                if not duplicate:
                    camera_frame, _stage_frame, camera_layout = display_utils.prepare_camera_frame(frame, width, height)
                    rgb_frame = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB)
                    result = face_detector.process(rgb_frame)
                    bodies = people.update(rgb_frame, getattr(result, "detections", None), now)
                    frame_processed = True
                    last_fresh_time = now
                    last_frame_id = frame_id if type(frame_id) is int else None
            draw_skeletons(screen, bodies, camera_layout, connections, now)
            pygame.display.flip()
            notify_first_frame(cap, frame_processed=frame_processed)
            clock.tick(60)
    finally:
        try:
            resources.__exit__(*sys.exc_info())
        finally:
            atexit.unregister(resources.close)


def wait_for_legacy_start(port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        while True:
            data, _address = sock.recvfrom(1024)
            try:
                message = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeError):
                continue
            if isinstance(message, dict) and message.get("cmd") == "START":
                return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", action="store_true", help="Wait for START signal via UDP")
    parser.add_argument("--port", type=int, default=0, help="UDP START port")
    args, _remaining = parser.parse_known_args()
    if args.wait and args.port > 0:
        wait_for_legacy_start(args.port)
    main()
