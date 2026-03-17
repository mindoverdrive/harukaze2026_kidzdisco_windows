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
pygfx Psychedelic Interactive Art
WGPU-based real-time mesh manipulation and color shifting.
"""

import os
import sys
import time
import math
import cv2
import numpy as np
import pygfx as gfx
from rendercanvas.auto import RenderCanvas, loop
import mediapipe as mp
import pylinalg as la

# Local modules path
sys.path.append(os.path.join(os.path.dirname(__file__), 'test'))

try:
    from hand_tracker import HandTracker
except ImportError:
    try:
        from test.hand_tracker import HandTracker
    except ImportError:
        HandTracker = None
        print("Warning: HandTracker not found. Interaction will be limited.")

# ==================== Configuration ====================
WIDTH, HEIGHT = 1280, 720
GRID_SIZE = (160, 90)  # High resolution mesh for smooth deformation

# ==================== Simulation Logic ====================
class PsychedelicApp:
    def __init__(self):
        # 1. Camera Setup
        self.cap = cv2.VideoCapture(2)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(2) # Cascade to 0
        
        # Increase resolution for better look
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # 2. Pygfx Setup
        self.canvas = RenderCanvas(size=(WIDTH, HEIGHT), title="Psychedelic pygfx Canvas")
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)
        self.scene = gfx.Scene()

        # Camera and Light
        self.camera = gfx.OrthographicCamera(WIDTH / 10, HEIGHT / 10)
        self.camera.local.position = (0, 0, 100)
        self.camera.look_at((0, 0, 0))
        
        # Add a light for mesh surface details
        self.scene.add(gfx.AmbientLight("#444"))
        directional_light = gfx.DirectionalLight("#fff", 1.0)
        directional_light.local.position = (0, 0, 100)
        self.scene.add(directional_light)

        # 3. Mesh Setup
        # Background: Large plane to fill window
        self.bg_geometry = gfx.plane_geometry(WIDTH / 10, HEIGHT / 10, GRID_SIZE[0], GRID_SIZE[1])
        
        # Foreground: Small plane to follow face
        self.fg_geometry = gfx.plane_geometry(WIDTH / 40, WIDTH / 40, 40, 40)
        
        # Initial texture (shared)
        placeholder = np.zeros((720, 1280, 4), dtype=np.uint8)
        self.texture = gfx.Texture(placeholder, dim=2)
        
        # Materials
        self.bg_material = gfx.MeshPhongMaterial(map=self.texture)
        self.fg_material = gfx.MeshPhongMaterial(map=self.texture, opacity=0.9)
        
        # Meshes
        self.bg_mesh = gfx.Mesh(self.bg_geometry, self.bg_material)
        self.fg_mesh = gfx.Mesh(self.fg_geometry, self.fg_material)
        
        self.scene.add(self.bg_mesh)
        self.scene.add(self.fg_mesh)
        
        # Move foreground slightly forward to avoid Z-fighting
        self.fg_mesh.local.position = (0, 0, 1)

        # 4. Event Handling
        self.canvas.add_event_handler(self.on_event, "key_down", "resize")
        
        # Initial Fit to background
        self.camera.show_object(self.bg_mesh)

        # 4. MediaPipe Setup
        self.hand_tracker = HandTracker(max_num_hands=2) if HandTracker else None
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(refine_landmarks=True)

        # 5. State
        self.start_time = time.time()
        self.hand_data = [] # List of dicts with {pos, finger_count, tips, velocity}
        self.face_pos = (0, 0) # Face center normalized
        self.mouth_ratio = 0.0
        self.hue_shift = 0.0
        self.last_hand_pos = [] # For velocity tracking

    def update_texture(self, frame_bgr):
        # Flip and convert to RGBA for pygfx
        frame = cv2.flip(frame_bgr, 1)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        
        # Update texture content
        self.texture.data[:] = frame_rgb
        self.texture.update_range((0, 0, 0), self.texture.size)
        
        return frame

    def process_interactions(self, frame_bgr):
        # Hand tracking (Expects BGR)
        if self.hand_tracker:
            self.hand_tracker.find_hands(frame_bgr, draw=False)
            self.hand_data = []
            if self.hand_tracker.results and self.hand_tracker.results.multi_hand_landmarks:
                for i, hand_lms in enumerate(self.hand_tracker.results.multi_hand_landmarks):
                    lm_list = self.hand_tracker.get_landmark_positions(frame_bgr, i)
                    if not lm_list: continue

                    # Use palm center (Landmark 9)
                    cx = hand_lms.landmark[9].x * 2.0 - 1.0 # -1 to 1
                    cy = -(hand_lms.landmark[9].y * 2.0 - 1.0) # -1 to 1
                    
                    # Finger counting logic
                    fingers = []
                    # Thumb
                    if lm_list[4][1] > lm_list[3][1]: fingers.append(1)
                    else: fingers.append(0)
                    # 4 Fingers
                    tips = [8, 12, 16, 20]
                    pips = [6, 10, 14, 18]
                    for t, p in zip(tips, pips):
                        if lm_list[t][2] < lm_list[p][2]: fingers.append(1)
                        else: fingers.append(0)
                    
                    finger_count = sum(fingers)
                    
                    # Tip positions (normalized)
                    tip_positions = []
                    for t_id in [4, 8, 12, 16, 20]:
                        tx = hand_lms.landmark[t_id].x * 2.0 - 1.0
                        ty = -(hand_lms.landmark[t_id].y * 2.0 - 1.0)
                        tip_positions.append((tx, ty))

                    self.hand_data.append({
                        "pos": (cx, cy),
                        "count": finger_count,
                        "tips": tip_positions,
                        "fingers": fingers
                    })

        # Face tracking (Expects RGB/RGBA)
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        face_results = self.face_mesh.process(frame_rgb)
        if face_results.multi_face_landmarks:
            face = face_results.multi_face_landmarks[0]
            # Simple mouth open calculation
            u = face.landmark[13].y
            l = face.landmark[14].y
            self.mouth_ratio = max(0, min(1.0, (l - u) * 8.0)) # Normalized 0-1
            
            # Update face position
            nose = face.landmark[1]
            self.face_pos = (nose.x * 2.0 - 1.0, -(nose.y * 2.0 - 1.0))

    def on_event(self, event):
        etype = event.get("event_type")
        if etype == "key_down":
            key = event.get("key", "")
            if key.lower() == "q" or key == "Escape":
                print("Exiting...")
                loop.stop()
        elif etype == "resize":
            # Adjust camera to fit the background mesh perfectly when window resized
            self.camera.show_object(self.bg_mesh)

    def animate(self):
        elapsed = time.time() - self.start_time
        
        # Capture frame
        ret, frame_bgr = self.cap.read()
        if not ret:
            return

        # Resize to match expected texture size
        frame_bgr = cv2.resize(frame_bgr, (WIDTH, HEIGHT))
        
        # Update trackers
        self.process_interactions(frame_bgr)
        self.update_texture(frame_bgr)

        # --- Psychedelic Effects logic ---
        # 1. Mesh Deformation (Background only)
        positions = self.bg_geometry.positions.data
        grid_w, grid_h = GRID_SIZE
        
        freq = 3.3
        amp = 3.0 + self.mouth_ratio * 10.0
        
        x_coords = positions[:, 0] / (WIDTH / 20)
        y_coords = positions[:, 1] / (HEIGHT / 20)
        
        # Time-based waving with more complexity
        z_wave = np.sin(x_coords * freq + elapsed * 2.5) * np.cos(y_coords * freq * 0.8 + elapsed * 2.0) * amp
        z_wave += np.sin(x_coords * freq * 2.0 - elapsed * 1.5) * 2.0 # Extra turbulence
        
        # Add mouth-based ripple (global on background)
        z_wave += self.mouth_ratio * np.sin(np.sqrt(x_coords**2 + y_coords**2) * 8.0 - elapsed * 12.0) * 12.0
        
        # 2. Hand Gesture Based Visual Patterns
        for hand in self.hand_data:
            hx, hy = hand["pos"]
            count = hand["count"]
            tips = hand["tips"]
            
            # Distance to hand center
            dist_sq = (x_coords - hx)**2 + (y_coords - hy)**2
            
            if count == 0: # Black Hole - Sucking in (Negative displacement)
                z_wave -= np.exp(-dist_sq * 15.0) * 20.0
            
            elif count == 1: # Vortex - Twisting (Spiral wave)
                angle = np.arctan2(y_coords - hy, x_coords - hx)
                dist = np.sqrt(dist_sq)
                z_wave += np.sin(angle * 3.0 + dist * 10.0 - elapsed * 5.0) * np.exp(-dist_sq * 12.0) * 10.0
            
            elif count == 2: # Split - Wave tearing apart
                dx = x_coords - hx
                dy = y_coords - hy
                split_wave = np.sin(dx * 15.0 - elapsed * 8.0) * np.exp(-dist_sq * 5.0) * 15.0
                z_wave += split_wave
                
            elif count >= 4: # Solar Flare / Power Burst
                for tx, ty in tips:
                    t_dist_sq = (x_coords - tx)**2 + (y_coords - ty)**2
                    z_wave += np.exp(-t_dist_sq * 30.0) * 12.0 # Sharp peaks at tips
                # Explosion wave
                z_wave += np.sin(np.sqrt(dist_sq) * 15.0 - elapsed * 20.0) * np.exp(-dist_sq * 2.0) * 8.0

            else: # Standard Interaction
                z_wave += np.exp(-dist_sq * 10.0) * 12.0

        # Apply to Z channel
        positions[:, 2] = z_wave
        self.bg_geometry.positions.update_range(0, len(positions))

        # 2. Color Shifting (Psychedelic)
        r = (math.sin(elapsed * 1.0) + 1) / 2
        g = (math.sin(elapsed * 1.2 + 2) + 1) / 2
        b = (math.sin(elapsed * 1.4 + 4) + 1) / 2
        tint = (r, g, b, 1.0)
        self.bg_material.color = tint
        self.bg_material.emissive = (r * 0.3, g * 0.3, b * 0.3, 1.0)
        self.fg_material.color = (1, 1, 1, 1) # Keep face clearer

        # 3. Dynamic Rotation (Mouth linked BACKGROUND rotation)
        # 360 degrees = 2 * PI
        rotation_angle = self.mouth_ratio * 2.0 * math.pi
        self.bg_mesh.local.rotation = la.quat_from_euler((0, 0, rotation_angle))
        
        # 4. Foreground (Face) Following
        # Sync foreground position with face detected position
        self.fg_mesh.local.position = (self.face_pos[0] * (WIDTH/20), self.face_pos[1] * (HEIGHT/20), 5)
        
        # Subtle face wobble
        self.fg_mesh.local.rotation = la.quat_from_euler((
            math.sin(elapsed * 1.0) * 0.05,
            math.cos(elapsed * 1.2) * 0.05,
            0
        ))

        # Render
        self.renderer.render(self.scene, self.camera)
        self.canvas.request_draw()

    def run(self):
        self.canvas.request_draw(self.animate)
        loop.run()
        # Cleanup
        self.cap.release()

if __name__ == "__main__":
    app = PsychedelicApp()
    app.run()
