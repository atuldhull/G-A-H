"""Trusted in-memory approval state, pending the Part 2 journal integration."""

from dataclasses import dataclass, field
from pathlib import Path

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
    _permits: dict[str, str] = field(default_factory=dict, repr=False)
    _consent: str | None = field(default=None, repr=False)
    _edited_code: bool = field(default=False, repr=False)

    def __post_init__(self):
        self.repo_root = Path(self.repo_root).resolve(strict=True)
        if not self.repo_root.is_dir() or self.mode not in ("public", "confidential"):
            raise ValueError("invalid trusted session context")

    def record_edit(self, replacements: list[str]) -> None:
        """Part 1 calls after applying an edit with its exact REPLACE sides."""
        if any(changes_execution(text) for text in replacements):
            self._consent = None
            self._edited_code = True
            self._permits.clear()
            self.events.append(
                {"event": "test_consent_invalidated", "reason": "edited code"}
            )
