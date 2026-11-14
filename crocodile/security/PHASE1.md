# Part 3 Phase 1: approvals and test consent

Python 3.12, outside-repo virtual environments, and the later trusted bench-session
API are documented in [BENCH.md](BENCH.md). Ordinary sessions remain console-only.

Phase 2 supersedes the deferred command, executable, path and Git behavior below;
see [PHASE2.md](PHASE2.md) for current integration details and verification.

Implemented on the Phase 0 commit `9b6c8f2`. No separate local Phase 1 draft or
shared `contracts.py` existed. Changes stay in Part 3's security package and tests.

## Owner integration

Create one `ApprovalSession(repo_root=Path(...), mode=...)` from trusted CLI/session
state, serialize its calls, and retain it for the session lifetime. Do not expose
mode, session flags, grants or approval decisions as model-controlled arguments.
`Action` retains the Phase 0 fields and adds `cwd`, `paths` and `replacements`.

```python
from crocodile.security import Action, ApprovalSession, approvals, cmd

# The owner supplies the repo path, mode, and already-built argv.
session = ApprovalSession(repo_root=repo_path, mode=mode)
action = Action("shell", argv=argv, cwd=str(repo_path))
decision = approvals.ask(action, session=session)
result = cmd.run(
    argv, repo_path, timeout=120, action=action, decision=decision, session=session
)
```

`cmd.run(argv, cwd, *, timeout)` still works and now prompts rather than executing
without approval. Its optional session/action/decision keywords support explicit
integration. For owner-built pytest argv use `Action("test_consent", ...)`.
Only Part 1's `tools/tests.py` should construct pytest argv. This package validates
and displays it; it never constructs the invocation or imports pytest.

For writes, supply the exact staged diff, target paths, and REPLACE sides. Unknown
replacement text stays amber. Call `validate_before_execution(action, decision,
session=session)` immediately before applying the effect, use its resolved paths,
then call `session.record_edit(action.replacements)` after successful application.
Part 1 owns its matcher/edit/loop wiring; those files are not changed here.

## Behavior

- Schema and binding failures deny before any console prompt. Risk comes from
  typed action data and trusted session state. Protected writes deny; test/build
  paths, provenance-steered actions, irreversible Git and confidential execution
  require red confirmation. Known network sinks deny when confidential or steered.
- Green/amber accept y/yes and otherwise deny. Red accepts only the displayed
  word and fresh two-digit nonce. `yes_green` cannot combine with test consent;
  this phase does not implement automatic green approval or a benchmark exception.
- Console input uses CONIN$/CONOUT$ on Windows, draining pending keys before
  displaying the prompt. It never reads piped stdin; unavailable console denies.
  The POSIX backend uses /dev/tty with input flushing.
- Controls, CR, bidi/zero-width characters and nonprintables are escaped. Long
  values are capped with their exact omitted-character count. Previews show the
  diff or escaped argv, resolved executable, cwd, targets, and source if supplied.
- Single-use, session-local permits bind tool kind, exact original/resolved argv
  or diff, replacement sides, provenance, resolved target paths/pre-image hashes,
  executable path/size/mtime, cwd, trusted policy flags and config hashes. Inputs
  are rechecked after confirmation and immediately before spawning. A mismatch
  raises `ApprovalChanged`; the caller must obtain fresh approval. No automatic
  retry executes changed inputs. The process receives the bound absolute argv.
- Test consent shows the red repo-code panel, exact interpreter/argv and a static
  config inventory with SHA-256 hashes and escaped contents (including addopts,
  explicit `-p` arguments and pytest_plugins declarations). The inventory covers
  the repo recursively and configs above cwd, without importing/executing them.
  New/deleted configs are included in comparisons, not just changed file hashes.
- Exact consent reuse emits an approval event with `by: consent`. Changed argv,
  config, interpreter metadata, cwd or provenance cannot reuse consent. A steered
  test action requires fresh red approval every time and creates no reusable grant.
  The REPLACE-side AST hook invalidates consent and pending permits for execution
  surfaces, conservatively including unknown syntax/aliases. The next test panel
  says `will execute edited code` and requires fresh red consent (ADR-004), despite
  Architecture 10's older amber expected-outcome wording.
- Tests must explicitly include `-p no:cacheprovider`. Execution sets
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and removes PYTEST_ADDOPTS/PYTEST_PLUGINS from
  the child environment. Nonzero child exits return normally; timeouts propagate.

## Deliberate limits and remaining handoffs

Part 1 must wire approval, provenance sources, edits and consent into collection,
reproduction, baseline/oracle runs and verification, leaving syntax/isolated lint
available when test consent is refused. Quote stays static with Part 4. Part 2
must persist `session.events`/grants through its journal and later integrity owner
contract. No shared type promotion has second-owner agreement yet.

Config scan failures, linked directories, scans above 50,000 entries, configs
above 2 MB, config/root overrides, response files, --pyargs and test paths outside
the inventory are refused rather than guessed. Path-bearing addopts are refused.
Configured testpaths/pythonpath must also stay inside the scanned tree. Both
INI and TOML pytest configuration files are inventoried. Python 3.11+ is required.
The test-consent interpreter form is Python [-I] [-B] -m pytest. Other launchers
and advanced config indirection require an owner-agreed scanner extension.

This is approval enforcement, not the full security system: Phase 2 still owns
complete Windows path/executable rules and pins, hardened Git, isolated child
environment, and job-object cleanup. Confidential detection remains the Phase 0
always-public stub; callers must supply a trusted mode until it is replaced.
Provenance indexing, durable journals, HMAC/watch-set and benchmark profile wiring
remain with later phases/owners. Basic binding checks do not replace those gates.
Revalidation narrows the approval race; it is not an OS sandbox or an atomic lock
against a targeted same-user process changing files after the final check.

## Verification

Run the trusted fixtures with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1:

```powershell
python -m pytest -q -p no:cacheprovider --confcutdir=tests/security tests/security
python -m ruff check --isolated --no-cache crocodile/security tests/security
python -m compileall -q crocodile/security tests/security
```

The suite covers denial/no spawn, typed red confirmation, pending-key draining,
control escaping, exact-input and executable-metadata drift, one-use permits,
cross-session denial, static config scanning, consent reuse, config additions /
changes / removals, steered/changed argv, edit invalidation and re-prompting.
Native console interaction is mocked in these automated checks, not manually
attested. Trusted fixture subprocesses use the absolute installed Python with -I.

Verified on Windows / Python 3.14: 41 tests and 57 subtests passed; isolated Ruff,
compileall, import smoke and Git whitespace checks passed. The test tools were
installed outside the checkout; no new runtime dependency or project-wide test
configuration was added.
