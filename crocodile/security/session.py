"""Trusted in-memory approval state, pending the Part 2 journal integration."""

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

    def __post_init__(self):
        self.repo_root = Path(self.repo_root).resolve(strict=True)
        if not self.repo_root.is_dir() or self.mode not in ("public", "confidential"):
            raise ValueError("invalid trusted session context")
        self._exe_pins = pin_tools(self.repo_root)
        self.provenance = ProvenanceIndex(self.user_task)

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
