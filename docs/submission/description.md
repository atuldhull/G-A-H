# Submission form copy — review pending

## Short description (under 150 words)

Crocodile is a terminal coding agent with console approvals, test verification
and Bifrost gateway integration. Its code includes budget reservations,
confidential-routing checks, static task quotes and session receipts. Reviewed
deterministic red-team tests exercise the real owner APIs: Windows CI passed all
15 architecture groups; Ubuntu passed 13 and skipped two platform-dependent
groups. Gateway tests use an in-memory transport, not paid model calls. The
benchmark harness prepares isolated tasks, restores original tests for independent
grading, and records incomplete evidence explicitly. Its Gemini v4 plans validate
54 tasks and 270 planned slots. Comparable benchmark results remain incomplete;
we make no claim about savings, cost per solved task or completed benchmark
coverage. A live demo recording and final owner review are still pending.

## Problem and approach

Coding-agent teams need visible decisions about executing repository code,
private-data routing and spending. Crocodile implements those decisions in
application code around the agent. Tests provide evidence for specific refusal,
routing and integrity behaviors; they do not establish universal security or
benchmark efficiency.

## Technologies

Python 3.12, Typer/Rich, pytest, SQLite and an HTTPX Bifrost adapter; the benchmark
policy targets Bifrost v2.5.1 and Gemini Flash-Lite. Confidential routing targets
allowlisted local Ollama models. Tavily integration exists and is refused in
confidential mode; no live Tavily demo is claimed here. mini-swe-agent 2.4.6 is the
separate planned baseline, not a completed comparison.

## AI use and disclosure

Models propose coding actions; code handles approval, execution and verification.
Person 4 used OpenAI Codex for implementation, tests and these submission
materials. Other team members must confirm their own development-assistant
disclosures before submission. Do not claim that every team change has received
human review or name an additional assistant without owner confirmation.

## Fields still needing owner input

Atul: reviewed live agent clip and final form/track/deadline confirmation.
Vivek: sanitized native routing and closed-session evidence, budget/failover
recordings. Ritika: review the approval/confidential clips. Person 4: assemble and
review the final video; all public URLs, uploads and external submission remain
pending. See [checklist](checklist.md).
