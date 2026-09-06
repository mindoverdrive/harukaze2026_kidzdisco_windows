"""One worker owns camera/Hands; the render thread only reads immutable snapshots."""

from contextlib import ExitStack
from dataclasses import dataclass
import os
import threading
import time


@dataclass(frozen=True)
class CameraSnapshot:
    """Stage-sized RGB pixels and tips, stamped at acquisition in monotonic seconds."""

    timestamp: float
    rgb_bytes: bytes
    size: tuple[int, int]
    tips: tuple[tuple[int, int], ...]
    last_read_frame_id: int
    shm_name: str | None


def _load_native():
    # open_camera otherwise permits a standalone physical-camera fallback.
    if os.environ.get("HARUKAZE_SHARED_CAMERA_REQUIRED", "").strip().lower() not in {
        "1", "true", "yes", "on"
    }:
        raise RuntimeError("Spheres camera requires the Manager shared camera")
    import cv2
    import display_utils
    import mediapipe as mp

    return display_utils, cv2, mp.solutions.hands.Hands


class SpheresCameraFeed:
    def __init__(self, width, height, *, _native_loader=None,
                 _clock=time.monotonic, _close_timeout=2.0):
        self._size = (int(width), int(height))
        self._native_loader = _native_loader or _load_native
        self._clock = _clock
        self._close_timeout = _close_timeout
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._snapshot = None
        self._error = None
        self._pending_error = None
        self._closed = False

    def start(self):
        """Start acquisition without waiting for native initialization or a frame."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Spheres camera feed is closed")
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, name="SpheresCameraFeed", daemon=True)
                try:
                    self._thread.start()
                except BaseException:
                    if not self._thread.is_alive():
                        self._thread = None
                    self._closed = True
                    self._stop.set()
                    raise
        return self

    def latest(self):
        """Return the newest result under 0.5 seconds old, without waiting for work."""
        with self._lock:
            error = self._pending_error if self._pending_error is not None else self._error
            self._pending_error = None
            snapshot = self._snapshot
        if error is not None:
            raise RuntimeError(f"Spheres camera worker failed: {error}") from error
        if snapshot is not None and not 0 <= self._clock() - snapshot.timestamp < 0.5:
            return None
        return snapshot

    def close(self):
        """Wait at most two seconds for owned cleanup; report any unreported failure."""
        self._stop.set()
        with self._lock:
            self._closed = True
            self._snapshot = None
            worker = self._thread
        if worker is not None:
            worker.join(self._close_timeout)
            if worker.is_alive():
                raise RuntimeError(
                    "Spheres camera worker did not stop; native resources remain "
                    "owned by its daemon thread until the call returns or the process exits")
        # Do not replace an exception already delivered by latest() during unwinding.
        # A failure that occurs later in worker cleanup must still reach the caller.
        with self._lock:
            error = self._pending_error
            self._pending_error = None
        if error is not None:
            raise RuntimeError(f"Spheres camera worker failed: {error}") from error

    def _remember_error(self, error):
        with self._lock:
            self._snapshot = None
            if self._error is None:
                self._error = error
            if self._pending_error is None:
                self._pending_error = error
            else:
                self._pending_error.add_note(f"Additional camera cleanup failure: {error}")

    def _run(self):
        try:
            with ExitStack() as resources:
                try:
                    display, cv2, make_hands = self._native_loader()
                    if self._stop.is_set():
                        return
                    camera = display.open_camera()
                    if camera is None:
                        raise RuntimeError("Manager shared camera could not be opened")
                    resources.callback(camera.release)
                    if not camera.isOpened():
                        raise RuntimeError("Manager shared camera is not open")
                    if self._stop.is_set():
                        return
                    hands = make_hands(
                        model_complexity=1, max_num_hands=6,
                        min_detection_confidence=0.7, min_tracking_confidence=0.5)
                    resources.callback(hands.close)
                    self._read_frames(camera, hands, display, cv2)
                except BaseException as error:
                    self._remember_error(error)
        except BaseException as error:
            self._remember_error(error)

    def _read_frames(self, camera, hands, display, cv2):
        previous_frame_id = None
        while not self._stop.is_set():
            ok, frame = camera.read()
            if self._stop.is_set():
                return
            if not ok or frame is None:
                with self._lock:
                    self._snapshot = None
                self._stop.wait(0.005)
                continue
            frame_id = int(getattr(camera, "last_read_frame_id", 0) or 0)
            if frame_id > 0 and frame_id == previous_frame_id:
                self._stop.wait(0.005)
                continue
            timestamp = self._clock()
            camera_frame, stage_frame, layout = display.prepare_camera_frame(frame, *self._size)
            if self._stop.is_set():
                return
            camera_rgb = cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB)
            if self._stop.is_set():
                return
            result = hands.process(camera_rgb)
            if self._stop.is_set():
                return
            tips = tuple(
                display.normalized_to_stage(hand.landmark[8].x, hand.landmark[8].y, layout)
                for hand in (result.multi_hand_landmarks or ()))
            snapshot = CameraSnapshot(
                timestamp=timestamp,
                rgb_bytes=cv2.cvtColor(stage_frame, cv2.COLOR_BGR2RGB).tobytes(),
                size=self._size,
                tips=tips,
                last_read_frame_id=frame_id,
                shm_name=getattr(camera, "shm_name", None))
            with self._lock:
                if not self._stop.is_set():
                    self._snapshot = snapshot
            previous_frame_id = frame_id
