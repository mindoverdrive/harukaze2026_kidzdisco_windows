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
Magic Mirror Canvas - Interactive Art
mediapipe + pygame

自分自身がキャンバスになる、インタラクティブなビジュアルアートプログラム。
- 手指の動きに合わせてパーティクルが舞う
- 口を開けるとエフェクトが発生する
"""

import pygame
import numpy as np
import cv2
import mediapipe as mp
import random
import time
import math
from typing import List, Tuple, Dict
import sys
import os

# Add test directory to path to import local modules if needed
sys.path.append(os.path.join(os.path.dirname(__file__), 'test'))

try:
    # Try importing as if 'test' is in path (e.g. from inside test dir or if appended)
    from hand_tracker import HandTracker
    import spiral_mouth_effect as sme
    from kaleidoscope import KaleidoscopeEffect
except ImportError:
    try:
        # Try importing as package from root
        from test.hand_tracker import HandTracker
        import test.spiral_mouth_effect as sme
        from kaleidoscope import KaleidoscopeEffect
    except ImportError as e:
        print(f"Error importing modules: {e}")
        print("Please ensure 'test/hand_tracker.py', 'test/spiral_mouth_effect.py', and 'kaleidoscope.py' exist.")
        sys.exit(1)


# ==================== Constants ====================
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 960
FPS = 60

# Colors - Traditional Japanese "Shibui" palette
COLOR_BG = (10, 12, 18)  # Deep midnight (Kachiiro)
COLOR_SYSTEM_TEXT = (100, 105, 115)

# Astringent color palette (Muted, sophisticated)
COLOR_PALETTE = {
    "kachiiro": (13, 17, 38),     # Victory blue (Deep indigo)
    "kokutan": (28, 28, 28),     # Ebony
    "tokiwairo": (27, 46, 33),   # Evergreen
    "edomurasaki": (59, 43, 64), # Edo purple
    "ginnezumi": (145, 150, 153),# Silver gray
    "keshigane": (145, 125, 80), # Muted gold
    "fukusage": (61, 64, 53),    # Muted moss green
}

# Trad palettes for effects
SHIBUI_PALETTE = [
    (145, 125, 80),  # Keshigane (Muted gold)
    (60, 80, 100),   # Muted deep blue
    (80, 60, 80),    # Muted plum
    (100, 110, 90),  # Muted sage
    (120, 100, 90),  # Muted clay
    (70, 70, 80),    # Slate gray
]

# Particle configurations
GRAVITY = 0.2
FRICTION = 0.95

# Subtle, translucent palette for ripples
RIPPLE_COLORS_PALETTE = [
    (145, 125, 80),  # Gold
    (180, 190, 200), # Silver/White
    (100, 120, 140), # Pale blue
    (120, 100, 110), # Pale plum
]


# ==================== Particle System ====================
class Particle:
    def __init__(self, x, y, vx, vy, color, size, lifetime, p_type="normal"):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.size = size
        self.initial_size = size
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.p_type = p_type

    def update(self):
        self.x += self.vx
        self.y += self.vy
        
        if self.p_type == "spark":
            self.vy += GRAVITY
            self.vx *= FRICTION
            self.vy *= FRICTION
        elif self.p_type == "floaty":
            self.vy -= 0.05 # Float up
            self.x += math.sin(time.time() * 10 + self.y * 0.1) * 0.5
            
        self.lifetime -= 1

    def draw(self, surface):
        if self.lifetime <= 0:
            return
            
        alpha = max(0, min(255, int(255 * (self.lifetime / self.max_lifetime))))
        
        # Pygame uses simple ints for pos
        ix, iy = int(self.x), int(self.y)
        
        # Scaling size
        current_size = max(0, self.size * (self.lifetime / self.max_lifetime))
        
        # Create a surface for transparency support if needed, or simple direct drawing
        # For performance with many particles, direct drawing is faster.
        # If we really want alpha blending per particle, we need a surface or gfxdraw.
        # For now, let's just fade size or use non-alpha for speed unless crucial.
        # Or simulated alpha by darkening color
        
        r, g, b = self.color
        # Simple fade to black/bg
        fade = self.lifetime / self.max_lifetime
        curr_color = (int(r * fade), int(g * fade), int(b * fade))
        
        if self.p_type == "spark":
            pygame.draw.circle(surface, curr_color, (ix, iy), int(current_size))
        elif self.p_type == "floaty":
            s = pygame.Surface((int(current_size*2), int(current_size*2)), pygame.SRCALPHA)
            pygame.draw.circle(s, (*self.color, alpha), (int(current_size), int(current_size)), int(current_size))
            surface.blit(s, (ix - int(current_size), iy - int(current_size)))
        else:
             pygame.draw.circle(surface, curr_color, (ix, iy), int(current_size))


class RippleEffect:
    """波紋エフェクト - 口や手の開き方が波のように広がり、ぷるぷる震える"""
    def __init__(self, x, y, max_radius, max_lifetime, strength=1.0, base_color_idx=0):
        self.x = x
        self.y = y
        self.max_radius = max_radius
        self.lifetime = max_lifetime
        self.max_lifetime = max_lifetime
        self.strength = strength
        self.base_color_idx = base_color_idx
        self.creation_time = time.time()
        self.rings = []  # Internal rings for texture
        
        # Create multiple rings for wave texture
        for i in range(3):
            ring_delay = int((i / 3) * max_lifetime * 0.3)
            self.rings.append({
                'start_time': ring_delay,
                'width': 15 + i * 5
            })

    def get_color(self):
        """時間に基づいて色をゆっくり変化させる"""
        elapsed = time.time() - self.creation_time
        # 色パレットを順番に周回（約2秒で色が変わる）
        color_idx = int((elapsed * 0.5) + self.base_color_idx) % len(RIPPLE_COLORS_PALETTE)
        return RIPPLE_COLORS_PALETTE[color_idx]

    def update(self):
        self.lifetime -= 1

    def draw(self, surface):
        if self.lifetime <= 0:
            return
        
        progress = 1.0 - (self.lifetime / self.max_lifetime)
        current_radius = self.max_radius * progress
        
        # Alpha fade - very soft
        alpha = max(0, 1.0 - progress) * 0.6
        
        # Get time-varying color
        base_color = self.get_color()
        
        # 波形効果：振動を抑え、静かな拡がりを表現
        vibration = math.sin(time.time() * 2) * 1.5
        vibrant_radius = current_radius + vibration
        
        # Soft ring
        ring_color = tuple(int(c * alpha * self.strength) for c in base_color)
        
        if vibrant_radius > 5:
            # Subtle width
            pygame.draw.circle(surface, ring_color, (int(self.x), int(self.y)), int(vibrant_radius), 1)
        
        # Inner subtle ring
        for ring_idx, ring in enumerate(self.rings[:2]): # Fewer rings
            ring_progress = progress - (ring['start_time'] / self.max_lifetime * 0.5)
            if 0 <= ring_progress <= 1:
                ring_radius = self.max_radius * ring_progress * 0.8
                ring_alpha = max(0, 1.0 - ring_progress) * 0.2
                
                inner_color = tuple(int(c * ring_alpha) for c in base_color)
                
                if ring_radius > 2:
                    pygame.draw.circle(surface, inner_color, (int(self.x), int(self.y)), int(ring_radius), 1)


class BackgroundGenerator:
    """アニメーション背景生成 - サイケデリックなグラデーションとノイズ"""
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.creation_time = time.time()
        
        # Background color progression - Deep and quiet
        self.bg_colors = [
            ((5, 5, 10), (15, 20, 35)),      # Midnight blue
            ((10, 5, 15), (25, 15, 30)),     # Deep plum
            ((5, 15, 10), (15, 30, 20)),     # Deep forest
            ((10, 10, 5), (25, 20, 10)),     # Deep earth
        ]
    
    def get_gradient_colors(self):
        """時間に基づいて背景色を取得"""
        elapsed = time.time() - self.creation_time
        cycle_idx = int((elapsed * 0.3)) % len(self.bg_colors)
        next_idx = (cycle_idx + 1) % len(self.bg_colors)
        
        # Smooth transition between color schemes
        phase = (elapsed * 0.3) % 1.0
        
        curr_colors = self.bg_colors[cycle_idx]
        next_colors = self.bg_colors[next_idx]
        
        # Interpolate colors
        color1 = tuple(
            int(curr_colors[0][i] + (next_colors[0][i] - curr_colors[0][i]) * phase)
            for i in range(3)
        )
        color2 = tuple(
            int(curr_colors[1][i] + (next_colors[1][i] - curr_colors[1][i]) * phase)
            for i in range(3)
        )
        
        return color1, color2
    
    def generate(self, ripple_count=0):
        """背景を生成"""
        bg_surface = pygame.Surface((self.width, self.height))
        
        # Get animated colors
        color1, color2 = self.get_gradient_colors()
        
        # Create vertical gradient
        for y in range(self.height):
            # Gradient interpolation
            progress = y / self.height
            r = int(color1[0] + (color2[0] - color1[0]) * progress)
            g = int(color1[1] + (color2[1] - color1[1]) * progress)
            b = int(color1[2] + (color2[2] - color1[2]) * progress)
            
            # Add subtle animated wave to gradient
            wave_offset = math.sin(time.time() * 2 + y * 0.01) * 8
            r = int(max(0, min(255, r + wave_offset * 0.3)))
            g = int(max(0, min(255, g + wave_offset * 0.2)))
            b = int(max(0, min(255, b + wave_offset * 0.4)))
            
            pygame.draw.line(bg_surface, (r, g, b), (0, y), (self.width, y))
        
        # Add animated noise overlay
        self._add_noise_layer(bg_surface, ripple_count)
        
        return bg_surface
    
    def _add_noise_layer(self, surface, ripple_count):
        """ノイズレイヤーを追加"""
        noise_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        
        # Generate animated Perlin-like noise (simple sine/cosine based)
        for x in range(0, self.width, 40):
            for y in range(0, self.height, 40):
                # Animated noise
                noise_val = math.sin(x * 0.01 + time.time() * 1.5) * math.cos(y * 0.01 + time.time() * 1.2)
                noise_intensity = int((noise_val + 1) * 0.5 * 255 * 0.1)  # 10% opacity
                
                # Ripple count affects noise intensity
                extra_intensity = ripple_count * 8
                noise_intensity = min(255, noise_intensity + extra_intensity)
                
                color = (200, 150, 220, noise_intensity)
                pygame.draw.circle(noise_surface, color, (x, y), 20)
        
        surface.blit(noise_surface, (0, 0))


class InkOrPetal:
    """墨・花弁エフェクト - 静かに舞い、滲む表現"""
    def __init__(self, x, y, obj_type="ink", size=30, lifetime=180, color_idx=0):
        self.x = x
        self.y = y
        self.obj_type = obj_type # "ink" or "petal"
        self.size = size
        self.initial_size = size
        self.rotation = random.uniform(0, 360)
        self.rot_speed = random.uniform(-0.5, 0.5)
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        self.color_idx = color_idx
        self.vx = random.uniform(-0.3, 0.3)
        self.vy = random.uniform(0.1, 0.5) # Slowly fall
    
    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.rotation += self.rot_speed
        self.lifetime -= 1
        
        if self.obj_type == "ink":
            # Ink spreads and fades
            self.size = self.initial_size * (1.0 + (1.0 - self.lifetime / self.max_lifetime))
        else:
            # Petal wiggles
            self.vx += math.sin(time.time() * 2) * 0.05
    
    def draw(self, surface):
        if self.lifetime <= 0:
            return
        
        alpha_factor = self.lifetime / self.max_lifetime
        base_color = SHIBUI_PALETTE[self.color_idx % len(SHIBUI_PALETTE)]
        
        if self.obj_type == "ink":
            # Soft circular gradient like ink drop
            alpha = int(100 * alpha_factor)
            mask = pygame.Surface((int(self.size * 2), int(self.size * 2)), pygame.SRCALPHA)
            pygame.draw.circle(mask, (*base_color, alpha), (int(self.size), int(self.size)), int(self.size))
            surface.blit(mask, (int(self.x - self.size), int(self.y - self.size)))
        else:
            # Petal shape (ellipse)
            alpha = int(150 * alpha_factor)
            petal_surf = pygame.Surface((int(self.size), int(self.size * 1.5)), pygame.SRCALPHA)
            pygame.draw.ellipse(petal_surf, (*base_color, alpha), (0, 0, int(self.size), int(self.size * 1.5)))
            rotated = pygame.transform.rotate(petal_surf, self.rotation)
            surface.blit(rotated, (int(self.x - rotated.get_width()/2), int(self.y - rotated.get_height()/2)))


class GoldenThread:
    """金糸 - 指先から放たれる繊細な光の糸"""
    def __init__(self, x1, y1, x2, y2, color, lifetime=60):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.color = color
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        # Subtle waving
        self.phase = random.uniform(0, math.pi * 2)
    
    def update(self):
        self.lifetime -= 1
        # Slowly drift
        self.y1 += 0.1
        self.y2 += 0.1
    
    def draw(self, surface):
        if self.lifetime <= 0:
            return
        
        alpha = self.lifetime / self.max_lifetime
        color = tuple(int(c * alpha * 0.7) for c in self.color)
        
        # Draw wavy thread instead of straight line
        points = []
        num_segments = 10
        for i in range(num_segments + 1):
            t = i / num_segments
            px = self.x1 + (self.x2 - self.x1) * t
            py = self.y1 + (self.y2 - self.y1) * t
            # Add wave
            offset = math.sin(t * math.pi + self.phase + time.time() * 2) * 5 * (1.0 - t)
            points.append((px + offset, py))
            
        if len(points) > 1:
            pygame.draw.lines(surface, color, False, points, 1)


class EffectSystem:
    def __init__(self):
        self.particles: List[Particle] = []
        self.ripples: List[RippleEffect] = []
        self.ink_objects: List[InkOrPetal] = []
        self.threads: List[GoldenThread] = []

    def emit(self, x, y, count=1, color=(255, 255, 255), speed=2.0, size=5, life=30, p_type="normal"):
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            sp = random.uniform(0.5, speed)
            vx = math.cos(angle) * sp
            vy = math.sin(angle) * sp
            self.particles.append(Particle(x, y, vx, vy, color, size, life, p_type))
    
    def emit_ripple(self, x, y, max_radius=200, lifetime=40, strength=1.0, color_idx=0):
        """波紋を発生させる"""
        self.ripples.append(RippleEffect(x, y, max_radius, lifetime, strength, color_idx))
    
    def emit_ink_petal(self, x, y, obj_type="ink", size=30, lifetime=180, color_idx=0):
        """墨や花弁を発生させる"""
        self.ink_objects.append(InkOrPetal(x, y, obj_type, size, lifetime, color_idx))
    
    def emit_thread(self, x1, y1, x2, y2, color, lifetime=60):
        """光の糸を発生させる"""
        self.threads.append(GoldenThread(x1, y1, x2, y2, color, lifetime))

    def update(self):
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.lifetime > 0]
        
        for r in self.ripples:
            r.update()
        self.ripples = [r for r in self.ripples if r.lifetime > 0]
        
        for ink in self.ink_objects:
            ink.update()
        self.ink_objects = [ink for ink in self.ink_objects if ink.lifetime > 0]
        
        for t in self.threads:
            t.update()
        self.threads = [t for t in self.threads if t.lifetime > 0]

    def draw(self, surface):
        # Draw ripples first
        for r in self.ripples:
            r.draw(surface)
        # Threads
        for t in self.threads:
            t.draw(surface)
        # Ink objects
        for ink in self.ink_objects:
            ink.draw(surface)
        # Particles
        for p in self.particles:
            p.draw(surface)


# ==================== Main Application ====================
class InteractiveArtApp:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("Magic Mirror Canvas")
        self.clock = pygame.time.Clock()
        self.running = True

        # Camera Setup
        self.cap = cv2.VideoCapture(2) # Try 1 first (often external or OBS), if fails cascade to 0?
        if not self.cap.isOpened():
             print("Camera 1 failed, trying 0...")
             self.cap = cv2.VideoCapture(2)
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720) # Request 720p or similar

        # MediaPipe Setup
        self.hand_tracker = HandTracker(max_num_hands=2, detection_conf=0.7, track_conf=0.7)
        
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        # Effects
        self.effect_system = EffectSystem()
        self.background_gen = BackgroundGenerator(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.kaleidoscope = KaleidoscopeEffect(WINDOW_WIDTH, WINDOW_HEIGHT, segments=8)
        
        # State
        self.prev_time = time.time()
        self.mouth_open_accum = 0.0
        self.last_ripple_count = 0
        
        # Finger colors - Traditional shibui palette
        self.finger_colors = SHIBUI_PALETTE[:5]
        
        # Ripple triggered threshold and accumulator
        self.hand_open_threshold = 0.15
        self.mouth_open_threshold = 0.15
        
        # Flashy effects control
        self.last_shape_spawn_time = 0
        self.shape_spawn_cooldown = 1.0  # Slower spawn
        self.laser_threshold = 0.85  # Harder to trigger threads
        self.thread_intensity = 0.0

        # Kaleidoscope mapping state
        self.target_segments = 8
        self.current_segments = 8
        self.target_rotation = 0
        self.current_rotation = 0
        self.target_zoom = 1.0
        self.current_zoom = 1.0
        self.kaleidoscope_center = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)

    def process_camera(self):
        ret, frame = self.cap.read()
        if not ret:
            return None
        
        # Flip for mirror effect
        frame = cv2.flip(frame, 1)
        
        # Resize to window size if needed (usually better to keep aspect ratio)
        # For simplicity, we'll scale to window
        frame = cv2.resize(frame, (WINDOW_WIDTH, WINDOW_HEIGHT))
        
        return frame

    def draw_hand_effects(self, frame_rgb):
        # We need the frame in a format HandTracker accepts (it converts to RGB inside, but here we might pass BGR if using the lib as is, or RGB)
        # Local HandTracker expects BGR usually if it's wrapper around cv2.cvtColor. 
        # Let's verify: HandTracker.find_hands does cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).
        # So we should pass BGR (original opencv frame).
        
        # However, for efficiency, if we already have RGB for display, we might want to modify.
        # But let's stick to the interface: pass BGR.
        
        # Re-convert back to BGR for HandTracker? 
        # Wait, process_camera returns BGR (standard OpenCV).
        # We'll use local variable for BGR frame to pass to trackers.
        pass
    
    # _apply_glitch_effect removed for refined aesthetic
    
    def run(self):
        while self.running:
            # 1. Event Handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        self.running = False

            # 2. Capture and Process
            frame_bgr = self.process_camera()
            if frame_bgr is None:
                continue

            # Convert to RGB for face mesh (it expects RGB usually, or we pass BGR if wrapper handles it)
            # mp.solutions.face_mesh.process expects RGB
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            
            # --- Hand Tracking ---
            # HandTracker expects BGR
            self.hand_tracker.find_hands(frame_bgr, draw=False) # Don't draw internally, we draw in Pygame
            
            # --- Face Tracking ---
            face_results = self.face_mesh.process(frame_rgb)
            
            
            # 3. Update Logic
            
            # Hands
            lm_list_hands = []
            # HandTracker supports getting landmarks. 
            # Need to iterate potentially multiple hands.
            # Using private or helper method from HandTracker if available?
            # HandTracker.get_landmark_positions(frame, hand_index)
            
            # Check how many hands detected
            if self.hand_tracker.results and self.hand_tracker.results.multi_hand_landmarks:
                for i in range(len(self.hand_tracker.results.multi_hand_landmarks)):
                    lm = self.hand_tracker.get_landmark_positions(frame_bgr, i)
                    if lm:
                        # Draw/Emit from fingertips: IDs 4, 8, 12, 16, 20
                        tips = [4, 8, 12, 16, 20]
                        
                        # Calculate hand openness (distance between palm and fingertips)
                        palm_cx = int((lm[0][1] + lm[5][1] + lm[17][1]) / 3)  # Average center
                        palm_cy = int((lm[0][2] + lm[5][2] + lm[17][2]) / 3)
                        
                        max_finger_dist = 0
                        for tip_id in tips:
                            if tip_id < len(lm):
                                _, cx, cy = lm[tip_id]
                                dist = math.sqrt((cx - palm_cx)**2 + (cy - palm_cy)**2)
                                max_finger_dist = max(max_finger_dist, dist)
                        
                        # Normalize hand openness (0-1)
                        hand_openness = min(1.0, max_finger_dist / 120.0)
                        
                        # Emit ripple when hand opens beyond threshold
                        if hand_openness > self.hand_open_threshold:
                            color_idx = (i * 3) % len(RIPPLE_COLORS_PALETTE)
                            max_r = int(150 + hand_openness * 150)
                            self.effect_system.emit_ripple(
                                palm_cx, palm_cy, 
                                max_radius=max_r, 
                                lifetime=35, 
                                strength=hand_openness,
                                color_idx=color_idx
                            )
                            
                            # Spawn ink or petals periodically
                            current_time = time.time()
                            if current_time - self.last_shape_spawn_time > self.shape_spawn_cooldown:
                                effect_type = random.choice(["ink", "petal"])
                                spawn_x = palm_cx + random.randint(-50, 50)
                                spawn_y = palm_cy + random.randint(-50, 50)
                                size = random.randint(20, 40)
                                self.effect_system.emit_ink_petal(
                                    spawn_x, spawn_y,
                                    obj_type=effect_type,
                                    size=size,
                                    lifetime=random.randint(120, 240),
                                    color_idx=random.randint(0, len(SHIBUI_PALETTE) - 1)
                                )
                                self.last_shape_spawn_time = current_time
                        
                        # Emit threads when hand is VERY open
                        if hand_openness > self.laser_threshold:
                            # Increase thread intensity
                            self.thread_intensity = min(1.0, self.thread_intensity + 0.05)
                            
                            # Shoot golden threads from each fingertip
                            thread_color = SHIBUI_PALETTE[0] # Golden
                            for idx, tip_id in enumerate(tips):
                                if tip_id < len(lm):
                                    _, fx, fy = lm[tip_id]
                                    if random.random() < 0.2:
                                        target_x = fx + random.randint(-200, 200)
                                        target_y = fy + random.randint(-200, 200)
                                        self.effect_system.emit_thread(
                                            fx, fy, target_x, target_y,
                                            color=thread_color,
                                            lifetime=random.randint(40, 80)
                                        )
                        
                        for idx, tip_id in enumerate(tips):
                            if tip_id < len(lm):
                                _, cx, cy = lm[tip_id]
                                # Emit particles from fingertips
                                col = self.finger_colors[idx]
                                brightness = 0.3 + hand_openness * 0.7  # Brighten with openness
                                bright_col = tuple(int(c * brightness) for c in col)
                                self.effect_system.emit(cx, cy, count=1, color=bright_col, speed=1.5, size=4, life=20, p_type="spark")

            # Face (Mouth Open)
            if face_results.multi_face_landmarks:
                for face_landmarks in face_results.multi_face_landmarks:
                    try:
                        # Using existing logic from spiral_mouth_effect for openness
                        # But rewriting simple version here to avoid complex dependency
                        # Landmarks 13 (upper) and 14 (lower)
                        upper = face_landmarks.landmark[13]
                        lower = face_landmarks.landmark[14]
                        
                        # Convert to pixels
                        ih, iw, _ = frame_bgr.shape
                        u_y = int(upper.y * ih)
                        l_y = int(lower.y * ih)
                        
                        # Face height reference
                        top = face_landmarks.landmark[10].y * ih
                        bottom = face_landmarks.landmark[152].y * ih
                        face_h = bottom - top
                        
                        mouth_h = l_y - u_y
                        mouth_ratio = mouth_h / face_h if face_h > 0 else 0
                        
                        mouth_cx = int((upper.x + lower.x) / 2 * iw)
                        mouth_cy = int((upper.y + lower.y) / 2 * ih)

                        # Map face to kaleidoscope
                        # 1. Use nose/mouth position as center
                        self.kaleidoscope_center = (mouth_cx, mouth_cy)
                        # Save face center/radius for masking kaleidoscope overlay
                        self.face_center = (mouth_cx, mouth_cy)
                        # Estimate face radius from face height
                        try:
                            self.face_radius = int(face_h * 0.6)
                        except Exception:
                            self.face_radius = max(WINDOW_WIDTH, WINDOW_HEIGHT) // 6
                        
                        # 2. Use face tilt for rotation
                        # Landmarks 33 (left eye outer) and 263 (right eye outer)
                        left_eye = face_landmarks.landmark[33]
                        right_eye = face_landmarks.landmark[263]
                        dx = right_eye.x - left_eye.x
                        dy = right_eye.y - left_eye.y
                        face_angle = math.degrees(math.atan2(dy, dx))
                        self.target_rotation = face_angle * 2.0 # Amplify tilt

                        # 3. Use mouth ratio for zoom/segments
                        if mouth_ratio > self.mouth_open_threshold:
                            # Zoom in when mouth opens
                            self.target_zoom = 1.0 + mouth_ratio * 2.0
                            
                            # Emit ripple for mouth opening
                            ripple_radius = int(100 + mouth_ratio * 200)
                            ripple_strength = min(1.0, mouth_ratio / 0.3)
                            self.effect_system.emit_ripple(
                                mouth_cx, mouth_cy,
                                max_radius=ripple_radius,
                                lifetime=45,
                                strength=ripple_strength,
                                color_idx=2
                            )
                            
                            # Emit "Breath" effects
                            breath_col = (180, 185, 200) # Airy silver
                            self.effect_system.emit(mouth_cx, mouth_cy, count=1, color=breath_col, speed=1.0, size=5, life=90, p_type="floaty")
                            
                    except Exception:
                        pass

            self.effect_system.update()
            
            # Decay intensity
            self.thread_intensity *= 0.98
            
            # Smoothly interpolate kaleidoscope params
            self.current_segments += (self.target_segments - self.current_segments) * 0.1
            self.current_rotation += (self.target_rotation - self.current_rotation) * 0.1
            self.current_zoom += (self.target_zoom - self.current_zoom) * 0.1
            
            # Reset target zoom/segments if no hands/face detection (optional, for "calm" state)
            self.target_zoom = max(1.0, self.target_zoom * 0.99)
            
            # --- Complex Dynamic Mapping ---
            # 1. Faster color rotation (Psychedelic)
            hue_shift = (time.time() * 60) % 180 
            
            # 2. Internal spin (Dynamic movement inside segments)
            internal_spin = time.time() * 45
            
            # 3. Dynamic segments linked to mouth (6 to 24 segments)
            segments = 8 + int(mouth_ratio * 16)
            overlay_segments = 12 + int(mouth_ratio * 12)
            
            # 4. Zoom and rotation
            
            # Smart Projection Mode Switching
            projection_mode = 'flat'
            if mouth_ratio > 0.6:
                projection_mode = 'tunnel'
                self.target_zoom = 2.0  # Deep zoom for tunnel
            elif mouth_ratio > 0.35:
                # Sphere mode for medium mouth open
                projection_mode = 'sphere'
                
            # Color boost based on overall activity
            # Use ripple count (hand activity) and mouth ratio
            color_boost = 1.0 + (ripple_count * 0.1) + (mouth_ratio * 0.8)

            self.kaleidoscope.set_params(
                segments=segments,
                rotation=self.current_rotation,
                zoom=self.current_zoom,
                center=self.kaleidoscope_center,
                hue_shift=hue_shift,
                internal_spin=internal_spin,
                overlay_segments=overlay_segments,
                overlay_rotation=-self.current_rotation * 1.5,
                projection_mode=projection_mode,
                color_boost=color_boost
            )

            # 4. Rendering
            # Draw camera feed as the main/base layer (priority)
            if frame_bgr is not None:
                frame_rgb_base = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                base_surf = pygame.image.frombuffer(frame_rgb_base.tobytes(), (WINDOW_WIDTH, WINDOW_HEIGHT), 'RGB')
                self.screen.blit(base_surf, (0, 0))

            # Generate animated background tint and blend subtly over camera
            ripple_count = len(self.effect_system.ripples)
            bg_surface = self.background_gen.generate(ripple_count)
            try:
                bg_surface.set_alpha(70)  # subtle tint
            except Exception:
                pass
            self.screen.blit(bg_surface, (0, 0))

            # Optional kaleidoscope overlay as light visual seasoning
            if frame_bgr is not None:
                try:
                    # Composite kaleidoscope frame with stronger flashy effects
                    kaleido_frame = self.kaleidoscope.process(frame_bgr)
                    kaleido_frame = self.kaleidoscope.apply_flashy_effects(kaleido_frame, intensity=0.5 * self.thread_intensity + 0.4)
                    frame_rgb_k = cv2.cvtColor(kaleido_frame, cv2.COLOR_BGR2RGB)
                    ksurf = pygame.image.frombuffer(frame_rgb_k.tobytes(), (WINDOW_WIDTH, WINDOW_HEIGHT), 'RGB')

                    # Transparency handling: Solid but glowy
                    overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
                    overlay.blit(ksurf, (0, 0))

                    # Blend with animated color tint to boost neon feel
                    r = int(127 + 127 * math.sin(time.time() * 2.1))
                    g = int(127 + 127 * math.sin(time.time() * 2.3 + 2))
                    b = int(127 + 127 * math.sin(time.time() * 2.5 + 4))
                    tint_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
                    tint_surf.fill((r, g, b, 150))
                    overlay.blit(tint_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

                    # If we have face center/radius, mask overlay so kaleidoscope appears outside face boundary
                    if hasattr(self, 'face_center') and hasattr(self, 'face_radius') and self.face_center is not None:
                        mask = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
                        # default opaque
                        mask.fill((255, 255, 255, 255))
                        # punch transparent hole at face center - slightly smaller to allow effect closer to face
                        try:
                            pygame.draw.circle(mask, (0, 0, 0, 0), self.face_center, max(10, int(self.face_radius * 0.7)))
                        except Exception:
                            pass
                        # Multiply overlay by mask (transparent inside face)
                        overlay.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

                    # High alpha to make effect flashy and dominating (low transparency)
                    overlay.set_alpha(210) 
                    self.screen.blit(overlay, (0, 0))
                except Exception:
                    pass

            # Draw Effects on top
            self.effect_system.draw(self.screen)
            
            # Glitch effect removed for refined aesthetic
            
            # Debug info
            fps = int(self.clock.get_fps())
            # Simple font rendering
            try:
                font = pygame.font.SysFont("Arial", 20)
                fps_text = font.render(f"FPS: {fps}", True, (0, 255, 0))
                self.screen.blit(fps_text, (10, 10))
            except:
                pass

            pygame.display.flip()
            self.clock.tick(FPS)

        # Cleanup
        self.cap.release()
        cv2.destroyAllWindows()
        pygame.quit()

if __name__ == "__main__":
    app = InteractiveArtApp()
    app.run()
