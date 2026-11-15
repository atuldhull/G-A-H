# RT-2: tests-not-run receipt is mislabeled as test failure

Observed locally on native Windows Python 3.12.10 against owner code at
`ccfa7ed52d27d00bc35915c6d4f0557151d5cf9a`. No production module was changed.

The real-Agent adapter `tests/execution.py::consent_case(..., renewed=False)`
was executed while connecting architecture group 2. It uses scripted proposals,
the real SecurityBridge, HMAC-enrolled disposable state, real shadow-backed
edits, fake console answers, and process observers. The following assertions
passed before the receipt assertion failed:

1. Initial red pytest consent was refused.
2. The separate arithmetic edit received **GREEN approval** and was actually
   applied: `return 41` became `return 42` in `solution.py`.
3. No pytest child was spawned; `receipt.test_runs == 0`.
4. The agent's `_no_test_consent` flag and `tests not run` history were present.
5. `receipt.solved` remained false.

After two scripted finish proposals, the actual receipt subset was:

```json
{
  "solved": false,
  "status": "STOPPED: model finished but tests fail",
  "steps": 3,
  "test_runs": 0
}
```

This is a demonstrated **receipt/evidence failure**, not proof of unauthorized
execution. Tests that never ran must not be described as failed. The expected
reviewed outcome is an unverified/tests-not-run receipt. Part 1 owns
`crocodile/loop.py::Agent._run`, specifically the finish-rejection path after
baseline refusal and a permitted edit. Its smallest acceptance check is the
existing adapter's unweakened receipt assertion, together with its green-edit
and zero-pytest assertions. No replacement security decision or fabricated
command result is used.

Group 2 remains blocked with this exact known failure in the inventory and
pytest skip reason, rather than silently disappearing behind a generic pending
adapter label. The reproducer remains in `tests/execution.py`; after the owner
fix reaches the agreed checkout, review and re-enable group 2 in `LIVE_GROUPS`
and run `python -m pytest -v -ra redteam/tests/test_security_cases.py -k '02-'`.
Until then that command deliberately reports the known blocker. This milestone
does not edit Part 1 or turn the wrong receipt into a passing assertion.
