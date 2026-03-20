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
Fly Shooing AR
A realistic interaction where you shoo away swarming flies with your bare hands.
"""

import math
import time
import os
import random
import numpy as np
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision
import pygfx as gfx
import display_utils
from rendercanvas.auto import RenderCanvas, loop
import pylinalg as la

# ==================== Constants ====================
_DU_W, _DU_H, _DU_X, _DU_Y = display_utils.get_second_monitor_size()
WINDOW_WIDTH = _DU_W
WINDOW_HEIGHT = _DU_H
FOV = 60

# Model paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HAND_MODEL_PATH = os.path.join(SCRIPT_DIR, "models", "hand_landmarker.task")
FACE_MODEL_PATH = os.path.join(SCRIPT_DIR, "models", "face_landmarker.task")


# ==================== Utils ====================
def quaternion_from_euler(pitch, yaw, roll):
    return la.quat_from_euler((pitch, yaw, roll), order='XYZ')


# ==================== Tracking Manager ====================
class TrackingManager:
    def __init__(self):
        # Hand Landmarker
        hand_options = vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=HAND_MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=8, # Support multiple people
            min_hand_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.hand_landmarker = vision.HandLandmarker.create_from_options(hand_options)

        # Face Landmarker
        face_options = vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=FACE_MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=4, # Support multiple people
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.face_landmarker = vision.FaceLandmarker.create_from_options(face_options)

        self.face_rotation = (0, 0)
        self.hands = [] # Changed to list for multiple people
        self.frame_timestamp = 0

    def process(self, image):
        self.frame_timestamp += 33
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)

        hand_result = self.hand_landmarker.detect_for_video(mp_image, self.frame_timestamp)
        face_result = self.face_landmarker.detect_for_video(mp_image, self.frame_timestamp)

        if face_result.face_landmarks:
            self._process_face(face_result.face_landmarks[0], image.shape)

        self.hands = []
        if hand_result.hand_landmarks and hand_result.handedness:
            for landmarks, handedness in zip(hand_result.hand_landmarks, hand_result.handedness):
                label = handedness[0].category_name
                wrist = landmarks[0]
                
                pos = np.array([wrist.x, wrist.y, wrist.z])
                self.hands.append({"pos": pos, "label": label})

    def _process_face(self, landmarks, shape):
        nose = landmarks[4]
        left_ear = landmarks[234]
        right_ear = landmarks[454]

        face_width = right_ear.x - left_ear.x
        if face_width > 0:
            nose_rel = (nose.x - left_ear.x) / face_width
            yaw = (nose_rel - 0.5) * -3.0
        else:
            yaw = 0

        pitch = (nose.y - 0.5) * -2.0
        self.face_rotation = (pitch, yaw)


# ==================== Objects ====================

class Fly:
    def __init__(self, scene, position):
        self.scene = scene
        self.pos = np.array(position, dtype=float)
        self.velocity = np.zeros(3)
        self.target_offset = np.random.uniform(-3, 3, 3) 
        
        # States: APPROACHING, HOVERING, FLEEING, WATCHING
        self.state = "APPROACHING" 
        self.state_timer = 0
        self.move_timer = 0
        
        self.wing_phase = np.random.random() * 100
        
        # Flight characteristics
        self.speed = 0.0
        self.target_dir = np.array([0.0, 0.0, 1.0])
        
        self.mesh = self._create_mesh()
        self.mesh.local.position = tuple(self.pos)
        self.scene.add(self.mesh)

    def _create_mesh(self):
        group = gfx.Group()
        scale = 15.0 # Increased size as requested (5.0 * 3)
        
        # More detailed fly body
        body_mat = gfx.MeshStandardMaterial(color="#050505", roughness=0.4, metalness=0.6)
        
        # Abdomen
        abdomen = gfx.Mesh(gfx.sphere_geometry(0.25 * scale), body_mat)
        abdomen.local.scale = (1, 1.5, 1)
        
        # Thorax
        thorax = gfx.Mesh(gfx.sphere_geometry(0.2 * scale), body_mat)
        thorax.local.position = (0, 0.25 * scale, 0.15 * scale)
        
        # Head
        head = gfx.Mesh(gfx.sphere_geometry(0.18 * scale), body_mat)
        head.local.position = (0, 0.45 * scale, 0.25 * scale)
        
        # Big Red Eyes
        eye_mat = gfx.MeshStandardMaterial(color="#aa0000", roughness=0.2, metalness=0.1)
        l_eye = gfx.Mesh(gfx.sphere_geometry(0.08 * scale), eye_mat)
        l_eye.local.position = (-0.08 * scale, 0.48 * scale, 0.35 * scale)
        r_eye = gfx.Mesh(gfx.sphere_geometry(0.08 * scale), eye_mat)
        r_eye.local.position = (0.08 * scale, 0.48 * scale, 0.35 * scale)
        
        # Wings
        wing_geo = gfx.plane_geometry(0.8 * scale, 0.3 * scale)
        wing_mat = gfx.MeshBasicMaterial(color="#ffffff", opacity=0.3, side="both")
        
        l_wing = gfx.Mesh(wing_geo, wing_mat)
        l_wing.local.position = (-0.3 * scale, 0.3 * scale, 0.2 * scale)
        l_wing.local.rotation = la.quat_from_euler((0.2, -0.2, 0))
        
        r_wing = gfx.Mesh(wing_geo, wing_mat)
        r_wing.local.position = (0.3 * scale, 0.3 * scale, 0.2 * scale)
        r_wing.local.rotation = la.quat_from_euler((0.2, 0.2, 0))
        
        group.add(abdomen, thorax, head, l_eye, r_eye, l_wing, r_wing)
        return group

    def update(self, dt, target_pos, hand_vectors): # Changed argument to hand_vectors
        self.wing_phase += dt * 60.0 # Standard wing speed
        
        # State Machine
        self.state_timer -= dt
        self.move_timer -= dt
        
        # 1. State Transitions & Logic
        if self.state == "APPROACHING":
            #Zigzag approach towards target
            if self.move_timer <= 0:
                to_target = target_pos + self.target_offset - self.pos
                dist = np.linalg.norm(to_target)
                
                if dist < 10.0:
                    self.state = "HOVERING"
                    self.state_timer = np.random.uniform(2.0, 4.0) 
                else:
                    if dist > 0: to_target /= dist
                    noise = np.random.uniform(-1, 1, 3)
                    new_dir = to_target * 0.1 + noise * 0.9 
                    new_dir /= np.linalg.norm(new_dir)
                    self.target_dir = new_dir
                    # Speed x1.2 (300-800 -> 360-960)
                    self.speed = np.random.uniform(360.0, 960.0) 
                    self.move_timer = np.random.uniform(0.1, 0.5) 

        elif self.state == "HOVERING":
            if self.state_timer <= 0:
                self.state = "APPROACHING"
            
            if self.move_timer <= 0:
                if np.random.random() < 0.2:
                    self.speed = 0
                    self.move_timer = np.random.uniform(0.2, 0.5)
                else:
                    self.target_dir = np.random.uniform(-1, 1, 3)
                    self.target_dir /= np.linalg.norm(self.target_dir)
                    # Speed x1.2 (200-500 -> 240-600)
                    self.speed = np.random.uniform(240.0, 600.0)
                    self.move_timer = np.random.uniform(0.05, 0.15)
                    
        elif self.state == "FLEEING":
            color_val = max(0, self.state_timer / 0.5) 
            red_intensity = int(color_val * 255)
            self.mesh.children[0].material.color = f"#{red_intensity:02x}0505"

            if self.state_timer <= 0:
                self.state = "WATCHING"
                self.speed = 0
                self.state_timer = np.random.uniform(0.5, 1.5) 
                self.mesh.children[0].material.color = "#050505" 
                
        elif self.state == "WATCHING":
            self.speed = 0
            if self.state_timer <= 0:
                self.state = "APPROACHING"

        # 2. Hand Interaction (Override) - Vector/Angle based
        fleeing_now = False
        
        fly_vec = self.pos 
        fly_dist = np.linalg.norm(fly_vec)
        if fly_dist > 0:
            fly_dir = fly_vec / fly_dist
            
            for h_vec in hand_vectors:
                alignment = np.dot(fly_dir, h_vec)
                
                if alignment > 0.92: 
                    self.state = "FLEEING"
                    self.state_timer = 0.5 
                    
                    # Flee direction: Flee away from the person/hand in all directions (X,Y,Z)
                    # No forced Z bias anymore.
                    dir_from_camera = self.pos / np.linalg.norm(self.pos)
                    
                    # Random 3D scatter in all axes
                    scatter = np.random.uniform(-1.0, 1.0, 3)
                    
                    flee_dir = dir_from_camera + scatter
                    flee_dir /= np.linalg.norm(flee_dir)
                    
                    self.target_dir = flee_dir
                    # Speed x1.2 (1500 -> 1800)
                    self.speed = 1800.0 
                    fleeing_now = True
                    break
        
        # 3. Physics & Visuals
        if fleeing_now:
             self.velocity = self.target_dir * self.speed
             self.wing_phase += dt * 360.0 # Faster wings
        elif self.speed > 1.0:
             target_vel = self.target_dir * self.speed
             self.velocity = self.velocity * 0.4 + target_vel * 0.6
             self.wing_phase += dt * 120.0 
        else:
             self.velocity *= 0.8
        
        self.pos += self.velocity * dt

        # Recalculate target offset occasionally to simulate "coming in and out" of FOV
        if self.state != "FLEEING" and np.random.random() < 0.01:
            if np.random.random() < 0.3:
                # DIVE: Pick a target closer to the screen center
                self.target_offset = np.random.uniform(-30, 30, 3)
                self.target_offset[2] = np.random.uniform(-100, -70) # Bring it closer
            else:
                # HIDE: Pick a target far outside the FOV or deep behind
                self.target_offset = np.array([
                    np.random.choice([-1, 1]) * np.random.uniform(100, 300),
                    np.random.uniform(-100, 100),
                    np.random.uniform(-300, -150)
                ])

        # FACE AVOIDANCE: Hard limit to keep flies away from the screen/face
        # Minimum distance in Z is -60 (Kept as per user's "unrealistic" request)
        if self.pos[2] > -60.0:
            self.pos[2] = -60.0
            self.velocity[2] *= -0.5
            self.target_dir[2] = -abs(self.target_dir[2])
        
        # Orientation
        if self.state == "WATCHING":
             look_dir = target_pos - self.pos
        elif np.linalg.norm(self.velocity) > 0.1:
             look_dir = self.velocity
        else:
             look_dir = None

        if look_dir is not None and np.linalg.norm(look_dir) > 0.001:
            look_dir /= np.linalg.norm(look_dir)
            pitch = -math.asin(max(-1.0, min(1.0, look_dir[1])))
            yaw = math.atan2(look_dir[0], look_dir[2])
            self.mesh.local.rotation = la.quat_from_euler((pitch, yaw, 0))

        self.mesh.local.position = tuple(self.pos)
        
        # Wing animation
        if self.speed > 1.0 or self.state == "HOVERING" or fleeing_now:
             wing_angle = math.sin(self.wing_phase) * 0.5
             self.mesh.children[5].local.rotation = la.quat_from_euler((0.2, -0.2, wing_angle))
             self.mesh.children[6].local.rotation = la.quat_from_euler((0.2, 0.2, -wing_angle))
        else:
             self.mesh.children[5].local.rotation = la.quat_from_euler((0.2, -0.2, 0))
             self.mesh.children[6].local.rotation = la.quat_from_euler((0.2, 0.2, 0))


class FlyManager:
    def __init__(self, scene):
        self.scene = scene
        self.flies = []
        
        # Spawn cloud of flies - EXTREME DISTANCE
        for _ in range(40): # More flies
            # Z range -50 to -200
            pos = (np.random.uniform(-100, 100), np.random.uniform(-50, 50), np.random.uniform(-200, -50))
            fly = Fly(self.scene, pos)
            # Huge offset for scattering
            fly.target_offset = np.random.uniform(-80, 80, 3)
            self.flies.append(fly)

    def update(self, dt, camera_pos, hands):
        # Calculate Hand Vectors (Direction from camera) for all detected hands
        hand_vectors = []
        
        fov_rad = math.radians(FOV)
        tan_half_fov = math.tan(fov_rad / 2)
        aspect = WINDOW_WIDTH / WINDOW_HEIGHT
        
        for hand in hands: # hands is now a list
            # Normalize 0..1 to -1..1
            ndc_x = (hand["pos"][0] - 0.5) * 2.0
            ndc_y = (0.5 - hand["pos"][1]) * 2.0
            
            # Camera space direction
            cx = ndc_x * tan_half_fov * aspect
            cy = ndc_y * tan_half_fov
            cz = -1.0
            
            vec = np.array([cx, cy, cz])
            vec /= np.linalg.norm(vec)
            hand_vectors.append(vec)
        
        for fly in self.flies:
            # Target is Z = -100 (Deep background)
            fly.update(dt, np.array([0, 0, -100]), hand_vectors)


# ==================== Main App ====================
class FlyShooingApp:
    def __init__(self):
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="Fly Shooing AR")
        display_utils.setup_rendercanvas_fullscreen(self.canvas)
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)
        self.scene = gfx.Scene()

        self.camera = gfx.PerspectiveCamera(FOV, WINDOW_WIDTH / WINDOW_HEIGHT)
        self.camera.local.position = (0, 0, 0)

        # Background
        self.bg_tex = gfx.Texture(np.zeros((720, 1280, 4), dtype=np.uint8), dim=2)
        bg_material = gfx.BackgroundImageMaterial(map=self.bg_tex)
        self.bg_plane = gfx.Background(None, bg_material)
        self.scene.add(self.bg_plane)

        # Lighting
        self.scene.add(gfx.AmbientLight("#404040", 1.0))
        sun = gfx.DirectionalLight("#ffffff", 3.0)
        sun.local.position = (10, 20, 10)
        self.scene.add(sun)

        self.fly_manager = FlyManager(self.scene)
        self.tracker = TrackingManager()
        
        self.cap = display_utils.open_camera()
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # Add key event handler
        self.canvas.add_event_handler(self.on_key, "key_down")

        self.last_time = time.time()
        print("Fly Shooing AR Initialized.")

    def animate(self):
        now = time.time()
        dt = now - self.last_time
        self.last_time = now

        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.tracker.process(rgb)

            frame_rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            frame_rgba = cv2.flip(frame_rgba, 0)
            self.bg_tex.data[:] = frame_rgba
            self.bg_tex.update_range((0, 0, 0), self.bg_tex.size)

        # Fixed Camera - removed face tracking
        # self.update_camera_from_face()

        self.fly_manager.update(dt, np.array([0, 0, 0]), self.tracker.hands)

        self.renderer.render(self.scene, self.camera)
        self.canvas.request_draw()

    def run(self):
        self.canvas.request_draw(self.animate)
        loop.run()

    def on_key(self, event):
        if event.key == "q" or event.key == "Q":
            print("Quitting...")
            loop.stop()

    def cleanup(self):
        self.cap.release()


if __name__ == "__main__":
    game = FlyShooingApp()
    try:
        game.run()
    except KeyboardInterrupt:
        pass
    finally:
        game.cleanup()
