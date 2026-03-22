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
FACE_GRID_W = 200
FACE_GRID_H = 150
FACE_GRID_W = 40
FACE_GRID_H = 30
FACE_GRID_W = 200
FACE_GRID_H = 150
FACE_GRID_W = 40
FACE_GRID_H = 30
FACE_GRID_W = 200
FACE_GRID_H = 150
FACE_GRID_W = 40
FACE_GRID_H = 30
FACE_GRID_W = 200
FACE_GRID_H = 150
FACE_GRID_W = 40
FACE_GRID_H = 30
FACE_GRID_W = 200
FACE_GRID_H = 150
FACE_GRID_W = 40
FACE_GRID_H = 30
FACE_GRID_W = 200
FACE_GRID_H = 150
FACE_GRID_W = 40
FACE_GRID_H = 30
FACE_GRID_W = 200
FACE_GRID_H = 150
FACE_GRID_W = 40
FACE_GRID_H = 30
FACE_GRID_W = 200
FACE_GRID_H = 150

class PolygonVibesApp:
    def __init__(self):
        # 1. Setup pygfx
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="Polygon Vibes 3D (Face & Mouth Control)")
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
        face_model_path = display_utils.resolve_model_path("models/face_landmarker.task")
        seg_model_path = display_utils.resolve_model_path(
            "models/selfie_segmenter.tflite",
            "test/models/selfie_segmenter.tflite",
        )
        
        self.detector = None
        self.segmenter = None
        self.segmentation_enabled = False

        if not display_utils.is_valid_model_asset(face_model_path):
            print(f"Warning: Face model not found at {face_model_path}")
        if not display_utils.is_valid_model_asset(seg_model_path):
            print(f"Warning: Segmentation model missing or invalid at {seg_model_path}")

        # Faces (手の代わりに顔で検知)
        if display_utils.is_valid_model_asset(face_model_path):
            try:
                base_options = python.BaseOptions(model_asset_path=face_model_path)
                options = vision.FaceLandmarkerOptions(
                    base_options=base_options,
                    num_faces=1,
                    min_face_detection_confidence=0.5,
                    min_face_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                    running_mode=vision.RunningMode.VIDEO)
                self.detector = vision.FaceLandmarker.create_from_options(options)
            except Exception as e:
                print(f"Face landmarker init failed: {e}")

        # Segmentation
        if display_utils.is_valid_model_asset(seg_model_path):
            try:
                seg_base_options = python.BaseOptions(model_asset_path=seg_model_path)
                seg_options = vision.ImageSegmenterOptions(
                    base_options=seg_base_options,
                    running_mode=vision.RunningMode.VIDEO,
                    output_category_mask=True)
                self.segmenter = vision.ImageSegmenter.create_from_options(seg_options)
                self.segmentation_enabled = True
            except Exception as e:
                print(f"Segmentation init failed: {e}")
                self.segmentation_enabled = False

        # 3. Camera
        self.cap = display_utils.open_camera()
        if not self.cap.isOpened():
             print("Camera 2 failed, trying 1...")
             self.cap = display_utils.open_camera()
             
        self.camera_frame_width, self.camera_frame_height = display_utils.get_camera_frame_size(self.cap)
        
        # 4. Create Scenes
        self.create_background_mesh()
        self.create_foreground_plane()
        
        # Control State
        self.shake_amp = 0.0
        self.base_color_hue = 0.0
        self.mouth_openness = 0.0
        self.point_light_target = np.array([0, 0, 500], dtype=np.float32)
        
        # Random phases for shake (per vertex)
        n_verts = self.bg_geo.positions.nitems
        self.shake_phases = np.random.uniform(0, 2*np.pi, (n_verts, 1)).astype(np.float32)
        # Random directions for shake (normalized)
        dirs = np.random.uniform(-1, 1, (n_verts, 3)).astype(np.float32)
        norms = np.linalg.norm(dirs, axis=1, keepdims=True)
        self.shake_dirs = dirs / (norms + 1e-6)
        
        self.start_time = time.time()
        
        # 口の位置（波の発生源）
        self.mouth_pos = np.array([0.0, 0.0], dtype=np.float32)
        
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
        # Background Mesh (Low Res 40x30, Animated)
        self.bg_geo = gfx.plane_geometry(3000, 2200, GRID_W, GRID_H)
        self.bg_positions_base = self.bg_geo.positions.data.copy()
        
        n_vertices = self.bg_geo.positions.nitems
        colors = np.ones((n_vertices, 4), dtype=np.float32)
        self.bg_geo.colors = gfx.Buffer(colors)
        
        self.bg_material = gfx.MeshPhongMaterial(
            color_mode="vertex",
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

        # Face Mesh (High Res 200x150, No Wave Movement)
        self.face_geo = gfx.plane_geometry(3000, 2200, FACE_GRID_W, FACE_GRID_H)
        self.face_positions_base = self.face_geo.positions.data.copy()
        
        n_vertices_face = self.face_geo.positions.nitems
        colors_face = np.zeros((n_vertices_face, 4), dtype=np.float32)
        self.face_geo.colors = gfx.Buffer(colors_face)
        
        self.face_material = gfx.MeshPhongMaterial(
            color_mode="vertex",
            shininess=30,
            specular=0.4,
            flat_shading=True
        )
        self.face_mesh = gfx.Mesh(self.face_geo, self.face_material)
        self.face_mesh.local.z = -495  # Slightly in front
        self.face_mesh.local.rotation = self.bg_mesh.local.rotation
        self.scene.add(self.face_mesh)

        self.face_wire_material = gfx.MeshBasicMaterial(color_mode="vertex", wireframe=True)
        self.face_wire = gfx.Mesh(self.face_geo, self.face_wire_material)
        self.face_wire.local.z = -485 
        self.face_wire.local.rotation = self.bg_mesh.local.rotation
        self.scene.add(self.face_wire)

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
    
    def process_face(self, mp_image, timestamp_ms):
        if self.detector is None:
            return 0.05, 0.0, None, [], np.array([0.0, 0.0], dtype=np.float32)
            
        result = self.detector.detect_for_video(mp_image, timestamp_ms)
        
        shake_param = 0.05
        color_param = 0.0
        light_pos = None
        face_points_world = []
        mouth_pos = np.array([0.0, 0.0], dtype=np.float32)
        
        if hasattr(result, 'face_landmarks') and result.face_landmarks:
            for face_landmarks in result.face_landmarks:
                nose = face_landmarks[1]
                
                # Point Light
                wx = (nose.x - 0.5) * 2000
                wy = -(nose.y - 0.5) * 1500
                
                # Transform to Grid Space (approx 3000x2200)
                points = []
                for lm in face_landmarks:
                    px = (lm.x - 0.5) * 3000 
                    py = -(lm.y - 0.5) * 2200 
                    points.append([px, py])
                face_points_world.append(np.array(points, dtype=np.float32))
                
                shake_param = max(0.1, (1.0 - nose.y) * 2.0)
                light_pos = (wx, wy, 400)
                
                # 口の位置を算出（グリッド空間）
                upper_lip = face_landmarks[13]
                lower_lip = face_landmarks[14]
                mouth_cx = ((upper_lip.x + lower_lip.x) / 2.0 - 0.5) * 3000
                mouth_cy = -((upper_lip.y + lower_lip.y) / 2.0 - 0.5) * 2200
                mouth_pos = np.array([mouth_cx, mouth_cy], dtype=np.float32)
                
                # Mouth opening tracking -> Color Hue
                face_top = face_landmarks[10]
                face_bottom = face_landmarks[152]
                
                mouth_dist = abs(upper_lip.y - lower_lip.y)
                face_height = abs(face_top.y - face_bottom.y)
                if face_height > 0:
                    opening_ratio = mouth_dist / face_height
                    color_param = np.clip((opening_ratio - 0.02) * 6.0, 0.0, 1.0)
                    
        return shake_param, color_param, light_pos, face_points_world, mouth_pos

    def animate(self):
        ret, frame = self.cap.read()
        if not ret: return
        
        timestamp_ms = int((time.time() - self.start_time) * 1000)
        
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        
        # 1. Process Face
        target_shake, target_color, target_light, face_points, mouth_pos_new = self.process_face(mp_image, timestamp_ms)
        
        # 口の位置を滑らかに追従
        self.mouth_pos = self.mouth_pos * 0.7 + mouth_pos_new * 0.3
        
        self.shake_amp = self.shake_amp * 0.9 + (target_shake * 120.0) * 0.1
        self.base_color_hue = self.base_color_hue * 0.9 + target_color * 0.1
        self.mouth_openness = self.mouth_openness * 0.8 + target_color * 0.2
        
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
        if self.segmentation_enabled and self.segmenter is not None:
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
        
        # 4. Update Background meshes
        t = time.time() - self.start_time
        
        v_px = self.bg_positions_base[:, 0]
        v_py = self.bg_positions_base[:, 1]
        
        # 口の位置からの距離を計算（波の発生源）
        dx_mouth = v_px - self.mouth_pos[0]
        dy_mouth = v_py - self.mouth_pos[1]
        dist_from_mouth = np.sqrt(dx_mouth**2 + dy_mouth**2) / 800.0
        
        # 口の位置から放射状に広がる波
        wave1 = np.sin(dist_from_mouth * 8.0 - t * 4.0) * (100.0 * self.mouth_openness)
        ripple = np.sin(dist_from_mouth * 10.0 - t * 5.0) * (self.shake_amp * self.mouth_openness)
        noise = np.sin(t * 10.0 + self.shake_phases[:, 0]) * (self.shake_amp * 0.2 * self.mouth_openness)
        
        # Interactions
        v_px = self.bg_positions_base[:, 0]
        v_py = self.bg_positions_base[:, 1]
        
        ref_x_f = self.face_positions_base[:, 0] / 800.0
        v_px_f = self.face_positions_base[:, 0]
        v_py_f = self.face_positions_base[:, 1]
        
        bg_influence = np.zeros_like(v_px)
        face_influence_f = np.zeros_like(ref_x_f)
        
        if face_points:
            for face_lm_arr in face_points:
                # Affects Background (flattens it)
                dx_bg = v_px[:, np.newaxis] - face_lm_arr[:, 0]
                dy_bg = v_py[:, np.newaxis] - face_lm_arr[:, 1]
                d2_bg = dx_bg**2 + dy_bg**2
                sigma2_bg = 80.0**2 
                force_bg = 1.0 * np.exp(-d2_bg / sigma2_bg)
                bg_influence += np.max(force_bg, axis=1)

                # Affects Face Mesh (bumps it up)
                dx_f = v_px_f[:, np.newaxis] - face_lm_arr[:, 0]
                dy_f = v_py_f[:, np.newaxis] - face_lm_arr[:, 1]
                d2_f = dx_f**2 + dy_f**2
                sigma2_f = 40.0**2 
                strength_f = 150.0 
                force_f = strength_f * np.exp(-d2_f / sigma2_f)
                face_influence_f += np.max(force_f, axis=1)

        # Base Background (Damped where face is)
        bg_influence = np.clip(bg_influence * 1.5, 0, 1)
        wave_multiplier = (1.0 - bg_influence)
        z_offsets_bg = (wave1 + ripple + noise) * wave_multiplier
        
        self.bg_geo.positions.data[:, 2] = self.bg_positions_base[:, 2] + z_offsets_bg
        self.bg_geo.positions.update_range()
        
        # Colors for BG
        norm_h_bg = (z_offsets_bg + 150) / 450.0
        norm_h_bg = np.clip(norm_h_bg, 0, 1)
        
        hue_bg = (self.base_color_hue + t * 0.1 + norm_h_bg * 0.2) % 1.0
        val_bg = 0.6 + 0.4 * norm_h_bg 
        
        p = hue_bg * 6.28318 
        r = 0.5 + 0.5 * np.cos(p)
        g = 0.5 + 0.5 * np.cos(p + 2.09) 
        b = 0.5 + 0.5 * np.cos(p + 4.18) 
        
        r *= val_bg
        g *= val_bg
        b *= val_bg
        
        new_colors_bg = np.stack([r, g, b, np.ones_like(r)], axis=1).astype(np.float32)
        self.bg_geo.colors.data[:] = new_colors_bg
        self.bg_geo.colors.update_range()

        # Face Mesh (Only face info, no continuous wave)
        z_offsets_f = face_influence_f
        self.face_geo.positions.data[:, 2] = self.face_positions_base[:, 2] + z_offsets_f
        self.face_geo.positions.update_range()
        
        # Colors for Face
        norm_h_f = (z_offsets_f + 150) / 450.0
        norm_h_f = np.clip(norm_h_f, 0, 1)
        
        hue_f = (self.base_color_hue + t * 0.1 + norm_h_f * 0.2) % 1.0
        val_f = 0.6 + 0.4 * norm_h_f 
        
        p_f = hue_f * 6.28318 
        r_f = 0.5 + 0.5 * np.cos(p_f)
        g_f = 0.5 + 0.5 * np.cos(p_f + 2.09) 
        b_f = 0.5 + 0.5 * np.cos(p_f + 4.18)
        
        alpha_f = np.clip(face_influence_f / 30.0, 0, 1)
        
        # Premultiply alpha? Usually not needed if blending is standard, but pygfx handles it.
        new_colors_f = np.stack([r_f*val_f, g_f*val_f, b_f*val_f, alpha_f], axis=1).astype(np.float32)
        self.face_geo.colors.data[:] = new_colors_f
        self.face_geo.colors.update_range()

        # 5. Render
        self.renderer.render(self.scene, self.camera, flush=False)
        
        ui_w, ui_h = 320, 240
        padding = 0
        x = WINDOW_WIDTH - ui_w - padding
        y = padding
        
        self.renderer.render(self.ui_scene, self.ui_camera, rect=(x, y, ui_w, ui_h), clear=False)
        
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
