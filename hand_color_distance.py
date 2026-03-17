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
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision
import math
import numpy as np
import colorsys
import time
import os

def calculate_distance_3d(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2 + (p1[2] - p2[2])**2)

def get_closest_point_on_segment_3d(p, a, b):
    ab = b - a
    ap = p - a
    t = np.dot(ap, ab) / (np.dot(ab, ab) + 1e-9)
    t = np.clip(t, 0, 1)
    return a + t * ab

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "models", "hand_landmarker.task")
    
    if not os.path.exists(model_path):
        print(f"Error: Model file not found at {model_path}")
        return

    base_options = mp_tasks.BaseOptions(model_asset_path=model_path)
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        num_hands=10, 
        min_hand_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )

    # Threshold for interaction in 3D space
    HOOK_RADIUS = 0.08

    with vision.HandLandmarker.create_from_options(options) as landmarker:
        cap = cv2.VideoCapture(2)
        if not cap.isOpened():
            for i in [0, 1]:
                cap = cv2.VideoCapture(i)
                if cap.isOpened(): break
        
        if not cap.isOpened():
            print("Error: Could not open webcam.")
            return

        cv2.namedWindow('True 3D Ayatori - Spatial String', cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty('True 3D Ayatori - Spatial String', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        print("True 3D Spatial Ayatori Mode.")
        
        while cap.isOpened():
            success, image = cap.read()
            if not success: continue

            image = cv2.flip(image, 1)
            h, w, _ = image.shape
            
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            
            frame_timestamp = int(time.time() * 1000)
            result = landmarker.detect_for_video(mp_image, frame_timestamp)

            if result.hand_landmarks and result.handedness:
                # Convert landmarks to numpy arrays for 3D math
                all_hands_data = []
                for lms in result.hand_landmarks:
                    pts = np.array([[lm.x, lm.y, lm.z] for lm in lms])
                    all_hands_data.append(pts)
                
                # Pair Left and Right hands
                left_hands = [pts for pts, hand in zip(all_hands_data, result.handedness) if hand[0].category_name == "Left"]
                right_hands = [pts for pts, hand in zip(all_hands_data, result.handedness) if hand[0].category_name == "Right"]
                
                num_pairs = min(len(left_hands), len(right_hands))
                
                draw_items = [] # (avg_z, type, data)

                for idx in range(num_pairs):
                    L = left_hands[idx]
                    R = right_hands[idx]
                    
                    # 21 base strings
                    for i in range(21):
                        p_start = L[i]
                        p_end = R[i]
                        
                        # Find fingers affecting this string
                        # Fingers: 4, 8, 12, 16, 20
                        influencers = []
                        for hand_pts in all_hands_data:
                            # 糸の端点となっている手自身の指先は除外（自分自身を引っ張らない）
                            is_own_hand = False
                            for h_pts in [L, R]:
                                if np.array_equal(hand_pts, h_pts):
                                    is_own_hand = True
                                    break
                            if is_own_hand:
                                continue

                            for tip_idx in [4, 8, 12, 16, 20]:
                                tip = hand_pts[tip_idx]
                                # Check distance to segments
                                closest = get_closest_point_on_segment_3d(tip, p_start, p_end)
                                dist = np.linalg.norm(tip - closest)
                                
                                if dist < HOOK_RADIUS:
                                    # Finger pulls the string
                                    influencers.append(tip)
                        
                        # Calculate color based on total "tension" (actual length vs straight length)
                        straight_len = np.linalg.norm(p_end - p_start)
                        
                        # Smooth color cycling over time and space
                        t_offset = time.time() * 0.2 # Slow time-based cycle
                        hue = (straight_len * 1.5 + i * 0.03 + t_offset) % 1.0
                        rgb = colorsys.hsv_to_rgb(hue, 0.7, 1.0)
                        base_color = (int(rgb[2] * 255), int(rgb[1] * 255), int(rgb[0] * 255))
                        
                        if influencers:
                            # String path: p_start -> influencers -> p_end
                            # Sort influencers to make a smooth-ish path or just use the strongest
                            # For ayatori feel, let's just use one dominant puller for simplicity in rendering
                            puller = influencers[0]
                            
                            # Add segments to draw list
                            mid_z = (p_start[2] + puller[2]) / 2
                            draw_items.append((mid_z, 'line', (p_start, puller, base_color)))
                            mid_z2 = (p_end[2] + puller[2]) / 2
                            draw_items.append((mid_z2, 'line', (puller, p_end, base_color)))
                        else:
                            mid_z = (p_start[2] + p_end[2]) / 2
                            draw_items.append((mid_z, 'line', (p_start, p_end, base_color)))

                # Add hand points to draw list for occlusion
                # Add hand points to draw list for occlusion (Only Tips)
                for hand_pts in all_hands_data:
                    for tip_idx in [4, 8, 12, 16, 20]:
                        pt = hand_pts[tip_idx]
                        draw_items.append((pt[2], 'point', (pt, tip_idx)))

                # Depth Sorting (Painter's algorithm: draw back-to-front)
                # MediaPipe Z: small is close to camera. So sort descending.
                draw_items.sort(key=lambda x: x[0], reverse=True)

                for z, item_type, data in draw_items:
                    if item_type == 'line':
                        p1_3d, p2_3d, color = data
                        p1 = (int(p1_3d[0] * w), int(p1_3d[1] * h))
                        p2 = (int(p2_3d[0] * w), int(p2_3d[1] * h))
                        
                        # Depth-based visuals: 手前ほど太く明るく
                        depth_factor = np.clip(1.0 - (z + 0.2) / 0.5, 0.3, 1.0) 
                        thickness = 2 # 前回（1）の1.5倍相当として2に設定
                        c = [int(channel * depth_factor) for channel in color]
                        
                        cv2.line(image, p1, p2, tuple(c), thickness, cv2.LINE_AA)
                        
                    elif item_type == 'point':
                        pt_3d, idx = data
                        pos = (int(pt_3d[0] * w), int(pt_3d[1] * h))
                        # Landmark colors (Always Tips now)
                        depth_factor = np.clip(1.0 - (pt_3d[2] + 0.2) / 0.5, 0.5, 1.0)
                        radius = 2 # 点も合わせて調整
                        cv2.circle(image, pos, radius + 1, (255, 255, 255), -1, cv2.LINE_AA)

            cv2.imshow('True 3D Ayatori - Spatial String', image)
            if cv2.waitKey(5) & 0xFF == ord('q') or cv2.waitKey(5) & 0xFF == 27:
                break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
