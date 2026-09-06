"""Camera-free launcher whose child already belongs to a private Windows Job."""
import ctypes
import json
from pathlib import Path
import signal
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from windows_process import _ExtendedLimits, _check, _kernel

signal.signal(signal.SIGBREAK, signal.default_int_handler)
kernel = _kernel()
job = _check(kernel.CreateJobObjectW(None, None))
child = None
try:
    limits = _ExtendedLimits()
    limits.basic.flags = 0x2000
    _check(kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    _check(kernel.AssignProcessToJobObject(job, int(child._handle)))
    ready = Path(sys.argv[1])
    pending = ready.with_suffix(".pending")
    pending.write_text(json.dumps({"child_pid": child.pid}), encoding="utf-8")
    pending.replace(ready)
    child.wait()
except KeyboardInterrupt:
    pass
finally:
    kernel.CloseHandle(job)
    if child is not None:
        child.wait(timeout=3)
