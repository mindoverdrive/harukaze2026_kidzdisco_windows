import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from unittest import mock

from scene_control import JsonChannel, SceneLaunchControl, SceneControlError


class SceneControlTests(unittest.TestCase):
    def spawn_fixture(self, control, **settings):
        env = os.environ.copy()
        env.update({key: str(value) for key, value in settings.items()})
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        fixture = Path(__file__).parent / "fixtures" / "handshake_scene_acer.py"
        proc = subprocess.Popen([sys.executable, "-u", str(fixture), *control.argv()],
                                env=env, creationflags=flags,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def cleanup():
            control.close()
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=3)
        self.addCleanup(cleanup)
        return proc

    def wait_state(self, control, proc, expected, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if control.poll(proc) == expected:
                return
            time.sleep(0.005)
        self.fail(f"did not reach {expected}: {control.state}")

    def test_real_runner_waits_for_start_and_reports_first_processed_frame(self):
        control = SceneLaunchControl(ready_timeout=3)
        proc = self.spawn_fixture(control, FIXTURE_READY_DELAY=0.08, FIXTURE_FRAME_DELAY=0.12)
        self.assertEqual(control.poll(proc), "LAUNCHED")
        self.wait_state(control, proc, "READY")
        self.assertIsNone(control.first_frame)
        control.start()
        self.wait_state(control, proc, "START_ACK")
        self.assertIsNone(control.first_frame)
        self.wait_state(control, proc, "FIRST_FRAME")
        self.assertEqual(control.first_frame["frame_id"], 42)
        self.assertEqual(control.first_frame["pid"], proc.pid)
        with self.assertRaisesRegex(SceneControlError, "requires READY"):
            control.start()

    def test_initialization_exception_is_observed_without_first_frame(self):
        control = SceneLaunchControl(ready_timeout=3)
        proc = self.spawn_fixture(control, FIXTURE_FAIL=1)
        self.wait_state(control, proc, "READY")
        control.start()
        with self.assertRaises(SceneControlError):
            self.wait_state(control, proc, "FIRST_FRAME")
        self.assertIsNone(control.first_frame)

    def test_missing_first_frame_has_a_deadline(self):
        control = SceneLaunchControl(ready_timeout=3, frame_timeout=0.15)
        proc = self.spawn_fixture(control, FIXTURE_NO_FRAME=1)
        self.wait_state(control, proc, "READY")
        control.start()
        with self.assertRaisesRegex(SceneControlError, "FIRST_FRAME timeout"):
            self.wait_state(control, proc, "FIRST_FRAME")

    def test_waiting_child_exits_on_manager_disconnect(self):
        control = SceneLaunchControl(ready_timeout=3)
        proc = self.spawn_fixture(control)
        self.wait_state(control, proc, "READY")
        control.close()
        self.assertNotEqual(proc.wait(timeout=3), 0)

    def test_fragmented_and_combined_messages_have_explicit_boundaries(self):
        left, right = socket.socketpair()
        channel = JsonChannel(left)
        self.addCleanup(channel.close)
        self.addCleanup(right.close)
        right.sendall(b'{"event":"REA')
        self.assertEqual(channel.receive(), [])
        right.sendall(b'DY"}\n{"event":"START_ACK"}\n')
        self.assertEqual([m["event"] for m in channel.receive()], ["READY", "START_ACK"])

    def test_wrong_launch_identity_is_rejected(self):
        control = SceneLaunchControl()
        self.addCleanup(control.close)
        connection = socket.create_connection(("127.0.0.1", control.port))
        self.addCleanup(connection.close)
        process = mock.Mock(pid=123, returncode=None)
        process.poll.return_value = None
        message = {"event": "READY", "launch_id": "wrong", "pid": 123}
        connection.sendall(json.dumps(message).encode() + b"\n")
        with self.assertRaisesRegex(SceneControlError, "mismatch"):
            control.poll(process)

    def test_ready_timeout_does_not_apply_to_idle_preloaded_scene(self):
        control = SceneLaunchControl(ready_timeout=3)
        proc = self.spawn_fixture(control)
        self.wait_state(control, proc, "READY")
        control.created_at -= 3600
        self.assertEqual(control.poll(proc), "READY")


if __name__ == "__main__":
    unittest.main()
