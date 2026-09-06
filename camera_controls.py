"""Bounded camera commands; only the capture owner touches the driver."""
import json
import math
import os
from pathlib import Path
import threading
import uuid


CONTROL_SPECS = {
    "exposure": {"config": "CAMERA_EXPOSURE", "property": "CAP_PROP_EXPOSURE", "min": -13, "max": 0, "step": 1},
    "zoom": {"config": "CAMERA_ZOOM", "property": "CAP_PROP_ZOOM", "min": 100, "max": 500, "step": 1},
}


def validate_controls(values):
    if not isinstance(values, dict) or not values or set(values) - CONTROL_SPECS.keys():
        raise ValueError("露出・ズームだけを指定してください")
    result = {}
    for name, value in values.items():
        spec = CONTROL_SPECS[name]
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                or not spec["min"] <= value <= spec["max"] or value != int(value)):
            raise ValueError(f"{name}: {spec['min']}〜{spec['max']}の整数を指定してください")
        result[name] = int(value)
    return result


def read_controls(cap):
    import cv2
    values = {}
    for name, spec in CONTROL_SPECS.items():
        try:
            value = float(cap.get(getattr(cv2, spec["property"])))
            values[name] = value if math.isfinite(value) and spec["min"] <= value <= spec["max"] else None
        except Exception:
            values[name] = None
    return values


def apply_controls(cap, values):
    import cv2
    values = validate_controls(values)
    previous = read_controls(cap)
    attempted = []
    try:
        for name, value in values.items():
            prop = getattr(cv2, CONTROL_SPECS[name]["property"])
            attempted.append(name)
            if not cap.set(prop, value):
                raise RuntimeError(f"{name}: カメラが設定を拒否しました")
            actual = float(cap.get(prop))
            if not math.isfinite(actual) or abs(actual - value) > 0.5:
                raise RuntimeError(f"{name}: 要求={value}、読戻し={actual}で一致しません")
        return read_controls(cap)
    except Exception as exc:
        rollback_errors = []
        for name in reversed(attempted):
            try:
                old = previous[name]
                prop = getattr(cv2, CONTROL_SPECS[name]["property"])
                if old is None or not cap.set(prop, old):
                    rollback_errors.append(name)
                else:
                    restored = float(cap.get(prop))
                    if not math.isfinite(restored) or abs(restored - old) > 0.5:
                        rollback_errors.append(name)
            except Exception:
                rollback_errors.append(name)
        suffix = f" / 元の値の復元を確認できません: {', '.join(rollback_errors)}" if rollback_errors else ""
        raise RuntimeError(str(exc) + suffix) from exc


class CameraControlMailbox:
    def __init__(self):
        self.lock = threading.Lock()
        self.save_lock = threading.Lock()
        self.pending = None
        self.closed = False
        self.state = {"sequence": 0, "status": "idle", "actual": {}, "applied": {}, "error": None}

    def snapshot(self):
        with self.lock:
            return {**self.state, "actual": dict(self.state["actual"]), "applied": dict(self.state["applied"])}

    def observe(self, cap):
        values = read_controls(cap)
        with self.lock:
            self.state["actual"] = values

    def submit(self, values):
        values = validate_controls(values)
        with self.lock:
            if self.closed or self.state["status"] in {"pending", "applying"}:
                raise RuntimeError("カメラは終了中、または前の設定を反映中です")
            self.state.update(sequence=self.state["sequence"] + 1, status="pending", error=None)
            self.pending = (self.state["sequence"], values)
            return self.state["sequence"]

    def apply_pending(self, cap):
        with self.lock:
            if self.pending is None or self.closed:
                return None
            sequence, values = self.pending
            self.pending = None
            self.state["status"] = "applying"
        error = None
        try:
            actual = apply_controls(cap, values)
        except Exception as exc:
            actual, error = read_controls(cap), str(exc)
        with self.lock:
            if not self.closed:
                self.state.update(status="failed" if error else "applied", error=error, actual=actual)
                if error is None:
                    self.state["applied"].update(values)
        print(f"[CameraControls] sequence={sequence} values={values} actual={actual} error={error}")
        return values if error is None else None

    def close(self):
        with self.lock:
            self.closed = True
            self.pending = None
            self.state.update(status="closed", error="カメラを終了しました")


def save_controls(config_path, mailbox, sequence):
    # Persist only a confirmed command, never an unverified slider value.
    with mailbox.save_lock:
        state = mailbox.snapshot()
        if state["status"] != "applied" or state["sequence"] != sequence or not state["applied"]:
            raise RuntimeError("適用完了を確認してから保存してください")
        values = validate_controls(state["applied"])
        path = Path(config_path)
        original = path.read_bytes()
        data = json.loads(original.decode("utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("設定JSONがオブジェクトではありません")
        for name, value in values.items():
            data[CONTROL_SPECS[name]["config"]] = value
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            # Apply/close may run while the file is prepared; serialize saves and
            # keep the final confirmation and publication atomic with submit.
            with mailbox.lock:
                if mailbox.state["status"] != "applied" or mailbox.state["sequence"] != sequence:
                    raise RuntimeError("設定が別の操作で変わりました。適用完了を再確認してください")
                if path.read_bytes() != original:
                    raise RuntimeError("設定ファイルが他の操作で変わりました。再確認してください")
                os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return {CONTROL_SPECS[name]["config"]: value for name, value in values.items()}
