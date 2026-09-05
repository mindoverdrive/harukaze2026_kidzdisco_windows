"""Own only the processes spawned for a scene, including Windows venv redirectors."""
import ctypes
from ctypes import wintypes as wt
import os
import time
from functools import lru_cache


class _BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                ("flags", wt.DWORD), ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t), ("active_limit", wt.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wt.DWORD), ("scheduling", wt.DWORD)]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", _BasicLimits), ("io", ctypes.c_ulonglong * 6),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("size", wt.DWORD), ("usage", wt.DWORD), ("pid", wt.DWORD),
                ("heap", ctypes.c_size_t), ("module", wt.DWORD), ("threads", wt.DWORD),
                ("parent_pid", wt.DWORD), ("priority", wt.LONG), ("flags", wt.DWORD),
                ("exe", wt.WCHAR * 260)]


@lru_cache(maxsize=1)
def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, wt.LPCWSTR], wt.HANDLE),
        "SetInformationJobObject": ([wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD], wt.BOOL),
        "QueryInformationJobObject": ([wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p], wt.BOOL),
        "AssignProcessToJobObject": ([wt.HANDLE, wt.HANDLE], wt.BOOL),
        "IsProcessInJob": ([wt.HANDLE, wt.HANDLE, ctypes.POINTER(wt.BOOL)], wt.BOOL),
        "TerminateJobObject": ([wt.HANDLE, wt.UINT], wt.BOOL),
        "OpenProcess": ([wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
        "CloseHandle": ([wt.HANDLE], wt.BOOL),
        "WaitForSingleObject": ([wt.HANDLE, wt.DWORD], wt.DWORD),
        "CreateToolhelp32Snapshot": ([wt.DWORD, wt.DWORD], wt.HANDLE),
        "Process32FirstW": ([wt.HANDLE, ctypes.POINTER(_ProcessEntry)], wt.BOOL),
        "Process32NextW": ([wt.HANDLE, ctypes.POINTER(_ProcessEntry)], wt.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    return kernel


def _check(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def _process_parents(kernel):
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents = {}
    try:
        entry = _ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        present = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            parents[entry.pid] = entry.parent_pid
            present = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(snapshot)
    return parents


def _is_descendant(kernel, pid, root_pid, parents=None):
    if parents is None:
        parents = _process_parents(kernel)
    seen = set()
    while pid and pid not in seen:
        if pid == root_pid:
            return True
        seen.add(pid)
        pid = parents.get(pid)
    return False


class WindowsSceneJob:
    def __init__(self, process):
        if os.name != "nt":
            raise OSError("Scene jobs require Windows")
        self.kernel = _kernel()
        self.handle = _check(self.kernel.CreateJobObjectW(None, None))
        self.root_pid = process.pid
        try:
            limits = _ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            _check(self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            # Popen's existing Windows handle identifies this exact launched process.
            _check(self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)))
            # Include interpreters already created by a fast native redirector,
            # before waiting for READY or risking a startup timeout.
            parents = _process_parents(self.kernel)
            for pid in parents:
                if pid != self.root_pid and _is_descendant(self.kernel, pid, self.root_pid, parents):
                    try:
                        self.adopt_scene_pid(pid)
                    except OSError as exc:
                        if getattr(exc, "winerror", None) != 87:  # Process already exited.
                            raise
        except BaseException:
            self.close()
            raise

    def adopt_scene_pid(self, pid):
        if type(pid) is not int or pid <= 0:
            return False
        access = 0x100000 | 0x1000 | 0x100 | 0x1  # synchronize, query, set quota, terminate
        process_handle = _check(self.kernel.OpenProcess(access, False, pid))
        try:
            if self.kernel.WaitForSingleObject(process_handle, 0) != 258:  # WAIT_TIMEOUT means alive
                return False
            inside = wt.BOOL()
            _check(self.kernel.IsProcessInJob(process_handle, self.handle, ctypes.byref(inside)))
            if inside.value:
                return True
            # A redirector may create the interpreter before Popen returns and
            # before the root is assigned. Adopt only a verified descendant.
            if not _is_descendant(self.kernel, pid, self.root_pid):
                return False
            _check(self.kernel.AssignProcessToJobObject(self.handle, process_handle))
            return True
        finally:
            self.kernel.CloseHandle(process_handle)

    def active_pids(self):
        if self.handle is None:
            return []
        count = 8
        pointer_size = ctypes.sizeof(ctypes.c_size_t)
        while count <= 4096:
            buffer = ctypes.create_string_buffer(8 + count * pointer_size)
            if self.kernel.QueryInformationJobObject(self.handle, 3, buffer, len(buffer), None):
                raw = buffer.raw
                returned = int.from_bytes(raw[4:8], "little")
                return [int.from_bytes(raw[8 + i * pointer_size:8 + (i + 1) * pointer_size], "little")
                        for i in range(returned)]
            if ctypes.get_last_error() != 234:  # ERROR_MORE_DATA
                raise ctypes.WinError(ctypes.get_last_error())
            count *= 2
        raise OSError("Unexpectedly large scene process tree")

    def is_alive(self):
        return bool(self.active_pids())

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while self.is_alive():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)
        return True

    def terminate(self):
        if self.handle is not None:
            _check(self.kernel.TerminateJobObject(self.handle, 1))

    def close(self):
        if getattr(self, "handle", None) is not None:
            _check(self.kernel.CloseHandle(self.handle))
            self.handle = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def get_scene_job(process):
    return vars(process).get("_scene_job") if process is not None else None
