#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import os
import random
import socket
import subprocess
import sys
import threading
import time
import argparse
import gc

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
    "PRELOAD_COUNT": 1,
    "SCENE_TERMINATE_TIMEOUT": 3.0,
    "SCENE_SWITCH_DELAY": 0.2,
    "SCENE_PRELOAD_START_GRACE": 0.25,
    "TRANSITION_ENABLED": True,
    "TRANSITION_SCRIPT": "sakura_transition.py",
    "TRANSITION_TOTAL_DURATION": 5.0,
    "TRANSITION_PHASE1_END": 1.5,
    "TRANSITION_PHASE2_END": 2.5,
    "TRANSITION_COVER_DELAY": 1.5,
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
        self.last_state = None
        self.switch_count = 0
        self.last_switch_time = 0.0

    def get_hand_state(self, hand_landmarks):
        if not hand_landmarks:
            return "none"
        
        wrist = hand_landmarks.landmark[0]
        extended_count = 0
        
        # Check index (8, 6), middle (12, 10), ring (16, 14), pinky (20, 18)
        # We consider a finger extended if the tip is further from the wrist than the PIP joint.
        for tip_idx, pip_idx in [(8, 6), (12, 10), (16, 14), (20, 18)]:
            tip = hand_landmarks.landmark[tip_idx]
            pip = hand_landmarks.landmark[pip_idx]
            
            dist_tip = math.sqrt((tip.x - wrist.x)**2 + (tip.y - wrist.y)**2)
            dist_pip = math.sqrt((pip.x - wrist.x)**2 + (pip.y - wrist.y)**2)
            
            # Simple heuristic for finger extension
            if dist_tip > dist_pip * 1.1:
                extended_count += 1
                
        if extended_count >= 3:
            return "paper"
        elif extended_count <= 1:
            return "rock"
        return "other"

    def check_gesture(self, left_hand_landmarks, right_hand_landmarks):
        left_state = self.get_hand_state(left_hand_landmarks)
        right_state = self.get_hand_state(right_hand_landmarks)

        current_time = time.time()

        if left_state in ("none", "other") or right_state in ("none", "other") or left_state == right_state:
            # If states are invalid or hands show the same gesture, check if we've timed out
            if current_time - self.last_switch_time > 1.5:
                self.switch_count = 0
                self.last_state = None
            return False

        # Now we know left and right states are definitely ("rock", "paper") or ("paper", "rock")
        current_combo = (left_state, right_state)
        
        if self.last_state is None:
            self.last_state = current_combo
            self.switch_count = 0
            self.last_switch_time = current_time
            return False

        if current_combo != self.last_state:
            # A valid switch happened!
            time_diff = current_time - self.last_switch_time
            
            # Allow between 0.05s and 1.5s for a switch
            if 0.05 < time_diff < 1.5:
                self.switch_count += 1
                self.last_state = current_combo
                self.last_switch_time = current_time
                print(f"[Gesture] Switch detected! Count: {self.switch_count}/5")
                
                # We need alternating states 5 times
                if self.switch_count >= 5:
                    self.switch_count = 0
                    self.last_state = None
                    return True
            elif time_diff >= 1.5:
                # Took too long, restart counting from 1
                self.switch_count = 1
                self.last_state = current_combo
                self.last_switch_time = current_time

        return False


class SceneManager:
    def __init__(self, camera_env=None):
        self.running_process = None
        self.running_scene_path = None
        self.current_scene_name = "None"
        self.scene_index = 0
        self.camera_env = dict(camera_env or {})
        self.preloaded_process = None
        self.preloaded_scene_path = None
        self.preloaded_scene_name = None
        self.preloaded_port = None
        self.transition_process = None
        self.preload_enabled = int(CONFIG.get("PRELOAD_COUNT", 1)) > 0
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
            "sitecustomize.py",
            "visual_monitor.py",
            "process_sakura.py",
            "sound_face.py",
            "harukaze2026_proto2025.py",
            "harukaze2026proto2026_1.py",
            "hand_drawing_app.py",
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

    def _creationflags(self):
        if os.name == "nt":
            return subprocess.CREATE_NEW_PROCESS_GROUP
        return 0

    def _scene_env(self):
        env = os.environ.copy()
        env["WGPU_BACKEND"] = env.get("WGPU_BACKEND", "dx12")
        env.update(self.camera_env)
        return env

    def _spawn_process(self, argv, cwd):
        return subprocess.Popen(
            argv,
            cwd=cwd,
            env=self._scene_env(),
            creationflags=self._creationflags(),
        )

    def _stage_geometry(self):
        return (
            int(CONFIG.get("DISPLAY_X", 0)),
            int(CONFIG.get("DISPLAY_Y", 0)),
            int(CONFIG.get("DISPLAY_WIDTH", 1360)),
            int(CONFIG.get("DISPLAY_HEIGHT", 800)),
        )

    def _reserve_udp_port(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    def _send_scene_command(self, port, cmd):
        if not port:
            return
        payload = json.dumps({"cmd": cmd}).encode("utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(payload, ("127.0.0.1", int(port)))

    def _announce_launch(self, scene_name, mode="launching"):
        label = "PRELOADING" if mode == "preload" else "LAUNCHING"
        print(f"\n[Manager] >>> {label}: {scene_name} <<<\n")

    def _next_scene_path(self):
        return self.all_scenes[self.scene_index % len(self.all_scenes)]

    def _launch_scene_process(self, scene_path, wait=False, port=None):
        argv = [sys.executable, scene_path]
        if wait and port:
            argv.extend(["--wait", "--port", str(port)])
        proc = self._spawn_process(argv, cwd=os.path.dirname(scene_path))
        return proc

    def _kill_process(self, proc, scene_name):
        if proc and proc.poll() is None:
            print(f"[Manager] Killing scene: {scene_name}")
            proc.terminate()
            try:
                proc.wait(timeout=float(CONFIG.get("SCENE_TERMINATE_TIMEOUT", 3.0)))
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    proc.kill()
                proc.wait()
        gc.collect()

    def kill_current(self):
        self._kill_process(self.running_process, self.current_scene_name)
        self.running_process = None
        self.running_scene_path = None

    def _clear_preloaded(self):
        self.preloaded_process = None
        self.preloaded_scene_path = None
        self.preloaded_scene_name = None
        self.preloaded_port = None

    def _discard_preloaded(self):
        if self.preloaded_process is not None:
            self._kill_process(self.preloaded_process, self.preloaded_scene_name or "preloaded")
        self._clear_preloaded()

    def _start_transition_overlay(self):
        if not CONFIG.get("TRANSITION_ENABLED", True):
            return None
        transition_name = CONFIG.get("TRANSITION_SCRIPT", "sakura_transition.py")
        transition_path = os.path.join(CONFIG["SCENE_DIR"], transition_name)
        if not os.path.exists(transition_path):
            print(f"[Manager] Warning: transition script not found: {transition_path}")
            return None

        x, y, w, h = self._stage_geometry()
        argv = [
            sys.executable,
            transition_path,
            "--x", str(x),
            "--y", str(y),
            "--width", str(w),
            "--height", str(h),
            "--total-duration", str(CONFIG.get("TRANSITION_TOTAL_DURATION", 5.0)),
            "--phase1-end", str(CONFIG.get("TRANSITION_PHASE1_END", 1.5)),
            "--phase2-end", str(CONFIG.get("TRANSITION_PHASE2_END", 2.5)),
        ]
        self.transition_process = self._spawn_process(argv, cwd=os.path.dirname(transition_path))
        return self.transition_process

    def _wait_for_transition_finish(self, proc, cover_delay):
        if proc is None:
            return
        total_duration = float(CONFIG.get("TRANSITION_TOTAL_DURATION", 5.0))
        remaining = max(0.0, total_duration - cover_delay) + 1.0
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            self._kill_process(proc, "sakura_transition")
        finally:
            self.transition_process = None

    def _ensure_preloaded_scene(self):
        if not self.preload_enabled or not self.all_scenes:
            return
        if self.preloaded_process is not None:
            if self.preloaded_process.poll() is None:
                return
            print(f"[Manager] Warning: preloaded scene exited early: {self.preloaded_scene_name}")
            self._clear_preloaded()

        scene_path = self._next_scene_path()
        self.preloaded_port = self._reserve_udp_port()
        self.preloaded_scene_path = scene_path
        self.preloaded_scene_name = os.path.basename(scene_path)
        self._announce_launch(self.preloaded_scene_name, mode="preload")
        self.preloaded_process = self._launch_scene_process(
            scene_path,
            wait=True,
            port=self.preloaded_port,
        )

    def _activate_preloaded_scene(self, send_start=True):
        if self.preloaded_process is None:
            return False
        if self.preloaded_process.poll() is not None:
            print(f"[Manager] Warning: preloaded scene failed before START: {self.preloaded_scene_name}")
            self._clear_preloaded()
            return False

        self._announce_launch(self.preloaded_scene_name, mode="launch")
        if send_start:
            self._send_scene_command(self.preloaded_port, "START")
        self.running_process = self.preloaded_process
        self.running_scene_path = self.preloaded_scene_path
        self.current_scene_name = self.preloaded_scene_name or "None"
        self.scene_index += 1
        self._clear_preloaded()
        return True

    def launch_scene(self, scene_path):
        self.current_scene_name = os.path.basename(scene_path)
        self.running_scene_path = scene_path
        self._announce_launch(self.current_scene_name, mode="launch")
        self.running_process = self._launch_scene_process(scene_path)

    def switch_scene(self):
        if not self.all_scenes:
            print("[Manager] No scenes available.")
            return

        if self.running_process is None:
            if self.preload_enabled:
                self._ensure_preloaded_scene()
                if not self._activate_preloaded_scene():
                    scene_path = self._next_scene_path()
                    self.scene_index += 1
                    self.launch_scene(scene_path)
            else:
                scene_path = self._next_scene_path()
                self.scene_index += 1
                self.launch_scene(scene_path)
            time.sleep(float(CONFIG.get("SCENE_SWITCH_DELAY", 0.2)))
            self._ensure_preloaded_scene()
            return

        if self.preload_enabled:
            self._ensure_preloaded_scene()

        cover_delay = float(
            CONFIG.get(
                "TRANSITION_COVER_DELAY",
                CONFIG.get("TRANSITION_PHASE1_END", 1.5),
            )
        )
        transition_proc = self._start_transition_overlay()
        if transition_proc is not None:
            time.sleep(max(0.0, cover_delay))

        activated_preloaded = False
        if self.preload_enabled and self.preloaded_process is not None:
            self._send_scene_command(self.preloaded_port, "START")
            time.sleep(float(CONFIG.get("SCENE_PRELOAD_START_GRACE", 0.25)))
            self._kill_process(self.running_process, self.current_scene_name)
            self.running_process = None
            self.running_scene_path = None
            activated_preloaded = self._activate_preloaded_scene(send_start=False)

        if not activated_preloaded:
            self.kill_current()
            scene_path = self._next_scene_path()
            self.scene_index += 1
            time.sleep(float(CONFIG.get("SCENE_SWITCH_DELAY", 0.2)))
            self.launch_scene(scene_path)

        self._wait_for_transition_finish(transition_proc, cover_delay)
        self._ensure_preloaded_scene()

    def is_scene_running(self):
        if self.running_process is None:
            return False
        return self.running_process.poll() is None

    def cleanup(self):
        self._discard_preloaded()
        self.kill_current()
        if self.transition_process is not None:
            self._kill_process(self.transition_process, "sakura_transition")
            self.transition_process = None


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

            left_hand_landmarks = results.left_hand_landmarks
            right_hand_landmarks = results.right_hand_landmarks

            if self.interpreter.check_gesture(left_hand_landmarks, right_hand_landmarks):
                print("[Monitor] GUPAR DETECTED! (Alternating Rock/Paper 5x)")
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
