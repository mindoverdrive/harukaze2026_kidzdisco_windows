# =============================================================================
# [AUTO-INJECTED] Scene Preload & Wait Logic
# =============================================================================
import sys
import argparse
import socket
import json

# Only execute the wait logic if we are running the script directly
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", action="store_true", help="Wait for START signal via UDP")
    parser.add_argument("--port", type=int, default=0, help="UDP port to listen on for START signal")
    # Parse known args so we don't crash if other args are passed
    args, _ = parser.parse_known_args()

    if args.wait and args.port > 0:
        print(f"[Scene] Started in PRELOAD mode. Waiting for START command on port {args.port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", args.port))
        sock.settimeout(None) # Wait indefinitely
        
        while True:
            data, addr = sock.recvfrom(1024)
            try:
                msg = json.loads(data.decode('utf-8'))
                if msg.get("cmd") == "START":
                    print("[Scene] Received START command. Booting up...")
                    sock.close()
                    break
            except Exception as e:
                pass
# =============================================================================
import atexit
from contextlib import ExitStack
import pygame
import display_utils
from scene_control import notify_first_frame, notify_exit_request
import math
import cv2
import mediapipe as mp

_resources = ExitStack()
atexit.register(_resources.close)
_resources.callback(pygame.quit)

# Initialize MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(model_complexity=1, 
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)
_resources.callback(hands.close)

# Initialize Webcam
cap = display_utils.open_camera()
if cap is not None:
    _resources.callback(cap.release)
if cap is None or not cap.isOpened():
    raise RuntimeError("The shared C922 camera could not be attached")

pygame.init()
screen, _pg_size = display_utils.setup_pygame_fullscreen()
w, h = screen.get_size()
clock = pygame.time.Clock()

cols = 40
rows = 30
spacing_x = w // cols
spacing_y = h // rows

running = True
t = 0

# Initial cursors
cursors = []
camera_surface = None
camera_layout = None

while running:
    # Read frame from webcam
    ret, frame = cap.read()
    cursors = []
    if ret:
        frame, stage_frame, camera_layout = display_utils.prepare_camera_frame(frame, w, h)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        stage_rgb = cv2.cvtColor(stage_frame, cv2.COLOR_BGR2RGB)
        camera_surface = pygame.image.frombuffer(stage_rgb.tobytes(), (w, h), "RGB")
        # Process the frame with MediaPipe
        results = hands.process(rgb_frame)
        
        if results.multi_hand_landmarks:
            new_cursors = []
            for hand_landmarks in results.multi_hand_landmarks:
                # Get index finger tip (landmark 8)
                index_tip = hand_landmarks.landmark[8]
                new_cursors.append(display_utils.normalized_to_stage(index_tip.x, index_tip.y, camera_layout))
            if new_cursors:
                cursors = new_cursors
    else:
        camera_surface = None
    
    if camera_surface is not None:
        screen.blit(camera_surface, (0, 0))
    else:
        screen.fill((0, 0, 0))
    t = pygame.time.get_ticks() * 0.006
    # Ambient motion has no finger marker; only current detections drive markers.
    influencers = cursors or [(w * (0.5 + 0.15 * math.cos(t * 0.03)),
                               h * (0.5 + 0.18 * math.sin(t * 0.027)))]

    # Draw cursors
    for cx, cy in cursors:
        pygame.draw.circle(screen, (255, 255, 255), (cx, cy), 8)

    for y in range(rows):
        for x in range(cols):
            px = x * spacing_x + spacing_x // 2
            py = y * spacing_y + spacing_y // 2

            # Calculate distance and identify the nearest hand
            d, near_idx = min((math.hypot(cx - px, cy - py), i) for i, (cx, cy) in enumerate(influencers))

            offset = math.sin(d * 0.04 - t) * 30
            size = max(2, 12 - d * 0.015 + math.cos(t)*2)

            color = pygame.Color(0)
            # Use near_idx to shift the hue (e.g., by 160 degrees for the second hand)
            c_hue = (d * 0.4 - t * 20 + near_idx * 160) % 360
            color.hsva = (c_hue, 100, 100, 100)

            draw_y = py + offset

            pygame.draw.circle(screen, color, (int(px), int(draw_y)), int(size))

            if x < cols - 1:
                next_px = (x + 1) * spacing_x + spacing_x // 2
                next_d = min(math.hypot(cx - next_px, cy - py) for cx, cy in influencers)
                next_offset = math.sin(next_d * 0.04 - t) * 30
                pygame.draw.line(screen, (30,30,30), (int(px), int(draw_y)), (int(next_px), int(py + next_offset)), 1)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            notify_exit_request("pygame_quit")
            running = False
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
            notify_exit_request("key_escape" if event.key == pygame.K_ESCAPE else "key_q")
            running = False

    pygame.display.flip()
    notify_first_frame(cap, frame_processed=bool(ret))
    clock.tick(60)
