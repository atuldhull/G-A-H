"""Pre-call atomic budget reservation and degradation ladder.

Enforces:
  Σ settled + Σ held <= limit (ADR-005)
Zero overshoot by construction across concurrent processes.
Uses SQLite in WAL mode with BEGIN IMMEDIATE transactions.
"""

from __future__ import annotations

import math
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from crocodile.contracts import LadderRung, Reservation
from crocodile.gateway.prices import PriceTable

# Default budget settings from docs/architecture/04-data-model.md §5
DEFAULT_WARN_FRAC = 0.8
DEFAULT_HEARTBEAT_INTERVAL_S = 20
DEFAULT_STALE_LEASE_S = 60
DEFAULT_CALIB_Q95 = 1.35
DEFAULT_MAX_OUT_CAP = 4096
DEFAULT_MAX_OUT_FLOOR = 1024


class Denied(Exception):
    """Raised when a pre-call reservation cannot be satisfied."""

    def __init__(self, remaining: float, needed: float, reason: str = "insufficient_budget") -> None:
        self.remaining = remaining
        self.needed = needed
        self.reason = reason
        super().__init__(
            f"Reservation denied: needed ${needed:.4f}, but only ${remaining:.4f} remaining ({reason})"
        )


class Ladder:
    """Model degradation ladder: strong -> cheap -> local -> pause."""

    RUNGS: list[LadderRung] = ["strong", "cheap", "local", "pause"]

    def __init__(self, current: LadderRung = "cheap", is_confidential: bool = False) -> None:
        self.current: LadderRung = "local" if is_confidential else current
        self.is_confidential = is_confidential

    def step_down(self, why: str = "") -> LadderRung:
        """Step down to the next cheaper tier upon budget exhaustion or failure."""
        if self.is_confidential:
            self.current = "pause"
            return self.current

        idx = self.RUNGS.index(self.current)
        if idx < len(self.RUNGS) - 1:
            self.current = self.RUNGS[idx + 1]
        else:
            self.current = "pause"
        return self.current

    def escalate(self, why: str = "") -> LadderRung:
        """Escalate to a stronger model when evidence shows repeated failures."""
        if self.is_confidential:
            return "local"

        if self.current == "cheap":
            self.current = "strong"
        return self.current


def get_utc_date_window() -> str:
    """Returns today's date in UTC format YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def init_database(db_path: str | Path) -> sqlite3.Connection:
    """Initialize state.db with SQLite WAL mode and busy_timeout=5000."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")

    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                k TEXT PRIMARY KEY,
                v TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ledger (
                id TEXT PRIMARY KEY,
                principal TEXT NOT NULL,
                session TEXT,
                task TEXT,
                window TEXT NOT NULL,
                status TEXT CHECK(status IN ('held','settled','cancelled','expired')),
                reserved_usd REAL NOT NULL,
                actual_usd REAL,
                overshoot_usd REAL DEFAULT 0,
                model_ceiling TEXT,
                model_actual TEXT,
                tier TEXT,
                rung TEXT,
                est_in INT,
                bound_in INT,
                max_out INT,
                in_uncached INT,
                in_cache_read INT,
                in_cache_write INT,
                out_tokens INT,
                request_id TEXT,
                owner_pid INT,
                owner_start REAL,
                heartbeat REAL,
                sent INT DEFAULT 0,
                created_at REAL,
                settled_at REAL
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS ledger_pw ON ledger(principal, window, status);
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calib (
                model TEXT,
                ratio REAL,
                ts REAL
            );
            """
        )
    return conn


def is_pid_alive(pid: int) -> bool:
    """Check if process with given PID is still running on Windows / POSIX."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class BudgetManager:
    """Manages pre-call reservations, leases, reconciliations, and limits."""

    def __init__(
        self,
        db_path: str | Path,
        price_table: PriceTable,
        limits: dict[str, float] | None = None,
        integrity_verifier: Callable[[], None] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.price_table = price_table
        self.limits: dict[str, float] = limits or {}  # principal -> daily_usd
        self.integrity_verifier = integrity_verifier
        init_database(self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def get_principal_limit(self, principal: str) -> float:
        """Get the daily limit for a principal; defaults to 5.00 if unconfigured."""
        return self.limits.get(principal, 5.00)

    def get_window_spend(self, principal: str, window: str | None = None) -> tuple[float, float]:
        """Returns (spent_usd, held_usd) for a principal in the given window."""
        window = window or get_utc_date_window()
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'settled' THEN actual_usd ELSE 0 END), 0.0),
                    COALESCE(SUM(CASE WHEN status = 'held' THEN reserved_usd ELSE 0 END), 0.0)
                FROM ledger
                WHERE principal = ? AND window = ?
                """,
                (principal, window),
            )
            row = cur.fetchone()
            return float(row[0]), float(row[1])
        finally:
            conn.close()

    def expire_dead_leases(self, conn: sqlite3.Connection) -> int:
        """Expire held reservations whose owner PID has died."""
        cur = conn.cursor()
        cur.execute("SELECT id, owner_pid, heartbeat FROM ledger WHERE status = 'held'")
        rows = cur.fetchall()
        now = time.time()
        expired_count = 0
        for res_id, pid, heartbeat in rows:
            dead = not is_pid_alive(pid)
            stale = (now - heartbeat) > (DEFAULT_STALE_LEASE_S * 2)
            if dead or stale:
                cur.execute(
                    "UPDATE ledger SET status = 'expired', settled_at = ? WHERE id = ?",
                    (now, res_id),
                )
                expired_count += 1
        return expired_count

    def reserve(
        self,
        principal: str,
        chain: list[str],
        prompt_text: str | None = None,
        raw_token_count: int | None = None,
        session: str = "default-session",
        task: str = "default-task",
        rung: str = "cheap",
        max_out_cap: int = DEFAULT_MAX_OUT_CAP,
        max_out_floor: int = DEFAULT_MAX_OUT_FLOOR,
        window: str | None = None,
    ) -> Reservation:
        """Atomically reserves budget at worst-case fallback model and tier (ADR-005)."""
        if self.integrity_verifier:
            self.integrity_verifier()

        window = window or get_utc_date_window()

        # 1. Estimate input tokens
        if raw_token_count is not None:
            raw_in = raw_token_count
        elif prompt_text:
            # Conservative heuristic: 1 token ~= 3 characters
            raw_in = math.ceil(len(prompt_text) / 3.0)
        else:
            raw_in = 1000

        est_in = math.ceil(raw_in * DEFAULT_CALIB_Q95)
        bound_in = len(prompt_text.encode("utf-8")) if prompt_text else est_in

        # 2. Compute worst-case pricing across the fallback chain
        def compute_worst(target_chain: list[str], n_in: int, n_out: int) -> tuple[float, str, str]:
            max_cost = 0.0
            worst_model = target_chain[0]
            worst_tier_name = "default"
            for m in target_chain:
                pricing = self.price_table.get_model_pricing(m)
                tier = pricing.tier_for(n_in)
                in_p = max(tier.in_, tier.cache_write_5m or tier.in_) / 1_000_000.0
                out_p = tier.out / 1_000_000.0
                cost = (n_in * in_p) + (n_out * out_p)
                if cost >= max_cost:
                    max_cost = cost
                    worst_model = m
                    worst_tier_name = str(tier.upto)
            return max_cost, worst_model, worst_tier_name

        conn = self._get_connection()
        try:
            # BEGIN IMMEDIATE serializes reservations across all processes
            conn.execute("BEGIN IMMEDIATE;")

            # Check for clock rollback vs latest ledger entry
            cur = conn.cursor()
            cur.execute("SELECT MAX(window) FROM ledger WHERE principal = ?", (principal,))
            latest_window = cur.fetchone()[0]
            if latest_window and window < latest_window:
                conn.execute("ROLLBACK;")
                raise RuntimeError(
                    f"Clock skew detected: current window {window} is behind ledger window {latest_window}"
                )

            self.expire_dead_leases(conn)

            limit = self.get_principal_limit(principal)
            cur.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'settled' THEN actual_usd ELSE 0 END), 0.0),
                    COALESCE(SUM(CASE WHEN status = 'held' THEN reserved_usd ELSE 0 END), 0.0)
                FROM ledger
                WHERE principal = ? AND window = ?
                """,
                (principal, window),
            )
            spent, held = cur.fetchone()
            remaining = limit - spent - held

            # Near the limit: hard-bounded mode
            initial_worst, _, _ = compute_worst(chain, est_in, max_out_cap)
            n_in = bound_in if remaining < 3 * initial_worst else est_in

            # Shrink max_tokens if needed before refusing
            max_out = max_out_cap
            worst_cost, ceiling_model, tier_name = compute_worst(chain, n_in, max_out)
            while worst_cost > remaining and max_out > max_out_floor:
                max_out //= 2
                worst_cost, ceiling_model, tier_name = compute_worst(chain, n_in, max_out)

            if worst_cost > remaining:
                conn.execute("ROLLBACK;")
                raise Denied(remaining=remaining, needed=worst_cost, reason="budget_exhausted")

            # Insert held reservation
            res_id = f"res_{int(time.time() * 1000)}_{os.getpid()}_{math.ceil(time.perf_counter()*1e6)%10000}"
            now = time.time()
            cur.execute(
                """
                INSERT INTO ledger (
                    id, principal, session, task, window, status,
                    reserved_usd, actual_usd, model_ceiling, tier, rung,
                    est_in, bound_in, max_out, owner_pid, owner_start,
                    heartbeat, created_at
                ) VALUES (
                    ?, ?, ?, ?, ?, 'held',
                    ?, 0.0, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?
                )
                """,
                (
                    res_id, principal, session, task, window,
                    worst_cost, ceiling_model, tier_name, rung,
                    est_in, bound_in, max_out, os.getpid(), now,
                    now, now,
                ),
            )
            conn.commit()

            return Reservation(
                id=res_id,
                principal=principal,
                usd=worst_cost,
                model_ceiling=ceiling_model,
                tier=tier_name,
                est_in=est_in,
                bound_in=bound_in,
                max_out=max_out,
                owner_pid=os.getpid(),
                heartbeat=now,
            )
        except Exception:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def reconcile(
        self,
        res: Reservation,
        actual_model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        request_id: str | None = None,
    ) -> float:
        """Reconciles reservation to actual spend once the inference completes."""
        actual_usd = self.price_table.calculate_cost(
            model_id=actual_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )

        overshoot_usd = max(0.0, actual_usd - res.usd)
        uncached_in = max(0, prompt_tokens - cache_read_tokens - cache_write_tokens)
        now = time.time()

        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE ledger SET
                        status = 'settled',
                        actual_usd = ?,
                        overshoot_usd = ?,
                        model_actual = ?,
                        in_uncached = ?,
                        in_cache_read = ?,
                        in_cache_write = ?,
                        out_tokens = ?,
                        request_id = ?,
                        settled_at = ?
                    WHERE id = ?
                    """,
                    (
                        actual_usd, overshoot_usd, actual_model,
                        uncached_in, cache_read_tokens, cache_write_tokens,
                        completion_tokens, request_id, now, res.id,
                    ),
                )
            return actual_usd
        finally:
            conn.close()

    def cancel(self, res: Reservation, sent: bool = False) -> None:
        """Releases the reservation if un-sent; if sent, keeps it held until reconciled."""
        if sent:
            # As per ADR-005, once bytes leave the machine, the reservation must remain held
            # to prevent parallel calls from overshooting while the remote response might still bill.
            return

        now = time.time()
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE ledger SET status = 'cancelled', settled_at = ? WHERE id = ?",
                    (now, res.id),
                )
        finally:
            conn.close()

    def heartbeat(self, res_id: str) -> None:
        """Updates the lease heartbeat for an active in-flight call."""
        now = time.time()
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    "UPDATE ledger SET heartbeat = ? WHERE id = ? AND status = 'held'",
                    (now, res_id),
                )
        finally:
            conn.close()
