"""Interactive colorful tree, prepared for the managed Acer scene runtime."""

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


FINGER_PARAMS = {
    0: (0.7, 0.75, 7),
    1: (0.7, 0.75, 8),
    2: (0.7, 0.75, 9),
    3: (0.7, 0.75, 10),
    4: (0.7, 0.75, 11),
    5: (0.7, 0.75, 12),
}
LERP_SPEED = 3.0
TARGET_LERP_SPEED = 5.0
CAMERA_FAILURE_TIMEOUT_SECONDS = 1.0


def count_raised_fingers(hand_landmarks):
    tips = (4, 8, 12, 16, 20)
    pips = (3, 6, 10, 14, 18)
    thumb_tip = hand_landmarks.landmark[4]
    index_mcp = hand_landmarks.landmark[5]
    wrist = hand_landmarks.landmark[0]
    middle_mcp = hand_landmarks.landmark[9]

    count = 0
    if middle_mcp.x - wrist.x > 0:
        if thumb_tip.x > index_mcp.x + 0.01:
            count += 1
    elif thumb_tip.x < index_mcp.x - 0.01:
        count += 1
    for index in range(1, 5):
        if hand_landmarks.landmark[tips[index]].y < hand_landmarks.landmark[pips[index]].y:
            count += 1
    return max(0, min(5, count))


def _stage_position(landmark, width, height, camera_layout):
    if camera_layout is None:
        return int(landmark.x * width), int(landmark.y * height)
    return display_utils.normalized_to_stage(landmark.x, landmark.y, camera_layout)


def _mirrored_stage_x(x, width, camera_layout):
    if camera_layout is None:
        return width - x
    left = camera_layout["offset_x"]
    right = left + camera_layout["scaled_width"] - 1
    return left + right - x


def choose_single_hand_base_path(current_path, wrist_x):
    """Keep branch ownership stable near the center while allowing deliberate side changes."""
    if current_path == "L":
        return "R" if wrist_x > 0.6 else "L"
    if current_path == "R":
        return "L" if wrist_x < 0.4 else "R"
    return "R" if wrist_x >= 0.5 else "L"


def get_raised_fingers_dict(hand_landmarks, width, height, camera_layout=None):
    tips = (4, 8, 12, 16, 20)
    pips = (3, 6, 10, 14, 18)
    wrist = hand_landmarks.landmark[0]
    middle_mcp = hand_landmarks.landmark[9]
    thumb_tip = hand_landmarks.landmark[4]
    index_mcp = hand_landmarks.landmark[5]
    raised = {}

    if middle_mcp.x - wrist.x > 0:
        if thumb_tip.x > index_mcp.x + 0.01:
            raised[0] = _stage_position(thumb_tip, width, height, camera_layout)
    elif thumb_tip.x < index_mcp.x - 0.01:
        raised[0] = _stage_position(thumb_tip, width, height, camera_layout)

    if hand_landmarks.landmark[tips[1]].y < hand_landmarks.landmark[pips[1]].y:
        raised[1] = _stage_position(hand_landmarks.landmark[tips[1]], width, height, camera_layout)
    return raised


def lerp(current, target, speed, dt):
    difference = target - current
    step = speed * dt
    if abs(difference) < 0.001:
        return target
    return current + difference * min(step, 1.0)


def lerp2d(current_position, target_position, speed, dt):
    return (
        int(lerp(current_position[0], target_position[0], speed, dt)),
        int(lerp(current_position[1], target_position[1], speed, dt)),
    )


def draw_tree(
    screen,
    x,
    y,
    angle,
    depth,
    length,
    color_hue,
    base_spread_angle,
    branch_ratio,
    path,
    finger_targets,
    primary_side="",
):
    if depth <= 0:
        return

    current_angle = angle
    spread_scale = 1.0
    target_position = finger_targets.get(path)
    if target_position:
        target_x, target_y = target_position
        dx = target_x - x
        dy = -(target_y - y)
        distance = math.hypot(dx, dy)
        if distance > 0.1:
            current_angle = math.atan2(dy, dx)
            spread_scale = max(0.2, distance / (length + 1e-6))
            length = distance

    x2 = x + math.cos(current_angle) * length
    y2 = y - math.sin(current_angle) * length
    color = pygame.Color(0)
    final_hue = (color_hue + 180) % 360 if path.startswith("L") else color_hue
    color.hsva = (final_hue % 360, 100, 100, 100)
    pygame.draw.line(screen, color, (x, y), (x2, y2), max(1, int(depth * 1.2)))
    if target_position and path.startswith(primary_side):
        pygame.draw.circle(screen, (255, 255, 255), target_position, 8, 0)

    next_length = length * branch_ratio
    actual_spread = base_spread_angle * spread_scale
    draw_tree(
        screen, x2, y2, current_angle - actual_spread, depth - 1, next_length,
        color_hue + 2, base_spread_angle, branch_ratio, path + "L", finger_targets,
        primary_side,
    )
    draw_tree(
        screen, x2, y2, current_angle + actual_spread, depth - 1, next_length,
        color_hue + 18, base_spread_angle, branch_ratio, path + "R", finger_targets,
        primary_side,
    )


def main():
    resources = ExitStack()
    atexit.register(resources.close)
    try:
        resources.callback(pygame.quit)
        pygame.init()
        screen, _stage_size = display_utils.setup_pygame_fullscreen()
        width, height = screen.get_size()

        hands = mp.solutions.hands.Hands(
            model_complexity=1,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5,
        )
        resources.callback(hands.close)
        cap = display_utils.open_camera()
        if cap is not None:
            resources.callback(cap.release)
        if cap is None or not cap.isOpened():
            raise RuntimeError("The shared camera could not be attached")
        clock = pygame.time.Clock()

        current_spread_multiplier = 0.55
        current_branch_ratio = 0.76
        current_max_depth = 10.0
        detected_fingers = 2
        smooth_targets = {}
        multi_hand_centers = {}
        multi_hand_specs = []
        single_hand_base_path = None
        camera_surface = None
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

            dt = clock.get_time() / 1000.0
            finger_targets = {}
            base_path = ""
            target_spread, target_ratio, target_depth = FINGER_PARAMS[2]
            ret, frame = cap.read()
            frame_processed = False
            if not ret or frame is None:
                now = time.monotonic()
                if camera_failure_since is None:
                    camera_failure_since = now
                if now - camera_failure_since >= CAMERA_FAILURE_TIMEOUT_SECONDS:
                    notify_exit_request("camera_read_failed_timeout")
                    break
            else:
                camera_failure_since = None
                camera_frame, stage_frame, camera_layout = display_utils.prepare_camera_frame(
                    frame, width, height
                )
                results = hands.process(cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB))
                frame_processed = True
                stage_rgb = cv2.cvtColor(stage_frame, cv2.COLOR_BGR2RGB)
                camera_surface = pygame.image.frombuffer(
                    stage_rgb.tobytes(), (width, height), "RGB"
                )
                hands_list = list(getattr(results, "multi_hand_landmarks", None) or ())
                hands_list.sort(key=lambda hand: hand.landmark[0].x)
                multi_hand_specs = []
                if len(hands_list) > 1:
                    finger_counts = []
                    for hand_index, hand in enumerate(hands_list[:2]):
                        finger_count = count_raised_fingers(hand)
                        finger_counts.append(finger_count)
                        _spread, branch_ratio, max_depth = FINGER_PARAMS[finger_count]
                        wrist = hand.landmark[0]
                        palm = hand.landmark[9]
                        thumb = hand.landmark[4]
                        index_tip = hand.landmark[8]
                        target_center = _stage_position(wrist, width, height, camera_layout)
                        current_center = multi_hand_centers.get(hand_index, target_center)
                        center = lerp2d(current_center, target_center, TARGET_LERP_SPEED, dt)
                        multi_hand_centers[hand_index] = center
                        palm_position = _stage_position(palm, width, height, camera_layout)
                        dx = palm_position[0] - center[0]
                        dy = palm_position[1] - center[1]
                        angle = math.atan2(-dy, dx) if math.hypot(dx, dy) > 1 else math.pi / 2
                        openness = math.hypot(
                            thumb.x - index_tip.x, thumb.y - index_tip.y
                        )
                        spread_multiplier = max(0.35, min(0.85, 0.35 + openness * 1.5))
                        multi_hand_specs.append({
                            "center": center,
                            "angle": angle,
                            "depth": max(1, int(max_depth) - 2),
                            "ratio": branch_ratio,
                            "spread": (math.pi / 2) * spread_multiplier,
                            "hue_offset": hand_index * 120,
                        })
                elif hands_list:
                    first_hand = hands_list[0]
                    detected_fingers = count_raised_fingers(first_hand)
                    target_spread, target_ratio, target_depth = FINGER_PARAMS[detected_fingers]
                    control_hand = first_hand
                    wrist = control_hand.landmark[0]
                    single_hand_base_path = choose_single_hand_base_path(
                        single_hand_base_path, wrist.x
                    )
                    base_path = single_hand_base_path

                    raised = get_raised_fingers_dict(
                        control_hand, width, height, camera_layout
                    )
                    raised[-1] = _stage_position(wrist, width, height, camera_layout)
                    path_mapping = {-1: base_path, 0: base_path + "L", 1: base_path + "R"}
                    for finger_index, position in raised.items():
                        if finger_index not in path_mapping:
                            continue
                        primary_path = path_mapping[finger_index]
                        finger_targets[primary_path] = position
                        mirrored_path = "".join(
                            "L" if character == "R" else "R"
                            for character in primary_path
                        )
                        finger_targets[mirrored_path] = (
                            _mirrored_stage_x(position[0], width, camera_layout),
                            position[1],
                        )

            for path in list(smooth_targets):
                if path in finger_targets:
                    smooth_targets[path] = lerp2d(
                        smooth_targets[path], finger_targets[path], TARGET_LERP_SPEED, dt
                    )
            for path, position in finger_targets.items():
                if path not in smooth_targets:
                    smooth_targets[path] = position

            current_spread_multiplier = lerp(
                current_spread_multiplier, target_spread, LERP_SPEED, dt
            )
            current_branch_ratio = lerp(current_branch_ratio, target_ratio, LERP_SPEED, dt)
            current_max_depth = lerp(current_max_depth, float(target_depth), LERP_SPEED, dt)

            if camera_surface is None:
                screen.fill((0, 0, 0))
            else:
                screen.blit(camera_surface, (0, 0))
            center_x = width // 2
            center_y = height // 2
            fractal_depth = max(1, int(current_max_depth) - 1)
            fractal_length = height / 8
            color_hue = (pygame.time.get_ticks() / 20) % 360
            spread_angle = (math.pi / 2) * current_spread_multiplier
            if multi_hand_specs:
                for spec in multi_hand_specs:
                    for angle_offset, path in ((0, "L"), (math.pi, "R")):
                        draw_tree(
                            screen,
                            spec["center"][0],
                            spec["center"][1],
                            spec["angle"] + angle_offset,
                            spec["depth"],
                            height / 12,
                            color_hue + spec["hue_offset"],
                            spec["spread"],
                            spec["ratio"],
                            path,
                            {},
                            "",
                        )
            else:
                for angle, path in ((math.pi / 2, "L"), (-math.pi / 2, "R")):
                    draw_tree(
                        screen,
                        center_x,
                        center_y,
                        angle,
                        fractal_depth,
                        fractal_length,
                        color_hue,
                        spread_angle,
                        current_branch_ratio,
                        path,
                        smooth_targets,
                        base_path,
                    )
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
