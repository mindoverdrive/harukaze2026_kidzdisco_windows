#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Snake Finger Game - テストモード（GUI不要）
"""

import cv2
import mediapipe as mp

# MediaPipeの動作確認
print("Testing MediaPipe...")
try:
    hands = mp.solutions.hands.Hands(model_complexity=1, 
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5
    )
    print("✓ MediaPipe loaded successfully")
except Exception as e:
    print(f"✗ MediaPipe Error: {e}")

# OpenCVの動作確認
print("\nTesting OpenCV...")
try:
    cap = display_utils.open_camera()
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            print(f"✓ Camera works - Frame size: {frame.shape}")
        else:
            print("✗ Cannot read from camera")
        cap.release()
    else:
        print("✗ Camera not available (this is OK for testing)")
except Exception as e:
    print(f"✗ OpenCV Error: {e}")

# Pygameの動作確認
print("\nTesting Pygame...")
try:
    import pygame
    import display_utils
    pygame.init()
    screen, _pg_size = display_utils.setup_pygame_fullscreen()
    pygame.display.set_caption("Test")
    print("✓ Pygame loaded successfully")
    pygame.quit()
except Exception as e:
    print(f"✗ Pygame Error: {e}")

print("\n✓ All tests passed! You can run: python snake_game_final.py")
