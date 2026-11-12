# ADR-009: SQLite for ledger, journal and egress log

- **Status:** Accepted
- **Context:** We need atomic reservations across processes, an append-only journal for resume, and an audit log, on Windows, with no server.
- **Decision:** One `state.db` in WAL mode; `BEGIN IMMEDIATE` serialises reservations across processes; `busy_timeout` 5 s; a locked ledger denies (fail closed). Tables are HMAC-protected by `integrity.py`. Hash chains on events/egress are P1. Team scale = Postgres `SELECT … FOR UPDATE` (P2).
- **Consequences:** + Zero ops, stdlib only, testable race invariant. − Single-machine scope; same-user processes can still edit the file (detected, not prevented).
