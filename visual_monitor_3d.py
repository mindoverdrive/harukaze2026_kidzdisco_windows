
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
import requests
import io
import threading
import numpy as np
import cv2
import pygfx as gfx
import pylinalg as la
import display_utils
from rendercanvas.auto import RenderCanvas, loop
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# ==================== Configuration ====================
_DU_W, _DU_H, _DU_X, _DU_Y = display_utils.get_second_monitor_size()
WINDOW_WIDTH = _DU_W
WINDOW_HEIGHT = _DU_H

# Image URLs to fetch (Fallback if offline)
IMAGE_URLS = [
    "https://harukaze.asia/gallery/wp-content/uploads/photo-gallery/2024-03-16/0000-05-240316_Harukaze_071.jpg",
    "https://harukaze.asia/gallery/wp-content/uploads/photo-gallery/2024-03-16/0000-04-240316_Harukaze_000.jpg",
    "https://harukaze.asia/gallery/wp-content/uploads/photo-gallery/2024-03-16/0000-02-240316_Harukaze_065.jpg", 
    "https://harukaze.asia/gallery/wp-content/uploads/photo-gallery/2024-03-16/0000-06-240316_Harukaze_072.jpg",
]

# Local assets to prefer for offline use
LOCAL_ASSET_PATHS = [
    "test/images.jpeg",
    "test/images (1).jpeg",
    "test/images.png",
    "test/earth_texture.png",
    "test/galaxy_texture.jpg"
]

# Fallback colors
FALLBACK_COLORS = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#00FFFF", "#FF00FF"]

class TextureManager:
    def __init__(self):
        self.textures = []
        self.current_index = 0
        self.loading_thread = None
        self.stop_loading = False
        
        # Add a default placeholder texture immediately
        self.textures.append(self.create_placeholder_texture("#333333"))

    def start_loading(self):
        self.loading_thread = threading.Thread(target=self._load_images)
        self.loading_thread.daemon = True
        self.loading_thread.start()

    def _load_images(self):
        print("Starting image loading...")
        count = 0
        
        # 1. Try Local Assets first (Offline support)
        for path in LOCAL_ASSET_PATHS:
            if self.stop_loading: break
            try:
                # Use absolute path if possible
                full_path = path if os.path.isabs(path) else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", path)
                if os.path.exists(full_path):
                    img = cv2.imread(full_path, cv2.IMREAD_COLOR)
                    if img is not None:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
                        tex = gfx.Texture(img, dim=2)
                        self.textures.append(tex)
                        count += 1
                        print(f"Loaded local asset: {path}")
            except Exception as e:
                print(f"Failed to load local asset {path}: {e}")

        # 2. Try Remote URLs if still needed or as extras
        for url in IMAGE_URLS:
            if self.stop_loading: break
            try:
                print(f"Fetching {url}...")
                resp = requests.get(url, timeout=2) # Reduced timeout for offline fail-fast
                if resp.status_code == 200:
                    img_array = np.frombuffer(resp.content, np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    if img is not None:
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
                        tex = gfx.Texture(img, dim=2)
                        self.textures.append(tex)
                        count += 1
                        print(f"Loaded remote image: {url}")
            except Exception as e:
                print(f"Failed to fetch {url} (Offline?): {e}")
        
        if count == 0:
            print("No images loaded, using generators.")
            for col in FALLBACK_COLORS:
                self.textures.append(self.create_placeholder_texture(col))
                
        # Remove initial placeholder if we have real images
        if count > 0 and len(self.textures) > 1:
            pass

    def create_placeholder_texture(self, color_hex):
        # Create a simple 64x64 texture
        data = np.zeros((64, 64, 4), dtype=np.float32)
        c = gfx.Color(color_hex)
        data[:] = c
        start, end = 16, 48
        data[start:end, start:end] = (1, 1, 1, 1)
        return gfx.Texture(data, dim=2)

    def get_current_texture(self):
        if not self.textures:
            return None
        return self.textures[self.current_index % len(self.textures)]

    def next_texture(self):
        if not self.textures: return
        self.current_index = (self.current_index + 1) % len(self.textures)
        return self.get_current_texture()

    def prev_texture(self):
        if not self.textures: return
        self.current_index = (self.current_index - 1) % len(self.textures)
        return self.get_current_texture()

class VisualMonitorApp:
    def __init__(self):
        # 1. Setup RenderCanvas (replaces wgpu.gui.pygame)
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="Interactive 3D Monitor")
        display_utils.setup_rendercanvas_fullscreen(self.canvas)
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)
        
        # Scene 1: Main 3D Scene
        self.scene = gfx.Scene()
        self.camera = gfx.PerspectiveCamera(70, 16/9)
        self.camera.local.z = 800
        
        # Lights
        self.scene.add(gfx.AmbientLight("#404040", 1.0))
        d_light = gfx.DirectionalLight("#ffffff", 2.0)
        d_light.local.position = (500, 500, 1000)
        self.scene.add(d_light)
        
        # Scene 2: 2D Overlay (HUD) for Camera Feed
        self.hud_scene = gfx.Scene()
        self.hud_camera = gfx.OrthographicCamera(320, 240) # Small viewport size
        
        # 3. Monitor Object
        self.create_monitor()
        
        # 4. Texture Manager
        self.tex_manager = TextureManager()
        self.tex_manager.start_loading()
        
        # 5. MediaPipe Setup
        self.init_mediapipe()
        
        # 6. Camera Setup
        self.cap = display_utils.open_camera()
        if not self.cap.isOpened():
            print("Warning: Camera 0 not found, trying 1")
            self.cap = display_utils.open_camera()
            
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        # Camera Feed Texture
        self.cam_tex = gfx.Texture(np.zeros((480, 640, 4), dtype=np.uint8), dim=2)
        self.cam_plane = gfx.Mesh(
            gfx.plane_geometry(320, 240),
            gfx.MeshBasicMaterial(map=self.cam_tex)
        )
        self.hud_scene.add(self.cam_plane)
        
        # State
        self.monitor_rot = [0.0, 0.0] # Pitch, Yaw
        self.last_hand_pos = None # For delta calculation
        self.gesture_cooldown = 0
        
        # Event Handling
        self.canvas.add_event_handler(self.on_event, "key_down")

    def create_monitor(self):
        monitor_w, monitor_h, monitor_d = 400, 300, 20
        
        self.monitor_body_mat = gfx.MeshStandardMaterial(color="#111111", roughness=0.5, metalness=0.8)
        self.monitor_screen_mat = gfx.MeshBasicMaterial(color="#ffffff") 
        
        self.monitor_group = gfx.Group()
        
        # 1. Bezel/Body
        bezel = gfx.Mesh(
            gfx.box_geometry(monitor_w + 20, monitor_h + 20, monitor_d),
            self.monitor_body_mat
        )
        self.monitor_group.add(bezel)
        
        # 2. Screen (slightly in front)
        self.screen_mesh = gfx.Mesh(
            gfx.plane_geometry(monitor_w, monitor_h),
            self.monitor_screen_mat
        )
        self.screen_mesh.local.position = (0, 0, monitor_d/2 + 1)
        self.monitor_group.add(self.screen_mesh)
        
        # 3. Stand
        stand_pole = gfx.Mesh(
            gfx.cylinder_geometry(15, 15, 100),
            self.monitor_body_mat
        )
        stand_pole.local.position = (0, -(monitor_h/2 + 50), -20)
        stand_pole.local.rotation = la.quat_from_euler((0, 0, 0))
        self.monitor_group.add(stand_pole)
        
        base = gfx.Mesh(
            gfx.cylinder_geometry(80, 80, 10),
            self.monitor_body_mat
        )
        base.local.position = (0, -(monitor_h/2 + 100), -20)
        base.local.rotation = la.quat_from_euler((1.57, 0, 0)) # Cylinder is Y-up, need it flat? No, default cylinder is usually Y-axis. 
        # Check pygfx cylinder: "The cylinder's axis is the y-axis."
        # So to make it a flat base on the ground (XZ plane), we rely on its dimensions.
        # 80 radius, 10 height. It's a flat disk in XZ if we do nothing? No, it's a disk in XZ if we rotate it?
        # If axis is Y, it stands up like a column.
        # We want a flat base. So axis should be Y (vertical). That's fine.
        # Wait, if axis is Y, the top and bottom circular faces are in XZ plane. Correct.
        self.monitor_group.add(base)
        
        self.scene.add(self.monitor_group)

    def init_mediapipe(self):
        model_path = display_utils.resolve_model_path(
            "models/hand_landmarker.task",
            "test/models/hand_landmarker.task",
        )
        
        print(f"Loading MediaPipe model from: {model_path}")
        if not display_utils.is_valid_model_asset(model_path):
            print(f"Error initializing MediaPipe: invalid model asset at {model_path}")
            self.detector = None
            return

        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            running_mode=vision.RunningMode.VIDEO
        )
        try:
            self.detector = vision.HandLandmarker.create_from_options(options)
            print("MediaPipe Initialized.")
        except Exception as e:
            print(f"Error initializing MediaPipe: {e}")
            self.detector = None

    def on_event(self, event):
        if event["event_type"] == "key_down":
            if event["key"] in ["q", "Escape"]:
                loop.stop()
                if self.cap: self.cap.release()

    def process_hands(self, result):
        if not result.hand_landmarks:
            self.last_hand_pos = None
            return

        left_hand = None
        right_hand = None
        
        for i, landmarks in enumerate(result.hand_landmarks):
            # classification = result.handedness[i][0]
            # label = classification.category_name 
            
            # NOTE: MediaPipe Selfie Mode (which we don't strictly set but assume standard webcam mirror behavior):
            # If we flipped the image, then:
            # - Left Hand (User's real left) appears on Left side of screen.
            # - "Left" label usually refers to "Left Hand" (anatomy).
            
            # Let's rely on x-coordinate if labels are confusing.
            # < 0.5 is Left side of screen (User's Left if mirrored).
            
            # However, robust way is using category_name.
            # Assuming flipped input:
            label = result.handedness[i][0].category_name
            
            if label == "Left":
                left_hand = landmarks
            else:
                right_hand = landmarks

        # 1. Left Hand Control: Rotate Monitor
        if left_hand:
            # Thumb (4) and Index (8)
            thumb = left_hand[4]
            index = left_hand[8]
            
            # Distance in normalized coords
            dist = math.hypot(thumb.x - index.x, thumb.y - index.y)
            
            # Pinch threshold
            if dist < 0.05:
                curr_pos = np.array([index.x, index.y])
                if self.last_hand_pos is not None:
                    delta = curr_pos - self.last_hand_pos
                    # delta.x -> Yaw (Y-axis rotation)
                    # delta.y -> Pitch (X-axis rotation)
                    
                    # Sensitivity
                    self.monitor_rot[1] += delta[0] * 5.0 
                    self.monitor_rot[0] += delta[1] * 5.0
                self.last_hand_pos = curr_pos
            else:
                self.last_hand_pos = None
        else:
            self.last_hand_pos = None

        # 2. Right Hand Control: Change Image
        if right_hand:
            thumb = right_hand[4]
            index = right_hand[8]
            dist = math.hypot(thumb.x - index.x, thumb.y - index.y)
            
            if dist < 0.05:
                if self.gesture_cooldown <= 0:
                    self.tex_manager.next_texture()
                    print("Switched Image")
                    self.gesture_cooldown = 30 # ~0.5s at 60fps
            
        if self.gesture_cooldown > 0:
            self.gesture_cooldown -= 1

        # Apply Rotation
        rot = la.quat_from_euler((self.monitor_rot[0], self.monitor_rot[1], 0))
        self.monitor_group.local.rotation = rot

    def animate(self):
        if not self.cap or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if ret:
            # Flip for mirror feeling
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            
            timestamp = int(time.time() * 1000)
            if self.detector:
                result = self.detector.detect_for_video(mp_img, timestamp)
                self.process_hands(result)
            
            # Update HUD
            # Resize logic must match texture size
            # tex.size is (width, height, depth) -> (640, 480, 1) usually in Pygfx 
            # numpy array is (height, width, channels) -> (480, 640, 4)
            # cv2.resize takes (width, height) -> (640, 480)
            
            target_w, target_h = 640, 480
            scaled_frame = cv2.resize(frame, (target_w, target_h))
            rgba_hud = cv2.cvtColor(scaled_frame, cv2.COLOR_BGR2RGBA)
            self.cam_tex.data[:] = rgba_hud
            self.cam_tex.update_range((0,0,0), self.cam_tex.size)
            
        # Update Monitor Texture
        current_tex = self.tex_manager.get_current_texture()
        if current_tex and self.monitor_screen_mat.map is not current_tex:
            self.monitor_screen_mat.map = current_tex

        # Build Viewport Rects
        # 1. Main Scene: Full Window
        self.renderer.render(self.scene, self.camera, flush=False)
        
        # 2. HUD: Bottom Right (or Top Right)
        # Using logical coordinates.
        w, h = self.canvas.get_logical_size()
        hud_w, hud_h = 320, 240
        # Position at bottom-right: (w - hud_w, h - hud_h) ? 
        # rendercanvas/wgpu coordinates often have (0,0) at top-left.
        # Let's try to verify visually. Logic: rect=(x, y, w, h)
        
        self.renderer.render(self.hud_scene, self.hud_camera, rect=(w - hud_w, h - hud_h, hud_w, hud_h), clear=False, flush=True)
        
        # Request next frame
        self.canvas.request_draw()

    def run(self):
        self.canvas.request_draw(self.animate)
        loop.run()

if __name__ == "__main__":
    app = VisualMonitorApp()
    app.run()
