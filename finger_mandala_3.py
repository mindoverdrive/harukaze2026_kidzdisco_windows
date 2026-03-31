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
            except Exception:
                pass
# =============================================================================
import atexit
import pygame
import display_utils
import math
import cv2
import mediapipe as mp

# Initialize MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(model_complexity=1, 
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)

# Initialize Camera
cap = display_utils.open_camera()
def _cleanup():
    try:
        hands.close()
    except Exception:
        pass
    try:
        cap.release()
    except Exception:
        pass
    try:
        pygame.quit()
    except Exception:
        pass

atexit.register(_cleanup)

pygame.init()
screen, _pg_size = display_utils.setup_pygame_fullscreen()
w, h = screen.get_size()
clock = pygame.time.Clock()

# Separate canvas for drawing to avoid cursor trails
canvas = pygame.Surface((w, h), pygame.SRCALPHA)
canvas.fill((0, 0, 0, 0))

running = True
hue = 0
prev_pos = None
camera_layout = None

while running:
    # Handle Camera Input
    ret, frame = cap.read()
    if not ret:
        break

    frame, stage_frame, camera_layout = display_utils.prepare_camera_frame(frame, w, h)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    stage_rgb = cv2.cvtColor(stage_frame, cv2.COLOR_BGR2RGB)
    camera_surface = pygame.image.frombuffer(stage_rgb.tobytes(), (w, h), "RGB")
    
    # Process with MediaPipe
    results = hands.process(rgb_frame)
    
    # Draw camera every frame so the cursor matches the visible hand position
    screen.blit(camera_surface, (0, 0))
    screen.blit(canvas, (0, 0))
    
    # Mouse fallback
    mx, my = pygame.mouse.get_pos()
    has_drawing_hand = False

    if results.multi_hand_landmarks:
        # Use the first detected hand for continuous mandala drawing.
        hand1 = results.multi_hand_landmarks[0]
        x, y = display_utils.normalized_to_stage(
            hand1.landmark[8].x,
            hand1.landmark[8].y,
            camera_layout,
        )
        mx, my = x, y
        has_drawing_hand = True
        pygame.draw.circle(screen, (255, 255, 255), (mx, my), 5)

    cx, cy = w // 2, h // 2

    hue += 1
    if hue > 360:
        hue = 0

    color = pygame.Color(0)
    color.hsva = (hue, 100, 100, 100)

    if has_drawing_hand:
        current_pos = (mx - cx, my - cy)

        if prev_pos:
            segments = 12
            for i in range(segments):
                angle = (math.pi * 2 / segments) * i

                cos_a = math.cos(angle)
                sin_a = math.sin(angle)

                p1_x = prev_pos[0] * cos_a - prev_pos[1] * sin_a + cx
                p1_y = prev_pos[0] * sin_a + prev_pos[1] * cos_a + cy

                p2_x = current_pos[0] * cos_a - current_pos[1] * sin_a + cx
                p2_y = current_pos[0] * sin_a + current_pos[1] * cos_a + cy

                pygame.draw.line(canvas, color, (p1_x, p1_y), (p2_x, p2_y), 2)

                p1_x_m = (-prev_pos[0]) * cos_a - prev_pos[1] * sin_a + cx
                p1_y_m = (-prev_pos[0]) * sin_a + prev_pos[1] * cos_a + cy

                p2_x_m = (-current_pos[0]) * cos_a - current_pos[1] * sin_a + cx
                p2_y_m = (-current_pos[0]) * sin_a + current_pos[1] * cos_a + cy

                pygame.draw.line(canvas, color, (p1_x_m, p1_y_m), (p2_x_m, p2_y_m), 2)

        prev_pos = current_pos
    else:
        prev_pos = None

    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and (event.key == pygame.K_ESCAPE or event.key == pygame.K_q)):
            running = False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            canvas.fill((0, 0, 0, 0))

    pygame.display.flip()
    clock.tick(120)
