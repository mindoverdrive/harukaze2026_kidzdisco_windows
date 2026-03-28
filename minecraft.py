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
Minecraft-like 3D Block Builder with Gesture Control
Pygame + Pygfx + MediaPipe
"""

import math
import time
import numpy as np
import cv2
import mediapipe as mp
import pygame
import display_utils
from rendercanvas.auto import RenderCanvas, loop
import pygfx as gfx
import pylinalg as la

# ==================== Constants ====================
_DU_W, _DU_H, _DU_X, _DU_Y = display_utils.get_second_monitor_size()
WINDOW_WIDTH = _DU_W
WINDOW_HEIGHT = _DU_H
BLOCK_SIZE = 3.0
GRID_SIZE = 100
INTERACTION_DISTANCE = 40.0 # Distance from camera to place blocks
MOVE_SPEED = 0.5
ROTATION_SPEED = 0.05

COLORS = [
    (1.0, 0.0, 0.0, 1.0),   # Red
    (1.0, 1.0, 0.0, 1.0),   # Yellow
    (0.2, 0.2, 0.2, 1.0),   # Dark Grey
    (0.5, 1.0, 0.0, 1.0),   # Chartreuse
    (0.0, 1.0, 0.0, 1.0),   # Green
    (1.0, 1.0, 1.0, 1.0),   # White
    (0.0, 1.0, 1.0, 1.0),   # Cyan
    (0.5, 0.5, 0.5, 1.0),   # Grey
    (1.0, 0.5, 0.0, 1.0),   # Orange
    (0.0, 0.0, 1.0, 1.0),   # Blue
    (0.5, 0.0, 1.0, 1.0),   # Violet
    (1.0, 0.0, 1.0, 1.0),   # Magenta
    (1.0, 0.0, 0.5, 1.0),   # Rose
    (0.0, 1.0, 0.5, 1.0),   # Spring Green
    (0.0, 0.5, 1.0, 1.0),   # Azure
    

]

# ==================== Utils ====================
def distance(p1, p2):
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

def np_distance(p1, p2):
    return np.linalg.norm(np.array(p1) - np.array(p2))

# ==================== Listeners & Logic ====================

class GestureManager:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.mp_face_mesh = mp.solutions.face_mesh
        
        self.hands = self.mp_hands.Hands(model_complexity=1, 
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        
        self.mouth_state = "closed" # closed, open
        self.last_mouth_open_time = 0
        self.color_cycle_trigger = False
        
        self.both_hands_fist_time = 0
        self.reset_trigger = False

    def process(self, image):
        # Image is RGB
        h, w, _ = image.shape
        results_hands = self.hands.process(image)
        results_face = self.face_mesh.process(image)
        
        gestures = {
            "left_hand": None, # {type: 'rotate', pos: (x,y), state: 'grab'/'hover'}
            "right_hand": None, # {type: 'pointer', pos: (x,y), action: 'create'/'erase'/'move'}
            "face": None # {mouth_open: bool}
        }
        
        # 1. Face Analysis (Mouth)
        if results_face.multi_face_landmarks:
            landmarks = results_face.multi_face_landmarks[0].landmark
            # Mouth lips: 13 (upper), 14 (lower)
            upper = landmarks[13]
            lower = landmarks[14]
            # Normalize by face size roughly?
            # Or just distance. Face is usually centered.
            # Using absolute distance
            dist = math.hypot(upper.x - lower.x, upper.y - lower.y)
            is_open = dist > 0.05 # Threshold needs checking
            
            if is_open and self.mouth_state == "closed":
                self.color_cycle_trigger = True
                self.mouth_state = "open"
            elif not is_open:
                self.mouth_state = "closed"
                
        # 2. Hand Analysis
        left_hand_lm = None
        right_hand_lm = None
        
        if results_hands.multi_hand_landmarks:
            for hand_landmarks, handedness in zip(results_hands.multi_hand_landmarks, results_hands.multi_handedness):
                label = handedness.classification[0].label
                # Note: MediaPipe assumes mirrored image input (selfie mode).
                # If label is "Right", it detects a right hand (user's left if mirrored? No, MP is smart).
                # Wait, standard MP: "Right" means RIGHT HAND.
                # User said: "Left hand rotates", "Right hand creates".
                
                if label == "Left":
                    left_hand_lm = hand_landmarks
                else:
                    right_hand_lm = hand_landmarks

        # --- Detect Gestures ---
        
        # Check for Double Fist -> Open (Reset)
        is_left_fist = self.is_fist(left_hand_lm) if left_hand_lm else False
        is_right_fist = self.is_fist(right_hand_lm) if right_hand_lm else False
        
        if is_left_fist and is_right_fist:
            if self.both_hands_fist_time == 0:
                self.both_hands_fist_time = time.time()
        else:
            # If we were fisting (?) and now opened both
            if self.both_hands_fist_time > 0:
                # If held for a bit? Or just event?
                # "Both hands simultaneously Goo -> Par"
                is_left_open = self.is_palm_open(left_hand_lm) if left_hand_lm else False
                is_right_open = self.is_palm_open(right_hand_lm) if right_hand_lm else False
                
                if is_left_open and is_right_open:
                    self.reset_trigger = True
                
                self.both_hands_fist_time = 0
                
        # Left Hand: Rotation
        if left_hand_lm:
            # Center of palm
            cx = (left_hand_lm.landmark[0].x + left_hand_lm.landmark[9].x) / 2
            cy = (left_hand_lm.landmark[0].y + left_hand_lm.landmark[9].y) / 2
            gestures["left_hand"] = {
                "pos": (cx, cy),
                "is_active": True
            }

        # Right Hand: Actions
        if right_hand_lm:
            # Index Finger Tip
            idx_tip = right_hand_lm.landmark[8]
            
            action = "none"
            if self.is_pointing(right_hand_lm):
                action = "create"
            elif self.is_palm_open(right_hand_lm):
                action = "erase"
            # Pinch (move) removed as per request
                
            gestures["right_hand"] = {
                "pos": (idx_tip.x, idx_tip.y), # 0-1 normalized
                "z": idx_tip.z, # relative depth
                "action": action
            }
            
        return gestures

    def is_pointing(self, landmarks):
        # Index straight, others folded
        # Simple check: Index Tip y < Index PIP y (if upright)
        # Better: Distance from wrist.
        # Check Index extended, Middle/Ring/Pinky closed.
        wrist = landmarks.landmark[0]
        idx_tip = landmarks.landmark[8]
        idx_pip = landmarks.landmark[6]
        mid_tip = landmarks.landmark[12]
        
        # Index extended?
        idx_ext = distance(wrist, idx_tip) > distance(wrist, idx_pip)
        # Middle closed?
        mid_clssd = distance(wrist, mid_tip) < distance(wrist, landmarks.landmark[10]) # PIP
        
        return idx_ext and mid_clssd

    def is_palm_open(self, landmarks):
        # All fingers extended
        wrist = landmarks.landmark[0]
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        
        count = 0
        for t, p in zip(tips, pips):
            if distance(wrist, landmarks.landmark[t]) > distance(wrist, landmarks.landmark[p]):
                count += 1
        return count >= 4

    def is_fist(self, landmarks):
        # All fingers closed
        wrist = landmarks.landmark[0]
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        
        count = 0
        for t, p in zip(tips, pips):
            if distance(wrist, landmarks.landmark[t]) < distance(wrist, landmarks.landmark[p]):
                count += 1
        return count >= 4
        
    # is_pinching removed


class EffectParticle:
    def __init__(self, pos, color, velocity):
        self.pos = np.array(pos, dtype=np.float32)
        self.velocity = np.array(velocity, dtype=np.float32)
        self.color = color
        self.life = 1.0 # Seconds
        
        self.mesh = gfx.Mesh(
            gfx.box_geometry(BLOCK_SIZE*0.3, BLOCK_SIZE*0.3, BLOCK_SIZE*0.3),
            gfx.MeshBasicMaterial(color=color)
        )
        self.mesh.local.position = pos

class MinecraftApp:
    def __init__(self):
        # Pygfx Setup
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="Hand Gesture Minecraft")
        display_utils.setup_rendercanvas_fullscreen(self.canvas)
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)
        self.scene = gfx.Scene()
        
        # Camera
        self.camera = gfx.PerspectiveCamera(70, WINDOW_WIDTH/WINDOW_HEIGHT)
        self.camera.local.z = 50
        
        # Directional Light
        self.scene.add(gfx.AmbientLight((0.5, 0.5, 0.5), 1.0))
        light = gfx.DirectionalLight((1, 1, 1), 1.0)
        light.local.position = (50, 100, 50)
        self.scene.add(light)

        self.cap = display_utils.open_camera()
        self.camera_frame_width, self.camera_frame_height = display_utils.get_camera_frame_size(self.cap)
        
        # Camera Feed Background - using pygfx Background for guaranteed render order
        self.bg_tex = gfx.Texture(
            np.zeros((self.camera_frame_height, self.camera_frame_width, 4), dtype=np.uint8),
            dim=2,
        )
        bg_material = gfx.BackgroundImageMaterial(map=self.bg_tex)
        self.bg_plane = gfx.Background(None, bg_material)
        self.scene.add(self.bg_plane)
        
        # Grid/Floor
        self.setup_grid()
        
        # Block Management
        self.blocks = {} # (idx_x, idx_y, idx_z) -> Mesh
        self.current_color_idx = 0
        self.particles = [] # List of EffectParticle
        
        # Cursor (Box)
        self.cursor = gfx.Mesh(
            gfx.box_geometry(BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE),
            gfx.MeshBasicMaterial(color=(1, 1, 1, 0.5), wireframe=True)
        )
        self.scene.add(self.cursor)
        
        # HUD (Instruction Manual)
        self.setup_hud()
        
        # Hand/Input
        self.gesture_manager = GestureManager()
        
        # State
        self.camera_rot_x = 0
        self.camera_rot_y = 0
        self.last_time = time.time()
        
    def setup_grid(self):
        # Grid removed for better AR transparency
        pass
        # grid = gfx.GridHelper(size=GRID_SIZE*BLOCK_SIZE, divisions=GRID_SIZE)
        # grid.local.rotation = la.quat_from_euler((math.pi/2, 0, 0)) # Rotate to be XZ plane
        # grid.local.y = -10 # Move down slightly
        # self.scene.add(grid)
        
    def setup_hud(self):
        # Create a HUD surface using Pygame for instructions
        pygame.font.init()
        hud_surface = pygame.Surface((1024, 512), pygame.SRCALPHA)
        hud_surface.fill((0, 0, 0, 100)) # Semi-transparent black
        
        font = pygame.font.SysFont("Arial", 40, bold=True)
        
        # Instructions List
        items = [
            ("☝️ Right Index", "Create Block"),
            ("🖐️ Right Open", "Erase Block"),
            # ("🤏 Right Pinch", "Move Block"), # Removed
            ("✋ Left Hand",  "Rotate View"),
            ("😮 Open Mouth", "Cycle Color"),
            ("✊✊ -> 👋👋",   "Reset All")
        ]
        
        y_off = 30
        for icon, desc in items:
            txt_icon = font.render(icon, True, (255, 255, 255))
            txt_desc = font.render(": " + desc, True, (200, 255, 200))
            hud_surface.blit(txt_icon, (50, y_off))
            hud_surface.blit(txt_desc, (350, y_off))
            y_off += 60
            
        # Current Color indicator area
        txt_color = font.render("Current Color:", True, (255, 255, 255))
        hud_surface.blit(txt_color, (50, 420))
        
        # Convert to texture
        rgba_view = pygame.surfarray.array3d(hud_surface)
        alpha_view = pygame.surfarray.array_alpha(hud_surface)
        
        # Transpose
        rgba_view = np.transpose(rgba_view, (1, 0, 2))
        alpha_view = np.transpose(alpha_view, (1, 0))
        
        h, w = rgba_view.shape[:2]
        self.hud_data = np.empty((h, w, 4), dtype=np.uint8)
        self.hud_data[..., :3] = rgba_view
        self.hud_data[..., 3] = alpha_view
        
        self.hud_tex = gfx.Texture(self.hud_data, dim=2)
        hud_material = gfx.MeshBasicMaterial(map=self.hud_tex)
        self.hud_plane = gfx.Mesh(gfx.plane_geometry(60, 30), hud_material)
        
        # Place HUD in screen corner (local camera space)
        self.hud_plane.local.position = (25, 20, -50) 
        self.camera.add(self.hud_plane) # Child of camera for fixed position
        
    def update_hud_color(self):
        # Draw a preview box of the current color
        c = COLORS[self.current_color_idx]
        color_rgb = (int(c[0]*255), int(c[1]*255), int(c[2]*255))
        
        # We can just update the segment of the texture
        # y: 420..420+50, x: 350..350+100
        self.hud_data[420:470, 350:450, :3] = color_rgb
        self.hud_data[420:470, 350:450, 3] = 255 # opaque
        
        self.hud_tex.data[:] = self.hud_data
        self.hud_tex.update_range((0,0,0), self.hud_tex.size)

    def get_world_pos_from_screen(self, screen_x, screen_y, depth):
        # Simple projection: Map 0-1 screen coords to a plane at distance 'depth' from camera
        # FOV calculation
        # Normalized Device Coordinates (NDC): -1 to 1
        ndc_x = (screen_x - 0.5) * 2
        ndc_y = -(screen_y - 0.5) * 2 # Flip Y for 3D
        
        # In a real app we'd use unproject, but for simplicity with fixed depth:
        # Tan(FOV/2) * depth * aspectRatio
        fov = self.camera.fov * (math.pi / 180)
        h_world = 2 * math.tan(fov / 2) * depth
        w_world = h_world * (WINDOW_WIDTH / WINDOW_HEIGHT)
        
        # Local camera space coordinates
        # Adjust for "hand pointing" feeling
        # screen_x 0 -> left, 1 -> right
        # We want to map this to world coordinates considering camera rotation.
        
        # Actually easier: Create a Ray from camera through screen pos.
        # Find intersection with a plane in front of camera at 'depth'.
        # Since we just want to place it freely in air relative to view:
        
        vec = la.vec_transform_quat((ndc_x * w_world / 2, ndc_y * h_world / 2, -depth), self.camera.local.rotation)
        pos = np.array(self.camera.local.position) + vec
        return pos

    def grid_coords(self, pos):
        return (
            int(round(pos[0] / BLOCK_SIZE)),
            int(round(pos[1] / BLOCK_SIZE)),
            int(round(pos[2] / BLOCK_SIZE))
        )

    def create_block(self, grid_pos):
        if grid_pos in self.blocks:
            return
            
        color = COLORS[self.current_color_idx]
        material = gfx.MeshPhongMaterial(color=color)
        geometry = gfx.box_geometry(BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)
        mesh = gfx.Mesh(geometry, material)
        
        x = grid_pos[0] * BLOCK_SIZE
        y = grid_pos[1] * BLOCK_SIZE
        z = grid_pos[2] * BLOCK_SIZE
        
        mesh.local.position = (x, y, z)
        self.scene.add(mesh)
        self.blocks[grid_pos] = mesh

    def remove_block(self, grid_pos):
        if grid_pos in self.blocks:
            mesh = self.blocks.pop(grid_pos)
            self.scene.remove(mesh)
            
            # Spawn delete particles (Crumbing effect)
            center_pos = mesh.local.position
            color = mesh.material.color
            for _ in range(8):
                # Random velocity slightly upwards then down
                vel = (
                    (np.random.random() - 0.5) * 5,
                    (np.random.random() * 5) + 2, 
                    (np.random.random() - 0.5) * 5
                )
                offset = (
                    (np.random.random() - 0.5) * BLOCK_SIZE,
                    (np.random.random() - 0.5) * BLOCK_SIZE,
                    (np.random.random() - 0.5) * BLOCK_SIZE
                )
                p = EffectParticle(
                    (center_pos[0]+offset[0], center_pos[1]+offset[1], center_pos[2]+offset[2]),
                    color, vel
                )
                self.scene.add(p.mesh)
                self.particles.append(p)
                
    # move_grabbed_block removed as per request

    def clear_all(self):
        # Explode all blocks
        for mesh in self.blocks.values():
            self.scene.remove(mesh)
            
            # Spawn explosion particles
            center_pos = mesh.local.position
            color = mesh.material.color
            for _ in range(2): # Fewer particles per block to save perf
                # Explosion velocity outwards from center? Or just random
                vel = (
                    (np.random.random() - 0.5) * 20,
                    (np.random.random() - 0.5) * 20 + 5,
                    (np.random.random() - 0.5) * 20
                )
                p = EffectParticle(center_pos, color, vel)
                self.scene.add(p.mesh)
                self.particles.append(p)
                
        self.blocks.clear()
        
    def update_particles(self, dt):
        dead_particles = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                dead_particles.append(p)
                continue
                
            # Physics
            p.velocity[1] -= 20.0 * dt # Gravity
            p.pos += p.velocity * dt
            p.mesh.local.position = p.pos
            
            # Fade out alpha?
            # p.mesh.material.opacity = p.life
            
        for p in dead_particles:
            self.scene.remove(p.mesh)
            self.particles.remove(p)

    def update_camera(self, left_hand_data):
        if not left_hand_data: return
        
        # 'pos' is (0.5, 0.5) at center
        lx, ly = left_hand_data['pos']
        
        # Map to rotation velocity or absolute rotation?
        # Absolute rotation is more intuitive for "holding an object".
        # But for viewing a world, maybe velocity.
        # User said: "Left hand rotates 3D".
        # Let's try: Center screen is rest. Moving hand rotates camera around origin (0,0,0) or itself.
        # Let's Orbit around (0,0,0)
        
        target_rot_y = (lx - 0.5) * -3.0 # Yaw
        target_rot_x = (ly - 0.5) * 2.0 # Pitch
        
        # Smooth interpolation
        self.camera_rot_y += (target_rot_y - self.camera_rot_y) * 0.1
        self.camera_rot_x += (target_rot_x - self.camera_rot_x) * 0.1
        
        # Orbit Logic
        # r = distance
        r = 60
        cx = r * math.sin(self.camera_rot_y) * math.cos(self.camera_rot_x)
        cz = r * math.cos(self.camera_rot_y) * math.cos(self.camera_rot_x)
        cy = r * math.sin(self.camera_rot_x)
        
        self.camera.local.position = (cx, cy, cz)
        self.camera.look_at((0, 0, 0))


    def animate(self):
        now = time.time()
        dt = now - self.last_time
        self.last_time = now
        
        self.update_particles(dt)
        
        ret, frame = self.cap.read()
        if not ret: return
        
        # Flip and convert
        frame = cv2.flip(frame, 1) # Mirror for selfie
        # frame = cv2.flip(frame, 0) # Removed: don't flip analysis frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process inputs
        inputs = self.gesture_manager.process(rgb)
        
        # 1. Logic
        
        # Reset
        if self.gesture_manager.reset_trigger:
            self.clear_all()
            self.gesture_manager.reset_trigger = False
        
        # Color Cycle
        if self.gesture_manager.color_cycle_trigger:
            self.current_color_idx = (self.current_color_idx + 1) % len(COLORS)
            # Update cursor color
            self.cursor.material.color = COLORS[self.current_color_idx]
            self.update_hud_color() # Update instructions HUD color
            self.gesture_manager.color_cycle_trigger = False
            print(f"Color changed to {self.current_color_idx}")
            
        # Camera Background Plane Update
        frame_rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        # Flip vertically for Pygfx (OpenCV top-left vs Pygfx bottom-left)
        frame_rgba = cv2.flip(frame_rgba, 0)
        self.bg_tex.data[:] = frame_rgba
        self.bg_tex.update_range((0,0,0), self.bg_tex.size)
        
        # Camera
        self.update_camera(inputs["left_hand"])
        
        # Right Hand Interactions
        rh = inputs["right_hand"]
        if rh:
            # Map hand position to 3D world cursor
            # Depth: adjust based on pinch or just fixed interaction plane?
            # Creating: Use fixed plane.
            world_pos = self.get_world_pos_from_screen(rh['pos'][0], rh['pos'][1], INTERACTION_DISTANCE)
            grid_pos = self.grid_coords(world_pos)
            
            # Update Cursor visual
            self.cursor.local.position = (
                grid_pos[0] * BLOCK_SIZE,
                grid_pos[1] * BLOCK_SIZE,
                grid_pos[2] * BLOCK_SIZE
            )
            
            action = rh['action']
            
            if action == 'create':
                self.grabbed_block_pos = None
                self.create_block(grid_pos)
                
            elif action == 'erase':
                self.remove_block(grid_pos)
                
            # 'move' action removed

        # Render
        # Render
        try:
            try:
                self.renderer.render(self.scene, self.camera)
            except RuntimeError:
                pass
        except RuntimeError as exc:
            print(f"[minecraft] Render skipped: {exc}")
            # loop.stop() # Removed to prevent DX12 surface loss crash
            return
        self.canvas.request_draw()

    def run(self):
        self.canvas.request_draw(self.animate)
        loop.run()
        
    def cleanup(self):
        self.gesture_manager.hands.close()
        self.gesture_manager.face_mesh.close()
        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = MinecraftApp()
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.cleanup()
