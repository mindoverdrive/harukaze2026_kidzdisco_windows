"""Standalone hand drawing with the same camera coordinates/feedback as stage scenes."""
import argparse
from contextlib import ExitStack
from dataclasses import dataclass
import json
import math
import socket
import time

import cv2
import mediapipe as mp
import numpy as np

import display_utils
from hand_drawing_effects import EFFECT_NAMES, FadingInk
from hand_drawing_tracking import HandTracks
from hand_drawing_gestures import (
    COLOR_STABLE_SECONDS, FINGER_COLORS_BGR, StableFingerColor, finger_states, valid_hand,
)
from hand_focus_overlay import draw_cv2 as draw_hand_overlay
from scene_control import notify_exit_request, notify_first_frame


WINDOW_NAME = "Hand Drawing App"
DEFAULT_WIDTH, DEFAULT_HEIGHT = 960, 540
MAX_INPUT_GAP_SECONDS = 0.20
MAX_STROKE_JUMP_FRACTION = 0.15
MAX_HANDS = 8
MAX_STROKE_HZ = 30
DEFAULT_MAX_SEGMENTS = 1920
CAMERA_TIMEOUT_SECONDS = 1.0
CAMERA_STALE_SECONDS = 0.25
CAMERA_BRIGHTNESS = 0.42
@dataclass(frozen=True)
class DrawingStroke:
    start: tuple
    end: tuple
    color_bgr: tuple
    effect_id: int
    track_id: int


@dataclass(frozen=True)
class HandInput:
    track_id: int
    effect_id: int
    handedness: str | None
    point: tuple | None
    selected_count: int
    anchor: tuple


@dataclass(frozen=True)
class DrawingFrame:
    hands: tuple
    active_points: tuple
    strokes: tuple
    inputs: tuple


class DrawingInput:
    """Eight independent hands; identity and style survive brief occlusion."""
    def __init__(self, width, height, stable_seconds=COLOR_STABLE_SECONDS, rng=None):
        self.width, self.height = width, height
        self.max_jump = math.hypot(width, height) * MAX_STROKE_JUMP_FRACTION
        self.stable_seconds = stable_seconds
        # Validate timing before acquiring any camera.
        StableFingerColor(stable_seconds)
        self.tracker = HandTracks(max_hands=MAX_HANDS, rng=rng)
        self.colors = {}
        self.previous_tips = {}
        self.last_stroke_times = {}
        self.last_update = None

    def reset(self):
        """Camera gaps break strokes, while short-lived identity reservations remain."""
        self.previous_tips.clear()
        self.last_stroke_times.clear()
        for color in self.colors.values():
            color.reset_candidate()
        self.tracker.break_continuity()
        self.last_update = None

    def update(self, results, layout, now):
        gap = None if self.last_update is None else now - self.last_update
        if gap is None or gap <= 0 or gap > MAX_INPUT_GAP_SECONDS:
            self.reset()
        self.last_update = now
        tracked = self.tracker.update(results, now)
        retained = set(self.tracker.tracks)
        self.colors = {key: color for key, color in self.colors.items() if key in retained}
        self.last_stroke_times = {key: value for key, value in self.last_stroke_times.items() if key in retained}
        visible = {item.track_id for item in tracked}
        for key in tuple(self.previous_tips):
            if key not in visible:
                self.previous_tips.pop(key, None)
        for key, color in self.colors.items():
            if key not in visible:
                color.reset_candidate()

        active, strokes, inputs = [], [], []
        for item in tracked:
            key = item.track_id
            color = self.colors.setdefault(key, StableFingerColor(self.stable_seconds))
            if not item.continuous:
                self.previous_tips.pop(key, None)
                color.reset_candidate()
            states = finger_states(item.hand, item.handedness)
            tip = item.hand.landmark[8]
            point = display_utils.normalized_to_stage(tip.x, tip.y, layout)
            previous = self.previous_tips.get(key)
            if previous is not None and math.dist(point, previous) > self.max_jump:
                self.previous_tips.pop(key, None)
                previous = None
                color.reset_candidate()
            color.update(sum(states), now)
            drawing_point = None
            if states[1] and 0 <= tip.x <= 1 and 0 <= tip.y <= 1:
                drawing_point = point
                active.append(point)
                # Keep the last emitted point while sampling: no gaps in the
                # polyline, and eight 60-FPS hands cannot evict ink before fade.
                if previous is not None and now - self.last_stroke_times[key] + 1e-9 >= 1 / MAX_STROKE_HZ:
                    strokes.append(DrawingStroke(previous, point,
                                   FINGER_COLORS_BGR[color.selected_count], item.effect_id, key))
                    self.previous_tips[key] = point
                    self.last_stroke_times[key] = now
                elif previous is None:
                    self.previous_tips[key] = point
                    self.last_stroke_times[key] = now
            else:
                self.previous_tips.pop(key, None)
            wrist = item.hand.landmark[0]
            inputs.append(HandInput(key, item.effect_id, item.handedness, drawing_point,
                          color.selected_count, display_utils.normalized_to_stage(wrist.x, wrist.y, layout)))
        return DrawingFrame(tuple(item.hand for item in tracked), tuple(active),
                            tuple(strokes), tuple(inputs))


def setup_window(width, height, fullscreen=False, window_name=WINDOW_NAME):
    """Standalone preview stays on the primary monitor, ignoring stage placement."""
    x, y, view_w, view_h = 40, 40, width, height
    try:
        from screeninfo import get_monitors
        monitors = get_monitors()
        monitor = next((m for m in monitors if getattr(m, "is_primary", False)), monitors[0])
        scale = min(1.0, monitor.width * .85 / width, monitor.height * .80 / height)
        view_w, view_h = max(1, round(width * scale)), max(1, round(height * scale))
        x, y = monitor.x + (monitor.width - view_w) // 2, monitor.y + (monitor.height - view_h) // 2
    except Exception:
        pass
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(window_name, view_w, view_h)
    cv2.moveWindow(window_name, x, y)
    if fullscreen:
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)


def render_frame(stage, ink, feedback, layout, now):
    image = cv2.convertScaleAbs(stage, alpha=CAMERA_BRIGHTNESS)
    cv2.add(image, ink.render(now), dst=image)
    # Same muted bones/palm frames and active-point rings as Mandala/Grid/Otedama.
    draw_hand_overlay(image, feedback.hands, layout=layout, focus=(), active_points=feedback.active_points)
    for count, color in FINGER_COLORS_BGR.items():
        center = (24 + (count - 1) * 48, 26)
        cv2.circle(image, center, 13, color, -1, cv2.LINE_AA)
        cv2.putText(image, str(count), (center[0] - 5, 31), cv2.FONT_HERSHEY_SIMPLEX,
                    .45, (15, 15, 15), 1, cv2.LINE_AA)
    for hand in feedback.inputs:
        x, y = hand.anchor
        label = f"H{hand.track_id} {(hand.handedness or '?')[0]} {hand.selected_count}: {EFFECT_NAMES[hand.effect_id]}"
        origin = (max(5, min(image.shape[1] - 175, x - 45)),
                  max(55, min(image.shape[0] - 35, y + 18)))
        cv2.putText(image, label, origin, cv2.FONT_HERSHEY_SIMPLEX, .36, (8, 10, 12), 3, cv2.LINE_AA)
        cv2.putText(image, label, origin, cv2.FONT_HERSHEY_SIMPLEX, .36,
                    FINGER_COLORS_BGR[hand.selected_count], 1, cv2.LINE_AA)
    cv2.putText(image, "BOTH INDEX FINGERS: DRAW   EACH HAND 1-5: COLOR   UP TO 8 HANDS   ESC/Q: EXIT",
                (14, image.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX, .42,
                (210, 220, 225), 1, cv2.LINE_AA)
    return image


def close_window(window_name=WINDOW_NAME):
    try:
        cv2.destroyWindow(window_name)
    except cv2.error:
        pass


def run_app(*, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, stable_seconds=COLOR_STABLE_SECONDS,
            hold_seconds=3.5, fade_seconds=3.0, max_segments=DEFAULT_MAX_SEGMENTS, fullscreen=False,
            controller=None, renderer=None, window_name=WINDOW_NAME):
    """Shared camera/window lifecycle for drawing and the separate shape scene."""
    ink = FadingInk(width, height, hold_seconds, fade_seconds, max_segments)
    controller = controller if controller is not None else DrawingInput(width, height, stable_seconds)
    renderer = renderer or render_frame
    with ExitStack() as resources:
        hands = mp.solutions.hands.Hands(model_complexity=1, max_num_hands=MAX_HANDS,
                                        min_detection_confidence=.7, min_tracking_confidence=.7)
        resources.callback(hands.close)
        cap = display_utils.open_camera()
        if cap is not None:
            resources.callback(cap.release)
        if cap is None or not cap.isOpened():
            raise RuntimeError("Camera unavailable. Check the shared camera or Windows DirectShow settings.")
        resources.callback(close_window, window_name)
        setup_window(width, height, fullscreen, window_name)
        stage = np.zeros((height, width, 3), np.uint8)
        feedback = DrawingFrame((), (), (), ())
        layout = None
        last_id, last_fresh_at, failure_since = None, None, None
        while True:
            # Poll on failed reads too; a missing camera cannot trap the Q/Esc keys.
            key = cv2.waitKey(10) & 0xFF
            if key in (ord('q'), 27):
                notify_exit_request("key_q" if key == ord('q') else "key_escape")
                break
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                notify_exit_request("window_close")
                break
            success, frame = cap.read()
            now = time.monotonic()
            frame_id = getattr(cap, "last_read_frame_id", None)
            repeated = type(frame_id) is int and frame_id == last_id
            valid = bool(success and frame is not None)
            fresh = valid and not repeated
            if fresh:
                last_id, last_fresh_at, failure_since = frame_id, now, None
                camera, stage, layout = display_utils.prepare_camera_frame(frame, width, height)
                rgb = cv2.cvtColor(camera, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                feedback = controller.update(hands.process(rgb), layout, now)
                for stroke in feedback.strokes:
                    ink.add_segment(stroke.start, stroke.end, stroke.color_bgr, now,
                                    effect_id=stroke.effect_id, track_id=stroke.track_id)
            elif not valid or last_fresh_at is None or now - last_fresh_at >= CAMERA_STALE_SECONDS:
                controller.reset()
                feedback = controller.update(None, layout, now)
                for stroke in feedback.strokes:
                    ink.add_segment(stroke.start, stroke.end, stroke.color_bgr, now,
                                    effect_id=stroke.effect_id, track_id=stroke.track_id)
                stage.fill(0)
                if failure_since is None:
                    failure_since = now
                elif now - failure_since >= CAMERA_TIMEOUT_SECONDS:
                    notify_exit_request("camera_read_failed_timeout")
                    raise RuntimeError("Camera stopped providing fresh frames for one second")
            cv2.imshow(window_name, renderer(stage, ink, feedback, layout, now))
            notify_first_frame(cap, frame_processed=fresh)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--fullscreen", action="store_true", help="Use the primary monitor fullscreen")
    parser.add_argument("--hold-seconds", type=float, default=3.5)
    parser.add_argument("--fade-seconds", type=float, default=3.0)
    parser.add_argument("--max-segments", type=int, default=DEFAULT_MAX_SEGMENTS)
    parser.add_argument("--color-stable-ms", type=float, default=180)
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    if not (320 <= args.width <= 3840 and 240 <= args.height <= 2160):
        parser.error("Preview size must be 320..3840 by 240..2160")
    if args.wait and args.port > 0:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("127.0.0.1", args.port))
            while True:
                data, _ = sock.recvfrom(1024)
                try:
                    if json.loads(data.decode("utf-8")).get("cmd") == "START":
                        break
                except (ValueError, UnicodeError):
                    continue
    run_app(width=args.width, height=args.height, fullscreen=args.fullscreen,
            hold_seconds=args.hold_seconds, fade_seconds=args.fade_seconds,
            max_segments=args.max_segments, stable_seconds=args.color_stable_ms / 1000)


if __name__ == "__main__":
    main()
