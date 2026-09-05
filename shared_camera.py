import os
import json
import struct
import threading
import time
import uuid
from multiprocessing import shared_memory

import cv2
import numpy as np


HEADER_FORMAT = "<8sIIIIQQd"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
# Version 2 timestamps use the machine's monotonic clock, including across processes.
MAGIC = b"HARUCAM2"

ENV_ENABLED = "HARUKAZE_SHARED_CAMERA"
ENV_REQUIRED = "HARUKAZE_SHARED_CAMERA_REQUIRED"
ENV_SHM_NAME = "HARUKAZE_CAMERA_SHM"
ENV_WIDTH = "HARUKAZE_CAMERA_WIDTH"
ENV_HEIGHT = "HARUKAZE_CAMERA_HEIGHT"
ENV_CHANNELS = "HARUKAZE_CAMERA_CHANNELS"
ENV_FPS = "HARUKAZE_CAMERA_FPS"
ENV_FOURCC = "HARUKAZE_CAMERA_FOURCC"
SESSION_INFO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".shared_camera_session.json")
DEFAULT_READ_FAILURE_REOPEN_THRESHOLD = 30
FRAME_MAX_AGE_SECONDS = 2.0
RECONNECT_INITIAL_DELAY = 0.25
RECONNECT_MAX_DELAY = 5.0
CAPTURE_JOIN_TIMEOUT = 2.0


def enumerate_camera_devices():
    try:
        from pygrabber.dshow_graph import FilterGraph

        return list(FilterGraph().get_input_devices())
    except Exception:
        return []


def resolve_camera_index(camera_index, camera_name_hint=None, exclude_name_hints=None, require_name_match=False):
    devices = enumerate_camera_devices()
    if not devices:
        if require_name_match:
            raise RuntimeError("No camera matches: device enumeration unavailable; check pygrabber and C922")
        return int(camera_index)

    excludes = [str(item).lower() for item in (exclude_name_hints or [])]
    hints = camera_name_hint or []
    if isinstance(hints, str):
        hints = [hints]
    hints = [str(item).lower() for item in hints if str(item).strip()]

    for idx, name in enumerate(devices):
        lower_name = name.lower()
        if any(ex in lower_name for ex in excludes):
            continue
        if any(hint in lower_name for hint in hints):
            print(f"[shared_camera] Selected camera by name: index={idx} name={name}")
            return idx

    print(f"[shared_camera] Camera hint did not match. Available devices: {devices}")
    if require_name_match:
        raise RuntimeError(f"No camera matches required hints {hints}; detected devices: {devices}")
    return int(camera_index)


def choose_camera_index(camera_index, camera_name_hint=None, exclude_name_hints=None, explicit_index=None, require_name_match=False):
    if explicit_index is not None:
        explicit_index = int(explicit_index)
        if explicit_index < 0:
            raise RuntimeError(f"Explicit OpenCV camera index must be non-negative: {explicit_index}")

        devices = enumerate_camera_devices()
        if devices:
            if explicit_index >= len(devices):
                raise RuntimeError(
                    f"Explicit OpenCV camera index={explicit_index} is outside detected devices {devices}"
                )
            selected_name = str(devices[explicit_index])
            lower_name = selected_name.lower()
            excludes = [str(item).lower() for item in (exclude_name_hints or [])]
            hints = camera_name_hint or []
            if isinstance(hints, str):
                hints = [hints]
            hints = [str(item).lower() for item in hints if str(item).strip()]
            if any(exclude in lower_name for exclude in excludes):
                raise RuntimeError(
                    f"Explicit OpenCV camera index={explicit_index} selects excluded device {selected_name!r}"
                )
            if hints and not any(hint in lower_name for hint in hints):
                raise RuntimeError(
                    f"Explicit OpenCV camera index={explicit_index} device {selected_name!r} "
                    f"does not match configured hints {hints}"
                )
            print(
                f"[shared_camera] Using explicit OpenCV camera index={explicit_index} "
                f"name={selected_name}"
            )
        else:
            if require_name_match:
                raise RuntimeError("No camera matches: cannot verify explicit index without device enumeration")
            print(
                f"[shared_camera] Using explicit OpenCV camera index={explicit_index}; "
                "device name could not be enumerated"
            )
        return explicit_index
    return resolve_camera_index(camera_index, camera_name_hint, exclude_name_hints, require_name_match)


def _backend_from_name(name):
    mapping = {
        "default": None,
        "any": cv2.CAP_ANY,
        "msmf": cv2.CAP_MSMF,
        "dshow": cv2.CAP_DSHOW,
    }
    return mapping.get(str(name).lower(), None)


def _backend_order(preference, strict_backend=False):
    key = str(preference or "default").lower()
    if strict_backend:
        backend = _backend_from_name(key)
        if backend is None:
            return [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        return [backend]
    if key == "dshow":
        return [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
    if key == "msmf":
        return [cv2.CAP_MSMF, cv2.CAP_ANY, cv2.CAP_DSHOW]
    if key == "any":
        return [cv2.CAP_ANY, cv2.CAP_MSMF, cv2.CAP_DSHOW]
    # On this Windows setup, the default backend can hang before returning.
    return [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]


def _decode_fourcc(value):
    try:
        packed = struct.pack("<I", int(value))
        return packed.decode("ascii", errors="ignore").strip("\x00")
    except Exception:
        return str(value)


def _normalize_fourcc(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"auto", "default", "none"}:
        return None
    return text[:4]


def _measure_capture_fps(cap, sample_seconds=2.0):
    sample_seconds = max(float(sample_seconds), 0.25)
    frames = 0
    first_ts = None
    last_ts = None
    deadline = time.perf_counter() + sample_seconds

    while time.perf_counter() < deadline:
        ret, _frame = cap.read()
        if not ret:
            continue
        now = time.perf_counter()
        if first_ts is None:
            first_ts = now
        last_ts = now
        frames += 1

    if first_ts is None or last_ts is None or last_ts <= first_ts:
        return 0.0, frames

    elapsed = last_ts - first_ts
    return frames / elapsed, frames


def _open_with_backends(
    camera_index,
    width,
    height,
    fps,
    fourcc,
    backend_preference,
    fallback_to_default,
    strict_backend=False,
):
    def _setup_props(cap):
        normalized_fourcc = _normalize_fourcc(fourcc)
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 1)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if normalized_fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*normalized_fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)

    indices = [camera_index]
    if fallback_to_default:
        indices.extend(idx for idx in (0, 1, 2) if idx != camera_index)
    for idx in indices:
        for backend in _backend_order(backend_preference, strict_backend=strict_backend):
            cap = None
            opened = False
            try:
                print(f"[shared_camera] Trying camera index={idx} backend={backend}")
                cap = cv2.VideoCapture(idx) if backend is None else cv2.VideoCapture(idx, backend)
                if cap.isOpened():
                    _setup_props(cap)
                    actual_fourcc = _decode_fourcc(cap.get(cv2.CAP_PROP_FOURCC))
                    print(f"[shared_camera] Opened physical camera index={idx} "
                          f"backend={backend} fourcc={actual_fourcc}")
                    opened = True
                    return cap
            except Exception as exc:
                print(f"[shared_camera] Open/setup failed index={idx} backend={backend}: {exc}")
            finally:
                if cap is not None and not opened:
                    # Do not open another handle if releasing this one fails.
                    cap.release()

    return None


class SharedMemoryCamera:
    def __init__(self, shm_name, width, height, channels=3, fps=60):
        self.shm_name = shm_name
        self.width = int(width)
        self.height = int(height)
        self.channels = int(channels)
        self.fps = float(fps)
        self.frame_bytes = self.width * self.height * self.channels
        self.closed = False
        self.last_read_frame_id = 0
        self.shm = shared_memory.SharedMemory(name=shm_name)

    def isOpened(self):
        return not self.closed

    def release(self):
        if self.closed:
            return
        self.shm.close()
        self.closed = True

    def set(self, prop_id, value):
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            self.width = int(value)
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            self.height = int(value)
        elif prop_id == cv2.CAP_PROP_FPS:
            self.fps = float(value)
        return True

    def get(self, prop_id):
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.width)
        if prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.height)
        if prop_id == cv2.CAP_PROP_FPS:
            return float(self.fps)
        return 0.0

    def read(self):
        if self.closed:
            return False, None

        for _ in range(5):
            header1 = struct.unpack_from(HEADER_FORMAT, self.shm.buf, 0)
            magic, width, height, channels, status, write_seq1, frame_id, timestamp = header1
            if magic != MAGIC or write_seq1 % 2 == 1:
                time.sleep(0.001)
                continue

            frame_bytes = width * height * channels
            age = time.monotonic() - timestamp
            if (status != 2 or frame_id <= 0 or not 0 <= age <= FRAME_MAX_AGE_SECONDS
                    or width <= 0 or height <= 0 or channels != 3
                    or frame_bytes > len(self.shm.buf) - HEADER_SIZE):
                return False, None
            frame_buffer = bytes(self.shm.buf[HEADER_SIZE:HEADER_SIZE + frame_bytes])

            header2 = struct.unpack_from(HEADER_FORMAT, self.shm.buf, 0)
            write_seq2 = header2[5]
            if header1 == header2 and write_seq2 % 2 == 0:
                frame = np.frombuffer(frame_buffer, dtype=np.uint8).reshape((height, width, channels))
                self.last_read_frame_id = int(header2[6])
                return True, frame.copy()

        return False, None

    @classmethod
    def from_env(cls):
        if os.environ.get(ENV_ENABLED) != "1":
            return None
        shm_name = os.environ.get(ENV_SHM_NAME)
        width = os.environ.get(ENV_WIDTH)
        height = os.environ.get(ENV_HEIGHT)
        channels = os.environ.get(ENV_CHANNELS, "3")
        fps = os.environ.get(ENV_FPS, "60")
        if not shm_name or not width or not height:
            return None
        return cls(shm_name=shm_name, width=width, height=height, channels=channels, fps=fps)

    @classmethod
    def from_session_file(cls):
        try:
            with open(SESSION_INFO_PATH, "r", encoding="utf-8") as f:
                session = json.load(f)
        except Exception:
            return None

        try:
            shm_name = session["shm_name"]
            width = session["width"]
            height = session["height"]
            channels = session.get("channels", 3)
            fps = session.get("fps", 60)
            return cls(shm_name=shm_name, width=width, height=height, channels=channels, fps=fps)
        except Exception:
            return None


class SharedCameraRelay:
    def __init__(
        self,
        camera_index,
        width,
        height,
        fps,
        backend_preference="default",
        fallback_to_default=False,
        camera_name_hint=None,
        exclude_name_hints=None,
        explicit_index=None,
        fourcc="MJPG",
        diagnostic_seconds=2.0,
        strict_backend=True,
        require_name_match=False,
    ):
        self.requested_camera_index = int(camera_index)
        self.camera_index = choose_camera_index(
            camera_index,
            camera_name_hint=camera_name_hint,
            exclude_name_hints=exclude_name_hints,
            explicit_index=explicit_index,
            require_name_match=require_name_match,
        )
        self.width = int(width)
        self.height = int(height)
        self.channels = 3
        self.fps = float(fps)
        self.fourcc = str(fourcc or "MJPG")
        self.diagnostic_seconds = float(diagnostic_seconds)
        self.strict_backend = bool(strict_backend)
        self.backend_preference = backend_preference
        self.fallback_to_default = fallback_to_default
        self.camera_name_hint = camera_name_hint
        self.exclude_name_hints = exclude_name_hints
        self.explicit_index = explicit_index
        self.require_name_match = require_name_match
        self.frame_bytes = self.width * self.height * self.channels
        self.shm_name = f"harukaze_cam_{os.getpid()}_{uuid.uuid4().hex[:12]}"
        self.shm = shared_memory.SharedMemory(create=True, size=HEADER_SIZE + self.frame_bytes, name=self.shm_name)
        self.cap = None
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.latest_frame = None
        self.latest_timestamp = 0.0
        self.last_success_at = None
        self.max_frame_gap = 0.0
        self.frame_id = 0
        self.write_seq = 0
        self.read_failures = 0
        self.read_failures_total = 0
        self.reopen_attempts = 0
        self.last_error = None
        self.release_error = None
        self._closed = False
        self._write_header(status=0, timestamp=0.0)

    def _write_header(self, status, timestamp):
        struct.pack_into(
            HEADER_FORMAT,
            self.shm.buf,
            0,
            MAGIC,
            self.width,
            self.height,
            self.channels,
            int(status),
            int(self.write_seq),
            int(self.frame_id),
            float(timestamp),
        )

    def start(self):
        try:
            self.cap = self._create_capture()
            if self.cap is None or not self.cap.isOpened():
                raise RuntimeError(f"Could not open physical camera index={self.camera_index}")

            actual_width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            actual_fourcc = _decode_fourcc(self.cap.get(cv2.CAP_PROP_FOURCC))
            measured_fps, measured_frames = _measure_capture_fps(self.cap, self.diagnostic_seconds)
            print(
                "[shared_camera] Camera diagnostic "
                f"requested={self.width}x{self.height}@{self.fps:.0f} fourcc={self.fourcc} "
                f"actual={actual_width:.0f}x{actual_height:.0f}@{actual_fps:.2f} fourcc={actual_fourcc} "
                f"measured_fps={measured_fps:.2f} frames={measured_frames} "
                f"sample_seconds={self.diagnostic_seconds:.2f}"
            )
            self.write_session_file()

            self.running = True
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()
            return self
        except BaseException:
            self.close()
            raise

    def _create_capture(self):
        return _open_with_backends(
            camera_index=self.camera_index,
            width=self.width,
            height=self.height,
            fps=self.fps,
            fourcc=self.fourcc,
            backend_preference=self.backend_preference,
            fallback_to_default=self.fallback_to_default,
            strict_backend=self.strict_backend,
        )

    def _reopen_capture(self):
        if not self._release_capture() or self.stop_event.is_set():
            return False
        self.reopen_attempts += 1
        try:
            # USB reconnect can change enumeration order. Never select a different
            # device silently when an explicit index or required name was given.
            self.camera_index = choose_camera_index(
                self.requested_camera_index, self.camera_name_hint, self.exclude_name_hints,
                self.explicit_index, self.require_name_match,
            )
            self.cap = self._create_capture()
            if self.stop_event.is_set():
                self._release_capture()
                return False
            if self.cap is None or not self.cap.isOpened():
                self._release_capture()
                raise RuntimeError("camera still unavailable")
            self.read_failures = 0
            print(f"[shared_camera] Reopened camera index={self.camera_index} attempt={self.reopen_attempts}")
            return True
        except Exception as exc:
            self.last_error = f"reopen: {exc}"
            print(f"[shared_camera] Reconnect attempt={self.reopen_attempts} failed: {exc}")
            self._release_capture()
            return False

    def _release_capture(self):
        if self.cap is None:
            return True
        try:
            self.cap.release()
        except Exception as exc:
            self.release_error = f"camera release: {exc}"
            print(f"[shared_camera] {self.release_error}")
            return False
        self.cap = None
        self.release_error = None
        return True

    def _mark_unavailable(self):
        with self.lock:
            self.latest_frame = None
            self.latest_timestamp = 0.0
        self.write_seq = (self.write_seq + 2) & ~1
        self._write_header(status=0, timestamp=0.0)

    def _capture_loop(self):
        reconnect_delay = RECONNECT_INITIAL_DELAY
        try:
            while self.running and not self.stop_event.is_set():
                if self.cap is None or self.read_failures >= DEFAULT_READ_FAILURE_REOPEN_THRESHOLD:
                    if self.stop_event.wait(reconnect_delay):
                        break
                    reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX_DELAY)
                    if not self._reopen_capture():
                        continue
                try:
                    ret, frame = self.cap.read()
                    if self.stop_event.is_set():
                        break
                    if not ret or frame is None:
                        raise RuntimeError("camera read returned no frame")
                    if len(frame.shape) != 3 or frame.shape[2] != self.channels:
                        raise RuntimeError(f"unexpected camera shape: {frame.shape}")
                    if frame.shape[1] != self.width or frame.shape[0] != self.height:
                        frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
                    frame = np.ascontiguousarray(frame)
                    frame_bytes = frame.tobytes()
                    if len(frame_bytes) != self.frame_bytes:
                        raise RuntimeError("unexpected camera frame byte length")
                    now = time.monotonic()
                    if self.last_success_at is not None:
                        self.max_frame_gap = max(self.max_frame_gap, now - self.last_success_at)
                    self.last_success_at = now
                    self.write_seq += 1
                    self._write_header(status=1, timestamp=now)
                    self.shm.buf[HEADER_SIZE:HEADER_SIZE + self.frame_bytes] = frame_bytes
                    self.frame_id += 1
                    self.write_seq += 1
                    self._write_header(status=2, timestamp=now)
                    with self.lock:
                        self.latest_frame = frame.copy()
                        self.latest_timestamp = now
                    self.read_failures = 0
                    self.last_error = None
                    reconnect_delay = RECONNECT_INITIAL_DELAY
                except Exception as exc:
                    self.read_failures += 1
                    self.read_failures_total += 1
                    self.last_error = f"read/publish: {exc}"
                    if self.read_failures == 1:
                        print(f"[shared_camera] {self.last_error}")
                    self._mark_unavailable()
                    self.stop_event.wait(0.01)
        finally:
            self.running = False
            try:
                self._mark_unavailable()
            finally:
                self._release_capture()

    def read(self):
        with self.lock:
            if (self.latest_frame is None
                    or not 0 <= time.monotonic() - self.latest_timestamp <= FRAME_MAX_AGE_SECONDS):
                return False, None
            return True, self.latest_frame.copy()

    def export_env(self):
        return {
            ENV_ENABLED: "1",
            ENV_REQUIRED: "1",
            ENV_SHM_NAME: self.shm_name,
            ENV_WIDTH: str(self.width),
            ENV_HEIGHT: str(self.height),
            ENV_CHANNELS: str(self.channels),
            ENV_FPS: str(int(self.fps)),
            ENV_FOURCC: self.fourcc,
            "KIDZDISCO_CAMERA_INDEX": str(self.camera_index),
            "KIDZDISCO_CAMERA_OPENCV_INDEX": str(self.camera_index),
            "KIDZDISCO_CAMERA_WIDTH": str(self.width),
            "KIDZDISCO_CAMERA_HEIGHT": str(self.height),
            "KIDZDISCO_CAMERA_FPS": str(int(self.fps)),
            "KIDZDISCO_CAMERA_FOURCC": self.fourcc,
            "KIDZDISCO_CAMERA_BACKEND": str(self.backend_preference),
            "KIDZDISCO_CAMERA_STRICT_BACKEND": str(self.strict_backend).lower(),
            "KIDZDISCO_CAMERA_ALLOW_FALLBACK": str(self.fallback_to_default).lower(),
        }

    def write_session_file(self):
        payload = {
            "shm_name": self.shm_name,
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "fps": self.fps,
            "fourcc": self.fourcc,
            "pid": os.getpid(),
        }
        temp_path = f"{SESSION_INFO_PATH}.{self.shm_name}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(temp_path, SESSION_INFO_PATH)
        except Exception as exc:
            print(f"[shared_camera] Warning: could not write session file: {exc}")
        finally:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                print(f"[shared_camera] Could not remove session temporary file: {exc}")

    def close(self):
        if getattr(self, "_closed", False):
            return True

        errors = []
        self.running = False
        self.stop_event.set()

        thread = getattr(self, "thread", None)
        if thread and thread is not threading.current_thread():
            try:
                thread.join(timeout=CAPTURE_JOIN_TIMEOUT)
            except Exception as exc:
                errors.append(f"capture thread join: {exc}")
            if thread.is_alive():
                errors.append("capture thread did not stop")

        if thread and thread.is_alive():
            print("[shared_camera] Cleanup incomplete: " + "; ".join(errors))
            return False

        # Only the worker releases an active native read/open. Before start or
        # after it exits, close can retry a failed release without racing it.
        if not self._release_capture():
            errors.append(self.release_error)
        try:
            with open(SESSION_INFO_PATH, "r", encoding="utf-8") as f:
                session = json.load(f)
            if session.get("shm_name") == self.shm_name:
                os.remove(SESSION_INFO_PATH)
        except FileNotFoundError:
            pass
        except Exception as exc:
            errors.append(f"session file removal: {exc}")

        shm = getattr(self, "shm", None)
        if shm is not None:
            shm_released = True
            try:
                shm.close()
            except Exception as exc:
                shm_released = False
                errors.append(f"shared memory close: {exc}")
            try:
                shm.unlink()
            except FileNotFoundError:
                pass
            except Exception as exc:
                shm_released = False
                errors.append(f"shared memory unlink: {exc}")
            if shm_released:
                self.shm = None
        self._closed = self.cap is None and not errors

        if errors:
            print("[shared_camera] Cleanup completed with errors: " + "; ".join(errors))
            return False
        return True


def open_camera_source(
    camera_index,
    width,
    height,
    fps,
    backend_preference="default",
    fallback_to_default=False,
    camera_name_hint=None,
    exclude_name_hints=None,
    explicit_index=None,
    fourcc="MJPG",
    diagnostic_seconds=2.0,
    strict_backend=True,
):
    shared_required = str(os.environ.get(ENV_REQUIRED, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    try:
        shared_cap = SharedMemoryCamera.from_env()
    except Exception as exc:
        if shared_required:
            raise RuntimeError(f"Manager shared camera is required but attach failed: {exc}") from exc
        raise
    if shared_cap is not None:
        print(f"[shared_camera] Attached to shared camera {shared_cap.shm_name}")
        return shared_cap

    if shared_required:
        raise RuntimeError("Manager shared camera is required but connection details are unavailable")

    shared_cap = SharedMemoryCamera.from_session_file()
    if shared_cap is not None:
        print(f"[shared_camera] Attached to manager shared camera {shared_cap.shm_name}")
        return shared_cap

    resolved_index = choose_camera_index(
        camera_index,
        camera_name_hint=camera_name_hint,
        exclude_name_hints=exclude_name_hints,
        explicit_index=explicit_index,
    )

    cap = _open_with_backends(
        camera_index=resolved_index,
        width=width,
        height=height,
        fps=fps,
        fourcc=fourcc,
        backend_preference=backend_preference,
        fallback_to_default=fallback_to_default,
        strict_backend=strict_backend,
    )
    if cap is None:
        print(f"[shared_camera] Error: Could not open camera {resolved_index}")
        return None
    return cap
