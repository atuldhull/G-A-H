"""Part 1 lifecycle binding to Part 3; no implicit enrollment or replayed permits."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from pathlib import Path

from .security.classification import SecurityStore, default_state_path
from .security.confidential import Detector
from .security.integrity import IntegrityViolation, StateIntegrity
from .security.outputs import prepare_tool_result
from .security.provenance import ProvenanceIndex, Source
from .security.session import ApprovalSession


def clean(value):
    from .security.secrets import secret_scan

    if isinstance(value, str):
        return secret_scan(value)
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    return value


def state_path():
    return Path(os.environ.get("CROCODILE_STATE_DB", default_state_path())).absolute()


SESSION_WAIT_S = 900.0
_held: dict[str, list] = {}  # lock path -> [file handle, refcount]; re-entrant within one process


class StateSessionLock:
    """One Crocodile process at a time per state DB.

    Every legitimate write re-seals the state HMAC, and Part 3's watch-set treats a seal change during a
    watched action as tampering. Two processes on one state DB therefore abort each other with false
    INTEGRITY VIOLATIONs (seen 15 Nov: two shards run in parallel on one machine). Instead of weakening
    that check, a second process waits here. It is an OS lock, so it is released automatically if the
    holder crashes; use CROCODILE_STATE_DB for truly parallel sessions (each with its own `init`).
    """

    def __init__(self, db_path):
        self.path = Path(str(db_path) + ".session.lock")
        self._key = str(self.path).lower()
        self._acquired = False

    @staticmethod
    def _try_lock(handle) -> bool:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def acquire(self, wait_s: float = SESSION_WAIT_S, on_wait=None) -> None:
        import time

        if self._acquired:
            return
        held = _held.get(self._key)
        if held is not None:  # same process: share it (never deadlock against ourselves)
            held[1] += 1
            self._acquired = True
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")
        deadline = time.monotonic() + wait_s
        told = False
        while not self._try_lock(handle):
            if time.monotonic() >= deadline:
                handle.close()
                raise TimeoutError(
                    f"another Crocodile session kept {self.path.name} locked for {wait_s:.0f}s; "
                    "finish it, or give this session its own CROCODILE_STATE_DB"
                )
            if not told and on_wait is not None:
                on_wait()
                told = True
            time.sleep(0.5)
        _held[self._key] = [handle, 1]
        self._acquired = True

    def release(self) -> None:
        if not self._acquired:
            return
        self._acquired = False
        held = _held.get(self._key)
        if held is None:
            return
        held[1] -= 1
        if held[1] > 0:
            return
        handle = _held.pop(self._key)[0]
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            handle.close()


def session_directory(session_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", session_id):
        raise ValueError("invalid session id")
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "crocodile/sessions"
    path = base / session_id
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)):
        raise IntegrityViolation("linked session storage refused")
    return path


class SecurityContext:
    def __init__(self, repo, task, *, security_session=None, integrity=None):
        root = Path(repo).resolve(strict=True)
        if security_session is None:
            state = integrity or StateIntegrity(state_path())
            if state.path.resolve().is_relative_to(root):
                raise IntegrityViolation("security state must be outside the repository")
            state.verify_state()  # never enroll/re-sign an unknown DB on startup
            detector = Detector(SecurityStore(state.path, integrity=state))
            mode = detector.detect(root, root=root).mode
            security_session = ApprovalSession(
                root, mode=mode, user_task=task, integrity=state, confidentiality=detector
            )
        if security_session.repo_root != root or security_session.user_task != task:
            raise IntegrityViolation("security session root/original task mismatch")
        if security_session.integrity is None or security_session.confidentiality is None:
            raise IntegrityViolation("run requires attached state integrity and confidential detection")
        if security_session.integrity.path.resolve().is_relative_to(root):
            raise IntegrityViolation("security state must be outside the repository")
        self.p3 = security_session
        self._original_task = task
        self.check()

    @property
    def original_task(self):
        return self._original_task

    def check(self, session=None):
        self.p3.verify_integrity()
        self.p3.refresh_confidentiality()
        self.p3.verify_integrity()
        if session is not None:
            session.mode = self.p3.mode

    def observe(self, text, source):
        return prepare_tool_result(text, index=self.p3.provenance, source=source)

    def _signature(self, data):
        raw = json.dumps(
            data, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
        ).encode()
        return hmac.new(
            self.p3.integrity.keys.load(), b"crocodile-run-context-v1\0" + raw, hashlib.sha256
        ).hexdigest()

    def save(self, session, state, *, pending=None):
        self.p3.ensure_active()
        directory = session_directory(session.id)
        if directory.resolve().is_relative_to(self.p3.repo_root):
            raise IntegrityViolation("session storage must be outside the repository")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = {
            "version": 1,
            "repo": str(self.p3.repo_root),
            "original_task": self.original_task,
            "mode": self.p3.mode,
            "pending": pending,
            "state": clean(state),
            "observations": [
                {"text": clean(text), "kind": src.kind, "ref": src.ref, "line": src.line}
                for text, src in self.p3.provenance.observations()
            ],
        }
        raw = json.dumps({"data": data, "hmac": self._signature(data)}, ensure_ascii=True).encode()
        if len(raw) > 64 * 1024 * 1024:
            raise IntegrityViolation("session checkpoint exceeds size limit")
        descriptor, temporary = tempfile.mkstemp(dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, directory / "context.json")
        finally:
            Path(temporary).unlink(missing_ok=True)

    @classmethod
    def resume(cls, repo, session_id, *, security_session=None, integrity=None):
        path = session_directory(session_id) / "context.json"
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_nlink != 1
            or path.stat().st_size > 64 * 1024 * 1024
        ):
            raise IntegrityViolation("invalid resume checkpoint")
        envelope = json.loads(path.read_text(encoding="utf-8"))
        data = envelope["data"]
        state = (
            security_session.integrity
            if security_session is not None
            else integrity or StateIntegrity(state_path())
        )
        state.verify_state()
        # Obtain the trusted state/key before accepting task text or repo identity.
        raw = json.dumps(
            data, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
        ).encode()
        signature = hmac.new(
            state.keys.load(), b"crocodile-run-context-v1\0" + raw, hashlib.sha256
        ).hexdigest()
        if not isinstance(envelope.get("hmac"), str) or not hmac.compare_digest(signature, envelope["hmac"]):
            raise IntegrityViolation("resume checkpoint signature mismatch")
        if data["version"] != 1 or data["repo"] != str(Path(repo).resolve(strict=True)):
            raise IntegrityViolation("resume checkpoint belongs to another repository")
        if data["pending"] is not None:
            raise IntegrityViolation("operation outcome unknown; reconcile before resuming, never replay it")
        if security_session is not None and security_session.bench_auto:
            raise IntegrityViolation("bench automation authority is not restored on resume")
        context = cls(repo, data["original_task"], security_session=security_session, integrity=state)
        if data["mode"] == "confidential":
            context.p3.mode = "confidential"
        context.p3._permits.clear()
        context.p3._consent = None
        context.p3.provenance = ProvenanceIndex(data["original_task"])
        for entry in data["observations"]:
            context.p3.provenance.add(entry["text"], Source(entry["kind"], entry["ref"], entry["line"]))
        context.check()
        return context, data["state"]
