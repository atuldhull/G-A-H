"""StateSessionLock: exclusive across processes, re-entrant within one, released when the holder dies."""

import subprocess
import sys
import time

import pytest

from crocodile.runtime_security import StateSessionLock

HOLD = """
import sys, time
from crocodile.runtime_security import StateSessionLock
lock = StateSessionLock(sys.argv[1]); lock.acquire(wait_s=5)
print("held", flush=True)
time.sleep(float(sys.argv[2]))
"""


def _holder(db, seconds):
    p = subprocess.Popen([sys.executable, "-c", HOLD, str(db), str(seconds)], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "held"
    return p


def test_second_process_waits_then_gets_lock(tmp_path):
    db = tmp_path / "state.db"
    holder = _holder(db, 2.0)
    waited = []
    t0 = time.monotonic()
    lock = StateSessionLock(db)
    lock.acquire(wait_s=30, on_wait=lambda: waited.append(True))
    try:
        assert waited and time.monotonic() - t0 >= 1.0   # it really waited for the other process
    finally:
        lock.release()
        holder.wait(timeout=10)


def test_times_out_with_clear_message(tmp_path):
    db = tmp_path / "state.db"
    holder = _holder(db, 10.0)
    try:
        with pytest.raises(TimeoutError, match="CROCODILE_STATE_DB"):
            StateSessionLock(db).acquire(wait_s=1)
    finally:
        holder.kill()
        holder.wait(timeout=10)


def test_lock_freed_when_holder_is_killed(tmp_path):
    db = tmp_path / "state.db"
    holder = _holder(db, 60.0)
    holder.kill()
    holder.wait(timeout=10)
    lock = StateSessionLock(db)
    lock.acquire(wait_s=5)       # no stale lock after a crash
    lock.release()


def test_reentrant_in_one_process(tmp_path):
    db = tmp_path / "state.db"
    a, b = StateSessionLock(db), StateSessionLock(db)
    a.acquire(wait_s=1)
    b.acquire(wait_s=1)          # same process: shared, never a self-deadlock
    a.release()
    b.release()
    holder = _holder(db, 0.1)    # fully released: another process can take it
    holder.wait(timeout=10)
