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
import warnings
from contextlib import ExitStack
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision
import numpy as np
import wgpu
import display_utils
from hand_focus_overlay import draw_cv2 as draw_hand_overlay
from scene_control import notify_exit_request, notify_first_frame
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
        self._resources = ExitStack()
        self._frame_error = None
        try:
            self._initialize()
        except BaseException as error:
            try:
                self.cleanup()
            except BaseException as cleanup_error:
                error.add_note(f"Earth cleanup also failed: {cleanup_error}")
            raise

    def _initialize(self):
        # 1. Setup pygfx
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="3D Earth Viewer")
        self._resources.callback(self.canvas.close)
        display_utils.setup_rendercanvas_fullscreen(self.canvas)
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)
        self.scene = gfx.Scene()
        
        # Camera
        self.camera = gfx.PerspectiveCamera(70, WINDOW_WIDTH / max(1, WINDOW_HEIGHT))
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
        self.hud_camera.local.z = 100
        self.create_hud()

        # 2. MediaPipe Hands (model_complexity=1, Tasks API)
        model_path = display_utils.resolve_model_path("models/hand_landmarker.task")
        if not display_utils.is_valid_model_asset(model_path):
            raise RuntimeError(f"Earth hand model missing or invalid: {model_path}")
        
        base_options = mp_tasks.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2 # Need 2 hands now
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        self._resources.callback(self.detector.close)
        
        # 3. Event Handlers
        self.canvas.add_event_handler(self.on_event, "key_down", "close")
        
        # 4. Webcam
        self.cap = display_utils.open_camera()
        if self.cap is not None:
            self._resources.callback(self.cap.release)
        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError("Earth: the shared camera could not be attached")
        self.last_timestamp = 0
        self.camera_last_frame_id = None
        self.camera_last_fresh_at = None
        self.camera_failure_since = None
        self.detected_hands = ()
        self.active_hand_indices = ()
        self.input_state = (False, 0., 0., 0., False, 0., 0.)
        
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
        self.interacting_galaxy = False

    def on_event(self, event):
        key = event.get("key")
        if event.get("event_type") == "close" or key in ("q", "Q", "Escape"):
            notify_exit_request("window_close" if event.get("event_type") == "close" else
                                "key_escape" if key == "Escape" else "key_q")
            loop.stop()

    def create_hud(self):
        # Create a plane for camera feed
        # Size: Let's say 320x240 (1/4 scale of 1280x960 is 320x240)
        w, h = 320, 240
        self.hud_tex = gfx.Texture(np.zeros((h, w, 4), dtype=np.uint8), dim=2)
        material = gfx.MeshBasicMaterial(map=self.hud_tex, depth_test=False, depth_write=False)
        
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
        
        # These are the existing tracked JPEGs. Decode the large galaxy at JPEG
        # draft resolution before RGBA conversion (avoid a ~460 MB full decode).
        # Keep Pillow's global safety limit intact for every other image consumer.
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                with Image.open(tex_path) as source:
                    source.draft("RGB", (4096, max(1, round(4096 * source.height / source.width))))
                    source.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
                    img_data = np.array(source.convert("RGBA"))
            return gfx.Texture(img_data, dim=2)
        except (OSError, ValueError) as error:
            raise RuntimeError(f"Earth texture unavailable: {filename}") from error

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
        self.scene.add(self.earth_mesh)

    def process_input(self, frame, timestamp, layout=None):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        
        results = self.detector.detect_for_video(mp_img, timestamp)
        self.detected_hands = tuple(results.hand_landmarks or ())
        active_by_label = {}
        
        # Outputs
        earth_tx, earth_ty, earth_tz = 0.0, 0.0, 0.0
        galaxy_tx, galaxy_ty = 0.0, 0.0
        
        has_left = False
        has_right = False
        
        if results.hand_landmarks:
            for idx, hand_landmarks in enumerate(results.hand_landmarks):
                # Retrieve handedness (if available, assume order matches)
                label = "Unknown"
                if idx < len(results.handedness) and results.handedness[idx]:
                   label = results.handedness[idx][0].category_name
                
                wrist = hand_landmarks[0]
                middle = hand_landmarks[9]
                
                # Position (0.0 to 1.0)
                cx = (wrist.x + middle.x) / 2
                cy = (wrist.y + middle.y) / 2
                
                if label == "Left":
                    active_by_label[label] = idx
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
                    active_by_label[label] = idx
                    has_right = True
                    # Galaxy Control
                    # X/Y -> Rotation
                    galaxy_tx = (cy - 0.5) * -1.0 * math.pi
                    galaxy_ty = (cx - 0.5) * -1.0 * math.pi

        self.active_hand_indices = tuple(active_by_label.values())
        return has_left, earth_tx, earth_ty, earth_tz, has_right, galaxy_tx, galaxy_ty

    def clear_input(self):
        self.detected_hands = ()
        self.active_hand_indices = ()
        self.input_state = (False, 0., 0., 0., False, 0., 0.)
        self.interacting_earth = self.interacting_galaxy = False
        self.hud_tex.data[:] = (0, 0, 0, 255)
        self.hud_tex.update_range((0, 0, 0), self.hud_tex.size)

    def update_camera(self, now):
        self.clear_input()
        ret, frame = self.cap.read()
        fresh = bool(ret and frame is not None)
        frame_id = getattr(self.cap, "last_read_frame_id", None)
        if fresh and type(frame_id) is int:
            if frame_id != self.camera_last_frame_id:
                self.camera_last_frame_id = frame_id
                self.camera_last_fresh_at = now
            elif self.camera_last_fresh_at is not None and now - self.camera_last_fresh_at >= 0.25:
                fresh = False
        if not fresh:
            if self.camera_failure_since is None:
                self.camera_failure_since = now
            elif now - self.camera_failure_since >= 1.0:
                notify_exit_request("camera_read_failed_timeout")
                raise RuntimeError("Earth: shared camera unavailable for one second")
            return False
        self.camera_failure_since = None
        camera, hud_frame, layout = display_utils.prepare_camera_frame(frame, 320, 240)
        timestamp = max(int(now * 1000), self.last_timestamp + 1)
        self.last_timestamp = timestamp
        self.input_state = self.process_input(camera, timestamp, layout)
        # Preserve the original camera HUD. The controlled point is the palm
        # center, never a fingertip; unknown/unused handedness stays passive.
        for idx, hand in enumerate(self.detected_hands):
            draw_hand_overlay(hud_frame, (hand,), layout=layout, focus=(),
                              palm_focus=idx in self.active_hand_indices)
        hud_rgb = cv2.cvtColor(hud_frame, cv2.COLOR_BGR2RGBA)
        self.hud_tex.data[:] = hud_rgb
        self.hud_tex.update_range((0, 0, 0), self.hud_tex.size)
        return True

    def animate(self):
        # Even a failed camera read must schedule the next draw to allow recovery.
        try:
            self._animate_frame()
        except Exception as error:
            # RenderCanvas logs callback exceptions; stop its loop as well so
            # run() releases resources and Manager can observe/restart the scene.
            self._frame_error = error
            notify_exit_request("earth_frame_failed")
            loop.stop()
            raise
        finally:
            self.canvas.request_draw()

    def _animate_frame(self):
        try:
            frame_processed = self.update_camera(time.monotonic())
        except BaseException:
            self.clear_input()
            raise
        has_L, e_tx, e_ty, e_tz, has_R, g_tx, g_ty = self.input_state
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
        self.renderer.render(self.scene, self.camera, flush=False)
        self.renderer.render(self.hud_scene, self.hud_camera, clear=False)
        notify_first_frame(self.cap, frame_processed=frame_processed)

    def run(self):
        try:
            self.canvas.request_draw(self.animate)
            loop.run()
            if self._frame_error is not None:
                raise self._frame_error
        finally:
            self.cleanup()

    def cleanup(self):
        self._resources.close()

if __name__ == "__main__":
    app = EarthViewer3D()
    try:
        app.run()
    finally:
        app.cleanup()
