#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
"""
Face Gesture Controller
カメラ映像から顔をスキャンして、両手で表情を操作するSF風インターフェース。
"""

import cv2
import mediapipe as mp
import pygame
import display_utils
import numpy as np
import time
import math
from scipy.spatial import Delaunay

# ==================== Constants ====================
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60

# Colors
COLOR_SCAN_GRID = (0, 255, 255)     # Cyan for scanning
COLOR_SCAN_BEAM = (255, 255, 255)   # White beam
COLOR_LOCKED = (0, 255, 100)        # Green for locked/complete
COLOR_CONNECT_LINE = (255, 255, 255) # White connection line
COLOR_HAND_GESTURE = (50, 100, 255)   # Blue for hand gestures
COLOR_FACE_MESH = (100, 200, 255)   # Light blue (will be used for warping or debug)

# Parameters
SCAN_DURATION = 2.0  # Slightly faster scan
FACE_MATCH_THRESHOLD = 0.8 
HAND_FACE_DISTANCE_THRESHOLD = 0.6 
EXAGGERATION_FACTOR = 2.5 # multiplier for facial movements

# ==================== Helper Classes ====================

class PersonData:
    def __init__(self, face_id):
        self.face_id = face_id
        self.scan_progress = 0.0
        self.is_scanned = False
        self.scan_start_time = 0
        self.last_seen_time = time.time()
        
        self.face_landmarks = None
        self.assigned_left_hand = None  # Hand landmarks object
        self.assigned_right_hand = None # Hand landmarks object
        
        # State for smoothing values
        self.mouth_open = 0.0
        self.eye_open = 1.0
        self.brow_tilt = 0.0

    def update_scan(self, is_facing_camera, dt):
        if self.is_scanned:
            return

        # Scanning logic: Needs to face camera
        if is_facing_camera:
            self.scan_progress += dt / SCAN_DURATION
            if self.scan_progress >= 1.0:
                self.scan_progress = 1.0
                self.is_scanned = True
        else:
            # Decay if looking away
            self.scan_progress = max(0.0, self.scan_progress - dt * 2.0)

    def reset_hands(self):
        self.assigned_left_hand = None
        self.assigned_right_hand = None

# ==================== Main App ====================

class FaceGestureApp:
    def __init__(self):
        pygame.init()
        self.window_screen, self.screen, self.display_layout = display_utils.setup_pygame_scaled_fullscreen(
            WINDOW_WIDTH,
            WINDOW_HEIGHT,
        )
        pygame.display.set_caption("Face Gesture Interface")
        self.clock = pygame.time.Clock()
        self.running = True

        # Camera
        self.cap = display_utils.open_camera()
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, WINDOW_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, WINDOW_HEIGHT)

        # MediaPipe
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=3,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(model_complexity=1, 
            max_num_hands=4, 
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        self.people = {} # face_id -> PersonData
        self.font = pygame.font.SysFont("Courier New", 20, bold=True)
    
    def detect_hand_openness(self, hand_landmarks):
        """
        手の開き具合を 0.0 (拳) 〜 1.0 (全開) で計算する
        """
        if not hand_landmarks:
            return 0.5

        wrist = hand_landmarks.landmark[0]
        # 指先: 親指(4), 人差し指(8), 中指(12), 薬指(16), 小指(20)
        tips = [4, 8, 12, 16, 20]
        
        # 手のサイズ（手首から中指の付け根）を基準距離にする
        mcp = hand_landmarks.landmark[9]
        hand_base_size = math.hypot(mcp.x - wrist.x, mcp.y - wrist.y)
        if hand_base_size < 0.01: hand_base_size = 0.01
        
        distances = []
        for tip_idx in tips:
            tip = hand_landmarks.landmark[tip_idx]
            d = math.hypot(tip.x - wrist.x, tip.y - wrist.y)
            distances.append(d / hand_base_size)
            
        avg_dist = sum(distances) / len(distances)
        
        # 通常、拳の時は約1.2、全開の時は約2.6程度になる（中指付け根比）
        # これを 0.0 〜 1.0 にマップする
        openness = (avg_dist - 1.2) / (2.6 - 1.2)
        return max(0.0, min(1.0, openness))

    def apply_face_warping(self, img, person, modifiers):
        """
        表情変形（ワーピング）を画像に適用する
        """
        ih, iw = img.shape[:2]
        landmarks = person.face_landmarks
        if not landmarks: return img

        # 1. ワーピングに使用するランドマークの選択
        indices = [1, 10, 152, 234, 454, 33, 133, 159, 145, 362, 263, 386, 374, 
                   70, 107, 336, 300, 61, 291, 0, 17, 13, 14]
        silhouette_ids = [338, 297, 332, 284, 251, 389, 356, 323, 361, 288, 397, 365, 
                          379, 378, 400, 377, 148, 176, 149, 150, 136, 172, 58, 132, 93, 127, 162, 21, 54, 103, 67, 109]
        indices = sorted(list(set(indices + silhouette_ids)))
        
        src_pts = []
        for idx in indices:
            lm = landmarks.landmark[idx]
            src_pts.append([lm.x * iw, lm.y * ih])
        
        # 画面の四隅を固定点として追加
        src_pts.append([0, 0])
        src_pts.append([iw-1, 0])
        src_pts.append([0, ih-1])
        src_pts.append([iw-1, ih-1])
        
        src_pts = np.array(src_pts, dtype=np.float32)
        dst_pts = src_pts.copy()
        
        # 2. 変形量の計算 (自然な範囲に調整)
        mouth_y_base = modifiers.get('mouth_y', 0.0)
        mouth_y_offset = mouth_y_base * 70 # Natural range (was 160)
        
        eye_scale = modifiers.get('eye_scale', 1.0) # 0.1 to 1.25 range from process
        
        brow_y = modifiers.get('brow_y', 0.0)
        
        idx_map = {idx: i for i, idx in enumerate(indices)}
        
        # 口の大袈裟な変形
        for m_idx in [17, 14, 314, 317, 402, 318, 13, 14]:
            if m_idx in idx_map:
                dst_pts[idx_map[m_idx]][1] += mouth_y_offset
        
        # 目の大袈裟な変形
        eye_centers = {
            'L': src_pts[idx_map[159]] if 159 in idx_map else src_pts[0],
            'R': src_pts[idx_map[386]] if 386 in idx_map else src_pts[1]
        }
        for e_idx in [33, 133, 159, 145]: 
            if e_idx in idx_map:
                rel = src_pts[idx_map[e_idx]] - eye_centers['L']
                dst_pts[idx_map[e_idx]] = eye_centers['L'] + rel * eye_scale
        for e_idx in [362, 263, 386, 374]:
            if e_idx in idx_map:
                rel = src_pts[idx_map[e_idx]] - eye_centers['R']
                dst_pts[idx_map[e_idx]] = eye_centers['R'] + rel * eye_scale

        for b_idx in [70, 107, 336, 300]:
            if b_idx in idx_map:
                dst_pts[idx_map[b_idx]][1] += brow_y

        # 3. トライアングル分割と描画
        tri = Delaunay(src_pts)
        warped_img = img.copy()
        
        for simplex in tri.simplices:
            pts_src = src_pts[simplex]
            pts_dst = dst_pts[simplex]
            
            pts_dst_int = pts_dst.astype(np.int32)
            rect = cv2.boundingRect(pts_dst_int)
            x, y, w, h = rect
            if w <= 0 or h <= 0: continue
            
            # Image boundary clipping
            x1, y1 = max(0, x), max(0, y)
            x2, y2 = min(iw, x + w), min(ih, y + h)
            if x2 <= x1 or y2 <= y1: continue

            # Create full patch and mask
            mask = np.zeros((h, w, 3), dtype=np.uint8)
            cv2.fillConvexPoly(mask, pts_dst_int - (x, y), (1, 1, 1))
            
            src_tri = pts_src.astype(np.float32)
            dst_tri = (pts_dst - (x, y)).astype(np.float32)
            
            affine_mat = cv2.getAffineTransform(src_tri, dst_tri)
            patch = cv2.warpAffine(img, affine_mat, (w, h), None, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
            
            # Sub-slicing for valid image area
            mask_area = mask[y1-y : y2-y, x1-x : x2-x]
            patch_area = patch[y1-y : y2-y, x1-x : x2-x]
            
            warped_img[y1 : y2, x1 : x2] = warped_img[y1 : y2, x1 : x2] * (1 - mask_area) + patch_area * mask_area
            
        return warped_img

    def draw_scan_effects(self, surface, person):
        """
        スキャン中のエフェクト（ビーム、グリッドなど）のみを描画する
        顔のメッシュ線は描画しない
        """
        scan_progress = person.scan_progress
        is_scanned = person.is_scanned
        ih, iw = WINDOW_HEIGHT, WINDOW_WIDTH
        
        # --- Scanning Beam ---
        if not is_scanned and scan_progress > 0:
            beam_y = int((time.time() * 400) % ih)
            pygame.draw.line(surface, (255, 255, 255), (0, beam_y), (iw, beam_y), 2)
            s = pygame.Surface((iw, 40), pygame.SRCALPHA)
            for i in range(40):
                alpha = int(100 * (i/40))
                pygame.draw.line(s, (*COLOR_SCAN_GRID, alpha), (0, i), (iw, i))
            surface.blit(s, (0, beam_y - 40))

    def process(self):
        ret, frame = self.cap.read()
        if not ret: return

        frame = cv2.flip(frame, 1)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        face_results = self.face_mesh.process(frame_rgb)
        hand_results = self.hands.process(frame_rgb)
        
        # Draw Camera
        frame_surface = pygame.image.frombuffer(frame_rgb.tobytes(), (WINDOW_WIDTH, WINDOW_HEIGHT), 'RGB')
        self.screen.blit(frame_surface, (0, 0))
        
        # Overlay
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        
        # 1. Update Faces
        current_faces = []
        if face_results.multi_face_landmarks:
            for i, landmarks in enumerate(face_results.multi_face_landmarks):
                # Simple tracking: map by index 
                # (Note: index can swap, better to use spatial tracking, but sufficient for simple demo)
                if i not in self.people:
                    self.people[i] = PersonData(i)
                person = self.people[i]
                person.face_landmarks = landmarks
                person.reset_hands()
                
                # Check orientation
                nose = landmarks.landmark[1]
                left_ear = landmarks.landmark[234]
                right_ear = landmarks.landmark[454]
                face_width = abs(right_ear.x - left_ear.x)
                if face_width < 0.01: face_width = 0.01
                
                nose_offset = abs((left_ear.x + right_ear.x)/2 - nose.x)
                is_facing = nose_offset < (face_width * 0.3)
                
                person.update_scan(is_facing, 1.0/FPS)
                current_faces.append(person)

        # 2. Hand Logic & Drawing
        if hand_results.multi_hand_landmarks:
            for hand_landmarks, handedness in zip(hand_results.multi_hand_landmarks, hand_results.multi_handedness):
                wrist = hand_landmarks.landmark[0]
                hx, hy = int(wrist.x * WINDOW_WIDTH), int(wrist.y * WINDOW_HEIGHT)
                
                # Draw Hand (Red Skeleton)
                points = {}
                for idx, lm in enumerate(hand_landmarks.landmark):
                    points[idx] = (int(lm.x * WINDOW_WIDTH), int(lm.y * WINDOW_HEIGHT))
                
                for conn in self.mp_hands.HAND_CONNECTIONS:
                    p1 = points[conn[0]]
                    p2 = points[conn[1]]
                    pygame.draw.line(overlay, COLOR_HAND_GESTURE, p1, p2, 3)
                    pygame.draw.circle(overlay, (255, 100, 100), p1, 4)

                # Assign to closest face
                closest_person = None
                min_dist = WINDOW_WIDTH * 0.4 # Max reach
                
                for person in current_faces:
                    nose = person.face_landmarks.landmark[1]
                    nx, ny = int(nose.x * WINDOW_WIDTH), int(nose.y * WINDOW_HEIGHT)
                    dist = math.hypot(hx - nx, hy - ny)
                    if dist < min_dist:
                        min_dist = dist
                        closest_person = person
                
                if closest_person:
                    label = handedness.classification[0].label
                    # "Right" label = Person's Left Hand (screen right)
                    if label == "Right":
                        closest_person.assigned_left_hand = hand_landmarks
                    else:
                        closest_person.assigned_right_hand = hand_landmarks

        # 3. Render Person Effects
        img_to_display = frame_rgb
        
        # Pre-process warping for all scanned people
        for person in current_faces:
            modifiers = {}
            if person.assigned_left_hand:
                openness = self.detect_hand_openness(person.assigned_left_hand)
                # 自然な「あ」の開き(0.6程度)を最大値にマッピング
                mouth_val = openness * 0.6
                person.mouth_open = person.mouth_open * 0.6 + mouth_val * 0.4
                modifiers['mouth_y'] = person.mouth_open
                
                # 眉の移動も控えめに
                brow_val = (openness - 0.5) * 30 # -15 to +15
                person.brow_tilt = person.brow_tilt * 0.6 + brow_val * 0.4
                modifiers['brow_y'] = person.brow_tilt
                
            if person.assigned_right_hand:
                openness = self.detect_hand_openness(person.assigned_right_hand)
                # 自然な見開き(1.25倍程度)を最大値にマッピング
                # 拳(0.0)は 0.1 (閉じ気味)
                eye_val = 0.1 + openness * 1.15
                person.eye_open = person.eye_open * 0.6 + eye_val * 0.4
                modifiers['eye_scale'] = person.eye_open
            
            if person.is_scanned:
                img_to_display = self.apply_face_warping(img_to_display, person, modifiers)

        # Draw Camera (processed)
        frame_surface = pygame.image.frombuffer(img_to_display.tobytes(), (WINDOW_WIDTH, WINDOW_HEIGHT), 'RGB')
        self.screen.blit(frame_surface, (0, 0))
        
        # Overlay drawing (Scanning effects, hand lines)
        for person in current_faces:
            self.draw_scan_effects(overlay, person)
            
            # Status & Connections
            head = person.face_landmarks.landmark[10]
            hx, hy = int(head.x * WINDOW_WIDTH), int(head.y * WINDOW_HEIGHT)
            
            if person.is_scanned:
                txt = self.font.render("[ SYNCHRONIZED ]", True, COLOR_LOCKED)
                overlay.blit(txt, (hx - 80, hy - 50))
                
                # Connection Lines
                def draw_conn(hand_lm):
                    if not hand_lm: return
                    wrist = hand_lm.landmark[0]
                    wx, wy = int(wrist.x * WINDOW_WIDTH), int(wrist.y * WINDOW_HEIGHT)
                    nose = person.face_landmarks.landmark[1]
                    nx, ny = int(nose.x * WINDOW_WIDTH), int(nose.y * WINDOW_HEIGHT)
                    pygame.draw.line(overlay, COLOR_CONNECT_LINE, (nx, ny), (wx, wy), 1)
                    pygame.draw.circle(overlay, COLOR_CONNECT_LINE, (nx, ny), 4)
                    pygame.draw.circle(overlay, COLOR_CONNECT_LINE, (wx, wy), 4)
                
                draw_conn(person.assigned_left_hand)
                draw_conn(person.assigned_right_hand)
            elif person.scan_progress > 0.05:
                pct = int(person.scan_progress * 100)
                txt = self.font.render(f"ANALYZING... {pct}%", True, COLOR_SCAN_GRID)
                overlay.blit(txt, (hx - 80, hy - 50))
                
                # Grid Box
                bounds = [person.face_landmarks.landmark[10], person.face_landmarks.landmark[152],
                          person.face_landmarks.landmark[234], person.face_landmarks.landmark[454]]
                min_x = min([p.x for p in bounds]) * WINDOW_WIDTH
                max_x = max([p.x for p in bounds]) * WINDOW_WIDTH
                min_y = min([p.y for p in bounds]) * WINDOW_HEIGHT
                max_y = max([p.y for p in bounds]) * WINDOW_HEIGHT
                rect = pygame.Rect(min_x-30, min_y-30, max_x-min_x+60, max_y-min_y+60)
                pygame.draw.rect(overlay, COLOR_SCAN_GRID, rect, 1)

        self.screen.blit(overlay, (0, 0))
        
        # FPS
        fps = int(self.clock.get_fps())
        fps_text = self.font.render(f"FPS: {fps}", True, (0, 255, 0))
        self.screen.blit(fps_text, (10, 10))
        
        display_utils.present_pygame_scaled(self.window_screen, self.screen, self.display_layout)

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
                        self.running = False
            
            self.process()
            self.clock.tick(FPS)

        self.hands.close()
        self.face_mesh.close()
        self.cap.release()
        pygame.quit()

if __name__ == "__main__":
    app = FaceGestureApp()
    app.run()
