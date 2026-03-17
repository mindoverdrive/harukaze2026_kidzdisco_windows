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
# 右手の指の本数に応じて描画の色が変わるように変更して。
# また、左手の指が、他の数から5本に変わると画がリセットされて、新たに描画できるように変えて。


import cv2
import display_utils
import mediapipe as mp
import numpy as np
import math
import time
# MediaPipe Initialization
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles
def distance(p1, p2):
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

def count_fingers(hand_landmarks, label):
    """Count raised fingers for a single hand landmarks.
    Uses simple heuristic: for index/middle/ring/pinky compare tip.y with pip.y.
    For thumb, use x comparison depending on handedness.
    Returns int in range 0-5.
    """
    tips_ids = [4, 8, 12, 16, 20]
    count = 0
    # Thumb
    thumb_tip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
    thumb_ip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_IP]
    if label == "Right":
        if thumb_tip.x < thumb_ip.x:
            count += 1
    else:
        if thumb_tip.x > thumb_ip.x:
            count += 1
    # Other fingers (index, middle, ring, pinky)
    for tip_id in tips_ids[1:]:
        tip = hand_landmarks.landmark[tip_id]
        pip = hand_landmarks.landmark[tip_id - 2]
        if tip.y < pip.y:
            count += 1
    return count

def animate_wipe_left_to_right(canvas_img, ref_img, duration=0.3):
    """Animate clearing the canvas from left to right over `duration` seconds."""
    h, w, _ = canvas_img.shape
    steps = max(6, int(duration * 60))
    delay_ms = max(1, int((duration / steps) * 1000))
    for i in range(1, steps + 1):
        wipe_x = int(w * (i / steps))
        temp = canvas_img.copy()
        if wipe_x > 0:
            temp[:, :wipe_x] = 0
        gray_temp = cv2.cvtColor(temp, cv2.COLOR_BGR2GRAY)
        _, mask_temp = cv2.threshold(gray_temp, 10, 255, cv2.THRESH_BINARY)
        display = ref_img.copy()
        display[mask_temp > 0] = temp[mask_temp > 0]
        cv2.imshow('Hand Drawing App', display)
        if cv2.waitKey(delay_ms) & 0xFF == ord('q'):
            break
    canvas_img[:] = 0
def main():
    # Initialize Hands
    hands = mp_hands.Hands(
        model_complexity=0,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
        max_num_hands=2
    )
    cap = cv2.VideoCapture(3)
    display_utils.setup_cv2_fullscreen('Hand Drawing App')
    # Canvas for drawing
    canvas = None
    
    # State variables
    prev_index_finger_pos = None # For Right Hand drawing
    prev_left_hand_x = None      # For Left Hand swipe detection
    prev_left_finger_count = None # For Left Hand 5-finger reset detection
    
    # Constants
    SWIPE_THRESHOLD = 0.15 # Normalized coordinate distance per frame for swipe
    DRAW_COLOR = (0, 255, 255) # Yellow
    THICKNESS = 5
    print("Controls:")
    print("  Right Hand Index Finger: Draw")
    print("  Left Hand Swipe: Clear Canvas")
    print("  'q': Quit")
    while cap.isOpened():
        success, image = cap.read()
        if not success:
            print("Ignoring empty camera frame.")
            continue
        # Flip the image horizontally for a selfie-view display.
        image = cv2.flip(image, 1)
        h, w, c = image.shape
        
        # Initialize canvas if not created (or if size changes)
        if canvas is None or canvas.shape != image.shape:
             canvas = np.zeros_like(image)
        # To improve performance, optionally mark the image as not writeable to
        # pass by reference.
        image.flags.writeable = False
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = hands.process(image)
        # Draw the hand annotations on the image.
        image.flags.writeable = True
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        current_right_index_pos = None
        current_left_hand_x = None
        current_right_finger_count = None
        current_left_finger_count = None
        if results.multi_hand_landmarks:
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                # Draw landmarks
                mp_drawing.draw_landmarks(
                    image,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style())
                # Get Hand Label (Left or Right)
                # Note: MediaPipe assumes mirrored input for 'Left'/'Right' labels? 
                # Actually, after cv2.flip(image, 1), the image is mirrored. 
                # MediaPipe processes the mirrored image. 
                # Usually: Left hand appears on Left side of screen (which is actually Right side of world if mirrored).
                # Label 'Left' usually means the person's left hand.
                
                label = handedness.classification[0].label # "Left" or "Right"
                # Count fingers for this hand
                fingers = count_fingers(hand_landmarks, label)
                if label == "Right":
                    current_right_finger_count = fingers
                else:
                    current_left_finger_count = fingers
                if label == "Right":
                    # Drawing Logic (Index Finger Tip: 8)
                    index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                    current_right_index_pos = (int(index_tip.x * w), int(index_tip.y * h))
                
                if label == "Left":
                    # Clear Logic (Left Hand Swipe)
                    # We track the wrist or average x position
                    wrist = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
                    current_left_hand_x = wrist.x
                    
                    # Check if hand is "Open" (optional, for safety to avoid accidental clears)
                    # Simple check: fingertips are above wrist? Or just assume if left hand is present.
                    # Let's keep it simple: Swipe detection is main trigger.
        # Choose draw color based on right-hand finger count
        COLOR_MAP = {
            1: (0, 0, 255),    # Red
            2: (0, 255, 0),    # Green
            3: (255, 0, 0),    # Blue
            4: (0, 255, 255),  # Yellow
            5: (255, 0, 255),  # Magenta
        }

        # Process Drawing: draw only when right index is present and at least one finger detected
        if current_right_index_pos and current_right_finger_count and current_right_finger_count > 0:
            draw_color = COLOR_MAP.get(current_right_finger_count, (0, 255, 255))
            if prev_index_finger_pos:
                cv2.line(canvas, prev_index_finger_pos, current_right_index_pos, draw_color, THICKNESS)
            prev_index_finger_pos = current_right_index_pos
        else:
            prev_index_finger_pos = None
        # Process Clearing
        # Swipe-based clear (existing behavior)
        if current_left_hand_x is not None and prev_left_hand_x is not None:
            # Check delta
            delta_x = current_left_hand_x - prev_left_hand_x
            # Simple swipe detection: fast horizontal movement
            if abs(delta_x) > SWIPE_THRESHOLD:
                animate_wipe_left_to_right(canvas, image, duration=1.0)
                print("Canvas Cleared by swipe!")

        if current_left_hand_x is not None:
             prev_left_hand_x = current_left_hand_x
        else:
             prev_left_hand_x = None # Reset if hand lost

        # Left-hand 5-finger reset: only trigger when left hand count changes from a different number to 5
        if current_left_finger_count is not None:
            if prev_left_finger_count is not None and prev_left_finger_count != 5 and current_left_finger_count == 5:
                animate_wipe_left_to_right(canvas, image, duration=1.0)
                print("Canvas reset: Left hand changed to 5 fingers")
            prev_left_finger_count = current_left_finger_count
        else:
            prev_left_finger_count = None
        # Setup display
        # Combine image and canvas
        # Create mask of drawn area to overlay color
        gray_canvas = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray_canvas, 10, 255, cv2.THRESH_BINARY)
        
        # Copy canvas color to image where mask is set
        # Alternatively, just addWeighted usually works well for black background
        # image = cv2.addWeighted(image, 1.0, canvas, 1.0, 0) # This makes colors blend.
        
        # For solid drawing:
        image[mask > 0] = canvas[mask > 0]
        cv2.imshow('Hand Drawing App', image)
        if cv2.waitKey(5) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()
if __name__ == "__main__":
    main()