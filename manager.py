#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import os
import signal
import subprocess
import sys
import threading
import time
import argparse
import ast
import gc
import traceback

import cv2
import numpy as np

from shared_camera import SharedCameraRelay
from scene_control import SceneLaunchControl, SceneControlError
from scene_profile_runner import resolve_scene_path
from windows_process import WindowsSceneJob, get_scene_job
from runtime_diagnostics import RuntimeDiagnostics


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


def _parse_optional_float_setting(value):
    if value is None or str(value).strip().lower() in {"", "none", "null", "auto"}:
        return None
    if isinstance(value, bool):
        raise ValueError("expected a number or null, got boolean")
    return float(value)


DEFAULT_CONFIG = {
    "CAMERA_INDEX": 1,
    "CAMERA_WIDTH": 1280,
    "CAMERA_HEIGHT": 720,
    "CAMERA_FPS": 60,
    "CAMERA_FOURCC": "MJPG",
    "CAMERA_EXPOSURE": None,
    "CAMERA_DIAGNOSTIC_SECONDS": 2.0,
    "CAMERA_STRICT_BACKEND": True,
    "CAMERA_BACKEND": "dshow",
    "CAMERA_ALLOW_FALLBACK": False,
    "CAMERA_REQUIRE_NAME_MATCH": False,
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
    "SCENE_READY_TIMEOUT": 10.0,
    "SCENE_START_ACK_TIMEOUT": 5.0,
    "SCENE_FIRST_FRAME_TIMEOUT": 30.0,
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
    "CAMERA_EXPOSURE": _parse_optional_float_setting,
    "CAMERA_DIAGNOSTIC_SECONDS": float,
    "CAMERA_STRICT_BACKEND": _parse_bool_setting,
    "CAMERA_BACKEND": str,
    "CAMERA_OPENCV_INDEX": _parse_optional_int_setting,
    "CAMERA_ALLOW_FALLBACK": _parse_bool_setting,
    "CAMERA_REQUIRE_NAME_MATCH": _parse_bool_setting,
}


def validate_runtime_config(cfg):
    try:
        for key, caster in CAMERA_ENV_CASTERS.items():
            cfg[key] = caster(cfg[key])
        for key in ("SHARED_CAMERA_ENABLED", "CLAP_MONITOR_ENABLED", "TRANSITION_ENABLED"):
            cfg[key] = _parse_bool_setting(cfg[key])
        if not cfg["SHARED_CAMERA_ENABLED"]:
            raise ValueError("Manager requires SHARED_CAMERA_ENABLED=true to retain sole camera ownership")
        for key in ("CAMERA_WIDTH", "CAMERA_HEIGHT", "CAMERA_FPS", "TARGET_FPS"):
            if not isinstance(cfg[key], (int, float)) or not math.isfinite(cfg[key]) or cfg[key] <= 0:
                raise ValueError(f"{key} must be positive and finite")
        for key in ("CAMERA_INDEX", "PRELOAD_COUNT"):
            if int(cfg[key]) < 0:
                raise ValueError(f"{key} must be non-negative")
        if cfg["CAMERA_OPENCV_INDEX"] is not None and cfg["CAMERA_OPENCV_INDEX"] < 0:
            raise ValueError("CAMERA_OPENCV_INDEX must be non-negative or null")
        exposure = cfg["CAMERA_EXPOSURE"]
        if exposure is not None and (not math.isfinite(exposure) or not -13 <= exposure <= 0):
            raise ValueError("CAMERA_EXPOSURE must be finite, between -13 and 0, or null")
        for key in ("SCENE_GRACEFUL_TIMEOUT", "SCENE_TERMINATE_TIMEOUT", "SCENE_READY_TIMEOUT",
                    "SCENE_START_ACK_TIMEOUT", "SCENE_FIRST_FRAME_TIMEOUT", "TRANSITION_TOTAL_DURATION"):
            value = float(cfg[key])
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be positive and finite")
            cfg[key] = value
        for key in ("CAMERA_DIAGNOSTIC_SECONDS", "TRANSITION_COVER_DELAY"):
            value = float(cfg[key])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{key} must be non-negative and finite")
            cfg[key] = value
        if cfg["CAMERA_BACKEND"].lower() not in {"dshow", "msmf", "any", "default"}:
            raise ValueError("CAMERA_BACKEND must be dshow, msmf, any, or default")
        if cfg["CAMERA_REQUIRE_NAME_MATCH"] and cfg["CAMERA_ALLOW_FALLBACK"]:
            raise ValueError("Required camera name and arbitrary camera fallback cannot be combined")
        if not isinstance(cfg["SCENE_DIR"], str) or not cfg["SCENE_DIR"].strip():
            raise ValueError("SCENE_DIR must be a directory path")
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        raise ConfigurationError(f"Invalid runtime config: {exc}") from exc


def load_config(path=CONFIG_PATH):
    cfg = dict(DEFAULT_CONFIG)
    camera_sources = {key: "internal default" for key in CAMERA_ENV_CASTERS}

    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            if not isinstance(user_cfg, dict):
                raise ConfigurationError("Config must be a JSON object")
            cfg.update(user_cfg)
            for key in CAMERA_ENV_CASTERS:
                if key in user_cfg:
                    camera_sources[key] = "config"
        except Exception as exc:
            raise ConfigurationError(f"Failed to read config file {path}: {exc}") from exc

    for key, caster in CAMERA_ENV_CASTERS.items():
        env_key = f"KIDZDISCO_{key}"
        if env_key not in os.environ:
            continue
        try:
            cfg[key] = caster(os.environ[env_key])
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid {env_key}: {exc}") from exc
        camera_sources[key] = "environment"

    validate_runtime_config(cfg)
    scene_dir = os.path.expanduser(cfg["SCENE_DIR"])
    if not os.path.isabs(scene_dir):
        scene_dir = os.path.abspath(os.path.join(BASE_DIR, scene_dir))
    cfg["SCENE_DIR"] = scene_dir
    cfg["_CAMERA_CONFIG_SOURCES"] = camera_sources
    return cfg


def validate_scene_entrypoint(scene_path):
    try:
        with open(scene_path, encoding="utf-8-sig") as file:
            tree = ast.parse(file.read(), filename=scene_path)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "run_scene"]
        if len(calls) != 1 or not calls[0].args:
            raise ValueError("expected one literal run_scene(source, profile='acer') call")
        source = ast.literal_eval(calls[0].args[0])
        profile = next((ast.literal_eval(kw.value) for kw in calls[0].keywords if kw.arg == "profile"), None)
        if not isinstance(source, str) or profile != "acer":
            raise ValueError("entrypoint must specify a source filename and profile='acer'")
        source_path = resolve_scene_path(source)
        ast.parse(source_path.read_text(encoding="utf-8-sig"), filename=str(source_path))
    except (OSError, SyntaxError, ValueError, TypeError) as exc:
        raise ConfigurationError(f"Invalid scene entrypoint {scene_path}: {exc}") from exc


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
        validate_scene_entrypoint(scene_path)
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
    def __init__(self, camera_env=None, scenes=None, diagnostics=None):
        self.running_process = None
        self.running_scene_path = None
        self.current_scene_name = "None"
        self.scene_index = 0
        self.camera_env = dict(camera_env or {})
        self.preloaded_process = None
        self.preloaded_scene_path = None
        self.preloaded_scene_name = None
        self.preloaded_control = None
        self.transition_process = None
        self.transition_started_at = None
        self.switch_pending = False
        self.switch_cover_until = None
        self.last_switch_error = None
        self.fatal_error = None
        self.uncontained_process = None
        self.diagnostics = diagnostics
        self.completed_switches = 0
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
        if all(key in CONFIG for key in ("DISPLAY_X", "DISPLAY_Y", "DISPLAY_WIDTH", "DISPLAY_HEIGHT")):
            env["KIDZDISCO_DISPLAY_TARGET"] = "stage"
        for key in ("DISPLAY_TARGET", "DISPLAY_X", "DISPLAY_Y", "DISPLAY_WIDTH", "DISPLAY_HEIGHT"):
            if key in CONFIG:
                env[f"KIDZDISCO_{key}"] = str(CONFIG[key])
        return env

    def _spawn_process(self, argv, cwd):
        if self.uncontained_process is not None:
            raise OSError("Previous uncontained launch could not be stopped")
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=self._scene_env(),
            creationflags=self._creationflags(),
            **({"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT} if self.diagnostics else {}),
        )
        try:
            if os.name == "nt":
                proc._scene_job = WindowsSceneJob(proc)
            if self.diagnostics:
                self.diagnostics.capture_stdout(proc)
                self.diagnostics.record("scene_spawn", launcher_pid=proc.pid, argv=argv)
        except BaseException:
            # Keep ownership even if Job assignment or diagnostic I/O fails.
            self.uncontained_process = proc
            if self._kill_process(proc, "failed launch setup"):
                self.uncontained_process = None
            else:
                self.fatal_error = "Scene process could not be stopped after launch setup failure"
            raise
        return proc

    def _stage_geometry(self):
        return (
            int(CONFIG.get("DISPLAY_X", 0)),
            int(CONFIG.get("DISPLAY_Y", 0)),
            int(CONFIG.get("DISPLAY_WIDTH", 1360)),
            int(CONFIG.get("DISPLAY_HEIGHT", 800)),
        )

    def _announce_launch(self, scene_name, mode="launching"):
        label = "PRELOADING" if mode == "preload" else "LAUNCHING"
        print(f"\n[Manager] >>> {label}: {scene_name} <<<\n")

    def _next_scene_path(self):
        return self.all_scenes[self.scene_index % len(self.all_scenes)]

    def _launch_scene_process(self, scene_path, control):
        argv = [sys.executable, scene_path]
        argv.extend(control.argv())
        proc = self._spawn_process(argv, cwd=os.path.dirname(scene_path))
        return proc

    def _kill_process(self, proc, scene_name):
        if proc is None:
            return True

        graceful_timeout = float(CONFIG.get("SCENE_GRACEFUL_TIMEOUT", 2.0))
        terminate_timeout = float(CONFIG.get("SCENE_TERMINATE_TIMEOUT", 3.0))
        job = get_scene_job(proc)

        def stopped():
            if job is not None:
                if not job.wait(terminate_timeout):
                    return False
                job.close()
            return True

        try:
            if proc.poll() is not None and (job is None or not job.is_alive()):
                return stopped()

            print(f"[Manager] Stopping scene: {scene_name}")
            try:
                if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.send_signal(signal.SIGINT)
                proc.wait(timeout=graceful_timeout)
                if stopped():
                    return True
            except subprocess.TimeoutExpired:
                print(f"[Manager] Warning: graceful stop timed out: {scene_name}")
            except Exception as exc:
                print(f"[Manager] Warning: graceful stop failed for {scene_name}: {exc}")

            if job is not None:
                try:
                    job.terminate()
                    proc.wait(timeout=terminate_timeout)
                    return stopped()
                except Exception as exc:
                    print(f"[Manager] Error: owned scene job stop failed for {scene_name}: {exc}")
                    return False

            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=terminate_timeout, check=False)
                else:
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
                        timeout=terminate_timeout,
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
        control = getattr(self, "preloaded_control", None)
        if control is not None:
            control.close()
        self.preloaded_control = None
        self.preloaded_process = None
        self.preloaded_scene_path = None
        self.preloaded_scene_name = None

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
        self.transition_started_at = time.monotonic()
        return self.transition_process

    def _ensure_preloaded_scene(self):
        if not self.all_scenes:
            return False
        if self.preloaded_process is not None:
            return True

        scene_path = self._next_scene_path()
        try:
            self.preloaded_control = SceneLaunchControl(
                ready_timeout=CONFIG.get("SCENE_READY_TIMEOUT", 10.0),
                ack_timeout=CONFIG.get("SCENE_START_ACK_TIMEOUT", 5.0),
                frame_timeout=CONFIG.get("SCENE_FIRST_FRAME_TIMEOUT", 30.0),
                on_event=(lambda event: self.diagnostics.record("scene_control", detail=event)) if self.diagnostics else None,
            )
            self.preloaded_scene_path = scene_path
            self.preloaded_scene_name = os.path.basename(scene_path)
            self._announce_launch(self.preloaded_scene_name, mode="preload")
            self.preloaded_process = self._launch_scene_process(scene_path, self.preloaded_control)
            return True
        except (OSError, SceneControlError) as exc:
            self._fail_switch(str(exc))
            return False

    def launch_scene(self, scene_path):
        if scene_path not in self.all_scenes:
            raise ConfigurationError(f"Scene is outside PRODUCTION_SCENES: {scene_path}")
        if self.switch_pending or self.transition_process is not None:
            return False
        if not self._discard_preloaded():
            return False
        self.scene_index = self.all_scenes.index(scene_path)
        return self.switch_scene()

    def switch_scene(self):
        if not self.all_scenes or self.switch_pending or self.transition_process is not None:
            return False
        self.last_switch_error = None
        self.switch_pending = True
        self.switch_cover_until = None
        if not self._ensure_preloaded_scene():
            self.switch_pending = False
            return False
        self.tick()
        return self.last_switch_error is None

    def _fail_switch(self, reason):
        self.last_switch_error = reason
        print(f"[Manager] Candidate failed: {self.preloaded_scene_name}: {reason}")
        self.switch_pending = False
        self.switch_cover_until = None
        if not self._discard_preloaded():
            self.fatal_error = "failed candidate could not be stopped: " + reason
        elif not self.is_scene_running():
            self.fatal_error = "no running scene after candidate failure: " + reason

    def tick(self):
        now = time.monotonic()
        transition = self.transition_process
        if transition is not None:
            if transition.poll() is not None:
                self.transition_process = None
            elif now - self.transition_started_at > float(CONFIG.get("TRANSITION_TOTAL_DURATION", 5.0)) + 1.0:
                if self._kill_process(transition, "sakura_transition"):
                    self.transition_process = None
                else:
                    self.fatal_error = "transition overlay could not be stopped"

        if self.preloaded_process is None or self.fatal_error:
            return
        try:
            control = self.preloaded_control
            state = control.poll(self.preloaded_process)
            if not self.switch_pending:
                return
            if state == "READY":
                control.start()
                return
            if state != "FIRST_FRAME":
                return

            expected_shm = self.camera_env.get("HARUKAZE_CAMERA_SHM")
            if expected_shm and control.first_frame.get("shm_name") != expected_shm:
                raise SceneControlError("FIRST_FRAME came from a different shared camera")

            if self.switch_cover_until is None:
                overlay = self._start_transition_overlay() if self.is_scene_running() else None
                delay = float(CONFIG.get("TRANSITION_COVER_DELAY", 1.5)) if overlay else 0.0
                self.switch_cover_until = now + max(0.0, delay)
            if now < self.switch_cover_until:
                return
            if not self.kill_current():
                raise SceneControlError("current scene could not be stopped; keeping its handle")

            self.running_process = self.preloaded_process
            self.running_scene_path = self.preloaded_scene_path
            self.current_scene_name = self.preloaded_scene_name
            print(f"[Manager] Promoted {self.current_scene_name} pid={self.running_process.pid} after FIRST_FRAME")
            self.scene_index += 1
            self.completed_switches += 1
            self._clear_preloaded()
            self.switch_pending = False
            self.switch_cover_until = None
            if self.preload_enabled:
                self._ensure_preloaded_scene()
        except (OSError, SceneControlError) as exc:
            self._fail_switch(str(exc))

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

        uncontained = getattr(self, "uncontained_process", None)
        if uncontained is not None and run_step("uncontained scene", lambda: self._kill_process(uncontained, "failed launch")):
            self.uncontained_process = None

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
        holistic = None
        try:
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
        except Exception as exc:
            self.status = "failed"
            print(f"[Monitor] Error: {exc}")
        finally:
            if holistic is not None:
                try:
                    holistic.close()
                except Exception as exc:
                    print(f"[Monitor] Cleanup error: {exc}")


def _positive_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be positive and finite")
    return number


def main():
    global CONFIG
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="Use an explicit configuration file, e.g. configs/kids_test_acer.json")
    parser.add_argument("--report-dir", help="Write bounded trial logs and resource observations here")
    parser.add_argument("--duration-seconds", type=_positive_seconds, help="Stop this trial after the first scene has run this long")
    parser.add_argument("--switch-interval-seconds", type=_positive_seconds, help="Request a trial switch after each successful scene has run this long")
    parser.add_argument("--switch-count", type=int, help="Stop after this many successful trial switches, excluding initial launch")
    parser.add_argument(
        "--camera-only",
        action="store_true",
        help="Start only the shared camera relay for manual scene editing.",
    )
    args = parser.parse_args()
    if args.switch_count is not None and (args.switch_count <= 0 or args.switch_interval_seconds is None):
        parser.error("--switch-count requires a positive count and --switch-interval-seconds")
    if args.camera_only and (args.switch_count or args.switch_interval_seconds):
        parser.error("camera-only mode cannot run scene switch trials")

    if args.config:
        try:
            if not os.path.isfile(args.config):
                raise ConfigurationError(f"Config file not found: {args.config}")
            CONFIG = load_config(args.config)
        except ConfigurationError as exc:
            print(f"[Manager] Configuration error: {exc}")
            return 2
    elif CONFIG_LOAD_ERROR is not None:
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
    diagnostics = None
    trial_started_at = None
    next_switch_at = None
    observed_switches = 0
    next_sample_at = 0.0
    stop_reason = "error"
    exit_code = 0
    try:
        if args.report_dir:
            diagnostics = RuntimeDiagnostics(args.report_dir, CONFIG)
            print(f"[Manager] Trial logs: {diagnostics.directory}")
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
            require_name_match=CONFIG.get("CAMERA_REQUIRE_NAME_MATCH", False),
            exposure=CONFIG.get("CAMERA_EXPOSURE"),
        )
        camera_relay.start()

        camera_env = camera_relay.export_env()
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
            manager = SceneManager(camera_env=camera_env, scenes=production_scenes, diagnostics=diagnostics)

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
            now = time.monotonic()
            if camera_relay.thread is not None and not camera_relay.thread.is_alive():
                raise RuntimeError(f"Camera capture thread stopped: {camera_relay.last_error}")
            if manager is not None:
                manager.tick()
                if manager.fatal_error:
                    raise RuntimeError(manager.fatal_error)
                if (args.switch_interval_seconds or args.duration_seconds) and manager.last_switch_error:
                    raise RuntimeError(f"Trial switch failed: {manager.last_switch_error}")

            if trial_started_at is None and (manager is None or manager.is_scene_running()):
                trial_started_at = time.monotonic()
                if diagnostics:
                    diagnostics.record("trial_started")
            if manager is not None and manager.completed_switches != observed_switches:
                observed_switches = manager.completed_switches
                next_switch_at = time.monotonic() + args.switch_interval_seconds if args.switch_interval_seconds else None
            if diagnostics and now >= next_sample_at:
                diagnostics.sample(camera_relay, manager)
                next_sample_at = now + 10.0
            if args.duration_seconds and trial_started_at is not None and now - trial_started_at >= args.duration_seconds:
                stop_reason = "duration_reached"
                break
            if (args.switch_count and manager is not None and manager.completed_switches >= args.switch_count + 1
                    and manager.transition_process is None and not manager.switch_pending):
                stop_reason = "switch_count_reached"
                break
            if next_switch_at is not None and now >= next_switch_at and manager is not None:
                if manager.switch_scene():
                    next_switch_at = None
            if monitor and monitor.consume_clap() and manager is not None:
                print("[Manager] Head clap detected. Switching scene.")
                manager.switch_scene()

            if manager is not None and not manager.is_scene_running() and not manager.switch_pending:
                print(f"[Manager] Scene '{manager.current_scene_name}' exited. Launching next...")
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
                stop_reason = "user_quit"
                break
            if key == ord("n") and manager is not None:
                print("[Manager] Keyboard next scene")
                manager.switch_scene()

    except KeyboardInterrupt:
        stop_reason = "user_interrupt"
        print("\n[Manager] Interrupted by user.")
    except Exception as exc:
        print(f"[Manager] Fatal error: {exc}")
        traceback.print_exc()
        exit_code = 1
        if diagnostics:
            try:
                diagnostics.record("run_error", reason=str(exc), traceback=traceback.format_exc())
            except OSError:
                pass
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
        if diagnostics:
            try:
                diagnostics.record("run_end", reason=stop_reason, exit_code=exit_code,
                                   trial_elapsed_s=time.monotonic() - trial_started_at if trial_started_at else 0,
                                   completed_switches=max(0, manager.completed_switches - 1) if manager else 0,
                                   human_check_required=True)
            except OSError as exc:
                print(f"[Manager] Report error: {exc}")
                exit_code = 1
            try:
                if not diagnostics.close():
                    print(f"[Manager] Report cleanup incomplete: {diagnostics.error}")
                    exit_code = 1
            except OSError as exc:
                print(f"[Manager] Report cleanup error: {exc}")
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
