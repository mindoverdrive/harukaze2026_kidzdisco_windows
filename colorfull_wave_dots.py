"""A fingertip-driven wave grid, prepared for the managed Acer scene runtime."""

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
from scene_control import notify_exit_request, notify_first_frame


PARTICLE_SPACING = 15
FINGERTIP_IDS = (4, 8, 12, 16, 20)
CAMERA_FAILURE_TIMEOUT_SECONDS = 1.0


def create_particles(width, height, spacing=PARTICLE_SPACING):
    return [
        {"x": x, "y": y, "ox": x, "oy": y, "vx": 0.0, "vy": 0.0, "pinch_effect": 0.0}
        for x in range(0, width, spacing)
        for y in range(0, height, spacing)
    ]


def collect_active_fingertips(results, width, height, camera_layout=None):
    active = []
    for hand_landmarks in getattr(results, "multi_hand_landmarks", None) or ():
        index_tip = hand_landmarks.landmark[8]
        thumb_tip = hand_landmarks.landmark[4]
        pinching = math.hypot(index_tip.x - thumb_tip.x, index_tip.y - thumb_tip.y) < 0.05
        for tip_id in FINGERTIP_IDS:
            fingertip = hand_landmarks.landmark[tip_id]
            if camera_layout is None:
                position = (int(fingertip.x * width), int(fingertip.y * height))
            else:
                position = display_utils.normalized_to_stage(
                    fingertip.x, fingertip.y, camera_layout
                )
            active.append({"x": position[0], "y": position[1], "down": pinching})
    return active


def update_particle(particle, active_fingertips):
    vx_add = 0.0
    vy_add = 0.0
    for fingertip in active_fingertips:
        dx = fingertip["x"] - particle["x"]
        dy = fingertip["y"] - particle["y"]
        distance = math.hypot(dx, dy)
        if distance < 75:
            angle = math.atan2(dy, dx)
            force = (75 - distance) * 0.4
            if fingertip["down"]:
                force *= 5
                particle["pinch_effect"] = 1.0
            vx_add -= math.cos(angle) * force
            vy_add -= math.sin(angle) * force

    # Keep the original operation order so the established particle motion stays exact.
    particle["vx"] += vx_add
    particle["vy"] += vy_add
    particle["vx"] += (particle["ox"] - particle["x"]) * 0.05
    particle["vy"] += (particle["oy"] - particle["y"]) * 0.05
    particle["vx"] *= 0.92
    particle["vy"] *= 0.92
    particle["x"] += particle["vx"]
    particle["y"] += particle["vy"]
    if particle["pinch_effect"] > 0:
        particle["pinch_effect"] -= 0.05
        if particle["pinch_effect"] < 0:
            particle["pinch_effect"] = 0.0


def particle_color(particle):
    distance = math.hypot(particle["x"] - particle["ox"], particle["y"] - particle["oy"])
    distance_factor = min(1.0, distance / 100.0)
    base_hue = 20 + 30 * (1.0 - distance_factor)
    base_saturation = 70 + 30 * distance_factor
    base_brightness = 90 + 10 * (1.0 - distance_factor)
    pinch_hue = 240 - 30 * (1.0 - distance_factor)
    pinch_saturation = 80 + 20 * distance_factor
    pinch_brightness = 40 + 50 * (1.0 - distance_factor)
    if distance < 5:
        base_hue = 180
        base_saturation = 20
        base_brightness = 60

    effect = particle["pinch_effect"]
    hue = base_hue * (1.0 - effect) + pinch_hue * effect
    saturation = base_saturation * (1.0 - effect) + pinch_saturation * effect
    brightness = base_brightness * (1.0 - effect) + pinch_brightness * effect
    color = pygame.Color(0)
    color.hsva = (int(hue) % 360, int(saturation), int(brightness), 100)
    return color, hue, saturation, brightness


def draw_particle(screen, particle):
    color, hue, saturation, brightness = particle_color(particle)
    if particle["pinch_effect"] <= 0:
        pygame.draw.rect(screen, color, (int(particle["x"]), int(particle["y"]), 2, 2))
        return

    effect = particle["pinch_effect"]
    eased = effect**0.5
    center = (int(particle["x"]), int(particle["y"]))
    core_color = pygame.Color(0)
    core_color.hsva = (
        int(hue) % 360,
        max(0, int(saturation - 70 * eased)),
        min(100, int(brightness + 60 * eased)),
        100,
    )
    outer_radius = int(2 + eased * 12)
    if outer_radius > 2:
        pygame.draw.circle(screen, color, center, outer_radius, max(1, int(effect * 3)))
    pygame.draw.circle(screen, core_color, center, int(2 + eased * 4))
    if effect > 0.4:
        line_length = eased * 16
        pygame.draw.line(
            screen, core_color,
            (int(center[0] - line_length), center[1]),
            (int(center[0] + line_length), center[1]), 2,
        )
        pygame.draw.line(
            screen, core_color,
            (center[0], int(center[1] - line_length)),
            (center[0], int(center[1] + line_length)), 2,
        )
        diagonal = line_length * 0.7
        pygame.draw.line(
            screen, core_color,
            (int(center[0] - diagonal), int(center[1] - diagonal)),
            (int(center[0] + diagonal), int(center[1] + diagonal)), 1,
        )
        pygame.draw.line(
            screen, core_color,
            (int(center[0] - diagonal), int(center[1] + diagonal)),
            (int(center[0] + diagonal), int(center[1] - diagonal)), 1,
        )


def main():
    resources = ExitStack()
    atexit.register(resources.close)
    try:
        resources.callback(pygame.quit)
        pygame.init()
        screen, _stage_size = display_utils.setup_pygame_fullscreen()
        width, height = screen.get_size()
        clock = pygame.time.Clock()

        hands = mp.solutions.hands.Hands(
            model_complexity=1,
            max_num_hands=5,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5,
        )
        resources.callback(hands.close)
        cap = display_utils.open_camera()
        if cap is not None:
            resources.callback(cap.release)
        if cap is None or not cap.isOpened():
            raise RuntimeError("The shared camera could not be attached")

        particles = create_particles(width, height)
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
            if not ret or frame is None:
                now = time.monotonic()
                if camera_failure_since is None:
                    camera_failure_since = now
                if now - camera_failure_since >= CAMERA_FAILURE_TIMEOUT_SECONDS:
                    notify_exit_request("camera_read_failed_timeout")
                    break
                clock.tick(60)
                continue
            camera_failure_since = None

            camera_frame, stage_frame, camera_layout = display_utils.prepare_camera_frame(
                frame, width, height
            )
            results = hands.process(cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB))
            active_fingertips = collect_active_fingertips(
                results, width, height, camera_layout
            )
            stage_rgb = cv2.cvtColor(stage_frame, cv2.COLOR_BGR2RGB)
            camera_surface = pygame.image.frombuffer(stage_rgb.tobytes(), (width, height), "RGB")

            screen.blit(camera_surface, (0, 0))
            for particle in particles:
                update_particle(particle, active_fingertips)
                draw_particle(screen, particle)
            pygame.display.flip()
            notify_first_frame(cap, frame_processed=True)
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
        print(f"[Scene] Started in PRELOAD mode. Waiting for START command on port {port}...")
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
    parser.add_argument("--port", type=int, default=0, help="UDP port for the START signal")
    arguments, _remaining = parser.parse_known_args()
    if arguments.wait and arguments.port > 0:
        wait_for_legacy_start(arguments.port)
    main()
