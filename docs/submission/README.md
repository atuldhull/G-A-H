# Submission pack: Crocodile (Team Crocodile, PS-01)

Final submission materials for Global AI Hackathon 2026, problem statement PS-01, as of 21 Nov 2026.
The numbers here are the same as in the [project README](../../README.md), the demo video and the slides.

| Item | Where |
|---|---|
| Demo video (2:08, unlisted) | https://www.youtube.com/watch?v=TlRELesKAsM |
| Short description and form text | [description.md](description.md) |
| Video scenes and what each shows | [demo.md](demo.md) |
| Benchmark status and evidence | [benchmark-status.md](benchmark-status.md) |
| What was checked before submission | [checklist.md](checklist.md) |
| Code | `main`, commit `75b8a7e` and later documentation commits |

## In one paragraph

Crocodile is a terminal coding agent that fixes code until the tests pass, with as few tokens as possible,
and asks before it runs anything. Every model call goes through the Bifrost gateway; Tavily provides
documentation search. On 54 benchmark tasks with the same model, it solved 104 of 108 runs with 4.6× fewer
tokens than mini-swe-agent and 2.6× fewer than its own savings-off twin (a limited run; see
[benchmark-status.md](benchmark-status.md)).

## Team

| Part | Owner | Area |
|---|---|---|
| 1 | Atul | Agent loop, tools, token levers, receipts |
| 2 | Vivek | Bifrost gateway: egress, failover, budgets, local routing, Tavily |
| 3 | Ritika | Security: approvals, confidential detection, sealed state |
| 4 | Tharun | Benchmark harness, red-team suite, terminal UI, submission |
