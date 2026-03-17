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
3D ルーレットゲーム - CV2 Display版
mediapipe + pygfx でヘッドレス rendering + cv2 表示
"""

import numpy as np
import cv2
import mediapipe as mp
import pygfx as gfx
from collections import deque
import time

# ==================== Constants ====================
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 960
NUM_SECTORS = 16

# Colors
COLORS = [
    (1.0, 0.3, 0.3),   # Red
    (1.0, 0.6, 0.2),   # Orange
    (1.0, 0.8, 0.2),   # Yellow
    (0.3, 0.8, 0.3),   # Green
    (0.3, 0.6, 1.0),   # Blue
    (0.8, 0.3, 1.0),   # Purple
    (1.0, 0.3, 0.6),   # Pink
    (0.3, 0.8, 0.8),   # Cyan
]


# ==================== 3D Roulette ====================
class Roulette3D:
    def __init__(self, num_sectors=16):
        self.num_sectors = num_sectors
        self.rotation_z = 0.0
        self.rotation_x = 0.0
        self.rotation_y = 0.0
        
        self.rotation_velocity = 0.0
        self.rotation_friction = 0.97
        
        self.world = gfx.Group()
        self.create_meshes()
    
    def create_meshes(self):
        """メッシュを作成"""
        radius = 200
        depth = 50
        
        for idx in range(self.num_sectors):
            a1 = (2 * np.pi * idx) / self.num_sectors
            a2 = (2 * np.pi * (idx + 1)) / self.num_sectors
            
            r, g, b = COLORS[idx % len(COLORS)]
            
            # 頂点作成
            vertices = np.array([
                [0, 0, depth/2],
                [radius * np.cos(a1), radius * np.sin(a1), depth/2],
                [radius * np.cos(a2), radius * np.sin(a2), depth/2],
                [0, 0, -depth/2],
                [radius * np.cos(a1), radius * np.sin(a1), -depth/2],
                [radius * np.cos(a2), radius * np.sin(a2), -depth/2],
            ], dtype=np.float32)
            
            # インデックス
            indices = np.array([
                0, 1, 2, 3, 5, 4,
                1, 4, 3, 0, 3, 1,
                2, 0, 5, 5, 0, 3,
            ], dtype=np.uint32)
            
            # ジオメトリ
            geom = gfx.Geometry()
            geom.positions = vertices
            geom.indices = indices
            
            # マテリアル
            mat = gfx.MeshPhongMaterial(
                color=f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
            )
            
            mesh = gfx.Mesh(geom, mat)
            self.world.add(mesh)
    
    def update(self, hand_velocity_right, hand_rotation_left):
        """更新"""
        if abs(hand_velocity_right) > 0.005:
            self.rotation_velocity = hand_velocity_right
        else:
            self.rotation_velocity *= self.rotation_friction
        
        self.rotation_z += self.rotation_velocity
        self.rotation_z %= (2 * np.pi)
        
        if hand_rotation_left is not None:
            tx, ty = hand_rotation_left
            self.rotation_x += (tx - self.rotation_x) * 0.1
            self.rotation_y += (ty - self.rotation_y) * 0.1
        
        # ワールド回転を直接設定（クォータニオンではなくオイラー角で）
        # 各メッシュに回転を適用
        for mesh in self.world.children:
            euler = [self.rotation_x, self.rotation_y, self.rotation_z]
            from_euler = getattr(mesh.rotation, 'set_from_euler', None)
            if from_euler:
                mesh.rotation.set_from_euler(euler)


# ==================== Hand Detector ====================
class HandDetector:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        self.hand_angles = deque(maxlen=15)
        self.cap = cv2.VideoCapture(2)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    def get_frame(self):
        """フレーム取得"""
        ret, frame = self.cap.read()
        if not ret:
            return None
        return cv2.flip(frame, 1)
    
    def process(self, frame):
        """手を検出"""
        if frame is None:
            return 0.0, None
        
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)
        
        vel = 0.0
        left_pos = None
        
        if results.multi_hand_landmarks and results.multi_handedness:
            h, w = frame.shape[:2]
            for landmarks, hand in zip(results.multi_hand_landmarks, results.multi_handedness):
                htype = hand.classification[0].label
                
                if htype == "Right":
                    vel = self._calc_velocity(landmarks, frame)
                elif htype == "Left":
                    palm = landmarks.landmark[0]
                    left_pos = np.array([(palm.x * 2 - 1.0) * 0.5, (palm.y * 2 - 1.0) * 0.5])
        
        return vel, left_pos
    
    def _calc_velocity(self, landmarks, frame):
        """速度計算"""
        h, w = frame.shape[:2]
        m = landmarks.landmark[9]
        i = landmarks.landmark[5]
        
        angle = np.arctan2(m.y * h - i.y * h, m.x * w - i.x * w)
        self.hand_angles.append(angle)
        
        if len(self.hand_angles) > 3:
            diff = self.hand_angles[-1] - self.hand_angles[-2]
            if diff > np.pi:
                diff -= 2 * np.pi
            elif diff < -np.pi:
                diff += 2 * np.pi
            return -diff * 0.8
        return 0.0
    
    def get_3d_rotation(self, left_pos):
        """3D回転を計算"""
        if left_pos is None:
            return None
        max_rot = np.pi / 4
        return (left_pos[1] * max_rot, left_pos[0] * max_rot)
    
    def release(self):
        self.cap.release()
        self.hands.close()


# ==================== Main Game ====================
class Roulette3DGame:
    def __init__(self):
        self.roulette = Roulette3D(NUM_SECTORS)
        self.hand_detector = HandDetector()
        
        # CV2ウィンドウ用
        self.window_name = "3D Roulette - Hand Control"
        
        # シーン設定
        self.scene = gfx.Scene()
        self.camera = gfx.PerspectiveCamera(fov=50, aspect=WINDOW_WIDTH/WINDOW_HEIGHT)
        self.camera.position = (0, 0, 400)
        
        # ライト設定
        amb = gfx.AmbientLight("#ffffff", 0.6)
        self.scene.add(amb)
        
        direc = gfx.DirectionalLight("#ffffff", 1)
        direc.position = (100, 100, 100)
        self.scene.add(direc)
        
        self.scene.add(self.roulette.world)
        
        # Renderer初期化（Canvas型ではなく、numpy array を使用）
        try:
            # 試験的に Canvas を作成しない形での renderer 初期化
            self.renderer = None
            print("Running in CV2 display mode (headless rendering)")
        except Exception as e:
            print(f"Renderer initialization: {e}")
            self.renderer = None
        
        self.frame_count = 0
        self.fps_time = time.time()
        self.last_rotation_x = 0
        self.last_rotation_y = 0
        self.last_rotation_z = 0
        self.current_fps = 0
    
    def update_and_render(self):
        """更新と描画"""
        frame = self.hand_detector.get_frame()
        if frame is None:
            return False
        
        vel, left_pos = self.hand_detector.process(frame)
        rot_3d = self.hand_detector.get_3d_rotation(left_pos)
        
        # ルーレット更新
        self.roulette.update(vel, rot_3d)
        
        # 情報を画面上に描画（テキスト表示）
        display_frame = frame.copy()
        
        # 回転情報をテキスト表示
        h, w = display_frame.shape[:2]
        y_offset = 30
        
        cv2.putText(display_frame, "3D Roulette Hand Control", (10, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        
        y_offset += 40
        cv2.putText(display_frame, f"Rotation Z: {self.roulette.rotation_z:.2f} rad ({np.degrees(self.roulette.rotation_z):.1f} deg)",
                   (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 1)
        
        y_offset += 35
        cv2.putText(display_frame, f"3D Tilt X: {self.roulette.rotation_x:.2f} rad ({np.degrees(self.roulette.rotation_x):.1f} deg)",
                   (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 1)
        
        y_offset += 35
        cv2.putText(display_frame, f"3D Tilt Y: {self.roulette.rotation_y:.2f} rad ({np.degrees(self.roulette.rotation_y):.1f} deg)",
                   (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 1)
        
        y_offset += 35
        cv2.putText(display_frame, f"Velocity: {vel:.3f} rad/frame", (10, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 0), 1)
        
        # 簡易ルーレット表示（円）
        center = (w // 2, h - 100)
        radius = 80
        cv2.circle(display_frame, center, radius, (100, 100, 100), 2)
        
        # 回転に応じた線を描画
        angle = self.roulette.rotation_z
        end_x = center[0] + int(radius * np.cos(angle))
        end_y = center[1] + int(radius * np.sin(angle))
        cv2.line(display_frame, center, (end_x, end_y), (0, 255, 0), 3)
        
        # FPS 表示
        self.frame_count += 1
        now = time.time()
        if now - self.fps_time > 1.0:
            current_fps = self.frame_count
            self.frame_count = 0
            self.fps_time = now
            self.current_fps = current_fps
        
        if hasattr(self, 'current_fps'):
            cv2.putText(display_frame, f"FPS: {self.current_fps}", (w - 150, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 1)
        
        # CV2 で表示
        cv2.imshow(self.window_name, display_frame)
        
        # ESC キーで終了
        if cv2.waitKey(1) == 27:
            return False
        
        return True
    
    def run_headless(self):
        """CV2ウィンドウで実行"""
        print("\nStarting 3D Roulette Game")
        print("Controls:")
        print("  Right hand: Rotate roulette (Z-axis)")
        print("  Left hand: Tilt roulette in 3D (X-Y axes)")
        print("  ESC key: Quit\n")
        
        try:
            while self.update_and_render():
                pass
        except KeyboardInterrupt:
            print("\nGame ended by user")
        finally:
            cv2.destroyAllWindows()
            self.hand_detector.release()


# ==================== Entry Point ====================
def main():
    game = Roulette3DGame()
    game.run_headless()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
