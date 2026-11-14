"""File-edit checkpoints in an independent, local-only shadow Git repository.

Part 1 must serialize prepare -> validate -> approved edit -> complete. No command
side effects or target Git index/history are captured. Types remain Part 3 local.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

from . import procs
from .approvals import escape
from .classification import ClassificationError
from .executables import resolve_pinned
from .paths import resolve_in_repo
from .session import ApprovalSession

MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_FILES = 1000


class UndoError(RuntimeError):
    """No silent fallback when a checkpoint cannot be verified."""


class UndoConflict(UndoError):
    def __init__(self, paths):
        self.paths = list(paths)
        super().__init__(
            "Undo conflict; preserved files: " + ", ".join(map(escape, paths))
        )


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _replace(path, data):
    descriptor, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class ShadowUndo:
    """Trusted owner API; storage/session are never model-supplied options.

    A checkpoint's expected post-state is supplied BEFORE editing. A pending or
    interrupted edit blocks further history changes until explicitly reconciled.
    Git is used only against the private shadow repository, including for reads.
    """

    def __init__(
        self,
        root: Path,
        *,
        storage: Path | None = None,
        session: ApprovalSession | None = None,
    ):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise UndoError("repository root must be a directory")
        self.session = session or ApprovalSession(self.root)
        if self.session.repo_root != self.root:
            raise UndoError("approval session belongs to another repository")
        key = _digest(os.path.normcase(str(self.root)).encode())
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
        raw = (
            Path(storage)
            if storage is not None
            else base / "crocodile" / "shadow" / key
        )
        self.storage = raw.absolute()
        # No linked storage ancestors, and no overlap in either direction.
        if any(
            p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
            for p in (self.storage, *self.storage.parents)
        ):
            raise UndoError("shadow storage must not traverse links")
        self.storage = self.storage.resolve()
        if self.storage.is_relative_to(self.root) or self.root.is_relative_to(
            self.storage
        ):
            raise UndoError(
                "shadow storage must be separate from the target repository"
            )
        self.storage.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.git_dir = self.storage / "git"
        self.ledger = self.storage / "history.json"
        self.pins = self.session._exe_pins
        with self._locked():
            if not self.ledger.exists():
                if self.git_dir.exists():
                    raise UndoError(
                        "unregistered shadow Git directory; preserve it for recovery"
                    )
                self._git(
                    ["init", "--bare", "--template=", str(self.git_dir)], initial=True
                )
                config = _digest((self.git_dir / "config").read_bytes())
                self._save(
                    {
                        "version": 1,
                        "root": str(self.root),
                        "config": config,
                        "entries": [],
                    }
                )
            self._load()

    @contextmanager
    def _locked(self):
        self.session.verify_integrity()
        path = self.storage / "operation.lock"
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise UndoError(
                "shadow operation locked; inspect interrupted owner before removing operation.lock"
            ) from error
        try:
            with os.fdopen(descriptor, "w") as stream:
                stream.write(str(os.getpid()))
            yield
        finally:
            path.unlink()

    def _save(self, value):
        _replace(self.ledger, _json(value).encode())

    def _load(self):
        try:
            if self.ledger.is_symlink() or self.ledger.stat().st_nlink != 1:
                raise ValueError("linked ledger")
            value = json.loads(self.ledger.read_text(encoding="utf-8"))
            if value["version"] != 1 or value["root"] != str(self.root):
                raise ValueError("wrong repository or schema")
            if not isinstance(value["entries"], list):
                raise TypeError("invalid entries")
            for entry in value["entries"]:
                if (
                    not re.fullmatch(r"[0-9a-f]{32}", entry["id"])
                    or not re.fullmatch(r"[0-9a-f]{40,64}", entry["commit"])
                    or entry["state"]
                    not in {"prepared", "applied", "restoring", "undone", "cancelled"}
                ):
                    raise ValueError("invalid entry")
            self._check_git(value["config"])
            return value
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise UndoError(
                "invalid shadow state; preserve storage for recovery"
            ) from error

    def _check_git(self, config):
        for item in (
            self.git_dir,
            self.git_dir / "config",
            self.git_dir / "objects",
            self.git_dir / "refs",
        ):
            if item.is_symlink() or (
                hasattr(item, "is_junction") and item.is_junction()
            ):
                raise UndoError("linked shadow Git metadata")
        if any(
            (self.git_dir / item).exists()
            for item in (
                "objects/info/alternates",
                "commondir",
                "config.worktree",
                "info/grafts",
            )
        ):
            raise UndoError("redirected shadow Git metadata")
        if _digest((self.git_dir / "config").read_bytes()) != config:
            raise UndoError("shadow Git configuration changed")

    def _git(self, arguments, *, worktree=None, initial=False):
        if not initial:
            value = json.loads(self.ledger.read_text(encoding="utf-8"))
            self._check_git(value["config"])
        exe = resolve_pinned("git", self.root, self.storage, self.pins)
        options = [str(exe), "--no-pager", "--literal-pathspecs"]
        settings = {
            "core.hooksPath": str(self.storage / "empty-hooks"),
            "core.fsmonitor": "false",
            "core.attributesFile": os.devnull,
            "core.autocrlf": "false",
            "core.safecrlf": "false",
            "commit.gpgsign": "false",
            "maintenance.auto": "false",
            "gc.auto": "0",
            "core.pager": "cat",
            "diff.external": "",
            "credential.helper": "",
            "protocol.allow": "never",
            "user.name": "Crocodile shadow",
            "user.email": "shadow@localhost",
            "core.logAllRefUpdates": "false",
        }
        hooks = self.storage / "empty-hooks"
        hooks.mkdir(exist_ok=True)
        if (
            hooks.is_symlink()
            or (hasattr(hooks, "is_junction") and hooks.is_junction())
            or any(hooks.iterdir())
        ):
            raise UndoError("shadow hooks directory must be empty")
        for key, value in settings.items():
            options.extend(["-c", f"{key}={value}"])
        if not initial:
            options.append(f"--git-dir={self.git_dir}")
        if worktree is not None:
            options.append(f"--work-tree={worktree}")
        result = procs.run(
            options + arguments,
            self.storage,
            root=self.storage,
            timeout=120,
            git_env=True,
        )
        if result.returncode:
            raise UndoError("shadow Git failed: " + escape(result.stderr))
        return result.stdout.strip()

    def _path(self, raw):
        self.session.refresh_confidentiality()
        path = resolve_in_repo(raw, self.root, for_write=True, mode=self.session.mode)
        if self.session.confidentiality is not None:
            self.session.confidentiality.guard(
                path, root=self.root, mode=self.session.mode
            )
        # Reject aliases even when their resolved target stays inside the repo.
        lexical = self.root / raw
        for prefix in (lexical, *lexical.parents):
            if prefix == self.root:
                break
            if prefix.is_symlink() or (
                hasattr(prefix, "is_junction") and prefix.is_junction()
            ):
                raise UndoError("undo does not follow file or directory links")
        if not path.parent.is_dir():
            raise UndoError("undo requires an existing parent directory")
        return path

    def _state(self, raw, *, content=False):
        path = self._path(raw)
        if not path.exists():
            return None
        before = path.stat()
        if before.st_size > MAX_FILE:
            raise UndoError("file exceeds checkpoint size limit")
        with path.open("rb") as stream:
            data = stream.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise UndoError("file exceeds checkpoint size limit")
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_mode,
        ):
            raise UndoError("file changed while reading checkpoint")
        value = {"sha256": _digest(data), "mode": stat.S_IMODE(after.st_mode)}
        if content:
            value["data"] = base64.b64encode(data).decode("ascii")
        return value

    @staticmethod
    def _signature(state):
        return None if state is None else {k: state[k] for k in ("sha256", "mode")}

    def _manifest(self, entry):
        try:
            data = json.loads(self._git(["show", f"{entry['commit']}:manifest.json"]))
            if data["root"] != str(self.root) or data["id"] != entry["id"]:
                raise ValueError("checkpoint identity mismatch")
            if not 0 < len(data["files"]) <= MAX_FILES:
                raise ValueError("invalid checkpoint file count")
            seen = set()
            for item in data["files"]:
                try:
                    path = self._path(item["path"])
                except (OSError, ValueError, UndoError) as error:
                    raise UndoConflict([item["path"]]) from error
                if path in seen:
                    raise ValueError("duplicate checkpoint path")
                seen.add(path)
                for side in ("before", "after"):
                    value = item[side]
                    if value is None:
                        continue
                    if not re.fullmatch(
                        r"[0-9a-f]{64}", value["sha256"]
                    ) or not isinstance(value["mode"], int):
                        raise ValueError("invalid file signature")
                    if side == "before":
                        blob = base64.b64decode(value["data"], validate=True)
                        if len(blob) > MAX_FILE or _digest(blob) != value["sha256"]:
                            raise ValueError("invalid preimage")
            return data
        except (ValueError, KeyError, TypeError) as error:
            raise UndoError("invalid shadow checkpoint") from error

    def prepare(
        self, changes: Mapping[str, bytes | None], *, reason: str, call_id: str
    ) -> str:
        """Capture preimages and intended postimages. None means delete.

        Existing permissions must be preserved by the edit owner. New files use
        0600 (0666 on Windows). Parents must exist; directory edits are unsupported.
        """
        if not isinstance(changes, Mapping) or not 0 < len(changes) <= MAX_FILES:
            raise UndoError("checkpoint requires 1..1000 explicit file changes")
        with self._locked():
            ledger = self._load()
            if any(e["state"] in {"prepared", "restoring"} for e in ledger["entries"]):
                raise UndoError("finish or reconcile the pending checkpoint first")
            files, seen, total = [], set(), 0
            for raw, data in changes.items():
                if not isinstance(raw, str) or (
                    data is not None and not isinstance(data, bytes)
                ):
                    raise TypeError("changes must map paths to bytes or None")
                path = self._path(raw)
                if path in seen or not path.parent.is_dir():
                    raise UndoError("duplicate target or missing parent directory")
                seen.add(path)
                relative = path.relative_to(self.root).as_posix()
                before = self._state(relative, content=True)
                total += (len(base64.b64decode(before["data"])) if before else 0) + (
                    len(data) if data else 0
                )
                if (data is not None and len(data) > MAX_FILE) or total > MAX_TOTAL:
                    raise UndoError("checkpoint exceeds size limit")
                mode = (
                    before["mode"] if before else (0o666 if os.name == "nt" else 0o600)
                )
                after = (
                    None if data is None else {"sha256": _digest(data), "mode": mode}
                )
                files.append({"path": relative, "before": before, "after": after})
            identifier = uuid.uuid4().hex
            manifest = {
                "id": identifier,
                "root": str(self.root),
                "reason": str(reason),
                "call_id": str(call_id),
                "files": files,
            }
            with tempfile.TemporaryDirectory(dir=self.storage) as directory:
                stage = Path(directory)
                (stage / "manifest.json").write_text(_json(manifest), encoding="utf-8")
                self._git(["read-tree", "--empty"])
                self._git(["add", "--all"], worktree=stage)
                tree = self._git(["write-tree"])
                commit = self._git(
                    ["commit-tree", tree, "-m", "Crocodile file checkpoint"]
                )
                self._git(["update-ref", f"refs/crocodile/{identifier}", commit])
            ledger["entries"].append(
                {"id": identifier, "commit": commit, "state": "prepared"}
            )
            self._save(ledger)
            return identifier

    def _entry(self, ledger, identifier):
        for entry in ledger["entries"]:
            if entry["id"] == identifier:
                return entry
        raise UndoError("unknown checkpoint")

    def _matches(self, manifest, side):
        conflicts = []
        for item in manifest["files"]:
            try:
                if self._state(item["path"]) != self._signature(item[side]):
                    conflicts.append(item["path"])
            except (OSError, ValueError, UndoError):
                conflicts.append(item["path"])
        if conflicts:
            raise UndoConflict(conflicts)

    def validate(self, identifier: str) -> None:
        """Immediately before the approved write, recheck ALL preimages."""
        with self._locked():
            entry = self._entry(self._load(), identifier)
            if entry["state"] != "prepared":
                raise UndoError("checkpoint is not pending")
            self._matches(self._manifest(entry), "before")

    def complete(self, identifier: str) -> None:
        """Verify exact intended postimages; never adopt a changed file as agent output."""
        with self._locked():
            ledger = self._load()
            entry = self._entry(ledger, identifier)
            if entry["state"] != "prepared":
                raise UndoError("checkpoint is not pending")
            manifest = self._manifest(entry)
            self._matches(manifest, "after")
            entry["state"] = "applied"
            self._save(ledger)
            self._invalidate()

    def cancel(self, identifier: str) -> None:
        """Cancel only if every preimage is still intact. Never discard partial edits."""
        with self._locked():
            ledger = self._load()
            entry = self._entry(ledger, identifier)
            if entry["state"] != "prepared":
                raise UndoError("checkpoint is not pending")
            self._matches(self._manifest(entry), "before")
            entry["state"] = "cancelled"
            self._save(ledger)

    def _invalidate(self):
        # Restored files can execute code too: invalidate all outstanding consent.
        self.session._consent = None
        self.session._permits.clear()
        self.session._edited_code = True
        self.session.events.append(
            {"event": "test_consent_invalidated", "reason": "file checkpoint"}
        )

    def list(self) -> list[dict]:
        with self._locked():
            ledger = self._load()
            return [dict(entry) for entry in reversed(ledger["entries"])]

    def _restore(self, item):
        raw, before = item["path"], item["before"]
        path = self._path(raw)
        expected = self._signature(item["after"])
        if before is None:
            if self._state(raw) != expected:
                raise UndoConflict([raw])
            path.unlink(missing_ok=True)
            return
        descriptor, name = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(base64.b64decode(before["data"]))
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, before["mode"])
            # Check again after staging bytes, immediately before atomic replace.
            if self._path(raw) != path or self._state(raw) != expected:
                raise UndoConflict([raw])
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def undo(self, steps: int = 1) -> list[str]:
        """User-invoked handler. Preflight the whole batch, then restore newest first.

        A restoring entry may be retried after an I/O interruption: each file must
        still equal its exact pre- or postimage. No force-overwrite option exists.
        """
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
            raise ValueError("undo steps must be a positive integer")
        with self._locked():
            ledger = self._load()
            if any(e["state"] == "prepared" for e in ledger["entries"]):
                raise UndoError(
                    "pending edit: complete or cancel its checkpoint before undo"
                )
            entries = [
                e
                for e in reversed(ledger["entries"])
                if e["state"] in {"applied", "restoring"}
            ]
            if len(entries) < steps:
                raise UndoError(
                    f"requested {steps} checkpoints; only {len(entries)} available"
                )
            selected = [(entry, self._manifest(entry)) for entry in entries[:steps]]
            virtual, conflicts = {}, []
            for entry, manifest in selected:
                for item in manifest["files"]:
                    raw = item["path"]
                    try:
                        current = virtual[raw] if raw in virtual else self._state(raw)
                        acceptable = [self._signature(item["after"])]
                        if entry["state"] == "restoring":
                            acceptable.append(self._signature(item["before"]))
                        if current not in acceptable:
                            conflicts.append(raw)
                        virtual[raw] = self._signature(item["before"])
                    except (OSError, ValueError, UndoError):
                        conflicts.append(raw)
            if conflicts:
                raise UndoConflict(sorted(set(conflicts)))
            restored = []
            for entry, manifest in selected:
                resuming = entry["state"] == "restoring"
                entry["state"] = "restoring"
                self._save(ledger)  # durable recovery marker BEFORE changing a file
                self._invalidate()
                for item in manifest["files"]:
                    raw, before = item["path"], item["before"]
                    current = self._state(raw)
                    if resuming and current == self._signature(before):
                        continue
                    if current != self._signature(item["after"]):
                        raise UndoConflict([raw])
                    self._restore(item)
                    if self._state(raw) != self._signature(before):
                        raise UndoConflict([raw])
                entry["state"] = "undone"
                self._save(ledger)
                restored.extend(item["path"] for item in manifest["files"])
            return list(dict.fromkeys(restored))


def snapshot(
    root: Path,
    reason: str,
    call_id: str,
    *,
    changes: Mapping[str, bytes | None],
    storage: Path | None = None,
    session: ApprovalSession | None = None,
) -> str:
    """Proposed owner contract: exact intended changes are mandatory, not inferred."""
    return ShadowUndo(root, storage=storage, session=session).prepare(
        changes, reason=reason, call_id=call_id
    )


def undo(
    root: Path,
    steps: int = 1,
    *,
    storage: Path | None = None,
    session: ApprovalSession | None = None,
) -> list[str]:
    return ShadowUndo(root, storage=storage, session=session).undo(steps)


def main(argv=None, *, session=None, storage=None) -> int:
    """Standalone handler pending Part 1 registration of `crocodile undo [N] --list`."""
    parser = argparse.ArgumentParser(description="Undo Crocodile file edits")
    parser.add_argument("steps", nargs="?", type=int, default=1)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    try:
        from .confidential import mode_for

        root = args.repo.resolve(strict=True)
        if session is None:
            session = ApprovalSession(root, mode=mode_for(root, root=root))
        manager = ShadowUndo(root, session=session, storage=storage)
        if args.list:
            for entry in manager.list():
                print(f"{entry['id']} {entry['state']}")
        else:
            for path in manager.undo(args.steps):
                print("Restored " + escape(path))
        return 0
    except (UndoError, OSError, ValueError, ClassificationError) as error:
        print(escape(str(error)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
