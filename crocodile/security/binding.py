"""Resolve and fingerprint inputs for approval and immediate pre-effect checks."""

import hashlib
import json
import os
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from .consent import SKIP, ConfigFile, discover
from .session import ApprovalSession
from .types import Action

PROTECTED = {".git", ".crocodile", ".vscode", ".idea", ".claude", ".cursor"}


@dataclass(frozen=True)
class BoundAction:
    """Execute these resolved inputs instead of resolving original strings again."""

    digest: str
    argv: tuple[str, ...]
    cwd: str
    paths: tuple[str, ...]
    configs: tuple[ConfigFile, ...]


def validate_schema(action: Action) -> None:
    if type(action) is not Action or action.kind not in (
        "write",
        "shell",
        "git",
        "test_consent",
    ):
        raise ValueError("unknown action schema")
    for value in (action.cwd, action.diff, action.source):
        if value is not None and (not isinstance(value, str) or "\0" in value):
            raise ValueError("invalid string field")
    if not isinstance(action.cwd, str):
        raise TypeError("cwd is required")
    for values in (
        action.paths,
        action.replacements,
        action.argv if action.argv is not None else [],
    ):
        if not isinstance(values, list) or any(
            not isinstance(v, str) or "\0" in v for v in values
        ):
            raise ValueError("invalid list field")
    if action.kind == "write":
        if action.diff is None or not action.paths or action.argv is not None:
            raise ValueError("writes require diff and paths, without argv")
    elif (
        not action.argv
        or not action.argv[0]
        or action.diff is not None
        or action.replacements
    ):
        raise ValueError("execution requires argv without edit fields")


def resolve_exe(name: str, root: Path, cwd: Path) -> Path:
    candidate = Path(name)
    if not candidate.is_absolute():
        if candidate.parent != Path("."):
            raise ValueError("relative executable paths are refused")
        candidates = []
        extensions = [""]
        if os.name == "nt" and not candidate.suffix:
            extensions = [
                ext.lower()
                for ext in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(
                    os.pathsep
                )
                if ext.startswith(".") and ext[1:].isalnum()
            ]
        for entry in os.get_exec_path():
            path = Path(entry)
            if (
                path.is_absolute()
                and not path.resolve().is_relative_to(root)
                and not path.resolve().is_relative_to(cwd)
            ):
                candidates.extend(path / (name + ext) for ext in extensions)
        # Do not use shutil.which: Windows may prepend the current directory.
        resolved = next(
            (
                path
                for path in candidates
                if path.is_file() and os.access(path, os.X_OK)
            ),
            None,
        )
        if resolved is None:
            raise ValueError("executable not found outside repository")
        candidate = resolved
    candidate = candidate.resolve(strict=True)
    if (
        candidate.is_relative_to(root)
        or candidate.is_relative_to(cwd)
        or not candidate.is_file()
    ):
        raise ValueError("executable must be a file outside repository and cwd")
    if candidate.stem.lower() == "crocodile":
        raise ValueError("Crocodile cannot invoke itself")
    return candidate


def bind(action: Action, session: ApprovalSession) -> BoundAction:
    validate_schema(action)
    root = session.repo_root.resolve(strict=True)
    cwd = (root / action.cwd).resolve(strict=True)
    if not cwd.is_relative_to(root) or not cwd.is_dir():
        raise ValueError("cwd outside repository")
    targets = []
    for raw in action.paths:
        lexical = Path(raw)
        if any(part.rstrip(" .").lower() in PROTECTED for part in lexical.parts):
            raise ValueError("protected target path")
        path = (cwd / raw).resolve()
        if not path.is_relative_to(root):
            raise ValueError("target outside repository")
        relative = path.relative_to(root)
        parts = [part.lower().rstrip(" .") for part in relative.parts]
        if (
            any(p in PROTECTED or p.startswith(".env") for p in parts)
            or fnmatchcase(path.name.lower(), "*.code-workspace")
            or path.name.lower() == "mcp.json"
        ):
            raise ValueError("protected target path")
        if path.exists() and (not path.is_file() or path.stat().st_nlink > 1):
            raise ValueError("target must be a regular, singly-linked file")
        targets.append(
            (
                str(path),
                hashlib.sha256(path.read_bytes()).hexdigest()
                if path.exists()
                else None,
            )
        )
    argv = tuple(action.argv or ())
    exe_meta = None
    configs = ()
    if argv:
        exe = resolve_exe(argv[0], root, cwd)
        if exe.suffix.lower() in (".bat", ".cmd") and any(
            any(c in arg for c in '&|<>^%"\n\r') for arg in argv[1:]
        ):
            raise ValueError("unsafe batch-file arguments")
        stat = exe.stat()
        exe_meta = (str(exe), stat.st_size, stat.st_mtime_ns)
        argv = (str(exe), *argv[1:])
        if action.kind == "test_consent":
            args = list(argv[1:])
            if not exe.stem.lower().startswith("python") or "-m" not in args:
                raise ValueError("test consent requires a Python -m pytest invocation")
            index = args.index("-m")
            if args[:index] not in ([], ["-I"], ["-B"], ["-I", "-B"]) or args[
                index + 1 : index + 2
            ] != ["pytest"]:
                raise ValueError("invalid pytest interpreter arguments")
            if not any(
                args[i : i + 2] == ["-p", "no:cacheprovider"] for i in range(len(args))
            ):
                raise ValueError("pytest must disable its cache provider")
            if any(
                arg.startswith(
                    (
                        "-c",
                        "--rootdir",
                        "--confcutdir",
                        "--override-ini",
                        "-o",
                        "@",
                        "--pyargs",
                        "--config-file",
                        "--noconftest",
                    )
                )
                for arg in args[index + 2 :]
            ):
                raise ValueError(
                    "pytest config overrides are not supported for consent"
                )
            for arg in args[index + 2 :]:
                # Test ids can carry ::node suffixes. All path-bearing selectors
                # must stay inside the inventory and outside skipped directories.
                selector = arg.split("::", 1)[0]
                if not arg.startswith("-") and (
                    "/" in selector
                    or "\\" in selector
                    or selector.endswith(".py")
                    or selector in (".", "..")
                    or selector.lower() in SKIP
                ):
                    path = (cwd / selector).resolve()
                    if not path.is_relative_to(root) or any(
                        part.lower() in SKIP for part in path.relative_to(root).parts
                    ):
                        raise ValueError(
                            "test selector lies outside the static config inventory"
                        )
            configs = discover(root, cwd)
    payload = {
        "kind": action.kind,
        "original_argv": action.argv,
        "argv": argv,
        "diff": action.diff,
        "replacements": action.replacements,
        "source": action.source,
        "exe": exe_meta,
        "cwd": str(cwd),
        "paths": targets,
        "root": str(root),
        "mode": session.mode,
        "yes_green": session.yes_green,
        "edited_code": session._edited_code,
        "configs": [(cfg.path, cfg.sha256) for cfg in configs],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return BoundAction(digest, argv, str(cwd), tuple(p for p, _ in targets), configs)
