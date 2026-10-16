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
import random
from collections import deque
import math
import sys
import colorsys
import time
from scene_control import notify_exit_request, notify_first_frame
from hand_focus_overlay import draw_pygame as draw_hand_overlay

# -----------------------------------------------------------------------------
# Constants & Configuration
# -----------------------------------------------------------------------------
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60
MAX_HANDS = 6  # Three participants can each use both hands.

# Colors will be dynamic, but we define some base constants
COLOR_BG_DARK = (5, 5, 10)

# Physics Constants
GRAVITY = 0.6
AIR_RESISTANCE = 0.995
BOUNCE_FACTOR = 0.85
HAND_BOUNCE_FACTOR = 1.3
MAX_SPEED = 35.0
SPEED_RAMP_SECONDS = 90.0
MAX_SPEED_MULTIPLIER = 1.5
MAX_ACTIVE_FRAME_SECONDS = 0.1
PAUSED_FRAME_SECONDS = 0.5

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


def gameplay_speed_multiplier(play_seconds):
    progress = min(1.0, max(0.0, play_seconds) / SPEED_RAMP_SECONDS)
    return 1.0 + (MAX_SPEED_MULTIPLIER - 1.0) * progress

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
        damping = AIR_RESISTANCE ** dt_scale
        self.vx *= damping
        self.vy *= damping
        
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
        self.base_hue = (self.base_hue + 0.005 * dt_scale) % 1.0

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
        self.window_screen, self.screen, self.display_layout = display_utils.setup_pygame_scaled_fullscreen(
            WINDOW_WIDTH,
            WINDOW_HEIGHT,
        )
        pygame.display.set_caption("OTEDAMA PSYCHEDELIC 2026")
        self.clock = pygame.time.Clock()
        
        # Fonts (Unified style)
        self.font_main = pygame.font.SysFont("Courier New", 60, bold=True)
        self.font_sub = pygame.font.SysFont("Courier New", 30, bold=True)

        # MediaPipe
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(model_complexity=1, 
            max_num_hands=MAX_HANDS,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )
        
        # Camera
        self.cap = display_utils.open_camera()
        if self.cap is None or not self.cap.isOpened():
            self.hands.close()
            pygame.quit()
            raise RuntimeError("The shared camera could not be attached")
        self.camera_failure_since = None
        self.camera_last_frame_id = None
        self.camera_last_fresh_at = None
        self.frame_processed = False

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
        self.play_elapsed_seconds = 0.0
        self._start_frame_pending = False
        
    def reset_game(self):
        self.score = 0
        self.combo = 1
        self.balls = []
        self.particles = []
        self.balls.append(Otedama(WINDOW_WIDTH // 2, 0))
        self.state = STATE_PLAYING
        self.fever_mode = False
        self.play_elapsed_seconds = 0.0
        self._start_frame_pending = True

    def advance_play_time(self, frame_seconds):
        if self.state != STATE_PLAYING:
            return 0.0
        if self._start_frame_pending:
            self._start_frame_pending = False
            return 0.0
        # Keep the wall clock independent of the physics budget, including 5 FPS.
        # Long stopped/debugger intervals do not count as active gameplay.
        if not math.isfinite(frame_seconds) or frame_seconds > PAUSED_FRAME_SECONDS:
            return 0.0
        active_seconds = max(0.0, frame_seconds)
        self.play_elapsed_seconds += active_seconds
        return min(MAX_ACTIVE_FRAME_SECONDS, active_seconds)

    def advance_ball(self, ball, active_seconds, speed_multiplier):
        # Time-scale the existing gravity and movement without compounding velocity.
        # Substeps keep a faster ball from skipping a hand between display frames.
        if active_seconds <= 0:
            return False
        frame_scale = active_seconds * FPS * speed_multiplier
        steps = max(1, math.ceil(frame_scale))
        step_scale = frame_scale / steps
        hit = False
        for _ in range(steps):
            ball.update(dt_scale=step_scale)
            hit = self.check_hand_collision(ball) or hit
            if ball.is_dead:
                break
        return hit

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
                notify_exit_request("pygame_quit")
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    notify_exit_request("key_escape")
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
        
        # Rebuild from this frame only. Each detected hand is independent: Left/
        # Right labels repeat across participants and detection order can change.
        # No per-index hand velocity/history is used to drive the ball response.
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

    def update(self, frame_seconds=1.0 / FPS):
        self.global_hue = (self.global_hue + 0.002) % 1.0
        
        # Camera
        success, img = self.cap.read()
        self.frame_processed = bool(success and img is not None)
        frame_id = getattr(self.cap, "last_read_frame_id", None)
        if self.frame_processed and type(frame_id) is int:
            now = time.monotonic()
            if frame_id != self.camera_last_frame_id:
                self.camera_last_frame_id = frame_id
                self.camera_last_fresh_at = now
            elif self.camera_last_fresh_at is not None and now - self.camera_last_fresh_at >= 0.25:
                # Shared memory can return its last frame during a camera stall.
                self.frame_processed = False
        if self.frame_processed:
            if self.camera_failure_since is not None:
                self._start_frame_pending = True
            self.camera_failure_since = None
            img = cv2.flip(img, 1) 
            self.process_hands(img)
        else:
            self.hand_colliders.clear()
            if self.camera_failure_since is None:
                self.camera_failure_since = time.monotonic()
            elif time.monotonic() - self.camera_failure_since >= 1.0:
                notify_exit_request("camera_read_failed_timeout")
                raise RuntimeError("Shared camera did not provide a frame for one second")
            return

        # Start Button Logic
        if self.state in [STATE_TITLE, STATE_GAMEOVER]:
            if self.start_button.check_collision(self.hand_colliders):
                self.reset_game()

        # Game State Logic
        if self.state == STATE_PLAYING:
            active_seconds = self.advance_play_time(frame_seconds)
            speed_multiplier = gameplay_speed_multiplier(self.play_elapsed_seconds)
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
                hit = self.advance_ball(ball, active_seconds, speed_multiplier)
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
        # Camera frames drive hand detection only; keep the stage background dark.
        self.screen.fill(COLOR_BG_DARK)
            
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

        # The entire palm collider is the input; keep its exact center/radius visible.
        draw_hand_overlay(
            self.screen, [hand['landmarks'] for hand in self.hand_colliders],
            palm_focus=True,
            palm_circles=[(*hand['pos'], hand['radius']) for hand in self.hand_colliders])

        display_utils.present_pygame_scaled(self.window_screen, self.screen, self.display_layout)
        notify_first_frame(self.cap, frame_processed=self.frame_processed)

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
        previous_frame_at = time.monotonic()
        try:
            while self.handle_input():
                frame_at = time.monotonic()
                frame_seconds = frame_at - previous_frame_at
                previous_frame_at = frame_at
                self.update(frame_seconds)
                self.draw()
                self.clock.tick(FPS)
        finally:
            self.cleanup()

    def cleanup(self):
        try:
            self.hands.close()
        finally:
            try:
                self.cap.release()
            finally:
                pygame.quit()

if __name__ == "__main__":
    game = ModernOtedamaGame()
    game.run()
