"""The only Part 3 process-spawn boundary: allowlisted env and tree cleanup."""

import math
import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from .executables import safe_path
from .paths import resolve_in_repo
from .types import CmdResult


def child_environment(root: Path, cwd: Path, scratch: Path) -> dict[str, str]:
    env = {}
    if os.name == "nt":
        systemroot = str(Path(os.environ["SYSTEMROOT"]).resolve(strict=True))
        env.update(
            {
                "SYSTEMROOT": systemroot,
                "WINDIR": systemroot,
                "COMSPEC": str(Path(systemroot, "System32", "cmd.exe")),
            }
        )
    env.update(
        {
            "PATH": os.pathsep.join(str(path) for path in safe_path(root, cwd)),
            "PATHEXT": ".COM;.EXE;.BAT;.CMD",
            "PYTHONUTF8": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "NoDefaultCurrentDirectoryInExePath": "1",
        }
    )
    for name in (
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
        "HOME",
        "HOMEPATH",
        "TEMP",
        "TMP",
        "TMPDIR",
    ):
        env[name] = str(scratch)
    env["HOMEDRIVE"] = scratch.drive
    return env


def run(
    argv: list[str],
    cwd: Path,
    *,
    root: Path,
    timeout: float,
    before_spawn: Callable[[], None] | None = None,
    git_env: bool = False,
) -> CmdResult:
    """Internal runner; callers enforce approval/templates. No model env overrides.

    File-backed output avoids hangs from descendants inheriting pipe handles.
    Windows children start suspended and are job-assigned before resumption.
    """
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(arg, str) or "\0" in arg for arg in argv)
    ):
        raise ValueError("argv must be a non-empty list of NUL-free strings")
    if not Path(argv[0]).is_absolute():
        raise ValueError("runner requires a resolved executable")
    root = Path(root).resolve(strict=True)
    cwd = resolve_in_repo(cwd, root, mode="confidential")
    exe = Path(argv[0]).resolve(strict=True)
    if not cwd.is_dir() or exe.is_relative_to(root) or exe.is_relative_to(cwd):
        raise ValueError("invalid process executable or cwd")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("timeout must be positive and finite")
    local = os.environ.get("LOCALAPPDATA")
    parent = (
        Path(local) / "crocodile" / "sbx"
        if os.name == "nt" and local
        else Path(tempfile.gettempdir()) / "crocodile-sbx"
    )
    if parent.resolve().is_relative_to(root):
        raise ValueError("scratch profile must be outside the repository")
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as directory:
        scratch = Path(directory)
        env = child_environment(root, cwd, scratch)
        if git_env:
            env.update(
                {
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_OPTIONAL_LOCKS": "0",
                    "GIT_ATTR_NOSYSTEM": "1",
                    "GIT_LFS_SKIP_SMUDGE": "1",
                }
            )
        job = None
        process = None
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            try:
                flags = 0
                if os.name == "nt":
                    from .windows_job import Job

                    job = Job()
                    flags = (
                        subprocess.CREATE_NO_WINDOW
                        | subprocess.CREATE_NEW_PROCESS_GROUP
                        | 4
                    )
                if before_spawn:
                    before_spawn()
                deadline = time.monotonic() + timeout
                process = subprocess.Popen(
                    argv,
                    cwd=cwd,
                    env=env,
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    close_fds=True,
                    creationflags=flags,
                    start_new_session=os.name != "nt",
                )
                if job:
                    job.attach_and_resume(process.pid)
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except BaseException:
                if job:
                    job.terminate()
                if process is not None:
                    if os.name != "nt":
                        _kill_group(process.pid)
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                raise
            finally:
                if (
                    process is not None
                    and os.name == "nt"
                    and process.returncode is not None
                ):
                    # CPython retains this native handle until object destruction.
                    # Release it before waiting for job accounting to drain.
                    process._handle.Close()
                if job:
                    job.close()
                if process is not None and os.name != "nt":
                    _kill_group(process.pid)
            stdout.seek(0)
            stderr.seek(0)
            return CmdResult(
                argv.copy(),
                process.returncode,
                stdout.read().decode("utf-8", errors="replace"),
                stderr.read().decode("utf-8", errors="replace"),
            )


def _kill_group(pid: int):
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
