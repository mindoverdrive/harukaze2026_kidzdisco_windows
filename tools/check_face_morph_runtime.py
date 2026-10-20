"""Opt-in, camera-free integration check of the real Face Morph child process.

The hardware capture boundary supplies generated colour frames. Manager, its
Windows Job and TCP protocol, relay publication, MediaPipe, OpenCV and Pygame
remain real. SDL's dummy driver does not prove monitor output or face tracking.
No photo/video is read or saved. All evidence goes to the required output folder.
"""
from contextlib import ExitStack
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# This temporary startup hook delegates successful operations to the installed
# libraries. Counters are evidence, not substitute render/detection results.
CHILD_PROBE = r'''
import atexit, json, os, pathlib, socket, sys, time
stats = {"pid": os.getpid(), "physical_capture_attempts": 0,
         "external_network_attempts": 0, "detector_attempts": 0,
         "detector_created": 0, "detector_closed": 0, "processed_frames": 0,
         "faces_detected": 0, "display_flips": 0, "shared_releases": 0,
         "pygame_quits": 0, "hook_loaded": True,
         "process_total_s": 0.0, "process_max_s": 0.0,
         "flip_total_s": 0.0, "flip_max_s": 0.0}
def save(point="atexit"):
    stats["observation_point"] = point
    stats["pygame_initialized_at_exit"] = pygame.get_init()
    stats["display_initialized_at_exit"] = pygame.display.get_init()
    path = pathlib.Path(os.environ["FACE_MORPH_PROBE_DIR"]) / ("probe_" + str(os.getpid()) + ".json")
    path.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
def local_only(host):
    if host not in ("localhost", "127.0.0.1", "::1"):
        stats["external_network_attempts"] += 1
        raise RuntimeError("Runtime probe prohibits external network access")
real_connect, real_getaddrinfo = socket.socket.connect, socket.getaddrinfo
def connect(sock, address):
    local_only(address[0]); return real_connect(sock, address)
def getaddrinfo(host, *args, **kwargs):
    local_only(host); return real_getaddrinfo(host, *args, **kwargs)
socket.socket.connect, socket.getaddrinfo = connect, getaddrinfo
import cv2
def no_capture(*args, **kwargs):
    stats["physical_capture_attempts"] += 1
    raise RuntimeError("Runtime probe prohibits physical camera access")
cv2.VideoCapture = no_capture
import pygame
atexit.register(save)
real_flip, real_quit = pygame.display.flip, pygame.quit
def flip():
    if not stats["display_flips"]:
        delay = float(os.environ.get("FACE_MORPH_PROBE_FLIP_DELAY", "0"))
        if delay:
            stats["injected_first_flip_delay_s"] = delay
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                time.sleep(0.01)
    started = time.perf_counter()
    result = real_flip()
    elapsed = time.perf_counter() - started
    stats["flip_total_s"] += elapsed
    stats["flip_max_s"] = max(stats["flip_max_s"], elapsed)
    stats["display_flips"] += 1
    now = time.monotonic()
    stats.setdefault("first_flip_monotonic", now)
    stats["last_flip_monotonic"] = now
    stats["display_driver"] = pygame.display.get_driver()
    stats["surface_size"] = list(pygame.display.get_surface().get_size())
    stats["surface_flags"] = pygame.display.get_surface().get_flags()
    if stats["display_flips"] == 1 and stats["display_driver"] == "windows":
        import ctypes
        from ctypes import wintypes
        hwnd = pygame.display.get_wm_info().get("window")
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        rect = wintypes.RECT()
        stats["window_visible"] = bool(user32.IsWindowVisible(hwnd))
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            stats["window_rect"] = [rect.left, rect.top, rect.right, rect.bottom]
    return result
def quit():
    result = real_quit(); stats["pygame_quits"] += 1
    # ERROR reaches Manager after ExitStack has closed the app's resources.
    # Persist here because an ensuing CTRL_BREAK may precede Python's atexit.
    save("pygame_quit")
    return result
pygame.display.flip, pygame.quit = flip, quit
import mediapipe as mp
face_module = mp.solutions.face_mesh
if os.environ.get("FACE_MORPH_PROBE_FAIL_MODEL") == "1":
    face_module._BINARYPB_FILE_PATH = os.environ["FACE_MORPH_PROBE_MISSING_GRAPH"]
real_face_mesh = face_module.FaceMesh
def face_mesh(*args, **kwargs):
    stats["detector_attempts"] += 1
    detector = real_face_mesh(*args, **kwargs)
    stats["detector_created"] += 1
    real_process, real_close = detector.process, detector.close
    def process(frame):
        started = time.perf_counter()
        result = real_process(frame)
        elapsed = time.perf_counter() - started
        stats["process_total_s"] += elapsed
        stats["process_max_s"] = max(stats["process_max_s"], elapsed)
        stats["processed_frames"] += 1
        stats["faces_detected"] += len(result.multi_face_landmarks or ())
        return result
    def close():
        result = real_close(); stats["detector_closed"] += 1; return result
    detector.process, detector.close = process, close
    return detector
face_module.FaceMesh = face_mesh
sys.path.insert(0, os.environ["FACE_MORPH_PROBE_SOURCE"])
import shared_camera
real_release = shared_camera.SharedMemoryCamera.release
def release(camera):
    was_closed = camera.closed
    result = real_release(camera)
    if not was_closed and camera.closed: stats["shared_releases"] += 1
    return result
shared_camera.SharedMemoryCamera.release = release
'''


class SyntheticFeed:
    """Only the physical capture is substituted; relay operations stay real."""

    def __init__(self, width=320, height=240, fps=30):
        self.width, self.height, self.fps = width, height, fps
        self.mode = "running"
        self.captures = []
        self.frames = 0

    def open(self, stop_event):
        capture = SyntheticCapture(self, stop_event)
        self.captures.append(capture)
        return capture


class SyntheticCapture:
    def __init__(self, feed, stop_event):
        self.feed, self.stop_event = feed, stop_event
        self.released = False

    def isOpened(self):
        return not self.released

    def get(self, prop):
        import cv2
        return {cv2.CAP_PROP_FRAME_WIDTH: self.feed.width,
                cv2.CAP_PROP_FRAME_HEIGHT: self.feed.height,
                cv2.CAP_PROP_FPS: self.feed.fps,
                cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"MJPG"),
                cv2.CAP_PROP_BACKEND: cv2.CAP_ANY}.get(prop, 0)

    def read(self):
        import numpy as np
        while self.feed.mode == "freeze" and not self.released:
            if self.stop_event.wait(0.02):
                return False, None
        if self.stop_event.wait(1 / self.feed.fps) or self.released:
            return False, None
        if self.feed.mode == "error":
            raise RuntimeError("injected synthetic capture read failure")
        self.feed.frames += 1
        frame = np.empty((self.feed.height, self.feed.width, 3), dtype=np.uint8)
        frame[:, :, 0] = np.arange(self.feed.width, dtype=np.uint8)[None, :]
        frame[:, :, 1] = np.arange(self.feed.height, dtype=np.uint8)[:, None]
        frame[:, :, 2] = self.feed.frames % 256
        return True, frame

    def release(self):
        self.released = True


def wait_for(condition, timeout, step=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if step is not None:
            step()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("Bounded integration wait timed out")


def require(value, message):
    if not value:
        raise AssertionError(message)


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_scenario(name, output, hook_dir, repeats, visible=False, steady_seconds=0.5):
    import cv2
    import manager
    import shared_camera
    from multiprocessing import shared_memory
    from runtime_diagnostics import RuntimeDiagnostics, process_sample
    from windows_process import get_scene_job

    directory = output / name
    directory.mkdir()
    feed = SyntheticFeed()
    processes, controls, jobs = [], [], []
    result = {"scenario": name, "passed": False, "promotions": 0,
              "completed_switches": 0, "cleanup": {}}
    config = dict(manager.CONFIG, TRANSITION_ENABLED=False, PRELOAD_COUNT=0,
                  DISPLAY_TARGET="stage", DISPLAY_X=0, DISPLAY_Y=0,
                  DISPLAY_WIDTH=640, DISPLAY_HEIGHT=360,
                  SCENE_READY_TIMEOUT=15.0, SCENE_START_ACK_TIMEOUT=5.0,
                  SCENE_FIRST_FRAME_TIMEOUT=15.0)
    environment = {
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(hook_dir), "SDL_VIDEODRIVER": "windows" if visible else "dummy",
        "SDL_AUDIODRIVER": "dummy",
        "MATAHARI_FACE_CHECK": "0", "MATAHARI_FACE_INPUT": "detector",
        "FACE_MORPH_PROBE_DIR": str(directory), "FACE_MORPH_PROBE_SOURCE": str(ROOT),
        "FACE_MORPH_PROBE_FAIL_MODEL": "0",
        "FACE_MORPH_PROBE_FLIP_DELAY": "0",
        "FACE_MORPH_PROBE_MISSING_GRAPH": str(hook_dir / "intentionally_missing.binarypb"),
    }
    relay = scene_manager = diagnostics = None
    shm_name = None
    before = process_sample(os.getpid())
    with ExitStack() as scope:
        scope.enter_context(mock.patch.dict(os.environ, environment))
        scope.enter_context(mock.patch.object(manager, "CONFIG", config))
        scope.enter_context(mock.patch.object(shared_camera, "SESSION_INFO_PATH", str(hook_dir / (name + ".json"))))
        scope.enter_context(mock.patch.object(shared_camera, "choose_camera_index", return_value=0))
        scope.enter_context(mock.patch.object(cv2, "VideoCapture", side_effect=AssertionError("Physical capture prohibited")))
        try:
            relay = shared_camera.SharedCameraRelay(0, feed.width, feed.height, feed.fps, diagnostic_seconds=0)
            # The owned synthetic handle is the only substituted hardware boundary.
            relay._create_capture = lambda: feed.open(relay.stop_event)
            relay.start()
            shm_name = relay.shm_name
            wait_for(lambda: relay.frame_id > 1, 3)
            diagnostics = RuntimeDiagnostics(directory, {
                "mode": "synthetic_window" if visible else "synthetic_offscreen", **config})
            scene_manager = manager.SceneManager(
                camera_env=relay.export_env(), scenes=[str(ROOT / "face_morph_acer.py")], diagnostics=diagnostics)

            def launch(expect_success=True):
                previous = scene_manager.running_process
                require(scene_manager.request_scene("next"), "Manager rejected launch")
                process, control = scene_manager.preloaded_process, scene_manager.preloaded_control
                require(process is not None and control is not None, "Child was not spawned")
                processes.append(process); controls.append(control)
                jobs.append(get_scene_job(process))
                wait_for(lambda: not scene_manager.switch_pending, 22, scene_manager.tick)
                if expect_success:
                    require(scene_manager.last_switch_error is None, str(scene_manager.last_switch_error))
                    require(scene_manager.is_scene_running(), "Promoted process is not alive")
                    require(control.first_frame and control.first_frame["shm_name"] == shm_name,
                            "No FIRST_FRAME from the owned shared input")
                    require(control.first_frame["frame_id"] > 0, "Missing real frame ID")
                    if previous is not None:
                        require(previous.poll() is not None, "Predecessor did not stop")
                    # Keep the actual detector/render loop alive beyond its first frame.
                    time.sleep(steady_seconds)
                    require(process.poll() is None, "Child died immediately after FIRST_FRAME")
                    diagnostics.sample(relay, scene_manager)
                else:
                    require(scene_manager.last_switch_error, "Failed startup was not rejected")
                    require(control.first_frame is None, "Failed startup announced FIRST_FRAME")
                    if previous is not None:
                        require(scene_manager.running_process is previous and previous.poll() is None,
                                "Failed candidate displaced healthy predecessor")
                return process

            if name == "startup_without_frames":
                feed.mode = "error"
                wait_for(lambda: relay.read_failures_total > 0, 3)
                launch(expect_success=False)
                require(scene_manager.completed_promotions == 0, "Empty input was promoted")
            elif name in {"model_initialization_failure", "late_first_frame"}:
                launch()
                if name == "model_initialization_failure":
                    os.environ["FACE_MORPH_PROBE_FAIL_MODEL"] = "1"
                else:
                    os.environ["FACE_MORPH_PROBE_FLIP_DELAY"] = "3"
                    config["SCENE_FIRST_FRAME_TIMEOUT"] = 0.5
                launch(expect_success=False)
                require(scene_manager.completed_promotions == 1, "Failed candidate was promoted")
                if name == "late_first_frame":
                    require("FIRST_FRAME timeout" in scene_manager.last_switch_error,
                            "Late frame did not expire the real control deadline")
            else:
                for _ in range(repeats if name == "repeat_and_freeze" else 1):
                    launch()
                feed.mode = "freeze" if name == "repeat_and_freeze" else "error"
                process = scene_manager.running_process
                wait_for(lambda: process.poll() is not None, 8)
                require(process.returncode != 0, "Stalled input unexpectedly exited successfully")
                if feed.mode == "error":
                    require(relay.read_failures_total > 0 and relay.reopen_attempts > 0,
                            "Real relay error/reconnect path was not exercised")
            result.update(promotions=scene_manager.completed_promotions,
                          completed_switches=scene_manager.completed_switches,
                          startup_error=scene_manager.last_switch_error,
                          first_frames=[control.first_frame for control in controls if control.first_frame],
                          shared_read_failures=relay.read_failures_total,
                          shared_reopen_attempts=relay.reopen_attempts)
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            # Only objects and process groups created by this scenario are stopped.
            if scene_manager is not None:
                result["cleanup"]["manager"] = scene_manager.cleanup()
            if relay is not None:
                result["cleanup"]["relay"] = relay.close()
                result["cleanup"]["relay_idempotent"] = relay.close()
                result["cleanup"]["capture_thread_stopped"] = not (relay.thread and relay.thread.is_alive())
            if diagnostics is not None:
                result["cleanup"]["diagnostics"] = diagnostics.close()
            result["cleanup"]["all_children_exited"] = all(p.poll() is not None for p in processes)
            result["cleanup"]["all_jobs_closed"] = all(j is None or not j._job_handles() for j in jobs)
            result["cleanup"]["all_synthetic_captures_released"] = all(c.released for c in feed.captures)
            result["cleanup"]["session_removed"] = not Path(shared_camera.SESSION_INFO_PATH).exists()
            result["cleanup"]["control_listeners_closed"] = all(c.listener.fileno() == -1 for c in controls)
            result["cleanup"]["control_channels_closed"] = all(c.channel is None or c.channel.sock.fileno() == -1 for c in controls)
            if shm_name:
                try:
                    leaked = shared_memory.SharedMemory(name=shm_name)
                except FileNotFoundError:
                    result["cleanup"]["shared_memory_removed"] = True
                else:
                    leaked.close()
                    result["cleanup"]["shared_memory_removed"] = False

    probes = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("probe_*.json"))]
    result["probes"] = probes
    result["processes"] = [{"launcher_pid": p.pid, "scene_pid": getattr(p, "_scene_pid", None),
                            "returncode": p.returncode} for p in processes]
    result["manager_sample_before"] = before
    result["manager_sample_after"] = process_sample(os.getpid())
    checks = {
        "one_probe_per_child": len(probes) == len(processes) and bool(probes),
        "no_physical_camera_attempt": all(p["physical_capture_attempts"] == 0 for p in probes),
        "no_external_network_attempt": all(p["external_network_attempts"] == 0 for p in probes),
        "real_detectors_closed": all(p["detector_created"] == p["detector_closed"] for p in probes),
        "shared_consumers_released": all(p["shared_releases"] == 1 for p in probes),
        "pygame_closed": all(p["pygame_quits"] >= 1 and not p["pygame_initialized_at_exit"]
                             and not p["display_initialized_at_exit"] for p in probes),
        "real_render": sum(p["display_flips"] > 0 and p["processed_frames"] > 0
                           and p.get("display_driver") == ("windows" if visible else "dummy")
                           for p in probes) == result["promotions"],
    }
    if visible:
        checks["windows_visible"] = all(p.get("window_visible") is True for p in probes if p["display_flips"])
    if name == "model_initialization_failure":
        checks["real_model_failure"] = sum(p["detector_attempts"] == 1 and p["detector_created"] == 0 for p in probes) == 1
    result["checks"] = checks
    result["passed"] = not result.get("error") and all(result["cleanup"].values()) and all(checks.values())
    (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def run_checks(output, repeats=3, visible=False, scenarios=None, steady_seconds=0.5):
    if os.name != "nt":
        raise RuntimeError("This check requires the Windows Manager/Job runtime")
    if repeats < 2:
        raise ValueError("Use at least two launches to exercise a real scene switch")
    if not 0.1 <= steady_seconds <= 30:
        raise ValueError("steady_seconds must be between 0.1 and 30")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_files = [ROOT / name for name in ("manager.py", "shared_camera.py", "scene_control.py",
                    "scene_profile_runner.py", "face_morph_acer.py", "face_morph_app.py", "face_morph_field.py")]
    hashes = {path.name: file_digest(path) for path in source_files}
    report = {"mode": "synthetic_input_and_sdl_windows" if visible else "synthetic_input_and_sdl_dummy",
              "physical_camera_tested": False, "native_window_tested": visible,
              "visual_quality_tested": False, "live_face_tracking_tested": False,
              "photo_or_video_saved": False, "python": sys.executable, "python_version": sys.version,
              "source": str(ROOT), "source_sha256": hashes, "scenarios": []}
    for package in ("numpy", "opencv-contrib-python", "mediapipe", "pygame", "pygame-ce"):
        try:
            report.setdefault("packages", {})[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report.setdefault("packages", {})[package] = None
    with tempfile.TemporaryDirectory(prefix="isolated_", dir=output) as temporary:
        hook_dir = Path(temporary)
        (hook_dir / "sitecustomize.py").write_text(CHILD_PROBE, encoding="utf-8")
        for name in scenarios or ("repeat_and_freeze", "input_read_error", "startup_without_frames", "model_initialization_failure", "late_first_frame"):
            result = run_scenario(name, output, hook_dir, repeats, visible, steady_seconds)
            report["scenarios"].append(result)
            print(json.dumps({"scenario": name, "passed": result["passed"], "error": result.get("error")}), flush=True)
    report["source_unchanged_during_run"] = hashes == {path.name: file_digest(path) for path in source_files}
    report["passed"] = report["source_unchanged_during_run"] and all(s["passed"] for s in report["scenarios"])
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory for JSON/log evidence; no media is saved")
    parser.add_argument("--repeats", default=3, type=int)
    parser.add_argument("--visible", action="store_true", help="Use a bounded 640x360 native SDL window")
    parser.add_argument("--steady-seconds", default=0.5, type=float, help="Seconds to keep each promoted child rendering (0.1-30)")
    parser.add_argument("--scenario", action="append", choices=("repeat_and_freeze", "input_read_error", "startup_without_frames", "model_initialization_failure", "late_first_frame"))
    args = parser.parse_args()
    report = run_checks(args.output, args.repeats, args.visible, args.scenario, args.steady_seconds)
    print(json.dumps({"passed": report["passed"], "summary": str(args.output.resolve() / "summary.json")}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
