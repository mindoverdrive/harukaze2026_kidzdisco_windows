import os
import struct
import threading
import time
from multiprocessing import shared_memory

import cv2
import numpy as np


HEADER_FORMAT = "<8sIIIIQQd"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAGIC = b"HARUCAM1"

ENV_ENABLED = "HARUKAZE_SHARED_CAMERA"
ENV_SHM_NAME = "HARUKAZE_CAMERA_SHM"
ENV_WIDTH = "HARUKAZE_CAMERA_WIDTH"
ENV_HEIGHT = "HARUKAZE_CAMERA_HEIGHT"
ENV_CHANNELS = "HARUKAZE_CAMERA_CHANNELS"
ENV_FPS = "HARUKAZE_CAMERA_FPS"
ENV_FOURCC = "HARUKAZE_CAMERA_FOURCC"


def enumerate_camera_devices():
    try:
        from pygrabber.dshow_graph import FilterGraph

        return list(FilterGraph().get_input_devices())
    except Exception:
        return []


def resolve_camera_index(camera_index, camera_name_hint=None, exclude_name_hints=None):
    devices = enumerate_camera_devices()
    if not devices:
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
    return int(camera_index)


def choose_camera_index(camera_index, camera_name_hint=None, exclude_name_hints=None, explicit_index=None):
    if explicit_index is not None:
        explicit_index = int(explicit_index)
        print(f"[shared_camera] Using explicit OpenCV camera index={explicit_index}")
        return explicit_index
    return resolve_camera_index(camera_index, camera_name_hint, exclude_name_hints)


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

    for backend in _backend_order(backend_preference, strict_backend=strict_backend):
        try:
            if backend is None:
                backend_label = "default"
                print(f"[shared_camera] Trying camera index={camera_index} backend={backend_label}")
                cap = cv2.VideoCapture(camera_index)
            else:
                backend_label = str(backend)
                print(f"[shared_camera] Trying camera index={camera_index} backend={backend_label}")
                cap = cv2.VideoCapture(camera_index, backend)
        except Exception as exc:
            print(f"[shared_camera] Open failed index={camera_index} backend={backend}: {exc}")
            continue
        if cap.isOpened():
            _setup_props(cap)
            actual_fourcc = _decode_fourcc(cap.get(cv2.CAP_PROP_FOURCC))
            print(
                f"[shared_camera] Opened physical camera index={camera_index} "
                f"backend={backend_label} fourcc={actual_fourcc}"
            )
            return cap
        cap.release()

    if fallback_to_default:
        for idx in [0, 1, 2]:
            if idx == camera_index:
                continue
            for backend in _backend_order(backend_preference, strict_backend=strict_backend):
                try:
                    if backend is None:
                        backend_label = "default"
                        print(f"[shared_camera] Trying fallback camera index={idx} backend={backend_label}")
                        cap = cv2.VideoCapture(idx)
                    else:
                        backend_label = str(backend)
                        print(f"[shared_camera] Trying fallback camera index={idx} backend={backend_label}")
                        cap = cv2.VideoCapture(idx, backend)
                except Exception as exc:
                    print(f"[shared_camera] Fallback open failed index={idx} backend={backend}: {exc}")
                    continue
                if cap.isOpened():
                    _setup_props(cap)
                    actual_fourcc = _decode_fourcc(cap.get(cv2.CAP_PROP_FOURCC))
                    print(
                        f"[shared_camera] Warning: camera_index={camera_index} failed, "
                        f"opened fallback camera={idx} backend={backend_label} fourcc={actual_fourcc}"
                    )
                    return cap
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
        self.shm = shared_memory.SharedMemory(name=shm_name)

    def isOpened(self):
        return not self.closed

    def release(self):
        if self.closed:
            return
        self.closed = True
        self.shm.close()

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
            magic, width, height, channels, _status, write_seq1, _frame_id1, _timestamp1 = header1
            if magic != MAGIC or write_seq1 % 2 == 1:
                time.sleep(0.001)
                continue

            frame_bytes = width * height * channels
            frame_buffer = bytes(self.shm.buf[HEADER_SIZE:HEADER_SIZE + frame_bytes])

            header2 = struct.unpack_from(HEADER_FORMAT, self.shm.buf, 0)
            write_seq2 = header2[5]
            if write_seq1 == write_seq2 and write_seq2 % 2 == 0:
                frame = np.frombuffer(frame_buffer, dtype=np.uint8).reshape((height, width, channels))
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
    ):
        self.requested_camera_index = int(camera_index)
        self.camera_index = choose_camera_index(
            camera_index,
            camera_name_hint=camera_name_hint,
            exclude_name_hints=exclude_name_hints,
            explicit_index=explicit_index,
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
        self.frame_bytes = self.width * self.height * self.channels
        self.shm_name = f"harukaze_cam_{os.getpid()}"
        self.shm = shared_memory.SharedMemory(create=True, size=HEADER_SIZE + self.frame_bytes, name=self.shm_name)
        self.cap = None
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.latest_frame = None
        self.frame_id = 0
        self.write_seq = 0
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
        self.cap = _open_with_backends(
            camera_index=self.camera_index,
            width=self.width,
            height=self.height,
            fps=self.fps,
            fourcc=self.fourcc,
            backend_preference=self.backend_preference,
            fallback_to_default=self.fallback_to_default,
            strict_backend=self.strict_backend,
        )
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

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        return self

    def _capture_loop(self):
        target_sleep = 1.0 / max(self.fps, 1.0)
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height))

            with self.lock:
                self.latest_frame = frame.copy()

            now = time.time()
            self.write_seq += 1
            self._write_header(status=1, timestamp=now)
            self.shm.buf[HEADER_SIZE:HEADER_SIZE + self.frame_bytes] = frame.tobytes()
            self.frame_id += 1
            self.write_seq += 1
            self._write_header(status=2, timestamp=now)
            time.sleep(target_sleep)

    def read(self):
        with self.lock:
            if self.latest_frame is None:
                return False, None
            return True, self.latest_frame.copy()

    def export_env(self):
        return {
            ENV_ENABLED: "1",
            ENV_SHM_NAME: self.shm_name,
            ENV_WIDTH: str(self.width),
            ENV_HEIGHT: str(self.height),
            ENV_CHANNELS: str(self.channels),
            ENV_FPS: str(int(self.fps)),
            ENV_FOURCC: self.fourcc,
        }

    def close(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap is not None:
            self.cap.release()
        self.shm.close()
        try:
            self.shm.unlink()
        except FileNotFoundError:
            pass


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
    shared_cap = SharedMemoryCamera.from_env()
    if shared_cap is not None:
        print(f"[shared_camera] Attached to shared camera {shared_cap.shm_name}")
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
        diagnostic_seconds=diagnostic_seconds,
        strict_backend=strict_backend,
        backend_preference=backend_preference,
        fallback_to_default=fallback_to_default,
    )
    if cap is None:
        print(f"[shared_camera] Error: Could not open camera {resolved_index}")
        return None
    return cap
