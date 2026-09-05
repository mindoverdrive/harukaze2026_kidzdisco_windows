import os
import sys
import time
from types import SimpleNamespace
from scene_control import notify_first_frame

assert "--control-port" not in sys.argv and "--launch-id" not in sys.argv
assert "--wait" not in sys.argv
if os.environ.get("FIXTURE_FAIL") == "1":
    raise RuntimeError("injected initialization failure")
time.sleep(float(os.environ.get("FIXTURE_FRAME_DELAY", "0")))
if os.environ.get("FIXTURE_NO_FRAME") != "1":
    notify_first_frame(SimpleNamespace(last_read_frame_id=42, shm_name="fixture_camera"))
while True:
    time.sleep(0.05)
