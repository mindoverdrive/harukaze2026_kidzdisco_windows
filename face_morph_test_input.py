"""Explicit synthetic inputs for the camera-free face-morph window check.

The capture replaces only the Manager relay's physical input. The detector
replaces only landmark inference; the scene's tracking and renderer stay real.
No input here is evidence of physical-camera or face-recognition accuracy.
"""
import math
import time
from types import SimpleNamespace

import cv2
import numpy as np


LOOP_SECONDS = 42.0
_PHASES = (
    (6.5, 'single_face', 1),
    (8.0, 'two_faces', 2),
    (9.5, 'three_faces', 3),
    (11.0, 'four_faces', 4),
    (20.0, 'five_face_cycles', 5),
    (22.0, 'order_reversal', 5),
    (23.0, 'crossing', 5),
    (26.0, 'separation_recovery', 5),
    (26.5, 'short_occlusion', 5),
    (30.0, 'short_regain', 5),
    (32.0, 'long_exit', 5),
    (LOOP_SECONDS, 'long_regain', 5),
)


def _phase_at(elapsed):
    loop_time = elapsed % LOOP_SECONDS
    for until, name, count in _PHASES:
        if loop_time < until:
            return loop_time, name, count
    raise AssertionError('unreachable phase')


class SyntheticLandmarkDetector:
    """FaceMesh-shaped context manager with a repeatable 42-second program."""

    def __init__(self, *, clock=None, **_face_mesh_options):
        self._clock = clock or time.monotonic
        self._started_at = self._clock()
        self._closed = False

    @property
    def elapsed(self):
        return max(0.0, self._clock() - self._started_at)

    @property
    def phase(self):
        return _phase_at(self.elapsed)[1]

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def close(self):
        self._closed = True

    def process(self, rgb):
        if self._closed:
            raise RuntimeError('synthetic detector is closed')
        if rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) <= 0:
            raise ValueError('expected a nonempty RGB image')
        loop_time, phase, count = _phase_at(self.elapsed)
        if loop_time < 4.1:
            opening = 1.0 if loop_time % 1.4 < .7 else 0.0
        elif loop_time < 11.0:
            # Complete the first solo transformation, then leave every new
            # participant closed so all five start the same cycle together.
            opening = 0.0
        else:
            opening = 1.0 if (loop_time - 11.0) % 1.6 < .8 else 0.0
        faces = []
        for index in range(count):
            if phase == 'short_occlusion' and index == 0:
                continue
            if phase == 'long_exit' and index == 4:
                continue
            x, y = .12 + index * .19, .55
            if phase == 'crossing' and index in (1, 2):
                x = .405 + (index - 1) * .01
            face_opening = opening
            # Enter the short gap while open, then regain while closed. The
            # hidden close must never count toward a transformation.
            if index == 0 and 25.0 <= loop_time < 26.0:
                face_opening = 1.0
            elif index == 0 and 26.5 <= loop_time < 27.5:
                face_opening = 0.0
            points = [SimpleNamespace(x=x + .048 * math.cos(j * math.tau / 468),
                                      y=y + .125 * math.sin(j * math.tau / 468), z=0.0)
                      for j in range(468)]
            points[1] = SimpleNamespace(x=x, y=y, z=0.0)
            points[168] = SimpleNamespace(x=x, y=y - .015, z=0.0)
            points[10] = SimpleNamespace(x=x, y=y - .125, z=0.0)
            points[152] = SimpleNamespace(x=x, y=y + .125, z=0.0)
            # Lip separation and face height share the image's vertical scale,
            # so face_from_landmarks' pixel-aspect correction stays applicable.
            gap = .25 * (.02 + face_opening * .13)
            points[13] = SimpleNamespace(x=x, y=y + .035 - gap / 2, z=0.0)
            points[14] = SimpleNamespace(x=x, y=y + .035 + gap / 2, z=0.0)
            faces.append(SimpleNamespace(landmark=points))
        if phase == 'order_reversal':
            faces.reverse()
        return SimpleNamespace(multi_face_landmarks=faces)


class SyntheticCapture:
    """Paced schematic BGR source implementing the capture API used by relay."""

    def __init__(self, width, height, fps, *, clock=None, sleep=None):
        self.width, self.height, self.fps = int(width), int(height), float(fps)
        if self.width <= 0 or self.height <= 0 or not math.isfinite(self.fps) or self.fps <= 0:
            raise ValueError('invalid synthetic capture dimensions or frame rate')
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._next_frame_at = self._clock()
        self._closed = False
        self._background = None
        self.frame_count = 0

    def isOpened(self):
        return not self._closed

    def release(self):
        self._closed = True
        self._background = None

    def get(self, prop_id):
        return float({cv2.CAP_PROP_FRAME_WIDTH: self.width,
                      cv2.CAP_PROP_FRAME_HEIGHT: self.height,
                      cv2.CAP_PROP_FPS: self.fps}.get(prop_id, 0.0))

    def set(self, prop_id, value):
        if self._closed:
            return False
        if prop_id in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT, cv2.CAP_PROP_FPS):
            if not math.isfinite(value) or value <= 0:
                return False
            if prop_id == cv2.CAP_PROP_FPS:
                self.fps = float(value)
                self._next_frame_at = self._clock()
            else:
                dimension = int(value)
                if dimension < 1:
                    return False
                if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
                    self.width = dimension
                else:
                    self.height = dimension
                self._background = None
        return True

    def read(self):
        if self._closed:
            return False, None
        period = 1.0 / self.fps
        delay = min(period, max(0.0, self._next_frame_at - self._clock()))
        if delay:
            self._sleep(delay)
        self._next_frame_at = self._clock() + period
        if self._background is None:
            background = np.full((self.height, self.width, 3), (30, 22, 16), dtype=np.uint8)
            for x in range(0, self.width, max(1, self.width // 12)):
                cv2.line(background, (x, 0), (x, self.height - 1), (43, 35, 29), 1)
            for y in range(0, self.height, max(1, self.height // 8)):
                cv2.line(background, (0, y), (self.width - 1, y), (43, 35, 29), 1)
            scale = max(.3, min(1.0, self.width / 900))
            cv2.putText(background, 'SYNTHETIC INPUT / NO PHYSICAL CAMERA',
                        (12, max(22, self.height // 12)), cv2.FONT_HERSHEY_SIMPLEX,
                        scale, (160, 210, 235), 1, cv2.LINE_AA)
            self._background = background
        frame = self._background.copy()
        self.frame_count += 1
        cv2.putText(frame, f'FRAME {self.frame_count}', (12, max(16, self.height - 18)),
                    cv2.FONT_HERSHEY_SIMPLEX, .5, (160, 210, 235), 1, cv2.LINE_AA)
        # The production camera adapter mirrors its input once. Author the
        # schematic in display coordinates so its labels survive that mirror.
        return True, cv2.flip(frame, 1)
