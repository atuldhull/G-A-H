# Merged benchmark API inspection

Inspected source revision: `89fba6a2d646cd0bd6b9745dbc0522695cf3e4d6`
(`origin/main`, team merge incorporating Person 4). `person-4` fast-forwarded
from `88a68edd421898167a19864f0b5f389571f6da4a`; all existing Person 4 commits
remain ancestors. No conflicts occurred. The shard milestone changes no other
owner's implementation or shared contracts. These are source-inspection findings,
not claims of a live integration test, security review, or benchmark result.

## Present agent and security entry points

`crocodile.loop.Agent` has this constructor:

```python
Agent(repo: Path, task: str, *, oracle: list[str] | None = None,
      full_suite: bool = False, flags: set[str] | None = None,
      tier: str = "cheap", approve_mode: str = "ask", step_cap: int = 30,
      user: str = "default", on_event=None, security_session=None)
```

`Agent.run() -> crocodile.loop.Receipt`; `Receipt.to_json() -> dict` preserves
`session`, `solved`, `status`, `steps`, `usage` (`prompt_tokens`,
`completion_tokens`, `cached_tokens`), `models`, `fallbacks`, `escalations`,
`tokens_avoided`, `test_runs`, `wall_s`, `cost_usd`, `stubs`, `flags`, `rewinds`,
`checkpoints`, and `savings`. `agent.s.id` is the agent session ID. Passing
`flags=None` enables all agent flags; `flags=set()` disables them. `step_cap=30`
is supported. There is **no overall wall-clock deadline/cancellation argument**;
the receipt's `wall_s` is elapsed measurement, not a 600-second enforcement API.
The `on_event(kind, data)` callback is notification, not a hard interruption API.

`from crocodile.security import ApprovalSession` exposes:

```python
ApprovalSession.for_bench(repo_root: Path, *, parent: Path | None = None,
                         user_task: str = "", events: list[dict] | None = None,
                         integrity=None, confidentiality=None)
sec.repo_root        # existing root; identity pinned by device/inode
sec.bench_auto       # active automation authority
sec.close_bench()    # revoke authority; must be called in finally
```

`for_bench` requires an **existing empty direct child** of the trusted parent,
rejecting links. Construct it before task copying and populate that same root
in place; never delete/recreate the pinned directory. The default parent is OS
temp. Bench auto is public-only disposable-workspace authority, not an OS sandbox.
Integrity/confidentiality managers are optional parameters, not automatic proof
of protected ledger initialization. See `crocodile/security/BENCH.md`.

`Agent(..., approve_mode="auto", security_session=sec)` calls
`SecurityBridge.bind_session(agent_session, sec)` and verifies the repo roots
match. The official bound bench session uses Part 3 approval/command permits.
Unbound `auto` still has a plain-runner bypass in the current adapter; an official
future harness must refuse to use that route. The adapter's introductory comment
describes older bypass behavior; the actual bound-session branch is authoritative.

Other present security APIs include:

```python
approvals.ask(action: Action, *, session: ApprovalSession | None = None) -> Decision
cmd.run(argv, cwd, *, timeout, session=None, action=None, decision=None) -> CmdResult
confidential.mode_for(repo_path, *, cwd=None, tool_paths=(), root=None,
                      store=None, session_id=None, force_confidential=False) -> Mode
```

`crocodile.security.git.Git`, `paths`, `secrets`, `integrity.StateIntegrity`, and
`integrity.WatchSet` implementations are also present. No security cases are
enabled by this inspection; Person 3 review of the red-team expectations is
still pending.

## Present gateway and bench entry points

The agent uses `crocodile.services.get(name)`, `override(name, impl)`, and `reset()`
with adapters in `crocodile.adapters`. Getting live services can initialize state
databases and credential access. This milestone does **not** call these APIs.
`GatewayEgress.chat(messages, tools, *, session, tier, max_tokens=4096,
temperature=0.0)` maps the agent session to the gateway session string.

The concrete Part 2 API is:

```python
EgressClient(bifrost_base_url="http://127.0.0.1:8080", budget_manager=None,
             journal=None, price_table=None, canaries=None)
client.chat(messages, tools=None, *, session="default-session",
            principal="default-principal", chain=None, fallbacks=None,
            vk="stub-vk", vk_alias="public", mode="public", tier="default",
            max_tokens=2048, temperature=None, mock_response=None) -> ChatResult
EventJournal(db_path).append(session: str, event_type: str, payload: dict) -> int
EventJournal(db_path).get_events(session: str) -> list[dict]
EventJournal(db_path).resume(session: str) -> State
PriceTable.from_yaml_file(path) -> PriceTable
price_table.calculate_cost(model_id, prompt_tokens, completion_tokens,
                           cache_read_tokens=0, cache_write_tokens=0,
                           cache_write_ttl="5m") -> float
```

The outbound gateway source sets `x-bf-session-id` from `session`. This is the join
key a future runner/exporter must preserve with receipt and plan run IDs. The
Part 2 journal uses three append arguments; it is not the older two-argument
shared protocol. Gateway accounting/state databases are not authoritative Bifrost
`logs.db` exports. No database was opened or altered for this inspection.

Existing Part 4 APIs remain:

```python
prepare_workspace(source, destination) -> Path
grade_exercise(original, final, output, *, task_id, timeout=180, test_paths=()) -> dict
build_plan(task_index, *, polyglot=None, quixbugs=None, dataset_set="both",
           limit=None, runs=2, shard=None) -> dict
write_manifest(plan, output) -> Path
calculate_report(plan_path, results_path, logs_path, prices_path, *, seed) -> dict
```

## Remaining execution blockers

Follow-up: the [runner milestone](runner.md) implements the in-place preparation
and durable execution/evidence portions of items 1 and 4 below, using the present
Agent and bench-session APIs. The list records the original inspection findings;
hard deadlines, gateway fairness, authoritative cost export and mini remain open.
`populate_workspace(source, existing_empty_destination)` now preserves the pinned
root, while `prepare_workspace` retains its original new-destination contract.

1. **In-place preparation:** `prepare_workspace` currently rejects an existing
   destination, while `for_bench` requires an existing empty pinned root. Add a
   separately tested in-place preparation mode/adapter under `bench/` before
   wiring the runner. Deleting/replacing `sec.repo_root` is not a valid workaround.
2. **Hard time cap:** the Agent accepts the 30-step cap but has no overall
   600-second deadline/cancellation API. Coordinate a supported interruption and
   cleanup mechanism with Part 1; notification callbacks alone cannot stop a
   blocked model/tool call. Do not claim the plan cap is enforced yet.
3. **Gateway fairness:** the default agent adapter selects public/local aliases,
   allows tier escalation/fallback chains, and forwards `temperature=0.0`.
   Official plans require the bench alias, same pinned model/effort, no sampling
   parameters, explicit cache policy and appropriate shared budget/integrity
   lifecycle. Agree an injected gateway configuration with Parts 1–3 before live
   execution. Do not change owner defaults or access keys for this milestone.
4. **Durable runner/evidence:** add isolated per-run setup, finally-close,
   agent-reported versus graded solved fields, serialized receipt/session IDs,
   resume/deduplication and error/timeout evidence. No runner is wired here.
5. **Cost attribution:** implement a read-only Bifrost `logs.db` exporter with
   verified session/VK attribution and complete late/failure usage, then price it
   with the agreed snapshot. Missing/ambiguous rows remain incomplete. Compare
   receipt and log-based costs, flag differences above 1%, and never promote the
   receipt to authoritative cost. The current `prices.yaml` is native Part 2 YAML;
   the offline reporter expects a normalized JSON-compatible YAML interchange
   with provenance metadata and disjoint usage categories. An adapter is needed.
6. **Grading/oracle argv:** the independent grader restores original tests and
   configs, but uses fixed `python -m pytest -q`; planned custom arguments (such as
   bitcount timeout) need alignment. Agent `oracle` is a list of pytest targets,
   not the planner's complete executable argv. Keep the two distinct.
7. **Mini and full-suite assembly:** no mini-swe-agent runner/WSL path adapter is
   implemented. Preserve two Crocodile, two mini, one all-off planned runs per
   task; never silently replace mini. Review the real 34/20 index, revisions and
   dependencies; join all four shard manifests/results by identical full-plan
   identity and unique run IDs before publishing a full-suite report.

The merged `bench/race.py` needed a minimal lint cleanup: defer gateway imports
until its functions are called (after its existing standalone path bootstrap),
and remove an unused timer assignment. No race, agent, benchmark exercise, paid
model call, Bifrost database, or credential operation was executed for this work.
