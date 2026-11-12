# 02 · Components

## 1. Module layout

```
crocodile/
  cli.py          P0  typer app: run, quote, undo, audit, doctor, bench, redteam, budget show, init, admin
  ui.py           P0  rich renderables: status line, quote, banners, approval panels, receipt (ASCII fallback)
  config.py       P0  loads config/policy/prices from %APPDATA%\crocodile, limits from %PROGRAMDATA%\crocodile
  secrets.py      P0  keyring (Windows Credential Manager): VKs, Tavily key, HMAC key. Never os.environ
  integrity.py    P0  watch-set hashes + state.db HMAC; verify before every reserve and around every EXEC
  loop.py         P0  phase machine, step cap, stop-on-green, escalation hooks (~400 lines)
  taskstate.py    P0  pinned task state, rendered last in every prompt
  context.py      P0  cache-stable prefix, batched masking, fit-to-window; compaction hook (P1)
  outputs.py      P0  output gate: ANSI strip, pytest/traceback parsers, head+tail, must-keep, spill, secret scan
  editmatch.py    P0  SEARCH/REPLACE parser + staged matcher + "did you mean"
  verify.py       P0  oracle, verification ladder, format_failure, green check
  thrash.py       P0  error signatures, triggers, strategy ladder
  quote.py        P0  static quote (no execution)
  budget.py       P0  reserve / reconcile / cancel / lease, price tiers, ladder
  router.py       P0  rung → prefixed chain + fallbacks, confidential pin, ctx_window
  failover.py     P0  routing headers → RoutingInfo, error class, banner data
  egress.py       P0  the only HTTP client; socket guard; confidential asserts; egress log; canary scan
  journal.py      P0  append-only events in SQLite; replay; resume (hash chain P1)
  confidential.py P0  mode decision (realpath walk up + bounded scan down), sticky registry, model allowlist
  undo.py         P0  shadow git for file edits; P1: command side effects
  doctor.py       P0  user doctor (no admin creds, black-box probes); P1: admin doctor + signed attestation
  audit.py        P0  egress log + Bifrost logs + canary scan → PASS/FAIL
  tools/          P0  base.py fs.py search.py edit.py tests.py cmd.py git.py web_docs.py
  policy/         P0  engine.py paths.py procs.py gitsafe.py approve.py provenance.py
                  P1  explain.py (tree-sitter-bash); P0 keeps a minimal shell-script flagger
  repomap.py      P1  ast-based file list + top-level defs (no PageRank)
  localize.py     P1  rg + stack frames → files → symbols
  compact.py      P1  structured compaction on the cheap model
  bench/          P0  tasks.py runner.py grade.py race.py report.py mswea/ ; P1 waste.py
  redteam/        P0  fixtures/ + runner.py (MVP 10–15 cases); P2 hostile model stub
third_party/      P0  copied files with original headers + LICENSE; NOTICE at repo root
tests/            P0  unit + invariant + red-team tests
```

**Structural rules (enforced by AST lint tests in `tests/test_structure.py`):**
- Only `egress.py` imports `httpx`/`socket`.
- Only `tools/tests.py` may build a pytest argv. Only `policy/procs.py` calls `subprocess`.
- `egress.post_bifrost` requires a `reservation_id` in state `held`.
- No module reads `os.environ` for secrets, and nothing loads `.env`.

## 2. Responsibilities and dependencies

| Module | Depends on | Must never |
|---|---|---|
| loop | context, verify, thrash, tools, budget, router, egress, journal | decide policy or price itself |
| policy.engine | paths, procs, gitsafe, provenance, confidential, config | read prompt text other than tool args |
| tools.* | policy.procs, policy.paths, outputs, undo | spawn anything except via `procs.run` |
| budget | config, integrity, journal | allow a call without a held row |
| egress | secrets, journal, confidential | send without a reservation, send unprefixed model ids |
| verify | tools.tests (approval path), outputs | run pytest directly |
| confidential | config, journal | downgrade a repo id once confidential |

## 3. Public interfaces

```python
# tools/base.py
class Effect(Enum): READ="read"; WRITE="write"; EXEC="exec"; GIT_READ="git_read"; GIT_MUT="git_mut"; NET="net"

@dataclass
class ToolCall:   id: str; name: str; args: dict; steered_by: list["Source"]   # filled by provenance

@dataclass
class ToolResult: call_id: str; ok: bool; shown: str; spill: str | None        # "out:42"
                  raw_sha: str; untrusted: bool; tokens_shown: int; tokens_avoided: int; snapshot: str | None

class Tool(Protocol):
    name: str; effect: Effect; schema: dict          # frozen, sorted; no risk/approval fields
    def sensitive(self, args: dict) -> list[tuple[str, str]]   # (value, field_type) checked by provenance
    def run(self, args: dict, ctx: "RunCtx") -> ToolResult

# policy/provenance.py  (P0 provenance-lite)
@dataclass(frozen=True)
class Source: kind: Literal["file","cmd","web","search"]; ref: str; line: int | None
class ProvenanceIndex:
    def add(self, text: str, src: Source) -> None                    # every untrusted result; names are untrusted too
    def steered_by(self, fields: list[tuple[str, str]]) -> list[Source]
        # value (>= 8 chars, or any URL/host) found verbatim in untrusted text and NOT in the user's task text

# policy/engine.py
@dataclass
class Decision: verdict: Literal["allow","ask","deny"]; level: Literal["green","amber","red"] | None
                reasons: list[str]; steered_by: list[Source]; confirm_word: str | None; token: str | None
def decide(call: ToolCall, s: "Session") -> Decision

# policy/paths.py / procs.py / gitsafe.py / approve.py
def resolve_in_repo(p: str, root: Path, for_write: bool, s: "Session") -> Path    # raises PolicyDeny
def resolve_exe(name: str, root: Path) -> Path                                   # absolute, outside repo/cwd
def run(argv: list[str], root: Path, timeout: int, extra_env: dict | None = None) -> "Proc"  # job object, scratch profile
def git(args: list[str], *, work_tree: Path, git_dir: Path | None = None) -> "Proc"      # hardened, per-call cfg check
def validate_rev(rev: str, work_tree: Path) -> str                               # returns resolved SHA or PolicyDeny
def approve(d: Decision, batch: list[ToolCall]) -> bool                          # CONIN$ only
def token(call: ToolCall, resolved: dict) -> str                                 # sha256 of what will run

# tools/tests.py  (ADR-004)
@dataclass
class TestConsent: argv: list[str]; interpreter_sha: str; cfg_hashes: dict[str, str]; expires_at: float
def run_tests(ids: list[str], s: "Session") -> "TestReport"   # requires valid consent, else asks

# budget.py
@dataclass
class Reservation: id: str; principal: str; usd: float; model_ceiling: str; tier: str
                   est_in: int; bound_in: int; max_out: int; owner_pid: int; heartbeat: float
class Denied(Exception): remaining: float; needed: float; reason: str
def reserve(principal: str, route: "Route", prompt: "Prompt", s: "Session") -> Reservation
def reconcile(res: Reservation, usage: "Usage", actual_model: str) -> float
def cancel(res: Reservation, sent: bool) -> None        # sent → stays held until logs reconcile (06 §3)
class Ladder: rung: Literal["strong","cheap","local","pause"]
    def step_down(self, why: str) -> str; def escalate(self, why: str) -> str

# router.py / egress.py / failover.py
@dataclass
class Route: rung: str; chain: list[str]; fallbacks: list[str]; vk_alias: Literal["public","local"]
             data_label: str; phase: str; max_tokens: int; ctx_window: int
def plan(s: "Session", phase: str) -> Route
def post_bifrost(body: dict, route: Route, reservation_id: str, s: "Session") -> "BifrostResponse"
def count_tokens(body: dict, route: Route) -> int | None          # /anthropic/v1/messages/count_tokens
def parse(headers: Mapping[str, str], body: dict) -> "RoutingInfo"   # incl. error class of the primary

# verify.py / thrash.py / taskstate.py
@dataclass
class OracleSpec: test_ids: list[str]; file_shas: dict[str, str]; created_by: Literal["existing","agent"]
@dataclass
class VerifyResult: stage: Literal["syntax","lint","affected","full"]; ok: bool; sig: str | None; shown: str
def ladder(s: "Session", touched: list[Path]) -> VerifyResult
def is_green(s: "Session") -> bool          # oracle ids pass, no regression by id set, no new skip/xfail
class Thrash: def check(self, s: "Session") -> Literal["escalate","stop_report"] | None
@dataclass
class TaskState: task: str; oracle: OracleSpec | None; plan: list[str]; decisions: list[str]
                 failing: list[str]; phase: str; switches: int
    def render(self, max_tokens: int = 600) -> str

# journal.py / undo.py / integrity.py / confidential.py
def append(session: str, type: str, payload: dict) -> int
def replay(session: str) -> "SessionState"
def snapshot(root: Path, reason: str, call_id: str) -> str
def undo(root: Path, steps: int = 1) -> list[str]
def verify_state() -> None                 # raises IntegrityError → fail closed
def watch(call_id: str) -> ContextManager  # hashes watch-set before/after an EXEC
def mode_for(paths: list[Path]) -> Literal["public","confidential"]
def check_local_model(model_id: str, ollama_host: str) -> None   # raises ConfidentialDeny
```

## 4. Dependencies and borrowed components

| Package / source | Licence | Use | How |
|---|---|---|---|
| `httpx` | BSD-3 | only HTTP client (in `egress`) | library |
| `typer`, `rich`, `pyyaml`, `pydantic` v2 | MIT | CLI, UI, config validation | library |
| `keyring` | MIT | Windows Credential Manager | library |
| `tiktoken` | MIT | o200k estimate for OpenAI routes | library |
| `pytest`, `ruff`, `matplotlib` | MIT / MIT / PSF-style | oracle, lint rung, bench chart | tools |
| stdlib `sqlite3`, `difflib`, `hashlib`, `hmac`, `msvcrt`, `ctypes`, `ast` | PSF | ledger, matcher, integrity, console, exec surface | stdlib |
| mini-swe-agent 2.4.6 | MIT | **baseline only**, separate venv in WSL2 | never imported |
| Bifrost v2.5.1 | Apache-2.0 | gateway, unmodified | pinned binary |
| LiteLLM `budget_reservation.py` | MIT | reserve-max → reconcile → cancel idea | reimplemented |
| Aider `editblock_coder.py` | Apache-2.0 | staged matcher stages | reimplemented |
| SWE-agent `history_processors.py` | MIT | batched masking schedule | reimplemented |
| gemini-cli truncation/masking | Apache-2.0 | spill + tail-biased truncation | reimplemented |
| Codex `permissions.rs`, Gemini `commandSafety.ts` | Apache-2.0 | protected names, git option denials (as facts) | reimplemented |
| Roo `ShadowCheckpointService.ts`, OpenCode `git.ts` | Apache-2.0 / MIT | hardened shadow-git config | reimplemented |
| P1: OpenHands `shell_parser.py`, Aider `python-tags.scm` | MIT / Apache-2.0 | explainer, repo map | copied with headers into `third_party/` |
| **Not used:** `bashlex` (GPL), `shlex` for decisions, `python-dotenv`, `tavily-python` | — | — | — |

Copied files keep their header and LICENSE under `third_party/`; Apache sources get a NOTICE entry; GPL/AGPL/unlicensed code (incl. peer repos) is read only.

## 5. Tier summary by area

| Area | P0 | P1 | P2 |
|---|---|---|---|
| Loop | own loop, tools, step cap, pinned state, stop-on-green | localisation funnel, agent-written repro test, early termination | — |
| Tokens | cache-stable prefix, output gate, read cache, staged matcher, batched masking | compaction, repo map, quote refinement | — |
| R1 | prefixed chain + fallbacks, banner with error class, journal resume | breaker, local last-resort tail | — |
| R2 | reservation, lease, tiers, ladder, race demo, admin limits | hard input bound by bytes near limit | Postgres team ledger |
| R3 | marker/registry, local VK only, allowlist, Tavily off, egress log, canary audit | hash-chained egress log, DPAPI blob encryption | — |
| R4 | console approvals, argv-only, hardened git, test consent, provenance-lite, shadow-git file undo, integrity watch | command side-effect undo, tree-sitter explainer | full taint wallet, restricted-token sandbox |
