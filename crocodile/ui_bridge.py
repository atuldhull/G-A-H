"""Part 1 bridge to Part 4's screens (crocodile.ui): live status, final receipt and static quote.

Converts the agent's own state into Part 4's typed snapshots. Values we do not know stay None;
SOLVED is only shown when Part 4's evidence gate accepts our test-runner evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

PHASE = {"explore": "reproduce", "fix": "fix", "verify": "verify", "done": "done"}


def available() -> bool:
    try:
        import crocodile.ui  # noqa: F401
    except ImportError:
        return False
    return True


def _savings(r) -> Any:
    from crocodile.ui import SavingsEstimate
    s = r.savings or {}
    return SavingsEstimate(
        total_tokens=sum(s.values()) if s else None,
        spilled_tokens=s.get("gate"),
        unchanged_tokens=s.get("readcache"),
        masked_tokens=s.get("mask"),
        calls_avoided=1 if s.get("stop_green") else 0,
    )


def snapshot(agent) -> Any:
    from crocodile.ui import SessionMoney, SessionSnapshot, TokenUsage, VerificationState

    r, st, last = agent.r, agent.state, agent.ctx.tests.last
    real_cost = r.cost_usd is not None and not r.stubs
    tier = "local" if agent.s.mode == "confidential" else st.tier
    return SessionSnapshot(
        model=r.models[-1] if r.models else None,
        rung=tier if tier in ("cheap", "strong", "local") else None,
        turn=r.steps or None,
        phase=PHASE.get(st.phase),
        mode=agent.s.mode,
        verification=VerificationState(
            affected_passed=len(last.passed) if last else None,
            affected_total=(len(last.passed) + len(last.failed)) if last else None,
            failing_oracles=len(last.failed) if last else None,
        ),
        tokens=TokenUsage(input_tokens=r.usage.prompt_tokens, output_tokens=r.usage.completion_tokens,
                          cache_read_tokens=r.usage.cached_tokens, estimated=False),
        money=SessionMoney(session_usd=r.cost_usd, cost_estimated=not real_cost),
        savings=_savings(r),
        task=st.task[:200],
        repository=str(agent.s.repo),
        session_id=agent.s.id,
        escalations=r.escalations,
    )


def receipt(agent) -> Any:
    from crocodile.ui import SessionReceipt, TestOutcome

    r, tr = agent.r, agent.ctx.tests
    last = tr.last
    if r.solved:
        outcome = "solved"
    elif r.status.startswith("UNVERIFIED"):
        outcome = "tests_not_run"
    else:
        outcome = "stopped"
    evidence = None
    if tr.oracle_ids:
        ran = tr.runs > 0 and last is not None
        evidence = TestOutcome(
            source="test_runner",
            verified=bool(r.solved),
            scope="full" if tr.full_targets is not None else "partial",
            tests_run=ran,
            oracle_frozen="_oracle_modified" not in agent.s.flags,
            pytest_exit_code=last.exit_code if ran else None,
            timed_out=bool(last.timed_out) if ran else None,
            passed=len(last.passed) if ran else None,
            failed=len(last.failed) if ran else None,
            regressions=0 if r.solved else None,
            oracle=", ".join(tr.oracle_ids)[:200],
            consent_granted=False if "_no_test_consent" in agent.s.flags else (True if ran else None),
        )
    return SessionReceipt(outcome=outcome, session=snapshot(agent), test_outcome=evidence, reason=r.status)


def quote(task: str, repo: Path, *, ascii_only: bool = False) -> Any:
    """Static quote (no code runs): prices per tier from prices.yaml, a task-size usage estimate."""
    from crocodile.ui import RungPrice, UsageEstimate, quote_task

    from .adapters import PROJECT_ROOT, chain_for

    pricing: dict[str, Any] = {}
    try:
        from crocodile.gateway.prices import PriceTable
        table = PriceTable.from_yaml_file(PROJECT_ROOT / "prices.yaml")
        for rung in ("cheap", "strong", "local"):
            model = chain_for(rung)[0]
            try:
                t = table.get_model_pricing(model).tiers[0]
                pricing[rung] = RungPrice(model, t.in_, t.out)
            except (KeyError, AttributeError):
                pricing[rung] = None
    except ImportError:
        pricing = {}
    # Dev-check medians (Gemini Flash-Lite, Polyglot + QuixBugs): ~9.7K input, ~1K output per solved task.
    usage = UsageEstimate(input_tokens=10_000, output_tokens=1_200)
    return quote_task(task, repo, pricing=pricing or None, usage=usage, ascii_only=ascii_only)
