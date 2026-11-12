# ADR-002: Our own loop, not a fork of mini-swe-agent

- **Status:** Accepted
- **Context:** The rules require the core to be built during the hackathon. mini-swe-agent is ~100 lines and would be quick to fork, but it is also our baseline, and it executes model-written shell strings, which our approval model forbids.
- **Decision:** Write our own ~400-line loop with structured tools (`read`, `search`, `list`, `edit`, `run_tests`, `run_cmd` as argv, `git`, `web_docs`). Use mini-swe-agent **only as the baseline**, in a separate venv (WSL2), never imported. Credit the idea of a linear message history in NOTICE.
- **Consequences:** + Clear "built here" story; the bench compares two different agents, not a fork with patches; approvals are enforceable per tool. − 2–3 h of build time; we own all loop bugs.
