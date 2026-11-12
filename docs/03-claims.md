# 03 · Claims sheet

Only these wordings may appear in the README, pitch, slides and video. Rules:
- A claim about Crocodile is allowed **only if the feature is in the repo on 15 Nov** and has a passing test. P1/P2 items go on a "Roadmap" slide.
- Our numbers come only from `bench/report.md`, `crocodile bench race` and `crocodile redteam` output, each with model, task set, n, runs, date and Bifrost version. Receipts are "estimated, first-order".
- Never name peer teams. Describe peer weaknesses as attack classes.

## 1. Our results (placeholders until 14 Nov 18:00)

| Topic | Wording | Source |
|---|---|---|
| Headline | "On `<n>` Aider Polyglot Python tasks with `<model>` through Bifrost (`<runs>` independent runs, `<date>`), Crocodile's cost per solved task was $`<x>` vs $`<y>` for mini-swe-agent." | `bench/report.md` |
| Savings | "On tasks both agents solved, Crocodile cost `<r>`× as much per task (95% CI `<lo>`–`<hi>`)." | paired cost ratio |
| Accuracy | If the CI lower bound > −10 pp: "Pass rate `<a>`% vs `<b>`%: not worse by more than 10 points (paired bootstrap CI)." Otherwise: "Pass rate `<a>`% vs `<b>`%; the difference is inconclusive at this sample size." | paired diff |
| Bug-fix set | Same three rows for QuixBugs (`<m>` tasks), labelled "secondary set". | `bench/report.md` |
| Levers | "Against the same agent with every lever off, the levers cut cost per solved task by `<z>`% at a pass rate of `<c>`% vs `<d>`%." | all-off twin |
| Budget race | "8 processes, mock gateway latency, one $0.02 budget: overshoot $0.0000 with reservation, $`<n>` with check-then-record." | `bench race` |
| Red team | "`<k>` of 15 red-team cases pass (list in the repo)." | `crocodile redteam` |

## 2. Feature claims (allowed once built and tested)

| Feature | Wording |
|---|---|
| Budget | "Every model call reserves money atomically before it is sent, priced at the most expensive model that could answer; a reservation never exceeds what is left." |
| Ladder | "At the limit, Crocodile steps down strong → cheap → local and then pauses; it never overspends." |
| Failover | "When Bifrost fails over, Crocodile says which model took over and why (error class), and the session continues." |
| Confidential | "In a confidential repo the process never loads a cloud key, only allowlisted local Ollama models are accepted, and web search is off." · "`crocodile audit` showed zero canary hits and no cloud requests in the agent's egress for confidential sessions." |
| Approvals | "Reads are free; writes, commands, test runs and git mutations need a console approval the model cannot answer." · "Commands are argv lists; no shell string is ever auto-approved." · "Running the repo's tests is treated as running the repo's code and needs approval." |
| Provenance | "If a command or URL the model proposes appears literally in untrusted text read this session, the prompt turns red and names the file and line." |
| Git | "Our own git calls run with hooks, fsmonitor and external diff disabled, and repo git config is re-checked before every git call." |
| Undo | "`crocodile undo` reverts file edits" (P0). "…and what commands changed" only if P1 #1 ships. |
| Correctness | "Tests are the oracle: the model never declares success; we stop as soon as the frozen tests pass with no regressions." |
| Integrity | "Agent state is integrity-checked on every call; tampering stops the session." Always with: "a determined process running as the same user can still bypass local checks; the gateway budget is the independent cap." |

## 3. External facts (with sources)

| Topic | Wording | Source |
|---|---|---|
| Model self-estimates | "8 frontier models predicting their own token use on SWE-bench Verified reach a Pearson r of at most 0.39, and all underestimate." | arXiv 2604.22750 |
| Trace-based routing | "Routing after 2 cheap-model turns scored Route-AUC 0.780 vs 0.627 for query-only routing." No $ figure. | arXiv 2607.00053 |
| Early termination | "EET cut cost by 19–55% (mean 32%) across 3 agents on SWE-bench Verified with ≤ −0.2 pp resolve-rate change." | arXiv 2601.05777 |
| Masking | "Masking halved cost in all 5 configs; solve rate equal or better for two models, lower for two (−2 pp, −4 pp)." | arXiv 2508.21433 |
| Bifrost budgets | "Bifrost's pre-check compares current usage with the limit without estimating the incoming request and books usage after the response, so concurrent requests can overshoot; exhaustion returns HTTP 402." | source, research/06 §2.1 |
| Bifrost fallbacks | "Explicit fallbacks fire on any primary error; unprefixed model names get inferred cross-provider fallbacks, so we always send prefixed ids and an explicit list." | source, research/09 §1.5 |
| Ollama cloud | "Ollama's local daemon can proxy `-cloud` models to ollama.com, so 'runs on Ollama' does not by itself mean 'stays local'." | Ollama docs, research/07 C3 |
| Caching prices | "Anthropic cache reads cost 0.1× input on Haiku 5.5 (0.05× on Sonnet/Opus 5.5); 5-minute writes cost 1.25×." | Anthropic pricing, research/09 §5 |
| Git config RCE | "An allowlisted `git show --output=.git/config` followed by `git diff` gave RCE in Codex CLI (fixed 0.95.0); `core.fsmonitor` ran code when Goose ran `git diff` (CVE-2026-72718)." | research/05 |
| Budgets need outside enforcement | "Ramp Labs found agents ignored a budget-request tool entirely (0 calls in 5,000+ turns)." | research/02 |

## 4. Never use

- "We solve more", "no accuracy loss", "same accuracy", "significant" (unless `bench/report.md` supports exactly that).
- "X% fewer tokens" without the pass rate next to it.
- "45 public bypasses/CVEs", "hostile model stub", "taint wallet", "hash-chained ledger", "undo of command side effects", "tree-sitter explainer", "sandbox", until each exists.
- "tamper-proof", "cannot be bypassed", "proves no bytes left the machine" (say "in the agent's egress").
- "Our approval prompt cannot be keystroke-injected" (untested).
- "seeds" for Anthropic runs (say "independent runs").
- "First agent with failover / spending limits / local-only mode / audit log / undo".
- "−32% from trace-based escalation"; "tiktoken undercounts Claude by 15–20%".
- Any peer team's name.
