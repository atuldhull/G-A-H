"""Real-path detection, persistent sticky classification and guarded init logic."""

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from .classification import ClassificationError, RepoIdentity, SecurityStore
from .executables import pin_tools
from .types import Mode

SKIP = {".git", "node_modules", ".venv"}


def _canonical(path) -> Path:
    return Path(path).resolve()


def _present(path: Path) -> bool:
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _marker(parent: Path) -> bool:
    metadata = parent / ".crocodile"
    try:
        metadata.lstat()
    except FileNotFoundError:
        return False
    if metadata.is_symlink() or getattr(metadata, "is_junction", lambda: False)():
        return True  # redirected metadata cannot establish public classification
    if not metadata.is_dir():
        raise ClassificationError(".crocodile metadata is not a directory")
    try:
        (metadata / "confidential").lstat()
        return True
    except FileNotFoundError:
        return False


def repo_root(path: Path) -> Path:
    directory = path if path.is_dir() else path.parent
    for parent in (directory, *directory.parents):
        if _present(parent / ".git"):
            return parent
    return directory


def identity_for(root: Path) -> RepoIdentity:
    """Use the Phase 2 hardened reader for available Git identities, never a shell.

    Loose/unborn directories still have a canonical path identity. A real Git
    repository that cannot be audited does not silently lose its other identities.
    """
    root = root.resolve()
    identity = RepoIdentity(os.path.normcase(str(root)))
    gitdir = root / ".git"
    if _present(gitdir) and (
        not gitdir.is_dir()
        or gitdir.is_symlink()
        or getattr(gitdir, "is_junction", lambda: False)()
    ):
        raise ClassificationError(
            "linked Git worktree identity requires an owner adapter"
        )
    if not _present(gitdir / "HEAD"):
        if _present(gitdir / "config"):
            raise ClassificationError(
                "repository identity is inconclusive without Git HEAD"
            )
        return identity
    from .git import Git

    context = SimpleNamespace(
        repo_root=root,
        mode="confidential",
        _exe_pins=pin_tools(root),
        _git_disabled=False,
        events=[],
    )
    try:
        with Git(context) as git:
            git._audit()
            remote = git._config.get("remote.origin.url")
            result = git._call(["rev-list", "--max-parents=0", "--all"], timeout=15)
            if result.returncode:
                raise ClassificationError("cannot determine repository first commit")
            commits = sorted(line for line in result.stdout.splitlines() if line)
            first = commits[0] if commits else None
            return RepoIdentity(identity.realpath, first, remote)
    except (OSError, ValueError, RuntimeError) as error:
        raise ClassificationError("cannot audit repository identity") from error


@dataclass(frozen=True)
class Detection:
    mode: Mode
    root: Path
    identity: RepoIdentity
    denied_subtrees: tuple[Path, ...] = ()
    alerts: tuple[str, ...] = ()


class Detector:
    def __init__(
        self,
        store: SecurityStore | None = None,
        *,
        cap=50_000,
        identity_reader=identity_for,
    ):
        if type(cap) is not int or cap < 1:
            raise ValueError("scan cap must be a positive integer")
        self.store = store if store is not None else SecurityStore()
        self.cap = cap
        self.identity_reader = identity_reader

    def scan(self, root: Path) -> tuple[Path, ...]:
        found, pending, count = [], [root], 0
        while pending:
            directory = pending.pop()
            if directory != root and _marker(directory):
                found.append(directory)
                continue
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        count += 1
                        if count > self.cap:
                            raise ClassificationError(
                                "cannot prove no nested confidential subtree: use --confidential"
                            )
                        if entry.name in SKIP:
                            continue
                        path = Path(entry.path)
                        if (
                            entry.is_symlink()
                            or getattr(path, "is_junction", lambda: False)()
                        ):
                            if entry.is_dir():
                                raise ClassificationError(
                                    "nested scan encountered linked directory: use --confidential"
                                )
                        elif entry.is_dir(follow_symlinks=False):
                            pending.append(path)
            except OSError as error:
                raise ClassificationError(
                    "nested confidentiality scan is inconclusive: use --confidential"
                ) from error
        return tuple(sorted(found))

    def detect(
        self,
        repo_path,
        *,
        cwd=None,
        tool_paths=(),
        root=None,
        session_id=None,
        force_confidential=False,
    ) -> Detection:
        base = _canonical(cwd) if cwd is not None else Path.cwd().resolve()
        primary = _canonical(base / Path(repo_path))
        primary_root = (
            _canonical(base / Path(root)) if root is not None else repo_root(primary)
        )
        if not primary.is_relative_to(primary_root):
            raise ClassificationError(
                "declared repository root does not contain the target"
            )
        if self.store.path.resolve().is_relative_to(primary_root) or any(
            path.is_relative_to(primary_root) for path in self.store.journals
        ):
            raise ClassificationError(
                "classification state must live outside the target repository"
            )
        primary_identity = self.identity_reader(primary_root)
        paths = [
            primary,
            *([_canonical(cwd)] if cwd is not None else []),
            *(
                _canonical((base if cwd is not None else primary_root) / Path(path))
                for path in tool_paths
            ),
        ]
        for path in paths:
            start = path if path.is_dir() else path.parent
            markers = [parent for parent in (start, *start.parents) if _marker(parent)]
            point_root = (
                primary_root if path.is_relative_to(primary_root) else repo_root(path)
            )
            identity = (
                primary_identity
                if point_root == primary_root
                else self.identity_reader(point_root)
            )
            sticky = self.store.is_confidential(
                identity
            ) or self.store.path_is_confidential(start)
            if markers or sticky or force_confidential:
                # Nested markers belong to their subtree, not their public parent.
                chosen = (
                    markers[0]
                    if markers
                    and markers[0].is_relative_to(point_root)
                    and markers[0] != point_root
                    else point_root
                )
                if chosen != point_root:
                    identity = (
                        self.identity_reader(chosen)
                        if (chosen / ".git").exists()
                        else RepoIdentity(os.path.normcase(str(chosen)))
                    )
                _, history = self.store.history(identity)
                registered = any(
                    event["type"] == "registry" and identity.ids <= event["ids"]
                    for event in history
                )
                if (
                    not self.store.is_confidential(identity)
                    or not registered
                    or session_id
                ):
                    self.store.record(
                        identity,
                        "confidential",
                        kind="session_started"
                        if session_id
                        else "classification_detected",
                        session=session_id,
                    )
                alerts = (
                    (
                        "confidential classification retained after marker removal or repository change",
                    )
                    if sticky and not markers
                    else ()
                )
                return Detection("confidential", primary_root, identity, alerts=alerts)
        denied = self.scan(primary_root)
        for subtree in denied:
            identity = (
                self.identity_reader(subtree)
                if (subtree / ".git").exists()
                else RepoIdentity(os.path.normcase(str(subtree)))
            )
            if not self.store.is_confidential(identity):
                self.store.record(identity, "confidential")
        if session_id:
            self.store.record(
                primary_identity, "public", kind="session_started", session=session_id
            )
        return Detection("public", primary_root, primary_identity, denied)

    def guard(self, path, *, root: Path, mode: Mode):
        if mode == "confidential":
            return
        if mode != "public":
            raise ClassificationError("unknown confidentiality mode")
        point = _canonical(root / Path(path))
        if self.store.path_is_confidential(point):
            raise ClassificationError("path inside sticky confidential subtree")
        start = point if point.is_dir() else point.parent
        for parent in (start, *start.parents):
            if _marker(parent):
                raise ClassificationError("path inside confidential subtree")


def mode_for(
    repo_path,
    *,
    cwd=None,
    tool_paths=(),
    root=None,
    store=None,
    session_id=None,
    force_confidential=False,
) -> Mode:
    """Call before loading task text or choosing credentials; recheck each turn."""
    return (
        Detector(store)
        .detect(
            repo_path,
            cwd=cwd,
            tool_paths=tool_paths,
            root=root,
            session_id=session_id,
            force_confidential=force_confidential,
        )
        .mode
    )


def guard_public_path(path: Path, root: Path, *, store=None):
    Detector(store).guard(path, root=root, mode="public")


def set_classification(
    repo_path, *, confidential: bool, store=None, canary_source=None
) -> Detection:
    """Privileged init handler; only console confirmation may lower classification.

    No task/model-controlled flag may bypass this function. Crocodile self-command
    execution remains denied by cmd.run. Canary registration precedes file writes.
    """
    from .approvals import ApprovalDenied, _console_answer, escape
    from .paths import atomic_write, resolve_in_repo

    if type(confidential) is not bool:
        raise TypeError("confidential must be a boolean")
    detector = Detector(store)
    root = _canonical(repo_path)
    if not root.is_dir():
        raise ClassificationError("classification target must be a directory")
    if detector.store.path.resolve().is_relative_to(root) or any(
        path.is_relative_to(root) for path in detector.store.journals
    ):
        raise ClassificationError(
            "classification state must live outside the repository"
        )
    identity = detector.identity_reader(root)
    metadata = root / ".crocodile"
    if (
        metadata.is_symlink()
        or getattr(metadata, "is_junction", lambda: False)()
        or (metadata.exists() and not metadata.is_dir())
    ):
        raise ClassificationError("redirected init metadata refused")
    if not confidential:
        for parent in root.parents:
            if _marker(parent) or detector.store.is_confidential(
                RepoIdentity(os.path.normcase(str(parent)))
            ):
                raise ClassificationError(
                    "cannot clear a confidential ancestor from this repository"
                )
        # Ensure the journal survives a marker unlink or registry-row loss.
        if _marker(root) and not detector.store.is_confidential(identity):
            detector.store.record(identity, "confidential")
    source = (
        resolve_in_repo(str(canary_source), root, for_write=True, mode="confidential")
        if canary_source is not None
        else None
    )
    if source is not None and (
        not confidential
        or not source.is_file()
        or source.suffix not in (".py", ".js", ".ts", ".c", ".cpp", ".java", ".rs")
    ):
        raise ClassificationError(
            "optional canary comment requires a supported existing source file"
        )
    original = source.read_bytes() if source is not None else None
    marker = metadata / "confidential"
    before = (
        identity,
        marker.exists(),
        hashlib.sha256(original).hexdigest() if original is not None else None,
        repr(detector.store.history(identity)),
    )
    word = "confidential" if confidential else "public"
    nonce = f"{secrets.randbelow(100):02d}"
    preview = f"RED classification change: {word}\nrepo: {escape(str(root))}\n"
    aliases, _ = detector.store.history(identity)
    preview += (
        "\n".join("identity: " + escape(value) for value in sorted(aliases)[:50]) + "\n"
    )
    if len(aliases) > 50:
        preview += f"[+{len(aliases) - 50} identities omitted]\n"
    if source is not None:
        preview += "append canary comment to: " + escape(str(source)) + "\n"
    if not confidential:
        preview += (
            "This clears sticky classification for matching repository identities.\n"
        )
    try:
        answer = _console_answer(preview + f"Type {word} {nonce} to confirm: ").strip()
    except (OSError, EOFError, KeyboardInterrupt) as error:
        raise ApprovalDenied(
            "classification change requires an interactive console"
        ) from error
    if answer != f"{word} {nonce}":
        raise ApprovalDenied("classification change not confirmed")
    after = (
        detector.identity_reader(root),
        marker.exists(),
        hashlib.sha256(source.read_bytes()).hexdigest() if source is not None else None,
        repr(detector.store.history(identity)),
    )
    if (
        after != before
        or metadata.is_symlink()
        or getattr(metadata, "is_junction", lambda: False)()
    ):
        raise ApprovalDenied("classification inputs changed; confirm again")
    if confidential:
        token = "CANARY-" + secrets.token_hex(16)
        detector.store.record(
            identity,
            "confidential",
            kind="classification_changed",
            by="console",
            canary=(token, metadata / "canary"),
        )
        metadata.mkdir(exist_ok=True)
        for target, data in (
            (marker, b"confidential\n"),
            (metadata / "canary", (token + "\n").encode()),
        ):
            if target.is_symlink() or (
                target.exists() and (not target.is_file() or target.stat().st_nlink > 1)
            ):
                raise ClassificationError(
                    "linked init metadata refused; classification remains confidential"
                )
            target.write_bytes(data)
        if source is not None:
            prefix = b"#" if source.suffix == ".py" else b"//"
            atomic_write(
                str(source),
                original
                + b"\n"
                + prefix
                + b" Crocodile canary: "
                + token.encode()
                + b"\n",
                root=root,
                mode="confidential",
            )
    else:
        if marker.is_symlink() or (marker.exists() and not marker.is_file()):
            raise ClassificationError("non-file classification marker refused")
        marker.unlink(missing_ok=True)
        detector.store.record(
            identity, "public", kind="classification_changed", by="console"
        )
    return detector.detect(root, root=root)


def main(argv=None):
    """Part 3 CLI handler; Part 1 owns registration on the shared Typer app."""
    import argparse

    from .approvals import ApprovalDenied, escape
    from .classification import default_state_path

    parser = argparse.ArgumentParser(
        description="Inspect or interactively change repo classification"
    )
    parser.add_argument("command", choices=("mode", "init"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--state-db", type=Path, default=default_state_path())
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--confidential", action="store_true")
    mode.add_argument("--public", action="store_true")
    parser.add_argument("--canary-source")
    args = parser.parse_args(argv)
    store = SecurityStore(args.state_db)
    try:
        if args.command == "init":
            if not args.confidential and not args.public:
                parser.error("init requires --confidential or --public")
            result = set_classification(
                args.repo,
                confidential=args.confidential,
                store=store,
                canary_source=args.canary_source,
            )
        else:
            if args.public or args.canary_source:
                parser.error("mode does not accept --public or --canary-source")
            result = Detector(store).detect(
                args.repo, force_confidential=args.confidential
            )
        print(result.mode + ": " + escape(str(result.root)))
        for alert in result.alerts:
            print("RED: " + escape(alert))
        return 0
    except (ClassificationError, ApprovalDenied, OSError, ValueError) as error:
        print("REFUSED: " + escape(str(error)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
