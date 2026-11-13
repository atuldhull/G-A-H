"""Append-only SQLite event journal and idempotent resume logic.

Implements:
- Monotonic session event stream in SQLite events table.
- Idempotent resume: tools in flight (tool_started without tool_result)
  are flagged as OUTCOME UNKNOWN and never re-executed.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from crocodile.contracts import LadderRung, State


def init_journal_table(conn: sqlite3.Connection) -> None:
    """Ensures the events table exists in state.db."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                session TEXT,
                seq INT,
                ts REAL,
                type TEXT,
                payload TEXT,
                prev_hash TEXT,
                hash TEXT,
                PRIMARY KEY(session, seq)
            );
            """
        )


class EventJournal:
    """Manages appending and replaying session events."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_connection()
        try:
            init_journal_table(conn)
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def append(self, session: str, event_type: str, payload: dict[str, Any]) -> int:
        """Appends a new event to the session stream and returns the seq number."""
        now = time.time()
        conn = self._get_connection()
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE session = ?",
                    (session,),
                )
                next_seq = cur.fetchone()[0]
                payload_str = json.dumps(payload, default=str)
                cur.execute(
                    """
                    INSERT INTO events (session, seq, ts, type, payload)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session, next_seq, now, event_type, payload_str),
                )
                return int(next_seq)
        finally:
            conn.close()

    def get_events(self, session: str) -> list[dict[str, Any]]:
        """Retrieves all events for a given session in sequence order."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT seq, ts, type, payload FROM events WHERE session = ? ORDER BY seq ASC",
                (session,),
            )
            rows = cur.fetchall()
            events = []
            for seq, ts, etype, payload_str in rows:
                try:
                    payload = json.loads(payload_str)
                except Exception:
                    payload = {"raw": payload_str}
                events.append({"seq": seq, "ts": ts, "type": etype, "payload": payload})
            return events
        finally:
            conn.close()

    def resume(self, session: str) -> State:
        """Reconstructs session state from journal for idempotent resume.

        Specifically guards against repeating side effects:
        - If tool_started has no tool_result, reports OUTCOME UNKNOWN.
        """
        events = self.get_events(session)
        current_rung: LadderRung = "cheap"
        total_spent = 0.0
        is_paused = False
        pause_reason = None

        started_tools: dict[str, dict[str, Any]] = {}
        completed_tools: set[str] = set()

        for ev in events:
            etype = ev["type"]
            p = ev["payload"]

            if etype == "rung_changed":
                current_rung = p.get("to", current_rung)
            elif etype == "model_response":
                total_spent += float(p.get("cost", 0.0))
            elif etype == "paused":
                is_paused = True
                pause_reason = p.get("reason", "manual_pause")
            elif etype == "resumed":
                is_paused = False
                pause_reason = None
            elif etype == "tool_started":
                cid = p.get("call_id")
                if cid:
                    started_tools[cid] = p
            elif etype == "tool_result":
                cid = p.get("call_id")
                if cid:
                    completed_tools.add(cid)

        # Detect any started tools that never got a result (crash or interruption)
        interrupted_calls = set(started_tools.keys()) - completed_tools
        if interrupted_calls:
            # Append synthesized tool_result marking OUTCOME UNKNOWN so it is never re-run
            for cid in interrupted_calls:
                snapshot = started_tools[cid].get("snapshot", "")
                self.append(
                    session=session,
                    event_type="tool_result",
                    payload={
                        "call_id": cid,
                        "ok": False,
                        "status": "unknown",
                        "error": "OUTCOME UNKNOWN: tool was in flight during interruption",
                        "snapshot": snapshot,
                        "tokens_shown": 0,
                        "tokens_avoided": 0,
                    },
                )

        return State(
            session_id=session,
            events=[e["payload"] for e in events],
            current_rung=current_rung,
            total_spent_usd=total_spent,
            is_paused=is_paused,
            pause_reason=pause_reason,
        )
