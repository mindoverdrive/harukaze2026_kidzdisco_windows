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
import pygame
import display_utils
import mediapipe as mp
import numpy as np
import math
import random

def solve_ik_2bone(root, target, l1, l2, flip=False):
    dx = target[0] - root[0]
    dy = target[1] - root[1]
    dist = math.hypot(dx, dy)
    
    if dist >= l1 + l2:
        angle = math.atan2(dy, dx)
        return (root[0] + l1*math.cos(angle), root[1] + l1*math.sin(angle)), target

    dist = max(dist, 0.001)
    val = (l1*l1 + dist*dist - l2*l2) / (2 * l1 * dist)
    val = max(-1.0, min(1.0, val))
    a1 = math.acos(val)
    
    base_angle = math.atan2(dy, dx)
    final_angle = base_angle - a1 if flip else base_angle + a1
        
    j_x = root[0] + l1 * math.cos(final_angle)
    j_y = root[1] + l1 * math.sin(final_angle)
    
    return (j_x, j_y), target

class Bug:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.pos = np.array([random.uniform(50, w-50), random.uniform(50, h-50)])
        
        # 1/50 chance for a rainbow/special bug
        self.is_special = random.randint(1, 50) == 1
        
        if self.is_special:
            self.color = (255, 255, 255) # Placeholder, will be dynamically rainbow
        else:
            self.color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
            
        self.pattern = random.randint(0, 9)
        self.speed_mult = random.uniform(0.5, 2.5) * (1.5 if self.is_special else 1.0)
        self.time = random.uniform(0, 100)
        self.active = True
        self.radius = 12 if self.is_special else 5
        self.particles = []  # trailing light particles for special bugs

    def update(self):
        self.time += 0.05 * self.speed_mult
        t = self.time
        
        if self.is_special:
            r = int((math.sin(t * 5) + 1) * 127)
            g = int((math.sin(t * 5 + 2) + 1) * 127)
            b = int((math.sin(t * 5 + 4) + 1) * 127)
            self.color = (r, g, b)
            # Spawn trailing particle
            self.particles.append([self.pos.copy(), (r, g, b), random.uniform(5, 12)])
            # Decay particles
            for p in self.particles:
                p[2] *= 0.85
            self.particles = [p for p in self.particles if p[2] > 0.5]

        # 10 different movement patterns
        if self.pattern == 0:
            # Linear erratic
            dx = math.sin(t * 2) * 2
            dy = math.cos(t * 1.5) * 2
        elif self.pattern == 1:
            # Circles
            dx = math.cos(t) * 3
            dy = math.sin(t) * 3
        elif self.pattern == 2:
            # Figure 8 fast
            dx = math.cos(t * 2) * 4
            dy = math.sin(t * 4) * 4
        elif self.pattern == 3:
            # Jitter
            dx = random.uniform(-4, 4)
            dy = random.uniform(-4, 4)
        elif self.pattern == 4:
            # Slow sweep
            dx = math.sin(t * 0.5) * 1.5
            dy = 1.0
        elif self.pattern == 5:
            # Zig zag
            dx = 3 if int(t * 2) % 2 == 0 else -3
            dy = 2
        elif self.pattern == 6:
            # Spiral outward
            r = (math.sin(t)*0.5 + 0.5) * 5
            dx = math.cos(t*3) * r
            dy = math.sin(t*3) * r
        elif self.pattern == 7:
            # Dash and stop
            if int(t) % 3 == 0:
                dx, dy = 0, 0
            else:
                dx = math.cos(t*10)*5
                dy = math.sin(t*10)*5
        elif self.pattern == 8:
            # Bouncing wave
            dx = 2.5
            dy = math.sin(t * 3) * 5
        else:
            # Totally random wander
            dx = math.sin(t * random.uniform(1, 3)) * 3
            dy = math.cos(t * random.uniform(1, 3)) * 3

        self.pos[0] += dx
        self.pos[1] += dy

        # Wrap around edges
        if self.pos[0] < 0: self.pos[0] += self.w
        elif self.pos[0] > self.w: self.pos[0] -= self.w
        if self.pos[1] < 0: self.pos[1] += self.h
        elif self.pos[1] > self.h: self.pos[1] -= self.h

    def draw(self, surface):
        if self.active:
            if self.is_special:
                # Draw trailing particles
                for p in self.particles:
                    pygame.draw.circle(surface, p[1], (int(p[0][0]), int(p[0][1])), int(p[2]))
                # Outer glow ring
                pygame.draw.circle(surface, self.color, (int(self.pos[0]), int(self.pos[1])), self.radius + 4, 2)
                # Inner bright core
                pygame.draw.circle(surface, (255, 255, 255), (int(self.pos[0]), int(self.pos[1])), int(self.radius * 0.6))
            else:
                pygame.draw.circle(surface, self.color, (int(self.pos[0]), int(self.pos[1])), self.radius)


def solve_ik_2bone_fk_style(root, target, l1, l2, phase_offset, dist_factor):
    # This solves IK like normal so the foot stays planted, but calculates
    # the joint position with an exaggerated, dynamic offset (acting like an FK joint).
    dx = target[0] - root[0]
    dy = target[1] - root[1]
    
    mid_x = root[0] + dx * 0.5
    mid_y = root[1] + dy * 0.5
    
    # Perp direction
    length = math.hypot(dx, dy)
    if length < 0.001:
        length = 0.001
        
    nx = -dy / length
    ny = dx / length
    
    # Exaggerated outward bowing
    bow_amount = (l1 + l2) * 0.8 * dist_factor * math.sin(phase_offset)
    
    j_x = mid_x + nx * bow_amount
    j_y = mid_y + ny * bow_amount
    
    return (j_x, j_y), target
    
    return (j_x, j_y), target

def solve_fk_2bone(root, base_angle, swing_angle, knee_angle, l1, l2):
    a1 = base_angle + swing_angle
    j_x = root[0] + l1 * math.cos(a1)
    j_y = root[1] + l1 * math.sin(a1)
    
    a2 = a1 + knee_angle
    end_x = j_x + l2 * math.cos(a2)
    end_y = j_y + l2 * math.sin(a2)
    
    return (j_x, j_y), (end_x, end_y)

class Spider:
    def __init__(self, x, y, is_ik=True):
        self.pos = np.array([x, y], dtype=float)
        self.is_ik = is_ik
        self.num_legs = 8
        self.leg_bases = []
        self.feet = []
        self.vel = np.array([0.0, 0.0])
        self.base_radius = 20 * 0.66
        self.phase = 0.0
        self.color = np.array([255.0, 255.0, 255.0]) # Target color
        self.current_color = np.array([255.0, 255.0, 255.0]) # Interpolated display color
        
        self.rainbow_mode = False
        self.rainbow_timer = 0
        self.particles = []  # particle effects for rainbow mode
        
        self.leg_angles = []
        self.leg_lengths = []
        
        self.leg_stepping = [False] * 8
        self.leg_step_start = [np.array([0.0, 0.0])] * 8
        self.leg_step_end = [np.array([0.0, 0.0])] * 8
        self.leg_step_t = [0.0] * 8
        
        for i in range(self.num_legs):
            angle = random.uniform(0, 2 * math.pi)
            self.leg_angles.append(angle)
            l1 = random.uniform(30, 80) * 0.66
            l2 = random.uniform(40, 100) * 0.66
            self.leg_lengths.append((l1, l2))
            
            bx = x + self.base_radius * math.cos(angle)
            by = y + self.base_radius * math.sin(angle)
            self.leg_bases.append(np.array([bx, by]))
            
            fx = x + (l1 + l2) * 0.7 * math.cos(angle)
            fy = y + (l1 + l2) * 0.7 * math.sin(angle)
            self.feet.append(np.array([fx, fy]))

    def update(self, target_pos, bugs):
        # Rainbow mode: color cycling + particle spawning
        if self.rainbow_mode:
            self.rainbow_timer -= 1
            if self.rainbow_timer <= 0:
                self.rainbow_mode = False
            else:
                t = pygame.time.get_ticks() / 150.0
                r = int((math.sin(t * 2) + 1) * 127)
                g = int((math.sin(t * 2 + 2) + 1) * 127)
                b = int((math.sin(t * 2 + 4) + 1) * 127)
                self.color = np.array([r, g, b], dtype=float)
                # Spawn particles from body
                self.particles.append([self.pos.copy(), (r, g, b), random.uniform(8, 20)])
                # Spawn particles from random feet
                for foot in self.feet:
                    if random.random() < 0.2:
                        self.particles.append([foot.copy(), (r, g, b), random.uniform(4, 10)])

        # Update particles (float upward + fade)
        for p in self.particles:
            p[0][0] += random.uniform(-3, 3)
            p[0][1] -= random.uniform(1, 5)
            p[2] *= 0.88
        self.particles = [p for p in self.particles if p[2] > 0.5]

        self.current_color += (self.color - self.current_color) * 0.05
        
        # Check eating bugs
        for bug in bugs:
            if bug.active:
                if np.linalg.norm(self.pos - bug.pos) < self.base_radius * 2.0:
                    bug.active = False
                    if bug.is_special:
                        self.rainbow_mode = True
                        self.rainbow_timer = 60 * 30  # 30 seconds at 60 FPS
                    else:
                        self.color = np.array(bug.color, dtype=float)
                    # Burst particles on eat
                    for _ in range(30 if bug.is_special else 10):
                        c = (255, 255, 255) if bug.is_special else bug.color
                        offset = np.array([random.uniform(-10, 10), random.uniform(-10, 10)])
                        self.particles.append([self.pos.copy() + offset, c, random.uniform(6, 15)])

        t = np.array(target_pos, dtype=float)
        diff = t - self.pos
        dist = np.linalg.norm(diff)
        
        if dist > 0:
            speed = min(dist * 0.06, 12.0)
            if self.rainbow_mode:
                speed *= 1.3
            self.vel = (diff / dist) * speed
        else:
            self.vel *= 0.5
            
        self.pos += self.vel
        self.phase += np.linalg.norm(self.vel) * 0.15
        
        for i in range(self.num_legs):
            angle = self.leg_angles[i]
            ideal_bx = self.pos[0] + self.base_radius * math.cos(angle)
            ideal_by = self.pos[1] + self.base_radius * math.sin(angle)
            
            foot_dir = self.feet[i] - np.array([ideal_bx, ideal_by])
            foot_dist = np.linalg.norm(foot_dir)
            if foot_dist > 0:
                pull = (foot_dir / foot_dist) * min(self.base_radius * 0.5, foot_dist * 0.1)
            else:
                pull = np.array([0, 0])
            self.leg_bases[i] = np.array([ideal_bx, ideal_by]) + pull

        for i in range(self.num_legs):
            if self.leg_stepping[i]:
                self.leg_step_t[i] += 0.1
                if self.leg_step_t[i] >= 1.0:
                    self.leg_step_t[i] = 1.0
                    self.leg_stepping[i] = False
                    self.feet[i] = self.leg_step_end[i].copy()
                else:
                    t_val = self.leg_step_t[i]
                    sx, sy = self.leg_step_start[i]
                    ex, ey = self.leg_step_end[i]
                    self.feet[i] = np.array([sx + (ex - sx) * t_val, sy + (ey - sy) * t_val])
                    
        stepping_count = sum(self.leg_stepping)
        if stepping_count < 2:
            best_score = 0
            best_leg = -1
            
            for i in range(self.num_legs):
                if not self.leg_stepping[i]:
                    base = self.leg_bases[i]
                    foot = self.feet[i]
                    dist_to_base = np.linalg.norm(foot - base)
                    max_reach = self.leg_lengths[i][0] + self.leg_lengths[i][1]
                    
                    dist_to_cursor = np.linalg.norm(foot - target_pos)
                    
                    ideal_fx = base[0] + math.cos(self.leg_angles[i]) * (max_reach * 0.6)
                    ideal_fy = base[1] + math.sin(self.leg_angles[i]) * (max_reach * 0.6)
                    err = np.linalg.norm(foot - np.array([ideal_fx, ideal_fy]))
                    
                    force_step = dist_to_base > max_reach * 0.85
                    
                    if force_step or err > max_reach * 0.4:
                        score = dist_to_cursor + (2000 if force_step else 0)
                        if score > best_score:
                            best_score = score
                            best_leg = i
                            
            if best_leg != -1:
                self.leg_stepping[best_leg] = True
                self.leg_step_t[best_leg] = 0.0
                self.leg_step_start[best_leg] = self.feet[best_leg].copy()
                
                base = self.leg_bases[best_leg]
                max_reach = self.leg_lengths[best_leg][0] + self.leg_lengths[best_leg][1]
                
                ideal_fx = base[0] + math.cos(self.leg_angles[best_leg]) * (max_reach * 0.5)
                ideal_fy = base[1] + math.sin(self.leg_angles[best_leg]) * (max_reach * 0.5)
                
                new_fx = ideal_fx + self.vel[0] * 15
                new_fy = ideal_fy + self.vel[1] * 15
                self.leg_step_end[best_leg] = np.array([new_fx, new_fy])

    def draw(self, surface):
        points = []
        draw_color = (int(self.current_color[0]), int(self.current_color[1]), int(self.current_color[2]))

        # Draw spider particles (rainbow aura)
        for p in self.particles:
            pygame.draw.circle(surface, p[1], (int(p[0][0]), int(p[0][1])), int(p[2]))

        for i in range(self.num_legs):
            base = self.leg_bases[i]
            target = self.feet[i]
            l1, l2 = self.leg_lengths[i]
            
            if self.is_ik:
                flip = i % 2 == 0
                j, end = solve_ik_2bone(base, target, l1, l2, flip)
            else:
                # Foot is planted on target, but the knee bows out wildly
                dist_factor = 1.0 - (np.linalg.norm(target - base) / (l1 + l2))
                dist_factor = max(0.2, dist_factor)
                phase_offset = self.phase * 0.5 + i * 2.5
                j, end = solve_ik_2bone_fk_style(base, target, l1, l2, phase_offset, dist_factor)

            pygame.draw.line(surface, draw_color, base, j, 2)
            pygame.draw.line(surface, draw_color, j, end, 2)
            pygame.draw.circle(surface, draw_color, (int(j[0]), int(j[1])), 4)
            pygame.draw.circle(surface, draw_color, (int(end[0]), int(end[1])), 4)
                
            points.append((int(base[0]), int(base[1])))
            
        if len(points) >= 3:
            center_x = sum([p[0] for p in points]) / len(points)
            center_y = sum([p[1] for p in points]) / len(points)
            
            def get_angle(p):
                return math.atan2(p[1] - center_y, p[0] - center_x)
                
            points.sort(key=get_angle)
            
            pygame.draw.polygon(surface, draw_color, points, 2)
            for p in points:
                pygame.draw.circle(surface, draw_color, p, 6)
                
        pygame.draw.circle(surface, draw_color, (int(self.pos[0]), int(self.pos[1])), 10)

def main():
    pygame.init()
    screen, _pg_size = display_utils.setup_pygame_fullscreen()
    width, height = screen.get_size()
    pygame.display.set_caption("Spider Cursor")
    clock = pygame.time.Clock()

    cap = display_utils.open_camera()
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(model_complexity=1, 
        max_num_hands=2,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7
    )

    spider_1 = Spider(width//2 - 100, height//2, True)
    spider_2 = Spider(width//2 + 100, height//2, False)

    bugs = []
    max_bugs = 5

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        if len(bugs) < max_bugs and random.random() < 0.01:
            bugs.append(Bug(width, height))

        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)

        target1 = None
        target2 = None

        if results.multi_hand_landmarks:
            h_count = len(results.multi_hand_landmarks)
            h0 = results.multi_hand_landmarks[0].landmark[8]
            target1 = np.array([h0.x * width, h0.y * height])
            
            if h_count > 1:
                h1 = results.multi_hand_landmarks[1].landmark[8]
                target2 = np.array([h1.x * width, h1.y * height])
            else:
                target2 = target1 + np.array([100, 100])

        if target1 is not None:
            spider_1.update(target1, bugs)
        else:
            spider_1.update(spider_1.pos, bugs)

        if target2 is not None:
            spider_2.update(target2, bugs)
        else:
            spider_2.update(spider_2.pos, bugs)

        screen.fill((0, 0, 0))

        # Update and draw bugs
        for bug in bugs[:]:
            if bug.active:
                bug.update()
                bug.draw(screen)
            else:
                bugs.remove(bug)

        spider_1.draw(screen)
        spider_2.draw(screen)

        pygame.display.flip()
        clock.tick(60)

    cap.release()
    pygame.quit()

if __name__ == "__main__":
    main()
