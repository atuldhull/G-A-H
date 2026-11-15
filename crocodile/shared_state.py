"""Shared Part 1/2/3 state location contract; resolution never creates or migrates data."""

import os
from pathlib import Path


class StateLocationError(RuntimeError):
    pass


def _absolute(path):
    path = Path(path)
    if not path.is_absolute():
        raise StateLocationError("state database paths must be absolute")
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)):
        raise StateLocationError("linked state database paths are refused")
    return path.resolve()


def historical_state_paths():
    if os.name == "nt":
        roots = [os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")]
        if not roots[0]:
            raise StateLocationError("APPDATA is required for the canonical state location")
        paths = [_absolute(Path(root) / "crocodile/state.db") for root in roots if root]
    else:
        base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state"
        paths = [_absolute(Path(base) / "crocodile/state.db")]
    return tuple(dict.fromkeys(paths))


def resolve_state_path(path=None):
    """Explicit fixture/CLI paths win; an env override must not hide existing state.

    Fresh Windows default is APPDATA. A sole legacy LOCALAPPDATA DB is retained
    in place, including WAL state. Two candidates are ambiguous, even if one is
    empty. No copying, merging, automatic enrollment or deletion occurs here.
    """
    if path is not None:
        return _absolute(path)
    candidates = historical_state_paths()
    existing = []
    for candidate in candidates:
        if candidate.exists():
            if not candidate.is_file():
                raise StateLocationError("state database is not a regular file")
            existing.append(candidate)
        elif any(Path(str(candidate) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise StateLocationError("orphaned state journal found; recover existing state before startup")
    override = os.environ.get("CROCODILE_STATE_DB")
    if override:
        selected = _absolute(override)
        if not selected.exists() and existing:
            raise StateLocationError(
                "state override is missing while historical state exists; select the existing database"
            )
        if selected.exists() and not selected.is_file():
            raise StateLocationError("state database is not a regular file")
        return selected
    if len(existing) > 1:
        raise StateLocationError(
            "both APPDATA and LOCALAPPDATA state databases exist; review them and set CROCODILE_STATE_DB to the chosen existing database"
        )
    return existing[0] if existing else candidates[0]
