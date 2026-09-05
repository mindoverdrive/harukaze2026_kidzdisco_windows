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
NUM_PARTICLES = 45000
WORLD_SCALE = 800

# Physics Constants
RETURN_SPRING_STRENGTH = 4.0     # Force to return to Saturn shape (Increased for better shape retention)
DRAG_STRENGTH = 5.0              # Strength of pinch drag
FINGER_PULL_RADIUS = 300.0       # Radius of index finger influence
FINGER_PULL_STRENGTH = 1000.0    # Strength of index finger pull (Reduced)
DAMPING = 0.92                   # Velocity damping

# Saturn Shape Constants
PLANET_RADIUS = 250
RING_INNER_RADIUS = 350
RING_OUTER_RADIUS = 600
PLANET_PARTICLE_RATIO = 0.4      # 40% particles in planet, 60% in rings

class SaturnParticlesApp:
    def __init__(self):
        # 1. Setup pygfx
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="Saturn Particle Interaction")
        display_utils.setup_rendercanvas_fullscreen(self.canvas)
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)
        self.scene = gfx.Scene()
        
        # Camera
        self.camera = gfx.PerspectiveCamera(CAMERA_FOV, WINDOW_WIDTH / max(1, WINDOW_HEIGHT))
        self.camera.local.z = 1200

        self.background_z = -1600.0
        background_depth = float(self.camera.local.z - self.background_z)
        background_height = 2.0 * math.tan(math.radians(CAMERA_FOV) / 2.0) * background_depth
        background_width = background_height * (WINDOW_WIDTH / max(1.0, float(WINDOW_HEIGHT)))
        self.cam_tex = gfx.Texture(np.zeros((WINDOW_HEIGHT, WINDOW_WIDTH, 4), dtype=np.uint8), dim=2)
        self.bg_plane = gfx.Mesh(
            gfx.plane_geometry(background_width, background_height),
            gfx.MeshBasicMaterial(map=self.cam_tex)
        )
        self.bg_plane.local.position = (0, 0, self.background_z)
        self.scene.add(self.bg_plane)
        
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

        # 3. Camera Setup
        self.cap = display_utils.open_camera()
        if not self.cap.isOpened():
            self.cap = display_utils.open_camera()
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        self.camera_layout = display_utils.get_uniform_layout(640, 480, WINDOW_WIDTH, WINDOW_HEIGHT)

        # 4. Particle System Initialization
        self.init_particles()
        
        # 5. Interaction State
        self.hand_data_list = []  # List of hand data dicts
        
        # 6. Time Tracking
        self.last_time = time.time()
        self.last_timestamp = 0

        # Hand Cursors
        self.cursors = []
        cursor_geo = gfx.sphere_geometry(15)
        for _ in range(2):
            cursor_mat = gfx.MeshBasicMaterial(color="#00ff00")
            mesh = gfx.Mesh(cursor_geo, cursor_mat)
            mesh.visible = False
            self.scene.add(mesh)
            self.cursors.append(mesh)

        # Event Handling
        self.canvas.add_event_handler(self.on_event, "key_down")

    def init_particles(self):
        # --- PLANET ---
        count_planet = int(NUM_PARTICLES * PLANET_PARTICLE_RATIO)
        self.p_pos = np.zeros((count_planet, 3), dtype=np.float32)
        
        phi = np.random.uniform(0, 2 * np.pi, count_planet)
        costheta = np.random.uniform(-1, 1, count_planet)
        u = np.random.uniform(0, 1, count_planet)
        
        theta = np.arccos(costheta)
        r = PLANET_RADIUS * np.cbrt(u)
        
        self.p_pos[:, 0] = r * np.sin(theta) * np.cos(phi)
        self.p_pos[:, 1] = r * np.sin(theta) * np.sin(phi)
        self.p_pos[:, 2] = r * np.cos(theta)
        
        self.p_col = np.zeros((count_planet, 4), dtype=np.float32)
        self.p_col[:] = [0.8, 0.6, 0.3, 0.8]  # Golden
        
        self.p_orig_col = self.p_col.copy()
        self.p_target = self.p_pos.copy()
        self.p_vel = np.zeros((count_planet, 3), dtype=np.float32)
        self.p_sizes = np.random.uniform(2.0, 6.0, count_planet).astype(np.float32)

        self.planet_geo = gfx.Geometry(positions=self.p_pos, colors=self.p_col, sizes=self.p_sizes)
        self.planet_points = gfx.Points(self.planet_geo, gfx.PointsMaterial(size=5, size_space="world", color_mode="vertex"))
        self.scene.add(self.planet_points)

        # --- RINGS ---
        count_ring = NUM_PARTICLES - count_planet
        self.r_pos = np.zeros((count_ring, 3), dtype=np.float32)

        r_sq = np.random.uniform(RING_INNER_RADIUS**2, RING_OUTER_RADIUS**2, count_ring)
        r_ring = np.sqrt(r_sq)
        theta_ring = np.random.uniform(0, 2 * np.pi, count_ring)
        
        self.r_pos[:, 0] = r_ring * np.cos(theta_ring)
        self.r_pos[:, 1] = np.random.uniform(-5, 5, count_ring)
        self.r_pos[:, 2] = r_ring * np.sin(theta_ring)
        
        # Ring Tilt
        tilt_angle = np.radians(20)
        c, s = np.cos(tilt_angle), np.sin(tilt_angle)
        y = self.r_pos[:, 1] * c - self.r_pos[:, 2] * s
        z = self.r_pos[:, 1] * s + self.r_pos[:, 2] * c
        self.r_pos[:, 1] = y
        self.r_pos[:, 2] = z

        self.r_col = np.zeros((count_ring, 4), dtype=np.float32)
        self.r_col[:] = [0.9, 0.8, 0.6, 0.6]  # Beige

        self.r_orig_col = self.r_col.copy()
        self.r_target = self.r_pos.copy()
        self.r_vel = np.zeros((count_ring, 3), dtype=np.float32)
        self.r_sizes = np.random.uniform(2.0, 6.0, count_ring).astype(np.float32)

        self.ring_geo = gfx.Geometry(positions=self.r_pos, colors=self.r_col, sizes=self.r_sizes)
        self.ring_points = gfx.Points(self.ring_geo, gfx.PointsMaterial(size=5, size_space="world", color_mode="vertex"))
        self.scene.add(self.ring_points)

    def on_event(self, event):
        if event["event_type"] == "key_down":
            if event["key"] in ["q", "Escape"]:
                loop.stop()

    def _landmark_to_world(self, landmark, camera_layout):
        stage_x, stage_y = display_utils.normalized_to_stage(landmark.x, landmark.y, camera_layout)
        norm_x = stage_x / float(WINDOW_WIDTH)
        norm_y = stage_y / float(WINDOW_HEIGHT)
        world_z = float(np.clip(-(landmark.z) * 1200.0, -700.0, 700.0))
        camera_z = float(self.camera.local.z)
        depth = max(1.0, camera_z - world_z)
        half_height = math.tan(math.radians(CAMERA_FOV) / 2.0) * depth
        half_width = half_height * (WINDOW_WIDTH / float(WINDOW_HEIGHT))
        world_x = (norm_x - 0.5) * 2.0 * half_width
        world_y = (0.5 - norm_y) * 2.0 * half_height
        return np.array([world_x, world_y, world_z], dtype=np.float32), (stage_x, stage_y)

    def update_physics(self, dt):
        # Update Planet
        # Hand 0 controls Planet
        hand0 = self.hand_data_list[0] if len(self.hand_data_list) > 0 else None
        self._update_system(dt, self.p_pos, self.p_vel, self.p_col, self.p_orig_col, 
                            self.p_target, self.planet_points, hand0, rotation_speed=0.2)
        
        # Update Ring
        # Hand 1 controls Ring (if present), else no control
        hand1 = self.hand_data_list[1] if len(self.hand_data_list) > 1 else None
        self._update_system(dt, self.r_pos, self.r_vel, self.r_col, self.r_orig_col, 
                            self.r_target, self.ring_points, hand1, rotation_speed=-0.2)

    def _update_system(self, dt, pos, vel, col, orig_col, target, points_obj, hand_info, rotation_speed):
        forces = np.zeros_like(pos)
        
        # Rotation
        angle = time.time() * rotation_speed
        # Create rotation quaternion from Euler angles (y-axis rotation)
        # pylinalg.quat_from_euler expects (pitch, yaw, roll) -> (x, y, z)
        # We want Y-axis rotation
        rot_quat = la.quat_from_euler((0, angle, 0))
        points_obj.local.rotation = rot_quat
        
        # Interaction in World Space
        # Current world position of points is calculated by GPU, but for physics we simulate in Local Frame
        # effectively, because we apply rotation to the container.
        # BUT, to interact with World Hand, we need to transform Hand to Local Space
        # OR transform Particles to World Space.
        
        # Let's transform HAND to LOCAL SPACE.
        # Local Pos = InverseRotation * (WorldHandPos - WorldObjectPos)
        # Object is at (0,0,0) usually.
        
        if hand_info:
            h_pos_world = hand_info['index_tip']
            is_pinch = hand_info['pinch']
            openness = hand_info['openness']
            
            # Inverse Rotation
            # To invert a quaternion (x, y, z, w), we conjugate it (-x, -y, -z, w)
            # pylinalg quats are (x, y, z, w)
            q_inv = (rot_quat[0] * -1, rot_quat[1] * -1, rot_quat[2] * -1, rot_quat[3])
            
            # Rotate Hand Pos into Local Space
            # la.vec_transform_quat(vec, quat)
            h_pos_local = la.vec_transform_quat(h_pos_world, q_inv)
            
            # Vector from particle to hand (in Local Space)
            delta = h_pos_local - pos
            dist_sq = np.sum(delta**2, axis=1) + 1.0
            dist = np.sqrt(dist_sq)

            mask = dist < FINGER_PULL_RADIUS

            # Calculate Falloff based on hand distance from center (World Space)
            # h_pos_world is the index tip position
            hand_dist_center = np.linalg.norm(h_pos_world)
            FALLOFF_START = 400.0
            FALLOFF_END = 900.0
            falloff = 1.0 - (hand_dist_center - FALLOFF_START) / (FALLOFF_END - FALLOFF_START)
            falloff = np.clip(falloff, 0.0, 1.0)

            if is_pinch:
                # Pinch: drag 
                forces[mask] += delta[mask] * DRAG_STRENGTH * falloff
                # Red
                alpha = np.clip(1.0 - dist[mask] / FINGER_PULL_RADIUS, 0, 1)[:, np.newaxis] * falloff
                target_c = np.array([1.0, 0.2, 0.5, 1.0])
                col[mask] = col[mask] * (1 - alpha) + target_c * alpha
            else:
                # Pull
                pull_str = FINGER_PULL_STRENGTH * (1.0 - dist[mask] / FINGER_PULL_RADIUS) * falloff
                direction = delta[mask] / dist[mask, np.newaxis]
                forces[mask] += direction * pull_str[:, np.newaxis] * 5.0
                # Blue
                alpha = np.clip(1.0 - dist[mask] / FINGER_PULL_RADIUS, 0, 1)[:, np.newaxis] * falloff
                target_c = np.array([0.0, 0.8, 1.0, 1.0])
                col[mask] = col[mask] * (1 - alpha) + target_c * alpha

            # Convergence (Return Force)
            # If falloff is high (hand near), convergence depends on openness.
            # If falloff is low (hand far), convergence should be high (force return).
            # holding_strength: 1.0 = Strong Hold (Closed & Near), 0.0 = Release (Open OR Far)
            holding_strength = (1.0 if is_pinch else 0.0) * falloff
            
            # inverse of holding strength -> return strength
            convergence = 1.0 - holding_strength * 0.8 # Never go fully to 0 to keep some structure? 
            # Actually, if holding, we want convergence to be low (drag dominates).
            # If releasing, we want convergence high.
            
            delta_target = target - pos
            spring_force = delta_target * (RETURN_SPRING_STRENGTH * convergence)
            forces += spring_force
            
        else:
            # Return
            delta_target = target - pos
            forces += delta_target * RETURN_SPRING_STRENGTH

        # Integration
        vel += forces * dt
        vel *= DAMPING
        pos += vel * dt

        # Color Decay
        col[:] = col * 0.9 + orig_col * 0.1

        # Update Geometry
        points_obj.geometry.positions.data[:] = pos
        points_obj.geometry.positions.update_range()
        points_obj.geometry.colors.data[:] = col
        points_obj.geometry.colors.update_range()

    def detect_hands(self):
        ret, frame = self.cap.read()
        if not ret:
            self.hand_data_list = []
            for c in self.cursors:
                c.visible = False
            return
        
        try:
            camera_frame, stage_frame, camera_layout = display_utils.prepare_camera_frame(frame, WINDOW_WIDTH, WINDOW_HEIGHT)
            self.camera_layout = camera_layout
            frame_rgb = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB)
            frame_rgba = cv2.cvtColor(stage_frame, cv2.COLOR_BGR2RGBA)
            self.cam_tex.data[:] = frame_rgba
            self.cam_tex.update_range((0, 0, 0), self.cam_tex.size)
            
            # MediaPipe - ensure strictly increasing timestamp
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            timestamp = int(time.time() * 1000)
            if timestamp <= self.last_timestamp:
                timestamp = self.last_timestamp + 1
            self.last_timestamp = timestamp
            
            if self.detector is None:
                self.hand_data_list = []
                return

            result = self.detector.detect_for_video(mp_img, timestamp)
            
            # Reset
            self.hand_data_list = []
            for c in self.cursors:
                c.visible = False
            
            if result.hand_landmarks:
                # Sort hands by X coordinate to ensure consistent assignment?
                # Or just use detection order (usually consistent enough for casual use)
                # Let's use detection order.
                
                for i, hand_lms in enumerate(result.hand_landmarks):
                    if i >= 2: break # Max 2 hands
                    
                    wrist = hand_lms[0]
                    index_tip = hand_lms[8]
                    thumb_tip = hand_lms[4]
                    
                    # World Coords are derived from the visible camera position
                    index_world, screen_pos = self._landmark_to_world(index_tip, camera_layout)
                    
                    # Pinch Detection
                    pinch_dist = math.sqrt(
                        (index_tip.x - thumb_tip.x)**2 +
                        (index_tip.y - thumb_tip.y)**2
                    )
                    is_pinch = pinch_dist < 0.05
                    
                    # Openness
                    tips = [8, 12, 16, 20]
                    dists = []
                    for t in tips:
                        lm = hand_lms[t]
                        d = math.sqrt(
                            (lm.x - wrist.x)**2 +
                            (lm.y - wrist.y)**2 +
                            (lm.z - wrist.z)**2
                        )
                        dists.append(d)
                    avg_dist = sum(dists) / 4
                    openness = float(np.clip((avg_dist - 0.1) / 0.25, 0, 1))

                    hand_info = {
                        'index_tip': index_world,
                        'pinch': is_pinch,
                        'openness': openness,
                        'screen_pos': screen_pos,
                    }
                    self.hand_data_list.append(hand_info)
                    
                    # Update Cursor
                    if i < len(self.cursors):
                        self.cursors[i].visible = True
                        self.cursors[i].local.position = tuple(index_world)
                        col = "#ff0000" if is_pinch else "#00ff00"
                        
                        # Hand assignment color hint
                        if i == 0: # Planet
                            col = "#ffcc00" # Gold-ish
                        else: # Ring
                            col = "#00ccff" # Cyan-ish
                            
                        self.cursors[i].material.color = col

            return True

        except Exception as e:
            print(f"Hand detection error: {e}")

    def animate(self):
        try:
            dt = time.time() - self.last_time
            self.last_time = time.time()
            if dt < 0.001:
                dt = 0.001
            if dt > 0.1:
                dt = 0.1
            
            frame_processed = self.detect_hands()
            self.update_physics(dt)
            
            try:
                self.renderer.render(self.scene, self.camera)
            except RuntimeError:
                pass
            else:
                notify_first_frame(self.cap, frame_processed=bool(frame_processed))
            
            self.canvas.request_draw()
        except Exception as e:
            print(f"Animate error: {e}")
            self.canvas.request_draw()

    def run(self):
        self.canvas.request_draw(self.animate)
        loop.run()

    def cleanup(self):
        if getattr(self, "cap", None) is not None:
            self.cap.release()
        detector = getattr(self, "detector", None)
        if detector is not None and hasattr(detector, "close"):
            detector.close()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = SaturnParticlesApp()
    try:
        app.run()
    finally:
        app.cleanup()
