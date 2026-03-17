"""
display_utils.py
全シーンスクリプト共通のディスプレイ設定ユーティリティ。
セカンドモニター（デスクトップ2）にフルスクリーンで表示する。
"""

import os
import json

# config.json からモニター設定を読み込み
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

def _load_display_config():
    """config.json からディスプレイ設定を読み込む"""
    cfg = {
        "DISPLAY_INDEX": 0,  # デフォルト: セカンドモニター（0番目 = 非プライマリ）
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
    """
    セカンドモニター（デスクトップ2）の情報を返す。
    Returns: (x, y, width, height) or None
    """
    try:
        from screeninfo import get_monitors
        monitors = get_monitors()
        if len(monitors) < 2:
            print("[display_utils] Warning: Only 1 monitor detected, using primary.")
            m = monitors[0]
            return (m.x, m.y, m.width, m.height)

        # DISPLAY_INDEX で指定（デフォルト0 = 最初のモニター）
        display_idx = _DISPLAY_CFG.get("DISPLAY_INDEX", 0)

        # 非プライマリモニターを優先的に取得
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
    except Exception as e:
        print(f"[display_utils] Warning: Could not detect monitors: {e}")
        return None


def setup_cv2_fullscreen(window_name):
    """
    OpenCV のウィンドウをセカンドモニターにフルスクリーン表示する。
    使い方:
        setup_cv2_fullscreen('My Window')
        cv2.imshow('My Window', frame)
    """
    import cv2

    monitor = get_second_monitor()

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    if monitor:
        x, y, w, h = monitor
        cv2.moveWindow(window_name, x, y)
        cv2.resizeWindow(window_name, w, h)
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    return monitor


def setup_pygame_fullscreen():
    """
    Pygame のウィンドウをセカンドモニターにフルスクリーン表示する。
    使い方:
        screen, (w, h) = setup_pygame_fullscreen()
    Returns: (screen, (width, height))
    """
    import pygame

    monitor = get_second_monitor()

    if monitor:
        x, y, w, h = monitor
        # ウィンドウ位置を環境変数で指定（pygame が参照する）
        os.environ['SDL_VIDEO_WINDOW_POS'] = f'{x},{y}'
        screen = pygame.display.set_mode((w, h), pygame.NOFRAME)
        return screen, (w, h)
    else:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        info = pygame.display.Info()
        return screen, (info.current_w, info.current_h)


def get_second_monitor_size():
    """
    セカンドモニターのサイズだけを返す。
    RenderCanvas 等で使用。
    Returns: (width, height, x, y) or (1920, 1080, 0, 0) as default
    """
    monitor = get_second_monitor()
    if monitor:
        x, y, w, h = monitor
        return (w, h, x, y)
    return (1920, 1080, 0, 0)
