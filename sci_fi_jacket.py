"""Live garment-color patterns for the shared-camera audience scene."""

import argparse
import atexit
from contextlib import ExitStack
import json
import socket
import sys
import time

import cv2
import display_utils
import mediapipe as mp
import pygame

from jacket_effect import JacketFlow, blend_on_stage
from scene_control import notify_exit_request, notify_first_frame


CAMERA_FAILURE_TIMEOUT_SECONDS = 1.0
PROCESSING_LIMIT = 640


def processing_frame(frame):
    height, width = frame.shape[:2]
    scale = min(1.0, PROCESSING_LIMIT / max(width, height))
    if scale == 1.0:
        return frame
    return cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))),
                      interpolation=cv2.INTER_AREA)


def main():
    resources = ExitStack()
    atexit.register(resources.close)
    try:
        resources.callback(pygame.quit)
        pygame.init()
        screen, _stage_size = display_utils.setup_pygame_fullscreen()
        pygame.display.set_caption("Sci-Fi Jacket")
        width, height = screen.get_size()
        cap = display_utils.open_camera()
        if cap is not None:
            resources.callback(cap.release)
        if cap is None or not cap.isOpened():
            raise RuntimeError("The shared camera could not be attached")
        segmentation = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1)
        resources.callback(segmentation.close)
        clock = pygame.time.Clock()
        effect = None
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
            now = time.monotonic()
            frame_processed = False
            camera_surface = None
            if not ret or frame is None:
                if effect is not None:
                    effect.clear()
                if camera_failure_since is None:
                    camera_failure_since = now
                if now - camera_failure_since >= CAMERA_FAILURE_TIMEOUT_SECONDS:
                    notify_exit_request("camera_read_failed_timeout")
                    break
            else:
                camera_failure_since = None
                camera_frame, stage_frame, layout = display_utils.prepare_camera_frame(frame, width, height)
                small = processing_frame(camera_frame)
                size = (small.shape[1], small.shape[0])
                if effect is None or effect.size != size:
                    effect = JacketFlow(size)
                result = segmentation.process(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
                pattern, alpha = effect.render(small, getattr(result, "segmentation_mask", None), now)
                output = blend_on_stage(stage_frame, pattern, alpha, layout)
                rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
                camera_surface = pygame.image.frombuffer(rgb.tobytes(), (width, height), "RGB")
                frame_processed = True
            screen.fill((0, 0, 0))
            if camera_surface is not None:
                screen.blit(camera_surface, (0, 0))
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
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    arguments, _remaining = parser.parse_known_args()
    if arguments.wait and arguments.port > 0:
        wait_for_legacy_start(arguments.port)
    main()
