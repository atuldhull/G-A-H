"""Local HMAC sealing and bounded command watch-sets. No ledger ownership."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

REQUIRED = ("ledger", "confidential_repos", "grants")
PROTECTED = (*REQUIRED, "canaries", "security_classification_events", "meta")
MAX_ROWS = 100_000
MAX_ENTRIES = 50_000
MAX_BYTES = 256 * 1024 * 1024


class IntegrityViolation(RuntimeError):
    """Fail closed; never disclose database content or credentials in errors."""


class HMACKeys:
    """Use Windows Credential Manager directly; no backend discovery/fallback.

    Injected backends are a trusted fixture/owner seam, never model parameters.
    Creation is an explicit init operation, never performed during verification.
    """

    def __init__(self, *, backend=None):
        self._backend = backend

    def _vault(self):
        if self._backend is None:
            if os.name != "nt":
                raise IntegrityViolation("Windows Credential Manager is unavailable")
            try:
                from keyring.backends.Windows import WinVaultKeyring

                self._backend = WinVaultKeyring()
                if self._backend.priority <= 0:
                    raise RuntimeError("unavailable backend")
            except Exception as error:
                raise IntegrityViolation(
                    "Windows Credential Manager backend unavailable; install keyring and pywin32"
                ) from error
        return self._backend

    def load(self, *, create=False) -> bytes:
        try:
            backend = self._vault()
            value = backend.get_password("crocodile", "hmac_key")
            if value is None and create:
                value = secrets.token_bytes(32).hex()
                backend.set_password("crocodile", "hmac_key", value)
                if backend.get_password("crocodile", "hmac_key") != value:
                    raise IntegrityViolation("HMAC key storage verification failed")
            if not isinstance(value, str) or len(value) != 64:
                raise IntegrityViolation("HMAC key missing or malformed; run init")
            key = bytes.fromhex(value)
            if len(key) != 32:
                raise IntegrityViolation("HMAC key malformed")
            return key
        except IntegrityViolation:
            raise
        except Exception as error:
            raise IntegrityViolation("HMAC key storage failed") from error


def _encoded(value):
    if isinstance(value, bytes):
        return ["blob", base64.b64encode(value).decode("ascii")]
    return [type(value).__name__, value]


def _json(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")
    ).encode()


class StateIntegrity:
    """Sign logical rows/schema, independent of WAL layout and SELECT ordering.

    All ledger windows are protected (stronger than current-window-only); rolling
    over UTC midnight never silently accepts altered history. Only meta.hmac is
    owned here. Part 2 creates its tables and owns every money/routing operation.
    """

    def __init__(self, path: Path, *, keys: HMACKeys | None = None):
        self.path = Path(path).absolute()
        self.keys = keys or HMACKeys()

    def _check_path(self):
        if any(
            p.is_symlink() or getattr(p, "is_junction", lambda: False)()
            for p in (self.path, *self.path.parents)
        ):
            raise IntegrityViolation("linked state path refused")
        if not self.path.is_file() or self.path.stat().st_nlink != 1:
            raise IntegrityViolation("state database missing or linked")

    def _connection(self, db):
        self._check_path()
        files = list(db.execute("PRAGMA database_list"))
        if (
            len(files) != 1
            or files[0][1] != "main"
            or Path(files[0][2]).resolve() != self.path.resolve()
        ):
            raise IntegrityViolation(
                "integrity connection must use only the intended state database"
            )
        if not db.in_transaction:
            raise IntegrityViolation("integrity requires an owner transaction")

    def _digest(self, db):
        schema = list(
            db.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
            )
        )
        tables = {row[1] for row in schema if row[0] == "table"}
        if not {*REQUIRED, "meta"}.issubset(tables):
            raise IntegrityViolation("required protected state table missing")
        digest = hashlib.sha256(b"crocodile-state-v1\0")
        for table in PROTECTED:
            records = [tuple(row) for row in schema if row[2] == table]
            digest.update(_json([table, records]))
            if table not in tables:
                continue
            rows = db.execute(f'SELECT * FROM "{table}"').fetchmany(MAX_ROWS + 1)
            if len(rows) > MAX_ROWS:
                raise IntegrityViolation("protected state row limit exceeded")
            canonical = []
            for row in rows:
                if table == "meta" and row[0] == "hmac":
                    continue
                canonical.append(_json([_encoded(v) for v in row]))
            for row in sorted(canonical):
                digest.update(len(row).to_bytes(8, "big"))
                digest.update(row)
        return hmac.new(self.keys.load(), digest.digest(), hashlib.sha256).hexdigest()

    def _verify(self, db):
        self._connection(db)
        try:
            row = db.execute("SELECT v FROM meta WHERE k='hmac'").fetchone()
            expected = row[0] if row else None
            actual = self._digest(db)
            if not isinstance(expected, str) or not hmac.compare_digest(
                expected, actual
            ):
                raise IntegrityViolation("state HMAC mismatch or missing seal")
            return actual
        except (sqlite3.Error, ValueError, TypeError, OverflowError) as error:
            raise IntegrityViolation("state integrity verification failed") from error

    def verify_state(self, db=None) -> str:
        try:
            if db is not None:
                return self._verify(db)
            self._check_path()
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=ro", uri=True, timeout=5
            )
            try:
                connection.execute("PRAGMA busy_timeout=5000")
                connection.execute("BEGIN")
                return self._verify(connection)
            finally:
                connection.close()
        except (OSError, sqlite3.Error) as error:
            raise IntegrityViolation("state database inaccessible") from error

    def initialize(self, db) -> None:
        """Explicit trusted init only, in the owner's BEGIN IMMEDIATE transaction.

        Never call to repair a failed verification. Existing seals cannot be reset.
        """
        self._connection(db)
        db.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        if db.execute("SELECT 1 FROM meta WHERE k='hmac'").fetchone():
            raise IntegrityViolation("state is already sealed; refusing re-enrollment")
        self.keys.load(create=True)
        self._seal(db)

    def _seal(self, db):
        value = self._digest(db)
        db.execute(
            "INSERT INTO meta(k,v) VALUES ('hmac',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (value,),
        )
        self._verify(db)

    @contextmanager
    def authorized_write(self, db):
        """Inside BEGIN IMMEDIATE: verify -> owner writes -> seal -> owner commit.

        Failure rolls back the entire transaction. No blind reseal API is exposed.
        The owner must hold the SQLite writer lock, and must not commit in the body.
        """
        try:
            self.verify_state(db)
            yield db
            self._connection(db)
            self._seal(db)
        except BaseException:
            db.rollback()
            raise

    def before_reserve(self, db, *, session=None) -> str:
        """Part 2 calls under its BEGIN IMMEDIATE lock before computing budget."""
        return verify_state(self, connection=db, session=session)


class WatchSet:
    """Bounded hashes of the specified settings and repository security metadata."""

    def __init__(
        self,
        root: Path,
        *,
        config_dir: Path,
        state: StateIntegrity | None = None,
        extra=(),
    ):
        self.root = Path(root).resolve(strict=True)
        self.config_dir = Path(config_dir).absolute()
        self.state = state
        self.extra = tuple(Path(p).absolute() for p in extra)

    def snapshot(self) -> dict[str, str]:
        result, pending = {}, []
        base, git = self.config_dir, self.root / ".git"
        pending.extend(
            base / name
            for name in ("config.yaml", "policy.yaml", "prices.yaml", "empty-hooks")
        )
        pending.extend(
            (
                git / "config",
                git / "hooks",
                git / "info" / "attributes",
                self.root / ".gitattributes",
                self.root / ".gitmodules",
                self.root / ".crocodile",
            )
        )
        pending.extend(self.extra)
        if self.state is not None:
            result["state:HMAC"] = self.state.verify_state()
        else:
            pending.extend((base / "state.db", base / "state.db-wal"))
        total = 0
        while pending:
            path = pending.pop()
            if len(result) >= MAX_ENTRIES:
                raise IntegrityViolation("integrity watch-set entry limit exceeded")
            # Check ancestors too, including Git metadata links.
            if any(
                p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                for p in (path, *path.parents)
            ):
                raise IntegrityViolation("linked integrity watch-set path")
            key = str(path)
            try:
                info = path.stat()
            except FileNotFoundError:
                result[key] = "missing"
                continue
            if path.is_dir():
                result[key] = f"directory:{info.st_mode}"
                for child in path.iterdir():
                    pending.append(child)
                    if len(pending) + len(result) > MAX_ENTRIES:
                        raise IntegrityViolation(
                            "integrity watch-set entry limit exceeded"
                        )
                continue
            if not path.is_file() or info.st_nlink != 1:
                raise IntegrityViolation("non-regular integrity watch-set file")
            if total + info.st_size > MAX_BYTES:
                raise IntegrityViolation("integrity watch-set byte limit exceeded")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while block := stream.read(65536):
                    digest.update(block)
                    total += len(block)  # bound growing files as well as stat sizes
                    if total > MAX_BYTES:
                        raise IntegrityViolation(
                            "integrity watch-set byte limit exceeded"
                        )
            after = path.stat()
            if (info.st_size, info.st_mtime_ns, info.st_ino, info.st_mode) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ino,
                after.st_mode,
            ):
                raise IntegrityViolation("watch-set changed while hashing")
            result[key] = f"{info.st_mode}:{digest.hexdigest()}"
        return result


def verify_state(integrity: StateIntegrity, *, connection=None, session=None) -> str:
    """Owner verification hook for tool decisions/reservations outside Part 3."""
    if session is not None:
        session.ensure_active()
    try:
        return integrity.verify_state(connection)
    except (IntegrityViolation, OSError) as error:
        if session is not None:
            session.abort_integrity("state", "valid HMAC", "invalid or unavailable")
        raise IntegrityViolation("state integrity check failed") from error
