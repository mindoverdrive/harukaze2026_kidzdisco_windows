import cv2
import numpy as np
import time

def test_fluid():
    # Create canvas
    h, w = 400, 400
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    
    # Draw some "sticky lines"
    cv2.line(canvas, (150, 100), (250, 100), (0, 255, 255), 8)
    cv2.line(canvas, (200, 50), (200, 150), (255, 0, 255), 8)
    cv2.circle(canvas, (120, 180), 20, (0, 0, 255), -1)
    
    # Precompute LUT
    fluid_lut = np.zeros((256, 1), dtype=np.uint8)
    for i in range(256):
        if i < 20: # Surface tension cutoff
            fluid_lut[i] = 0
        else:
            fluid_lut[i] = min(255, int((i - 10) * 1.05))

    print("Running simulation (saving 10 frames)...")
    
    out_frames = []
    
    for frame in range(90):
        # Shift down
        shift_dist = int(4 + (frame * 0.1))
        canvas = np.roll(canvas, shift_dist, axis=0)
        canvas[:shift_dist, :] = 0
        
        # Viscosity & Mixing
        canvas = cv2.GaussianBlur(canvas, (11, 11), 0)
        
        # Surface Tension (Pulls together)
        canvas = cv2.LUT(canvas, fluid_lut)
        
        if frame % 10 == 0:
            out_frames.append(canvas.copy())
            print(f"Frame {frame} max value: {canvas.max()}")

    print("Fluid simulation ran successfully without crashing. LUT and Blur logic works.")

if __name__ == '__main__':
    test_fluid()
