"""Resolve and fingerprint inputs for approval and immediate pre-effect checks."""

import hashlib
import json
from dataclasses import dataclass

from .consent import SKIP, ConfigFile, discover
from .executables import resolve_pinned
from .paths import resolve_in_repo
from .provenance import sensitive_fields
from .session import ApprovalSession
from .types import Action


@dataclass(frozen=True)
class BoundAction:
    """Execute these resolved inputs instead of resolving original strings again."""

    digest: str
    argv: tuple[str, ...]
    cwd: str
    paths: tuple[str, ...]
    configs: tuple[ConfigFile, ...]
    steered_by: tuple[str, ...] = ()


def validate_schema(action: Action) -> None:
    if type(action) is not Action or action.kind not in (
        "write",
        "shell",
        "git",
        "test_consent",
        "network",
    ):
        raise ValueError("unknown action schema")
    for value in (action.cwd, action.diff, action.source, action.query, action.url):
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
    if action.kind == "network":
        if (
            not (action.query or action.url)
            or action.argv is not None
            or action.diff is not None
            or action.paths
            or action.replacements
        ):
            raise ValueError(
                "network actions require query/url without execution or edit fields"
            )
    elif action.query is not None or action.url is not None:
        raise ValueError("query/url fields are only valid on network actions")
    elif action.kind == "write":
        if action.diff is None or not action.paths or action.argv is not None:
            raise ValueError("writes require diff and paths, without argv")
    elif (
        not action.argv
        or not action.argv[0]
        or action.diff is not None
        or action.replacements
    ):
        raise ValueError("execution requires argv without edit fields")


def bind(action: Action, session: ApprovalSession) -> BoundAction:
    validate_schema(action)
    session.verify_integrity()
    session.refresh_confidentiality()
    root = session.repo_root.resolve(strict=True)
    cwd = resolve_in_repo(action.cwd, root, mode=session.mode)
    if not cwd.is_dir():
        raise ValueError("cwd must be a directory")
    targets = []
    previous_texts = []
    for raw in action.paths:
        path = resolve_in_repo(raw, root, cwd=cwd, for_write=True, mode=session.mode)
        if session.confidentiality is not None:
            session.confidentiality.guard(path, root=root, mode=session.mode)
        raw = path.read_bytes() if path.exists() else None
        targets.append(
            (str(path), hashlib.sha256(raw).hexdigest() if raw is not None else None)
        )
        if raw is not None and len(action.paths) == 1:
            previous_texts.append(raw.decode("utf-8", errors="replace"))
    argv = tuple(action.argv or ())
    exe_meta = None
    configs = ()
    if argv:
        exe = resolve_pinned(argv[0], root, cwd, session._exe_pins)
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
    steered = tuple(
        source.location
        for source in session.provenance.steered_by(
            sensitive_fields(action, previous_texts=previous_texts)
        )
    )
    if action.source and action.source not in steered:
        steered += (action.source,)
    payload = {
        "kind": action.kind,
        "original_argv": action.argv,
        "argv": argv,
        "diff": action.diff,
        "replacements": action.replacements,
        "source": action.source,
        "steered_by": steered,
        "query": action.query,
        "url": action.url,
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
    return BoundAction(
        digest, argv, str(cwd), tuple(p for p, _ in targets), configs, steered
    )
