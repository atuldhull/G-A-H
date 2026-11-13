"""Canonical repository paths and protected metadata checks for Part 1 tools."""

import os
import re
import tempfile
from pathlib import Path, PureWindowsPath

PROTECTED = {".git", ".crocodile", ".vscode", ".idea", ".claude", ".cursor"}
DEVICES = re.compile(
    r"^(?:con|prn|aux|nul|conin\$|conout\$|clock\$|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)",
    re.IGNORECASE,
)


def _normalise(raw: str) -> str:
    if not isinstance(raw, str) or not raw or any(ord(char) < 32 for char in raw):
        raise ValueError("invalid path string")
    windows = PureWindowsPath(raw)
    if raw.startswith(("\\\\", "//")) or windows.drive.startswith("\\\\"):
        raise ValueError("UNC and Windows device paths are refused")
    if windows.drive and not windows.root:
        raise ValueError("drive-relative paths are refused")
    for part in windows.parts[1:] if windows.drive else windows.parts:
        if ":" in part or DEVICES.match(part.rstrip(" .")):
            raise ValueError("device names and alternate data streams are refused")
    if os.name != "nt":
        # Reject Windows spellings even on CI, without changing POSIX semantics.
        return raw
    parts = []
    for part in windows.parts:
        if part in (windows.anchor, ".", ".."):
            parts.append(part)
        else:
            part = part.rstrip(" .")
            if not part:
                raise ValueError("empty Windows path component")
            parts.append(part)
    return str(Path(*parts))


def _protected(path: Path) -> bool:
    parts = [part.lower().rstrip(" .") for part in path.parts]
    return any(part in PROTECTED or part.startswith(".env") for part in parts) or any(
        part.endswith(".code-workspace") or part == "mcp.json" for part in parts
    )


def resolve_in_repo(
    raw: str | os.PathLike[str],
    root: Path,
    *,
    cwd: Path | None = None,
    for_write: bool = False,
    mode: str = "public",
) -> Path:
    """Resolve aliases and every intermediate link, then enforce containment.

    Writes also check lexical and resolved intermediate names, so links cannot
    disguise protected metadata. No filesystem effect is performed here.
    """
    root = Path(root).resolve(strict=True)
    base = Path(cwd).resolve(strict=True) if cwd is not None else root
    if not base.is_relative_to(root):
        raise ValueError("cwd outside repository")
    value = _normalise(os.fspath(raw))
    lexical = base / value
    candidate = lexical.resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("path outside repository")
    if mode not in ("public", "confidential"):
        raise ValueError("unknown confidentiality mode")
    if for_write and _protected(lexical):
        raise ValueError("protected target path")
    # Check every prefix, including a junction that resolves through .git then
    # returns to a normal-looking final path.
    for prefix in (lexical, *lexical.parents):
        if prefix == root.parent:
            break
        resolved = prefix.resolve()
        if resolved == root:
            break
        if not resolved.is_relative_to(root):
            raise ValueError("intermediate path outside repository")
        if for_write and _protected(resolved):
            raise ValueError("protected intermediate path")
    if mode == "public":
        for parent in (candidate, *candidate.parents):
            if (parent / ".crocodile" / "confidential").exists():
                raise ValueError("path inside confidential subtree")
            if parent == root:
                break
    if (
        for_write
        and candidate.exists()
        and (not candidate.is_file() or candidate.stat().st_nlink > 1)
    ):
        raise ValueError("write target must be a regular, singly-linked file")
    return candidate


def atomic_write(raw: str, data: bytes, *, root: Path, mode: str = "public") -> Path:
    """Owner hook: same-directory temp + replacement, with a final path check.

    Approval/pre-image revalidation remains the edit owner's responsibility.
    Parent directories must already exist. This is not command-side-effect undo.
    """
    target = resolve_in_repo(raw, root, for_write=True, mode=mode)
    descriptor, name = tempfile.mkstemp(dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if resolve_in_repo(raw, root, for_write=True, mode=mode) != target:
            raise ValueError("write target changed before replacement")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
