"""Console confirmation, single-use action permits and session test consent."""

import os
import secrets
import unicodedata
from dataclasses import replace
from pathlib import Path

from .binding import BoundAction, bind
from .policy import decide, risk
from .session import ApprovalSession
from .types import Action, Decision


class ApprovalDenied(PermissionError):
    """No valid approval exists; no effect may be performed."""


class ApprovalChanged(ApprovalDenied):
    """Inputs changed after preview; a fresh prompt is required."""


def escape(value: object, cap: int = 4000) -> str:
    """Render controls visibly; cap original characters and show omitted count."""
    text = str(value)
    shown = []
    for char in text[:cap]:
        if not char.isprintable() or unicodedata.category(char).startswith("C"):
            code = ord(char)
            shown.append(f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}")
        elif char == "\\":
            shown.append("\\\\")
        else:
            shown.append(char)
    if len(text) > cap:
        shown.append(f" [+{len(text) - cap} chars omitted]")
    return "".join(shown)


def _console_answer(preview: str) -> str:
    """Drain queued input before displaying a prompt; never read sys.stdin."""
    if os.name == "nt":
        import msvcrt

        with (
            open("CONIN$", encoding="utf-8") as reader,
            open("CONOUT$", "w", encoding="utf-8") as writer,
        ):
            while msvcrt.kbhit():
                msvcrt.getwch()
            writer.write(preview)
            writer.flush()
            return reader.readline()
    import termios

    with (
        open("/dev/tty", encoding="utf-8") as reader,
        open("/dev/tty", "w", encoding="utf-8") as writer,
    ):
        termios.tcflush(reader.fileno(), termios.TCIFLUSH)
        writer.write(preview)
        writer.flush()
        return reader.readline()


def _preview(
    action: Action, bound: BoundAction, decision: Decision, session: ApprovalSession
) -> str:
    lines = [f"{decision.level.upper()} approval"]
    if action.kind == "test_consent":
        lines += ["THIS EXECUTES CODE FROM THE REPO", "Plugins autoload: OFF"]
        if session._edited_code:
            lines.append("will execute edited code")
    if bound.argv:
        lines += [
            "argv: " + escape(repr(list(bound.argv))),
            "interpreter/executable: " + escape(bound.argv[0]),
            "cwd: " + escape(bound.cwd),
        ]
        executable = Path(bound.argv[0]).stem.lower()
        if (
            executable.startswith("python")
            or executable
            in ("bash", "sh", "cmd", "powershell", "pwsh", "node", "ruby", "perl")
        ) and any(
            arg.lower() in ("-c", "/c", "-command", "-encodedcommand")
            for arg in bound.argv[1:]
        ):
            lines.append("unparsed script")
    if action.diff is not None:
        lines.append("diff: " + escape(action.diff))
        lines += ["target: " + escape(path) for path in bound.paths]
    if action.source:
        lines.append("suggested by " + escape(action.source))
    if session.mode == "confidential" and bound.argv:
        lines.append("network is not blocked for child processes")
    for cfg in bound.configs:
        lines += [
            "config: " + escape(cfg.path) + " sha256=" + cfg.sha256,
            "static config (includes addopts/plugin declarations): "
            + escape(cfg.content),
        ]
    return "\n".join(lines) + "\n"


def ask(action: Action, *, session: ApprovalSession | None = None) -> Decision:
    """Confirm exact inputs; pass a session to retain a consumable permit."""
    session = session if session is not None else ApprovalSession()
    try:
        bound = bind(action, session)
        decision = risk(action, bound, session)
        if decision.verdict == "deny":
            if action.kind == "test_consent":
                session._consent = None
                session._permits.clear()
            session.events.append(
                {"event": "approval", "approved": False, "reasons": decision.reasons}
            )
            return decision
        reuse = (
            action.kind == "test_consent"
            and not action.source
            and session._consent == bound.digest
        )
        if action.kind == "test_consent" and not reuse:
            session._consent = None
            session._permits.clear()
        if not reuse:
            nonce = f"{secrets.randbelow(100):02d}"
            word = (
                "tests"
                if action.kind == "test_consent"
                else "apply"
                if action.kind == "write"
                else "run"
            )
            required = f"{word} {nonce}"
            prompt = _preview(action, bound, decision, session)
            prompt += (
                f"Type {required} to approve: "
                if decision.level == "red"
                else "Allow? [y/N] "
            )
            answer = _console_answer(prompt).strip()
            approved = (
                answer == required
                if decision.level == "red"
                else answer.lower() in ("y", "yes")
            )
            if not approved:
                session.events.append(
                    {"event": "approval", "approved": False, "by": "console"}
                )
                return replace(decision, verdict="deny", reasons=["not confirmed"])
        if bind(action, session).digest != bound.digest:
            raise ApprovalChanged("action changed while confirmation was displayed")
        token = secrets.token_hex(32)
        session._permits[token] = bound.digest
        if action.kind == "test_consent" and not action.source:
            session._consent = bound.digest
        session.events.append(
            {
                "event": "approval",
                "approved": True,
                "by": "consent" if reuse else "console",
                "token": token,
            }
        )
        return replace(decision, verdict="allow", token=token)
    except (
        OSError,
        EOFError,
        KeyboardInterrupt,
        ValueError,
        TypeError,
        RuntimeError,
    ) as error:
        session._consent = None
        session._permits.clear()
        session.events.append(
            {"event": "approval", "approved": False, "reason": str(error)}
        )
        return Decision("deny", reasons=[str(error)])


def validate_before_execution(
    action: Action, decision: Decision, *, session: ApprovalSession
) -> BoundAction:
    """Consume one permit immediately before an effect; mismatch never executes.

    Part 1 applies writes using the returned resolved paths, then calls
    session.record_edit with the REPLACE sides after a successful edit.
    """
    permit = session._permits.pop(decision.token, None)
    if decision.verdict != "allow" or permit is None:
        raise ApprovalDenied("no unconsumed approval in this session")
    try:
        bound = bind(action, session)
        if bound.digest != permit or risk(action, bound, session).verdict == "deny":
            raise ApprovalChanged("approval inputs changed; fresh approval required")
    except (OSError, ValueError, TypeError, RuntimeError, ApprovalChanged) as error:
        session._consent = None
        session._permits.clear()
        session.events.append({"event": "approval_invalidated", "reason": str(error)})
        raise ApprovalChanged(
            "approval inputs changed; fresh approval required"
        ) from error
    session.events.append({"event": "approval_used", "token": decision.token})
    return bound


__all__ = [
    "ApprovalChanged",
    "ApprovalDenied",
    "ApprovalSession",
    "ask",
    "decide",
    "escape",
    "validate_before_execution",
]
