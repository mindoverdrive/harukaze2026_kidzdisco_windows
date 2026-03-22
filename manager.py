#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import os
import random
import subprocess
import sys
import threading
import time
import argparse

import cv2
import numpy as np

from shared_camera import SharedCameraRelay


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "CAMERA_INDEX": 1,
    "CAMERA_WIDTH": 1280,
    "CAMERA_HEIGHT": 720,
    "CAMERA_FPS": 60,
    "CAMERA_BACKEND": "dshow",
    "CAMERA_ALLOW_FALLBACK": False,
    "CAMERA_OPENCV_INDEX": 0,
    "CAMERA_NAME_HINTS": ["c922", "pro stream webcam"],
    "CAMERA_EXCLUDE_HINTS": ["nizima", "virtual", "logi capture"],
    "SCENE_DIR": ".",
    "SHARED_CAMERA_ENABLED": True,
    "CLAP_MONITOR_ENABLED": True,
    "CLAP_DIST_THRESHOLD": 0.15,
    "CLAP_COOLDOWN": 0.5,
    "TARGET_FPS": 60,
}


def load_config(path=CONFIG_PATH):
    cfg = dict(DEFAULT_CONFIG)

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            if isinstance(user_cfg, dict):
                cfg.update(user_cfg)
        except Exception as exc:
            print(f"[Manager] Warning: Failed to read config file {path}: {exc}")

    scene_dir = os.path.expanduser(cfg["SCENE_DIR"])
    if not os.path.isabs(scene_dir):
        scene_dir = os.path.abspath(os.path.join(BASE_DIR, scene_dir))
    cfg["SCENE_DIR"] = scene_dir
    return cfg


CONFIG = load_config()


class GestureInterpreter:
    def __init__(self):
        self.last_clap_time = 0.0
        self.clap_count = 0
        self.hands_were_apart = True

    def check_head_clap(self, left_hand, right_hand, nose):
        if not (left_hand and right_hand and nose):
            return False

        if left_hand.y > nose.y + 0.1 or right_hand.y > nose.y + 0.1:
            return False

        dist = math.sqrt((left_hand.x - right_hand.x) ** 2 + (left_hand.y - right_hand.y) ** 2)
        current_time = time.time()

        if dist > CONFIG["CLAP_DIST_THRESHOLD"] * 1.5:
            self.hands_were_apart = True
            return False

        if dist < CONFIG["CLAP_DIST_THRESHOLD"] and self.hands_were_apart:
            self.hands_were_apart = False
            time_diff = current_time - self.last_clap_time

            if time_diff < CONFIG["CLAP_COOLDOWN"]:
                self.clap_count += 1
            else:
                self.clap_count = 1

            self.last_clap_time = current_time
            if self.clap_count >= 2:
                self.clap_count = 0
                return True

        return False


class SceneManager:
    def __init__(self, camera_env=None):
        self.running_process = None
        self.current_scene_name = "None"
        self.scene_index = 0
        self.camera_env = dict(camera_env or {})
        self.all_scenes = self._scan_and_shuffle_scenes()
        print(f"[Manager] Found {len(self.all_scenes)} scenes")

    def _scan_and_shuffle_scenes(self):
        scenes = []
        scene_dir = CONFIG["SCENE_DIR"]
        ignore_files = {
            "manager.py",
            "app.py",
            "display_utils.py",
            "shared_camera.py",
            "hand_tracker.py",
            "visual_monitor_3d.py",
            "sakura_transition.py",
        }
        ignore_prefixes = (
            "test_",
            "patch",
            "replace",
            "repair",
            "camera_",
        )
        ignore_contains = (
            "display_utils",
            "shared_camera",
        )

        if not os.path.exists(scene_dir):
            os.makedirs(scene_dir, exist_ok=True)
            return scenes

        for filename in os.listdir(scene_dir):
            if not filename.endswith(".py"):
                continue
            lower_name = filename.lower()
            if filename in ignore_files:
                continue
            if any(lower_name.startswith(prefix) for prefix in ignore_prefixes):
                continue
            if any(token in lower_name for token in ignore_contains):
                continue
            scenes.append(os.path.join(scene_dir, filename))

        random.shuffle(scenes)
        earth_path = os.path.join(scene_dir, "earth.py")
        if earth_path in scenes:
            scenes.remove(earth_path)
            scenes.insert(0, earth_path)
        return scenes

    def kill_current(self):
        if self.running_process and self.running_process.poll() is None:
            print(f"[Manager] Killing scene: {self.current_scene_name}")
            self.running_process.terminate()
            try:
                self.running_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.running_process.kill()
                self.running_process.wait()
            self.running_process = None

    def launch_scene(self, scene_path):
        self.current_scene_name = os.path.basename(scene_path)
        print(f"\n[Manager] >>> LAUNCHING: {self.current_scene_name} <<<\n")

        env = os.environ.copy()
        env["WGPU_BACKEND"] = env.get("WGPU_BACKEND", "dx12")
        env.update(self.camera_env)
        self.running_process = subprocess.Popen(
            [sys.executable, scene_path],
            cwd=os.path.dirname(scene_path),
            env=env,
        )

    def switch_scene(self):
        if not self.all_scenes:
            print("[Manager] No scenes available.")
            return
        self.kill_current()
        scene_path = self.all_scenes[self.scene_index % len(self.all_scenes)]
        self.scene_index += 1
        time.sleep(0.2)
        self.launch_scene(scene_path)

    def is_scene_running(self):
        if self.running_process is None:
            return False
        return self.running_process.poll() is None

    def cleanup(self):
        self.kill_current()


class HeadClapMonitor:
    def __init__(self, frame_source):
        self.frame_source = frame_source
        self.clap_detected = False
        self.running = True
        self.interpreter = GestureInterpreter()
        self.thread = None
        self.status = "idle"

    def start(self):
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)

    def consume_clap(self):
        if self.clap_detected:
            self.clap_detected = False
            return True
        return False

    def _monitor_loop(self):
        import mediapipe as mp

        mp_holistic = mp.solutions.holistic
        holistic = mp_holistic.Holistic(
            model_complexity=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5,
        )

        while self.running:
            ret, frame = self.frame_source.read()
            if not ret or frame is None:
                self.status = "waiting_frame"
                time.sleep(0.01)
                continue

            self.status = "monitoring"
            image = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            image.flags.writeable = False
            results = holistic.process(image)

            left_hand = None
            right_hand = None
            nose = None

            if results.pose_landmarks:
                nose = results.pose_landmarks.landmark[mp_holistic.PoseLandmark.NOSE]
            if results.left_hand_landmarks:
                left_hand = results.left_hand_landmarks.landmark[mp_holistic.HandLandmark.WRIST]
            if results.right_hand_landmarks:
                right_hand = results.right_hand_landmarks.landmark[mp_holistic.HandLandmark.WRIST]

            if self.interpreter.check_head_clap(left_hand, right_hand, nose):
                print("[Monitor] HEAD CLAP DETECTED!")
                self.clap_detected = True

            time.sleep(1.0 / max(CONFIG["TARGET_FPS"], 1))

        holistic.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--camera-only",
        action="store_true",
        help="Start only the shared camera relay for manual scene editing.",
    )
    args, _ = parser.parse_known_args()

    manager_window_available = True
    camera_relay = SharedCameraRelay(
        camera_index=CONFIG["CAMERA_INDEX"],
        width=CONFIG["CAMERA_WIDTH"],
        height=CONFIG["CAMERA_HEIGHT"],
        fps=CONFIG["CAMERA_FPS"],
        fourcc=CONFIG.get("CAMERA_FOURCC", "MJPG"),
        diagnostic_seconds=CONFIG.get("CAMERA_DIAGNOSTIC_SECONDS", 2.0),
        strict_backend=CONFIG.get("CAMERA_STRICT_BACKEND", True),
        backend_preference=CONFIG.get("CAMERA_BACKEND", "default"),
        fallback_to_default=CONFIG.get("CAMERA_ALLOW_FALLBACK", False),
        camera_name_hint=CONFIG.get("CAMERA_NAME_HINTS"),
        exclude_name_hints=CONFIG.get("CAMERA_EXCLUDE_HINTS"),
        explicit_index=CONFIG.get("CAMERA_OPENCV_INDEX"),
    ).start()

    camera_env = camera_relay.export_env() if CONFIG.get("SHARED_CAMERA_ENABLED", True) else {}
    print(
        f"[Manager] Camera index={CONFIG['CAMERA_INDEX']} "
        f"opencv_index={CONFIG.get('CAMERA_OPENCV_INDEX')} "
        f"fourcc={CONFIG.get('CAMERA_FOURCC', 'MJPG')} "
        f"diag={CONFIG.get('CAMERA_DIAGNOSTIC_SECONDS', 2.0)}s "
        f"strict_backend={CONFIG.get('CAMERA_STRICT_BACKEND', True)} "
        f"backend={CONFIG.get('CAMERA_BACKEND', 'default')} "
        f"shared={CONFIG.get('SHARED_CAMERA_ENABLED', True)}"
    )

    manager = None
    if not args.camera_only:
        manager = SceneManager(camera_env=camera_env)
        if not manager.all_scenes:
            print("[Manager] Error: No scene files found.")
            camera_relay.close()
            return

    monitor = None
    if not args.camera_only and CONFIG.get("CLAP_MONITOR_ENABLED", True):
        monitor = HeadClapMonitor(frame_source=camera_relay)
        monitor.start()
    elif args.camera_only:
        print("[Manager] Camera-only mode enabled. Scene launching is disabled.")
    else:
        print("[Manager] Clap monitor disabled by config.")

    if manager is not None:
        manager.switch_scene()
    try:
        cv2.namedWindow("Manager Control", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Manager Control", 440, 120)
    except cv2.error as exc:
        manager_window_available = False
        print(f"[Manager] Warning: Manager Control window disabled: {exc}")

    try:
        while True:
            if monitor and monitor.consume_clap() and manager is not None:
                print("[Manager] Head clap detected. Switching scene.")
                manager.switch_scene()

            if manager is not None and not manager.is_scene_running():
                print(f"[Manager] Scene '{manager.current_scene_name}' exited. Launching next...")
                time.sleep(0.5)
                manager.switch_scene()

            key = -1
            if manager_window_available:
                control_img = np.zeros((120, 440, 3), dtype=np.uint8)
                scene_name = manager.current_scene_name if manager is not None else "camera-only"
                cv2.putText(control_img, f"Scene: {scene_name}", (10, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                cv2.putText(control_img, f"Camera: {CONFIG['CAMERA_INDEX']} / {CONFIG.get('CAMERA_BACKEND', 'default')}", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)
                monitor_text = "Clap Monitor: disabled"
                if monitor:
                    monitor_text = f"Clap Monitor: {monitor.status}"
                cv2.putText(control_img, monitor_text, (10, 85),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
                cv2.putText(control_img, "n=Next  q=Quit", (10, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1)
                cv2.imshow("Manager Control", control_img)
                key = cv2.waitKey(100) & 0xFF
            else:
                time.sleep(0.1)

            if key == ord("q"):
                break
            if key == ord("n") and manager is not None:
                print("[Manager] Keyboard next scene")
                manager.switch_scene()

    except KeyboardInterrupt:
        print("\n[Manager] Interrupted by user.")
    finally:
        print("[Manager] Shutting down...")
        if monitor:
            monitor.stop()
        if manager is not None:
            manager.cleanup()
        camera_relay.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
