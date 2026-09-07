"""Transparent navigation and an acknowledged curtain, in one owned process.

Native libraries are imported only by the worker/main entrypoint so gesture and
presentation state can be tested without opening a camera or a window.
"""

import argparse
from contextlib import ExitStack
import math
import os
from pathlib import Path
import signal
import socket
import threading
import time

from scene_control import JsonChannel, SceneControlError


TRANSPARENT_COLOR = (255, 0, 128)
COVER_COLOR = (16, 23, 42)
DETECTION_MAX_AGE = 0.25
LWA_COLORKEY = 0x00000001
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040


def navigation_regions(width, height):
    margin = max(1, int(width * 0.035))
    top = max(1, int(height * 0.035))
    button_width, button_height = max(1, int(width * 0.20)), max(1, int(height * 0.15))
    return {"back": (margin, top, button_width, button_height),
            "next": (width - margin - button_width, top, button_width, button_height)}


class NavigationHold:
    def __init__(self, regions, hold_seconds=1.0, max_age=DETECTION_MAX_AGE, max_jump=100.0):
        self.regions = dict(regions)
        self.hold_seconds = float(hold_seconds)
        self.max_age = float(max_age)
        self.max_jump = float(max_jump)
        if self.hold_seconds <= 0 or self.max_age <= 0 or self.max_jump <= 0:
            raise ValueError("Navigation timing and motion limits must be positive")
        self.latched = False
        self.active = None
        self.point = None
        self.progress = 0.0
        self._started = None
        self._last_observed = None

    def _cancel(self):
        self.active = self.point = self._started = None
        self._last_observed = None
        self.progress = 0.0

    def update(self, points, observed_at, now, *, enabled=True):
        if (observed_at is None or not math.isfinite(observed_at)
                or not 0 <= now - observed_at <= self.max_age):
            self._cancel()
            return None
        if (self._last_observed is not None
                and not 0 <= observed_at - self._last_observed <= self.max_age):
            self._cancel()
        points = tuple(point for point in points
                       if len(point) == 2 and all(math.isfinite(value) for value in point))
        hits = {}
        for action, (x, y, width, height) in self.regions.items():
            inside = [point for point in points
                      if x <= point[0] < x + width and y <= point[1] < y + height]
            if inside:
                hits[action] = inside
        # Tracking loss is not proof of leaving both buttons. Require a fresh,
        # visible fingertip outside them before rearming after a fired action.
        if self.latched and points and not hits:
            self.latched = False
        if not enabled or self.latched or len(hits) != 1:
            self._cancel()
            return None
        action = next(iter(hits))
        candidates = hits[action]
        point = min(candidates, key=lambda value: math.dist(value, self.point)) if self.point else candidates[0]
        if (action != self.active or self.point is None
                or math.dist(point, self.point) > self.max_jump
                or observed_at < self._started):
            self.active = action
            self._started = observed_at
        self.point = point
        self._last_observed = observed_at
        # Repainting one old detector result must never advance a hold.
        self.progress = min(1.0, max(0.0, (observed_at - self._started) / self.hold_seconds))
        if self.progress >= 1.0:
            self.latched = True
            return action
        return None


class Curtain:
    DURATION = 0.35

    def __init__(self, cover_duration=None, reveal_duration=None):
        self.state = "idle"
        self.level = 0.0
        self.cycle = 0
        self._started = 0.0
        self.cover_duration = self.DURATION if cover_duration is None else cover_duration
        self.reveal_duration = self.DURATION if reveal_duration is None else reveal_duration

    def command(self, command, cycle, now):
        if type(cycle) is not int or cycle < 0:
            raise SceneControlError("Invalid curtain cycle")
        if command == "COVER" and self.state == "idle" and cycle > self.cycle:
            self.state, self.cycle, self._started = "covering", cycle, now
        elif command == "REVEAL" and self.state == "covered" and cycle == self.cycle:
            self.state, self._started = "revealing", now
        elif command == "FAIL_CLOSED":
            self.cycle = max(cycle, self.cycle)
            self.fail()
        else:
            raise SceneControlError(f"Unexpected {command} while curtain is {self.state}")

    def fail(self):
        self.state, self.level = "failed", 1.0

    def advance(self, now):
        duration = self.reveal_duration if self.state == "revealing" else self.cover_duration
        fraction = min(1.0, max(0.0, (now - self._started) / duration))
        fraction = fraction * fraction * (3.0 - 2.0 * fraction)
        if self.state == "covering":
            self.level = fraction
        elif self.state == "revealing":
            self.level = 1.0 - fraction
        return self.level

    def presented(self):
        if self.state == "covering" and self.level >= 1.0:
            self.state = "covered"
            return "COVERED"
        if self.state == "revealing" and self.level <= 0.0:
            self.state = "idle"
            return "REVEALED"
        return None


def present_frame(screen, pygame, curtain, now, draw_navigation=None, draw_camera=None, draw_logo=None, opacity=None, draw_background=None, draw_breakup=None):
    level = curtain.advance(now)
    screen.fill(TRANSPARENT_COLOR)
    if draw_navigation is not None and curtain.state == "idle":
        draw_navigation()
    if opacity is not None and curtain.state != "idle":
        # During breakup only the moving fragments occlude the prepared scene.
        # Keep them solid; uncovered gaps use the transparent color key.
        opacity(255 if draw_breakup is not None and curtain.state == "revealing" and level > 0
                else round(255 * level))
    if level >= 1.0 or (opacity is not None and curtain.state != "idle"):
        screen.fill(COVER_COLOR)
        if draw_background is not None:
            draw_background(screen.get_rect())
        if draw_camera is not None:
            draw_camera(screen.get_rect())
        if draw_logo is not None:
            draw_logo(screen.get_rect())
    elif level > 0:
        width, height = screen.get_size()
        curtain_width = math.ceil(width * level / 2)
        pygame.draw.rect(screen, COVER_COLOR, (0, 0, curtain_width, height))
        pygame.draw.rect(screen, COVER_COLOR, (width - curtain_width, 0, curtain_width, height))
        if draw_background is not None:
            draw_background((0, 0, curtain_width, height))
            draw_background((width - curtain_width, 0, curtain_width, height))
        if draw_camera is not None:
            draw_camera((0, 0, curtain_width, height))
            draw_camera((width - curtain_width, 0, curtain_width, height))
        if draw_logo is not None:
            draw_logo((0, 0, curtain_width, height))
            draw_logo((width - curtain_width, 0, curtain_width, height))
    if draw_breakup is not None and curtain.state == "revealing":
        if draw_breakup() is False and opacity is not None:
            # A missing optional particle asset/renderer falls back to the same
            # timed fade, only after the next scene has been safely prepared.
            opacity(round(255 * level))
    pygame.display.flip()
    if opacity is not None and curtain.state == "idle":
        # Replace the invisible full-cover buffer with transparent navigation
        # before restoring opacity, avoiding one opaque flash after reveal.
        opacity(255)
    if opacity is not None and ((curtain.state == "covering" and level >= 1.0)
                                or (curtain.state == "revealing" and level <= 0.0)):
        opacity.sync()
    # No ACK exists if rendering or the actual presentation raised an exception.
    return curtain.presented()


class CurtainCamera:
    """A fresh shared-camera image fades in only after full occlusion."""

    def __init__(self):
        self.surface = None
        self.stamp = None
        self.opacity = 0.0
        self.last_tick = None

    def update(self, pygame, snapshot, state, now):
        dt = 0.0 if self.last_tick is None else max(0.0, min(0.1, now - self.last_tick))
        self.last_tick = now
        stamp, frame = snapshot
        fresh = stamp is not None and frame is not None and 0 <= now - stamp <= DETECTION_MAX_AGE
        if state not in {"covered", "revealing"} or not fresh:
            self.opacity = 0.0
            self.surface = self.stamp = None
            return
        target = 96.0 if state == "covered" else 0.0
        rate = 96.0 / (0.45 if target else 1.6)
        if self.opacity < target:
            self.opacity = min(target, self.opacity + rate * dt)
        else:
            self.opacity = max(target, self.opacity - rate * dt)
        if self.opacity > 0 and stamp != self.stamp:
            # Worker owns publication; this fresh array is never mutated afterwards.
            self.surface = pygame.surfarray.make_surface(frame[:, :, ::-1].swapaxes(0, 1))
            self.stamp = stamp
        if self.surface is not None:
            self.surface.set_alpha(round(self.opacity))

    def draw(self, screen, rect):
        if self.surface is None or self.opacity <= 0:
            return
        previous_clip = screen.get_clip()
        screen.set_clip(rect)
        try:
            screen.blit(self.surface, (0, 0))
        finally:
            screen.set_clip(previous_clip)


class DetectionWorker:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._snapshot = (None, ())
        self._camera_snapshot = (None, None)
        self._error = None
        self._thread = threading.Thread(target=self._run, name="overlay-hands", daemon=True)

    def start(self):
        self._thread.start()

    def snapshot(self):
        with self._lock:
            return self._snapshot, self._error

    def camera_snapshot(self):
        with self._lock:
            return self._camera_snapshot

    def _publish(self, observed_at, points=()):
        with self._lock:
            self._snapshot = observed_at, tuple(points)

    def _run(self):
        try:
            import cv2
            import mediapipe as mp
            import display_utils
            from shared_camera import SharedMemoryCamera

            with ExitStack() as resources:
                # Never open a physical camera or search for another Manager session.
                cap = SharedMemoryCamera.from_env()
                if cap is None:
                    raise RuntimeError("Overlay requires the Manager shared camera")
                resources.callback(cap.release)
                hands = mp.solutions.hands.Hands(
                    model_complexity=0, max_num_hands=2,
                    min_detection_confidence=0.7, min_tracking_confidence=0.5,
                )
                resources.callback(hands.close)
                previous_frame = None
                while not self._stop.is_set():
                    ok, frame = cap.read()
                    observed_at = time.monotonic()
                    if not ok or frame is None:
                        self._publish(None)
                        with self._lock:
                            self._camera_snapshot = (None, None)
                        self._stop.wait(0.01)
                        continue
                    frame_id = cap.last_read_frame_id
                    if frame_id == previous_frame:
                        self._stop.wait(0.005)
                        continue
                    previous_frame = frame_id
                    camera_frame, _stage_frame, layout = display_utils.prepare_camera_frame(
                        frame, self.width, self.height
                    )
                    with self._lock:
                        self._camera_snapshot = (observed_at, _stage_frame)
                    result = hands.process(cv2.cvtColor(camera_frame, cv2.COLOR_BGR2RGB))
                    points = []
                    for hand in (result.multi_hand_landmarks or ())[:2]:
                        tip = hand.landmark[8]
                        points.append(display_utils.normalized_to_stage(tip.x, tip.y, layout))
                    self._publish(observed_at, points)
                    self._stop.wait(max(0.0, 1 / 30 - (time.monotonic() - observed_at)))
        except BaseException as exc:
            with self._lock:
                self._snapshot = (None, ())
                self._camera_snapshot = (None, None)
                self._error = f"{type(exc).__name__}: {exc}"

    def close(self):
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            raise RuntimeError("Overlay detector did not stop within two seconds")


class OverlayOpacity:
    """Fade the entire layered window; ACK only after DWM presents the endpoint."""

    def __init__(self, pygame):
        import ctypes
        from ctypes import wintypes
        self.hwnd = pygame.display.get_wm_info()["window"]
        self._set = ctypes.WinDLL("user32", use_last_error=True).SetLayeredWindowAttributes
        self._set.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.BYTE, wintypes.DWORD]
        self._set.restype = wintypes.BOOL
        self._flush = ctypes.WinDLL("dwmapi").DwmFlush
        self._flush.argtypes, self._flush.restype = [], ctypes.c_long
        self._last = None

    def __call__(self, alpha):
        import ctypes
        alpha = max(0, min(255, int(alpha)))
        if alpha == self._last:
            return
        r, g, b = TRANSPARENT_COLOR
        if not self._set(self.hwnd, r | (g << 8) | (b << 16), alpha, LWA_COLORKEY | 2):
            raise ctypes.WinError(ctypes.get_last_error())
        self._last = alpha

    def sync(self):
        result = self._flush()
        if result != 0:
            raise OSError(f"DwmFlush failed: {result}")


def configure_overlay_window(pygame, geometry):
    if os.name != "nt":
        raise RuntimeError("The transparent overlay requires Windows")
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = pygame.display.get_wm_info()["window"]
    get_style = user32.GetWindowLongPtrW
    set_style = user32.SetWindowLongPtrW
    get_style.argtypes, get_style.restype = [wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t
    set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.BYTE, wintypes.DWORD]
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    style = get_style(hwnd, -20)
    ctypes.set_last_error(0)
    set_style(hwnd, -20, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    if ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    red, green, blue = TRANSPARENT_COLOR
    if not user32.SetLayeredWindowAttributes(hwnd, red | (green << 8) | (blue << 16), 0, LWA_COLORKEY):
        raise ctypes.WinError(ctypes.get_last_error())
    # TOPMOST + SHOWWINDOW + NOACTIVATE + FRAMECHANGED; never take scene keyboard focus.
    if not user32.SetWindowPos(hwnd, -1, *geometry, SWP_SHOWWINDOW | SWP_NOACTIVATE | SWP_FRAMECHANGED):
        raise ctypes.WinError(ctypes.get_last_error())


class NavigationStyle:
    """Cache open glass edges, their rear plane and the foreground typography."""

    COLORS = {"back": (224, 159, 255), "next": (105, 243, 217)}

    def __init__(self, pygame, regions):
        self.cards = {}
        self.depth_layers = {}
        self.edge_lights = {}
        self.visual_rects = {}
        self.progress_tracks = {}
        font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        height = next(iter(regions.values()))[3]
        self.scale = height / 162
        self.shadow_margin = max(3, round(7 * self.scale))
        depth_x, depth_y = max(3, round(8 * self.scale)), max(4, round(8 * self.scale))
        title_size = max(20, round(54 * self.scale))
        detail_size = max(12, round(21 * self.scale))
        title = pygame.font.Font(str(font_dir / "bahnschrift.ttf"), title_size)
        detail = pygame.font.Font(str(font_dir / "YuGothB.ttc"), detail_size)

        def label_surface(font, text, color):
            glyph = font.render(text, True, color)
            # Back only the glyph pixels, so smooth text edges blend with their
            # own shadow instead of the Win32 window's magenta transparent color.
            backed = pygame.Surface(glyph.get_size(), pygame.SRCALPHA)
            pygame.mask.from_surface(glyph, 0).to_surface(
                backed, setcolor=(12, 15, 27, 255), unsetcolor=(0, 0, 0, 0)
            )
            backed.blit(glyph, (0, 0))
            return backed

        for action, (_, _, width, height) in regions.items():
            accent = self.COLORS[action]
            # Keep the original hit region, with a slimmer, centered capsule inside it.
            pill_height = max(1, round(height * .82))
            pill = pygame.Rect(0, (height - pill_height) // 2, width, pill_height)
            radius = pill.height // 2
            self.visual_rects[action] = pill
            pad = radius + max(3, round(8 * self.scale))
            self.progress_tracks[action] = pygame.Rect(
                pad, pill.bottom - max(5, round(12 * self.scale)),
                max(1, width - 2 * pad), max(2, round(3 * self.scale)),
            )
            margin = self.shadow_margin
            depth = pygame.Surface((width + depth_x + margin * 2, height + depth_y + margin * 2), pygame.SRCALPHA)
            depth.fill((0, 0, 0, 0))
            rear = pill.move(margin + depth_x, margin + depth_y)
            # Only outlines receive pixels. The scene remains visible through both
            # planes; cached contour bands soften the shadow without a filled card.
            for spread in range(margin, 0, -1):
                shade = (13 + spread * 2, 17 + spread * 2, 27 + spread * 3)
                pygame.draw.rect(depth, shade, rear.inflate(spread * 2, spread * 2),
                                 width=1, border_radius=radius + spread)
            pygame.draw.rect(depth, tuple(round(c * .30) for c in accent), rear,
                             width=1, border_radius=radius)
            pygame.draw.line(depth, tuple(round(c * .24) for c in accent),
                             (rear.left + radius, rear.bottom - 3),
                             (rear.right - radius, rear.bottom - 3), 1)
            for front in ((margin + radius, margin + pill.bottom - 1),
                          (margin + width - 1, margin + pill.centery),
                          (margin + width - radius, margin + pill.bottom - 1)):
                pygame.draw.line(depth, tuple(round(c * .44) for c in accent), front,
                                 (front[0] + depth_x, front[1] + depth_y), 1)
            self.depth_layers[action] = depth
            card = pygame.Surface((width, height), pygame.SRCALPHA)
            card.fill((0, 0, 0, 0))
            pygame.draw.rect(card, tuple(int(c * .55) for c in accent),
                             pill, width=1, border_radius=radius)
            # Restrained colored light along the top edge, wholly inside the card.
            pygame.draw.line(card, accent, (pad, pill.top + 2), (width - pad, pill.top + 2), 2)
            icon_inset = max(20, round(48 * self.scale))
            icon_x = icon_inset if action == "back" else width - icon_inset
            icon_y = pill.centery
            icon_radius = max(12, round(25 * self.scale))
            pygame.draw.circle(card, tuple(int(c * .48) for c in accent), (icon_x, icon_y), icon_radius, 1)
            direction = -1 if action == "back" else 1
            arm = max(5, round(10 * self.scale))
            pygame.draw.lines(card, accent, False,
                              [(icon_x - direction * arm // 2, icon_y - arm),
                               (icon_x + direction * arm // 2, icon_y),
                               (icon_x - direction * arm // 2, icon_y + arm)], max(2, round(3 * self.scale)))
            label = label_surface(title, action.upper(), (243, 245, 255))
            hint = "1秒キープで " + ("もどる" if action == "back" else "つぎへ")
            subtitle = label_surface(detail, hint, (213, 221, 242))
            gap = max(2, round(5 * self.scale))
            text_top = pill.top + (pill.height - label.get_height() - gap - subtitle.get_height()) // 2
            label_rect = label.get_rect(midtop=(width // 2, text_top))
            subtitle_rect = subtitle.get_rect(midtop=(width // 2, label_rect.bottom + gap))
            shadow = title.render(action.upper(), False, (12, 15, 27))
            card.blit(shadow, label_rect.move(2, 2))
            card.blit(label, label_rect)
            card.blit(detail.render(hint, False, (12, 15, 27)), subtitle_rect.move(1, 1))
            card.blit(subtitle, subtitle_rect)
            self.cards[action] = card
            lights = []
            for step in range(8):
                light = pygame.Surface((width, height), pygame.SRCALPHA)
                light.fill((0, 0, 0, 0))
                gain = .58 + step * .035
                tint = tuple(round(c * gain) for c in accent)
                glint = tuple(round(c * .45 + 255 * (.30 + step * .025)) for c in accent)
                shift = round(step * self.scale)
                pygame.draw.line(light, tint, (pad + shift, pill.top + 5),
                                 (min(width - pad, pad + round(width * .22) + shift), pill.top + 5), 1)
                pygame.draw.line(light, glint, (width - pad - shift, pill.bottom - 5),
                                 (width - pad - round(width * .20) - shift, pill.bottom - 5), 1)
                cap = pygame.Rect(width - pill.height + 4, pill.top + 4, pill.height - 8, pill.height - 8)
                pygame.draw.arc(light, tint, cap, -.28 + step * .01, .28 + step * .01, 1)
                lights.append(light)
            self.edge_lights[action] = tuple(lights)


def draw_navigation(screen, pygame, style, hold, now=None):
    now = time.monotonic() if now is None else now
    for index, (action, rect) in enumerate(hold.regions.items()):
        x, y, width, height = rect
        screen.blit(style.depth_layers[action], (x - style.shadow_margin, y - style.shadow_margin))
        screen.blit(style.cards[action], (x, y))
        breath = (math.sin(now * .85 + index * .8) + 1.0) * .5
        lights = style.edge_lights[action]
        screen.blit(lights[round(breath * (len(lights) - 1))], (x, y))
        if hold.active == action:
            color = style.COLORS[action]
            pill = style.visual_rects[action].move(x, y)
            pygame.draw.rect(screen, color, pill, width=2, border_radius=pill.height // 2)
            track = style.progress_tracks[action].move(x, y)
            bar_width = round(track.width * hold.progress)
            if bar_width > 0:
                pygame.draw.rect(screen, color, (track.x, track.y, bar_width, track.height),
                                 border_radius=track.height // 2)
    if hold.point is not None:
        x, y = map(int, hold.point)
        radius = max(20, min(46, screen.get_height() // 24))
        accent = style.COLORS.get(hold.active, (105, 243, 217))
        pygame.draw.circle(screen, (245, 250, 255), (x, y), 5)
        pygame.draw.circle(screen, (90, 105, 130), (x, y), radius, 3)
        if hold.progress >= 1:
            pygame.draw.circle(screen, accent, (x, y), radius, 5)
        elif hold.progress > 0:
            pygame.draw.arc(screen, accent, (x - radius, y - radius, radius * 2, radius * 2),
                            -math.pi / 2, -math.pi / 2 + math.tau * hold.progress, 5)


def run_overlay(port, token, geometry):
    from stage_display import configure_audience_dpi
    from transition_logo import CurtainLogo
    from transition_particles import ParticleCurtain

    configure_audience_dpi()
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{geometry[0]},{geometry[1]}"
    import pygame

    with ExitStack() as resources:
        channel = JsonChannel(socket.create_connection(("127.0.0.1", port), timeout=5.0))
        resources.callback(channel.close)
        if hasattr(signal, "SIGBREAK"):
            previous = signal.signal(signal.SIGBREAK, signal.default_int_handler)
            resources.callback(signal.signal, signal.SIGBREAK, previous)
        resources.callback(pygame.quit)
        pygame.init()
        screen = pygame.display.set_mode(geometry[2:], pygame.NOFRAME | pygame.HIDDEN)
        pygame.display.set_caption("Scene navigation")
        curtain = Curtain(cover_duration=1.2, reveal_duration=1.6)
        # Populate the hidden surface before Win32 makes the layered window visible.
        present_frame(screen, pygame, curtain, time.monotonic())
        configure_overlay_window(pygame, geometry)
        opacity = OverlayOpacity(pygame)
        clock = pygame.time.Clock()
        hold = NavigationHold(navigation_regions(*geometry[2:]), max_jump=max(30, geometry[2] * 0.06))
        style = NavigationStyle(pygame, hold.regions)
        camera_layer = CurtainCamera()
        logo = CurtainLogo(geometry[2:])
        particles = ParticleCurtain(geometry[2:])
        worker = DetectionWorker(*geometry[2:])
        resources.callback(worker.close)
        worker.start()
        revealed_once = False
        failure = None
        error_reported = False
        connected = True

        def disconnect(reason):
            nonlocal connected, failure
            connected = False
            failure = failure or str(reason)
            curtain.fail()

        def send(message):
            if not connected:
                return False
            try:
                channel.send(message)
                return True
            except OSError as exc:
                disconnect(exc)
                return False

        send({"event": "READY", "token": token, "pid": os.getpid()})

        while True:
            now = time.monotonic()
            messages = []
            if connected:
                try:
                    messages = channel.receive()
                except OSError as exc:
                    disconnect(exc)
                except SceneControlError as exc:
                    failure = failure or str(exc)
                    curtain.fail()
                if channel.eof:
                    disconnect("Overlay control connection closed")
            for message in messages:
                try:
                    if message.get("token") != token:
                        raise SceneControlError("Overlay command token mismatch")
                    command = message.get("command")
                    if command == "CLOSE":
                        return
                    if not connected:
                        continue
                    curtain.command(command, message.get("cycle"), now)
                    if command == "FAIL_CLOSED":
                        failure = failure or "Manager requested emergency cover"
                except Exception as exc:
                    failure = failure or str(exc)
                    curtain.fail()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    failure = failure or "Overlay window close requested"
                    curtain.fail()
            (observed_at, points), detection_error = worker.snapshot()
            if detection_error:
                failure = failure or detection_error
                curtain.fail()
            enabled = revealed_once and curtain.state == "idle" and failure is None
            action = hold.update(points, observed_at, now, enabled=enabled)
            try:
                camera_layer.update(pygame, worker.camera_snapshot(), curtain.state, now)
                if action is not None:
                    send({"event": "ACTION", "token": token, "cycle": curtain.cycle, "action": action})
                acknowledgement = present_frame(
                    screen, pygame, curtain, now,
                    (lambda: draw_navigation(screen, pygame, style, hold, now)) if enabled else None,
                    lambda rect: camera_layer.draw(screen, rect),
                    lambda rect: logo.draw(screen, rect, now, curtain),
                    opacity,
                    lambda rect: particles.draw(screen, rect, now, curtain),
                    lambda: particles.breakup(screen, now, curtain),
                )
                if acknowledgement is not None:
                    if send({"event": acknowledgement, "token": token, "cycle": curtain.cycle}):
                        if acknowledgement == "REVEALED":
                            revealed_once = True
                    else:
                        # A failed REVEALED send must restore the cover before the
                        # next tick. Keep painting until the owning Manager stops us.
                        present_frame(screen, pygame, curtain, now, opacity=opacity)
                if failure is not None and not error_reported and connected:
                    send({"event": "COVERED", "token": token, "cycle": curtain.cycle,
                          "emergency": True, "reason": failure[:1000]})
                    send({"event": "ERROR", "token": token, "cycle": curtain.cycle,
                          "reason": failure[:1000]})
                    error_reported = True
            except Exception as exc:
                failure = failure or str(exc)
                curtain.fail()
            clock.tick(60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-port", type=int, required=True)
    parser.add_argument("--token", required=True)
    for name in ("x", "y", "width", "height"):
        parser.add_argument(f"--{name}", type=int, required=True)
    args = parser.parse_args()
    if not 0 < args.control_port < 65536 or not args.token or min(args.width, args.height) <= 0:
        parser.error("Invalid overlay connection or geometry")
    try:
        run_overlay(args.control_port, args.token, (args.x, args.y, args.width, args.height))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
