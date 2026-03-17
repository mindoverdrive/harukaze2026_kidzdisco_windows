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
ルーレットゲーム - 高度なエフェクト版
mediapipe + pygame
手指の回転ベロシティーでルーレットを回転させるゲーム
中心軸の柔軟な動きと高度なエフェクト搭載
"""

import pygame
import numpy as np
import cv2
import mediapipe as mp
from collections import deque
from dataclasses import dataclass
from enum import Enum
import os
import json

# Load config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
else:
    config = {}
VIDEO_PATH = config.get("VIDEO_PATH", "../sozai/Spiral_Focus.mp4")

import math
import random
from typing import Tuple, List, Optional
import time
from pyvidplayer2 import Video
import spiral_mouth_effect as sme

# ==================== Constants ====================
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 960
FPS = 60
NUM_SECTORS = 16

# Colors - より鮮やかな色
COLORS = [
    (255, 100, 100),   # Red
    (255, 150, 50),    # Orange
    (255, 200, 50),    # Yellow
    (100, 200, 100),   # Green
    (100, 150, 255),   # Blue
    (200, 100, 255),   # Purple
    (255, 100, 200),   # Pink
    (100, 200, 200),   # Cyan
    (255, 100, 150),   # Light Red
    (200, 200, 100),   # Olive
    (255, 180, 100),   # Peach
    (150, 200, 255),   # Light Blue
    (200, 100, 150),   # Mauve
    (150, 255, 150),   # Light Green
    (255, 100, 100),   # Light Pink
    (150, 150, 255),   # Light Purple
]

# Roulette settings
ROULETTE_CENTER = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
ROULETTE_RADIUS = 375
MARKER_Y = 100  # Top marker position


# ==================== Enums ====================
class GameState(Enum):
    PLAYING = 1
    WINNING = 2
    EXPANDING = 3
    MELTING = 4
    RESET = 5


# ==================== Particle Class ====================
class Particle:
    """パーティクル効果"""
    def __init__(self, x, y, vx, vy, lifetime, color, size=5):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.color = color
        self.size = size
    
    def update(self):
        """パーティクルの更新"""
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.2  # 重力
        self.lifetime -= 1
    
    def draw(self, surface):
        """パーティクルの描画"""
        if self.lifetime > 0:
            alpha = self.lifetime / self.max_lifetime
            current_size = max(1, int(self.size * alpha))
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), current_size)
    
    def is_alive(self):
        """パーティクルが生きているか"""
        return self.lifetime > 0


# ==================== Drawing Functions ====================
def draw_circle_pattern(surface, x, y, size, color):
    """複雑な円パターン"""
    # 外側の円
    pygame.draw.circle(surface, color, (x, y), size, 3)
    # 複数の内円
    for i in range(1, 4):
        r = size - (size // 3) * i
        pygame.draw.circle(surface, color, (x, y), r, 2)
    # ドット装飾
    for j in range(3):
        for angle in np.linspace(0, 2 * np.pi, 8 + j * 4, endpoint=False):
            px = x + (size * 0.5 + j * 8) * np.cos(angle)
            py = y + (size * 0.5 + j * 8) * np.sin(angle)
            pygame.draw.circle(surface, color, (int(px), int(py)), 3 - j)


def draw_star_pattern(surface, x, y, size, color):
    """複雑な星パターン"""
    # 大きい星
    points = []
    for i in range(10):
        angle = i * np.pi / 5
        if i % 2 == 0:
            r = size
        else:
            r = size * 0.4
        px = x + r * np.cos(angle - np.pi / 2)
        py = y + r * np.sin(angle - np.pi / 2)
        points.append((px, py))
    
    pygame.draw.polygon(surface, color, points, 2)
    
    # 内側の装飾星
    for num_stars in range(2):
        inner_size = size * (0.5 - num_stars * 0.2)
        for i in range(8):
            angle = i * np.pi / 4 + np.pi / 8
            if i % 2 == 0:
                r = inner_size
            else:
                r = inner_size * 0.5
            px = x + r * np.cos(angle)
            py = y + r * np.sin(angle)
            if i % 2 == 0:
                pygame.draw.circle(surface, color, (int(px), int(py)), 3)


def draw_flower_pattern(surface, x, y, size, color):
    """複雑な花パターン"""
    # 中心円
    pygame.draw.circle(surface, color, (x, y), size // 2, 0)
    
    # 複数層の花びら
    for layer in range(3):
        num_petals = 6 + layer * 2
        petal_size = size // 2 - layer * 8
        for i in range(num_petals):
            angle = i * 2 * np.pi / num_petals
            px = x + (size * 0.6 - layer * 10) * np.cos(angle)
            py = y + (size * 0.6 - layer * 10) * np.sin(angle)
            pygame.draw.circle(surface, color, (int(px), int(py)), petal_size - layer * 3, 1)
            
            # 花びらの内部模様
            for j in range(2):
                px2 = x + (size * 0.3 - layer * 5 - j * 5) * np.cos(angle)
                py2 = y + (size * 0.3 - layer * 5 - j * 5) * np.sin(angle)
                pygame.draw.circle(surface, color, (int(px2), int(py2)), 2)


def draw_diamond_pattern(surface, x, y, size, color):
    """複雑なダイヤモンドパターン"""
    # 外側のダイヤ
    points = [
        (x, y - size),
        (x + size, y),
        (x, y + size),
        (x - size, y)
    ]
    pygame.draw.polygon(surface, color, points, 2)
    
    # 内側のダイヤ複数層
    for layer in range(1, 3):
        scale = 1 - layer * 0.25
        inner_points = [
            (x, y - size * scale),
            (x + size * scale, y),
            (x, y + size * scale),
            (x - size * scale, y)
        ]
        pygame.draw.polygon(surface, color, inner_points, 1)
    
    # 装飾ドット
    for angle in np.linspace(0, 2 * np.pi, 12, endpoint=False):
        for dist in [size * 0.3, size * 0.6, size * 0.9]:
            px = x + dist * np.cos(angle)
            py = y + dist * np.sin(angle)
            pygame.draw.circle(surface, color, (int(px), int(py)), 2)


def draw_wave_pattern(surface, x, y, size, color):
    """複雑な波パターン"""
    # 複数の波線
    for wave_offset in range(-size, size + 1, 8):
        points = []
        for i in range(-size, size + 1, 3):
            py = y + wave_offset + 8 * np.sin(i / size * 3 * np.pi)
            px = x + i
            points.append((px, py))
        if len(points) > 1:
            pygame.draw.lines(surface, color, False, points, 2)
    
    # 交差する波
    for wave_offset in range(-size, size + 1, 8):
        points = []
        for i in range(-size, size + 1, 3):
            px = x + wave_offset + 8 * np.cos(i / size * 3 * np.pi)
            py = y + i
            points.append((px, py))
        if len(points) > 1:
            pygame.draw.lines(surface, color, False, points, 1)


def draw_spiral_pattern(surface, x, y, size, color):
    """複雑なスパイラルパターン"""
    # ダブルスパイラル
    for offset in [-1, 1]:
        points = []
        for t in np.linspace(0, 6 * np.pi, 150):
            r = size * t / (6 * np.pi)
            angle = t + offset * np.pi
            px = x + r * np.cos(angle)
            py = y + r * np.sin(angle)
            points.append((px, py))
        
        if len(points) > 1:
            pygame.draw.lines(surface, color, False, points, 2 if offset > 0 else 1)


# ==================== Roulette Class ====================
class RouletteGame:
    def __init__(self):
        """ルーレットゲームの初期化"""
        self.shapes = [
            draw_circle_pattern,
            draw_star_pattern,
            draw_flower_pattern,
            draw_diamond_pattern,
            draw_wave_pattern,
            draw_spiral_pattern,
        ]
        
        # ゲーム状態
        self.state = GameState.PLAYING
        self.rotation = 0.0  # ラジアン
        self.rotation_velocity = 0.0  # ラジアン/フレーム
        self.rotation_friction = 0.97  # 摩擦係数
        
        # 中心軸の動き
        self.center_offset = np.array([0.0, 0.0])
        self.center_target = np.array([0.0, 0.0])
        self.center_smooth = 0.15  # スムーズ係数
        
        # 当選関連
        self.winning_sector = 0
        self.winning_color = (255, 255, 255)
        
        # エフェクト関連
        self.particles: List[Particle] = []
        self.effect_timer = 0
        self.effect_max_duration = 180  # フレーム
        self.expansion_scale = 1.0
        self.expansion_speed = 0.02
        
        # 溶け効果
        self.melt_strips: List[dict] = []
        self.melt_duration = 30
        self.melt_timer = 0
        
        # mediapipe初期化
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # 手の位置履歴（ベロシティー計算用）
        self.hand_angles = deque(maxlen=15)
        self.hand_velocities = deque(maxlen=5)
        
        # カメラ初期化 (ID:0がOBS等の仮想カメラになる場合があるため、1に変更)
        self.cap = cv2.VideoCapture(2)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # 描画用データ
        self.current_frame = None
        self.hand_results = None

        # 顔認識・エフェクト用初期化
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=3,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.smoke_particles = []
        self.face_trackers = []
        self.smoke_open_threshold = 0.18
        self.emit_interval = 0.08
        self.face_prev_time = time.time()
        
        # 2本の手が検出された際の情報
        self.hand_distance_info = None
        
        # pygame初期化
        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("Roulette Game - Hand Control")
        self.clock = pygame.time.Clock()
        self.font_large = pygame.font.Font(None, 100)
        self.font_medium = pygame.font.Font(None, 50)
        self.font_small = pygame.font.Font(None, 24)

        # 背景動画の初期化
        self.video_path = VIDEO_PATH
        try:
            # 引数エラーを避けるため、一旦引数なしで試行し、読み込み後にボリューム調整
            self.video = Video(self.video_path)
            try:
                self.video.set_volume(0)
            except:
                pass
        except Exception as e:
            print(f"動画の読み込みに失敗しました: {e}")
            self.video = None

        # 背景演出用のカウンタと方向
        self.bg_timer = 0
        self.bg_direction = 1  # 1: 正回転, -1: 逆回転

        # ルーレット描画用のSurface (透過用)
        self.roulette_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)

        # CLI window settings
        self.cli_width = int(240 * 1.4)
        self.cli_height = int(180 * 1.4)
        self.cli_logs = deque(maxlen=15)
        self.cli_timer = 0
        self.cli_tech_strings = [
            "CHECKING MEDIA_PIPE STATUS... OK",
            "INITIALIZING FACE MESH... OK",
            "CALCULATING HAND ROTATION VELOCITY...",
            "UPDATING VFX PARTICLES...",
            "RENDER BUFFER SWAP... COMPLETED",
            "STREAMING DATA TO MAC ENGINE...",
            "ADAPTIVE MOTION FILTER: ON",
            "FPS STABILIZED AT 60.0",
            "MEMORY ALLOCATION: HEAP 24.5MB",
            "NEURAL ENGINE LOAD: 12%",
            "IO SERVICE DISCOVERY... OK",
            "HARDWARE ACCELERATION: METAL ENABLED",
            "SCANNING HAND GESTURES...",
            "OPTIMIZING SHADER CACHE...",
            "MAC_SILICON_PERFORMANCE_MODE: ULTRA"
        ]
        self.cli_logs.append("SYSTEM BOOTING...")

    def get_hand_rotation_velocity(self, frame):
        """手指の回転ベロシティーを計算"""
        self.current_frame = frame.copy()
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.hand_results = self.hands.process(rgb_frame)
        results = self.hand_results
        
        velocity = 0.0
        hand_center = None
        
        if results.multi_hand_landmarks and results.multi_handedness:
            hand_landmarks = results.multi_hand_landmarks[0]
            
            # 中指（landmarks[9]）と人差し指（landmarks[5]）の位置から回転角を計算
            mid_finger = hand_landmarks.landmark[9]
            index_finger = hand_landmarks.landmark[5]
            
            # フレーム座標に変換
            h, w, c = frame.shape
            mid_x, mid_y = int(mid_finger.x * w), int(mid_finger.y * h)
            idx_x, idx_y = int(index_finger.x * w), int(index_finger.y * h)
            
            # 手の中心
            hand_center_x = (mid_x + idx_x) / 2
            hand_center_y = (mid_y + idx_y) / 2
            hand_center = np.array([hand_center_x / w - 0.5, hand_center_y / h - 0.5])
            
            # 現在の角度
            current_angle = np.arctan2(mid_y - idx_y, mid_x - idx_x)
            
            self.hand_angles.append(current_angle)
            
            # 角度の変化からベロシティーを計算
            if len(self.hand_angles) > 3:
                angle_diff = self.hand_angles[-1] - self.hand_angles[-2]
                # 角度差分の正規化 (-pi, pi]
                if angle_diff > np.pi:
                    angle_diff -= 2 * np.pi
                elif angle_diff < -np.pi:
                    angle_diff += 2 * np.pi
                
                velocity = -angle_diff * 0.8  # スケール調整（逆回転に設定）
                self.hand_velocities.append(velocity)

        # 2本の手が検出された場合の距離計算
        self.hand_distance_info = None
        if results.multi_hand_landmarks and len(results.multi_hand_landmarks) >= 2:
            h, w, c = frame.shape
            hand1 = results.multi_hand_landmarks[0]
            hand2 = results.multi_hand_landmarks[1]
            
            # 各指の先端座標（4, 8, 12, 16, 20）
            tips = [4, 8, 12, 16, 20]
            distances = []
            for tip_idx in tips:
                p1 = hand1.landmark[tip_idx]
                p2 = hand2.landmark[tip_idx]
                
                pos1 = (int(p1.x * w), int(p1.y * h))
                pos2 = (int(p2.x * w), int(p2.y * h))
                dist = math.hypot(pos1[0] - pos2[0], pos1[1] - pos2[1])
                distances.append({
                    'pos1': pos1,
                    'pos2': pos2,
                    'dist': dist
                })
            
            self.hand_distance_info = distances
        
        # 中心軸の動きを更新
        if hand_center is not None:
            self.center_target = hand_center * 50  # スケール調整
        else:
            self.center_target = np.array([0.0, 0.0])
        
        return velocity

    def process_face_effect(self, frame):
        """顔のエフェクト処理（スパイラル＆煙）"""
        now = time.time()
        dt = now - self.face_prev_time
        self.face_prev_time = now

        img_h, img_w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)

        out = frame.copy()

        if results.multi_face_landmarks:
            face_mouths = []
            for face_landmarks in results.multi_face_landmarks:
                lm = face_landmarks.landmark

                # 口の中心計算
                try:
                    mouth_idxs = [13, 14, 61, 291]
                    mx = np.mean([lm[i].x for i in mouth_idxs])
                    my = np.mean([lm[i].y for i in mouth_idxs])
                    cx = int(mx * img_w)
                    cy = int(my * img_h)
                except Exception:
                    xs = [p.x for p in lm]
                    ys = [p.y for p in lm]
                    cx = int(np.mean(xs) * img_w)
                    cy = int(np.mean(ys) * img_h)

                # 顔の半径計算
                xs = [p.x for p in lm]
                ys = [p.y for p in lm]
                minx = int(min(xs) * img_w)
                maxx = int(max(xs) * img_w)
                miny = int(min(ys) * img_h)
                maxy = int(max(ys) * img_h)
                face_w = maxx - minx
                face_h = maxy - miny
                radius = int(0.9 * max(face_w, face_h) / 2)
                radius = max(radius, 20)

                openness = sme.mouth_openness(lm, img_w, img_h)
                face_mouths.append((cx, cy, openness, radius))

            # トラッカー更新
            for (mx, my, openness, radius) in face_mouths:
                matched = None
                best_d = 1e9
                for t in self.face_trackers:
                    d = math.hypot(t['x'] - mx, t['y'] - my)
                    if d < 80 and d < best_d:
                        matched = t
                        best_d = d

                if matched is None:
                    matched = {'x': mx, 'y': my, 'open_accum': 0.0, 'last_seen': now, 'emitting': False, 'emit_timer': 0.0}
                    self.face_trackers.append(matched)

                matched['x'] = mx
                matched['y'] = my
                matched['last_seen'] = now

                if openness >= self.smoke_open_threshold:
                    matched['open_accum'] += dt
                else:
                    matched['open_accum'] = 0.0
                    matched['emitting'] = False
                    matched['emit_timer'] = 0.0

                if matched['open_accum'] >= 2.0 and not matched['emitting']:
                    matched['emitting'] = True
                    matched['emit_timer'] = 0.0
                    matched['open_accum'] = 0.0

                if matched['emitting']:
                    matched['emit_timer'] += dt
                    if matched['emit_timer'] >= self.emit_interval:
                        sme.spawn_puff(self.smoke_particles, matched['x'], matched['y'], now)
                        matched['emit_timer'] = 0.0

                if openness < 0.02:
                    continue

                base_strength = openness * 4.0
                strength = float(np.clip(base_strength, 0.0, 1.5))
                twist = -18.0 * (openness ** 0.9 + openness * 0.5)

                out = sme.apply_spiral_region(out, (mx, my), int(radius * 1.1), twist, strength)
                out = sme.apply_spiral_region(out, (mx, my), radius, twist * 0.6, strength * 0.8)

            self.face_trackers = [t for t in self.face_trackers if now - t['last_seen'] < 1.0]

        out = sme.update_and_draw_smoke(out, self.smoke_particles, dt)
        return out

    def update(self, frame):
        """ゲーム状態の更新"""
        self.bg_timer += 1
        # 手指のベロシティー取得
        hand_velocity = self.get_hand_rotation_velocity(frame)
        
        # 顔エフェクト処理適用（self.current_frameを更新）
        self.current_frame = self.process_face_effect(frame)
        
        # 中心軸の動き（なめらかに）
        self.center_offset += (self.center_target - self.center_offset) * self.center_smooth
        
        # 手が動いている場合は回転速度を更新
        if abs(hand_velocity) > 0.005:
            self.rotation_velocity = hand_velocity
        else:
            self.rotation_velocity *= self.rotation_friction
        
        # ルーレットの回転を更新
        self.rotation += self.rotation_velocity
        self.rotation %= (2 * np.pi)
        
        # パーティクルの更新
        for particle in self.particles:
            particle.update()
        self.particles = [p for p in self.particles if p.is_alive()]
        
        # ゲーム状態に応じた更新
        if self.state == GameState.PLAYING:
            # 速度が十分に低下したら当選判定
            if abs(self.rotation_velocity) < 0.002 and abs(hand_velocity) < 0.002:
                self._on_winning()
        
        elif self.state == GameState.WINNING:
            self.effect_timer += 1
            
            # パーティクルエフェクト
            if self.effect_timer % 5 == 0:
                self._emit_particles()
            
            if self.effect_timer >= 60:
                self.state = GameState.EXPANDING
                self.effect_timer = 0

        elif self.state == GameState.EXPANDING:
            self.effect_timer += 1
            self.expansion_scale += self.expansion_speed
            
            # 拡大中もパーティクル
            if self.effect_timer % 3 == 0:
                self._emit_particles_around_sector()
            
            if self.expansion_scale >= 4.0:
                self.state = GameState.MELTING
                self.melt_timer = 0
                self._initialize_melt_strips()
        
        elif self.state == GameState.MELTING:
            self.melt_timer += 1
            
            if self.melt_timer >= self.melt_duration:
                self._reset_game()

        # CLIの更新
        self._update_cli_logs()

    def _update_cli_logs(self):
        """CLIログの更新"""
        self.cli_timer += 1
        if self.cli_timer % 15 == 0:
            new_log = random.choice(self.cli_tech_strings)
            timestamp = time.strftime("%H:%M:%S", time.localtime())
            self.cli_logs.append(f"[{timestamp}] {new_log}")

    def _on_winning(self):
        """当選時の処理"""
        # 当選セクターを判定
        angle_offset = (self.rotation + np.pi / NUM_SECTORS) % (2 * np.pi)
        self.winning_sector = int(angle_offset / (2 * np.pi / NUM_SECTORS))
        self.winning_color = COLORS[self.winning_sector % len(COLORS)]
        
        self.state = GameState.WINNING
        self.effect_timer = 0
        self.expansion_scale = 1.0

    def _emit_particles(self):
        """ルーレット周辺からパーティクル放出"""
        center = ROULETTE_CENTER
        angle = np.random.uniform(0, 2 * np.pi)
        
        px = center[0] + ROULETTE_RADIUS * np.cos(angle)
        py = center[1] + ROULETTE_RADIUS * np.sin(angle)
        
        vx = np.random.uniform(-3, 3)
        vy = np.random.uniform(-5, 1)
        
        color = COLORS[self.winning_sector % len(COLORS)]
        particle = Particle(px, py, vx, vy, 60, color, size=8)
        self.particles.append(particle)

    def _emit_particles_around_sector(self):
        """当選セクター周辺からパーティクル放出"""
        center = np.array(ROULETTE_CENTER) + self.center_offset
        
        start_angle = (2 * np.pi * self.winning_sector / NUM_SECTORS) - self.rotation
        end_angle = (2 * np.pi * (self.winning_sector + 1) / NUM_SECTORS) - self.rotation
        figure_angle = (start_angle + end_angle) / 2
        
        # セクター周辺に複数のパーティクル
        for _ in range(5):
            offset_angle = np.random.uniform(-0.3, 0.3)
            angle = figure_angle + offset_angle
            
            radius = ROULETTE_RADIUS * (0.6 + np.random.uniform(-0.1, 0.1))
            px = center[0] + radius * np.cos(angle)
            py = center[1] + radius * np.sin(angle)
            
            # 中心方向への速度
            direction = np.array([center[0] - px, center[1] - py])
            direction = direction / np.linalg.norm(direction) if np.linalg.norm(direction) > 0 else np.array([0, 0])
            
            vx = direction[0] * 2 + np.random.uniform(-1, 1)
            vy = direction[1] * 2 + np.random.uniform(-1, 1)
            
            color = self.winning_color
            particle = Particle(px, py, vx, vy, 80, color, size=10)
            self.particles.append(particle)

    def _initialize_melt_strips(self):
        """溶け効果のストリップを初期化"""
        self.melt_strips = []
        strip_width = WINDOW_WIDTH // 20
        
        for i in range(20):
            strip = {
                'x': i * strip_width,
                'width': strip_width,
                'melt_y': 0,
                'drip_points': []
            }
            self.melt_strips.append(strip)

    def _reset_game(self):
        """ゲームをリセット（ここで回転方向を反転させる）"""
        self.bg_direction *= -1  # 溶け落ち（上から下のエフェクト）完了をトリガーに反転
        self.state = GameState.PLAYING
        self.rotation = 0.0
        self.rotation_velocity = 0.0
        self.center_offset = np.array([0.0, 0.0])
        self.center_target = np.array([0.0, 0.0])
        self.effect_timer = 0
        self.expansion_scale = 1.0
        self.melt_timer = 0
        self.melt_strips = []
        self.particles = []
        if self.video:
            self.video.restart()



    def draw_winning_effect(self, surface):
        """当選時のエフェクト描画"""
        if self.state == GameState.WINNING or self.state == GameState.EXPANDING:
            center = np.array(ROULETTE_CENTER) + self.center_offset
            
            start_angle = (2 * np.pi * self.winning_sector / NUM_SECTORS) - self.rotation
            end_angle = (2 * np.pi * (self.winning_sector + 1) / NUM_SECTORS) - self.rotation
            figure_angle = (start_angle + end_angle) / 2
            
            # 拡大するセクター
            scale = self.expansion_scale if self.state == GameState.EXPANDING else 1.0 + self.effect_timer / 60
            
            # セクターの図形を大きく描画
            effect_radius = ROULETTE_RADIUS * 0.65
            effect_x = center[0] + effect_radius * np.cos(figure_angle) * (0.5 + scale * 0.5)
            effect_y = center[1] + effect_radius * np.sin(figure_angle) * (0.5 + scale * 0.5)
            
            effect_size = int(50 * scale)
            shape_draw_func = self.shapes[self.winning_sector % len(self.shapes)]
            
            # グロー効果
            for glow in range(effect_size, 0, -15):
                alpha = max(0, 1 - (effect_size - glow) / effect_size)
                glow_color = tuple(int(c * (0.5 + alpha * 0.5)) for c in self.winning_color)
                shape_draw_func(surface, int(effect_x), int(effect_y), glow, glow_color)
            
            # テキスト
            if self.effect_timer > 20:
                congratulations = self.font_large.render("おめでとう！", True, (255, 255, 100))
                rect = congratulations.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
                
                # テキストの輝き効果
                shadow = self.font_large.render("おめでとう！", True, (200, 150, 50))
                surface.blit(shadow, (rect.x + 3, rect.y + 3))
                surface.blit(congratulations, rect)

    def draw_melt_effect(self, surface):
        """溶け効果の描画"""
        if self.state == GameState.MELTING:
            progress = self.melt_timer / self.melt_duration
            
            # スクリーンをコピーして変形
            for strip in self.melt_strips:
                melt_height = int(WINDOW_HEIGHT * progress * 1.2)
                
                # ドリップ効果
                drip_variation = int(50 * np.sin(progress * np.pi) * (1 + 0.5 * np.sin(strip['x'] / 100)))
                
                # 上から下への黒い帯
                pygame.draw.rect(surface, (0, 0, 0), 
                               (strip['x'], 0, strip['width'], melt_height + drip_variation))
                
                # ドリップの端
                for drip_offset in range(0, strip['width'], 10):
                    drip_y = melt_height + drip_variation
                    drip_length = drip_variation // 2
                    pygame.draw.line(surface, (0, 0, 0), 
                                   (strip['x'] + drip_offset, drip_y),
                                   (strip['x'] + drip_offset, drip_y + drip_length), 2)

    def draw_particles(self, surface):
        """パーティクルの描画"""
        for particle in self.particles:
            particle.draw(surface)

    def draw_spectrum_background(self, surface):
        """計算によるスペクトラムな背景演出（動画が読み込めない場合のバックアップ兼、追加演出）"""
        # 動画がない場合、または動画の上に薄く重ねる
        center = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        # bg_direction を掛けて回転方向を制御
        time_factor = self.bg_timer * 0.02 * self.bg_direction
        
        # 画面中央から虹色のスパイラルを細かく描画
        num_strands = 12
        for i in range(num_strands):
            points = []
            strand_offset = i * (2 * np.pi / num_strands) + time_factor
            
            # 色の変化（スペクトラム）
            hue = (i / num_strands + time_factor * 0.1) % 1.0
            
            # 2本の手の距離に応じて彩度や明度を調整
            saturation = 80
            lightness = 50
            if self.hand_distance_info:
                avg_dist = sum(d['dist'] for d in self.hand_distance_info) / len(self.hand_distance_info)
                # 距離に応じて変化 (100-500px程度を想定)
                saturation = min(100, 50 + avg_dist / 10)
                lightness = min(90, 30 + avg_dist / 15)
                hue = (hue + avg_dist / 1000) % 1.0

            color = pygame.Color(0)
            color.hsla = (hue * 360, saturation, lightness, 40) # 透過度40
            
            for r in range(0, int(WINDOW_WIDTH), 15):
                angle = r * 0.005 + strand_offset
                x = center[0] + r * np.cos(angle)
                y = center[1] + r * np.sin(angle)
                points.append((x, y))
            
            if len(points) > 1:
                pygame.draw.lines(surface, color, False, points, 4)

    def _draw_fancy_marker(self, surface, pos, scale=0.6):
        """スネークゲームスタイルの派手なマーカーを描画"""
        x, y = pos
        # サイズ設定: 元のラジウスをスケール
        r1, r2, r3, r4 = int(25 * scale), int(18 * scale), int(12 * scale), int(8 * scale)
        cross_len = int(15 * scale)
        thickness1 = max(1, int(3 * scale))
        thickness2 = max(1, int(2 * scale))

        # 外側の円 (Red)
        pygame.draw.circle(surface, (255, 100, 100), (x, y), r1, thickness1)
        # 中間の円 (Light Red)
        pygame.draw.circle(surface, (255, 150, 150), (x, y), r2, thickness2)
        # 内側の円 (Lighter Red)
        pygame.draw.circle(surface, (255, 200, 200), (x, y), r3, thickness2)
        # 指先の中心を強調 (Solid Red)
        pygame.draw.circle(surface, (255, 50, 50), (x, y), r4)
        # 十字マーク (Yellow)
        pygame.draw.line(surface, (255, 255, 0), (x - cross_len, y), (x + cross_len, y), thickness2)
        pygame.draw.line(surface, (255, 255, 0), (x, y - cross_len), (x, y + cross_len), thickness2)

    def draw_camera_frame(self, surface):
        """カメラ映像のプレビューを画面左右に垂直中央で表示"""
        if self.current_frame is None:
            return

        # サイズ設定: 240x180
        frame_width = 240
        frame_height = 180
        
        # フレームをリサイズしRGBに変換
        frame_resized = cv2.resize(self.current_frame, (frame_width, frame_height))
        frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
        
        # Pygame用Surfaceのベースを作成
        preview_surf = pygame.image.fromstring(
            frame_rgb.tobytes(),
            (frame_width, frame_height),
            'RGB'
        )
        
        # 骨格情報を描画
        if self.hand_results and self.hand_results.multi_hand_landmarks:
            for hand_landmarks in self.hand_results.multi_hand_landmarks:
                pts = []
                for landmark in hand_landmarks.landmark:
                    px = int(landmark.x * frame_width)
                    py = int(landmark.y * frame_height)
                    pts.append((px, py))

                # 指ごとの色と接続定義
                # (接続ペアのリスト, 色)
                finger_specs = [
                    # 親指 (Red)
                    ([(0, 1), (1, 2), (2, 3), (3, 4)], (255, 50, 50)),
                    # 人差し指 (Yellow/Gold)
                    ([(0, 5), (5, 6), (6, 7), (7, 8)], (255, 215, 0)),
                    # 中指 (Green)
                    ([(0, 9), (9, 10), (10, 11), (11, 12)], (50, 255, 50)),
                    # 薬指 (Cyan)
                    ([(0, 13), (13, 14), (14, 15), (15, 16)], (50, 255, 255)),
                    # 小指 (Purple/Magenta)
                    ([(0, 17), (17, 18), (18, 19), (19, 20)], (255, 50, 255)),
                    # 手のひら (White) - 指の付け根をつなぐ
                    ([(5, 9), (9, 13), (13, 17)], (200, 200, 200))
                ]

                # 接続線の描画
                for connections, color in finger_specs:
                    for start_idx, end_idx in connections:
                        start_pt = pts[start_idx]
                        end_pt = pts[end_idx]
                        pygame.draw.line(preview_surf, color, start_pt, end_pt, 2)

                # 関節点（ランドマーク）の描画 - 接続線の色に合わせて点を描画
                # 点は上書きされる可能性があるので、親指から順に描画
                # 0番（手首）は共通なので最後に白で描画しても良いが、ここでは各指のループで描画してしまう
                
                # まず手首(0)を白で
                pygame.draw.circle(preview_surf, (255, 255, 255), pts[0], 3)

                # 各指の関節を描画
                finger_indices = [
                    (range(1, 5), (255, 50, 50)),    # 親指
                    (range(5, 9), (255, 215, 0)),    # 人差し指
                    (range(9, 13), (50, 255, 50)),   # 中指
                    (range(13, 17), (50, 255, 255)), # 薬指
                    (range(17, 21), (255, 50, 255))  # 小指
                ]

                for indices, color in finger_indices:
                    for idx in indices:
                        pygame.draw.circle(preview_surf, color, pts[idx], 3)

                # 人差し指の先端(8)に派手なマーカーを表示
                tip_pos = pts[8]
                self._draw_fancy_marker(preview_surf, tip_pos, scale=0.5)

        # 配置位置の計算
        pos_y = (WINDOW_HEIGHT - frame_height) // 2
        margin = 15
        
        # 左側のプレビュー
        surface.blit(preview_surf, (margin, pos_y))
        pygame.draw.rect(surface, (255, 255, 255), (margin, pos_y, frame_width, frame_height), 2)
        
        # 右側のプレビュー
        surface.blit(preview_surf, (WINDOW_WIDTH - frame_width - margin, pos_y))
        pygame.draw.rect(surface, (255, 255, 255), (WINDOW_WIDTH - frame_width - margin, pos_y, frame_width, frame_height), 2)

    def draw_roulette_with_alpha(self):
        """ルーレットを透過Surfaceに描画し、アルファ値を設定"""
        self.roulette_surface.fill((0, 0, 0, 0))  # 透明にリセット
        
        center = np.array(ROULETTE_CENTER) + self.center_offset
        center = tuple(center.astype(int))
        
        # 透過度設定 (0-255)
        # 背景が見えにくい場合は、この数値をより小さく(例:120)してください
        roulette_alpha = 140 # ルーレット本体の透過度
        
        # 各セクターを描画
        for i in range(NUM_SECTORS):
            start_angle = (2 * np.pi * i / NUM_SECTORS) - self.rotation
            end_angle = (2 * np.pi * (i + 1) / NUM_SECTORS) - self.rotation
            
            # セクターの色にアルファ値を混ぜる
            base_color = COLORS[i % len(COLORS)]
            color = (*base_color, roulette_alpha)
            
            # セクターのポイント計算
            points = [center]
            num_points = 50
            for j in range(num_points + 1):
                angle = start_angle + (end_angle - start_angle) * j / num_points
                px = center[0] + ROULETTE_RADIUS * np.cos(angle)
                py = center[1] + ROULETTE_RADIUS * np.sin(angle)
                points.append((int(px), int(py)))
            
            pygame.draw.polygon(self.roulette_surface, color, points)
            pygame.draw.polygon(self.roulette_surface, (0, 0, 0, roulette_alpha), points, 3)
            
            # 図形を描画
            shape_draw_func = self.shapes[i % len(self.shapes)]
            figure_angle = (start_angle + end_angle) / 2
            figure_x = center[0] + ROULETTE_RADIUS * 0.65 * np.cos(figure_angle)
            figure_y = center[1] + ROULETTE_RADIUS * 0.65 * np.sin(figure_angle)
            
            shape_alpha_color = (50, 50, 50, roulette_alpha)
            shape_draw_func(self.roulette_surface, int(figure_x), int(figure_y), 30, shape_alpha_color)
        
        # 中心円
        pygame.draw.circle(self.roulette_surface, (255, 255, 255, roulette_alpha), center, 25, 0)
        pygame.draw.circle(self.roulette_surface, (0, 0, 0, roulette_alpha), center, 25, 4)
        
        # 中心の装飾
        center_color = self.winning_color if self.state != GameState.PLAYING else (200, 200, 200)
        pygame.draw.circle(self.roulette_surface, (*center_color, roulette_alpha), center, 15, 0)
        
        # 上部マーカー
        marker_x = ROULETTE_CENTER[0]
        marker_y = MARKER_Y
        pygame.draw.polygon(self.roulette_surface, (255, 0, 0, 220), [
            (marker_x - 15, marker_y),
            (marker_x + 15, marker_y),
            (marker_x, marker_y + 25)
        ])

    def draw_cli_window(self, surface):
        """CLIウィンドウの描画"""
        margin = 15
        x = WINDOW_WIDTH - self.cli_width - margin
        y = margin
        
        # ウィンドウの背景 (半透明の黒)
        cli_bg = pygame.Surface((self.cli_width, self.cli_height), pygame.SRCALPHA)
        pygame.draw.rect(cli_bg, (0, 0, 0, 180), (0, 0, self.cli_width, self.cli_height), border_radius=8)
        pygame.draw.rect(cli_bg, (255, 255, 255, 200), (0, 0, self.cli_width, self.cli_height), 2, border_radius=8)
        
        # ヘッダーバー (Mac風 - モノクロ版)
        pygame.draw.rect(cli_bg, (40, 40, 40, 220), (0, 0, self.cli_width, 25), border_top_left_radius=8, border_top_right_radius=8)
        # 閉じる・最小化・拡大ボタンっぽいやつ (グレー)
        for i, color in enumerate([(100, 100, 100), (130, 130, 130), (160, 160, 160)]):
            pygame.draw.circle(cli_bg, color, (15 + i*20, 12), 6)
            
        title = self.font_small.render("SYSTEM_IDENT_PROCESSING", True, (180, 180, 180))
        cli_bg.blit(title, (75, 5))
        
        # ログメッセージの描画
        line_height = 14
        for i, log in enumerate(list(self.cli_logs)):
            log_surf = self.font_small.render(log, True, (255, 255, 255))
            # 古いメッセージほど暗く
            alpha = int(255 * (i + 1) / len(self.cli_logs))
            log_surf.set_alpha(alpha)
            cli_bg.blit(log_surf, (10, 35 + i * line_height))
            
        # 点滅カーソル
        if (self.cli_timer // 20) % 2 == 0:
            cursor_y = 35 + len(self.cli_logs) * line_height
            if cursor_y < self.cli_height - 30:
                pygame.draw.rect(cli_bg, (255, 255, 255), (10, cursor_y, 8, 12))
            
        # 固定システム情報 (白)
        sys_info = f"FPS: {self.clock.get_fps():.1f} | VEL: {self.rotation_velocity:.4f}"
        sys_surf = self.font_small.render(sys_info, True, (255, 255, 255))
        cli_bg.blit(sys_surf, (10, self.cli_height - 20))

        surface.blit(cli_bg, (x, y))

    def draw(self, surface):
        """画面の描画"""
        # 1. 背景の描画 (一番奥)
        if self.video:
            self.video.update()
            if not self.video.active:
                self.video.restart()
            self.video.draw(surface, (0, 0, WINDOW_WIDTH, WINDOW_HEIGHT))
            # 動画の上にさらに薄くスペクトラムを重ねる
            self.draw_spectrum_background(surface)
        else:
            surface.fill((10, 10, 30)) # 暗い背景
            self.draw_spectrum_background(surface)
        
        # 2. ルーレットの描画 (透過Surfaceを使用して合成)
        # 溶け落ち中(MELTING)以外はルーレットを表示
        if self.state != GameState.MELTING:
            self.draw_roulette_with_alpha()
            surface.blit(self.roulette_surface, (0, 0))
        
        # 3. エフェクト (溶け落ちエフェクトは最前面)
        self.draw_particles(surface)
        self.draw_winning_effect(surface)
        self.draw_melt_effect(surface)
        self.draw_camera_frame(surface)
        self.draw_cli_window(surface)
        
        # 手の距離情報の描画
        if self.hand_distance_info:
            for info in self.hand_distance_info:
                p1 = info['pos1']
                p2 = info['pos2']
                dist = info['dist']
                # 画面の中央にマッピングが必要かもしれないが、今は物理カメラ座標のまま
                # draw_camera_frame でプレビューは 240x180 だが、座標は 640x480 (cap size)
                # 画面全体 (WINDOW_WIDTH x WINDOW_HEIGHT) にマッピングする
                scale_x = WINDOW_WIDTH / 640
                scale_y = WINDOW_HEIGHT / 480
                scr_p1 = (int(p1[0] * scale_x), int(p1[1] * scale_y))
                scr_p2 = (int(p2[0] * scale_x), int(p2[1] * scale_y))
                
                pygame.draw.line(surface, (255, 255, 255), scr_p1, scr_p2, 2)
                mid_p = ((scr_p1[0] + scr_p2[0]) // 2, (scr_p1[1] + scr_p2[1]) // 2)
                dist_text = self.font_small.render(f"{dist:.1f}", True, (255, 255, 255))
                surface.blit(dist_text, mid_p)

        # 情報表示
        info_text = f"Velocity: {self.rotation_velocity:.4f} | State: {self.state.name} | Press R to reset"
        info = self.font_small.render(info_text, True, (255, 255, 255))
        surface.blit(info, (10, 10))
        
        pygame.display.flip()

    def run(self):
        """メインループ"""
        running = True
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        self._reset_game()
                    elif event.key == pygame.K_SPACE:
                        # テスト用：スペースキーで当選
                        self._on_winning()
            
            # フレーム取得
            ret, frame = self.cap.read()
            if not ret:
                break
            
            # フレームを水平反転（鏡像）
            frame = cv2.flip(frame, 1)
            
            # ゲーム更新
            self.update(frame)
            
            # 描画
            self.draw(self.screen)
            
            # FPS制御
            self.clock.tick(FPS)
        
        self.cleanup()

    def cleanup(self):
        """リソースのクリーンアップ"""
        if self.video:
            self.video.close()
        self.cap.release()
        cv2.destroyAllWindows()
        pygame.quit()


# ==================== Main ====================
if __name__ == "__main__":
    game = RouletteGame()
    game.run()