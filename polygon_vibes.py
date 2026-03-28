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
import os
import time
import math
import random
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np
import wgpu
import display_utils
from rendercanvas.auto import RenderCanvas, loop
import pygfx as gfx
import pylinalg as la
import colorsys

# ==================== Constants ====================
_DU_W, _DU_H, _DU_X, _DU_Y = display_utils.get_second_monitor_size()
WINDOW_WIDTH = _DU_W
WINDOW_HEIGHT = _DU_H
GRID_W = 40
GRID_H = 30

class PolygonVibesApp:
    def __init__(self):
        # 1. Setup pygfx
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="Polygon Vibes 3D")
        display_utils.setup_rendercanvas_fullscreen(self.canvas)
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)
        self.scene = gfx.Scene()
        
        self.camera = gfx.PerspectiveCamera(70, 16 / 9)
        self.camera.local.z = 1200
        
        # Add Lights
        self.ambient_light = gfx.AmbientLight("#ffffff", 0.2)
        self.scene.add(self.ambient_light)
        
        self.directional_light = gfx.DirectionalLight("#ffffff", 0.8)
        self.directional_light.local.position = (500, 1000, 1000)
        self.directional_light.cast_shadow = True
        self.scene.add(self.directional_light)
        
        self.point_light = gfx.PointLight("#ffaa00", 2.0)
        self.point_light.local.position = (0, 0, 500)
        self.scene.add(self.point_light)
        
        # 2. MediaPipe Tasks API Setup
        
        # Verify model paths
        hand_model_path = display_utils.resolve_model_path(
            "models/hand_landmarker.task",
            "test/models/hand_landmarker.task",
        )
        seg_model_path = display_utils.resolve_model_path(
            "models/selfie_segmenter.tflite",
            "test/models/selfie_segmenter.tflite",
        )
        
        if not display_utils.is_valid_model_asset(hand_model_path):
            print(f"Warning: Hand model not found at {hand_model_path}")
        if not display_utils.is_valid_model_asset(seg_model_path):
            print(f"Warning: Segmentation model missing or invalid at {seg_model_path}")

        # Hands
        self.detector = None
        if display_utils.is_valid_model_asset(hand_model_path):
            base_options = python.BaseOptions(model_asset_path=hand_model_path)
            options = vision.HandLandmarkerOptions(
                base_options=base_options,
                num_hands=2,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                running_mode=vision.RunningMode.VIDEO)
            self.detector = vision.HandLandmarker.create_from_options(options)
        
        # Segmentation
        try:
            if display_utils.is_valid_model_asset(seg_model_path):
                seg_base_options = python.BaseOptions(model_asset_path=seg_model_path)
                seg_options = vision.ImageSegmenterOptions(
                    base_options=seg_base_options,
                    running_mode=vision.RunningMode.VIDEO,
                    output_category_mask=True)
                self.segmenter = vision.ImageSegmenter.create_from_options(seg_options)
                self.segmentation_enabled = True
            else:
                self.segmenter = None
                self.segmentation_enabled = False
        except Exception as e:
            print(f"Segmentation init failed: {e}")
            self.segmentation_enabled = False

        # 3. Camera
        self.cap = display_utils.open_camera()
        if not self.cap.isOpened():
             print("Camera 2 failed, trying 0...")
             self.cap = display_utils.open_camera()
             
        self.camera_frame_width, self.camera_frame_height = display_utils.get_camera_frame_size(self.cap)
        
        # 4. Create Scenes
        self.create_background_mesh()
        self.create_foreground_plane()
        
        # Control State
        self.shake_amp = 0.0
        self.base_color_hue = 0.0
        self.point_light_target = np.array([0, 0, 500], dtype=np.float32)
        
        # Random phases for shake (per vertex)
        n_verts = self.bg_geo.positions.nitems
        self.shake_phases = np.random.uniform(0, 2*np.pi, (n_verts, 1)).astype(np.float32)
        # Random directions for shake (normalized)
        dirs = np.random.uniform(-1, 1, (n_verts, 3)).astype(np.float32)
        norms = np.linalg.norm(dirs, axis=1, keepdims=True)
        self.shake_dirs = dirs / (norms + 1e-6)
        
        self.start_time = time.time()
        
        # 5. Event Handling
        self.canvas.add_event_handler(self.on_event, "key_down")

    def on_event(self, event):
        etype = event.get("event_type")
        if etype == "key_down":
            key = event.get("key", "")
            if key.lower() == "q" or key == "Escape":
                print("Exiting...")
                loop.stop()

    def create_background_mesh(self):
        self.bg_geo = gfx.plane_geometry(3000, 2200, GRID_W, GRID_H)
        self.bg_positions_base = self.bg_geo.positions.data.copy()
        
        n_vertices = self.bg_geo.positions.nitems
        colors = np.ones((n_vertices, 4), dtype=np.float32)
        self.bg_geo.colors = gfx.Buffer(colors)
        
        self.bg_material = gfx.MeshPhongMaterial(
            shininess=30,
            specular=0.4,
            flat_shading=True
        )
        
        self.bg_mesh = gfx.Mesh(self.bg_geo, self.bg_material)
        self.bg_mesh.local.z = -500
        self.bg_mesh.local.rotation = la.quat_from_euler((-0.2, 0, 0)) 
        
        self.scene.add(self.bg_mesh)
        
        self.wire_material = gfx.MeshBasicMaterial(color=(1.0, 1.0, 1.0, 0.15), wireframe=True)
        self.bg_wire = gfx.Mesh(self.bg_geo, self.wire_material)
        self.bg_wire.local.z = -490 
        self.bg_wire.local.rotation = self.bg_mesh.local.rotation
        
        self.scene.add(self.bg_wire)

        # UI Overlay Setup
        self.ui_scene = gfx.Scene()
        self.ui_camera = gfx.OrthographicCamera(self.camera_frame_width, self.camera_frame_height)
        
        # Texture for raw camera feed
        self.raw_cam_tex = gfx.Texture(
            np.zeros((self.camera_frame_height, self.camera_frame_width, 4), dtype=np.uint8),
            dim=2,
        )
        self.ui_plane = gfx.Mesh(
            gfx.plane_geometry(self.camera_frame_width, self.camera_frame_height),
            gfx.MeshBasicMaterial(map=self.raw_cam_tex)
        )
        self.ui_scene.add(self.ui_plane)

    def create_foreground_plane(self):
        self.fg_tex = gfx.Texture(
            np.zeros((self.camera_frame_height, self.camera_frame_width, 4), dtype=np.uint8),
            dim=2,
        )
        material = gfx.MeshBasicMaterial(map=self.fg_tex)
        fg_height = 1600 * (self.camera_frame_height / max(self.camera_frame_width, 1))
        self.fg_plane = gfx.Mesh(gfx.plane_geometry(1600, fg_height), material)
        self.fg_plane.local.z = 100
        self.scene.add(self.fg_plane)
    
    def process_hands(self, mp_image, timestamp_ms):
        if self.detector is None:
            return 0.05, 0.0, None, []
        result = self.detector.detect_for_video(mp_image, timestamp_ms)
        
        shake_param = 0.05
        color_param = 0.0
        light_pos = None
        hand_points_world = []
        
        if result.hand_landmarks:
            for i, hand_landmarks in enumerate(result.hand_landmarks):
                handedness_cat = result.handedness[i][0].category_name
                wrist = hand_landmarks[0]
                index_tip = hand_landmarks[8]
                
                wx = (index_tip.x - 0.5) * 2000
                wy = -(index_tip.y - 0.5) * 1500
                
                # Transform to Grid Space (approx 3000x2200)
                points = []
                for lm in hand_landmarks:
                    px = (lm.x - 0.5) * 3000 
                    py = -(lm.y - 0.5) * 2200 
                    points.append([px, py])
                hand_points_world.append(np.array(points, dtype=np.float32))
                
                if handedness_cat == "Right": # User's Left Hand
                    shake_param = max(0.1, (1.0 - wrist.y) * 2.0)
                    light_pos = (wx, wy, 400)
                    
                elif handedness_cat == "Left": # User's Right Hand
                    color_param = wrist.x
                    
        return shake_param, color_param, light_pos, hand_points_world

    def animate(self):
        ret, frame = self.cap.read()
        if not ret: return
        
        timestamp_ms = int((time.time() - self.start_time) * 1000)
        
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        
        # 1. Process Hands
        target_shake, target_color, target_light, hand_points = self.process_hands(mp_image, timestamp_ms)
        
        self.shake_amp = self.shake_amp * 0.9 + (target_shake * 120.0) * 0.1
        self.base_color_hue = self.base_color_hue * 0.9 + target_color * 0.1
        
        if target_light:
            self.point_light_target = np.array(target_light, dtype=np.float32)
        
        current_pos = np.array(self.point_light.local.position)
        new_pos = current_pos * 0.85 + self.point_light_target * 0.15
        self.point_light.local.position = tuple(new_pos)
        
        # Update Raw Camera Texture (UI)
        rgba_raw = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        self.raw_cam_tex.data[:] = rgba_raw
        self.raw_cam_tex.update_range((0,0,0), self.raw_cam_tex.size)
        
        # 2. Process Segmentation
        mask = None
        if self.segmentation_enabled:
            seg_result = self.segmenter.segment_for_video(mp_image, timestamp_ms)
            if seg_result.category_mask:
                mask_np = seg_result.category_mask.numpy_view()
                mask = (mask_np > 0.5).astype(np.uint8) * 255
            elif seg_result.confidence_masks:
                  mask_np = seg_result.confidence_masks[0].numpy_view()
                  mask = (mask_np > 0.5).astype(np.uint8) * 255
        
        # 3. Update Foreground
        if mask is not None:
             rgba = rgba_raw.copy()
             rgba[:, :, 3] = mask
             self.fg_tex.data[:] = rgba
        else:
             self.fg_tex.data[:] = 0
             
        self.fg_tex.update_range((0,0,0), self.fg_tex.size)
        
        # 4. Update Background
        t = time.time() - self.start_time
        
        ref_x = self.bg_positions_base[:, 0] / 800.0
        ref_y = self.bg_positions_base[:, 1] / 800.0
        
        wave1 = np.sin(ref_x * 3.0 + t * 0.5) * np.cos(ref_y * 2.5 + t * 0.3) * 100.0
        dist = np.sqrt(ref_x**2 + ref_y**2)
        ripple = np.sin(dist * 10.0 - t * 5.0) * self.shake_amp
        noise = np.sin(t * 10.0 + self.shake_phases[:, 0]) * (self.shake_amp * 0.2)
        
        # Hand Interaction
        hand_influence = np.zeros_like(ref_x)
        v_px = self.bg_positions_base[:, 0]
        v_py = self.bg_positions_base[:, 1]
        
        if hand_points:
            for hand_lm_arr in hand_points:
                # Need to reshape for broadcasting
                # v_px is (N,), hand_lm_arr is (21, 2)
                
                # Expand dims
                # v_px: (N, 1)
                # hand_x: (1, 21)
                dx = v_px[:, np.newaxis] - hand_lm_arr[:, 0]
                dy = v_py[:, np.newaxis] - hand_lm_arr[:, 1]
                d2 = dx**2 + dy**2
                
                sigma2 = 200.0**2 
                strength = 250.0 
                
                force = strength * np.exp(-d2 / sigma2)
                # Max force from any joint of this hand
                hand_influence += np.max(force, axis=1)

        z_offsets = wave1 + ripple + noise + hand_influence
        self.bg_geo.positions.data[:, 2] = self.bg_positions_base[:, 2] + z_offsets
        self.bg_geo.positions.update_range()
        
        # Colors
        norm_h = (z_offsets + 150) / 450.0
        norm_h = np.clip(norm_h, 0, 1)
        
        hue = (self.base_color_hue + t * 0.1 + norm_h * 0.2) % 1.0
        val = 0.6 + 0.4 * norm_h 
        
        p = hue * 6.28318 
        r = 0.5 + 0.5 * np.cos(p)
        g = 0.5 + 0.5 * np.cos(p + 2.09) 
        b = 0.5 + 0.5 * np.cos(p + 4.18) 
        
        r *= val
        g *= val
        b *= val
        
        new_colors = np.stack([r, g, b, np.ones_like(r)], axis=1).astype(np.float32)
        self.bg_geo.colors.data[:] = new_colors
        self.bg_geo.colors.update_range()
        
        # 5. Render
        # Main Scene (full clear default)
        try:
            self.renderer.render(self.scene, self.camera, flush=False)
        except RuntimeError:
            pass
        
        # UI Overlay
        ui_w, ui_h = 320, 240
        padding = 0
        # Position at the top-right corner
        x = WINDOW_WIDTH - ui_w - padding
        y = padding
        
        # Draw overlay on top without clearing color
        try:
            self.renderer.render(self.ui_scene, self.ui_camera, rect=(x, y, ui_w, ui_h), clear=False)
        except RuntimeError:
            pass
        
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
        segmenter = getattr(self, "segmenter", None)
        if segmenter is not None and hasattr(segmenter, "close"):
            segmenter.close()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = PolygonVibesApp()
    try:
        app.run()
    finally:
        app.cleanup()
