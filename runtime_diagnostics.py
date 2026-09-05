"""Bounded test logs and Windows process observations; never declares hardware stable."""
import codecs
import ctypes
from ctypes import wintypes as wt
from functools import lru_cache
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import threading
import time
import subprocess

from windows_process import _kernel, _check, get_scene_job


class _MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("page_faults", wt.DWORD)] + [
        (name, ctypes.c_size_t) for name in ("peak_working_set", "working_set", "peak_paged", "paged",
                                           "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile", "private")]


@lru_cache(maxsize=1)
def _metrics_api():
    kernel = _kernel()
    kernel.GetProcessHandleCount.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
    kernel.GetProcessHandleCount.restype = wt.BOOL
    kernel.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wt.BOOL
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_MemoryCounters), wt.DWORD]
    psapi.GetProcessMemoryInfo.restype = wt.BOOL
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetGuiResources.argtypes = [wt.HANDLE, wt.DWORD]
    user32.GetGuiResources.restype = wt.DWORD
    return kernel, psapi, user32


def process_sample(pid):
    result = {"pid": pid, "gpu_bytes": None}
    if os.name != "nt":
        return dict(result, unavailable="Windows counters only")
    kernel, psapi, user32 = _metrics_api()
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        return dict(result, unavailable=str(ctypes.WinError(ctypes.get_last_error())))
    try:
        memory = _MemoryCounters()
        memory.cb = ctypes.sizeof(memory)
        _check(psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb))
        handles = wt.DWORD()
        _check(kernel.GetProcessHandleCount(handle, ctypes.byref(handles)))
        creation, end, kernel_time, user_time = (wt.FILETIME() for _ in range(4))
        _check(kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in (creation, end, kernel_time, user_time))))
        ticks = lambda value: (value.dwHighDateTime << 32) | value.dwLowDateTime
        result.update(private_bytes=memory.private, working_set_bytes=memory.working_set,
                      handles=handles.value, cpu_seconds=(ticks(kernel_time) + ticks(user_time)) / 10_000_000,
                      creation_ticks=ticks(creation))
        for name, flag in (("gdi_objects", 0), ("user_objects", 1)):
            ctypes.set_last_error(0)
            value = user32.GetGuiResources(handle, flag)
            result[name] = None if not value and ctypes.get_last_error() else value
        return result
    except OSError as exc:
        return dict(result, unavailable=str(exc))
    finally:
        kernel.CloseHandle(handle)


class _StrictLogHandler(RotatingFileHandler):
    def handleError(self, record):
        raise OSError("Could not write the diagnostic log")


class RuntimeDiagnostics:
    def __init__(self, directory, config, max_bytes=5 * 1024 * 1024, backups=3):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.handler = _StrictLogHandler(self.directory / "runtime.jsonl", maxBytes=max_bytes,
                                        backupCount=backups, encoding="utf-8")
        try:
            self.output_handler = _StrictLogHandler(self.directory / "scene_output.jsonl", maxBytes=max_bytes,
                                                   backupCount=backups, encoding="utf-8")
        except BaseException:
            self.handler.close()
            raise
        self.readers = {}
        self.error = None
        self.started_at = time.monotonic()
        metadata = dict(config=config, python=os.sys.executable, python_version=os.sys.version,
                        physical_camera_tested=False, visual_tested=False)
        try:
            root = Path(__file__).resolve().parent
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=3, check=True)
            state = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=3, check=True)
            metadata.update(commit=head.stdout.strip(), dirty=bool(state.stdout.strip()))
        except (OSError, subprocess.SubprocessError) as exc:
            metadata["git_unavailable"] = str(exc)
        try:
            with (self.directory / "metadata.json").open("x", encoding="utf-8") as file:
                json.dump(metadata, file, ensure_ascii=False, indent=2)
            self.record("run_start")
        except BaseException:
            self.handler.close()
            self.output_handler.close()
            raise

    def record(self, event, **fields):
        message = json.dumps({"event": event, "elapsed_s": round(time.monotonic() - self.started_at, 3),
                              "wall_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **fields}, ensure_ascii=False)
        handler = self.output_handler if event.startswith("scene_output") else self.handler
        handler.handle(logging.LogRecord("runtime", logging.INFO, __file__, 0, message, (), None))

    def _reap_readers(self):
        self.readers = {pid: thread for pid, thread in self.readers.items() if thread.is_alive()}

    def capture_stdout(self, process):
        self._reap_readers()

        def drain():
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            try:
                while True:
                    chunk = process.stdout.read1(4096)
                    if not chunk:
                        break
                    if self.error is None:
                        try:
                            self.record("scene_output", launcher_pid=process.pid, text=decoder.decode(chunk))
                        except OSError as exc:
                            self.error = str(exc)
                if self.error is None:
                    tail = decoder.decode(b"", final=True)
                    if tail:
                        self.record("scene_output", launcher_pid=process.pid, text=tail)
                    self.record("scene_output_end", launcher_pid=process.pid)
            except Exception as exc:
                self.error = f"Scene output reader: {exc}"
            finally:
                process.stdout.close()

        thread = threading.Thread(target=drain, name=f"scene-log-{process.pid}", daemon=True)
        self.readers[process.pid] = thread
        thread.start()

    def sample(self, relay, scene_manager):
        if self.error:
            raise OSError(self.error)
        self._reap_readers()
        processes = [os.getpid()]
        if scene_manager is not None:
            for name in ("running_process", "preloaded_process", "transition_process", "uncontained_process"):
                process = getattr(scene_manager, name, None)
                if process is not None:
                    job = get_scene_job(process)
                    processes.extend(job.active_pids() if job is not None else [process.pid])
        last_frame_at = relay.last_success_at
        age = time.monotonic() - last_frame_at if last_frame_at is not None else None
        self.record("sample", processes=[process_sample(pid) for pid in sorted(set(processes))],
                    camera={"shm_name": relay.shm_name, "frame_id": relay.frame_id,
                            "age_s": age, "read_failures": relay.read_failures_total,
                            "reopen_attempts": relay.reopen_attempts, "last_error": relay.last_error,
                            "max_frame_gap_s": max(relay.max_frame_gap, age or 0)},
                    scene=scene_manager.current_scene_name if scene_manager else None,
                    running_pid=scene_manager.running_process.pid if scene_manager and scene_manager.running_process else None,
                    switch_pending=scene_manager.switch_pending if scene_manager else False,
                    switch_count=scene_manager.completed_switches if scene_manager else 0,
                    switch_error=scene_manager.last_switch_error if scene_manager else None)

    def close(self):
        unfinished = []
        for pid, thread in self.readers.items():
            thread.join(timeout=1)
            if thread.is_alive():
                unfinished.append(pid)
        if unfinished:
            self.error = f"Output readers still running for {unfinished}"
            return False
        self.handler.close()
        self.output_handler.close()
        self.readers.clear()
        return self.error is None
