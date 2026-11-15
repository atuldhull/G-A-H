"""Canonical session events, including read compatibility with historic envelopes."""

import os
from pathlib import Path

SESSION_STARTED = "session_started"
SESSION_START_ALIASES = frozenset((SESSION_STARTED, "session_start"))


def event_type(kind):
    if kind is not None and not isinstance(kind, str):
        raise ValueError("invalid journal event name")
    return SESSION_STARTED if kind in SESSION_START_ALIASES else kind


def session_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid session journal payload")
    result = dict(payload)
    if result.get("mode") not in (None, "public", "confidential") or (
        result.get("mode") == "public" and result.get("confidential") is True
    ):
        raise ValueError("conflicting or invalid session mode")
    if isinstance(result.get("repo_root"), str) and isinstance(result.get("repo"), str):
        if os.path.normcase(str(Path(result["repo_root"]).resolve())) != os.path.normcase(
            str(Path(result["repo"]).resolve())
        ):
            raise ValueError("conflicting session repository paths")
    if "repo_root" not in result and isinstance(result.get("repo"), str):
        result["repo_root"] = result["repo"]
    if "mode" not in result and result.get("confidential") is True:
        result["mode"] = "confidential"
    return result


def read_envelope(record):
    if not isinstance(record, dict):
        raise ValueError("invalid journal envelope")
    if "type" not in record and isinstance(record.get("event"), dict):
        return read_envelope(record["event"])
    kind = record.get("type", record.get("event"))
    if "type" in record and "event" in record and event_type(record["type"]) != event_type(record["event"]):
        raise ValueError("conflicting journal event names")
    payload = record.get(
        "payload",
        {key: value for key, value in record.items() if key not in ("ts", "type", "event", "session", "seq")},
    )
    kind = event_type(kind)
    return kind, session_payload(payload) if kind == SESSION_STARTED else payload
