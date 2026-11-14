"""Part 3 registry and append-only classification journal, not gateway logging."""

import json
import math
import os
import sqlite3
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path


class ClassificationError(RuntimeError):
    """Classification evidence is unavailable or inconsistent; refuse public use."""


@dataclass(frozen=True)
class RepoIdentity:
    realpath: str
    first_commit: str | None = None
    remote: str | None = None

    def __post_init__(self):
        if not isinstance(self.realpath, str) or any(
            value is not None and not isinstance(value, str)
            for value in (self.first_commit, self.remote)
        ):
            raise ClassificationError("invalid repository identity")
        if self.realpath:
            object.__setattr__(
                self, "realpath", os.path.normcase(str(Path(self.realpath).resolve()))
            )

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(
            f"{key}:{value}"
            for key, value in (
                ("realpath", self.realpath),
                ("first_commit", self.first_commit),
                ("remote", self.remote),
            )
            if value
        )


def default_state_path() -> Path:
    base = (
        Path(os.environ["APPDATA"])
        if os.name == "nt"
        else Path.home() / ".local" / "state"
    )
    return base / "crocodile" / "state.db"


def _event_ids(payload: dict) -> frozenset[str]:
    raw = payload.get("repo_id", {})
    if isinstance(raw, dict):
        values = {
            "realpath": raw.get("realpath") or payload.get("repo_root"),
            "first_commit": raw.get("first_commit"),
            "remote": raw.get("remote") or raw.get("remote_url"),
        }
    else:
        values = {"realpath": payload.get("repo_root")}
    ids = set(
        RepoIdentity(
            values.get("realpath") or "",
            values.get("first_commit"),
            values.get("remote"),
        ).ids
    )
    if "ids" in payload:
        if not isinstance(payload["ids"], list) or any(
            not isinstance(v, str)
            or not v.startswith(("realpath:", "first_commit:", "remote:"))
            for v in payload["ids"]
        ):
            raise ClassificationError("malformed journal repo identities")
        for value in payload["ids"]:
            if value.startswith("realpath:"):
                ids.update(RepoIdentity(value.removeprefix("realpath:")).ids)
            else:
                ids.add(value)
    return frozenset(ids)


class SecurityStore:
    """Own only confidential_repos, canaries and security_classification_events.

    Reads Part 2 events/JSONL but never creates or writes their journal/egress.
    Missing files are empty evidence; corrupt/unreadable evidence refuses use.
    """

    def __init__(self, path: Path | None = None, *, journals=(), integrity=None):
        supplied = Path(path if path is not None else default_state_path()).absolute()
        self.path = supplied.parent.resolve() / supplied.name
        self.journals = tuple(Path(p).resolve() for p in journals)
        self.integrity = integrity
        if integrity is not None and integrity.path.resolve() != self.path.resolve():
            raise ClassificationError("integrity belongs to another state database")

    def _exists(self):
        if self.integrity is not None:
            self.integrity.verify_state()
        try:
            self.path.lstat()
            return True
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ClassificationError("cannot inspect security state") from error

    @contextmanager
    def _open(self, *, write=False):
        if self.path.is_symlink():
            raise ClassificationError("linked security state refused")
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5)
        else:
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=ro", uri=True, timeout=5
            )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            with connection:
                if self.integrity is not None and not write:
                    connection.execute("BEGIN")
                    self.integrity.verify_state(connection)
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _schema(connection):
        connection.execute(
            "CREATE TABLE IF NOT EXISTS confidential_repos (first_commit TEXT, realpath TEXT, remote TEXT, since REAL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS canaries (token TEXT PRIMARY KEY, repo_id TEXT, path TEXT, created_at REAL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS security_classification_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, type TEXT NOT NULL, payload TEXT NOT NULL)"
        )

    def evidence(self) -> list[dict]:
        result = []
        try:
            if self.path.is_symlink():
                raise ClassificationError("linked security state refused")
            if self._exists():
                with self._open() as db:
                    tables = {
                        row[0]
                        for row in db.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    }
                    if "confidential_repos" in tables:
                        for row in db.execute(
                            "SELECT first_commit,realpath,remote,since FROM confidential_repos"
                        ):
                            ids = RepoIdentity(
                                row["realpath"] or "",
                                row["first_commit"],
                                row["remote"],
                            ).ids
                            result.append(
                                {
                                    "ts": row["since"],
                                    "mode": "confidential",
                                    "ids": ids,
                                    "session": None,
                                    "type": "registry",
                                }
                            )
                    for table in ("security_classification_events", "events"):
                        if table in tables:
                            session_column = ",session" if table == "events" else ""
                            for row in db.execute(
                                f"SELECT ts,type,payload{session_column} FROM {table} WHERE type IN ('session_started','classification_changed','classification_detected')"
                            ):
                                payload = json.loads(row["payload"])
                                parsed = self._parse_event(
                                    row["ts"], row["type"], payload
                                )
                                if table == "events":
                                    parsed["session"] = row["session"]
                                result.append(parsed)
            for path in self.journals:
                # An explicitly configured journal disappearing is inconclusive.
                with path.open(encoding="utf-8") as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        if not isinstance(event, dict):
                            raise ClassificationError("malformed journal event")
                        if event.get("type") in (
                            "session_started",
                            "classification_changed",
                            "classification_detected",
                        ):
                            parsed = self._parse_event(
                                event.get("ts"), event["type"], event.get("payload")
                            )
                            parsed["session"] = event.get("session", parsed["session"])
                            result.append(parsed)
            for event in result:
                if (
                    not event["ids"]
                    or event["mode"] not in ("public", "confidential")
                    or type(event["ts"]) not in (int, float)
                    or not math.isfinite(event["ts"])
                    or event["ts"] < 0
                ):
                    raise ClassificationError("malformed classification evidence")
            return result
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as error:
            raise ClassificationError(
                "cannot read classification registry/journal"
            ) from error

    @staticmethod
    def _parse_event(ts, kind, payload):
        if not isinstance(payload, dict):
            raise ClassificationError("malformed classification journal payload")
        # Public session starts never downgrade earlier confidential history.
        mode = payload.get("mode")
        return {
            "ts": ts,
            "type": kind,
            "mode": mode,
            "ids": _event_ids(payload),
            "session": payload.get("session"),
            "authorised_public": kind == "classification_changed"
            and payload.get("by") == "console",
        }

    def history(self, identity: RepoIdentity, *, at_time=None):
        evidence = self.evidence()
        if at_time is not None:
            evidence = [event for event in evidence if event["ts"] <= at_time]
        aliases = set(identity.ids)
        while True:
            expanded = aliases | set().union(
                *(set(e["ids"]) for e in evidence if aliases & e["ids"])
            )
            if expanded == aliases:
                break
            aliases = expanded
        relevant = [e for e in evidence if aliases & e["ids"]]
        return frozenset(aliases), relevant

    def is_confidential(self, identity: RepoIdentity, *, at_time=None) -> bool:
        _, history = self.history(identity, at_time=at_time)
        last_conf = max(
            (e["ts"] for e in history if e["mode"] == "confidential"), default=-1
        )
        last_public = max(
            (
                e["ts"]
                for e in history
                if e["mode"] == "public" and e.get("authorised_public")
            ),
            default=-1,
        )
        return last_conf >= 0 and last_conf >= last_public

    def path_is_confidential(self, path: Path, *, stop: Path | None = None) -> bool:
        # Match canonical ancestor IDs, even if a marker or registry row vanished.
        for parent in (path, *path.parents):
            if self.is_confidential(
                RepoIdentity(os.path.normcase(str(parent.resolve())))
            ):
                return True
            if parent == stop:
                break
        return False

    def record(
        self,
        identity: RepoIdentity,
        mode: str,
        *,
        kind="classification_detected",
        by=None,
        session=None,
        canary=None,
    ):
        if mode not in ("public", "confidential") or (
            mode == "public" and kind == "classification_changed" and by != "console"
        ):
            raise ClassificationError(
                "public reclassification requires console authorisation"
            )
        aliases, history = self.history(identity)
        stamp = max(time.time(), max((e["ts"] for e in history), default=0) + 0.000001)
        payload = {
            "repo_id": {
                "realpath": identity.realpath,
                "first_commit": identity.first_commit,
                "remote": identity.remote,
            },
            "ids": sorted(aliases),
            "mode": mode,
            "by": by,
            "session": session,
        }
        try:
            with self._open(write=True) as db:
                db.execute("BEGIN IMMEDIATE")
                with (
                    self.integrity.authorized_write(db)
                    if self.integrity is not None
                    else nullcontext()
                ):
                    self._record_rows(
                        db,
                        identity,
                        mode,
                        kind,
                        by,
                        session,
                        canary,
                        aliases,
                        stamp,
                        payload,
                    )
        except (OSError, sqlite3.Error) as error:
            raise ClassificationError(
                "cannot persist confidential classification"
            ) from error

    def _record_rows(
        self, db, identity, mode, kind, by, session, canary, aliases, stamp, payload
    ):
        self._schema(db)
        if mode == "public" and kind == "classification_changed":
            for row in db.execute(
                "SELECT rowid,first_commit,realpath,remote FROM confidential_repos"
            ).fetchall():
                if (
                    RepoIdentity(
                        row["realpath"] or "",
                        row["first_commit"],
                        row["remote"],
                    ).ids
                    & aliases
                ):
                    db.execute(
                        "DELETE FROM confidential_repos WHERE rowid=?",
                        (row["rowid"],),
                    )
        elif mode == "confidential":
            db.execute(
                "INSERT INTO confidential_repos(first_commit,realpath,remote,since) SELECT ?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM confidential_repos WHERE realpath=? AND first_commit IS ? AND remote IS ?)",
                (
                    identity.first_commit,
                    identity.realpath,
                    identity.remote,
                    stamp,
                    identity.realpath,
                    identity.first_commit,
                    identity.remote,
                ),
            )
        db.execute(
            "INSERT INTO security_classification_events(ts,type,payload) VALUES (?,?,?)",
            (stamp, kind, json.dumps(payload, sort_keys=True)),
        )
        if canary is not None:
            token, path = canary
            db.execute(
                "INSERT OR IGNORE INTO canaries(token,repo_id,path,created_at) VALUES (?,?,?,?)",
                (token, identity.realpath, str(path), stamp),
            )

    def canaries(self) -> tuple[str, ...]:
        if self.path.is_symlink():
            raise ClassificationError("linked security state refused")
        if not self._exists():
            return ()
        try:
            with self._open() as db:
                if not db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='canaries'"
                ).fetchone():
                    return ()
                return tuple(
                    row[0]
                    for row in db.execute("SELECT token FROM canaries ORDER BY token")
                )
        except sqlite3.Error as error:
            raise ClassificationError("cannot load canary registry") from error
