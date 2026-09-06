"""
Display and camera helpers shared by scene scripts.
"""

import json
import os

import cv2
import numpy as np


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_WINDOW_WIDTH = 1360
DEFAULT_WINDOW_HEIGHT = 800
DEFAULT_CAMERA_INDEX = 1
DEFAULT_CAMERA_WIDTH = 1280
DEFAULT_CAMERA_HEIGHT = 720
DEFAULT_CAMERA_FPS = 60
DEFAULT_CAMERA_FOURCC = "MJPG"
DEFAULT_CAMERA_DIAGNOSTIC_SECONDS = 2.0
DEFAULT_CAMERA_STRICT_BACKEND = True
DEFAULT_CAMERA_ALLOW_FALLBACK = False
DEFAULT_CAMERA_BACKEND = "dshow"
DEFAULT_CAMERA_OPENCV_INDEX = None
DEFAULT_CAMERA_NAME_HINTS = ["c922", "pro stream webcam"]
DEFAULT_CAMERA_EXCLUDE_HINTS = ["nizima", "virtual", "logi capture"]
ENV_PREFIX = "KIDZDISCO_"


def _parse_bool_env(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _load_display_config():
    cfg = {
        "DISPLAY_INDEX": 0,
        "DISPLAY_WIDTH": DEFAULT_WINDOW_WIDTH,
        "DISPLAY_HEIGHT": DEFAULT_WINDOW_HEIGHT,
        "CAMERA_INDEX": DEFAULT_CAMERA_INDEX,
        "CAMERA_WIDTH": DEFAULT_CAMERA_WIDTH,
        "CAMERA_HEIGHT": DEFAULT_CAMERA_HEIGHT,
        "CAMERA_FPS": DEFAULT_CAMERA_FPS,
        "CAMERA_FOURCC": DEFAULT_CAMERA_FOURCC,
        "CAMERA_DIAGNOSTIC_SECONDS": DEFAULT_CAMERA_DIAGNOSTIC_SECONDS,
        "CAMERA_STRICT_BACKEND": DEFAULT_CAMERA_STRICT_BACKEND,
        "CAMERA_ALLOW_FALLBACK": DEFAULT_CAMERA_ALLOW_FALLBACK,
        "CAMERA_BACKEND": DEFAULT_CAMERA_BACKEND,
        "CAMERA_OPENCV_INDEX": DEFAULT_CAMERA_OPENCV_INDEX,
        "CAMERA_NAME_HINTS": DEFAULT_CAMERA_NAME_HINTS,
        "CAMERA_EXCLUDE_HINTS": DEFAULT_CAMERA_EXCLUDE_HINTS,
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            if isinstance(user_cfg, dict):
                cfg.update(user_cfg)
        except Exception:
            pass
    env_overrides = {
        "DISPLAY_TARGET": str,
        "DISPLAY_NAME": str,
        "CONTROL_DISPLAY_NAME": str,
        "DISPLAY_RESOLVED": _parse_bool_env,
        "DISPLAY_INDEX": int,
        "DISPLAY_X": int,
        "DISPLAY_Y": int,
        "DISPLAY_WIDTH": int,
        "DISPLAY_HEIGHT": int,
        "CAMERA_INDEX": int,
        "CAMERA_WIDTH": int,
        "CAMERA_HEIGHT": int,
        "CAMERA_FPS": int,
        "CAMERA_FOURCC": str,
        "CAMERA_BACKEND": str,
        "CAMERA_STRICT_BACKEND": _parse_bool_env,
        "CAMERA_ALLOW_FALLBACK": _parse_bool_env,
        "CAMERA_OPENCV_INDEX": int,
    }
    for key, caster in env_overrides.items():
        env_key = f"{ENV_PREFIX}{key}"
        if env_key in os.environ and os.environ[env_key] != "":
            try:
                cfg[key] = caster(os.environ[env_key])
            except Exception:
                pass
    return cfg


_DISPLAY_CFG = _load_display_config()


def get_second_monitor():
    display_target = str(_DISPLAY_CFG.get("DISPLAY_TARGET", "")).strip().lower()
    if display_target == "audience":
        from stage_display import DisplayConfigurationError, resolve_audience_displays

        stage = resolve_audience_displays(_DISPLAY_CFG)["audience"]
        geometry = tuple(stage[key] for key in ("x", "y", "width", "height"))
        if _DISPLAY_CFG.get("DISPLAY_RESOLVED"):
            expected = tuple(_DISPLAY_CFG.get(f"DISPLAY_{key}") for key in ("X", "Y", "WIDTH", "HEIGHT"))
            if geometry != expected:
                raise DisplayConfigurationError("Audience layout changed since Manager startup; stop and check the displays")
        print(f"[display_utils] Audience screen: {stage['name']} ({stage['width']}x{stage['height']} at {stage['x']},{stage['y']})")
        return geometry
    if display_target == "primary":
        try:
            from screeninfo import get_monitors

            monitors = get_monitors()
            primary = next((m for m in monitors if getattr(m, "is_primary", False)), monitors[0])
            print(f"[display_utils] Using primary monitor: {primary.name} ({primary.width}x{primary.height} at {primary.x},{primary.y})")
            return (primary.x, primary.y, primary.width, primary.height)
        except Exception as exc:
            print(f"[display_utils] Warning: Could not detect primary monitor: {exc}")
            return (0, 0, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

    if all(k in _DISPLAY_CFG for k in ("DISPLAY_X", "DISPLAY_Y", "DISPLAY_WIDTH", "DISPLAY_HEIGHT")):
        x = int(_DISPLAY_CFG["DISPLAY_X"])
        y = int(_DISPLAY_CFG["DISPLAY_Y"])
        w = int(_DISPLAY_CFG["DISPLAY_WIDTH"])
        h = int(_DISPLAY_CFG["DISPLAY_HEIGHT"])
        print(f"[display_utils] Using config override: {w}x{h} at {x},{y}")
        return (x, y, w, h)

    try:
        from screeninfo import get_monitors

        monitors = get_monitors()
        if len(monitors) < 2:
            print("[display_utils] Warning: Only 1 monitor detected, using primary.")
            m = monitors[0]
            return (m.x, m.y, m.width, m.height)

        display_idx = _DISPLAY_CFG.get("DISPLAY_INDEX", 0)
        non_primary = [m for m in monitors if not m.is_primary]
        if non_primary and display_idx < len(non_primary):
            m = non_primary[display_idx]
        elif display_idx < len(monitors):
            m = monitors[display_idx]
        else:
            m = monitors[0]

        print(f"[display_utils] Using monitor: {m.name} ({m.width}x{m.height} at {m.x},{m.y})")
        return (m.x, m.y, m.width, m.height)
    except ImportError:
        print("[display_utils] Warning: screeninfo not installed. Using default position.")
        return None
    except Exception as exc:
        print(f"[display_utils] Warning: Could not detect monitors: {exc}")
        return None

class CameraResizingProxy:
    def __init__(self, source):
        self._source = source
        self._target_width = None
        self._target_height = None

    def read(self):
        ok, frame = self._source.read()
        if not ok or frame is None:
            return ok, frame
        target_w = self._target_width
        target_h = self._target_height
        if target_w and target_h:
            src_h, src_w = frame.shape[:2]
            if src_w != target_w or src_h != target_h:
                frame = cv2.resize(
                    frame,
                    (int(target_w), int(target_h)),
                    interpolation=cv2.INTER_LINEAR,
                )
        return ok, frame

    def set(self, prop_id, value):
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            self._target_width = int(value)
            return True
        if prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            self._target_height = int(value)
            return True
        return self._source.set(prop_id, value)

    def get(self, prop_id):
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH and self._target_width:
            return float(self._target_width)
        if prop_id == cv2.CAP_PROP_FRAME_HEIGHT and self._target_height:
            return float(self._target_height)
        return self._source.get(prop_id)

    def isOpened(self):
        return self._source.isOpened()

    def release(self):
        return self._source.release()

    def __getattr__(self, name):
        return getattr(self._source, name)


def get_stage_size():
    monitor = get_second_monitor()
    if monitor:
        _x, _y, w, h = monitor
        return w, h
    return DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT


def get_uniform_layout(base_width, base_height, stage_width=None, stage_height=None):
    if stage_width is None or stage_height is None:
        stage_width, stage_height = get_stage_size()
    scale = min(stage_width / float(base_width), stage_height / float(base_height))
    scaled_width = max(1, int(round(base_width * scale)))
    scaled_height = max(1, int(round(base_height * scale)))
    offset_x = (stage_width - scaled_width) // 2
    offset_y = (stage_height - scaled_height) // 2
    return {
        "base_width": int(base_width),
        "base_height": int(base_height),
        "stage_width": int(stage_width),
        "stage_height": int(stage_height),
        "scaled_width": int(scaled_width),
        "scaled_height": int(scaled_height),
        "offset_x": int(offset_x),
        "offset_y": int(offset_y),
        "scale": float(scale),
    }


def fit_frame_to_size(frame, target_width, target_height, pad_color=(0, 0, 0), *, layout=None):
    src_h, src_w = frame.shape[:2]
    if src_w == target_width and src_h == target_height:
        return frame
    if layout is None:
        layout = get_uniform_layout(src_w, src_h, target_width, target_height)
    resized = cv2.resize(
        frame,
        (layout["scaled_width"], layout["scaled_height"]),
        interpolation=cv2.INTER_LINEAR,
    )
    canvas = np.zeros((target_height, target_width, frame.shape[2]), dtype=frame.dtype)
    if pad_color != (0, 0, 0):
        canvas[:] = pad_color
    ox = layout["offset_x"]
    oy = layout["offset_y"]
    canvas[oy : oy + layout["scaled_height"], ox : ox + layout["scaled_width"]] = resized
    return canvas


def prepare_camera_frame(frame, stage_width, stage_height, mirror=True, pad_color=(0, 0, 0)):
    if frame is None:
        return None, None, None
    camera_frame = cv2.flip(frame, 1) if mirror else frame
    frame_h, frame_w = camera_frame.shape[:2]
    layout = get_uniform_layout(frame_w, frame_h, stage_width, stage_height)
    # The image placement and landmark projection must consume this same layout.
    stage_frame = fit_frame_to_size(camera_frame, stage_width, stage_height, pad_color=pad_color, layout=layout)
    return camera_frame, stage_frame, layout


def normalized_to_stage(norm_x, norm_y, layout):
    if layout is None:
        return int(norm_x), int(norm_y)
    nx = max(0.0, min(1.0, float(norm_x)))
    ny = max(0.0, min(1.0, float(norm_y)))
    x = layout["offset_x"] + nx * (layout["scaled_width"] - 1)
    y = layout["offset_y"] + ny * (layout["scaled_height"] - 1)
    return int(round(x)), int(round(y))


def setup_cv2_fullscreen(window_name):
    monitor = get_second_monitor()
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    if monitor:
        x, y, w, h = monitor
    else:
        x, y, w, h = 0, 0, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT

    cv2.moveWindow(window_name, x, y)
    cv2.resizeWindow(window_name, w, h)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    return monitor


def setup_pygame_fullscreen():
    import pygame

    monitor = get_second_monitor()
    if monitor:
        x, y, w, h = monitor
    else:
        x, y, w, h = 0, 0, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT

    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
    screen = pygame.display.set_mode((w, h), pygame.NOFRAME)
    return screen, (w, h)


def setup_pygame_scaled_fullscreen(base_width, base_height):
    import pygame

    window_screen, (stage_width, stage_height) = setup_pygame_fullscreen()
    layout = get_uniform_layout(base_width, base_height, stage_width, stage_height)
    scene_surface = pygame.Surface((int(base_width), int(base_height))).convert()
    return window_screen, scene_surface, layout


def present_pygame_scaled(window_screen, scene_surface, layout):
    import pygame

    scaled = pygame.transform.smoothscale(
        scene_surface,
        (layout["scaled_width"], layout["scaled_height"]),
    )
    window_screen.fill((0, 0, 0))
    window_screen.blit(scaled, (layout["offset_x"], layout["offset_y"]))
    pygame.display.flip()


def get_second_monitor_size():
    monitor = get_second_monitor()
    if monitor:
        x, y, w, h = monitor
        return (w, h, x, y)
    return (DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT, 0, 0)


def setup_rendercanvas_fullscreen(canvas):
    monitor = get_second_monitor()
    if monitor:
        x, y, w, h = monitor
    else:
        x, y, w, h = 0, 0, DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT

    try:
        import glfw

        if hasattr(canvas, "_window") and canvas._window:
            # Removing decorations can change the Win32 client bounds. Do it
            # before the final placement so the audience screen stays covered.
            glfw.set_window_attrib(canvas._window, glfw.DECORATED, False)
            glfw.set_window_pos(canvas._window, x, y)
            glfw.set_window_size(canvas._window, w, h)
            print(f"[display_utils] RenderCanvas moved to {x},{y} size {w}x{h}")
        else:
            print("[display_utils] Warning: canvas._window not available")
    except ImportError:
        print("[display_utils] Warning: glfw not installed, cannot move RenderCanvas")
    except Exception as exc:
        print(f"[display_utils] Warning: Failed to move RenderCanvas: {exc}")


def open_camera(
    camera_index=None,
    width=None,
    height=None,
    fps=None,
    fallback_to_default=None,
):
    if camera_index is None:
        camera_index = _DISPLAY_CFG.get("CAMERA_INDEX", DEFAULT_CAMERA_INDEX)
    if width is None:
        width = _DISPLAY_CFG.get("CAMERA_WIDTH", DEFAULT_CAMERA_WIDTH)
    if height is None:
        height = _DISPLAY_CFG.get("CAMERA_HEIGHT", DEFAULT_CAMERA_HEIGHT)
    if fps is None:
        fps = _DISPLAY_CFG.get("CAMERA_FPS", DEFAULT_CAMERA_FPS)
    if fallback_to_default is None:
        fallback_to_default = _DISPLAY_CFG.get("CAMERA_ALLOW_FALLBACK", DEFAULT_CAMERA_ALLOW_FALLBACK)

    try:
        from shared_camera import open_camera_source

        cap = open_camera_source(
            camera_index=camera_index,
            width=width,
            height=height,
            fps=fps,
            fourcc=_DISPLAY_CFG.get("CAMERA_FOURCC", DEFAULT_CAMERA_FOURCC),
            diagnostic_seconds=_DISPLAY_CFG.get("CAMERA_DIAGNOSTIC_SECONDS", DEFAULT_CAMERA_DIAGNOSTIC_SECONDS),
            strict_backend=_DISPLAY_CFG.get("CAMERA_STRICT_BACKEND", DEFAULT_CAMERA_STRICT_BACKEND),
            backend_preference=_DISPLAY_CFG.get("CAMERA_BACKEND", DEFAULT_CAMERA_BACKEND),
            fallback_to_default=fallback_to_default,
            camera_name_hint=_DISPLAY_CFG.get("CAMERA_NAME_HINTS", DEFAULT_CAMERA_NAME_HINTS),
            exclude_name_hints=_DISPLAY_CFG.get("CAMERA_EXCLUDE_HINTS", DEFAULT_CAMERA_EXCLUDE_HINTS),
            explicit_index=_DISPLAY_CFG.get("CAMERA_OPENCV_INDEX", DEFAULT_CAMERA_OPENCV_INDEX),
        )
        return CameraResizingProxy(cap) if cap is not None else None
    except Exception as exc:
        print(f"[display_utils] Error: camera open failed: {exc}")
        return None


def get_camera_frame_size(cap, default_width=DEFAULT_CAMERA_WIDTH, default_height=DEFAULT_CAMERA_HEIGHT):
    width = default_width
    height = default_height
    try:
        if cap is not None and cap.isOpened():
            cap_width = int(cap.get(3))
            cap_height = int(cap.get(4))
            if cap_width > 0:
                width = cap_width
            if cap_height > 0:
                height = cap_height
    except Exception:
        pass
    return width, height


def resolve_model_path(*relative_candidates):
    for candidate in relative_candidates:
        full_path = os.path.join(BASE_DIR, candidate)
        if os.path.exists(full_path):
            return full_path
    return os.path.join(BASE_DIR, relative_candidates[0])


def is_valid_model_asset(path, min_size_bytes=4096):
    try:
        return os.path.exists(path) and os.path.getsize(path) >= min_size_bytes
    except OSError:
        return False
