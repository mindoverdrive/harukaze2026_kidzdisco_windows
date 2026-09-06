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
import atexit
from contextlib import ExitStack
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
import display_utils
from scene_control import notify_first_frame
from rendercanvas.auto import RenderCanvas, loop
import pygfx as gfx
import pylinalg as la

# ==================== Constants ====================
_DU_W, _DU_H, _DU_X, _DU_Y = display_utils.get_second_monitor_size()
WINDOW_WIDTH = _DU_W
WINDOW_HEIGHT = _DU_H
CAMERA_FOV = 70.0
NUM_PARTICLES = 40000
WORLD_SCALE = 1000
ATTRACTION_STRENGTH = 450000.0 # Force towards/away from hand
DAMPING = 0.95                 # Velocity damping
NOISE_STRENGTH = 10.0          # Random movement
REPULSION_STRENGTH = 300000.0  # Force for explosion
EXPLOSION_THRESHOLD = 0.22      # Hand openness threshold for explosion

class ParticleStormApp:
    def __init__(self):
        self._resources = ExitStack()
        atexit.register(self.cleanup)
        self._resources.callback(cv2.destroyAllWindows)
        # 1. Setup pygfx
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="Particle Storm 3D")
        self._resources.callback(self.canvas.close)
        display_utils.setup_rendercanvas_fullscreen(self.canvas)
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)
        self.scene = gfx.Scene()
        
        # Camera
        self.camera = gfx.PerspectiveCamera(CAMERA_FOV, WINDOW_WIDTH / max(1, WINDOW_HEIGHT))
        self.camera.local.z = 1200
        
        # Lights (Optional for Points but good for scene)
        self.scene.add(gfx.AmbientLight("#101010", 1.0))

        # 2. MediaPipe Setup
        model_path = display_utils.resolve_model_path(
            "models/hand_landmarker.task",
            "test/models/hand_landmarker.task",
        )
        
        if not display_utils.is_valid_model_asset(model_path):
             print(f"Warning: Model not found at {model_path}")
        self.detector = None
        if display_utils.is_valid_model_asset(model_path):
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
            self._resources.callback(self.detector.close)

        # 3. Camera Setup
        self.cap = display_utils.open_camera() # Default to 0, or 2 if user has setup
        if self.cap is not None:
            self._resources.callback(self.cap.release)
        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError("The shared camera could not be attached")
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # 4. Background camera feed and overlay cursors
        self.bg_scene = gfx.Scene()
        self.bg_camera = gfx.OrthographicCamera(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.bg_camera.local.z = 1
        self.cam_tex = gfx.Texture(np.zeros((WINDOW_HEIGHT, WINDOW_WIDTH, 4), dtype=np.uint8), dim=2)
        self.bg_plane = gfx.Mesh(
            gfx.plane_geometry(WINDOW_WIDTH, WINDOW_HEIGHT),
            gfx.MeshBasicMaterial(map=self.cam_tex, depth_write=False)
        )
        self.bg_plane.local.z = 0
        self.bg_scene.add(self.bg_plane)

        self.overlay_scene = gfx.Scene()
        self.overlay_camera = gfx.OrthographicCamera(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.overlay_camera.local.z = 100
        self.camera_layout = display_utils.get_uniform_layout(640, 480, WINDOW_WIDTH, WINDOW_HEIGHT)

        # 5. Particle System Initialization
        self.init_particles()
        
        # 6. Hand State
        self.hand_data = [] # List of {'pos': np.array, 'gest': float} where gest: 1.0 (attract) or -1.5 (explode)
        
        # 7. Time Tracking
        self.start_time = time.monotonic()
        self.last_time = self.start_time
        self.last_timestamp = 0

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
        cursor_geo = gfx.sphere_geometry(18)
        for _ in range(2):
            cursor_mat = gfx.MeshBasicMaterial(color="#ff0044")
            mesh = gfx.Mesh(cursor_geo, cursor_mat)
            mesh.visible = False
            self.overlay_scene.add(mesh)
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

        # Hands steer only XY. Keep the 3D falloff above so XY strength and
        # proximity alpha are unchanged; depth retains its own noise/momentum.
        forces[:, 2] = 0.0

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


    def _stage_to_overlay(self, stage_x, stage_y):
        return (
            stage_x - WINDOW_WIDTH / 2.0,
            WINDOW_HEIGHT / 2.0 - stage_y,
        )

    def _landmark_to_world(self, landmark, camera_layout):
        stage_x, stage_y = display_utils.normalized_to_stage(landmark.x, landmark.y, camera_layout)
        norm_x = stage_x / float(WINDOW_WIDTH)
        norm_y = stage_y / float(WINDOW_HEIGHT)
        world_z = float(np.clip(-(landmark.z) * 1000.0, -700.0, 700.0))
        camera_z = float(self.camera.local.z)
        depth = max(1.0, camera_z - world_z)
        half_height = math.tan(math.radians(CAMERA_FOV) / 2.0) * depth
        half_width = half_height * (WINDOW_WIDTH / float(WINDOW_HEIGHT))
        world_x = (norm_x - 0.5) * 2.0 * half_width
        world_y = (0.5 - norm_y) * 2.0 * half_height
        return np.array([world_x, world_y, world_z], dtype=np.float32), (stage_x, stage_y)

    def analyze_hands(self, result, camera_layout):
        self.hand_data = []
        
        # Reset visibility
        for c in self.cursors:
            c.visible = False

        if result.hand_landmarks:
            for i, hand_lms in enumerate(result.hand_landmarks):
                # 1. Position Calculation
                wrist = hand_lms[0]
                index_tip = hand_lms[8]
                pos, screen_pos = self._landmark_to_world(index_tip, camera_layout)
                
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
                
                self.hand_data.append({'pos': pos, 'gest': gesture_factor, 'screen_pos': screen_pos})
                
                # Update Cursor
                if i < len(self.cursors):
                    self.cursors[i].visible = True
                    overlay_x, overlay_y = self._stage_to_overlay(*screen_pos)
                    self.cursors[i].local.position = (overlay_x, overlay_y, 0)
                    # Change cursor color based on state
                    if gesture_factor < 0:
                        self.cursors[i].material.color = "#00ffff" # Explode (Cyan)
                    else:
                        self.cursors[i].material.color = "#ff0044" # Attract (Red)


    def animate(self):
        now = time.monotonic()
        dt = now - self.last_time
        self.last_time = now
        
        # Cap dt to avoid explosion on lag
        if dt > 0.1: dt = 0.1
        
        ret, frame = self.cap.read()
        if ret:
            camera_frame, stage_frame, camera_layout = display_utils.prepare_camera_frame(frame, WINDOW_WIDTH, WINDOW_HEIGHT)
            self.camera_layout = camera_layout
            rgb = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            
            # Detect
            # VIDEO timestamps must increase even for frames within the same millisecond.
            timestamp_ms = max(int(now * 1000), self.last_timestamp + 1)
            self.last_timestamp = timestamp_ms
            if self.detector is not None:
                result = self.detector.detect_for_video(mp_img, timestamp_ms)
                self.analyze_hands(result, camera_layout)
            else:
                self.hand_data = []
                for c in self.cursors:
                    c.visible = False
            
            rgba = cv2.cvtColor(stage_frame, cv2.COLOR_BGR2RGBA)
            self.cam_tex.data[:] = rgba
            self.cam_tex.update_range((0,0,0), self.cam_tex.size)
        else:
            self.hand_data = []
            for c in self.cursors:
                c.visible = False

        # Physics
        self.update_physics(dt)
        
        # Render
        rendered = True
        try:
            self.renderer.render(self.bg_scene, self.bg_camera, flush=False)
        except RuntimeError:
            rendered = False
        
        try:
            self.renderer.render(self.scene, self.camera, clear=False, flush=False)
        except RuntimeError:
            rendered = False

        try:
            self.renderer.render(self.overlay_scene, self.overlay_camera, clear=False)
        except RuntimeError:
            rendered = False

        notify_first_frame(self.cap, frame_processed=bool(ret and rendered and self.detector is not None))
        
        self.canvas.request_draw()

    def run(self):
        self.canvas.request_draw(self.animate)
        loop.run()

    def cleanup(self):
        self._resources.close()

if __name__ == "__main__":
    app = ParticleStormApp()
    try:
        app.run()
    finally:
        app.cleanup()
