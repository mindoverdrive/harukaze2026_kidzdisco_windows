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
3D Earth Viewer - Gesture Controlled
====================================
A realistic 3D Earth viewer controlled by hand gestures.
- Left Hand X/Y: Rotates the Earth.
- Left Hand Z (Depth): Zooms in/out.
- Right Hand X/Y: Rotates the Galaxy Background.
- HUD: Camera feed in top-right with hand skeleton.
"""

import math
import time
import os
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision
import numpy as np
import wgpu
import display_utils
from rendercanvas.auto import RenderCanvas, loop
import pygfx as gfx
import pylinalg as la
from PIL import Image

# ==================== Constants ====================
_DU_W, _DU_H, _DU_X, _DU_Y = display_utils.get_second_monitor_size()
WINDOW_WIDTH = _DU_W
WINDOW_HEIGHT = _DU_H
EARTH_RADIUS = 300
GALAXY_RADIUS = 4000 # Large sphere for background

# ==================== Earth Viewer Class ====================
class EarthViewer3D:
    def __init__(self):
        # 1. Setup pygfx
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="3D Earth Viewer")
        display_utils.setup_rendercanvas_fullscreen(self.canvas)
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)
        self.scene = gfx.Scene()
        
        # Camera
        self.camera = gfx.PerspectiveCamera(70, 16 / 9)
        self.camera.local.z = 1000
        
        # Lighting (Sun)
        self.scene.add(gfx.AmbientLight(0.1)) # Darker ambient for space
        self.sun = gfx.DirectionalLight(3.0)
        self.sun.local.x = 2000
        self.sun.local.y = 1000
        self.sun.local.z = 2000
        self.scene.add(self.sun)

        # HUD Scene (Camera Feed)
        self.hud_scene = gfx.Scene()
        self.hud_camera = gfx.OrthographicCamera(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.create_hud()

        # 2. MediaPipe Hands (model_complexity=1, Tasks API)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(script_dir, "models", "hand_landmarker.task")
        
        base_options = mp_tasks.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2 # Need 2 hands now
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        
        # 3. Event Handlers
        @self.canvas.add_event_handler("key_down")
        def on_key_down(event):
            if event["key"] in ("q", "Q", "Escape"):
                loop.stop()
        
        # 4. Webcam
        self.cap = display_utils.open_camera()
        if not self.cap or not self.cap.isOpened():
            print("Warning: Camera open failed, retrying with fallback")
            self.cap = display_utils.open_camera(camera_index=1)

        if self.cap and self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, display_utils.DEFAULT_CAMERA_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, display_utils.DEFAULT_CAMERA_HEIGHT)
            self.cap.set(cv2.CAP_PROP_FPS, display_utils.DEFAULT_CAMERA_FPS)
        else:
            raise RuntimeError("Failed to open camera for EarthViewer3D")
        
        # 4. Create World
        self.create_galaxy()
        self.create_earth()
        
        # State
        # Earth (Left Hand)
        self.target_earth_rot_x = 0.0 # Pitch
        self.target_earth_rot_y = 0.0 # Yaw
        self.curr_earth_rot_x = 0.0
        self.curr_earth_rot_y = 0.0
        
        self.base_zoom = 1000
        self.target_zoom = 1000
        self.curr_zoom = 1000

        # Galaxy (Right Hand)
        self.target_galaxy_rot_x = 0.0
        self.target_galaxy_rot_y = 0.0
        self.curr_galaxy_rot_x = 0.0
        self.curr_galaxy_rot_y = 0.0
        
        # Auto-rotation (idle)
        self.auto_rotate_earth = 0.001
        self.auto_rotate_galaxy = 0.0002
        self.interacting_earth = False
        self.interacting_earth = False
        self.interacting_galaxy = False

    def create_hud(self):
        # Create a plane for camera feed
        # Size: Let's say 320x240 (1/4 scale of 1280x960 is 320x240)
        w, h = 320, 240
        self.hud_tex = gfx.Texture(np.zeros((h, w, 4), dtype=np.uint8), dim=2)
        material = gfx.MeshBasicMaterial(map=self.hud_tex)
        
        plane = gfx.plane_geometry(w, h)
        self.hud_mesh = gfx.Mesh(plane, material)
        
        # Position at Top-Right
        # Center of screen is 0,0. Top-Right corner is W/2, H/2.
        # Plane center needs to be at W/2 - w/2 - padding, H/2 - h/2 - padding
        padding = 20
        px = (WINDOW_WIDTH / 2) - (w / 2) - padding
        py = (WINDOW_HEIGHT / 2) - (h / 2) - padding
        
        self.hud_mesh.local.position = (px, py, 0)
        self.hud_scene.add(self.hud_mesh)

    def load_texture(self, filename, fallback_color=(0,0,255)):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        tex_path = os.path.join(script_dir, filename)
        
        if os.path.exists(tex_path):
            try:
                # Use PIL to load huge images safely or convert formats
                # Increase Image.MAX_IMAGE_PIXELS to allow large NASA/ESO textures
                Image.MAX_IMAGE_PIXELS = None
                img = Image.open(tex_path).convert('RGBA')
                # Resize if HUGE to avoid VRAM issues (e.g. 19M image)
                if img.width > 4096:
                    img = img.resize((4096, int(4096 * img.height / img.width)), Image.Resampling.LANCZOS)
                
                img_data = np.array(img)
                return gfx.Texture(img_data, dim=2)
            except Exception as e:
                print(f"Failed to load {filename}: {e}")
        
        # Fallback
        print(f"Using fallback texture for {filename}")
        tex_data = np.zeros((512, 1024, 4), dtype=np.uint8)
        tex_data[:,:,0] = fallback_color[2]
        tex_data[:,:,1] = fallback_color[1]
        tex_data[:,:,2] = fallback_color[0]
        tex_data[:,:,3] = 255
        return gfx.Texture(tex_data, dim=2)

    def create_galaxy(self):
        # Load Galaxy Texture
        self.galaxy_tex = self.load_texture("galaxy_texture.jpg", fallback_color=(0,0,0))
        
        # Material - Unlit (Basic) for background, full brightness
        material = gfx.MeshBasicMaterial(map=self.galaxy_tex, side='Back') # Render inside of sphere
        
        # Geometry: Large Sphere
        geometry = gfx.sphere_geometry(radius=GALAXY_RADIUS, width_segments=64, height_segments=64)
        
        self.galaxy_mesh = gfx.Mesh(geometry, material)
        self.scene.add(self.galaxy_mesh)

    def create_earth(self):
        # Load Earth Texture
        self.earth_tex = self.load_texture("real_earth_texture.jpg", fallback_color=(0,0,255))

        # Material - Phong for lighting
        material = gfx.MeshPhongMaterial(map=self.earth_tex, shininess=10)
        
        # Geometry: Sphere
        geometry = gfx.sphere_geometry(radius=EARTH_RADIUS, width_segments=64, height_segments=64)
        
        self.earth_mesh = gfx.Mesh(geometry, material)
        self.earth_mesh = gfx.Mesh(geometry, material)
        self.scene.add(self.earth_mesh)

    def draw_hand_skeleton(self, frame, landmarks):
        CONNECTIONS = [
            (0, 1), (1, 2), (2, 3), (3, 4), # Thumb
            (0, 5), (5, 6), (6, 7), (7, 8), # Index
            (0, 9), (9, 10), (10, 11), (11, 12), # Middle
            (0, 13), (13, 14), (14, 15), (15, 16), # Ring
            (0, 17), (17, 18), (18, 19), (19, 20), # Pinky
            (5, 9), (9, 13), (13, 17) # Knuckles
        ]
        
        h, w, _ = frame.shape
        pixel_landmarks = []
        for lm in landmarks:
            cx, cy = int(lm.x * w), int(lm.y * h)
            pixel_landmarks.append((cx, cy))
            
        # Draw connections
        for start_idx, end_idx in CONNECTIONS:
            start_point = pixel_landmarks[start_idx]
            end_point = pixel_landmarks[end_idx]
            cv2.line(frame, start_point, end_point, (0, 255, 255), 2) # Cyan/Yellowish
            
        # Draw points
        for p in pixel_landmarks:
            cv2.circle(frame, p, 3, (0, 0, 255), -1) # Red dots

    def process_input(self, frame, timestamp):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        
        results = self.detector.detect_for_video(mp_img, timestamp)
        
        # Outputs
        earth_tx, earth_ty, earth_tz = 0.0, 0.0, 0.0
        galaxy_tx, galaxy_ty = 0.0, 0.0
        
        has_left = False
        has_right = False
        
        if results.hand_landmarks:
            for idx, hand_landmarks in enumerate(results.hand_landmarks):
                # Draw skeleton
                self.draw_hand_skeleton(frame, hand_landmarks)

                # Retrieve handedness (if available, assume order matches)
                label = "Unknown"
                if idx < len(results.handedness):
                   label = results.handedness[idx][0].category_name
                
                wrist = hand_landmarks[0]
                middle = hand_landmarks[9]
                
                # Position (0.0 to 1.0)
                cx = (wrist.x + middle.x) / 2
                cy = (wrist.y + middle.y) / 2
                
                if label == "Left":
                    has_left = True
                    # Earth Control
                    # X/Y -> Rotation
                    earth_tx = (cy - 0.5) * -1.5 * math.pi
                    earth_ty = (cx - 0.5) * -1.5 * math.pi
                    
                    # Zoom
                    size = math.sqrt((wrist.x - middle.x)**2 + (wrist.y - middle.y)**2)
                    norm_size = (size - 0.05) / 0.25
                    norm_size = min(max(norm_size, 0), 1)
                    earth_tz = 1500 - (norm_size * 1100) # 1500 -> 400
                
                elif label == "Right":
                    has_right = True
                    # Galaxy Control
                    # X/Y -> Rotation
                    galaxy_tx = (cy - 0.5) * -1.0 * math.pi
                    galaxy_ty = (cx - 0.5) * -1.0 * math.pi

        return has_left, earth_tx, earth_ty, earth_tz, has_right, galaxy_tx, galaxy_ty

    def animate(self):
        ret, frame = self.cap.read()
        if not ret: return
        
        frame = cv2.flip(frame, 1)
        
        now = time.time()
        # process_input now draws on 'frame'
        has_L, e_tx, e_ty, e_tz, has_R, g_tx, g_ty = self.process_input(frame, int(now * 1000))
        
        # Update HUD Texture with the annotated frame
        hud_frame = cv2.resize(frame, (320, 240))
        hud_rgb = cv2.cvtColor(hud_frame, cv2.COLOR_BGR2RGBA)
        hud_rgb[:,:,3] = 255
        self.hud_tex.data[:] = hud_rgb
        self.hud_tex.update_range((0,0,0), self.hud_tex.size)
        
        self.interacting_earth = has_L
        self.interacting_galaxy = has_R
        
        # --- Earth Logic ---
        if has_L:
            self.target_earth_rot_x = e_tx * 2.0
            self.target_earth_rot_y = e_ty * 2.0
            self.target_zoom = e_tz
        else:
            # Idle
            self.target_earth_rot_y += self.auto_rotate_earth
            
        # Smooth Earth
        self.curr_earth_rot_x += (self.target_earth_rot_x - self.curr_earth_rot_x) * 0.1
        self.curr_earth_rot_y += (self.target_earth_rot_y - self.curr_earth_rot_y) * 0.1
        self.curr_zoom += (self.target_zoom - self.curr_zoom) * 0.1
        
        # Apply Earth
        self.earth_mesh.local.rotation = la.quat_from_euler((self.curr_earth_rot_x, self.curr_earth_rot_y, 0))
        self.camera.local.z = self.curr_zoom

        # --- Galaxy Logic ---
        if has_R:
            self.target_galaxy_rot_x = g_tx * 2.0
            self.target_galaxy_rot_y = g_ty * 2.0
        else:
            self.target_galaxy_rot_y += self.auto_rotate_galaxy # Very slow drift

        # Smooth Galaxy
        self.curr_galaxy_rot_x += (self.target_galaxy_rot_x - self.curr_galaxy_rot_x) * 0.05
        self.curr_galaxy_rot_y += (self.target_galaxy_rot_y - self.curr_galaxy_rot_y) * 0.05
        
        # Apply Galaxy
        # Note: Galaxy is huge. 
        self.galaxy_mesh.local.rotation = la.quat_from_euler((self.curr_galaxy_rot_x, self.curr_galaxy_rot_y, 0))

        # Render Main Scene (flush=False to allow HUD overlay)
        try:
            self.renderer.render(self.scene, self.camera, flush=False)
        except RuntimeError:
            pass
        # Render HUD Scene
        try:
            self.renderer.render(self.hud_scene, self.hud_camera)
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
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = EarthViewer3D()
    try:
        app.run()
    finally:
        app.cleanup()
