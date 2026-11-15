"""Bounded metadata-only failure evidence; never read exercise file contents."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from bench.prepare import WorkspaceEntryError


MAX_ENTRIES = 2000
MAX_DEPTH = 32
STAGES = {
    "plan-config", "probe", "prepare-original", "prepare-workspace", "launch-evidence",
    "process", "receipt", "final-copy", "grading",
}


def relative_name(path, root):
    """No link resolution or absolute/outside paths; unsafe components get IDs."""
    try:
        relative = Path(path).absolute().relative_to(Path(root).absolute())
    except (TypeError, ValueError):
        return None
    if any(part == ".." for part in relative.parts):
        return None
    parts = []
    for part in relative.parts:
        unsafe = (not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", part)
                  or re.search(r"sk-|gh[pousr]_|github_pat_|AKIA|tvly-|token|secret|password|credential|prompt|payload|api.?key",
                               part, re.IGNORECASE)
                  or len(part) > 48 or bool(re.fullmatch(r"[A-Za-z0-9_-]{24,}", part)))
        parts.append("[name-" + hashlib.sha256(part.encode("utf-8", "surrogatepass")).hexdigest()[:12] + "]"
                     if unsafe else part)
    return "/".join(parts) or "."


def _kind(metadata):
    if stat.S_ISLNK(metadata.st_mode):
        return "symlink"
    if getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
        return "reparse-point"
    if stat.S_ISDIR(metadata.st_mode):
        return "directory"
    if stat.S_ISREG(metadata.st_mode):
        return "file"
    return "special-file"


def inventory(root):
    """Best-effort lstat inventory; skip links/reparse points and never open files.

    Not an atomic snapshot or containment guarantee against concurrent mutation.
    An incomplete/capped inventory is explicitly marked, never silently complete.
    """
    root = Path(root).absolute()
    result = {"entries": [], "complete": True, "limit": MAX_ENTRIES,
              "file_contents_captured": False, "link_targets_captured": False}
    pending = [(root, 0)]
    while pending:
        current, depth = pending.pop()
        if len(result["entries"]) >= MAX_ENTRIES:
            result["complete"] = False
            break
        try:
            metadata = current.lstat()
            kind = _kind(metadata)
            row = {"path": relative_name(current, root), "kind": kind}
            if kind == "file":
                row["bytes"] = metadata.st_size
            result["entries"].append(row)
            if kind != "directory":
                continue
            if depth >= MAX_DEPTH:
                result["complete"] = False
                continue
            # A resolved-parent containment check supplements lstat. No entry
            # marked link/reparse is traversed; no readlink/target is serialized.
            if not current.resolve().is_relative_to(root):
                result["complete"] = False
                continue
            children = []
            with os.scandir(current) as stream:
                for entry in stream:
                    if len(children) + len(result["entries"]) >= MAX_ENTRIES:
                        result["complete"] = False
                        break
                    children.append(Path(entry.path))
            pending.extend((child, depth + 1) for child in sorted(children, reverse=True))
        except (OSError, ValueError):
            result["complete"] = False
            name = relative_name(current, root)
            if result["entries"] and result["entries"][-1]["path"] == name:
                result["entries"][-1]["error"] = "unavailable"
            elif len(result["entries"]) < MAX_ENTRIES:
                result["entries"].append({"path": name, "kind": "unavailable"})
    return result


def safe_error(error, stage, roots):
    """Allowlisted messages, not regex-only redaction of arbitrary exception text."""
    stage = stage if stage in STAGES else "unknown"
    result = {"type": type(error).__name__[:80], "stage": stage,
              "message": "Operation failed; raw exception text omitted to protect task and credential data.",
              "reason": "unclassified", "relative_path": None, "path_scope": None}
    path = None
    if isinstance(error, WorkspaceEntryError):
        result.update(message=error.MESSAGES[error.reason], reason=error.reason)
        path = error.path
    elif isinstance(error, OSError):
        result.update(message="Filesystem operation failed.", reason="filesystem-error", errno=error.errno)
        path = error.filename
    elif isinstance(error, json.JSONDecodeError):
        result.update(message="JSON evidence could not be decoded.", reason="invalid-json")
    for scope, root in roots.items():
        if path is not None and root is not None:
            name = relative_name(path, root)
            if name is not None:
                result.update(relative_path=name, path_scope=scope)
                break
    # Source filenames/line numbers only: no source lines, locals, messages or
    # chained exception payloads. This preserves the actual raise path next time.
    frames, trace = [], error.__traceback__
    package = Path(__file__).resolve().parent
    while trace is not None:
        name = relative_name(trace.tb_frame.f_code.co_filename, package)
        if name is not None and len(frames) < 16:
            frames.append({"module": name, "line": trace.tb_lineno})
        trace = trace.tb_next
    result["bench_frames"] = frames
    return result


def capture(row, artifacts, workspace, state, error, roots):
    detail = safe_error(error, state["stage"], roots)
    row["diagnostic_error"] = detail
    row["evidence"]["failure_inventory"] = None
    try:
        evidence = {"schema_version": 1, "kind": "mini-failure-inventory", "error": detail,
                    "workspace": inventory(workspace) if workspace is not None else None,
                    "capture_timing": "before temporary workspace cleanup" if workspace is not None else "no workspace",
                    "notice": "Metadata only; not an executable snapshot or independent grade."}
        path = Path(artifacts) / "failure-inventory.json"
        with path.open("xb") as stream:
            stream.write((json.dumps(evidence, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        row["evidence"]["failure_inventory"] = str(path)
    except (OSError, ValueError, RecursionError) as capture_error:
        detail["inventory_capture_error"] = type(capture_error).__name__


@contextmanager
def before_cleanup(row, artifacts, workspace, state, roots):
    try:
        yield
    except BaseException as error:
        capture(row, artifacts, workspace, state, error, roots)
        raise
