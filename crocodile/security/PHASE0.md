# Part 3 Phase 0 handoff

These are integration stubs, not completed security controls. Use trusted public
fixtures only. `mode_for` always returns `"public"`, including for marker-bearing
paths; `cmd.run` inherits the environment and does not enforce approvals or policy.

## Review baseline

The person-3 checkout at `191aa98` contained documentation only: no Python code,
shared `contracts.py`, or Phase 0 draft was present. This implementation follows
`docs/04-team-split.md` section 2, using the newer security-package layout rather
than the older flat architecture layout. No shared contracts were changed.

## Interfaces

- `from crocodile.security import approvals, cmd, confidential`
- `from crocodile.security.types import Action, Decision, CmdResult, Mode`
- `approvals.ask(Action(...)) -> Decision`: console y/n, default deny. Never reads
  piped stdin. Tests replace the private console reader with trusted answers.
  Callers check `decision.verdict == "allow"`; boolean conversion does the same.
- `cmd.run(argv, cwd, *, timeout) -> CmdResult`: list of string arguments,
  `shell=False`, closed stdin, UTF-8 captured stdout/stderr, nonzero exits returned.
  `subprocess.TimeoutExpired` and spawn `OSError` propagate to the caller.
- `confidential.mode_for(repo_path) -> Mode`: returns the literal string `"public"`.

`crocodile` is a namespace package so Phase 0 does not claim the shared package
initializer. There are no runtime dependencies beyond the Python standard library.

## Remaining contract handoffs

1. A second owner must agree to shared types before they move to `contracts.py`.
   Agree on Action validation and fields (cwd, resolved paths, edit pre-images,
   session context), and CmdResult timeout/spawn-error representation.
2. Part 1: wire approval before command execution; only `tools/tests.py` builds
   pytest argv. Final consent/policy, integrity hooks, provenance and edit metadata
   still need integration. The stub decision is not an execution capability.
3. Reconcile `Decision.steered_by`: this provisional list uses `file:line` strings;
   Architecture 02 describes Source objects. Agree the Source contract together.
4. Part 2: agree single-path versus multi-path mode input, session/journal state,
   registry and integrity interfaces. Replace the always-public stub before any
   confidentiality acceptance run or real private-data routing.
5. The older architecture centralizes subprocess in `policy/procs.py`; the newer
   team split assigns `security/cmd.py`. Agree the final internal runner location
   with Part 1 before structural lint is introduced.
6. Part 4: red-team and CI acceptance are deferred; Phase 0 smoke results do not
   establish security acceptance. Agree final journal event names with Part 2.

## Verification

Run from the repository root:

```powershell
python -m unittest discover -s tests/security -p 'test_*.py' -v
python -m compileall -q crocodile/security tests/security
```

With test tools installed, also run the isolated checks:

```powershell
python -m pytest -q -p no:cacheprovider --confcutdir=tests/security tests/security
python -m ruff check --isolated --no-cache crocodile/security tests/security
```

Set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` for pytest. Tests use a temporary public
directory and the absolute running Python interpreter, without executing repo
scripts, loading repo pytest config, or making network requests.

Verified on Windows with Python 3.14: 10 unittest tests passed; pytest reported
10 passed and 9 subtests passed; isolated Ruff, compileall, import smoke, and Git
whitespace checks passed. Temporary-directory cleanup required running the tests
outside the execution sandbox. Native interactive console behavior was not
manually exercised; the approval smoke fixtures substitute console answers.
