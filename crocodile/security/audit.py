"""Read-only audit of Part 2 egress evidence; never routes or logs requests."""

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ..journal_contract import SESSION_STARTED
from ..shared_state import StateLocationError, resolve_state_path
from .classification import ClassificationError, SecurityStore


@dataclass(frozen=True)
class AuditReport:
    status: str
    checked: int
    confidential_sent: int
    blocked: tuple[dict, ...]
    failures: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def passed(self):
        return self.status == "PASS"

    def render(self):
        lines = [
            f"RESULT: {self.status}",
            f"rows checked: {self.checked}; confidential sent: {self.confidential_sent}; blocked attempts: {len(self.blocked)}",
        ]
        lines.extend("FAIL: " + value for value in self.failures)
        lines.extend("MISSING: " + value for value in self.missing)
        for row in self.blocked:
            lines.append(
                f"BLOCKED session={row.get('session')} request={row.get('request_id')} reason={row.get('block_reason')}"
            )
        from .approvals import escape
        from .secrets import secret_scan

        return "\n".join(escape(secret_scan(line)) for line in lines)


def local_model(model, allowlist, *, actual=False):
    if not isinstance(model, str):
        return False
    tag = model.removeprefix("ollama/")
    return (
        (actual or model.startswith("ollama/"))
        and tag in allowlist
        and not any(value in tag.lower() for value in (":cloud", "-cloud", "/", "@"))
    )


def _destination(value):
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value if "://" in value else "http://" + value)
        if parsed.username is not None or parsed.password is not None:
            return ""
        return parsed.hostname or ""
    except ValueError:
        return ""


def audit_records(
    rows, *, allowlist, gateway_logs=None, session_modes=None
) -> AuditReport:
    failures, missing, blocked = [], [], []
    rows = list(rows)
    if not rows:
        missing.append("no egress evidence in the selected scope")
    if (
        not isinstance(allowlist, (tuple, list, set, frozenset))
        or not allowlist
        or any(not isinstance(tag, str) for tag in allowlist)
    ):
        failures.append("invalid or empty local model allowlist")
        allowlist = ()
    elif any(not local_model("ollama/" + tag, allowlist) for tag in allowlist):
        failures.append("invalid or empty local model allowlist")
    modes = session_modes or {}
    logs = {}
    if gateway_logs is not None:
        for log in gateway_logs:
            if not isinstance(log, dict) or not isinstance(log.get("request_id"), str):
                failures.append("malformed gateway log evidence")
                continue
            logs.setdefault(log["request_id"], []).append(log)
    seen, confidential = set(), 0
    for index, row in enumerate(rows):
        label = f"row {index + 1}"
        if (
            not isinstance(row, dict)
            or row.get("mode") not in ("public", "confidential")
            or row.get("verdict") not in ("sent", "blocked")
            or not isinstance(row.get("session"), str)
            or not row["session"]
        ):
            failures.append(label + ": malformed mode/session/verdict")
            continue
        mode = row["mode"]
        declared = modes.get(row["session"])
        if declared not in ("public", "confidential"):
            missing.append(label + ": no authoritative session-start mode")
        elif declared != mode:
            failures.append(label + ": mode disagrees with session journal")
        if type(row.get("canary_hits")) is not int or row["canary_hits"] < 0:
            failures.append(label + ": invalid canary hit count")
        if row["verdict"] == "blocked":
            if not isinstance(row.get("block_reason"), str) or not row["block_reason"]:
                failures.append(label + ": blocked attempt has no reason")
            blocked.append(
                {key: row.get(key) for key in ("session", "request_id", "block_reason")}
            )
            continue
        if not isinstance(row.get("dest"), str) or not row["dest"]:
            failures.append(label + ": missing destination")
        if not isinstance(row.get("payload_sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", row["payload_sha256"]
        ):
            failures.append(label + ": missing or invalid payload hash")
        if type(row.get("payload_bytes")) is not int or row["payload_bytes"] < 0:
            failures.append(label + ": missing or invalid payload byte count")
        request = row.get("request_id")
        if not isinstance(request, str) or not request or request in seen:
            failures.append(label + ": missing or duplicate sent request ID")
        seen.add(request if isinstance(request, str) else str(index))
        if mode == "public" and row.get("canary_hits") != 0:
            failures.append(label + ": canary found in a sent public payload")
        if mode != "confidential":
            continue
        confidential += 1
        if _destination(row.get("dest")) == "api.tavily.com":
            failures.append(label + ": confidential Tavily request was sent")
        try:
            parsed = urlsplit(
                row["dest"] if "://" in row["dest"] else "http://" + row["dest"]
            )
            destination_ok = (
                parsed.scheme == "http"
                and parsed.hostname == "127.0.0.1"
                and parsed.port == 8080
                and parsed.username is None
            )
        except (ValueError, TypeError, KeyError):
            destination_ok = False
        if not destination_ok:
            failures.append(label + ": confidential destination is not local Bifrost")
        if row.get("vk_alias") != "local":
            failures.append(
                label + ": confidential request did not use local key alias"
            )
        if not local_model(row.get("model_requested"), allowlist):
            failures.append(
                label + ": requested model is not an allowlisted local Ollama model"
            )
        try:
            fallbacks = (
                json.loads(row["fallbacks"])
                if isinstance(row.get("fallbacks"), str)
                else row["fallbacks"]
            )
        except (ValueError, KeyError, TypeError):
            fallbacks = None
        if fallbacks != []:
            failures.append(label + ": confidential fallbacks are not empty")
        if row.get("provider_actual") != "ollama" or not local_model(
            row.get("model_actual"), allowlist, actual=True
        ):
            failures.append(label + ": actual provider/model was not local Ollama")
        correlated = logs.get(request, []) if isinstance(request, str) else []
        if not correlated:
            missing.append(label + ": no matching Bifrost request log")
        elif any(
            log.get("provider") != "ollama"
            or not local_model(log.get("model"), allowlist, actual=True)
            for log in correlated
        ):
            failures.append(
                label + ": Bifrost evidence names a non-local provider/model"
            )
        version = row.get("evidence_version", 1)
        if type(version) is not int or version not in (1, 2):
            failures.append(label + ": invalid egress evidence version")
        # Old exports cannot silently select a weaker audit by omitting or
        # downgrading evidence_version. Correlation requirements apply to all.
        if len(correlated) > 1 or (not correlated and gateway_logs is not None):
            failures.append(label + ": sent request requires exactly one gateway record")
        if correlated:
            for log in correlated:
                required = ("session", "payload_sha256", "payload_bytes", "model_requested", "fallbacks", "vk_alias")
                for field in required:
                    expected = fallbacks if field == "fallbacks" else row.get(field)
                    if field not in log:
                        missing.append(label + ": gateway field unavailable: " + field)
                    elif log[field] != expected or type(log[field]) is not type(expected):
                        failures.append(label + ": gateway correlation mismatch: " + field)
                expected_model = str(row.get("model_actual", "")).removeprefix("ollama/")
                if str(log.get("model", "")).removeprefix("ollama/") != expected_model:
                    failures.append(label + ": gateway actual model mismatch")
                if row.get("gateway_request_id") and log.get("gateway_request_id") != row["gateway_request_id"]:
                    failures.append(label + ": gateway request ID mismatch")
    status = "FAIL" if failures else "INCOMPLETE" if missing else "PASS"
    return AuditReport(
        status, len(rows), confidential, tuple(blocked), tuple(failures), tuple(missing)
    )


def audit_database(
    path: Path,
    *,
    allowlist,
    gateway_logs=None,
    session=None,
    all_sessions=False,
    journals=(),
) -> AuditReport:
    """audit defaults to latest recorded session; --all includes all rows.

    Gateway records must be supplied by Part 2 or an explicit trusted log export.
    This function never imports a network client or obtains provider credentials.
    """
    if session is not None and all_sessions:
        raise ValueError("session and all_sessions are mutually exclusive")
    path = Path(path).absolute()
    try:
        with closing(
            sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
        ) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            if not all_sessions and session is None:
                latest = db.execute(
                    "SELECT session FROM egress ORDER BY ts DESC,seq DESC LIMIT 1"
                ).fetchone()
                session = latest["session"] if latest else None
            rows = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM egress"
                    + (
                        " WHERE session=?"
                        if not all_sessions and session is not None
                        else ""
                    )
                    + " ORDER BY seq",
                    (session,) if not all_sessions and session is not None else (),
                )
            ]
        modes = {}
        store = SecurityStore(path, journals=journals)
        selected = {row.get("session") for row in rows}
        for event in store.evidence():
            if event["type"] == SESSION_STARTED and event["session"]:
                if event["session"] not in selected:
                    continue
                if event["mode"] == "public":
                    # A public row and public session flag cannot launder an
                    # already-confidential repository into a passing audit.
                    identity_parts = {
                        value.partition(":")[0]: value.partition(":")[2]
                        for value in event["ids"]
                    }
                    from .classification import RepoIdentity

                    if store.is_confidential(
                        RepoIdentity(
                            identity_parts.get("realpath", ""),
                            identity_parts.get("first_commit"),
                            identity_parts.get("remote"),
                        ),
                        at_time=event["ts"],
                    ):
                        return AuditReport(
                            "FAIL",
                            len(rows),
                            0,
                            (),
                            ("public session contradicts sticky confidential history",),
                            (),
                        )
                previous = modes.get(event["session"])
                if previous and previous != event["mode"]:
                    return AuditReport(
                        "FAIL",
                        len(rows),
                        0,
                        (),
                        ("conflicting session journal modes",),
                        (),
                    )
                modes[event["session"]] = event["mode"]
        return audit_records(
            rows, allowlist=allowlist, gateway_logs=gateway_logs, session_modes=modes
        )
    except (OSError, sqlite3.Error, ClassificationError) as error:
        return AuditReport(
            "INCOMPLETE",
            0,
            0,
            (),
            (),
            ("cannot load egress/journal evidence: " + type(error).__name__,),
        )


def main(argv=None):
    """Standalone owner handler until Part 1 registers crocodile audit."""
    import argparse


    parser = argparse.ArgumentParser(
        description="Audit recorded agent egress; no requests are sent"
    )
    parser.add_argument("--state-db", type=Path)
    parser.add_argument("--allow-model", action="append", required=True)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--all", action="store_true", dest="all_sessions")
    scope.add_argument("--session")
    parser.add_argument("--gateway-log", type=Path)
    parser.add_argument("--journal", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    try:
        args.state_db = resolve_state_path(args.state_db)
    except StateLocationError as error:
        print("RESULT: INCOMPLETE\nMISSING: " + str(error))
        return 2
    logs = None
    if args.gateway_log is not None:
        try:
            from crocodile.gateway.records import read_gateway_records
            logs = read_gateway_records(args.gateway_log)
        except (OSError, ValueError, TypeError, KeyError):
            print(
                "RESULT: INCOMPLETE\nMISSING: cannot read normalized gateway log export"
            )
            return 2
    report = audit_database(
        args.state_db,
        allowlist=args.allow_model,
        gateway_logs=logs,
        session=args.session,
        all_sessions=args.all_sessions,
        journals=args.journal,
    )
    print(report.render())
    return 0 if report.passed else 1 if report.status == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
