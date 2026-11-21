# Submission form text

## Short description (under 150 words)

Crocodile is a terminal coding agent that fixes code until the tests pass, with as few tokens as possible,
and asks before it runs anything. Ten switchable levers cut waste: it never re-sends unchanged files,
compacts test logs, loads only the files the failing tests point to, and stops the moment tests go green.
Every model call goes through the Bifrost gateway with a virtual key, a budget and a cost log; Tavily
provides documentation search. Running repository code needs a typed approval, private repositories stay
on a local model, and each call reserves its cost before it is sent. On 54 benchmark tasks with the same
model, Crocodile solved 104 of 108 runs with 4.6× fewer tokens than mini-swe-agent (a limited run). Its
red-team suite passes all 15 attack groups.

## Problem and approach

Coding agents waste tokens (re-reading files, resending long test logs) and act without asking: they run
repository code, can send private code to the cloud and have no hard spending cap. Crocodile enforces four
rules in application code the model cannot reach: fewer tokens, asks first, private stays local, spend is
capped. Each rule has a test or a measured result behind it.

## Technologies

Python 3.12, Typer/Rich, pytest, SQLite and HTTPX; Bifrost v2.5.1 as the gateway; Gemini 3.5 Flash-Lite
(cheap tier) and Flash (escalation); a local Ollama model (qwen2.5-coder:7b) for confidential
repositories; Tavily for documentation search; mini-swe-agent 2.4.6 as the benchmark baseline.

## How AI is used in the product

The model proposes code actions; code, not the model, handles approval, execution, verification, budgets
and routing. The cheap model goes first, deterministic checks (syntax, lint) avoid model calls where
possible, and the receipt reports the calls avoided.

## Links

- Code: https://github.com/atuldhull/G-A-H
- Demo video: https://www.youtube.com/watch?v=TlRELesKAsM
