#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import argparse
import gc
import traceback

import cv2
import numpy as np

from shared_camera import SharedCameraRelay


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_PRODUCTION_SCENES = [
    "finger_colorfull_dots_acer.py",
    "finger_mandala_acer.py",
    "particle_storm_acer.py",
    "fractal_moving_acer.py",
    "finger_grid_interaction_acer.py",
    "saturn_particles_acer.py",
    "spider_cursor_acer.py",
]


class ConfigurationError(RuntimeError):
    pass


def _parse_bool_setting(value):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"expected boolean, got {value!r}")


def _parse_optional_int_setting(value):
    if value is None or str(value).strip().lower() in {"", "none", "null", "auto"}:
        return None
    return int(value)

DEFAULT_CONFIG = {
    "CAMERA_INDEX": 1,
    "CAMERA_WIDTH": 1280,
    "CAMERA_HEIGHT": 720,
    "CAMERA_FPS": 60,
    "CAMERA_FOURCC": "MJPG",
    "CAMERA_DIAGNOSTIC_SECONDS": 2.0,
    "CAMERA_STRICT_BACKEND": True,
    "CAMERA_BACKEND": "dshow",
    "CAMERA_ALLOW_FALLBACK": False,
    "CAMERA_OPENCV_INDEX": None,
    "CAMERA_NAME_HINTS": ["c922", "pro stream webcam"],
    "CAMERA_EXCLUDE_HINTS": ["nizima", "virtual", "logi capture"],
    "SCENE_DIR": ".",
    "PRODUCTION_SCENES": list(DEFAULT_PRODUCTION_SCENES),
    "SHARED_CAMERA_ENABLED": True,
    "CLAP_MONITOR_ENABLED": True,
    "CLAP_DIST_THRESHOLD": 0.15,
    "CLAP_COOLDOWN": 0.5,
    "TARGET_FPS": 60,
    "PRELOAD_COUNT": 1,
    "SCENE_GRACEFUL_TIMEOUT": 2.0,
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


CAMERA_ENV_CASTERS = {
    "CAMERA_INDEX": int,
    "CAMERA_WIDTH": int,
    "CAMERA_HEIGHT": int,
    "CAMERA_FPS": int,
    "CAMERA_FOURCC": str,
    "CAMERA_DIAGNOSTIC_SECONDS": float,
    "CAMERA_STRICT_BACKEND": _parse_bool_setting,
    "CAMERA_BACKEND": str,
    "CAMERA_OPENCV_INDEX": _parse_optional_int_setting,
    "CAMERA_ALLOW_FALLBACK": _parse_bool_setting,
}


def load_config(path=CONFIG_PATH):
    cfg = dict(DEFAULT_CONFIG)
    camera_sources = {key: "internal default" for key in CAMERA_ENV_CASTERS}

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            if isinstance(user_cfg, dict):
                cfg.update(user_cfg)
                for key in CAMERA_ENV_CASTERS:
                    if key in user_cfg:
                        camera_sources[key] = "config"
        except Exception as exc:
            print(f"[Manager] Warning: Failed to read config file {path}: {exc}")

    for key, caster in CAMERA_ENV_CASTERS.items():
        env_key = f"KIDZDISCO_{key}"
        if env_key not in os.environ:
            continue
        try:
            cfg[key] = caster(os.environ[env_key])
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid {env_key}: {exc}") from exc
        camera_sources[key] = "environment"

    scene_dir = os.path.expanduser(cfg["SCENE_DIR"])
    if not os.path.isabs(scene_dir):
        scene_dir = os.path.abspath(os.path.join(BASE_DIR, scene_dir))
    cfg["SCENE_DIR"] = scene_dir
    cfg["_CAMERA_CONFIG_SOURCES"] = camera_sources
    return cfg


def resolve_production_scenes(config):
    scene_dir = os.path.realpath(config["SCENE_DIR"])
    configured = config.get("PRODUCTION_SCENES")
    if not isinstance(configured, list) or not configured:
        raise ConfigurationError("PRODUCTION_SCENES must be a non-empty list")

    scenes = []
    seen = set()
    for position, raw_name in enumerate(configured, start=1):
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ConfigurationError(f"PRODUCTION_SCENES[{position}] must be a filename")

        filename = raw_name.strip()
        if filename != os.path.basename(filename):
            raise ConfigurationError(
                f"Production scene must be a basename inside SCENE_DIR: {filename!r}"
            )
        if not filename.lower().endswith("_acer.py"):
            raise ConfigurationError(
                f"Production scene must use an *_acer.py entrypoint: {filename!r}"
            )

        identity = filename.casefold()
        if identity in seen:
            raise ConfigurationError(f"Duplicate production scene: {filename!r}")
        seen.add(identity)

        scene_path = os.path.realpath(os.path.join(scene_dir, filename))
        try:
            inside_scene_dir = os.path.commonpath([scene_dir, scene_path]) == scene_dir
        except ValueError:
            inside_scene_dir = False
        if not inside_scene_dir:
            raise ConfigurationError(f"Production scene escapes SCENE_DIR: {filename!r}")
        if not os.path.isfile(scene_path):
            raise ConfigurationError(f"Production scene not found: {scene_path}")
        scenes.append(scene_path)

    return scenes


CONFIG_LOAD_ERROR = None
try:
    CONFIG = load_config()
except ConfigurationError as exc:
    CONFIG = dict(DEFAULT_CONFIG)
    CONFIG["SCENE_DIR"] = BASE_DIR
    CONFIG_LOAD_ERROR = exc


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
    def __init__(self, camera_env=None, scenes=None):
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
        self.all_scenes = list(scenes) if scenes is not None else self._scan_and_shuffle_scenes()
        print(f"[Manager] Found {len(self.all_scenes)} scenes")

    def _scan_and_shuffle_scenes(self):
        return resolve_production_scenes(CONFIG)

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
        if proc is None:
            return True

        graceful_timeout = float(CONFIG.get("SCENE_GRACEFUL_TIMEOUT", 2.0))
        terminate_timeout = float(CONFIG.get("SCENE_TERMINATE_TIMEOUT", 3.0))
        try:
            if proc.poll() is not None:
                return True

            print(f"[Manager] Stopping scene: {scene_name}")
            try:
                if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.send_signal(signal.SIGINT)
                proc.wait(timeout=graceful_timeout)
                return True
            except subprocess.TimeoutExpired:
                print(f"[Manager] Warning: graceful stop timed out: {scene_name}")
            except Exception as exc:
                print(f"[Manager] Warning: graceful stop failed for {scene_name}: {exc}")

            try:
                proc.terminate()
                proc.wait(timeout=terminate_timeout)
                return True
            except subprocess.TimeoutExpired:
                print(f"[Manager] Warning: terminate timed out: {scene_name}")
            except Exception as exc:
                print(f"[Manager] Warning: terminate failed for {scene_name}: {exc}")

            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    proc.kill()
                proc.wait(timeout=terminate_timeout)
            except Exception as exc:
                print(f"[Manager] Error: force stop failed for {scene_name}: {exc}")
                return False
            return proc.poll() is not None
        finally:
            gc.collect()

    def kill_current(self):
        stopped = self._kill_process(self.running_process, self.current_scene_name)
        if stopped:
            self.running_process = None
            self.running_scene_path = None
        return stopped

    def _clear_preloaded(self):
        self.preloaded_process = None
        self.preloaded_scene_path = None
        self.preloaded_scene_name = None
        self.preloaded_port = None

    def _discard_preloaded(self):
        stopped = True
        if self.preloaded_process is not None:
            stopped = self._kill_process(
                self.preloaded_process,
                self.preloaded_scene_name or "preloaded",
            )
        if stopped:
            self._clear_preloaded()
        return stopped

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
            return True
        total_duration = float(CONFIG.get("TRANSITION_TOTAL_DURATION", 5.0))
        remaining = max(0.0, total_duration - cover_delay) + 1.0
        stopped = False
        try:
            proc.wait(timeout=remaining)
            stopped = True
        except subprocess.TimeoutExpired:
            stopped = self._kill_process(proc, "sakura_transition")
        except Exception as exc:
            print(f"[Manager] Transition wait failed: {exc}")
        finally:
            if stopped and self.transition_process is proc:
                self.transition_process = None
        return stopped

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
            return False

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
            return True

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
            if not self.kill_current():
                print(
                    f"[Manager] Error: current scene is still running; "
                    f"aborting switch from {self.current_scene_name}"
                )
                self._discard_preloaded()
                self._wait_for_transition_finish(transition_proc, cover_delay)
                return False
            activated_preloaded = self._activate_preloaded_scene(send_start=False)

        if not activated_preloaded:
            if not self.kill_current():
                print(
                    f"[Manager] Error: current scene is still running; "
                    f"not launching another scene"
                )
                self._wait_for_transition_finish(transition_proc, cover_delay)
                return False
            scene_path = self._next_scene_path()
            self.scene_index += 1
            time.sleep(float(CONFIG.get("SCENE_SWITCH_DELAY", 0.2)))
            self.launch_scene(scene_path)

        self._wait_for_transition_finish(transition_proc, cover_delay)
        self._ensure_preloaded_scene()
        return True

    def is_scene_running(self):
        if self.running_process is None:
            return False
        return self.running_process.poll() is None

    def cleanup(self):
        errors = []

        def run_step(label, action):
            try:
                result = action()
                if result is False:
                    errors.append(f"{label}: resource still running")
                    return False
                return True
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                print(f"[Manager] Cleanup error ({label}): {exc}")
                return False

        run_step("preloaded scene", self._discard_preloaded)
        run_step("current scene", self.kill_current)
        transition_process = self.transition_process
        if transition_process is not None:
            transition_stopped = run_step(
                "transition overlay",
                lambda: self._kill_process(transition_process, "sakura_transition"),
            )
            if transition_stopped:
                self.transition_process = None

        if errors:
            print("[Manager] Cleanup completed with errors: " + "; ".join(errors))
            return False
        return True


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
            if self.thread.is_alive():
                print("[Monitor] Error: monitor thread did not stop")
                return False
            self.thread = None
        return True

    def consume_clap(self):
        if self.clap_detected:
            self.clap_detected = False
            return True
        return False

    def _monitor_loop(self):
        import mediapipe as mp

        holistic = None
        try:
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
        except Exception as exc:
            self.status = "failed"
            print(f"[Monitor] Error: {exc}")
        finally:
            if holistic is not None:
                try:
                    holistic.close()
                except Exception as exc:
                    print(f"[Monitor] Cleanup error: {exc}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--camera-only",
        action="store_true",
        help="Start only the shared camera relay for manual scene editing.",
    )
    args, _ = parser.parse_known_args()

    if CONFIG_LOAD_ERROR is not None:
        print(f"[Manager] Configuration error: {CONFIG_LOAD_ERROR}")
        return 2

    production_scenes = None
    if not args.camera_only:
        try:
            production_scenes = resolve_production_scenes(CONFIG)
        except ConfigurationError as exc:
            print(f"[Manager] Configuration error: {exc}")
            return 2

    manager_window_available = True
    camera_relay = None
    manager = None
    monitor = None
    exit_code = 0
    try:
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
        )
        camera_relay.start()

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
        camera_sources = CONFIG.get("_CAMERA_CONFIG_SOURCES", {})
        print(
            "[Manager] Camera config sources: "
            + ", ".join(
                f"{key}={camera_sources.get(key, 'unknown')}"
                for key in CAMERA_ENV_CASTERS
            )
        )

        if not args.camera_only:
            manager = SceneManager(camera_env=camera_env, scenes=production_scenes)

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
    except Exception as exc:
        print(f"[Manager] Fatal error: {exc}")
        traceback.print_exc()
        exit_code = 1
    finally:
        print("[Manager] Shutting down...")
        if monitor:
            try:
                if monitor.stop() is False:
                    exit_code = 1
            except Exception as exc:
                print(f"[Manager] Monitor cleanup error: {exc}")
                exit_code = 1
        if manager is not None:
            try:
                if manager.cleanup() is False:
                    exit_code = 1
            except Exception as exc:
                print(f"[Manager] Scene cleanup error: {exc}")
                exit_code = 1
        if camera_relay is not None:
            try:
                if camera_relay.close() is False:
                    exit_code = 1
            except Exception as exc:
                print(f"[Manager] Camera cleanup error: {exc}")
                exit_code = 1
        try:
            cv2.destroyAllWindows()
        except Exception as exc:
            print(f"[Manager] Window cleanup error: {exc}")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
