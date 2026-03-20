"""
Display and camera helpers shared by scene scripts.
"""

import json
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_WINDOW_WIDTH = 1360
DEFAULT_WINDOW_HEIGHT = 800
DEFAULT_CAMERA_INDEX = 1
DEFAULT_CAMERA_WIDTH = 1280
DEFAULT_CAMERA_HEIGHT = 720
DEFAULT_CAMERA_FPS = 60
DEFAULT_CAMERA_ALLOW_FALLBACK = False
DEFAULT_CAMERA_BACKEND = "dshow"
DEFAULT_CAMERA_OPENCV_INDEX = None
DEFAULT_CAMERA_NAME_HINTS = ["c922", "pro stream webcam"]
DEFAULT_CAMERA_EXCLUDE_HINTS = ["nizima", "virtual", "logi capture"]


def _load_display_config():
    cfg = {
        "DISPLAY_INDEX": 0,
        "DISPLAY_WIDTH": DEFAULT_WINDOW_WIDTH,
        "DISPLAY_HEIGHT": DEFAULT_WINDOW_HEIGHT,
        "CAMERA_INDEX": DEFAULT_CAMERA_INDEX,
        "CAMERA_WIDTH": DEFAULT_CAMERA_WIDTH,
        "CAMERA_HEIGHT": DEFAULT_CAMERA_HEIGHT,
        "CAMERA_FPS": DEFAULT_CAMERA_FPS,
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
    return cfg


_DISPLAY_CFG = _load_display_config()


def get_second_monitor():
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


def setup_cv2_fullscreen(window_name):
    import cv2

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
            glfw.set_window_pos(canvas._window, x, y)
            glfw.set_window_size(canvas._window, w, h)
            glfw.set_window_attrib(canvas._window, glfw.DECORATED, False)
            print(f"[display_utils] RenderCanvas moved to {x},{y} size {w}x{h}")
        else:
            print("[display_utils] Warning: canvas._window not available")
    except ImportError:
        print("[display_utils] Warning: glfw not installed, cannot move RenderCanvas")
    except Exception as exc:
        print(f"[display_utils] Warning: Failed to move RenderCanvas: {exc}")


def open_camera(
    camera_index=None,
    width=DEFAULT_CAMERA_WIDTH,
    height=DEFAULT_CAMERA_HEIGHT,
    fps=DEFAULT_CAMERA_FPS,
    fallback_to_default=None,
):
    if camera_index is None:
        camera_index = _DISPLAY_CFG.get("CAMERA_INDEX", DEFAULT_CAMERA_INDEX)
    if fallback_to_default is None:
        fallback_to_default = _DISPLAY_CFG.get("CAMERA_ALLOW_FALLBACK", DEFAULT_CAMERA_ALLOW_FALLBACK)

    try:
        from shared_camera import open_camera_source

        return open_camera_source(
            camera_index=camera_index,
            width=width,
            height=height,
            fps=fps,
            backend_preference=_DISPLAY_CFG.get("CAMERA_BACKEND", DEFAULT_CAMERA_BACKEND),
            fallback_to_default=fallback_to_default,
            camera_name_hint=_DISPLAY_CFG.get("CAMERA_NAME_HINTS", DEFAULT_CAMERA_NAME_HINTS),
            exclude_name_hints=_DISPLAY_CFG.get("CAMERA_EXCLUDE_HINTS", DEFAULT_CAMERA_EXCLUDE_HINTS),
            explicit_index=_DISPLAY_CFG.get("CAMERA_OPENCV_INDEX", DEFAULT_CAMERA_OPENCV_INDEX),
        )
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
