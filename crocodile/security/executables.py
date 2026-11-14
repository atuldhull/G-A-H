"""Absolute executable resolution, sanitized search paths and session pins."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .paths import _normalise

PINNED_NAMES = ("git", "rg", "ruff", "python")


def safe_path(root: Path, cwd: Path) -> tuple[Path, ...]:
    result = []
    for entry in os.get_exec_path():
        path = Path(entry)
        if path.is_absolute():
            path = path.resolve()
            if (
                path.is_dir()
                and not path.is_relative_to(root)
                and not path.is_relative_to(cwd)
                and path not in result
            ):
                result.append(path)
    return tuple(result)


def resolve_exe(name: str, root: Path, cwd: Path) -> Path:
    if not isinstance(name, str) or not name or any(ord(c) < 32 for c in name):
        raise ValueError("invalid executable name")
    name = _normalise(name)
    candidate = Path(name)
    if not candidate.is_absolute():
        if candidate.name != name:
            raise ValueError("relative executable paths are refused")
        extensions = (
            ("",)
            if os.name != "nt" or candidate.suffix
            else (".exe", ".com", ".bat", ".cmd")
        )
        found = [
            directory / (name + ext)
            for directory in safe_path(root, cwd)
            for ext in extensions
        ]
        candidate = next(
            (p for p in found if p.is_file() and os.access(p, os.X_OK)), None
        )
        if candidate is None:
            raise ValueError("executable not found outside repository")
    candidate = candidate.resolve(strict=True)
    if (
        candidate.is_relative_to(root)
        or candidate.is_relative_to(cwd)
        or not candidate.is_file()
    ):
        raise ValueError("executable must be a file outside repository and cwd")
    if os.name == "nt" and candidate.suffix.lower() not in (
        ".exe",
        ".com",
        ".bat",
        ".cmd",
    ):
        raise ValueError("unsupported Windows executable type")
    if candidate.stem.lower() == "crocodile":
        raise ValueError("Crocodile cannot invoke itself")
    return candidate


@dataclass(frozen=True)
class ExecutablePin:
    path: Path
    size: int
    mtime_ns: int

    @classmethod
    def capture(cls, path: Path):
        stat = path.stat()
        return cls(path, stat.st_size, stat.st_mtime_ns)


def pin_tools(root: Path) -> dict[str, ExecutablePin | None]:
    pins = {}
    for name in PINNED_NAMES:
        try:
            path = resolve_exe(sys.executable if name == "python" else name, root, root)
            pins[name] = ExecutablePin.capture(path)
        except (OSError, ValueError):
            pins[name] = None  # unavailable until a new session; no late PATH lookup
    return pins


def resolve_pinned(name: str, root: Path, cwd: Path, pins: dict) -> Path:
    name = _normalise(name)
    key = Path(name).stem.lower()
    if key in pins:
        pin = pins[key]
        if pin is None:
            raise ValueError(f"{key} was unavailable at session start")
        if Path(name).is_absolute() and Path(name).resolve() != pin.path:
            raise ValueError(f"{key} differs from its session pin")
        path = resolve_exe(str(pin.path), root, cwd)
        if ExecutablePin.capture(path) != pin:
            raise ValueError(f"{key} executable changed since session start")
        return path
    return resolve_exe(name, root, cwd)
