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
import display_utils
import mediapipe as mp
import numpy as np
import random
import math
import time

class Particle:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.reset()
        
    def reset(self):
        side = random.choice(['top', 'bottom', 'left', 'right'])
        if side == 'top':
            self.x = random.randint(0, self.w)
            self.y = random.randint(-50, 0)
        elif side == 'bottom':
            self.x = random.randint(0, self.w)
            self.y = random.randint(self.h, self.h + 50)
        elif side == 'left':
            self.x = random.randint(-50, 0)
            self.y = random.randint(0, self.h)
        else:
            self.x = random.randint(self.w, self.w + 50)
            self.y = random.randint(0, self.h)
            
        self.tx = None
        self.ty = None
        self.active = False
        self.color = (255, 255, 255)
        self.speed = random.uniform(0.15, 0.25)
        self.radius = random.randint(2, 4)
        self.max_dist = 15

    def set_target(self, tx, ty, color):
        self.tx = tx
        self.ty = ty
        self.color = color
        self.active = True

    def update(self):
        if self.active and self.tx is not None:
            self.x += (self.tx - self.x) * self.speed
            self.y += (self.ty - self.y) * self.speed
            
            dist = math.hypot(self.tx - self.x, self.ty - self.y)
            if dist < self.max_dist:
                self.reset()
        else:
            # Drift if not active
            self.x += random.uniform(-1, 1)
            self.y += random.uniform(-1, 1)

    def draw(self, img):
        if self.active:
            # Draw with a slight glow (simulated by a larger, fainter circle)
            overlay = img.copy()
            cv2.circle(overlay, (int(self.x), int(self.y)), self.radius + 2, self.color, -1)
            cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
            cv2.circle(img, (int(self.x), int(self.y)), self.radius, (255, 255, 255), -1)

def draw_sci_fi_overlay(img, rect, color, frame_count):
    x, y, w, h = rect
    
    # Glitch offset
    gx = random.randint(-2, 2)
    gy = random.randint(-2, 2)
    x += gx
    y += gy
    
    line_len = min(w, h) // 4
    thickness = 2
    draw_color = (255, 255, 255)
    
    # Corners
    cv2.line(img, (x, y), (x + line_len, y), draw_color, thickness)
    cv2.line(img, (x, y), (x, y + line_len), draw_color, thickness)
    
    cv2.line(img, (x + w, y), (x + w - line_len, y), draw_color, thickness)
    cv2.line(img, (x + w, y), (x + w, y + line_len), draw_color, thickness)
    
    cv2.line(img, (x, y + h), (x + line_len, y + h), draw_color, thickness)
    cv2.line(img, (x, y + h), (x, y + h - line_len), draw_color, thickness)
    
    cv2.line(img, (x + w, y + h), (x + w - line_len, y + h), draw_color, thickness)
    cv2.line(img, (x + w, y + h), (x + w, y + h - line_len), draw_color, thickness)
    
    # Scanline
    scan_speed = 0.1
    scan_y = y + int(((math.sin(frame_count * scan_speed) + 1) / 2) * h)
    cv2.line(img, (x, scan_y), (x + w, scan_y), color, 1)
    
    # Text
    label = f"SUBJECT DETECTED [{hex(id(rect) % 1000)}]"
    cv2.putText(img, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, draw_color, 1)
    
    # Hex Color
    hex_color = f"#{color[2]:02X}{color[1]:02X}{color[0]:02X}"
    cv2.putText(img, f"MAT: {hex_color}", (x, y + h + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

def main():
    mp_selfie_segmentation = mp.solutions.selfie_segmentation
    segmentation = mp_selfie_segmentation.SelfieSegmentation(model_selection=1)

    cap = cv2.VideoCapture(3)
    if not cap.isOpened():
        cap = cv2.VideoCapture(3)
    display_utils.setup_cv2_fullscreen('Sci-Fi Jacket Effect')
    if not cap.isOpened():
        print("Camera not found.")
        return

    particles = [Particle(640, 480) for _ in range(200)]
    frame_count = 0

    print("Press 'q' to exit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.resize(frame, (640, 480))
        frame = cv2.flip(frame, 1)
        h, w, c = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Segmentation
        seg_results = segmentation.process(rgb_frame)
        mask = seg_results.segmentation_mask
        
        # Binary mask for contours
        binary_mask = (mask > 0.5).astype(np.uint8) * 255
        
        # Find Contours (People)
        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter contours by size
        valid_targets = []
        for cnt in contours:
            if cv2.contourArea(cnt) > 2000: # Min area threshold
                x, y, cw, ch = cv2.boundingRect(cnt)
                
                # Extract Color from visual center (approx upper body)
                # Sample region: center x, upper 1/3 y
                sample_x = x + cw // 2
                sample_y = y + ch // 3
                
                # Ensure within bounds
                sample_x = max(0, min(w-1, sample_x))
                sample_y = max(0, min(h-1, sample_y))
                
                # Sample a small 10x10 patch
                patch_x = max(0, sample_x - 5)
                patch_y = max(0, sample_y - 5)
                patch_w_sz = min(w, patch_x + 10) - patch_x
                patch_h_sz = min(h, patch_y + 10) - patch_y
                
                patch = frame[patch_y:patch_y+patch_h_sz, patch_x:patch_x+patch_w_sz]
                if patch.size > 0:
                    mean_color = cv2.mean(patch)
                    target_color = (int(mean_color[0]), int(mean_color[1]), int(mean_color[2]))
                else:
                    target_color = (255, 255, 255)
                
                valid_targets.append({
                    'rect': (x, y, cw, ch),
                    'color': target_color,
                    'mask': binary_mask # We use the full mask, but could crop
                })

        # Draw Output
        # Darken background
        bg_image = np.zeros(frame.shape, dtype=np.uint8)
        output_image = cv2.addWeighted(frame, 0.3, bg_image, 0.7, 0)
        
        # Highlight people
        person_layer = cv2.bitwise_and(frame, frame, mask=binary_mask)
        output_image = np.where(binary_mask[:,:,None] > 0, frame, output_image)
        
        # Draw HUD and Assignments
        for target in valid_targets:
            draw_sci_fi_overlay(output_image, target['rect'], target['color'], frame_count)
        
        # Update Particles
        for p in particles:
            if not p.active:
                if valid_targets:
                    # Pick a random target
                    target = random.choice(valid_targets)
                    tx = target['rect'][0] + random.randint(0, target['rect'][2])
                    ty = target['rect'][1] + random.randint(0, target['rect'][3])
                    
                    # Verify point is in mask
                    if binary_mask[min(ty, h-1), min(tx, w-1)] > 0:
                        p.set_target(tx, ty, target['color'])
            
            p.update()
            p.draw(output_image)

        cv2.imshow('Sci-Fi Jacket Effect', output_image)
        
        frame_count += 1
        if cv2.waitKey(5) & 0xFF == ord('q'):
            break
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
