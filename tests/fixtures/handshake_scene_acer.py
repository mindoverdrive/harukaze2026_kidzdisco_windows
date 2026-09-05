"""Camera-free process fixture for the real runner/control integration tests."""
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scene_profile_runner import run_scene

time.sleep(float(os.environ.get("FIXTURE_READY_DELAY", "0")))
try:
    run_scene(str(Path(__file__).with_name("handshake_body.py")), profile="stage")
except KeyboardInterrupt:
    pass  # A Manager-requested graceful shutdown is expected in this fixture.
