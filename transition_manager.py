"""Manager-owned, persistent transition overlay with presentation acknowledgements."""

from pathlib import Path
import socket
import sys
import time
import uuid

from scene_control import JsonChannel, SceneControlError
from windows_process import get_scene_job


class TransitionManager:
    READY_TIMEOUT = 12.0
    COMMAND_TIMEOUT = 4.0

    def __init__(self, spawn, stop, geometry, camera_env=None, on_event=None):
        self.spawn, self.stop = spawn, stop
        if isinstance(geometry, dict):
            geometry = tuple(geometry[key] for key in ("x", "y", "width", "height"))
        if len(geometry) != 4 or any(type(value) is not int for value in geometry):
            raise ValueError("Overlay geometry must contain four integer physical pixels")
        if min(geometry[2:]) <= 0:
            raise ValueError("Overlay dimensions must be positive")
        self.geometry = tuple(geometry)
        # The injected spawn owns environment propagation and the Windows Job.
        self.camera_env = dict(camera_env or {})
        self.on_event = on_event
        self.process = None
        self.child_pid = None
        self.error = None
        self.covered = False
        self.busy = False
        self.token = uuid.uuid4().hex
        self.cycle = 0
        self._phase = "new"
        self._listener = None
        self._channel = None
        self._deadline = None
        self._action = None
        self._closed = False

    def _emit(self, event, **fields):
        if self.on_event is not None:
            try:
                self.on_event({"event": event, "cycle": self.cycle, **fields})
            except Exception:
                # Diagnostic consumers must not remove a cover or interrupt cleanup.
                pass

    def _send(self, command):
        if self._channel is None:
            raise SceneControlError("Overlay control channel is unavailable")
        self._channel.send({"command": command, "token": self.token, "cycle": self.cycle})

    def _fail(self, reason):
        if self.error is None:
            self.error = str(reason)
            self._emit("ERROR", reason=self.error)
            try:
                self._send("FAIL_CLOSED")
            except Exception:
                pass
        self.busy = True
        self._phase = "failed"
        self._deadline = None
        self._action = None

    def fail_closed(self, reason):
        """Retain the owned cover when scene termination cannot be confirmed."""
        self._fail(reason)

    def begin(self):
        if self.busy or self.error is not None or self._closed:
            return False
        self.busy = True
        self._action = None
        self.cycle += 1
        try:
            if self.process is None:
                self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._listener.bind(("127.0.0.1", 0))
                self._listener.listen(1)
                self._listener.setblocking(False)
                script = Path(__file__).resolve().with_name("transition_overlay.py")
                argv = [sys.executable, "-u", str(script), "--control-port",
                        str(self._listener.getsockname()[1]), "--token", self.token]
                for name, value in zip(("x", "y", "width", "height"), self.geometry):
                    argv.extend((f"--{name}", str(value)))
                self._phase = "starting"
                self._deadline = time.monotonic() + self.READY_TIMEOUT
                self.process = self.spawn(argv, cwd=str(script.parent))
            else:
                if self.process.poll() is not None:
                    raise SceneControlError("Overlay process has exited")
                self._request_cover()
            self._emit("BEGIN")
            return True
        except Exception as exc:
            self._fail(exc)
            return False

    def _request_cover(self):
        self.covered = False
        self._send("COVER")
        self._phase = "covering"
        self._deadline = time.monotonic() + self.COMMAND_TIMEOUT

    def reveal(self):
        if self.error is not None or self._phase != "covered" or not self.covered:
            return False
        try:
            self._send("REVEAL")
            self._phase = "revealing"
            self._deadline = time.monotonic() + self.COMMAND_TIMEOUT
            return True
        except Exception as exc:
            self._fail(exc)
            return False

    def _receive(self, message):
        if message.get("token") != self.token:
            raise SceneControlError("Overlay token mismatch")
        event = message.get("event")
        if event == "READY":
            pid = message.get("pid")
            if self._phase != "starting" or type(pid) is not int or pid <= 0:
                raise SceneControlError("Unexpected overlay READY/PID")
            job = get_scene_job(self.process)
            if pid != self.process.pid and not (job is not None and job.adopt_scene_pid(pid)):
                raise SceneControlError("Overlay PID is not an owned process")
            self.child_pid = pid
            self.process._scene_pid = pid
            self._request_cover()
        elif event == "COVERED" and message.get("emergency") is True:
            # Emergency acknowledgement is also emitted only after a full-cover flip.
            self.covered = True
            self._fail(str(message.get("reason", "Overlay entered emergency cover"))[:1000])
        elif event == "ERROR":
            self._fail(str(message.get("reason", "Overlay failed"))[:1000])
        elif self.error is not None:
            return
        elif event == "ACTION":
            if (self._phase == "idle" and not self.busy
                    and message.get("cycle") == self.cycle
                    and message.get("action") in ("next", "back")):
                if self._action is None:
                    self._action = message["action"]
        elif message.get("cycle") != self.cycle:
            raise SceneControlError("Overlay transition cycle mismatch")
        elif event == "COVERED" and self._phase == "covering":
            self.covered = True
            self._phase = "covered"
            # The scene controller owns its START/FIRST_FRAME deadline. Never uncover
            # a scene merely because the covered interval has become long.
            self._deadline = None
        elif event == "REVEALED" and self._phase == "revealing":
            self.covered = False
            self.busy = False
            self._phase = "idle"
            self._deadline = None
        else:
            raise SceneControlError(f"Unexpected overlay event: {event}")
        self._emit(event)

    def poll(self):
        if self.process is None or self._closed:
            return
        try:
            if self.process.poll() is not None:
                raise SceneControlError("Overlay exited unexpectedly")
            if self._channel is None and self._listener is not None:
                try:
                    connection, _address = self._listener.accept()
                except BlockingIOError:
                    connection = None
                if connection is not None:
                    self._channel = JsonChannel(connection)
                    self._listener.close()
                    self._listener = None
            if self._channel is not None:
                for message in self._channel.receive():
                    self._receive(message)
                if self._channel.eof:
                    raise SceneControlError("Overlay control connection closed")
            if self._deadline is not None and time.monotonic() >= self._deadline:
                raise SceneControlError(f"Overlay {self._phase} timeout")
        except Exception as exc:
            self._fail(exc)

    def consume_action(self):
        action, self._action = self._action, None
        if self.busy or self.error is not None or self._phase != "idle":
            return None
        return action

    def close(self):
        stopped = True
        try:
            if self.process is not None:
                try:
                    self._send("CLOSE")
                except Exception:
                    pass
                stopped = bool(self.stop(self.process, "transition_overlay", reason="overlay_shutdown"))
        except Exception as exc:
            stopped = False
            self._fail(exc)
        finally:
            for resource in (self._channel, self._listener):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        stopped = False
            self._channel = self._listener = None
        if stopped:
            self.process = None
            self.covered = self.busy = False
            self._closed = True
            self._phase = "closed"
        else:
            self._fail("Overlay could not be fully stopped")
        return stopped
