"""Model a Windows venv redirector using an owned, camera-free child process."""
from pathlib import Path
import signal
import subprocess
import sys

signal.signal(signal.SIGBREAK, signal.default_int_handler)
child = subprocess.Popen([sys.executable, str(Path(__file__).with_name("handshake_scene_acer.py")), *sys.argv[1:]])
try:
    raise SystemExit(child.wait())
except KeyboardInterrupt:
    if child.poll() is None:
        child.terminate()
    child.wait(timeout=3)
