"""Windows kill-on-close jobs; attach a suspended child before resuming it."""

import ctypes
import time
from ctypes import wintypes as w


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", w.DWORD),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_limit", w.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority", w.DWORD),
        ("scheduling", w.DWORD),
    ]


class IOCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_ops",
            "write_ops",
            "other_ops",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicLimits),
        ("io", IOCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class ThreadEntry(ctypes.Structure):
    _fields_ = [
        ("size", w.DWORD),
        ("usage", w.DWORD),
        ("tid", w.DWORD),
        ("pid", w.DWORD),
        ("base_priority", w.LONG),
        ("delta_priority", w.LONG),
        ("flags", w.DWORD),
    ]


class Accounting(ctypes.Structure):
    _fields_ = [
        ("user_time", ctypes.c_longlong),
        ("kernel_time", ctypes.c_longlong),
        ("period_user_time", ctypes.c_longlong),
        ("period_kernel_time", ctypes.c_longlong),
        ("page_faults", w.DWORD),
        ("total_processes", w.DWORD),
        ("active_processes", w.DWORD),
        ("terminated_processes", w.DWORD),
    ]


class Job:
    def __init__(self):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
            "SetInformationJobObject": (
                [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD],
                w.BOOL,
            ),
            "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
            "QueryInformationJobObject": (
                [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p],
                w.BOOL,
            ),
            "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "CreateToolhelp32Snapshot": ([w.DWORD, w.DWORD], w.HANDLE),
            "Thread32First": ([w.HANDLE, ctypes.POINTER(ThreadEntry)], w.BOOL),
            "Thread32Next": ([w.HANDLE, ctypes.POINTER(ThreadEntry)], w.BOOL),
            "OpenThread": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            "ResumeThread": ([w.HANDLE], w.DWORD),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway flags
        if not self.api.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def attach_and_resume(self, pid: int):
        process = self.api.OpenProcess(0x0100 | 0x0001, False, pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.api.CloseHandle(process)
        snapshot = self.api.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            more = self.api.Thread32First(snapshot, ctypes.byref(entry))
            while more:
                if entry.pid == pid:
                    thread = self.api.OpenThread(2, False, entry.tid)  # SUSPEND_RESUME
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        if self.api.ResumeThread(thread) == 0xFFFFFFFF:
                            raise ctypes.WinError(ctypes.get_last_error())
                        return
                    finally:
                        self.api.CloseHandle(thread)
                entry.size = ctypes.sizeof(entry)
                more = self.api.Thread32Next(snapshot, ctypes.byref(entry))
            raise OSError("suspended child's initial thread not found")
        finally:
            self.api.CloseHandle(snapshot)

    def terminate(self):
        if self.handle and not self.api.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            try:
                if not self.api.TerminateJobObject(handle, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
                accounting = Accounting()
                deadline = time.monotonic() + 5
                while True:
                    if not self.api.QueryInformationJobObject(
                        handle,
                        1,
                        ctypes.byref(accounting),
                        ctypes.sizeof(accounting),
                        None,
                    ):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if accounting.active_processes == 0:
                        break
                    if time.monotonic() >= deadline:
                        raise OSError(
                            "Windows job did not finish terminating within five seconds"
                        )
                    time.sleep(0.01)
            finally:
                if not self.api.CloseHandle(handle):
                    raise ctypes.WinError(ctypes.get_last_error())
