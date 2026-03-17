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
import pygame
import display_utils
import math
import random
import cv2
import mediapipe as mp

# Initialize MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    max_num_hands=2,  # Change to 2 hands
    min_detection_confidence=0.7,
    min_tracking_confidence=0.5
)

# Initialize Camera
cap = cv2.VideoCapture(3)

pygame.init()
info = pygame.display.Info()
w, h = info.current_w, info.current_h
screen, _pg_size = display_utils.setup_pygame_fullscreen()
clock = pygame.time.Clock()

# Separate canvas for drawing to avoid cursor trails
canvas = pygame.Surface((w, h), pygame.SRCALPHA)
canvas.fill((0, 0, 0, 0))

# Animation variables
anim_surface = None
anim_start_time = 0
ANIM_DURATION = 3000  # 3 seconds

running = True
hue = 0
prev_pos = None

# Gesture state for second hand
prev_gesture_hand2 = None  # 'FIST', 'OPEN', or None

def is_fist(hand_landmarks):
    # Check if fingers are curled.
    # Simple heuristic: compare tip y with pip y (assuming hand is upright)
    # However, for robustness in various orientations, distance to wrist is better.
    # Here using a simpler method: check if tips are closer to wrist than mcp/pip joints.
    
    # Landmarks: 0=WRIST, 
    # Index: 5=MCP, 6=PIP, 7=DIP, 8=TIP
    # Middle: 9=MCP, 10=PIP, 11=DIP, 12=TIP
    # Ring: 13=MCP, 14=PIP, 15=DIP, 16=TIP
    # Pinky: 17=MCP, 18=PIP, 19=DIP, 20=TIP
    
    # Thumb: 1=CMC, 2=MCP, 3=IP, 4=TIP
    
    # A robust way is to check if finger tips are folded towards the palm.
    # We can check distance between TIP and WRIST (0) vs PIP and WRIST (0).
    # If TIP is closer to WRIST than PIP, it's curled.
    
    wrist = hand_landmarks.landmark[0]
    
    fingers_curled = 0
    # Check Index, Middle, Ring, Pinky
    for tip_idx, pip_idx in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        tip = hand_landmarks.landmark[tip_idx]
        pip = hand_landmarks.landmark[pip_idx]
        
        d_tip = (tip.x - wrist.x)**2 + (tip.y - wrist.y)**2
        d_pip = (pip.x - wrist.x)**2 + (pip.y - wrist.y)**2
        
        if d_tip < d_pip:
            fingers_curled += 1
            
    # Thumb is special, we can ignore for simple 'rock' detection or check x distance
    # For simplicity, if 4 fingers are curled, it's a fist.
    return fingers_curled >= 3

while running:
    # Handle Camera Input
    ret, frame = cap.read()
    if not ret:
        break
    
    # Flip frame horizontally for mirror effect and convert to RGB
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # Process with MediaPipe
    results = hands.process(rgb_frame)
    
    # Clear screen every frame
    screen.fill((0, 0, 0))
    
    # Mouse fallback
    mx, my = pygame.mouse.get_pos()
    has_drawing_hand = False
    
    current_time = pygame.time.get_ticks()
    
    # Handle Reset Animation
    if anim_surface:
        elapsed = current_time - anim_start_time
        if elapsed < ANIM_DURATION:
            progress = elapsed / ANIM_DURATION
            # Reverse rotation: 0 to -360? Or just rotate continuously. User said "reverse rotation".
            # Let's assume the mandala has some rotational symmetry, but we'll just rotate the whole canvas.
            angle = progress * 360 * 2  # Rotate 2 full circles
            scale = 1.0 - progress
            
            # Rotate and scale
            # pygame.transform.rotozoom is filtered and smooth
            current_anim = pygame.transform.rotozoom(anim_surface, angle, scale)
            
            # Center it
            anim_rect = current_anim.get_rect(center=(w//2, h//2))
            screen.blit(current_anim, anim_rect)
        else:
            anim_surface = None # Animation finished
            
    # Draw existing canvas (if not animating, or behind animation if desired, 
    # but request implies "disappear", so maybe we don't show the static canvas while animating?)
    # "リセット時のアニメーションは、描画されている絵が三秒間で逆回転して無くなるものにして。"
    # This implies the *existing* drawing transforms. So we should NOT blit 'canvas' if we are animating the 'old' canvas.
    if not anim_surface:
        screen.blit(canvas, (0, 0))

    if results.multi_hand_landmarks:
        # Sort hands by detection? MediaPipe usually returns them in order of detection/confidence.
        # We assume index 0 is the first hand (Draw), index 1 is the second (Control).
        
        # --- Hand 1: Drawing ---
        if len(results.multi_hand_landmarks) >= 1:
            hand1 = results.multi_hand_landmarks[0]
             # Get Index Finger Tip (Landmark 8)
            ih, iw, _ = frame.shape
            x = int(hand1.landmark[8].x * w)
            y = int(hand1.landmark[8].y * h)
            mx, my = x, y
            has_drawing_hand = True
            
            # Draw cursor (white circle) on SCREEN, not canvas
            pygame.draw.circle(screen, (255, 255, 255), (mx, my), 5)

        # --- Hand 2: Control (Reset) ---
        if len(results.multi_hand_landmarks) >= 2:
            hand2 = results.multi_hand_landmarks[1]
            is_hand2_fist = is_fist(hand2)
            
            gesture = 'FIST' if is_hand2_fist else 'OPEN'
            
            if prev_gesture_hand2 == 'FIST' and gesture == 'OPEN':
                # Trigger Reset
                if not anim_surface: # Only trigger if not already animating
                    anim_surface = canvas.copy()
                    anim_start_time = pygame.time.get_ticks()
                    canvas.fill((0, 0, 0, 0)) # Clear the live canvas immediately
                    prev_pos = None # Reset drawing state
            
            prev_gesture_hand2 = gesture
        else:
            prev_gesture_hand2 = None

    cx, cy = w // 2, h // 2

    hue += 1
    if hue > 360: hue = 0

    color = pygame.Color(0)
    color.hsva = (hue, 100, 100, 100)

    # Only draw if we have a hand and are not animating (optional, but prevents drawing while resetting)
    if has_drawing_hand and not anim_surface:
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
        prev_pos = None # Reset prev_pos if no hand detected or animating

    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and (event.key == pygame.K_ESCAPE or event.key == pygame.K_q)):
            running = False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            canvas.fill((0,0,0,0)) # Clear canvas with Space

    pygame.display.flip()
    clock.tick(120)

cap.release()
pygame.quit()
