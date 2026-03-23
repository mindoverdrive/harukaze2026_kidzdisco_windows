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


def _person_roi_from_detection(detection, frame_w, frame_h):
    bbox = detection.location_data.relative_bounding_box
    face_x = int(bbox.xmin * frame_w)
    face_y = int(bbox.ymin * frame_h)
    face_w = max(1, int(bbox.width * frame_w))
    face_h = max(1, int(bbox.height * frame_h))

    center_x = face_x + face_w // 2
    roi_w = int(face_w * 3.8)
    top = face_y - int(face_h * 0.8)
    bottom = face_y + int(face_h * 6.0)
    left = center_x - roi_w // 2
    right = center_x + roi_w // 2

    left = max(0, left)
    top = max(0, top)
    right = min(frame_w, right)
    bottom = min(frame_h, bottom)
    if right - left < 32 or bottom - top < 32:
        return None
    return left, top, right, bottom

def main():
    # Initialize MediaPipe Pose
    mp_pose = mp.solutions.pose
    mp_face_detection = mp.solutions.face_detection
    pose = mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        model_complexity=2
    )
    face_detector = mp_face_detection.FaceDetection(
        model_selection=1,
        min_detection_confidence=0.5,
    )

    # Initialize Webcam
    cap = display_utils.open_camera()
    display_utils.setup_cv2_fullscreen('Skeleton Glitch')
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    # Store previous landmarks for velocity calculation
    prev_landmarks = {}
    
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
        
        # Create black background
        h, w, c = frame.shape
        canvas = np.zeros((h, w, c), dtype=np.uint8)
        current_people = {}
        face_results = face_detector.process(rgb_frame)
        detections = list(face_results.detections or [])
        detections.sort(key=lambda det: det.location_data.relative_bounding_box.xmin)

        for person_idx, detection in enumerate(detections[:3]):
            roi = _person_roi_from_detection(detection, w, h)
            if roi is None:
                continue
            x0, y0, x1, y1 = roi
            crop_rgb = rgb_frame[y0:y1, x0:x1]
            if crop_rgb.size == 0:
                continue
            results = pose.process(crop_rgb)
            if not results.pose_landmarks:
                continue

            landmarks = results.pose_landmarks.landmark
            current_landmarks_xy = np.array([
                ((x0 + lm.x * (x1 - x0)) / w, (y0 + lm.y * (y1 - y0)) / h)
                for lm in landmarks
            ])
            current_people[person_idx] = current_landmarks_xy

            velocities = np.zeros(len(landmarks))
            if person_idx in prev_landmarks:
                deltas = np.linalg.norm(current_landmarks_xy - prev_landmarks[person_idx], axis=1)
                velocities = deltas

            for start_idx, end_idx in CONNECTIONS:
                start_xy = current_landmarks_xy[start_idx]
                end_xy = current_landmarks_xy[end_idx]
                px_start = (int(start_xy[0] * w), int(start_xy[1] * h))
                px_end = (int(end_xy[0] * w), int(end_xy[1] * h))

                avg_velocity = (velocities[start_idx] + velocities[end_idx]) / 2.0

                if avg_velocity > VELOCITY_THRESHOLD:
                    glitch_colors = [(255, 255, 0), (255, 0, 255), (0, 255, 255)]
                    for color in glitch_colors:
                        offset_x = random.randint(-GLITCH_INTENSITY, GLITCH_INTENSITY)
                        offset_y = random.randint(-GLITCH_INTENSITY // 2, GLITCH_INTENSITY // 2)
                        vel_factor = min(avg_velocity * 100, 5)
                        offset_x = int(offset_x * vel_factor)
                        offset_y = int(offset_y * vel_factor)
                        thickness = random.randint(1, 4)
                        cv2.line(
                            canvas,
                            (px_start[0] + offset_x, px_start[1] + offset_y),
                            (px_end[0] + offset_x, px_end[1] + offset_y),
                            color,
                            thickness,
                        )

                    center_x = (px_start[0] + px_end[0]) // 2
                    center_y = (px_start[1] + px_end[1]) // 2
                    noise_prob = NOISE_DENSITY * min(avg_velocity * 50, 5.0)
                    if random.random() < noise_prob:
                        noise_w = random.randint(20, 100)
                        noise_h = random.randint(1, 4)
                        noise_x = center_x + random.randint(-50, 50)
                        noise_y = center_y + random.randint(-50, 50)
                        noise_color = random.choice([(255, 255, 255), (255, 255, 0), (255, 0, 255)])
                        cv2.rectangle(canvas, (noise_x, noise_y), (noise_x + noise_w, noise_y + noise_h), noise_color, -1)
                else:
                    cv2.line(canvas, px_start, px_end, (200, 200, 200), 2)

            for i, point_xy in enumerate(current_landmarks_xy):
                px = int(point_xy[0] * w)
                py = int(point_xy[1] * h)
                vel = velocities[i]
                if vel > VELOCITY_THRESHOLD:
                    radius = random.randint(3, 8)
                    for color in [(255, 0, 255), (0, 255, 255)]:
                        off_x = random.randint(-5, 5)
                        off_y = random.randint(-5, 5)
                        cv2.circle(canvas, (px + off_x, py + off_y), radius, color, 1)
                else:
                    cv2.circle(canvas, (px, py), 4, (255, 255, 255), -1)

        prev_landmarks = current_people

        # Display
        cv2.imshow('Skeleton Glitch', canvas)

        key = cv2.waitKey(5) & 0xFF
        if key == 27 or key == ord('q'):
            break

    pose.close()
    face_detector.close()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
