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

from contextlib import ExitStack
import scene_control
from minecraft_reset import (TwoHandReset, reset_sample, MAX_PARTICLES, RESET_SECONDS)
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
        self._resources = ExitStack()
        try:
            self._initialize()
        except BaseException as error:
            try:
                self._resources.close()
            except BaseException as cleanup_error:
                error.add_note(f"Minecraft gesture cleanup failed: {cleanup_error}")
            raise

    def close(self):
        self._resources.close()

    def _initialize(self):
        from hand_input_profile import solutions_options
        self.mp_hands = mp.solutions.hands
        self.mp_face_mesh = mp.solutions.face_mesh
        
        self.hands = self.mp_hands.Hands(**solutions_options(3))
        self._resources.callback(self.hands.close)
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=2,  # Reset is single-player; visible extra faces inhibit it.
            refine_landmarks=True,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        
        self._resources.callback(self.face_mesh.close)
        self.mouth_state = "closed" # closed, open
        self.last_mouth_open_time = 0
        self.color_cycle_trigger = False
        
        self.detected_hands = ()
        self.reset_gesture = TwoHandReset()
        self.reset_trigger = False

    def process(self, image):
        # Image is RGB
        h, w, _ = image.shape
        results_hands = self.hands.process(image)
        self.detected_hands = tuple(results_hands.multi_hand_landmarks or ())
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
        
        # Only fresh, unambiguous observations advance the one-shot reset.
        # Hands/FaceMesh do not provide person ownership: one player at a time.
        self.reset_trigger = self.reset_gesture.update(
            reset_sample(results_hands, results_face), time.monotonic())

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

    def cancel_reset(self):
        self.reset_gesture.cancel()
        self.reset_trigger = False

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
    def __init__(self, pos, color, velocity, *, geometry=None, life=1.0, spin=False):
        self.pos = np.array(pos, dtype=np.float32)
        self.velocity = np.array(velocity, dtype=np.float32)
        self.color = color
        self.life = min(life, RESET_SECONDS)
        self.spin = spin
        self.age = 0.0
        
        self.mesh = gfx.Mesh(
            geometry if geometry is not None else gfx.box_geometry(BLOCK_SIZE*0.3, BLOCK_SIZE*0.3, BLOCK_SIZE*0.3),
            gfx.MeshBasicMaterial(color=color)
        )
        self.mesh.local.position = pos

class MinecraftApp:
    def __init__(self):
        self._resources = ExitStack()
        self._frame_error = None
        self._camera_failure_since = None
        self._last_frame_id = None
        self._last_fresh_at = time.monotonic()
        try:
            self._initialize()
        except BaseException as error:
            try:
                self.cleanup()
            except BaseException as cleanup_error:
                error.add_note(f"Minecraft cleanup failed: {cleanup_error}")
            raise

    def _initialize(self):
        if scene_control._child_control is not None:
            import os
            if not os.environ.get("HARUKAZE_CAMERA_SHM") or os.environ.get("HARUKAZE_SHARED_CAMERA_REQUIRED", "").lower() not in {"1", "true", "yes", "on"}:
                raise RuntimeError("Minecraft requires Manager shared camera; physical fallback is forbidden")
        # Pygfx Setup
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="Hand Gesture Minecraft")
        self._resources.callback(self.canvas.close)
        self.canvas.add_event_handler(self.on_event, "close")
        display_utils.setup_rendercanvas_fullscreen(self.canvas)
        self.verify_managed_display()
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
        if self.cap is None:
            raise RuntimeError("Minecraft shared camera attach failed")
        self._resources.callback(self.cap.release)
        if not self.cap.isOpened():
            raise RuntimeError("Minecraft shared camera is not open")
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
        self.particles = [] # List of EffectParticle; shared cap includes erase effects.
        self._reset_remaining = 0.0
        self._reset_finished_this_frame = False
        self.grabbed_block_pos = None
        
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
        self._resources.callback(self.gesture_manager.close)
        from hand_focus_pygfx import PygfxHandOverlay
        self.hand_overlay = PygfxHandOverlay(WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # State
        self.camera_rot_x = 0
        self.camera_rot_y = 0
        self.last_time = time.monotonic()
        
    def verify_managed_display(self):
        if scene_control._child_control is None:
            return
        import glfw
        window = getattr(self.canvas, "_window", None)
        if window is None:
            raise RuntimeError("Minecraft audience window cannot be verified")
        width, height, x, y = display_utils.get_second_monitor_size()
        if tuple(glfw.get_window_pos(window)) != (x, y) or tuple(glfw.get_window_size(window)) != (width, height):
            raise RuntimeError("Minecraft audience window geometry mismatch")

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
        self._resources.callback(pygame.font.quit)
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
            ("Hold 2 fists", "Open to reset (1 player)")
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
        aspect = WINDOW_WIDTH / WINDOW_HEIGHT
        # pygfx FOV describes mean extent, as in the Saturn projection.
        h_world = 2 * math.tan(fov / 2) * depth * 2.0 / (1.0 + aspect)
        w_world = h_world * aspect
        
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
            for _ in range(min(8, MAX_PARTICLES - len(self.particles))):
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
        if self._reset_remaining > 0:
            return  # Never overlap bursts or allocate another batch.
        self._reset_remaining = RESET_SECONDS
        self.gesture_manager.cancel_reset()
        self.gesture_manager.color_cycle_trigger = False
        self.grabbed_block_pos = None
        self.cursor.visible = False
        for particle in self.particles:
            self.scene.remove(particle.mesh)
        self.particles.clear()
        meshes = tuple(self.blocks.values())
        for mesh in meshes:
            self.scene.remove(mesh)
        self.blocks.clear()
        if not meshes:
            return

        # Share cube geometry. Sample the whole construction within a fixed budget
        # instead of multiplying particles by an unbounded number of blocks.
        geometry = gfx.box_geometry(BLOCK_SIZE * 0.3, BLOCK_SIZE * 0.3, BLOCK_SIZE * 0.3)
        center = np.mean([mesh.local.position for mesh in meshes], axis=0)
        count = min(MAX_PARTICLES, max(48, len(meshes) * 12))
        for index in range(count):
            mesh = meshes[index * len(meshes) // count]
            position = np.asarray(mesh.local.position, dtype=np.float32)
            outward = position - center + np.random.uniform(-BLOCK_SIZE, BLOCK_SIZE, 3)
            length = np.linalg.norm(outward)
            outward = outward / length if length > 1e-6 else np.array((0.0, 1.0, 0.0))
            velocity = outward * np.random.uniform(24.0, 42.0)
            velocity[1] += np.random.uniform(12.0, 22.0)
            particle = EffectParticle(
                position + np.random.uniform(-BLOCK_SIZE * 0.4, BLOCK_SIZE * 0.4, 3),
                mesh.material.color, velocity, geometry=geometry,
                life=RESET_SECONDS, spin=True)
            self.scene.add(particle.mesh)
            self.particles.append(particle)

    def finish_reset(self):
        for particle in self.particles:
            self.scene.remove(particle.mesh)
        self.particles.clear()
        self.grabbed_block_pos = None
        self.current_color_idx = 0
        self.cursor.visible = False
        self.cursor.local.position = (0, 0, 0)
        self.cursor.material.color = (1, 1, 1, 0.5)
        self.camera_rot_x = self.camera_rot_y = 0
        self.camera.local.position = (0, 0, 50)
        self.camera.local.rotation = (0, 0, 0, 1)
        self.update_hud_color()
        self.gesture_manager.cancel_reset()
        self.gesture_manager.color_cycle_trigger = False
        self._reset_remaining = 0.0
        self._reset_finished_this_frame = True

    def update_particles(self, dt):
        # Expiry uses elapsed time; physics uses a bounded step after a stall.
        dt = max(0.0, dt)
        step = min(dt, 0.05)
        survivors = []
        for particle in self.particles:
            particle.life -= dt
            if particle.life <= 0:
                self.scene.remove(particle.mesh)
                continue
            particle.velocity[1] -= 20.0 * step
            particle.pos += particle.velocity * step
            particle.mesh.local.position = particle.pos
            particle.age += step
            if particle.spin:
                particle.mesh.local.rotation = la.quat_from_euler(
                    tuple(particle.velocity * particle.age * 0.12))
                shrink = min(1.0, particle.life / 0.35)
                particle.mesh.local.scale = (shrink, shrink, shrink)
            survivors.append(particle)
        self.particles[:] = survivors
        if self._reset_remaining > 0:
            self._reset_remaining = max(0.0, self._reset_remaining - dt)
            if self._reset_remaining == 0:
                self.finish_reset()

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


    def on_event(self, event):
        if event.get("event_type") == "close":
            scene_control.notify_exit_request("window_close")
            loop.stop()

    def animate(self):
        try:
            self._animate_frame()
        except BaseException as error:
            # RenderCanvas may log/swallow draw exceptions; make run() fail observably.
            self._frame_error = error
            loop.stop()

    def _animate_frame(self):
        now = time.monotonic()
        dt = now - self.last_time
        self.last_time = now
        
        self.update_particles(dt)
        
        ret, frame = self.cap.read()
        if not ret:
            self.clear_hand_feedback()
            self.gesture_manager.cancel_reset()
            now = time.monotonic()
            if self._camera_failure_since is None:
                self._camera_failure_since = now
            if now - self._camera_failure_since >= 3.0:
                raise RuntimeError("Minecraft camera input stopped")
            self.canvas.request_draw()
            return
        self._camera_failure_since = None
        frame_id = getattr(self.cap, "last_read_frame_id", None)
        if scene_control._child_control is not None:
            if frame_id == self._last_frame_id:
                if time.monotonic() - self._last_fresh_at >= 0.25:
                    self.clear_hand_feedback()
                if time.monotonic() - self._last_fresh_at >= 3.0:
                    raise RuntimeError("Minecraft shared camera frames stopped advancing")
                self.canvas.request_draw()
                return
            self._last_frame_id = frame_id
            self._last_fresh_at = time.monotonic()
        
        # Flip and convert
        frame = cv2.flip(frame, 1) # Mirror for selfie
        # frame = cv2.flip(frame, 0) # Removed: don't flip analysis frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process inputs; an effect cannot pre-arm the next reset.
        inputs = self.gesture_manager.process(rgb)
        if self._reset_remaining > 0 or self._reset_finished_this_frame:
            self.gesture_manager.cancel_reset()
        
        # 1. Logic
        
        # Reset
        if self.gesture_manager.reset_trigger:
            self.clear_all()
            self.gesture_manager.reset_trigger = False
        
        input_locked = (self._reset_remaining > 0 or self._reset_finished_this_frame
                        or self.gesture_manager.reset_gesture.armed)
        if input_locked:
            self.gesture_manager.color_cycle_trigger = False
            self.cursor.visible = False

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
        if not input_locked:
            self.update_camera(inputs["left_hand"])
        
        # Right Hand Interactions
        rh = None if input_locked else inputs["right_hand"]
        self.cursor.visible = rh is not None
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

        # Background uses full-viewport normalized coordinates; keep the same
        # mapping without mirroring again. Final pass stays visible above blocks.
        self.hand_overlay.update(self.gesture_manager.detected_hands)
        self.renderer.render(self.scene, self.camera, flush=False)
        self.renderer.render(self.hand_overlay.scene, self.hand_overlay.camera, clear=False)
        self._reset_finished_this_frame = False
        scene_control.notify_first_frame(self.cap)
        self.canvas.request_draw()

    def clear_hand_feedback(self):
        """Remove stale marks without advancing gestures or FIRST_FRAME."""
        self.hand_overlay.clear()
        self.renderer.render(self.scene, self.camera, flush=False)
        self.renderer.render(self.hand_overlay.scene, self.hand_overlay.camera, clear=False)

    def run(self):
        try:
            self.canvas.request_draw(self.animate)
            loop.run()
            if self._frame_error is not None:
                raise self._frame_error
        finally:
            self.cleanup()
        
    def cleanup(self):
        try:
            self._resources.close()
        finally:
            # Release scene-owned GPU references; the shared device belongs to pygfx.
            for name in ("blocks", "particles", "cursor", "hud_plane", "hud_data", "hud_tex", "bg_tex", "bg_plane", "scene", "renderer", "camera", "gesture_manager", "hand_overlay", "cap", "canvas"):
                if hasattr(self, name):
                    setattr(self, name, None)

if __name__ == "__main__":
    app = MinecraftApp()
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.cleanup()
