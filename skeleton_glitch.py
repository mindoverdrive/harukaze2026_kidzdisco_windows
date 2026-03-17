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
import time

def main():
    # Initialize MediaPipe Pose
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        model_complexity=1
    )

    # Initialize Webcam
    cap = cv2.VideoCapture(3)
    display_utils.setup_cv2_fullscreen('Skeleton Glitch')
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    # Store previous landmarks for velocity calculation
    prev_landmarks = None
    
    # Parameters
    VELOCITY_THRESHOLD = 0.005  # Threshold to trigger glitch
    GLITCH_INTENSITY = 10       # Max pixel offset for jitter
    NOISE_DENSITY = 0.1         # Probability of drawing noise
    
    # Bone connections (indices)
    CONNECTIONS = mp_pose.POSE_CONNECTIONS

    print("Press 'q' or 'Esc' to exit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Flip frame horizontally for mirror effect and convert to RGB
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Process with MediaPipe Pose
        results = pose.process(rgb_frame)
        
        # Create black background
        h, w, c = frame.shape
        canvas = np.zeros((h, w, c), dtype=np.uint8)

        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark
            
            # Current landmarks array (x, y)
            current_landmarks_xy = np.array([(lm.x, lm.y) for lm in landmarks])
            
            # Calculate velocity if previous landmarks exist
            velocities = np.zeros(len(landmarks))
            if prev_landmarks is not None:
                # Euclidean distance between current and previous positions
                deltas = np.linalg.norm(current_landmarks_xy - prev_landmarks, axis=1)
                velocities = deltas
            
            prev_landmarks = current_landmarks_xy
            
            # Draw connections (Bones)
            for connection in CONNECTIONS:
                start_idx = connection[0]
                end_idx = connection[1]
                
                # Get positions
                start_point = landmarks[start_idx]
                end_point = landmarks[end_idx]
                
                px_start = (int(start_point.x * w), int(start_point.y * h))
                px_end = (int(end_point.x * w), int(end_point.y * h))
                
                # Determine if this bone is moving (average velocity of endpoints)
                avg_velocity = (velocities[start_idx] + velocities[end_idx]) / 2.0
                
                if avg_velocity > VELOCITY_THRESHOLD:
                    # GLITCH EFFECT
                    # 1. RGB/CMY Split
                    # Colors: Cyan, Magenta, Yellow, White
                    glitch_colors = [(255, 255, 0), (255, 0, 255), (0, 255, 255)] 
                    
                    for color in glitch_colors:
                        offset_x = random.randint(-GLITCH_INTENSITY, GLITCH_INTENSITY)
                        offset_y = random.randint(-GLITCH_INTENSITY//2, GLITCH_INTENSITY//2) # Less vertical jitter
                        
                        # Apply stronger jitter for higher velocity
                        vel_factor = min(avg_velocity * 100, 5) # Cap multiplier
                        offset_x = int(offset_x * vel_factor)
                        offset_y = int(offset_y * vel_factor)

                        thickness = random.randint(1, 4)
                        cv2.line(canvas, 
                                 (px_start[0] + offset_x, px_start[1] + offset_y), 
                                 (px_end[0] + offset_x, px_end[1] + offset_y), 
                                 color, thickness)
                    
                    # 2. Digital Noise (Horizontal Scanlines/Blocks)
                    center_x = (px_start[0] + px_end[0]) // 2
                    center_y = (px_start[1] + px_end[1]) // 2
                    
                    # Probability increases with velocity
                    noise_prob = NOISE_DENSITY * min(avg_velocity * 50, 5.0)
                    
                    if random.random() < noise_prob:
                        noise_w = random.randint(20, 100)
                        noise_h = random.randint(1, 4)
                        noise_x = center_x + random.randint(-50, 50)
                        noise_y = center_y + random.randint(-50, 50)
                        
                        # Random Cyber Color
                        noise_color = random.choice([(255, 255, 255), (255, 255, 0), (255, 0, 255)])
                        cv2.rectangle(canvas, (noise_x, noise_y), (noise_x+noise_w, noise_y+noise_h), noise_color, -1)

                else:
                    # Stable Bone
                    cv2.line(canvas, px_start, px_end, (200, 200, 200), 2)

            # Draw Landmarks (Joints)
            for i, lm in enumerate(landmarks):
                px = int(lm.x * w)
                py = int(lm.y * h)
                
                # Check velocity
                vel = velocities[i]
                
                if vel > VELOCITY_THRESHOLD:
                    # Glitch Joint
                    radius = random.randint(3, 8)
                    for color in [(255, 0, 255), (0, 255, 255)]:
                        off_x = random.randint(-5, 5)
                        off_y = random.randint(-5, 5)
                        cv2.circle(canvas, (px + off_x, py + off_y), radius, color, 1)
                else:
                    # Stable Joint
                    cv2.circle(canvas, (px, py), 4, (255, 255, 255), -1)

        # Display
        cv2.imshow('Skeleton Glitch', canvas)

        key = cv2.waitKey(5) & 0xFF
        if key == 27 or key == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
