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
# スワイプでのリセットエフェクトは廃止。
# 両手指の本数に応じて描画の色が変わるように変更。
# 両手の指が、0本から5本に変わると画がリセット、桜吹雪のエフェクトを追加。
# 描画キャンバスが、ゆっくりと回転するように変更。
# 口を開けると、ランダムなスマイルが画面中央から拡大するエフェクトを追加。
# スマイルは複数のスタイルがあり、拡大しながらフェードアウトする。


import cv2
import display_utils
import mediapipe as mp
import numpy as np
import math
import time
import random
# MediaPipe Initialization
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
def distance(p1, p2):
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

def count_fingers(hand_landmarks, label):
    """Count raised fingers for a single hand landmarks.
    Uses simple heuristic: for index/middle/ring/pinky compare tip.y with pip.y.
    For thumb, use x comparison depending on handedness.
    Returns int in range 0-5.
    """
    tips_ids = [4, 8, 12, 16, 20]
    count = 0
    # Thumb
    thumb_tip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
    thumb_ip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_IP]
    if label == "Right":
        if thumb_tip.x < thumb_ip.x:
            count += 1
    else:
        if thumb_tip.x > thumb_ip.x:
            count += 1
    # Other fingers (index, middle, ring, pinky)
    for tip_id in tips_ids[1:]:
        tip = hand_landmarks.landmark[tip_id]
        pip = hand_landmarks.landmark[tip_id - 2]
        if tip.y < pip.y:
            count += 1
    return count

def animate_wipe_left_to_right(canvas_img, ref_img, duration=0.3):
    """Animate clearing the canvas from left to right over `duration` seconds."""
    h, w, _ = canvas_img.shape
    steps = max(6, int(duration * 60))
    delay_ms = max(1, int((duration / steps) * 1000))
    for i in range(1, steps + 1):
        wipe_x = int(w * (i / steps))
        temp = canvas_img.copy()
        if wipe_x > 0:
            temp[:, :wipe_x] = 0
        gray_temp = cv2.cvtColor(temp, cv2.COLOR_BGR2GRAY)
        _, mask_temp = cv2.threshold(gray_temp, 10, 255, cv2.THRESH_BINARY)
        display = ref_img.copy()
        display[mask_temp > 0] = temp[mask_temp > 0]
        cv2.imshow('Hand Drawing App', display)
        if cv2.waitKey(delay_ms) & 0xFF == ord('q'):
            break
    canvas_img[:] = 0
def main():
    # Initialize Hands
    hands = mp_hands.Hands(
        model_complexity=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
        max_num_hands=2
    )
    cap = display_utils.open_camera()
    display_utils.setup_cv2_fullscreen('Hand Drawing App')
    # Canvas for drawing
    canvas_layers = {"Left": None, "Right": None}
    
    # State variables
    prev_index_finger_pos = {} # per-hand previous index finger pos, keyed by label
    prev_hand_x = {}           # per-hand previous wrist x, keyed by label
    prev_finger_count = {}     # per-hand previous finger count
    # Particle system (list of particle dicts)
    particles = []
    last_time = time.time()
    # Face mesh / smile state
    face_mesh = None
    prev_mouth_open = False
    smiles = []

    # Canvas scroll speed (pixels per second to move left)
    CANVAS_SPEED_PX_PER_SEC = 160.0
    # Flow angle (degrees) and angular speed (deg/sec) — direction of flow rotates slowly
    flow_angles = {"Left": 0.0, "Right": 180.0}
    FLOW_ROTATION_DEG_PER_SEC = 10.0
    
    # Constants
    SWIPE_THRESHOLD = 0.15 # Normalized coordinate distance per frame for swipe
    DRAW_COLOR = (0, 255, 255) # Yellow
    THICKNESS = 5
    print("Controls:")
    print("  Both Hands Index Finger: Draw (color changes by finger count)")
    print("  Any Hand 5 Fingers: Spark + Sakura Reset")
    print("  Open Mouth: Random Smile Expansion Effect")
    print("  'q': Quit")
    while cap.isOpened():
        success, image = cap.read()
        if not success:
            print("Ignoring empty camera frame.")
            continue
        # Flip the image horizontally for a selfie-view display.
        image = cv2.flip(image, 1)
        h, w, c = image.shape
        # time delta for smooth motion
        now = time.time()
        dt = now - last_time
        last_time = now
        
        # Initialize per-hand canvases if not created (or if size changes)
        for label in ("Left", "Right"):
            if canvas_layers[label] is None or canvas_layers[label].shape != image.shape:
                canvas_layers[label] = np.zeros_like(image)
        # Shift each hand canvas in an opposite direction and rotation
        for label, direction in (("Left", 1.0), ("Right", -1.0)):
            flow_angles[label] = (flow_angles[label] + FLOW_ROTATION_DEG_PER_SEC * dt * direction) % 360.0
            theta = math.radians(flow_angles[label])
            dx_f = CANVAS_SPEED_PX_PER_SEC * dt * math.cos(theta) * direction
            dy_f = CANVAS_SPEED_PX_PER_SEC * dt * math.sin(theta) * direction
            shift_x = int(round(dx_f))
            shift_y = int(round(dy_f))
            if shift_x == 0 and shift_y == 0:
                continue
            canvas = canvas_layers[label]
            canvas = np.roll(canvas, shift=(-shift_y, -shift_x), axis=(0, 1))
            if shift_x > 0:
                canvas[:, w-shift_x:] = 0
            elif shift_x < 0:
                canvas[:, : -shift_x] = 0
            if shift_y > 0:
                canvas[h-shift_y:, :] = 0
            elif shift_y < 0:
                canvas[: -shift_y, :] = 0
            canvas_layers[label] = canvas
        # To improve performance, optionally mark the image as not writeable to
        # pass by reference.
        image.flags.writeable = False
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = hands.process(image)
        # Draw the hand annotations on the image.
        image.flags.writeable = True
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        # current per-hand detections
        current_index_pos = {}   # label -> (x,y)
        current_hand_x = {}      # label -> wrist.x
        current_finger_count = {}# label -> int
        if results.multi_hand_landmarks:
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                # Draw landmarks
                mp_drawing.draw_landmarks(
                    image,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style())
                label = handedness.classification[0].label # "Left" or "Right"
                # Count fingers for this hand
                fingers = count_fingers(hand_landmarks, label)
                current_finger_count[label] = fingers
                # Index tip for drawing
                index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                current_index_pos[label] = (int(index_tip.x * w), int(index_tip.y * h))
                # Wrist x for swipe detection
                wrist = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
                current_hand_x[label] = wrist.x
        # Choose draw color based on right-hand finger count
        COLOR_MAP = {
            1: (0, 0, 255),    # Red
            2: (0, 255, 0),    # Green
            3: (255, 0, 0),    # Blue
            4: (0, 255, 255),  # Yellow
            5: (255, 0, 255),  # Magenta
        }

        # Process Drawing: allow both hands to draw
        for label, pos in current_index_pos.items():
            fingers = current_finger_count.get(label, 0)
            if fingers and fingers > 0:
                draw_color = COLOR_MAP.get(fingers, (0, 255, 255))
                prev_pos = prev_index_finger_pos.get(label)
                canvas = canvas_layers.get(label)
                if prev_pos:
                    cv2.line(canvas, prev_pos, pos, draw_color, THICKNESS)
                prev_index_finger_pos[label] = pos
            else:
                prev_index_finger_pos[label] = None

        # Note: swipe reset removed per request — no swipe clearing

        # 5-finger reset: apply to any hand that changed to 5; spawn spark + sakura
        for label, cnt in current_finger_count.items():
            prev_cnt = prev_finger_count.get(label)
            # Reset only when a single hand's raised fingers transition from 0 to 5
            if prev_cnt is not None and prev_cnt == 0 and cnt == 5:
                canvas = np.maximum(canvas_layers["Left"], canvas_layers["Right"])
                gray_canvas = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
                _, mask_full = cv2.threshold(gray_canvas, 10, 255, cv2.THRESH_BINARY)
                ys, xs = np.where(mask_full > 0)
                num_pixels = len(xs)
                max_samples = 500
                if num_pixels == 0:
                    cx, cy = w // 2, h // 2
                    samples = [(cx, cy)]
                else:
                    idxs = np.random.choice(num_pixels, min(max_samples, num_pixels), replace=False)
                    samples = [(int(xs[i]), int(ys[i])) for i in idxs]
                # sparks
                for (sx, sy) in samples[:min(400, len(samples))]:
                    color = tuple(int(x) for x in canvas[sy, sx])
                    angle = random.uniform(0, 2 * math.pi)
                    speed = random.uniform(120, 700)
                    vx = math.cos(angle) * speed
                    vy = math.sin(angle) * speed * 0.6 - random.uniform(50, 250)
                    life = random.uniform(0.6, 1.6)
                    particles.append({
                        'type': 'spark',
                        'pos': [float(sx), float(sy)],
                        'vel': [vx, vy],
                        'color': color,
                        'life': life,
                        'radius': random.randint(1, 4)
                    })
                # sakura petals
                for (sx, sy) in samples[::max(1, len(samples)//120)][:120]:
                    pink = (180 + random.randint(-30,30), 120 + random.randint(-20,20), 200 + random.randint(-30,30))
                    angle = random.uniform(-math.pi/3, math.pi/3)
                    speed = random.uniform(30, 160)
                    vx = math.cos(angle) * speed + random.uniform(-40,40)
                    vy = math.sin(angle) * speed * 0.6 + random.uniform(-10,40)
                    life = random.uniform(1.2, 2.6)
                    particles.append({
                        'type': 'sakura',
                        'pos': [float(sx), float(sy)],
                        'vel': [vx, vy],
                        'color': pink,
                        'life': life,
                        'angle': random.uniform(0, 360),
                        'ang_vel': random.uniform(-120, 120),
                        'axes': (random.randint(6,14), random.randint(3,8))
                    })
                if num_pixels > 0:
                    for canvas_layer in canvas_layers.values():
                        canvas_layer[mask_full > 0] = 0
                print(f"Reset ({label}): spawned", len(particles), "particles")
            prev_finger_count[label] = cnt
        # remove prev_finger_count entries for hands lost
        for label in list(prev_finger_count.keys()):
            if label not in current_finger_count:
                prev_finger_count.pop(label, None)
        
        # Setup display
        # Combine image and canvas
        # Create mask of drawn area to overlay color
        canvas = np.maximum(canvas_layers["Left"], canvas_layers["Right"])
        gray_canvas = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray_canvas, 10, 255, cv2.THRESH_BINARY)
        
        # For solid drawing: overlay canvas onto image
        display = image.copy()
        display[mask > 0] = canvas[mask > 0]

        # --- Face / mouth detection for smile expansion effect ---
        # initialize face_mesh once
        if face_mesh is None:
            face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5)
        # Process face landmarks on RGB image (use a quick conversion)
        img_rgb_for_face = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        face_results = face_mesh.process(img_rgb_for_face)
        mouth_open = False
        mouth_center_x, mouth_center_y = w // 2, h // 2  # default fallback
        if face_results and face_results.multi_face_landmarks:
            fl = face_results.multi_face_landmarks[0]
            lm = fl.landmark
            if len(lm) > 14:
                upper = lm[13]
                lower = lm[14]
                mouth_gap = (lower.y - upper.y)
                # Calculate mouth center
                mouth_center_x = int((upper.x + lower.x) / 2.0 * w)
                mouth_center_y = int((upper.y + lower.y) / 2.0 * h)
                if mouth_gap > 0.05:
                    mouth_open = True
                if mouth_open:
                    mouth_idxs = [61,146,91,181,84,17,314,405,321,375,291]
                    pts = []
                    for idx in mouth_idxs:
                        if idx < len(lm):
                            xpt = int(lm[idx].x * w)
                            ypt = int(lm[idx].y * h)
                            pts.append((xpt, ypt))
                    if pts:
                        cv2.polylines(display, [np.array(pts, dtype=np.int32)], isClosed=True, color=(0,255,0), thickness=2)
        # trigger smile expansion when mouth transitions from closed->open
        if mouth_open and not prev_mouth_open:
            style = random.randint(0, 3)  # 4 random styles
            smiles.append({'life':1.8, 'max_life':1.8, 'scale':0.2, 'style': style, 'cx': mouth_center_x, 'cy': mouth_center_y})
        prev_mouth_open = mouth_open

        # Update and draw particles (non-blocking spark effect)
        if particles:
            # draw particles onto display
            alive = []
            for p in particles:
                p['life'] -= dt
                if p['life'] <= 0:
                    continue
                # update position with simple physics
                p['pos'][0] += p['vel'][0] * dt
                p['pos'][1] += p['vel'][1] * dt
                # different behaviors by type
                if p.get('type') == 'sakura':
                    # gentle gravity and rotation for petals
                    p['vel'][1] += 120.0 * dt
                    p['angle'] += p.get('ang_vel', 0) * dt
                    axes = p.get('axes', (8,4))
                    x = int(p['pos'][0])
                    y = int(p['pos'][1])
                    if x < 0 or x >= w or y < 0 or y >= h:
                        continue
                    color = tuple(int(v) for v in p['color'])
                    cv2.ellipse(display, (x, y), axes, p['angle'], 0, 360, color, -1)
                else:
                    # spark
                    p['vel'][1] += 600.0 * dt
                    x = int(p['pos'][0])
                    y = int(p['pos'][1])
                    if x < 0 or x >= w or y < 0 or y >= h:
                        continue
                    cv2.circle(display, (x, y), p.get('radius', 2), p['color'], -1)
                alive.append(p)
            particles = alive

        # Update and draw smiles (expanding + fade)
        if smiles:
            new_smiles = []
            for s in smiles:
                s['life'] -= dt
                if s['life'] <= 0:
                    continue
                t = 1.0 - (s['life'] / s['max_life'])  # progress: 0->1
                # scale from small to very large to fill screen
                scale = 0.2 + t * 4.0  # scale from 0.2 to ~4.2
                alpha = max(0.0, 1.0 - t)  # fade: 1->0
                style = s.get('style', 0)
                
                # draw smile starting from mouth position, expanding outward
                cx = s.get('cx', w // 2)
                cy = s.get('cy', h // 2)
                radius = int(min(w, h) * 0.08 * scale)
                if radius < 2:
                    new_smiles.append(s)
                    continue
                
                # create overlay for this smile
                overlay = display.copy()
                
                # style 0: classic yellow face with black outline
                if style == 0:
                    cv2.circle(overlay, (cx, cy), radius, (0, 215, 255), -1)  # yellow circle
                    cv2.circle(overlay, (cx, cy), radius, (0, 0, 0), max(2, radius//15))  # black outline
                    # eyes
                    eye_y = cy - radius // 3
                    eye_x_off = radius // 3
                    cv2.circle(overlay, (cx - eye_x_off, eye_y), max(2, radius // 8), (0, 0, 0), -1)
                    cv2.circle(overlay, (cx + eye_x_off, eye_y), max(2, radius // 8), (0, 0, 0), -1)
                    # arc mouth
                    mouth_axes = (max(3, radius // 2), max(2, radius // 3))
                    cv2.ellipse(overlay, (cx, cy + radius // 6), mouth_axes, 0, 20, 160, (0, 0, 0), max(2, radius // 12))
                
                # style 1: rainbow ring around yellow face
                elif style == 1:
                    cv2.circle(overlay, (cx, cy), radius, (0, 215, 255), -1)  # yellow
                    # rainbow ring
                    colors_ring = [(255, 0, 0), (255, 127, 0), (0, 255, 0), (0, 0, 255), (75, 0, 130), (148, 0, 211)]
                    for i, ring_color in enumerate(colors_ring):
                        ring_r = radius + (i + 1) * max(1, radius // 10)
                        cv2.circle(overlay, (cx, cy), ring_r, ring_color, max(1, radius // 20))
                    # black eyes and smile
                    eye_y = cy - radius // 3
                    eye_x_off = radius // 3
                    cv2.circle(overlay, (cx - eye_x_off, eye_y), max(2, radius // 8), (0, 0, 0), -1)
                    cv2.circle(overlay, (cx + eye_x_off, eye_y), max(2, radius // 8), (0, 0, 0), -1)
                    mouth_axes = (max(3, radius // 2), max(2, radius // 3))
                    cv2.ellipse(overlay, (cx, cy + radius // 6), mouth_axes, 0, 20, 160, (0, 0, 0), max(2, radius // 12))
                
                # style 2: simple line art smile
                elif style == 2:
                    cv2.circle(overlay, (cx, cy), radius, (200, 200, 200), max(2, radius // 15))  # light gray outline
                    # eyes
                    eye_y = cy - radius // 3
                    eye_x_off = radius // 3
                    cv2.circle(overlay, (cx - eye_x_off, eye_y), max(2, radius // 12), (100, 100, 100), max(1, radius // 20))
                    cv2.circle(overlay, (cx + eye_x_off, eye_y), max(2, radius // 12), (100, 100, 100), max(1, radius // 20))
                    # mouth
                    mouth_pt1 = (cx - radius // 3, cy + radius // 6)
                    mouth_pt2 = (cx, cy + radius // 4)
                    mouth_pt3 = (cx + radius // 3, cy + radius // 6)
                    cv2.polylines(overlay, [np.array([mouth_pt1, mouth_pt2, mouth_pt3], dtype=np.int32)], False, (100, 100, 100), max(2, radius // 15))
                
                # style 3: red happy face (big smile)
                else:  # style == 3
                    cv2.circle(overlay, (cx, cy), radius, (0, 0, 255), -1)  # red circle
                    cv2.circle(overlay, (cx, cy), radius, (0, 0, 0), max(2, radius // 15))  # black outline
                    # white eyes
                    eye_y = cy - radius // 3
                    eye_x_off = radius // 3
                    cv2.circle(overlay, (cx - eye_x_off, eye_y), max(3, radius // 7), (255, 255, 255), -1)
                    cv2.circle(overlay, (cx + eye_x_off, eye_y), max(3, radius // 7), (255, 255, 255), -1)
                    # big smile
                    mouth_axes = (max(4, radius // 2), max(3, radius // 2))
                    cv2.ellipse(overlay, (cx, cy + radius // 8), mouth_axes, 0, 0, 180, (255, 255, 255), -1)
                
                # blend with alpha
                cv2.addWeighted(overlay, alpha, display, 1.0 - alpha, 0, display)
                new_smiles.append(s)
            
            smiles = new_smiles

        cv2.imshow('Hand Drawing App', display)
        if cv2.waitKey(5) & 0xFF == ord('q'):
            break
    hands.close()
    if face_mesh is not None:
        face_mesh.close()
    cap.release()
    cv2.destroyAllWindows()
if __name__ == "__main__":
    main()
