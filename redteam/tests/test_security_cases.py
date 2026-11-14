"""Collected security-case placeholders: all skipped, never credited as passed."""

from pathlib import Path

import pytest

from redteam.inventory import CASES


REPOSITORY = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case.pytest_id,
                  marks=pytest.mark.skip(reason=case.blocked_reason(REPOSITORY)))
     for case in CASES],
)
def test_security_case(case):
    # Removing a skip cannot turn an unimplemented live test into a false pass.
    pytest.fail(f"No reviewed live assertion adapter for {case.pytest_id}")
