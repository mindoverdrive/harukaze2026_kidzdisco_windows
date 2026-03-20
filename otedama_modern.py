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
import numpy as np
import random
from collections import deque
import math
import sys
import colorsys

# Import HandTracker module
try:
    from hand_tracker import HandTracker
except ImportError:
    print("hand_tracker.py not found. Please ensure it is in the same directory.")
    sys.exit(1)

# -----------------------------------------------------------------------------
# Constants & Configuration
# -----------------------------------------------------------------------------
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60
COLOR_BG_DARK = (5, 5, 8)

# Physics
GRAVITY = 0.6
AIR_RESISTANCE = 0.995
BOUNCE_FACTOR = 0.85
MAX_SPEED = 40.0

# States
STATE_TITLE = 0
STATE_PLAYING = 1
STATE_GAMEOVER = 2

# Konami Code
KONAMI_CODE = [
    pygame.K_UP, pygame.K_UP,
    pygame.K_DOWN, pygame.K_DOWN,
    pygame.K_LEFT, pygame.K_RIGHT,
    pygame.K_LEFT, pygame.K_RIGHT,
    pygame.K_b, pygame.K_a
]

# -----------------------------------------------------------------------------
# Utils
# -----------------------------------------------------------------------------
def hsv_to_rgb(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))

# -----------------------------------------------------------------------------
# VFX Classes
# -----------------------------------------------------------------------------
class ScreenShake:
    def __init__(self):
        self.trauma = 0
        self.max_offset = 30
        self.decay = 0.9

    def add_trauma(self, amount):
        self.trauma = min(1.0, self.trauma + amount)

    def update(self):
        self.trauma *= self.decay
        if self.trauma < 0.01:
            self.trauma = 0

    def get_offset(self):
        if self.trauma == 0: return (0, 0)
        shake = self.trauma ** 2 
        dx = (random.random() * 2 - 1) * self.max_offset * shake
        dy = (random.random() * 2 - 1) * self.max_offset * shake
        return (int(dx), int(dy))

class Particle:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        self.lifetime = 255
        self.alive = True

    def update(self):
        pass
    
    def draw(self, surface):
        pass

class DotParticle(Particle):
    def __init__(self, x, y, color, speed_scale=1.0):
        super().__init__(x, y, color)
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(2, 8) * speed_scale
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.size = random.randint(3, 8)
        self.decay = random.uniform(5, 12)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.lifetime -= self.decay
        self.size = max(0, self.size - 0.2)
        self.vy += 0.1 
        if self.lifetime <= 0: self.alive = False

    def draw(self, surface):
        if self.size > 0:
            c = (self.color[0], self.color[1], self.color[2])
            pygame.draw.circle(surface, c, (int(self.x), int(self.y)), int(self.size))

class SparkParticle(Particle):
    def __init__(self, x, y, color):
        super().__init__(x, y, color)
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(10, 20) 
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.length = random.randint(10, 30)
        self.decay = 15

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.9
        self.vy *= 0.9
        self.lifetime -= self.decay
        if self.lifetime <= 0: self.alive = False

    def draw(self, surface):
        end_x = self.x - self.vx * 2 
        end_y = self.y - self.vy * 2
        pygame.draw.line(surface, self.color, (self.x, self.y), (end_x, end_y), 2)

class ShockwaveParticle(Particle):
    def __init__(self, x, y, color):
        super().__init__(x, y, color)
        self.radius = 5
        self.growth = 8
        self.decay = 20
        self.width = 5

    def update(self):
        self.radius += self.growth
        self.lifetime -= self.decay
        self.width = max(1, self.width - 0.2)
        if self.lifetime <= 0: self.alive = False

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), int(self.radius), int(self.width))

class TextParticle(Particle):
    def __init__(self, x, y, text, font):
        super().__init__(x, y, (255, 255, 255))
        self.text = text
        self.font = font
        self.vy = -2
        self.lifetime = 255
        self.decay = 5

    def update(self):
        self.y += self.vy
        self.lifetime -= self.decay
        if self.lifetime <= 0: self.alive = False

    def draw(self, surface):
        alpha = max(0, min(255, self.lifetime))
        if alpha < 10: return
        
        text_surf = self.font.render(self.text, True, (255, 255, 255))
        text_surf.set_alpha(alpha)
        
        rect = text_surf.get_rect(center=(int(self.x), int(self.y)))
        
        # Glow/Shadow
        shadow_surf = self.font.render(self.text, True, (255, 0, 255))
        shadow_surf.set_alpha(alpha)
        surface.blit(shadow_surf, (rect.x+2, rect.y+2))
        
        surface.blit(text_surf, rect)

class FlashParticle(Particle):
    def __init__(self, x, y):
        super().__init__(x, y, (255, 255, 255))
        self.radius = 10
        self.max_radius = 80
        self.lifetime = 10
        self.decay = 1

    def update(self):
        self.radius += (self.max_radius - self.radius) * 0.3
        self.lifetime -= self.decay
        if self.lifetime <= 0: self.alive = False

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), int(self.radius))

class Otedama:
    def __init__(self, x, y, fever_mode=False):
        self.x = x
        self.y = y
        self.vx = random.uniform(-4, 4)
        self.vy = random.uniform(-8, -4)
        self.radius = 25 if not fever_mode else 35
        self.trail = deque(maxlen=25)
        self.is_dead = False
        self.fever = fever_mode
        self.base_hue = random.random()

    def update(self, dt_scale=1.0):
        g = GRAVITY * 0.4 if self.fever else GRAVITY
        self.vy += g * dt_scale
        self.vx *= AIR_RESISTANCE
        self.vy *= AIR_RESISTANCE
        self.x += self.vx * dt_scale
        self.y += self.vy * dt_scale
        
        if self.x - self.radius < 0:
            self.x = self.radius
            self.vx *= -BOUNCE_FACTOR
        elif self.x + self.radius > WINDOW_WIDTH:
            self.x = WINDOW_WIDTH - self.radius
            self.vx *= -BOUNCE_FACTOR
            
        if self.y - self.radius > WINDOW_HEIGHT:
            self.is_dead = True

        self.trail.append((self.x, self.y, self.radius))
        self.base_hue = (self.base_hue + 0.01) % 1.0

    def draw(self, surface, global_hue):
        current_hue = (self.base_hue + global_hue) % 1.0
        color = hsv_to_rgb(current_hue, 1.0, 1.0)
        
        for i, (tx, ty, tr) in enumerate(self.trail):
            progress = i / len(self.trail)
            size = tr * progress * 0.9
            t_hue = (current_hue - (1-progress)*0.3) % 1.0
            t_col = hsv_to_rgb(t_hue, 1.0, 1.0)
            pygame.draw.circle(surface, t_col, (int(tx), int(ty)), int(size))
            
        pygame.draw.circle(surface, (255, 255, 255), (int(self.x), int(self.y)), self.radius + 5, 2)
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surface, (255, 255, 255), (int(self.x), int(self.y)), int(self.radius * 0.6))

# -----------------------------------------------------------------------------
# Main Game Class
# -----------------------------------------------------------------------------
class ModernOtedamaGame:
    def __init__(self):
        pygame.init()
        self.raw_screen, _pg_size = display_utils.setup_pygame_fullscreen()
        self.game_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT)) 
        
        pygame.display.set_caption("OTEDAMA HYPER 2026")
        self.clock = pygame.time.Clock()
        
        self.font_main = pygame.font.SysFont("Courier New", 70, bold=True)
        self.font_sub = pygame.font.SysFont("Courier New", 30, bold=True)
        self.font_popup = pygame.font.SysFont("Arial Black", 40)

        # Use HandTracker Module
        self.tracker = HandTracker(max_num_hands=2, detection_conf=0.7, track_conf=0.5)
        self.cap = display_utils.open_camera() 

        self.state = STATE_TITLE
        self.score = 0
        self.combo = 1
        self.balls = []
        self.particles = []
        self.hands_data = []
        
        self.global_hue = 0.0
        self.fever_mode = False
        self.fever_timer = 0
        self.shake = ScreenShake()
        self.input_code = []

    def reset_game(self):
        self.score = 0
        self.combo = 1
        self.balls = [Otedama(WINDOW_WIDTH//2, 0)]
        self.particles = []
        self.state = STATE_PLAYING
        self.fever_mode = False
        self.shake.add_trauma(0.5)

    def process_hands(self, frame):
        self.hands_data = []
        # Use HandTracker to get results (needed for later drawing)
        self.tracker.find_hands(frame, draw=False)
        
        # We can iterate through potentially detected hands by index
        # Since we set max_num_hands=2, check index 0 and 1
        for i in range(2):
            lm_list = self.tracker.get_landmark_positions(frame, hand_index=i)
            if lm_list:
                # lm_list is [(id, x, y), ...]
                # ID 0 = Wrist, ID 9 = Middle Finger MCP
                wrist = lm_list[0]
                mid = lm_list[9]
                
                wx, wy = wrist[1], wrist[2]
                mx, my = mid[1], mid[2]
                
                cx = int((wx + mx) / 2)
                cy = int((wy + my) / 2)
                
                # Check distance for radius scaling
                scale = math.hypot(wx - mx, wy - my)
                radius = int(scale * 1.5) # approximate palm size
                radius = max(40, min(120, radius))
                
                self.hands_data.append({'pos':(cx, cy), 'r':radius, 'lm_list': lm_list})

    def toggle_fever(self):
        self.fever_mode = True
        self.fever_timer = 900
        self.shake.add_trauma(1.0)
        for _ in range(30):
            self.particles.append(SparkParticle(WINDOW_WIDTH/2, WINDOW_HEIGHT/2, (255,255,255)))
        
        self.balls = [Otedama(b.x, b.y, True) for b in self.balls]
        self.balls.append(Otedama(WINDOW_WIDTH*0.4, 0, True))
        self.balls.append(Otedama(WINDOW_WIDTH*0.6, 0, True))

    def update(self):
        self.global_hue = (self.global_hue + 0.005) % 1.0
        self.shake.update()
        
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            frame = cv2.resize(frame, (WINDOW_WIDTH, WINDOW_HEIGHT))
            
            # Use HandTracker results
            self.process_hands(frame)
            
            tint = hsv_to_rgb(self.global_hue, 1, 1) # Full saturation
            f_float = frame.astype(float)
            f_float[:, :, 0] *= (tint[2]/255 * 0.5 + 0.5)
            f_float[:, :, 1] *= (tint[1]/255 * 0.5 + 0.5)
            f_float[:, :, 2] *= (tint[0]/255 * 0.5 + 0.5)
            f_float = np.clip(f_float * 1.2, 0, 255).astype(np.uint8)
            
            rgb = cv2.cvtColor(f_float, cv2.COLOR_BGR2RGB)
            self.bg_img = pygame.image.frombuffer(rgb.tobytes(), rgb.shape[1::-1], "RGB")
        else:
            # Fallback if camera fails
            self.bg_img = None
        
        if self.state != STATE_PLAYING:
            bx, by, br = WINDOW_WIDTH-80, 80, 60
            for h in self.hands_data:
                dist = math.hypot(h['pos'][0]-bx, h['pos'][1]-by)
                if dist < h['r'] + br:
                    self.reset_game()

        if self.state == STATE_PLAYING:
            cap = 2 + int(self.score / 600)
            if self.fever_mode: cap += 3
            if len(self.balls) < cap and random.random() < 0.02:
                self.balls.append(Otedama(random.randint(100, WINDOW_WIDTH-100), 0, self.fever_mode))

            if self.fever_mode:
                self.fever_timer -= 1
                if self.fever_timer <= 0:
                    self.fever_mode = False 

            next_balls = []
            for b in self.balls:
                b.update()
                
                hit = False
                for h in self.hands_data:
                    hx, hy = h['pos']
                    hr = h['r']
                    dist = math.hypot(b.x - hx, b.y - hy)
                    if dist < b.radius + hr:
                        hit = True
                        overlap = (b.radius + hr) - dist
                        if dist < 0.1: dist = 0.1
                        nx, ny = (b.x - hx)/dist, (b.y - hy)/dist
                        
                        b.x += nx * overlap
                        b.y += ny * overlap
                        
                        v_dot = b.vx*nx + b.vy*ny
                        b.vx -= 2 * v_dot * nx
                        b.vy -= 2 * v_dot * ny
                        
                        b.vy -= 15 if not self.fever_mode else 25
                        b.vx += random.uniform(-5, 5)
                        
                        sp = math.hypot(b.vx, b.vy)
                        if sp > MAX_SPEED:
                            scale = MAX_SPEED/sp
                            b.vx *= scale
                            b.vy *= scale
                            
                        # EFFECTS
                        self.shake.add_trauma(0.2)
                        c = hsv_to_rgb(self.global_hue, 0.5, 1)
                        self.spawn_explosion(b.x, b.y, c)
                        self.score += 100 * self.combo
                        self.combo += 1
                
                if not b.is_dead:
                    next_balls.append(b)
                else:
                    self.combo = 1 
            
            self.balls = next_balls
            if len(self.balls) == 0 and not self.fever_mode:
                self.state = STATE_GAMEOVER
                self.shake.add_trauma(0.5)

        for p in self.particles: p.update()
        self.particles = [p for p in self.particles if p.alive]

    def spawn_explosion(self, x, y, color):
        # Text Popup
        msgs = ["HIT", "NICE", "GOOD", "COOL", "WOW", "YEAH"]
        txt = random.choice(msgs)
        self.particles.append(TextParticle(x, y - 50, txt, self.font_popup))
        
        # Flash
        self.particles.append(FlashParticle(x, y))
        
        # Shockwave
        self.particles.append(ShockwaveParticle(x, y, color))
        # Sparks
        for _ in range(10):
            self.particles.append(SparkParticle(x, y, color))
        # Dots
        for _ in range(15):
            self.particles.append(DotParticle(x, y, color, 1.5))

    def draw(self):
        if hasattr(self, 'bg_img') and self.bg_img:
            self.game_surface.blit(self.bg_img, (0,0))
        else:
            self.game_surface.fill(COLOR_BG_DARK)
            
        for h in self.hands_data:
            hx, hy = h['pos']
            col = hsv_to_rgb((self.global_hue+0.5)%1.0, 1, 1)
            pygame.draw.circle(self.game_surface, col, (hx, hy), h['r'], 4)
            
            # Use data from get_landmark_positions to draw lines
            lm_list = h['lm_list']
            # Map ID to (x,y)
            id_to_pos = {id_: (x, y) for id_, x, y in lm_list}
            
            # Manually draw connections since we have points
            connections = self.tracker.mp_hands.HAND_CONNECTIONS
            for p1_id, p2_id in connections:
                if p1_id in id_to_pos and p2_id in id_to_pos:
                    pos1 = id_to_pos[p1_id]
                    pos2 = id_to_pos[p2_id]
                    pygame.draw.line(self.game_surface, (255, 255, 255), pos1, pos2, 2)

        if self.state != STATE_PLAYING:
            bx, by = WINDOW_WIDTH-80, 80
            pulse = 1.0 + math.sin(pygame.time.get_ticks()*0.01)*0.2
            c = hsv_to_rgb(self.global_hue, 1, 1)
            pygame.draw.circle(self.game_surface, c, (bx, by), int(60*pulse), 5)
            self.draw_text_centered("HIT", bx, by-15, self.font_sub, (255,255,255), self.game_surface)
            self.draw_text_centered("ME", bx, by+15, self.font_sub, (255,255,255), self.game_surface)

        for p in self.particles:
            p.draw(self.game_surface)

        for b in self.balls:
            if self.fever_mode:
                orig_x = b.x
                color = hsv_to_rgb((b.base_hue+self.global_hue)%1.0, 1, 1)
                
                b.x = orig_x - 5
                pygame.draw.circle(self.game_surface, (255,0,0), (int(b.x), int(b.y)), b.radius, 2)
                b.x = orig_x + 5
                pygame.draw.circle(self.game_surface, (0,255,255), (int(b.x), int(b.y)), b.radius, 2)
                
                b.x = orig_x
                b.draw(self.game_surface, self.global_hue)
            else:
                b.draw(self.game_surface, self.global_hue)
                
        if self.state == STATE_TITLE:
            self.draw_text_centered("PSYCHEDELIC OTEDAMA", WINDOW_WIDTH//2, WINDOW_HEIGHT//3, self.font_main, hsv_to_rgb(self.global_hue, 0.5, 1), self.game_surface)
            self.draw_text_centered("USE HANDS TO PLAY", WINDOW_WIDTH//2, WINDOW_HEIGHT//2, self.font_sub, (200,200,200), self.game_surface)
        elif self.state == STATE_PLAYING:
            self.game_surface.blit(self.font_main.render(str(self.score), True, (255,255,255)), (30,30))
            if self.combo > 1:
                c = hsv_to_rgb(self.global_hue*2%1.0, 1, 1)
                self.game_surface.blit(self.font_main.render(f"x{self.combo}", True, c), (30, 100))
            if self.fever_mode:
                self.draw_text_centered("FEVER MODE!!!", WINDOW_WIDTH//2, 100, self.font_main, hsv_to_rgb(random.random(), 1, 1), self.game_surface)
        elif self.state == STATE_GAMEOVER:
            self.draw_text_centered("GAME OVER", WINDOW_WIDTH//2, WINDOW_HEIGHT//2, self.font_main, (255,50,50), self.game_surface)

        sx, sy = self.shake.get_offset()
        self.raw_screen.blit(self.game_surface, (sx, sy))
        
        pygame.display.flip()

    def draw_text_centered(self, text, x, y, font, color, surf):
        s = font.render(text, True, color)
        r = s.get_rect(center=(x, y))
        surf.blit(s, r)
        
    def handle_input(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT: return False
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE: return False
                
                self.input_code.append(e.key)
                if len(self.input_code) > 10: self.input_code.pop(0)
                if self.input_code == KONAMI_CODE:
                    self.toggle_fever()
                    self.input_code = []
        return True

    def run(self):
        while self.handle_input():
            self.update()
            self.draw()
            self.clock.tick(FPS)
        self.cap.release()
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    ModernOtedamaGame().run()
