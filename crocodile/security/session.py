"""Trusted in-memory approval state, pending the Part 2 journal integration."""

import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .executables import pin_tools
from .provenance import ProvenanceIndex
from .surfaces import changes_execution
from .types import Mode


@dataclass
class ApprovalSession:
    """Caller-owned flags, never model arguments. One instance per session.

    Calls must be serialized. Grants are not persisted or restored across runs.
    """

    repo_root: Path = field(default_factory=Path.cwd)
    mode: Mode = "public"
    yes_green: bool = False
    events: list[dict] = field(default_factory=list)
    user_task: str = ""
    confidentiality: object | None = field(default=None, repr=False)
    integrity: object | None = field(default=None, repr=False)
    _aborted: bool = field(default=False, init=False, repr=False)
    provenance: ProvenanceIndex = field(init=False, repr=False)
    _permits: dict[str, str] = field(default_factory=dict, repr=False)
    _consent: str | None = field(default=None, repr=False)
    _edited_code: bool = field(default=False, repr=False)
    _exe_pins: dict = field(default_factory=dict, init=False, repr=False)
    _git_disabled: bool = field(default=False, init=False, repr=False)
    _output_counter: int = field(default=0, init=False, repr=False)
    _bench_root: tuple[Path, int, int] | None = field(
        default=None, init=False, repr=False
    )
    _bench_closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        self.repo_root = Path(self.repo_root).resolve(strict=True)
        if not self.repo_root.is_dir() or self.mode not in ("public", "confidential"):
            raise ValueError("invalid trusted session context")
        self._exe_pins = pin_tools(self.repo_root)
        self.provenance = ProvenanceIndex(self.user_task)

    @classmethod
    def for_bench(
        cls,
        repo_root: Path,
        *,
        parent: Path | None = None,
        user_task: str = "",
        events: list[dict] | None = None,
        integrity=None,
        confidentiality=None,
    ):
        """Trusted harness only: activate BEFORE populating an empty scratch repo.

        The harness owns creation, task preparation, grading and cleanup. Its root
        must be a direct child of the trusted scratch parent (OS temp by default).
        This does not attest OS isolation or make arbitrary child code safe.
        """
        raw = Path(repo_root).absolute()
        if any(
            p.is_symlink() or getattr(p, "is_junction", lambda: False)()
            for p in (raw, *raw.parents)
        ):
            raise ValueError("bench workspace must not traverse links")
        root = raw.resolve(strict=True)
        scratch = Path(parent if parent is not None else tempfile.gettempdir()).resolve(
            strict=True
        )
        if root.parent != scratch or not root.is_dir() or any(root.iterdir()):
            raise ValueError(
                "bench requires an empty direct child of its trusted scratch parent"
            )
        session = cls(
            repo_root=root,
            user_task=user_task,
            events=events if events is not None else [],
            integrity=integrity,
            confidentiality=confidentiality,
        )
        info = root.stat()
        session._bench_root = (root, info.st_dev, info.st_ino)
        session.events.append(
            {
                "event": "bench_session_started",
                "repo_root": str(root),
                "approval_mode": "bench_auto",
                "os_sandbox": False,
            }
        )
        return session

    @property
    def bench_auto(self) -> bool:
        return self._bench_root is not None and not self._bench_closed

    def close_bench(self):
        """Revoke all bench authority before the harness cleans up its workspace."""
        if self._bench_root is None:
            raise ValueError("not a bench session")
        self._bench_closed = True
        self._permits.clear()
        self._consent = None
        self.events.append({"event": "bench_session_closed"})

    def record_edit(self, replacements: list[str]) -> None:
        """Part 1 calls after applying an edit with its exact REPLACE sides."""
        if any(changes_execution(text) for text in replacements):
            self._consent = None
            self._edited_code = True
            self._permits.clear()
            self.events.append(
                {"event": "test_consent_invalidated", "reason": "edited code"}
            )

    def ensure_active(self):
        from .integrity import IntegrityViolation

        if self._aborted:
            raise IntegrityViolation("session aborted after integrity violation")
        if self._bench_closed:
            raise IntegrityViolation("bench session is closed")
        if self._bench_root is not None:
            root, device, inode = self._bench_root
            try:
                info = root.stat()
                valid = (
                    self.repo_root == root
                    and root.resolve(strict=True) == root
                    and not root.is_symlink()
                    and not getattr(root, "is_junction", lambda: False)()
                    and root.is_dir()
                    and (info.st_dev, info.st_ino) == (device, inode)
                )
            except OSError:
                valid = False
            if not valid:
                self.abort_integrity(
                    "bench workspace",
                    "original disposable root",
                    "changed or unavailable",
                )

    def abort_integrity(self, path, expected, found):
        from .integrity import IntegrityViolation

        if not self._aborted:
            self._aborted = True
            self._consent = None
            self._permits.clear()
            self._git_disabled = True
            self.events.append(
                {
                    "event": "integrity_violation",
                    "path": path,
                    "expected": expected,
                    "found": found,
                    "session_aborted": True,
                }
            )
        raise IntegrityViolation(
            "INTEGRITY VIOLATION: session aborted; inspect state before restarting"
        )

    def verify_integrity(self):
        from .integrity import verify_state

        self.ensure_active()
        if self.integrity is not None:
            return verify_state(self.integrity, session=self)

    @contextmanager
    def watch_integrity(self, *, extra=()):
        from .classification import default_state_path
        from .integrity import IntegrityViolation, WatchSet

        self.verify_integrity()
        config_dir = (
            self.integrity.path.parent
            if self.integrity is not None
            else default_state_path().parent
        )
        watcher = WatchSet(
            self.repo_root, config_dir=config_dir, state=self.integrity, extra=extra
        )

        def snapshot():
            try:
                return watcher.snapshot()
            except (IntegrityViolation, OSError, ValueError):
                self.abort_integrity(
                    "watch-set", "readable trusted paths", "invalid or unavailable"
                )

        baseline = snapshot()

        def check():
            self.ensure_active()
            current = snapshot()
            changed = sorted(
                k
                for k in baseline.keys() | current.keys()
                if baseline.get(k) != current.get(k)
            )
            if changed:
                # Do not leak arbitrary path names/values into journal consumers.
                from .approvals import escape

                key = changed[0]
                self.abort_integrity(
                    escape(key),
                    baseline.get(key, "missing"),
                    current.get(key, "missing"),
                )

        try:
            yield check
        finally:
            if not self._aborted:
                check()

    def refresh_confidentiality(self):
        """Owner hook: attach Detector and recheck before each turn/tool decision."""
        if self.confidentiality is None:
            return
        result = self.confidentiality.detect(self.repo_root, root=self.repo_root)
        if result.mode == "confidential" and self.mode != "confidential":
            self.mode = "confidential"
            self._consent = None
            self._permits.clear()
            self.events.append({"event": "mode_changed", "mode": "confidential"})
        self.events.extend(
            {"event": "confidential_alert", "message": alert} for alert in result.alerts
        )
