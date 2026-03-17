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

# MediaPipe Initialization
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

def distance(p1, p2):
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

def main():
    # Initialize Hands
    hands = mp_hands.Hands(
        model_complexity=0,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
        max_num_hands=2
    )

    cap = cv2.VideoCapture(2)
    cv2.namedWindow('Hand Drawing App', cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty('Hand Drawing App', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    
    # Canvas for drawing
    canvas = None
    
    # State variables
    prev_index_finger_pos = None # For Right Hand drawing
    prev_left_hand_x = None      # For Left Hand swipe detection
    
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

        # Process Drawing
        if current_right_index_pos:
            if prev_index_finger_pos:
                cv2.line(canvas, prev_index_finger_pos, current_right_index_pos, DRAW_COLOR, THICKNESS)
            prev_index_finger_pos = current_right_index_pos
        else:
            prev_index_finger_pos = None

        # Process Clearing
        if current_left_hand_x is not None and prev_left_hand_x is not None:
            # Check delta
            delta_x = current_left_hand_x - prev_left_hand_x
            
            # Simple swipe detection: fast horizontal movement
            if abs(delta_x) > SWIPE_THRESHOLD:
                # Clear canvas
                canvas[:] = 0
                print("Canvas Cleared!")
        
        if current_left_hand_x is not None:
             prev_left_hand_x = current_left_hand_x
        else:
             prev_left_hand_x = None # Reset if hand lost

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
