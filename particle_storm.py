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
import time
import math
import random
import os
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np
import wgpu
from rendercanvas.auto import RenderCanvas, loop
import pygfx as gfx
import pylinalg as la

# ==================== Constants ====================
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 960
NUM_PARTICLES = 15000
WORLD_SCALE = 1000
ATTRACTION_STRENGTH = 450000.0 # Force towards/away from hand
DAMPING = 0.95                 # Velocity damping
NOISE_STRENGTH = 10.0          # Random movement
REPULSION_STRENGTH = 300000.0  # Force for explosion
EXPLOSION_THRESHOLD = 0.22      # Hand openness threshold for explosion

class ParticleStormApp:
    def __init__(self):
        # 1. Setup pygfx
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="Particle Storm 3D")
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)
        self.scene = gfx.Scene()
        
        # Camera
        self.camera = gfx.PerspectiveCamera(70, 16 / 9)
        self.camera.local.z = 1200
        
        # Lights (Optional for Points but good for scene)
        self.scene.add(gfx.AmbientLight("#101010", 1.0))

        # 2. MediaPipe Setup
        cwd = os.getcwd()
        # Assuming models are in test/models based on previous file inspection
        model_path = os.path.join(cwd, "test/models/hand_landmarker.task")
        
        if not os.path.exists(model_path):
             print(f"Warning: Model not found at {model_path}")

        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            running_mode=vision.RunningMode.VIDEO
        )
        self.detector = vision.HandLandmarker.create_from_options(options)

        # 3. Camera Setup
        self.cap = cv2.VideoCapture(2) # Default to 0, or 2 if user has setup
        if not self.cap.isOpened():
             self.cap = cv2.VideoCapture(2)
             if not self.cap.isOpened():
                 print("Error: No camera found on index 0 or 2.")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # 4. Particle System Initialization
        self.init_particles()
        
        # 5. Hand State
        self.hand_data = [] # List of {'pos': np.array, 'gest': float} where gest: 1.0 (attract) or -1.5 (explode)
        
        # 6. Time Tracking
        self.start_time = time.time()
        self.last_time = time.time()

        # 7. UI Overlay for Camera Feed (Bottom-Right or Top-Right)
        self.ui_scene = gfx.Scene()
        self.ui_camera = gfx.OrthographicCamera(640, 480)
        self.cam_tex = gfx.Texture(np.zeros((480, 640, 4), dtype=np.uint8), dim=2)
        self.ui_plane = gfx.Mesh(
            gfx.plane_geometry(640, 480),
            gfx.MeshBasicMaterial(map=self.cam_tex)
        )
        # Position UI? Maybe full background or small pip?
        # Let's do small PIP in bottom-right for debug/feedback
        self.ui_scene.add(self.ui_plane)

        # Event Handling
        self.canvas.add_event_handler(self.on_event, "key_down")

    def init_particles(self):
        # Positions: Random cube/sphere
        pos = (np.random.rand(NUM_PARTICLES, 3) - 0.5) * (WORLD_SCALE * 2)
        self.positions = pos.astype(np.float32)
        
        # Velocities
        self.velocities = np.zeros((NUM_PARTICLES, 3), dtype=np.float32)
        
        # Colors: Initialize as white/cyan
        self.colors = np.ones((NUM_PARTICLES, 4), dtype=np.float32)
        self.colors[:, 0] = 0.0 # R
        self.colors[:, 1] = 1.0 # G
        self.colors[:, 2] = 1.0 # B
        self.colors[:, 3] = 0.8 # Alpha
        
        # Sizes
        self.sizes = np.random.rand(NUM_PARTICLES).astype(np.float32) * 15.0 + 2.0
        
        # Geometry
        self.geometry = gfx.Geometry(positions=self.positions, colors=self.colors, sizes=self.sizes)
        
        # Soft Texture for "Glow"
        self.particle_tex = self.create_soft_particle_texture()
        
        # Material
        self.material = gfx.PointsMaterial(
            size=15, # Larger for glow
            size_space="world",
            color_mode="vertex",
            map=self.particle_tex,
            # map_interpolation="linear" # Removed
        )
        
        self.points = gfx.Points(self.geometry, self.material)
        self.scene.add(self.points)

        # Background Grid for Depth (Removed)
        # self.grid = gfx.GridHelper(size=4000, thickness=2.0, color1="#444444", color2="#444444")
        # self.grid.local.rotation = la.quat_from_euler((-1.57, 0, 0)) # Lie flat
        # self.scene.add(self.grid)
        
        # Hand Cursors (Visual Feedback)
        self.cursors = []
        cursor_geo = gfx.sphere_geometry(20)
        for _ in range(2):
            cursor_mat = gfx.MeshBasicMaterial(color="#ff0044")
            mesh = gfx.Mesh(cursor_geo, cursor_mat)
            mesh.visible = False
            self.scene.add(mesh)
            self.cursors.append(mesh)

    def create_soft_particle_texture(self):
        size = 64
        # Create float32 RGBA
        tex_data = np.zeros((size, size, 4), dtype=np.float32)
        center = (size - 1) / 2.0
        y, x = np.ogrid[:size, :size]
        dist = np.sqrt((x - center)**2 + (y - center)**2)
        mask = dist <= center
        
        # Cubic falloff
        norm_dist = dist / center
        alpha = np.clip(1.0 - norm_dist, 0, 1) ** 3
        
        tex_data[mask, 0] = 1.0
        tex_data[mask, 1] = 1.0
        tex_data[mask, 2] = 1.0
        tex_data[mask, 3] = alpha[mask]
        
        return gfx.Texture(tex_data, dim=2)


    def on_event(self, event):
        if event["event_type"] == "key_down":
            if event["key"] in ["q", "Escape"]:
                loop.stop()

    def update_physics(self, dt):
        # 1. Base Noise/Drift
        # Simple Brownian motion or curl-like noise
        noise = (np.random.rand(NUM_PARTICLES, 3) - 0.5) * NOISE_STRENGTH
        
        # 2. Hand Interaction
        forces = np.zeros_like(self.positions)
        min_dists = np.full(NUM_PARTICLES, 2000.0, dtype=np.float32)
        
        if self.hand_data:
            for h_info in self.hand_data:
                h_pos = h_info['pos']
                h_gest = h_info['gest'] # 1.0 for pull, -x for push
                
                # Vector from particle to hand
                delta = h_pos - self.positions
                dist_sq = np.sum(delta**2, axis=1) + 1000.0 
                dist = np.sqrt(dist_sq)
                min_dists = np.minimum(min_dists, dist)
                
                dir_vec = delta / dist[:, np.newaxis]
                
                # Force magnitude
                if h_gest > 0:
                    # Attraction
                    strength = ATTRACTION_STRENGTH / (dist + 200.0) 
                    forces += dir_vec * strength[:, np.newaxis]
                else:
                    # Explosion (Repulsion)
                    # Use a stronger, shorter range force for "explosion"
                    strength = (REPULSION_STRENGTH / (dist + 50.0)) * abs(h_gest)
                    forces -= dir_vec * strength[:, np.newaxis]

        # Apply Force
        self.velocities += (forces + noise) * dt
        
        # Damping
        self.velocities *= DAMPING
        
        # Update Positions
        self.positions += self.velocities * dt
        
        # Bounds check
        limit = 1500
        mask_out = np.abs(self.positions) > limit
        self.positions[mask_out] *= -0.9 
        
        # Updating Geometry
        self.geometry.positions.data[:] = self.positions
        self.geometry.positions.update_range()
        
        # Update Colors based on x, y, z coordinates
        # Map world space -1500...1500 to 0...1
        limit = 1500
        norm_pos = np.clip((self.positions / limit) * 0.5 + 0.5, 0, 1)
        
        self.colors[:, 0] = norm_pos[:, 0] # X -> R
        self.colors[:, 1] = norm_pos[:, 1] # Y -> G
        self.colors[:, 2] = norm_pos[:, 2] # Z -> B
        
        # Alpha: Smoothly transition based on proximity to hand
        norm_dist = np.clip(min_dists / 1000.0, 0, 1)
        self.colors[:, 3] = 0.9 - norm_dist * 0.4 # More opaque when near hand
        
        self.geometry.colors.data[:] = self.colors
        self.geometry.colors.update_range()


    def analyze_hands(self, result):
        self.hand_data = []
        
        # Reset visibility
        for c in self.cursors:
            c.visible = False

        if result.hand_landmarks:
            for i, hand_lms in enumerate(result.hand_landmarks):
                # 1. Position Calculation
                wrist = hand_lms[0]
                middle = hand_lms[9]
                
                cx = (wrist.x + middle.x) / 2
                cy = (wrist.y + middle.y) / 2
                cz = (wrist.z + middle.z) / 2
                
                wx = (cx - 0.5) * 1400
                wy = -(cy - 0.5) * 1000 
                wz = -(cz) * 1000 
                
                # 2. Gesture Detection (Openness)
                # Check distance of fingertips from wrist
                tips_indices = [8, 12, 16, 20]
                total_dist = 0
                for tip_idx in tips_indices:
                    t = hand_lms[tip_idx]
                    d = math.sqrt((t.x - wrist.x)**2 + (t.y - wrist.y)**2 + (t.z - wrist.z)**2)
                    total_dist += d
                avg_dist = total_dist / 4
                
                # If avg_dist is large -> Hand is open -> Explode
                # If avg_dist is small -> Hand is fist/pinch -> Attract
                gesture_factor = 1.0 # Default attract
                if avg_dist > EXPLOSION_THRESHOLD:
                    gesture_factor = -2.0 # Explode strength multiplier
                
                pos = np.array([wx, wy, wz])
                self.hand_data.append({'pos': pos, 'gest': gesture_factor})
                
                # Update Cursor
                if i < len(self.cursors):
                    self.cursors[i].visible = True
                    self.cursors[i].local.position = (wx, wy, wz)
                    # Change cursor color based on state
                    if gesture_factor < 0:
                        self.cursors[i].material.color = "#00ffff" # Explode (Cyan)
                    else:
                        self.cursors[i].material.color = "#ff0044" # Attract (Red)


    def animate(self):
        dt = time.time() - self.last_time
        self.last_time = time.time()
        
        # Cap dt to avoid explosion on lag
        if dt > 0.1: dt = 0.1
        
        ret, frame = self.cap.read()
        if ret:
            # Prepare Image
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            
            # Detect
            timestamp_ms = int(time.time() * 1000)
            result = self.detector.detect_for_video(mp_img, timestamp_ms)
            
            # Analyze
            self.analyze_hands(result)
            
            # PIP Texture Update
            # Resize frame to match cam_tex size (640, 480)
            frame_resized = cv2.resize(frame, (640, 480))
            rgba = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGBA)
            self.cam_tex.data[:] = rgba
            self.cam_tex.update_range((0,0,0), self.cam_tex.size)

        # Physics
        self.update_physics(dt)
        
        # Render
        self.renderer.render(self.scene, self.camera, flush=False)
        
        # Draw PIP (Top Right)
        # Viewport: x, y, w, h
        pip_w, pip_h = 320, 240
        self.renderer.render(self.ui_scene, self.ui_camera, rect=(WINDOW_WIDTH - pip_w, 0, pip_w, pip_h), clear=False)
        
        self.canvas.request_draw()

    def run(self):
        self.canvas.request_draw(self.animate)
        loop.run()

if __name__ == "__main__":
    app = ParticleStormApp()
    app.run()
