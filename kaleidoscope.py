import display_utils
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
import numpy as np
import math
import time

class KaleidoscopeEffect:
    def __init__(self, width, height, segments=8):
        self.width = width
        self.height = height
        self.segments = segments
        self.rotation = 0
        self.zoom = 1.0
        self.center = (width // 2, height // 2)
        
        # New parameters for complexity and color
        self.hue_shift = 0        # 0-179 for HSV hue rotation
        self.internal_spin = 0    # Internal image rotation
        self.overlay_segments = 12 # Different segment count for extra complexity
        self.overlay_rotation = 0
        self.projection_mode = 'flat' # 'flat', 'sphere', 'tunnel'
        self.color_boost = 1.0
        
        self.last_update_time = time.time()
        
        # Precompute mask for one segment (not strictly needed if drawing per frame, but kept for future opt)
        self._update_mask()
        
        # Precompute 3D maps
        self._init_3d_maps()

    def _update_mask(self):
        """Update the triangular mask used for one slice."""
        pass

    def _init_3d_maps(self):
        """Precompute maps for 3D projection effects."""
        # Create grid
        x, y = np.meshgrid(np.arange(self.width), np.arange(self.height))
        
        # Normalize to -1 to 1
        x_norm = (x - self.width / 2) / (self.width / 2)
        y_norm = (y - self.height / 2) / (self.height / 2)
        r = np.sqrt(x_norm**2 + y_norm**2)
        theta = np.arctan2(y_norm, x_norm)
        
        # Sphere Map
        # r -> asin(r) to simulate curvature
        # Clamp r to slightly less than 1 to avoid NaN
        r_clamped = np.clip(r, 0, 0.99)
        r_sphere = np.arcsin(r_clamped) * (2 / math.pi)
        
        self.map_sphere_x = (r_sphere * np.cos(theta) * (self.width / 2) + self.width / 2).astype(np.float32)
        self.map_sphere_y = (r_sphere * np.sin(theta) * (self.height / 2) + self.height / 2).astype(np.float32)
        
        # Tunnel Map
        # r -> 1/r (inverse distance)
        # Avoid division by zero
        r_tunnel = 1.0 / (r + 0.1) 
        self.map_tunnel_x = (r_tunnel * np.cos(theta) * (self.width / 2) + self.width / 2).astype(np.float32)
        self.map_tunnel_y = (r_tunnel * np.sin(theta) * (self.height / 2) + self.height / 2).astype(np.float32)

    def set_params(self, segments=None, rotation=None, zoom=None, center=None, 
                   hue_shift=None, internal_spin=None, overlay_segments=None,
                   overlay_rotation=None, projection_mode=None, color_boost=None):
        if segments is not None:
            self.segments = max(2, int(segments))
        if rotation is not None:
            self.rotation = rotation
        if zoom is not None:
            self.zoom = max(0.1, zoom)
        if center is not None:
            self.center = center
        if hue_shift is not None:
            self.hue_shift = int(hue_shift) % 180
        if internal_spin is not None:
            self.internal_spin = internal_spin
        if overlay_segments is not None:
            self.overlay_segments = max(2, int(overlay_segments))
        if overlay_rotation is not None:
            self.overlay_rotation = overlay_rotation
        if projection_mode is not None:
            self.projection_mode = projection_mode
        if color_boost is not None:
            self.color_boost = color_boost

    def apply_color_effects(self, frame, shift, boost):
        """Apply radial hue shift and saturation boost with contrast control."""
        if shift == 0 and boost == 1.0:
            return frame
            
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        
        # 1. Hue Shift
        if shift != 0:
            h = ((h.astype(np.int16) + shift) % 180).astype(np.uint8)

        # 2. Color Boost (Saturation & Value)
        # We reduce the value boost to prevent "whitening"
        if boost > 1.0:
            # S: Saturate colors more
            s = cv2.multiply(s, boost * 1.2)
            # V: Boost contrast instead of just brightness
            # Simple contrast: (v - 128) * contrast + 128
            v_float = v.astype(np.float32)
            v_float = (v_float - 128) * (1.0 + (boost - 1.0) * 0.5) + 128
            v = np.clip(v_float, 0, 255).astype(np.uint8)
            
        hsv_shifted = cv2.merge([h, s, v])
        return cv2.cvtColor(hsv_shifted, cv2.COLOR_HSV2BGR)

    def apply_projection(self, frame):
        """Apply 3D projection distortion."""
        if self.projection_mode == 'sphere':
            return cv2.remap(frame, self.map_sphere_x, self.map_sphere_y, cv2.INTER_LINEAR)
        elif self.projection_mode == 'tunnel':
            return cv2.remap(frame, self.map_tunnel_x, self.map_tunnel_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        return frame

    def process(self, frame):
        """Apply multiple layers of kaleidoscope effect and color shifts."""
        h, w = frame.shape[:2]
        
        # 0. Apply dynamic color shift and boost
        colored_frame = self.apply_color_effects(frame, self.hue_shift, self.color_boost)
        
        # 1. Base transformation (Zoom + External Rotation + Internal Spin)
        M = cv2.getRotationMatrix2D(self.center, self.rotation + self.internal_spin, self.zoom)
        transformed_base = cv2.warpAffine(colored_frame, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        
        # 2. Render Layer 1 (Main Structure)
        # Use mirror effect for classic kaleidoscope
        canvas1 = self._render_layer(transformed_base, self.segments, self.rotation, mirror=True)
        
        # 3. Render Layer 2 (Overlay/Ghosting for complexity)
        # Use different zoom/rotation 
        M2 = cv2.getRotationMatrix2D(self.center, self.overlay_rotation - self.internal_spin * 0.5, self.zoom * 1.5)
        transformed_overlay = cv2.warpAffine(colored_frame, M2, (w, h), borderMode=cv2.BORDER_REFLECT)
        canvas2 = self._render_layer(transformed_overlay, self.overlay_segments, self.overlay_rotation, mirror=False)
        
        # 4. Composite Layers
        # Use a more balanced weighting to maintain contrast
        composite = cv2.addWeighted(canvas1, 0.6, canvas2, 0.4, 0)
        
        # 5. Apply 3D Projection
        final = self.apply_projection(composite)
        
        return final

    def _render_layer(self, transformed, segments, rotation_offset, mirror=True):
        """Render a single kaleidoscope layer with specific segments."""
        h, w = transformed.shape[:2]
        canvas = np.zeros_like(transformed)
        
        angle_step = 360.0 / segments
        center = self.center
        radius = math.sqrt(w**2 + h**2)
        
        # Define wedge mask (slightly larger to avoid gaps)
        mask = np.zeros((h, w), dtype=np.uint8)
        epsilon = 0.5 
        angle_start = math.radians(-epsilon)
        angle_end = math.radians(angle_step + epsilon)
        
        p1 = center
        p2 = (int(center[0] + radius * math.cos(angle_start)), 
              int(center[1] + radius * math.sin(angle_start)))
        p3 = (int(center[0] + radius * math.cos(angle_end)), 
              int(center[1] + radius * math.sin(angle_end)))
              
        cv2.fillConvexPoly(mask, np.array([p1, p2, p3]), 255)
        
        # Extract the source wedge
        slice_img = cv2.bitwise_and(transformed, transformed, mask=mask)
        
        # If mirroring, we also need a flipped version of the wedge?
        # A true mirror flips across the wedge boundary. 
        # Simpler aesthetic approximation: 
        # If mirror=True, every odd segment uses a flipped version of the source image.
        if mirror:
             # Create a horizontally flipped version of the source slice
             # We flip around the center y-axis of the wedge (which is at angle_step/2) - Hard to do simply.
             # Alternatively, flip the *entire* transformed image horizontally before extracting slice?
             # Let's try flipping the slice itself around the x-axis of the image? No.
             
             # Simplest visually pleasing mirror: Flip the source content horizontally before masking.
             mirrored_transformed = cv2.flip(transformed, 1)
             slice_img_mirror = cv2.bitwise_and(mirrored_transformed, mirrored_transformed, mask=mask)
        
        for i in range(segments):
            angle = i * angle_step
            
            # Choose source slice
            if mirror and (i % 2 == 1):
                src = slice_img_mirror
            else:
                src = slice_img
                
            # Rotate into position
            # origin of slice is at 0 degrees. We rotate by 'angle'.
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            
            # Warping the already masked slice
            # BORDER_TRANSPARENT is important so we don't overwrite with black
            # But warpAffine doesn't support BORDER_TRANSPARENT for the destination canvas directly in python elegantly
            # (It overwrites). We need to warp to a temp buffer and add.
            
            rotated_slice = cv2.warpAffine(src, M, (w, h))
            
            # Composite
            # Maximum or Add? Add creates light bloom. Max preserves structure.
            # Let's use Max to avoid blowing out to white too fast.
            canvas = cv2.max(canvas, rotated_slice)
            
        return canvas

    def apply_flashy_effects(self, frame, intensity=0.5):
        """Add chromatic aberration, Bloom, and Vignette for deep contrast."""
        if intensity <= 0:
            return frame
            
        h, w = frame.shape[:2]

        # 1. Chromatic Aberration
        b, g, r = cv2.split(frame)
        shift = int(12 * intensity)
        
        M_r = np.float32([[1, 0, shift], [0, 1, 0]])
        M_b = np.float32([[1, 0, -shift], [0, 1, 0]])
        
        r = cv2.warpAffine(r, M_r, (w, h), borderMode=cv2.BORDER_REFLECT)
        b = cv2.warpAffine(b, M_b, (w, h), borderMode=cv2.BORDER_REFLECT)
        
        aberration = cv2.merge([b, g, r])
        
        # 2. Vignette (Darkening the edges for depth)
        # Create a radial gradient mask
        kernel_x = cv2.getGaussianKernel(w, w/2)
        kernel_y = cv2.getGaussianKernel(h, h/2)
        vignette_mask = kernel_y * kernel_x.T
        vignette_mask = vignette_mask / vignette_mask.max()
        # Scale the mask impact by intensity
        vignette_mask = 1.0 - (1.0 - vignette_mask) * (0.5 + 0.5 * intensity)
        
        # Apply vignette
        vignette = (aberration.astype(np.float32) * vignette_mask[:, :, np.newaxis]).astype(np.uint8)

        # 3. Bloom (Glow) but more subtle
        small = cv2.resize(vignette, (0,0), fx=0.5, fy=0.5)
        blur = cv2.GaussianBlur(small, (15, 15), 0)
        blur_up = cv2.resize(blur, (w, h))
        
        # Add glow only to highlights (thresholded)
        gray_blur = cv2.cvtColor(blur_up, cv2.COLOR_BGR2GRAY)
        _, highlight_mask = cv2.threshold(gray_blur, 150, 255, cv2.THRESH_BINARY)
        highlight_mask = highlight_mask[:, :, np.newaxis] / 255.0
        
        bloom = cv2.addWeighted(vignette, 1.0, (blur_up * highlight_mask).astype(np.uint8), intensity * 0.5, 0)
        
        return bloom

if __name__ == "__main__":
    # Test script in main
    video_source = 2
    cap = display_utils.open_camera()
    if not cap.isOpened():
        cap = display_utils.open_camera() # Try alternate
    display_utils.setup_cv2_fullscreen("Kaleidoscope 2.0 Test")
        
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Force reasonable resolution
    if width > 1280: width = 1280
    if height > 720: height = 720
    
    kaleido = KaleidoscopeEffect(width, height, segments=12)
    
    print("Controls:")
    print(" [1] Flat Mode")
    print(" [2] Sphere Mode")
    print(" [3] Tunnel Mode")
    print(" [q] Quit")
    
    start_time = time.time()
    
    while True:
        ret, frame = cap.read()
        if not ret: break
        
        frame = cv2.resize(frame, (width, height))
        
        # Animate params
        t = time.time() - start_time
        seg = int(12 + 6 * math.sin(t * 0.5))
        rot = t * 15
        zoom = 1.0 + 0.3 * math.sin(t * 0.3)
        hue = int(t * 20) % 180
        
        kaleido.set_params(
            segments=seg, 
            rotation=rot, 
            zoom=zoom, 
            hue_shift=hue,
            internal_spin=t * 30,
            overlay_rotation=-rot,
            color_boost=1.5
        )
        
        # Demo: Cycle modes
        cycle = int(t / 5) % 3
        # Override manual control for demo if desired, but let's stick to manual override priority logic if we had it.
        # Just use keyboard for mode switching in this test.
        
        out = kaleido.process(frame)
        out = kaleido.apply_flashy_effects(out, intensity=0.6)
        
        cv2.imshow("Kaleidoscope 2.0 Test", out)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('1'):
            print("Switched to Flat")
            kaleido.projection_mode = 'flat'
        elif key == ord('2'):
            print("Switched to Sphere")
            kaleido.projection_mode = 'sphere'
        elif key == ord('3'):
            print("Switched to Tunnel")
            kaleido.projection_mode = 'tunnel'
            
    cap.release()
    cv2.destroyAllWindows()
