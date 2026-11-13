"""Console y/n stub, not the final policy or test-consent implementation."""

import os

from .types import Action, Decision


def _console_answer(preview: str) -> str:
    """Use the controlling terminal rather than piped stdin; no console denies."""
    if os.name == "nt":
        with (
            open("CONIN$", encoding="utf-8") as reader,
            open("CONOUT$", "w", encoding="utf-8") as writer,
        ):
            writer.write(preview)
            writer.flush()
            return reader.readline()
    with open("/dev/tty", "r+", encoding="utf-8") as console:
        console.write(preview)
        console.flush()
        return console.readline()


def ask(action: Action) -> Decision:
    """Ask y/n, defaulting to deny on empty input or unavailable console.

    Phase 0 only: no risk policy, nonce, consent grant, or approval binding.
    The returned decision does not execute the action.
    """
    if not isinstance(action, Action):
        raise TypeError("action must be a security.types.Action")
    if action.kind not in ("write", "shell", "git", "test_consent"):
        return Decision("deny", reasons=["unknown action kind"])
    # ascii/repr prevents raw terminal controls from proposal text being rendered.
    preview = (
        f"[PHASE 0 STUB] {action.kind}: argv={action.argv!a} "
        f"diff={action.diff!a} source={action.source!a}\nAllow? [y/N] "
    )
    try:
        approved = _console_answer(preview).strip().lower() in ("y", "yes")
    except (OSError, EOFError, KeyboardInterrupt):
        return Decision("deny", reasons=["console unavailable or interrupted"])
    return Decision(
        "allow" if approved else "deny",
        reasons=["Phase 0 console confirmation" if approved else "not confirmed"],
    )
