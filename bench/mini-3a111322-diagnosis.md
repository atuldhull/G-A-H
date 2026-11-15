# Mini attempt 3a111322: supplied evidence and diagnostic fix

Inspected on clean `person-4` at
`9c8d27ee869322b04e9f16d206f5cd6865cf9ac9`. Attachments were treated as untrusted
data: entry metadata and JSON shapes were checked first, JSON members read with
a bounded total size, and no member extracted, executed, imported or copied into
the repository. No instructions from attachment data were followed. No real
credentials, gateway payloads, database or teammate drive were accessed.

## Attachment identity and contents

| Supplied artifact | Bytes | SHA-256 |
|---|---:|---|
| `mini-3a111322.zip` | 3962 | `4f486c64623570af8ddee35802dc9b9d86482536007f5e30ae1ec20169d04d8a` |
| `native-session-evidence.json` | 10063 | `60b814525fb7d458f3d0332ed590b5a51cb034f83c17560ce8d165cb62312412` |

ZIP entries: `command.json`, `config.json`, `control.json`, `launch.json`,
`mini-receipt.json`, `probe.json`, `process.json`, `result-row.json`. All are
parseable JSON members (Unix mode unspecified/0), with no absolute/traversing
member names or encryption;
total uncompressed JSON is under 7 KiB. This ZIP contains **no traceback,
exception message, original/final exercise tree or grading artifact**.

## What the mini evidence establishes

- Attempt `3a111322b8d848afa41805a01e7527a6`, planned ID
  `quixbugs/kheapsort/mini-swe-agent/run-1`.
- Receipt: mini 2.4.6, pinned template blob
  `8b72f71f8092ae805ec43221dbeaeefc2340cd3e`, LiteLLM 1.109.1, 26 steps,
  `Submitted`; reported usage 133894 prompt / 3954 completion / 61809 cached.
- Process: return code 0, no timeout, worker deadline reported enforced,
  escaped-descendant containment false. These are supplied records, not a new
  process execution or independent OS containment verification here.
- Runner: `status=incomplete`, `agent_claimed_solved=true`, `solved=false`,
  `independently_graded_solved=null`, `grading=null`; final/grade evidence null.
  Error records only `ValueError`, phase `mini-setup-or-grading`.
- Header settings false with empty review reference; launch `session_header`
  and result `session_id` are null. Exact mini-session log attribution remains
  incomplete. A time window is not an exact session/request join.
- Config requests `openai/gemini/gemini-3.5-flash-lite`, empty fallback list,
  provider-default thinking, 30 steps / 600-second policy. This is configuration
  intent, not proof of actual served model or provider settings. The launch lacks
  the later `task_text_sha256` field; no canonical config attestation or runtime
  Git SHA is supplied. It cannot be retrospectively declared v2-comparable.

## Localized failure path and limits

At the inspected code revision, `bench/mini.py:230` calls
`prepare_workspace(workspace, artifacts / 'final')`, then assigns `evidence.final`
only after that call returns. Independent grading begins at line 233. The row's
receipt/status/steps/process fields are already populated, while final and grade
are null. **Against that recorded control flow, the failure is localized to
final-tree preparation, before grading**, not a pytest failure.

That call validates the source tree before creating its destination.
`bench/prepare.py::_inventory` calls `_is_directory` for every entry, including
inside excluded `.meta` directories. At the inspected revision, ValueError sites
include links/junctions (line 15), nonordinary files (20), overlap checks (65), and
an entry changing during copying (76). Root/source checks also apply. The outer
handler at `mini.py:241` previously ran **after** TemporaryDirectory cleanup,
recording only the exception type and losing both its message and workspace.

The ZIP cannot establish which specific check or file raised, or prove that
Atul ran byte-identical host source. **The exact original cause remains unknown.**
Do not assert a symlink, fix an assumed file, weaken rejection, rerun the deleted
workspace, or turn `Submitted` into an independently graded solve. Preserve this
attempt as incomplete, not an eligible measured task failure.

## Safe diagnostics for future attempts

The Person 4 fix adds `WorkspaceEntryError(ValueError)` with a controlled reason
and an internal offending Path; its message omits raw absolute names.
`MiniAdapter` records an operation stage and captures failure evidence inside the
temporary-directory lifetime. The durable attempt receives:

- A controlled `error.message`, reason, stage, sanitized `relative_path` and
  path scope when known. Unknown arbitrary exception strings are omitted, not
  merely passed through regex redaction. Known setup reason IDs stay allowlisted.
- Bench frame filenames/line numbers, without source lines, locals, raw chained
  exceptions, task text, keys or provider payloads.
- `evidence.failure_inventory` pointing to a newly created, fsynced
  `failure-inventory.json`. It captures lstat entry kinds, relative names and
  ordinary-file sizes **before cleanup**, with no file contents or link targets.
  Unsafe/control/credential-looking or long names become stable hashed IDs.
  Links and reparse points are not traversed; special files are never opened.
- Explicit bounds (2000 entries, depth 32), incomplete/unavailable markers and
  capture-error type if evidence cannot be written. No older evidence is
  overwritten; the primary attempt still remains incomplete.

This is a reviewable **metadata inventory**, not an executable snapshot, atomic
filesystem image, OS sandbox, proof against concurrent mutation, or independent
grade. The normal temporary workspace is still cleaned. Existing task/receipt
protocol files are not copied into the new diagnostic artifact. Earlier process
errors remain primary if a later snapshot operation also fails; its safe
`diagnostic_error` records the secondary failure separately.

Synthetic regressions cover the same Submitted/26-step/return-0 shape with a
rejected special entry, plus real FIFO/symlink rejection where supported, unknown
grading/setup exception payload suppression, bounded metadata-only capture, and
refusal to admit incomplete attempts to the offline reporter. The synthetic
special-file metadata case runs without privileged link creation on Windows;
real OS cases retain explicit platform skips.

Windows CI exposed an additional diagnostic issue: its TEMP ancestor can use an
8.3 alias, while preparation returns canonical long paths. The initial diagnostic
root then failed to match the rejected entry and inventory containment check.
Canonicalizing only the trusted, newly created temporary parent before launching
mini keeps these paths consistent. Agent-created links are still rejected and
their targets are never resolved for diagnostics. The existing special-entry and
real-symlink regressions caught this issue. This CI finding does not identify the
cause of Atul's earlier attempt.

This changes frozen v2 runtime files. **V2 is unchanged and now has intentional
runtime drift**: strict validation rejects it; audit reports drift rather than
waiving it. A reviewed successor must pin the diagnostic helper and updated
runtime before official execution. No new authorization or shard run is enabled.

## Native evidence against v2 requirements

The JSON is a supplied summary: **25 rows, 9 native session IDs**, 12 Crocodile
rows and 13 twin rows across kheapsort, kth and lcs_length. It labels 23 rows
`success`, two `error`; 17 rows have attempt status completed and eight incomplete.
These are row counts, **not task pass rates or independently verified run counts**.

| Requirement | Supported by supplied JSON | Still unverified |
|---|---|---|
| Bench VK | All 25 `virtual_key_name` values are `bench`. | Stable VK ID/value binding, same identity for mini/native, physical origin/version. No `virtual_key_id` exists. |
| Flash-Lite model | Every `model` is the bare name `gemini-3.5-flash-lite`. | Provider-prefixed wire identity and billed/served model: all `served_model` values are null; no provider field. |
| Session correlation | Nonempty native session IDs and timestamps, linked to task/variant labels in this summary. | Original receipts/journal/header correlation, unique request IDs, duplicate detection and complete inventory. Neither `id` nor `request_id` exists. |
| No fallback/escalation | No different requested model appears in the summary. | Actual fallback chain/outcome and served model; no fallback fields. Absence is not proof of no fallback. |
| Effective sampling/thinking | No evidence fields. | Requested/forwarded temperature, provider-effective behavior, thinking and policy attestation. Accepted sampling differences do not permit fabricated observation. |
| Costs/cache | Reported prompt/completion counts and cost scalars. | Cached token categories, full usage JSON, prices hash/rates, complete closed/flushed request inventory, failed/retry usage and log-derived authoritative cost. Receipt/scalar cost alone is insufficient. |

The two error rows belong to lcs_length native sessions
`20261114-225622-c63275` (Crocodile) and `20261114-225807-f6f74d` (twin).
Both sessions also contain earlier success rows; retain those calls and their
eventual reviewed costs. The user reports **429s**, but this JSON only labels
`error` and does not include HTTP status codes or error bodies. Do not claim the
codes were independently verified here. Treat the reported rate-limit failures
as incomplete infrastructure/quota outcomes, **not task failures**. Reported zero
usage/cost on error rows is not proof of a measured zero charge.
Their error timestamps (17:26:31 and 17:28:16 UTC) are later than the mini
attempt's 17:21:52 UTC finish and refer to lcs_length, not kheapsort. They do not
explain the mini final-copy ValueError.

This improves the evidence status from "no native artifact supplied" to "supplied
summary reviewed with these gaps". It does not establish complete native parity,
clear mini attribution/completeness, authorize the 3-task live smoke or start
official shards. No live gateway call or database operation was performed.
