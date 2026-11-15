# Part 3 completion audit fixes

This record supersedes the earlier statement that passing the 15 architecture
cases alone established complete implementation. Submission and videos belong to
Part 4 and are not counted as unfinished Part 3 implementation here.

## Closed code gaps

- Bench auto accepts eligible non-red edits and startup-registered exact pytest
  argv only. Arbitrary commands, Git mutations, web actions, red edits and changed
  test commands are denied. Optional external lint is skipped and journaled in
  that profile; syntax and approved pytest still run. Normal console approval and
  single-use permit revalidation remain active outside that exception.
- Root `init --repo PATH --confidential [--canary-source FILE]` and `init --repo
  PATH --public` use typed console confirmation and the enrolled integrity manager.
  The standalone classification command also attaches integrity. An unsigned store
  cannot write sealed classification state. Existing init seals are verified.
- `bifrost.base_url` is the canonical gateway setting. Runtime, doctor and probes
  share its resolver, accept the old flat `bifrost_url`, and reject conflicting
  values. Init does not overwrite existing settings.
- Shared Action inputs use a strict adapter; Decision, CmdResult and Mode reuse
  shared definitions. The network Action extension stays local, with no changes
  to contracts.py requiring another owner's approval.
- Full Part 3 Ruff checks are now required by both CI environments. The existing
  consent.py import-order issue is fixed. CLI and bench handoff documentation has
  been updated, while earlier phase reports remain labeled historical.

## Verification

The completion regression tests exercise CLI classification and clearing, canary
registration, valid HMAC after writes, rejection of unsigned/tampered state,
shared action execution and changed-input denial, and fresh/legacy gateway config.
Bench fixtures verify registered commands, denial boundaries and integrity aborts.
Updated CI results and source revisions will be recorded after the matrix finishes.

## Live acceptance

The user's Docker Desktop is updating. No host virtualization settings, kernel
installation or reboot was attempted. Live Bifrost/Ollama routing and independent
request-ID audit evidence must be checked once that update completes. Synthetic
HTTP fixtures are not a substitute for this live acceptance requirement.
