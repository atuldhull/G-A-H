"""Phase 0 argv-only subprocess stub for trusted integration fixtures.

Not a security boundary: approvals, executable/path checks, environment
hardening, job objects, and integrity checks are deferred to later phases.
"""

import math
import os
import subprocess

from .types import CmdResult


def run(argv: list[str], cwd: str | os.PathLike[str], *, timeout: float) -> CmdResult:
    """Run an argv list without a shell, capturing output and exit status.

    The caller must obtain approval first. TimeoutExpired and OSError propagate;
    a nonzero child exit is returned normally. No policy is applied in Phase 0.
    """
    if not isinstance(argv, list) or not argv:
        raise TypeError("argv must be a non-empty list of strings")
    if any(not isinstance(arg, str) or "\0" in arg for arg in argv):
        raise ValueError("argv entries must be strings without NUL characters")
    if not argv[0]:
        raise ValueError("argv[0] must not be empty")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise TypeError("timeout must be a positive finite number")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number")
    args = argv.copy()
    result = subprocess.run(
        args,
        cwd=cwd,
        timeout=timeout,
        shell=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return CmdResult(args, result.returncode, result.stdout, result.stderr)
