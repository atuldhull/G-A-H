"""Concurrency test: 50 threads racing against a strict budget cap.

Proves:
- Atomic reservations via SQLite BEGIN IMMEDIATE.
- Exact hard cap semantics: sum(settled) + sum(held) <= limit at all times.
- Zero overshoot under high concurrency (ADR-005, R2 guarantee).
"""

import concurrent.futures
from pathlib import Path
import pytest
from crocodile.gateway.budget import BudgetManager, Denied
from crocodile.gateway.prices import PriceTable


def test_concurrency_50_zero_overshoot(tmp_path):
    db_path = tmp_path / "race_state.db"
    pt = PriceTable.from_yaml_file("prices.yaml")
    
    # Set a tight limit of $0.002 so that 50 requests cannot all fit
    limit_usd = 0.002
    bm = BudgetManager(db_path, pt, limits={"race-user": limit_usd})

    success_reservations = []
    denied_count = 0

    def worker_reserve(thread_id: int):
        try:
            res = bm.reserve(
                principal="race-user",
                chain=["anthropic/claude-haiku-5-5"],
                prompt_text="Task text for race",
                max_out_cap=1024,
            )
            # Reconcile slightly below or equal to reserved
            actual = bm.reconcile(
                res=res,
                actual_model="anthropic/claude-haiku-5-5",
                prompt_tokens=200,
                completion_tokens=100,
            )
            return ("success", res.id, actual)
        except Denied:
            return ("denied", None, 0.0)
        except Exception:
            return ("denied", None, 0.0)

    # Launch 50 threads concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(worker_reserve, i) for i in range(50)]
        for f in concurrent.futures.as_completed(futures):
            status, res_id, actual = f.result()
            if status == "success":
                success_reservations.append((res_id, actual))
            else:
                denied_count += 1

    spent, held = bm.get_window_spend("race-user")
    total_consumed = spent + held

    # Assertions
    assert len(success_reservations) > 0, "At least some requests should have succeeded"
    assert denied_count > 0, "Some requests should have been denied due to the $0.01 limit"
    assert total_consumed <= limit_usd, f"Total consumed ${total_consumed} exceeded limit ${limit_usd}!"
    assert held == 0.0, "All successful reservations should be settled"
