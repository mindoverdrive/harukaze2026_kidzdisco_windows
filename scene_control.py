"""Bounded localhost startup protocol; READY is distinct from first-frame success."""

import json
import os
import select
import socket
import time
import uuid
from windows_process import get_scene_job

MAX_MESSAGE_BYTES = 4096


class SceneControlError(RuntimeError):
    pass


class JsonChannel:
    def __init__(self, sock):
        self.sock = sock
        self.sock.setblocking(False)
        self.buffer = bytearray()
        self.eof = False

    def send(self, message):
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(payload) > MAX_MESSAGE_BYTES:
            raise SceneControlError("control message too large")
        self.sock.settimeout(0.5)
        try:
            self.sock.sendall(payload)
        finally:
            self.sock.setblocking(False)

    def receive(self):
        messages = []
        # Bound each poll so a child cannot monopolize Manager's UI loop.
        for _ in range(8):
            try:
                data = self.sock.recv(MAX_MESSAGE_BYTES)
            except BlockingIOError:
                break
            if not data:
                self.eof = True
                break
            self.buffer.extend(data)
            while b"\n" in self.buffer:
                line, _, remainder = self.buffer.partition(b"\n")
                self.buffer = bytearray(remainder)
                if len(line) >= MAX_MESSAGE_BYTES:
                    raise SceneControlError("control message too large")
                try:
                    message = json.loads(line)
                except (ValueError, UnicodeError) as exc:
                    raise SceneControlError("invalid control JSON") from exc
                if not isinstance(message, dict):
                    raise SceneControlError("control message must be an object")
                messages.append(message)
            if len(self.buffer) >= MAX_MESSAGE_BYTES:
                raise SceneControlError("unterminated control message too large")
        return messages

    def close(self):
        self.sock.close()


class SceneLaunchControl:
    """Manager side. poll() never waits for a child to initialize."""

    def __init__(self, ready_timeout=10.0, ack_timeout=5.0, frame_timeout=30.0, on_event=None):
        self.launch_id = uuid.uuid4().hex
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.listener.bind(("127.0.0.1", 0))
            self.listener.listen(1)
            self.listener.setblocking(False)
        except BaseException:
            self.listener.close()
            raise
        self.port = self.listener.getsockname()[1]
        self.channel = None
        self.state = "LAUNCHED"
        self.created_at = time.monotonic()
        self.started_at = None
        self.ready_timeout = float(ready_timeout)
        self.ack_timeout = float(ack_timeout)
        self.frame_timeout = float(frame_timeout)
        self.first_frame = None
        self.error = None
        self.child_pid = None
        self.on_event = on_event

    def argv(self):
        return ["--control-port", str(self.port), "--launch-id", self.launch_id]

    def _log(self, event, **fields):
        payload = {
            "event": event, "launch_id": self.launch_id,
            "elapsed_s": round(time.monotonic() - self.created_at, 3), **fields,
        }
        print("[SceneControl] " + json.dumps(payload), flush=True)
        if self.on_event is not None:
            self.on_event(payload)

    def poll(self, process):
        if self.state == "FAILED":
            raise SceneControlError(self.error)
        try:
            if process.poll() is not None:
                raise SceneControlError(f"child exited before promotion: code={process.returncode}")
            if self.channel is None:
                try:
                    connection, _address = self.listener.accept()
                except BlockingIOError:
                    connection = None
                if connection is not None:
                    self.channel = JsonChannel(connection)
                    self.listener.close()
            if self.channel is not None:
                for message in self.channel.receive():
                    pid = message.get("pid")
                    if message.get("launch_id") != self.launch_id or type(pid) is not int or pid <= 0:
                        raise SceneControlError("launch_id/PID mismatch")
                    if self.child_pid is None:
                        job = get_scene_job(process)
                        if pid != process.pid and not (job is not None and job.adopt_scene_pid(pid)):
                            raise SceneControlError("launch_id/PID mismatch: not an owned scene process")
                        self.child_pid = pid
                    elif pid != self.child_pid:
                        raise SceneControlError("launch_id/PID mismatch: child identity changed")
                    event = message.get("event")
                    if event == "ERROR":
                        raise SceneControlError(f"child error: {message.get('reason', 'unknown')}")
                    if event == "READY" and self.state == "LAUNCHED":
                        self.state = "READY"
                    elif event == "START_ACK" and self.state == "START_SENT":
                        self.state = "START_ACK"
                    elif event == "FIRST_FRAME" and self.state == "START_ACK":
                        frame_id = message.get("frame_id")
                        if type(frame_id) is not int or frame_id <= 0:
                            raise SceneControlError("FIRST_FRAME requires a positive camera frame_id")
                        self.first_frame = message
                        self.state = "FIRST_FRAME"
                    else:
                        raise SceneControlError(f"unexpected {event!r} in {self.state}")
                    self._log(event, pid=pid, launcher_pid=process.pid, frame_id=message.get("frame_id"))
                if self.channel.eof and self.state != "FIRST_FRAME":
                    raise SceneControlError("control connection closed before FIRST_FRAME")
            now = time.monotonic()
            if self.state == "LAUNCHED" and now - self.created_at >= self.ready_timeout:
                raise SceneControlError("READY timeout")
            if self.state == "START_SENT" and now - self.started_at >= self.ack_timeout:
                raise SceneControlError("START_ACK timeout")
            if self.state in {"START_SENT", "START_ACK"} and now - self.started_at >= self.frame_timeout:
                raise SceneControlError("FIRST_FRAME timeout")
        except (OSError, SceneControlError) as exc:
            self.error = str(exc)
            self.state = "FAILED"
            self._log("FAILED", pid=process.pid, reason=self.error)
            raise SceneControlError(self.error) from exc
        return self.state

    def start(self):
        if self.state != "READY":
            raise SceneControlError(f"START requires READY, got {self.state}")
        self.channel.send({"event": "START", "launch_id": self.launch_id})
        self.started_at = time.monotonic()
        self.state = "START_SENT"
        self._log("START")

    def close(self):
        if self.channel is not None:
            self.channel.close()
        self.listener.close()


class SceneChildControl:
    def __init__(self, port, launch_id):
        self.launch_id = launch_id
        self.first_frame_sent = False
        self.sample_started_at = None
        self.processed_frames = 0
        self.channel = JsonChannel(socket.create_connection(("127.0.0.1", port), timeout=10.0))

    def send(self, event, **fields):
        self.channel.send({"event": event, "launch_id": self.launch_id, "pid": os.getpid(), **fields})

    def wait_for_start(self):
        self.send("READY")
        while True:
            select.select([self.channel.sock], [], [], 0.25)
            for message in self.channel.receive():
                if message.get("launch_id") != self.launch_id or message.get("event") != "START":
                    raise SceneControlError("invalid START")
                self.send("START_ACK")
                return
            if self.channel.eof:
                raise SceneControlError("Manager disconnected while waiting for START")

    def first_frame(self, camera):
        if self.first_frame_sent:
            self.processed_frames += 1
            now = time.monotonic()
            elapsed = now - self.sample_started_at
            if elapsed >= 10.0:
                print("[SceneMetrics] " + json.dumps({"pid": os.getpid(), "launch_id": self.launch_id,
                      "processed_render_fps": self.processed_frames / elapsed, "sample_seconds": elapsed,
                      "frame_id": getattr(camera, "last_read_frame_id", None)}), flush=True)
                self.sample_started_at, self.processed_frames = now, 0
            return
        frame_id = getattr(camera, "last_read_frame_id", 0)
        if type(frame_id) is not int or frame_id <= 0:
            return
        self.send("FIRST_FRAME", frame_id=frame_id, shm_name=getattr(camera, "shm_name", None))
        self.first_frame_sent = True
        self.sample_started_at = time.monotonic()

    def close(self):
        self.channel.close()


_child_control = None


def notify_first_frame(camera, *, frame_processed=True):
    """Call only after successful camera processing AND the draw/present call."""
    if _child_control is not None and frame_processed:
        _child_control.first_frame(camera)
