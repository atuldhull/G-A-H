# Part 3 Phase 3: provenance and secret redaction

Based on Phase 2 `69f9c10`; no separate local Phase 3 draft existed. Changes stay
in Part 3's package and tests. Shared contracts and Part 1/2 tool implementations
are not changed. Push phase commits only to person-3.

## Session provenance and approval integration

```python
from crocodile.security import Action, ApprovalSession, approvals
from crocodile.security.provenance import Source
from crocodile.security.outputs import prepare_tool_result

session = ApprovalSession(repo_root=repo_path, user_task=original_user_task)
shown = prepare_tool_result(
    text, index=session.provenance, source=Source("file", "README.md", 1)
)
decision = approvals.ask(Action("shell", argv=argv), session=session)
```

The owner must supply the original user task at session construction and reuse
the same session. Source references are supplied by trusted tool code, not model
arguments. A source starting at line 1 maps a match on its fortieth line to
README.md:40. Append observations in exposure order. The first matching observation
wins for the panel, with all matching sources available from the index.

`ProvenanceIndex.add(text, Source(kind, ref, line))` accepts file text, search
snippets, names/symbols, command output and web results. `steered_by(fields)` takes
(value, field_type) pairs and returns Source objects. Matching is literal,
case-sensitive substring membership: no decoding, case folding, fuzzy matching,
or paraphrase inference. Values shorter than eight characters are ignored except
typed URLs/hosts. Any value literally present in the original task is excluded.

Approval binding derives sensitive values from argv, paths, URL/host substrings,
network queries, and replacement-side URLs/hosts/new imports. Existing imports in
a single validated target pre-image are subtracted; multi-file/fragment cases are
conservative. Domain-shaped argv values also receive the host exception; this can
include short filenames that look like domains. URL host spelling is preserved.
Git remote helpers cover both URI and SCP-style hosts.

Derived sources cannot be overridden by a legacy caller-supplied Action.source.
The first location appears in the red typed-confirmation panel. Known steered
network sinks are denied before prompting, with attribution in the Decision.
Git checks original revisions before resolving them to SHAs, and checks audited
remote URLs/hosts before push. Confidential/steered push remains denied.
Validated fixed Git read templates remain free; provenance escalates mutations.

Sources are included in approval fingerprints. A newly observed relevant match
invalidates pending approval, and a steered test argv never reuses/stores session
test consent. Readme execution and direct network-denial fixtures check these
separately: commands that are recognized as network sinks deny rather than show a
red approval panel. Unparsed scripts remain approved code, not an OS sandbox.

`Action('network', query=..., url=...)` is a package-local proposed contract for
Part 2's web/egress owner. Query and URL are optional individually, with at least
one required. Public unsteered requests ask amber; confidential or steered requests
deny. The owner must consume/revalidate approval immediately before sending, just
as Part 1 does before effects. This phase adds no HTTP code, no network sender,
and no cloud-route approval requirement for ordinary egress.chat calls.

## Redaction and Part 1 hooks

`secrets.secret_scan(text)` / `secrets.redact(text)` return deterministic
[REDACTED:<kind>:<sha8>] markers, where sha8 is the first eight hex characters of
SHA-256 over the matched plaintext value. `redact_with_findings` additionally
returns kind/hash/span records without storing the original secret in findings.
Offsets apply after ANSI/OSC removal by default. Repeated scanning preserves valid
markers. Approval previews use strip_ansi=False before visibly escaping controls,
so redaction does not silently hide bytes from a proposed diff/argument.

Coverage: AKIA/ASIA IDs, GitHub ghp_/github_pat_ and related token prefixes,
sk- provider credentials, Slack xoxb-/xoxp-, complete/truncated PEM blocks, embedded
URL user:password credentials, JWTs, and high-entropy KEY/TOKEN/SECRET assignments
in env/JSON/YAML-like output. Generic values require length >=16 and Shannon
entropy >=3.5 bits/character; valid variable placeholders are excluded. This is a
deterministic format/entropy scanner, not a guarantee to find every secret or
encoded/paraphrased value. No credentials are loaded from the OS by this module.

ANSI/OSC is removed before scanning. Multiline secrets retain their newline count
after replacement, so later file:line attribution remains correct. Overlapping
matches prefer the outer span; a PEM block hides any tokens inside it. URL
credential redaction preserves the scheme/host/path while masking userinfo.

`outputs.prepare_tool_result` scans then indexes the sanitized complete text.
Part 1 must call it before any truncation, spill, cache, journal or model exposure
for every read/search/list/symbol result; Part 2 must do the same for web results.
Full raw secrets should not be indexed/persisted by those integrations. Part 3
automatically sanitizes and indexes returned command/Git stdout and stderr, and
sanitizes returned argv. Actual execution still uses the exact approved raw argv.
Internal Git bootstrap/config/revision outputs are not indexed as model-visible
observations. Approval previews use the same scanner before terminal escaping.
Owners must also sanitize exception/error text before exposing or persisting it.

Search integration exports:

- `READ_REDACT`: the Architecture 04 path patterns.
- `search_exclusion_args()`: argv pairs --glob !pattern for rg, never shell text.
- `path_is_redacted(path)`: lexical sensitive-file/directory detection.
- `search_result_allowed(path, repo_root=..., mode=...)`: post-filter lexical and
  canonical paths, including secret aliases, escapes and marked private subtrees.

Apply exclusions before searching, then the post-filter before exposing, indexing,
spilling or caching any search rows. Do not persist unfiltered rg output. Use the
same path checks for read/list handling. Configurable extra policy patterns and
Part 1's final search schema remain owner handoffs; the defaults here match the
documented list. A positive path result does not replace content scanning.

## Remaining integration and verification

Part 1 owns read/search/list/output-gate wiring, trusted Source construction, and
edit pre-image/REPLACE metadata. Part 2 owns web registration, journals and egress
events. Provenance and grants are session-local until durable journal/integrity
integration lands. All proposed types remain in this package pending a second
owner's agreement to shared contracts. Part 4 owns red-team/CI integration.

Synthetic fixtures check README.md:40 attribution, literal thresholds and task
exemption, URL/host spelling and exceptions, steered network denial, new imports,
consent invalidation, raw Git revision/remote attribution, credential formats,
stable hashes/idempotence, multiline offsets, fake-marker resistance, path globs,
canonical post-filtering, and command-result sanitation. No real credential is
used by these fixtures, and no test sends a network request.

Verified on Windows / Python 3.14: the complete Phase 0-3 run passed 96 tests and
109 subtests. After the final malformed-quote/control-preview adjustments, the
focused approval/redaction rerun passed 56 tests and 76 subtests, including the
additional quoted-value case (97 distinct tests verified across the runs). Ruff,
compileall, import smoke and Git whitespace checks passed. Test fixtures deny
console confirmation by default and override it only with explicit fake answers.
No runtime dependencies were added.
