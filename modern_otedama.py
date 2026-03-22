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
import pygame
import display_utils
import cv2
import mediapipe as mp
import numpy as np
import random
from collections import deque
import math
import sys
import colorsys

# -----------------------------------------------------------------------------
# Constants & Configuration
# -----------------------------------------------------------------------------
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60

# Colors will be dynamic, but we define some base constants
COLOR_BG_DARK = (5, 5, 10)

# Physics Constants
GRAVITY = 0.6
AIR_RESISTANCE = 0.995
BOUNCE_FACTOR = 0.85
HAND_BOUNCE_FACTOR = 1.3
MAX_SPEED = 35.0

# Game States
STATE_TITLE = 0
STATE_PLAYING = 1
STATE_GAMEOVER = 2

# Hidden Command (Konami Code)
KONAMI_CODE = [
    pygame.K_UP, pygame.K_UP,
    pygame.K_DOWN, pygame.K_DOWN,
    pygame.K_LEFT, pygame.K_RIGHT,
    pygame.K_LEFT, pygame.K_RIGHT,
    pygame.K_b, pygame.K_a
]

# -----------------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------------
def hsv_to_rgb(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))

# -----------------------------------------------------------------------------
# Classes
# -----------------------------------------------------------------------------
class Particle:
    def __init__(self, x, y, color, speed_scale=1.0, life_scale=1.0):
        self.x = x
        self.y = y
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(2, 6) * speed_scale
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.lifetime = 255 * life_scale
        self.color = color
        self.size = random.randint(3, 8)
        self.decay = random.uniform(5, 10)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.lifetime -= self.decay
        self.size = max(0, self.size - 0.1)
        self.vy += 0.1 # slight gravity

    def draw(self, surface):
        if self.lifetime > 0 and self.size > 0:
            alpha = int(max(0, min(255, self.lifetime)))
            intensity = alpha / 255.0
            r = int(self.color[0] * intensity)
            g = int(self.color[1] * intensity)
            b = int(self.color[2] * intensity)
            pygame.draw.circle(surface, (r, g, b), (int(self.x), int(self.y)), int(self.size))

class StartButton:
    def __init__(self):
        self.radius = 60
        self.x = WINDOW_WIDTH - 80
        self.y = 80
        self.active = False
        self.pulse = 0

    def check_collision(self, hands):
        for hand in hands:
            hx, hy = hand['pos']
            dist = math.hypot(self.x - hx, self.y - hy)
            if dist < self.radius + hand['radius']:
                return True
        return False

    def draw(self, surface, hue):
        self.pulse += 0.1
        scale = 1.0 + math.sin(self.pulse) * 0.1
        
        color = hsv_to_rgb((hue + 0.5) % 1.0, 1.0, 1.0)
        draw_r = int(self.radius * scale)
        
        # Glow
        for i in range(10):
            alpha_c = hsv_to_rgb((hue + 0.5) % 1.0, 1.0, 0.2) # darker for glow
            pygame.draw.circle(surface, alpha_c, (self.x, self.y), draw_r + i*2, 1)
            
        pygame.draw.circle(surface, color, (self.x, self.y), draw_r, 3)
        
        # Text "START"
        font = pygame.font.SysFont("Courier New", 20, bold=True)
        text = font.render("HIT", True, (255, 255, 255))
        rect = text.get_rect(center=(self.x, self.y - 10))
        surface.blit(text, rect)
        text2 = font.render("ME", True, (255, 255, 255))
        rect2 = text2.get_rect(center=(self.x, self.y + 10))
        surface.blit(text2, rect2)

class Otedama:
    def __init__(self, x, y, fever_mode=False):
        self.x = x
        self.y = y
        self.vx = random.uniform(-4, 4)
        self.vy = random.uniform(-8, -4)
        self.radius = 25 if not fever_mode else 40
        self.trail = deque(maxlen=20 if fever_mode else 15)
        self.is_dead = False
        self.fever = fever_mode
        self.base_hue = random.random()

    def update(self, dt_scale=1.0):
        # Physics
        g = GRAVITY * 0.5 if self.fever else GRAVITY
        
        self.vy += g * dt_scale
        self.vx *= AIR_RESISTANCE
        self.vy *= AIR_RESISTANCE
        
        self.x += self.vx * dt_scale
        self.y += self.vy * dt_scale
        
        # Walls
        if self.x - self.radius < 0:
            self.x = self.radius
            self.vx *= -BOUNCE_FACTOR
        elif self.x + self.radius > WINDOW_WIDTH:
            self.x = WINDOW_WIDTH - self.radius
            self.vx *= -BOUNCE_FACTOR
            
        # Floor (Death)
        if self.y - self.radius > WINDOW_HEIGHT:
            self.is_dead = True

        # Update trail
        self.trail.append((self.x, self.y, self.radius * (random.uniform(0.8, 1.2))))
        self.base_hue = (self.base_hue + 0.005) % 1.0

    def draw(self, Surface, global_hue):
        current_hue = (self.base_hue + global_hue) % 1.0
        color = hsv_to_rgb(current_hue, 1.0, 1.0)
        
        # Trail
        for i, (tx, ty, tr) in enumerate(self.trail):
            progress = i / len(self.trail)
            size = tr * progress * 0.8
            trail_hue = (current_hue - (1-progress)*0.2) % 1.0
            t_col = hsv_to_rgb(trail_hue, 1.0, 1.0)
            pygame.draw.circle(Surface, t_col, (int(tx), int(ty)), int(size))
            
        # Core
        pygame.draw.circle(Surface, (255, 255, 255), (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(Surface, color, (int(self.x), int(self.y)), self.radius - 3)

# -----------------------------------------------------------------------------
# Main Game Class
# -----------------------------------------------------------------------------
class ModernOtedamaGame:
    def __init__(self):
        pygame.init()
        self.screen, _pg_size = display_utils.setup_pygame_fullscreen()
        pygame.display.set_caption("OTEDAMA PSYCHEDELIC 2026")
        self.clock = pygame.time.Clock()
        
        # Fonts (Unified style)
        self.font_main = pygame.font.SysFont("Courier New", 60, bold=True)
        self.font_sub = pygame.font.SysFont("Courier New", 30, bold=True)

        # MediaPipe
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(model_complexity=1, 
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )
        
        # Camera
        self.cap = display_utils.open_camera()
        if not self.cap.isOpened():
             print("Warning: Default camera not found, trying index 1")
             self.cap = display_utils.open_camera()

        # Game Data
        self.state = STATE_TITLE
        self.score = 0
        self.combo = 1
        self.balls = []
        self.particles = []
        self.hand_colliders = []
        self.start_button = StartButton()
        
        # Psychedelic State
        self.global_hue = 0.0
        
        # Fever / Hidden Command
        self.input_history = []
        self.fever_mode = False
        self.fever_timer = 0
        
    def reset_game(self):
        self.score = 0
        self.combo = 1
        self.balls = []
        self.particles = []
        self.balls.append(Otedama(WINDOW_WIDTH // 2, 0))
        self.state = STATE_PLAYING
        self.fever_mode = False

    def toggle_fever(self):
        self.fever_mode = True
        self.fever_timer = 900 
        for _ in range(50):
            c = hsv_to_rgb(random.random(), 1, 1)
            self.particles.append(Particle(WINDOW_WIDTH/2, WINDOW_HEIGHT/2, c, 3.0, 2.0))
        self.balls = [Otedama(b.x, b.y, True) for b in self.balls] 
        self.balls.append(Otedama(WINDOW_WIDTH * 0.3, 0, True))
        self.balls.append(Otedama(WINDOW_WIDTH * 0.7, 0, True))

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                
                # Hidden Command
                self.input_history.append(event.key)
                if len(self.input_history) > len(KONAMI_CODE):
                    self.input_history.pop(0)
                
                if self.input_history == KONAMI_CODE:
                    self.toggle_fever()
                    self.input_history.clear()

                if self.state == STATE_GAMEOVER:
                     if event.key == pygame.K_SPACE:
                        self.reset_game()
                        
        return True

    def process_hands(self, frame):
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_rgb.flags.writeable = False 
        results = self.hands.process(frame_rgb)
        
        self.hand_colliders.clear()

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                wrist = hand_landmarks.landmark[0]
                middle = hand_landmarks.landmark[9]
                
                cx = int((wrist.x + middle.x) / 2 * WINDOW_WIDTH)
                cy = int((wrist.y + middle.y) / 2 * WINDOW_HEIGHT)
                
                scale = math.hypot(wrist.x - middle.x, wrist.y - middle.y)
                radius = int(scale * WINDOW_WIDTH * 0.6) 
                radius = max(40, min(120, radius))
                
                self.hand_colliders.append({'pos': (cx, cy), 'radius': radius, 'landmarks': hand_landmarks})

    def update(self):
        self.global_hue = (self.global_hue + 0.002) % 1.0
        
        # Camera
        success, img = self.cap.read()
        if success:
            img = cv2.flip(img, 1) 
            self.process_hands(img)
            img = cv2.resize(img, (WINDOW_WIDTH, WINDOW_HEIGHT))
            # Psychedelic Background Effect
            # Tint the camera feed heavily with the global hue inverted
            tint_color = hsv_to_rgb((self.global_hue + 0.5) % 1.0, 1.0, 1.0)
            
            # Simple tinting using numpy
            # Convert to float for math
            img_float = img.astype(float)
            # Add color tint
            img_float[:, :, 0] *= (tint_color[2] / 255.0) # B
            img_float[:, :, 1] *= (tint_color[1] / 255.0) # G
            img_float[:, :, 2] *= (tint_color[0] / 255.0) # R
            
            # Boost brightness/contrast
            img_float = img_float * 1.5
            np.clip(img_float, 0, 255, out=img_float)
            
            img_final = img_float.astype(np.uint8)
            img_rgb = cv2.cvtColor(img_final, cv2.COLOR_BGR2RGB)
            
            # Use tobytes instead of tostring to fix deprecation
            self.bg_surf = pygame.image.frombuffer(img_rgb.tobytes(), img_rgb.shape[1::-1], "RGB")
            self.bg_surf.set_alpha(150) # Semi-transparent
        else:
            self.bg_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
            self.bg_surf.fill(COLOR_BG_DARK)

        # Start Button Logic
        if self.state in [STATE_TITLE, STATE_GAMEOVER]:
            if self.start_button.check_collision(self.hand_colliders):
                self.reset_game()

        # Game State Logic
        if self.state == STATE_PLAYING:
            if len(self.balls) < 1 + int(self.score / 500) and not self.fever_mode:
                if random.randint(0, 300) == 0:
                    self.balls.append(Otedama(random.randint(200, WINDOW_WIDTH-200), 0))

            if self.fever_mode:
                self.fever_timer -= 1
                if self.fever_timer <= 0:
                    self.fever_mode = False
                    self.balls = [Otedama(b.x, b.y, False) for b in self.balls]

            active_balls = []
            for ball in self.balls:
                ball.update()
                hit = self.check_hand_collision(ball)
                if hit:
                    self.combo += 1
                    points = 100 * self.combo * (2 if self.fever_mode else 1)
                    self.score += points
                
                if not ball.is_dead:
                    active_balls.append(ball)
                else:
                    self.combo = 1 
            self.balls = active_balls
            
            if len(self.balls) == 0 and not self.fever_mode:
                 self.state = STATE_GAMEOVER

        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.lifetime > 0]
        
    def check_hand_collision(self, ball):
        hit_occurred = False
        for hand in self.hand_colliders:
            hx, hy = hand['pos']
            hr = hand['radius']
            
            dx = ball.x - hx
            dy = ball.y - hy
            dist = math.hypot(dx, dy)
            
            if dist < ball.radius + hr:
                overlap = (ball.radius + hr) - dist
                if dist == 0: dist = 0.001
                nx, ny = dx / dist, dy / dist
                
                ball.x += nx * overlap
                ball.y += ny * overlap
                
                v_dot_n = ball.vx * nx + ball.vy * ny
                ball.vx -= 2 * v_dot_n * nx
                ball.vy -= 2 * v_dot_n * ny
                
                ball.vy -= 12 if not self.fever_mode else 18
                ball.vx += random.uniform(-5, 5)
                
                speed = math.hypot(ball.vx, ball.vy)
                if speed > MAX_SPEED:
                    scale = MAX_SPEED / speed
                    ball.vx *= scale
                    ball.vy *= scale
                    
                c = hsv_to_rgb(self.global_hue, 1, 1)
                self.spawn_hit_particles(ball.x, ball.y, c)
                hit_occurred = True
                
        return hit_occurred

    def spawn_hit_particles(self, x, y, color):
        for _ in range(20):
            self.particles.append(Particle(x, y, color))
            
    def draw(self):
        # 1. Background
        if hasattr(self, 'bg_surf'):
            self.screen.blit(self.bg_surf, (0,0))
        else:
            self.screen.fill(COLOR_BG_DARK)
            
        # 2. Hands (model_complexity=1, Psychedelic Wireframe)
        for hand in self.hand_colliders:
            hx, hy = hand['pos']
            hr = hand['radius']
            
            hand_col = hsv_to_rgb(self.global_hue, 1, 1)
            pygame.draw.circle(self.screen, hand_col, (hx, hy), hr + 5, 3)
            
            lm = hand['landmarks'].landmark
            points = [(int(p.x * WINDOW_WIDTH), int(p.y * WINDOW_HEIGHT)) for p in lm]
            for connection in self.mp_hands.HAND_CONNECTIONS:
                start, end = connection
                pygame.draw.line(self.screen, (255, 255, 255), points[start], points[end], 2)

        # 3. Start Button (if applicable)
        if self.state in [STATE_TITLE, STATE_GAMEOVER]:
            self.start_button.draw(self.screen, self.global_hue)

        # 4. Particles
        for p in self.particles:
            p.draw(self.screen)

        # 5. Balls
        for ball in self.balls:
            ball.draw(self.screen, self.global_hue)
            
        # 6. UI
        self.draw_ui()

        pygame.display.flip()

    def draw_ui(self):
        # Unified Glitch Text Function
        def draw_glitch_text(text, x, y, font, color, center=True):
            offset_x = random.randint(-2, 2) if self.fever_mode else 0
            offset_y = random.randint(-2, 2)
            
            surf = font.render(text, True, color)
            if center:
                rect = surf.get_rect(center=(x + offset_x, y + offset_y))
            else:
                rect = surf.get_rect(topleft=(x + offset_x, y + offset_y))
            
            # Shadow/Glitch layer
            shadow_col = hsv_to_rgb((self.global_hue + 0.3)%1.0, 1, 1)
            shadow_surf = font.render(text, True, shadow_col)
            shadow_rect = rect.copy()
            shadow_rect.x += 4
            shadow_rect.y += 4
            self.screen.blit(shadow_surf, shadow_rect)
            
            self.screen.blit(surf, rect)

        if self.state == STATE_TITLE:
            draw_glitch_text("PSYCHEDELIC OTEDAMA", WINDOW_WIDTH//2, WINDOW_HEIGHT//3, self.font_main, (255, 255, 255))
            draw_glitch_text("HIT THE BUTTON ->", WINDOW_WIDTH//2, WINDOW_HEIGHT//2, self.font_sub, (200, 200, 200))
            
            # Hints
            if int(self.global_hue * 50) % 2 == 0:
                 hint_col = hsv_to_rgb(self.global_hue, 0.5, 1)
                 draw_glitch_text("SECRET CODE: \u2191 \u2191 \u2193 \u2193 \u2190 \u2192 \u2190 \u2192 B A", WINDOW_WIDTH//2, WINDOW_HEIGHT - 50, self.font_sub, hint_col)

        elif self.state == STATE_PLAYING:
            draw_glitch_text(f"SCORE: {self.score}", 50, 30, self.font_sub, (255, 255, 255), center=False)
            
            combo_col = hsv_to_rgb(self.global_hue * 2 % 1.0, 1, 1)
            draw_glitch_text(f"COMBO x{self.combo}", 50, 70, self.font_sub, combo_col, center=False)
            
            if self.fever_mode:
                draw_glitch_text("FEVER TIME!!!", WINDOW_WIDTH//2, 100, self.font_main, hsv_to_rgb(random.random(), 1, 1))

        elif self.state == STATE_GAMEOVER:
            draw_glitch_text("GAME OVER", WINDOW_WIDTH//2, WINDOW_HEIGHT//3, self.font_main, (255, 50, 50))
            draw_glitch_text(f"SCORE: {self.score}", WINDOW_WIDTH//2, WINDOW_HEIGHT//2, self.font_sub, (255, 255, 255))
            draw_glitch_text("HIT BUTTON TO RESTART", WINDOW_WIDTH//2, WINDOW_HEIGHT*2//3, self.font_sub, (200, 200, 200))

    def run(self):
        while True:
            keep_running = self.handle_input()
            if not keep_running:
                break
            self.update()
            self.draw()
            self.clock.tick(FPS)
        
        self.cleanup()

    def cleanup(self):
        self.hands.close()
        self.cap.release()
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = ModernOtedamaGame()
    game.run()
