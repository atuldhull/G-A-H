"""Trusted in-memory approval state, pending the Part 2 journal integration."""

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
