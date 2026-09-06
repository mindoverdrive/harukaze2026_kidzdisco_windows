"""Resolve the audience and operator screens without opening any windows."""
import os


AUDIENCE_DPI_ENV = {
    "SDL_WINDOWS_DPI_AWARENESS": "permonitorv2",
    "SDL_WINDOWS_DPI_SCALING": "0",
}


class DisplayConfigurationError(RuntimeError):
    pass


def configure_audience_dpi():
    """Keep screen enumeration and scene coordinates in physical pixels."""
    if os.name != "nt":
        raise DisplayConfigurationError("The Acer audience entrypoint requires Windows")
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    user32.GetThreadDpiAwarenessContext.argtypes = []
    user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int
    changed = user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    error = ctypes.get_last_error() if not changed else 0
    awareness = user32.GetAwarenessFromDpiAwarenessContext(user32.GetThreadDpiAwarenessContext())
    # ERROR_ACCESS_DENIED means a dependency already fixed the process mode.
    # Per-monitor V1 also supplies physical pixels; do not claim it is V2.
    if awareness != 2 or (not changed and error != 5):
        raise DisplayConfigurationError(
            f"Per-monitor DPI awareness required before opening windows (mode={awareness}, error={error})"
        )
    return {"awareness": "per_monitor", "physical_pixels": True}


def resolve_audience_displays(config, monitors=None):
    if monitors is None:
        try:
            from screeninfo import get_monitors
            monitors = get_monitors()
        except Exception as exc:
            raise DisplayConfigurationError(f"Cannot enumerate audience/operator screens: {exc}") from exc
    monitors = list(monitors)
    observed = [str(getattr(m, "name", None)) for m in monitors]

    def select(key):
        name = config.get(key)
        if not isinstance(name, str) or not name.strip():
            raise DisplayConfigurationError(f"{key} must explicitly name a Windows display")
        matches = [m for m in monitors if str(getattr(m, "name", "")).casefold() == name.casefold()]
        if len(matches) != 1:
            raise DisplayConfigurationError(f"Expected one {name}; detected displays: {observed}")
        m = matches[0]
        values = [getattr(m, k, None) for k in ("x", "y", "width", "height")]
        if any(type(v) is not int for v in values) or min(values[2:]) <= 0:
            raise DisplayConfigurationError(f"Invalid monitor geometry for {name}: {values}")
        return {"name": m.name, "x": m.x, "y": m.y, "width": m.width, "height": m.height,
                "is_primary": bool(getattr(m, "is_primary", False))}

    control = select("CONTROL_DISPLAY_NAME")
    audience = select("DISPLAY_NAME")
    if not control["is_primary"] or audience["is_primary"] or control["name"] == audience["name"]:
        raise DisplayConfigurationError("Operator display must be primary; audience display must be a separate extended screen")
    overlaps = (
        max(control["x"], audience["x"]) < min(control["x"] + control["width"], audience["x"] + audience["width"])
        and max(control["y"], audience["y"]) < min(control["y"] + control["height"], audience["y"] + audience["height"])
    )
    if overlaps:
        raise DisplayConfigurationError("Audience and operator screens overlap; use an extended desktop")
    return {"control": control, "audience": audience}


def apply_audience_displays(config):
    displays = resolve_audience_displays(config)
    result = dict(config)
    for key in ("x", "y", "width", "height"):
        result[f"DISPLAY_{key.upper()}"] = displays["audience"][key]
    result["_DISPLAY_OBSERVATION"] = displays
    return result
