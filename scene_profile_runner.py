import os
import argparse
import runpy
import signal
import sys
from pathlib import Path
import scene_control


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


def resolve_scene_path(script_name):
    script_path = (BASE_DIR / script_name).resolve()
    if not script_path.is_relative_to(BASE_DIR) or script_path.suffix != ".py":
        raise ValueError(f"Scene source must be a Python file inside {BASE_DIR}: {script_name}")
    if not script_path.is_file():
        raise FileNotFoundError(f"Scene script not found: {script_path}")
    return script_path


def run_scene(script_name, profile="stage"):
    script_path = resolve_scene_path(script_name)
    if profile not in PROFILES:
        raise ValueError(f"Unknown scene profile: {profile}")

    overrides = PROFILES.get(profile, {})
    previous = {}
    previous_argv = sys.argv[:]
    previous_break_handler = None
    control = None
    previous_control = scene_control._child_control
    lifecycle = scene_control.SceneLifecycle(script_path.name)
    previous_lifecycle = scene_control._scene_lifecycle
    failure = None
    secondary_failures = []
    try:
        scene_control._scene_lifecycle = lifecycle
        for key, value in overrides.items():
            if key in os.environ:
                continue
            previous[key] = os.environ.get(key)
            os.environ[key] = str(value)
        if os.environ.get("KIDZDISCO_DISPLAY_TARGET") == "audience":
            from stage_display import AUDIENCE_DPI_ENV, configure_audience_dpi

            for key, value in AUDIENCE_DPI_ENV.items():
                previous[key] = os.environ.get(key)
                os.environ[key] = value
            configure_audience_dpi()
        parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
        parser.add_argument("--control-port", type=int)
        parser.add_argument("--launch-id")
        args, remaining = parser.parse_known_args(sys.argv[1:])
        lifecycle.launch_id = args.launch_id
        if (args.control_port is None) != (args.launch_id is None):
            raise ValueError("--control-port and --launch-id must be supplied together")
        if hasattr(signal, "SIGBREAK"):
            previous_break_handler = signal.signal(signal.SIGBREAK, signal.default_int_handler)
        if args.control_port is not None:
            if "--wait" in remaining or "--port" in remaining:
                raise ValueError("TCP control and legacy UDP wait cannot be combined")
            sys.argv = [str(script_path), *remaining]
            control = scene_control.SceneChildControl(args.control_port, args.launch_id)
            scene_control._child_control = control
            control.wait_for_start()
        runpy.run_path(str(script_path), run_name="__main__")
    except BaseException as exc:
        failure = exc
        if control is not None:
            try:
                control.send("ERROR", reason=f"{type(exc).__name__}: {exc}"[:1500])
            except BaseException as notification_failure:
                secondary_failures.append(("ERROR notification", notification_failure))
        raise
    finally:
        def finalize(step, action, *args):
            try:
                action(*args)
            except BaseException as cleanup_failure:
                secondary_failures.append((step, cleanup_failure))

        # Each owned cleanup is attempted even if an earlier observation or close fails.
        finalize("lifecycle.finish", lifecycle.finish, failure)
        scene_control._scene_lifecycle = previous_lifecycle
        if control is not None:
            finalize("control.close", control.close)
        scene_control._child_control = previous_control
        sys.argv = previous_argv
        if previous_break_handler is not None:
            finalize("signal restore", signal.signal, signal.SIGBREAK, previous_break_handler)
        for key, old_value in previous.items():
            if old_value is None:
                finalize(f"environment restore ({key})", os.environ.pop, key, None)
            else:
                finalize(f"environment restore ({key})", os.environ.__setitem__, key, old_value)
        if secondary_failures:
            primary = failure if failure is not None else secondary_failures[0][1]
            for step, secondary in secondary_failures:
                if secondary is not primary:
                    try:
                        BaseException.add_note(primary, f"Runner {step} failed: {type(secondary).__name__}")
                    except BaseException:
                        # Reporting a secondary failure must not replace the original exception.
                        pass
            if failure is None:
                raise primary
