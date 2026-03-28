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
import cv2
import mediapipe as mp
import numpy as np
import math
import random
import time
import pygfx as gfx
import colorsys
import display_utils
from rendercanvas.auto import RenderCanvas, loop

_DU_W, _DU_H, _DU_X, _DU_Y = display_utils.get_second_monitor_size()
WINDOW_WIDTH = _DU_W
WINDOW_HEIGHT = _DU_H
MAX_BASE_POINTS = 7500
MAX_RED_POINTS = 35000

class FacePinch3DApp:
    def __init__(self):
        # ========== 1. Canvas & Renderer ==========
        self.canvas = RenderCanvas(size=(WINDOW_WIDTH, WINDOW_HEIGHT), title="3D Face Pinch Fire")
        display_utils.setup_rendercanvas_fullscreen(self.canvas)
        self.renderer = gfx.renderers.WgpuRenderer(self.canvas)

        # ========== 2. MediaPipe Setup ==========
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(model_complexity=1, 
            max_num_hands=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        # ========== 3. Camera ==========
        self.cap = display_utils.open_camera()
        if not self.cap.isOpened():
            self.cap = display_utils.open_camera()
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, WINDOW_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, WINDOW_HEIGHT)

        # ========== 4. Build Scenes ==========
        self._build_bg_scene()
        self._build_main_scene()

        # State
        self.fire_intensity = 0.0

        # Key handler
        self.canvas.add_event_handler(self._on_key, "key_down")

    # ------------------------------------------------------------------
    def _on_key(self, event):
        key = event.get("key", "")
        if key.lower() in ("q", "escape"):
            loop.stop()

    # ------------------------------------------------------------------
    def _build_bg_scene(self):
        self.bg_scene = gfx.Scene()
        # OrthographicCamera sized to match the camera texture resolution
        self.bg_camera = gfx.OrthographicCamera(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.bg_camera.local.position = (0, 0, 1000)
        self.bg_camera.look_at((0, 0, 0))

        self.cam_tex = gfx.Texture(
            np.zeros((WINDOW_HEIGHT, WINDOW_WIDTH, 4), dtype=np.uint8), dim=2
        )
        plane = gfx.Mesh(
            gfx.plane_geometry(WINDOW_WIDTH, WINDOW_HEIGHT),
            gfx.MeshBasicMaterial(map=self.cam_tex),
        )
        self.bg_scene.add(plane)

    # ------------------------------------------------------------------
    def _build_main_scene(self):
        self.scene = gfx.Scene()
        self.camera = gfx.OrthographicCamera(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.camera.local.position = (0, 0, 1000)
        self.camera.look_at((0, 0, 0))

        # --- Base White Face ---
        b_fp = np.zeros((MAX_BASE_POINTS, 3), dtype=np.float32)
        b_fc = np.zeros((MAX_BASE_POINTS, 4), dtype=np.float32)
        b_fs = np.full(MAX_BASE_POINTS, 1.0, dtype=np.float32)

        self.base_geo = gfx.Geometry(
            positions=gfx.Buffer(b_fp),
            colors=gfx.Buffer(b_fc),
            sizes=gfx.Buffer(b_fs),
        )
        self.base_pts = gfx.Points(
            self.base_geo,
            gfx.PointsMaterial(
                color_mode="vertex", size_mode="vertex", size_space="screen",
                depth_test=False
            ),
        )
        self.scene.add(self.base_pts)

        # --- Pinch Red Face (Expanded Face) ---
        r_fp = np.zeros((MAX_RED_POINTS, 3), dtype=np.float32)
        r_fc = np.zeros((MAX_RED_POINTS, 4), dtype=np.float32)
        r_fs = np.full(MAX_RED_POINTS, 1.0, dtype=np.float32)

        self.red_geo = gfx.Geometry(
            positions=gfx.Buffer(r_fp),
            colors=gfx.Buffer(r_fc),
            sizes=gfx.Buffer(r_fs),
        )
        self.red_pts = gfx.Points(
            self.red_geo,
            gfx.PointsMaterial(
                color_mode="vertex", size_mode="vertex", size_space="screen",
                depth_test=False
            ),
        )
        self.scene.add(self.red_pts)

        # --- Pinch Line ---
        lp = np.zeros((2, 3), dtype=np.float32)
        lc = np.ones((2, 4), dtype=np.float32)
        self.line_geo = gfx.Geometry(
            positions=gfx.Buffer(lp), colors=gfx.Buffer(lc)
        )
        self.pinch_line = gfx.Line(
            self.line_geo,
            gfx.LineMaterial(thickness=6.0, color_mode="vertex"),
        )
        self.scene.add(self.pinch_line)

    # ------------------------------------------------------------------
    @staticmethod
    def _mp_to_world(mx, my, w, h):
        """Convert MediaPipe normalised xy to pygfx world xy."""
        return (mx - 0.5) * w, -(my - 0.5) * h

    # ------------------------------------------------------------------
    def animate(self):
        ret, frame = self.cap.read()
        if not ret:
            return

        # Selfie-flip
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        w, h = WINDOW_WIDTH, WINDOW_HEIGHT

        # ---- Background texture update ----
        rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        self.cam_tex.data[:] = rgba
        self.cam_tex.update_range((0, 0, 0), self.cam_tex.size)

        # ---- MediaPipe inference ----
        face_results = self.face_mesh.process(rgb)
        hands_results = self.hands.process(rgb)

        # ---- Hands → fire_intensity ----
        self.fire_intensity = 0.0
        if hands_results.multi_hand_landmarks:
            hl = hands_results.multi_hand_landmarks[0]
            thumb = hl.landmark[self.mp_hands.HandLandmark.THUMB_TIP]
            index = hl.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_TIP]

            dist_px = math.hypot(
                (thumb.x - index.x) * w, (thumb.y - index.y) * h
            )
            # Reaches maximum intensity (and Red color) at 2/3 the previous distance (~200px instead of ~300px)
            self.fire_intensity = max(0.0, min(1.0, (dist_px - 10) / 190.0))

            # Pinch line in world coords
            tx, ty = self._mp_to_world(thumb.x, thumb.y, w, h)
            ix, iy = self._mp_to_world(index.x, index.y, w, h)
            lp = self.line_geo.positions.data
            lp[0] = [tx, ty, 5]
            lp[1] = [ix, iy, 5]
            self.line_geo.positions.update_range(0, 2)

            r = 1.0
            g = 1.0 - self.fire_intensity
            lc = self.line_geo.colors.data
            lc[0] = [r, g, 0, 1]
            lc[1] = [r, g, 0, 1]
            self.line_geo.colors.update_range(0, 2)
        else:
            lp = self.line_geo.positions.data
            lp[:] = [0, -9999, 0]
            self.line_geo.positions.update_range(0, 2)

        # ---- Face mesh logic ----
        bfp = self.base_geo.positions.data
        bfc = self.base_geo.colors.data
        bfs = self.base_geo.sizes.data
        n_base = 0

        rfp = self.red_geo.positions.data
        rfc = self.red_geo.colors.data
        rfs = self.red_geo.sizes.data
        n_red = 0

        scale = 1.0

        if face_results.multi_face_landmarks:
            for face_lm in face_results.multi_face_landmarks:
                lms = face_lm.landmark

                # ---- Face center for scaling ----
                cx_mp = sum(l.x for l in lms) / len(lms)
                cy_mp = sum(l.y for l in lms) / len(lms)
                cx_w, cy_w = self._mp_to_world(cx_mp, cy_mp, w, h)

                # ---- Dense point cloud ----
                dense = []
                for l in lms:
                    dense.append((l.x, l.y, l.z))
                for si, ti in self.mp_face_mesh.FACEMESH_TESSELATION:
                    s = lms[si]; t = lms[ti]
                    dense.append(((s.x+t.x)*0.5, (s.y+t.y)*0.5, (s.z+t.z)*0.5))

                offset_x_px = 350
                offsets = [-offset_x_px, offset_x_px]

                for off in offsets:
                    for (px, py, pz) in dense:
                        if n_base >= MAX_BASE_POINTS:
                            break

                        # Base Face: World position following current face exactly
                        wx, wy = self._mp_to_world(px, py, w, h)
                        wx_base = cx_w + off + (wx - cx_w) * scale
                        wy_base = cy_w + (wy - cy_w) * scale

                        # depth → bright (white base)
                        depth = np.clip((pz + 0.05) / 0.1, 0, 1)
                        bright = 1.0 - 0.4 * depth
                        # Pure white
                        cr, cg, cb = bright, bright, bright
                        rad = max(2.0, 4.0 * bright)

                        # small jitter
                        j_amp = 1.0 * (scale / 0.4)
                        jx = random.uniform(-j_amp, j_amp)
                        jy = random.uniform(-j_amp, j_amp)

                        w_final_x = wx_base + jx
                        w_final_y = wy_base + jy

                        bfp[n_base] = [w_final_x, w_final_y, pz * -200.0] 
                        bfc[n_base] = [cr, cg, cb, 1]
                        bfs[n_base] = rad
                        n_base += 1

                        # Pinch Expanded Face (up to 2x size) + Scatter Particles
                        if self.fire_intensity > 0.05:
                            if n_red >= MAX_RED_POINTS:
                                continue

                            red_scale = scale + self.fire_intensity * 1.5 # 1.0 to 2.5x
                            wx_red = cx_w + off + (wx - cx_w) * red_scale
                            wy_red = cy_w + (wy - cy_w) * red_scale
                            
                            # Base expanded point
                            r_j_amp = 1.0 * (red_scale / 0.4)
                            rjx = random.uniform(-r_j_amp, r_j_amp)
                            rjy = random.uniform(-r_j_amp, r_j_amp)
                            r_final_x = wx_red + rjx
                            r_final_y = wy_red + rjy
                            
                            # Smoothly transition hue based on pinch intensity.
                            hue = 0.6 * (1.0 - self.fire_intensity)
                            # Start white (saturation 0) at low intensity, and safely ramp up to full color
                            sat = max(0.0, min(1.0, (self.fire_intensity - 0.05) * 4.0))
                            rr, rg, rb = colorsys.hsv_to_rgb(hue, sat, bright)
                            r_rad = max(2.0, 4.0 * bright * (1.0 + self.fire_intensity * 0.5))
                            
                            rfp[n_red] = [r_final_x, r_final_y, pz * -200.0 * red_scale + 2.0]
                            rfc[n_red] = [rr, rg, rb, 1]
                            rfs[n_red] = r_rad
                            n_red += 1

                            # Extra Scatter Points around the expanded mesh
                            num_scatter_attempts = int(self.fire_intensity * 4)
                            for _ in range(num_scatter_attempts):
                                if n_red >= MAX_RED_POINTS:
                                    break
                                if random.random() < self.fire_intensity * 0.6:
                                    spread = random.uniform(5.0, 150.0 * self.fire_intensity)
                                    angle = random.uniform(0, math.pi * 2)
                                    sx = r_final_x + math.cos(angle) * spread
                                    sy = r_final_y + math.sin(angle) * spread
                                    
                                    # Scattered points are smaller and maybe slightly transparent
                                    sz = pz * -200.0 * red_scale + random.uniform(-20, 50)
                                    s_rad = r_rad * random.uniform(0.3, 0.8)
                                    
                                    rfp[n_red] = [sx, sy, sz]
                                    # Slightly alter brightness of scattered points
                                    s_bright = bright * random.uniform(0.6, 1.0)
                                    s_sat = sat * random.uniform(0.5, 1.0)
                                    srb, srg, srr = colorsys.hsv_to_rgb(hue, s_sat, s_bright)
                                    rfc[n_red] = [srb, srg, srr, random.uniform(0.5, 0.9)]
                                    rfs[n_red] = s_rad
                                    n_red += 1

        # Hide unused base face points
        if n_base < MAX_BASE_POINTS:
            bfp[n_base:] = [0, -9999, 0]
            bfc[n_base:] = [0, 0, 0, 0]
            bfs[n_base:] = 0
        self.base_geo.positions.update_range()
        self.base_geo.colors.update_range()
        self.base_geo.sizes.update_range()

        # Hide unused red face points
        if n_red < MAX_RED_POINTS:
            rfp[n_red:] = [0, -9999, 0]
            rfc[n_red:] = [0, 0, 0, 0]
            rfs[n_red:] = 0
        self.red_geo.positions.update_range()
        self.red_geo.colors.update_range()
        self.red_geo.sizes.update_range()

        # ---- Render ----
        try:
            self.renderer.render(self.bg_scene, self.bg_camera, flush=False)
        except RuntimeError:
            pass
        try:
            self.renderer.render(self.scene, self.camera, clear=False)
        except RuntimeError:
            pass
        self.canvas.request_draw()

    # ------------------------------------------------------------------
    def run(self):
        self.canvas.request_draw(self.animate)
        loop.run()

    def cleanup(self):
        if getattr(self, "cap", None) is not None:
            self.cap.release()
        hands = getattr(self, "hands", None)
        if hands is not None and hasattr(hands, "close"):
            hands.close()
        face_mesh = getattr(self, "face_mesh", None)
        if face_mesh is not None and hasattr(face_mesh, "close"):
            face_mesh.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    app = FacePinch3DApp()
    try:
        app.run()
    finally:
        app.cleanup()
