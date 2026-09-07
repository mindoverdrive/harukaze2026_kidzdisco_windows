"""Session-local camera display opacity; capture and inference stay untouched."""

import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time


ENV_KEY = "KIDZDISCO_CAMERA_PRESENTATION_PATH"


def validate_opacity(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Camera opacity must be a number between 0 and 1")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Camera opacity must be between 0 and 1")
    return value


class CameraPresentationControl:
    """Manager owns one isolated directory, removed after scene cleanup."""

    def __init__(self):
        self._directory = tempfile.TemporaryDirectory(prefix="kidzdisco-presentation-")
        self.path = Path(self._directory.name) / "camera.json"
        self._lock = threading.Lock()
        self._closed = False
        self._opacity = 1.0
        self.set_opacity(1.0)

    @property
    def opacity(self):
        with self._lock:
            return self._opacity

    def export_env(self):
        return {ENV_KEY: str(self.path)}

    def set_opacity(self, value):
        value = validate_opacity(value)
        with self._lock:
            if self._closed:
                raise RuntimeError("Camera presentation control is closed")
            pending = self.path.with_suffix(".tmp")
            try:
                pending.write_text(json.dumps({"opacity": value}), encoding="utf-8")
                os.replace(pending, self.path)
            finally:
                pending.unlink(missing_ok=True)
            self._opacity = value
        return value

    def close(self):
        with self._lock:
            self._directory.cleanup()
            self._closed = True
        return True


class CameraPresentationReader:
    """Poll small control data at most ten times/second, retaining last valid value."""

    def __init__(self, path=None, poll_interval=0.1):
        self.path = Path(path) if path else None
        self.poll_interval = poll_interval
        self._next_poll = float("-inf")
        self._opacity = 1.0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls):
        return cls(os.environ.get(ENV_KEY))

    def opacity(self):
        if self.path is None:
            return 1.0
        with self._lock:
            now = time.monotonic()
            if now < self._next_poll:
                return self._opacity
            self._next_poll = now + self.poll_interval
            try:
                with self.path.open("r", encoding="utf-8") as stream:
                    raw = stream.read(1025)
                if len(raw) > 1024:
                    return self._opacity
                self._opacity = validate_opacity(json.loads(raw)["opacity"])
            except (OSError, ValueError, TypeError, KeyError):
                pass
            return self._opacity


def apply_camera_opacity(frame, opacity):
    """Dim ONLY the display-stage BGR image over black, without modifying input."""
    opacity = validate_opacity(opacity)
    if opacity == 1.0 or frame is None:
        return frame
    import cv2

    # Stage frames are unsigned BGR. OpenCV scales into a separate uint8 buffer
    # without a large float temporary. Default is an exact zero-cost no-op.
    return cv2.convertScaleAbs(frame, alpha=opacity)
