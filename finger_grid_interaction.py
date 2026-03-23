
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
import pygame
import display_utils
import math
import cv2
import mediapipe as mp

# Initialize Pygame
pygame.init()
s, _pg_size = display_utils.setup_pygame_fullscreen()
W, H = s.get_size()
clock = pygame.time.Clock()

# Initialize MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(model_complexity=1, 
    max_num_hands=5,  # Support 5 hands
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

# Particle System Setup
cols = 50
rows = 30
spacing = 20
offset_x = W // 2 - (cols * spacing) // 2
offset_y = H // 2 - (rows * spacing) // 2

# Particles: [x, y, old_x, old_y, pinned]
P = []
for y in range(rows):
    for x in range(cols):
        px = x * spacing + offset_x
        py = y * spacing + offset_y
        pinned = (y == 0)
        P.append([px, py, px, py, pinned])

# Springs/Sticks: [p1_idx, p2_idx, rest_length, active, broken_time]
# broken_time: timestamp when it broke, or None if active
S = []
for i in range(len(P)):
    # Horizontal connection
    if (i + 1) % cols != 0:
        S.append([i, i + 1, spacing, True, 0])
    # Vertical connection
    if i < len(P) - cols:
        S.append([i, i + cols, spacing, True, 0])

# Camera capture
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
if not cap.isOpened():
   cap = display_utils.open_camera()
if not cap.isOpened():
   raise IOError("Cannot open webcam")

def get_hands_data(frame):
    if frame is None:
        return []
    
    # Flip frame horizontally for mirror effect and convert to RGB
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb_frame)
    
    hands_data = []
    
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            # Get index finger tip (landmark 8)
            index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            thumb_tip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
            
            # Convert normalized coordinates to screen coordinates
            x = int(index_tip.x * W)
            y = int(index_tip.y * H)
            
            # Check pinch (distance between thumb and index)
            tx, ty = int(thumb_tip.x * W), int(thumb_tip.y * H)
            dist_sq = (x - tx)**2 + (y - ty)**2
            is_pinching = dist_sq < 1600 # 40*40
            
            hands_data.append({'pos': (x, y), 'pinching': is_pinching})
            
    return hands_data

start_ticks = pygame.time.get_ticks()

# Regeneration settings
REGEN_DELAY = 3000 # Time before regeneration starts (ms) - Increased 3x
REGEN_DURATION = 4500 # Time to fully regenerate (ms) - Increased 3x
FLASH_DURATION = 300 # Flash duration after becoming fully active (ms)

running = True
while running:
    current_time = pygame.time.get_ticks()
    
    # Event handling
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                running = False
    
    # Camera processing
    ret, frame = cap.read()
    hands_list = get_hands_data(frame) if ret else []
    
    s.fill((0, 5, 10))

    # Interactions data collection (Hands + Mouse)
    mx, my = pygame.mouse.get_pos()
    md = pygame.mouse.get_pressed()
    
    interactions = []
    if md[0]:
        interactions.append({'pos': (mx, my), 'pinching': True}) 
    
    for hand in hands_list:
        interactions.append(hand)
        # Draw visual indicator for hands
        hx, hy = hand['pos']
        # Hand indicator also colorful? Maybe just white ring
        pygame.draw.circle(s, (255, 255, 255), (hx, hy), 12, 1)
        # Inner fill based on pinch
        fill_col = (255, 50, 50) if hand['pinching'] else (50, 255, 255)
        pygame.draw.circle(s, fill_col, (hx, hy), 8)


    # Verlet Integration
    for p in P:
        if not p[4]: # If not pinned
            # Interaction
            if interactions:
                px, py = p[0], p[1]
                for interact in interactions:
                    ix, iy = interact['pos']
                    
                    dx = px - ix
                    dy = py - iy
                    
                    if abs(dx) < 60 and abs(dy) < 60:
                        dist_sq = dx*dx + dy*dy
                        if dist_sq < 2500: # 50^2
                             # Pull towards finger
                            p[0] -= dx * 0.2
                            p[1] -= dy * 0.2
                            # Snap
                            if dist_sq < 100: # 10^2
                                p[0], p[1] = ix, iy
                                break # Prioritize closest

            # Verlet integration
            vx = (p[0] - p[2]) * 0.95
            vy = (p[1] - p[3]) * 0.95
            
            gravity = 0.4
            
            vx = max(-30, min(30, vx))
            vy = max(-30, min(30, vy))
            
            p[2], p[3] = p[0], p[1]
            p[0] += vx
            p[1] += vy + gravity

    # Constraint Solving & Logic (Sticks)
    # Using 3 iterations for performance with many sticks
    for _ in range(3): 
        for stick in S:
            # Unpack: p1, p2, len, active, broken_time
            if not stick[3]: 
                continue
                
            p1_idx, p2_idx, rest_len, _, _ = stick
            p1 = P[p1_idx]
            p2 = P[p2_idx]
            
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            dist_sq = dx*dx + dy*dy
            
            # Tear logic
            should_cut = False
            # Check interaction cuts
            if interactions:
                 min_x, max_x = min(p1[0], p2[0]), max(p1[0], p2[0])
                 min_y, max_y = min(p1[1], p2[1]), max(p1[1], p2[1])
                 
                 for interact in interactions:
                    if interact['pinching']:
                        ix, iy = interact['pos']
                        if min_x - 20 < ix < max_x + 20 and min_y - 20 < iy < max_y + 20: 
                             mid_x = (p1[0] + p2[0]) * 0.5
                             mid_y = (p1[1] + p2[1]) * 0.5
                             cut_dx = mid_x - ix
                             cut_dy = mid_y - iy
                             if cut_dx*cut_dx + cut_dy*cut_dy < 400: # 20*20
                                should_cut = True
                                break
            
            if dist_sq > 22500 or should_cut: # 150^2 = 22500
                stick[3] = False # Deactivate
                stick[4] = current_time # Set broken timestamp
                continue
            
            dist = math.sqrt(dist_sq)
            if dist < 0.0001: dist = 0.0001

            strength = 0.5 
            diff = (rest_len - dist) / dist * strength
            
            offset_x = dx * diff
            offset_y = dy * diff
            
            if not p1[4]: 
                p1[0] -= offset_x
                p1[1] -= offset_y
            if not p2[4]: 
                p2[0] += offset_x
                p2[1] += offset_y


    # Stick Rendering & Regeneration Logic
    # We iterate all sticks to handle regeneration even if inactive
    for stick in S:
        p1_idx, p2_idx, rest_len, active, broken_time = stick
        p1 = P[p1_idx]
        p2 = P[p2_idx]
        
        # Determine Color based on position and time
        # Position factor
        cx = (p1[0] + p2[0]) * 0.5
        cy = (p1[1] + p2[1]) * 0.5
        
        # Color Logic
        # Hue cycles over time and space
        hue = (current_time * 0.05 + cx * 0.2 + cy * 0.2) % 360
        base_color = pygame.Color(0)
        base_color.hsva = (hue, 100, 100, 100)
        
        if active:
            # Check if recently regenerated (Flash effect)
            # If (current_time - broken_time) is large, broken_time is old from previous break
            # Wait, we need to know WHEN it became active.
            # Simplified: broken_time stays as the time it broke. 
            # When active is true, broken_time is essentially "last broken time".
            # This logic is tricky. Let's use negative value or 0 for active state?
            # Or: When we regenerate, we set active=True but keep broken_time?
            # Let's say: 
            # If active, check if we are in flash window: time < regen_activation_time + flash_duration
            # We don't store regen_activation_time.
            # We can calculate it: activation_time = broken_time + REGEN_DELAY + REGEN_DURATION
            
            activation_time = broken_time + REGEN_DELAY + REGEN_DURATION
            # Only flash if broken_time > 0 (meaning it was broken at least once)
            if broken_time > 0 and current_time < activation_time + FLASH_DURATION:
                 # Flash White!
                 pygame.draw.line(s, (255, 255, 255), (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), 4)
            else:
                 # Normal active drawing
                 pygame.draw.line(s, base_color, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), 2)
                 
        else: # Inactive (Broken)
            # Check for regeneration
            time_since_break = current_time - broken_time
            
            if time_since_break > REGEN_DELAY:
                # Regeneration Phase: "Main Body Healing"
                # Apply gentle attraction force to pull the grid back together
                
                # Calculate vector and distance
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                dist_sq = dx*dx + dy*dy
                dist = math.sqrt(dist_sq)
                if dist < 0.0001: dist = 0.0001
                
                # Attraction Force (increasing as we get closer to deadline?)
                # Or constant gentle pull
                force = 0.1 # Stronger attraction as requested (was 0.02)
                
                fx = (dx / dist) * force * dist # proportional to distance (spring)
                fy = (dy / dist) * force * dist
                
                # Apply to particles (if not pinned)
                if not p1[4]:
                    p1[0] += fx * 0.5
                    p1[1] += fy * 0.5
                if not p2[4]:
                    p2[0] -= fx * 0.5
                    p2[1] -= fy * 0.5
                
                # Visualization: Line growing back
                # 0.0 to 1.0 progress based on time
                # But also maybe based on distance closing?
                # Let's use time progress for visuals
                progress = min(1.0, (time_since_break - REGEN_DELAY) / REGEN_DURATION)
                
                # Draw "healing" line
                # Alpha/Brightness based on progress
                # Pygame doesn't support alpha on main surface easily, so we darken the color
                
                h, s_val, v, a = base_color.hsva
                v = v * progress # Fade in brightness
                regen_color = pygame.Color(0)
                regen_color.hsva = (h, s_val, v, a)
                
                pygame.draw.line(s, regen_color, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), 1)

                # Reactivate condition
                # If time is up OR they are close enough
                if progress >= 1.0 or dist < rest_len * 1.5:
                    stick[3] = True
                    # Reset broken_time to initiate flash? No, keep it old.
                    # We need a new timestamp for "just healed".
                    # Let's store "healed_time" in stick[4] but wait, stick[4] is broken_time.
                    # We can use update broken_time to current_time - (REGEN+DELAY) to trigger logic?
                    # No, logic was: if broken_time > 0 and current < activation + FLASH
                    # Activation = broken + REGEN + DELAY.
                    # If we set broken_time such that activation matches now...
                    # broken = now - REGEN - DELAY
                    stick[4] = current_time - REGEN_DELAY - REGEN_DURATION


    pygame.display.flip()
    clock.tick(60)

