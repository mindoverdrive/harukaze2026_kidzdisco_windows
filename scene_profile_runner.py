import os
import runpy
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

PROFILES = {
    "stage": {},
    "acer": {
        "KIDZDISCO_DISPLAY_TARGET": "primary",
        "KIDZDISCO_CAMERA_INDEX": "0",
        "KIDZDISCO_CAMERA_BACKEND": "any",
        "KIDZDISCO_CAMERA_STRICT_BACKEND": "false",
        "KIDZDISCO_CAMERA_ALLOW_FALLBACK": "true",
    },
}


def run_scene(script_name, profile="stage"):
    script_path = BASE_DIR / script_name
    if not script_path.exists():
        raise FileNotFoundError(f"Scene script not found: {script_path}")

    overrides = PROFILES.get(profile, {})
    previous = {}
    try:
        for key, value in overrides.items():
            previous[key] = os.environ.get(key)
            os.environ[key] = str(value)
        runpy.run_path(str(script_path), run_name="__main__")
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
