# Submission text (form fields)

## Short description (≤150 words)

Crocodile is a terminal coding agent built to get correct, test-verified work done on the fewest tokens. It keeps prompts cache-stable, preloads only the files the task and tests point to, trims tool output to what matters, and stops the moment the frozen tests pass. Failed attempts that do not improve the test count are rewound out of the conversation, so dead ends stop costing tokens. Every model call goes through Bifrost with a budget reserved before the call, so a user can never overspend; failovers are announced with their cause. Confidential repositories stay on local Ollama models, and writes, commands and test runs need console approval that no prompt can answer. Tavily supplies documentation search on demand. We measure cost per solved task against mini-swe-agent and the same agent with every optimization off, on the same model and gateway. Results: `<from bench/report.md>`.

## Problem

Coding agents waste most of their tokens: re-reading files, carrying old tool output, failed attempts that stay in context, and extra turns after the work is already verified. Teams also need hard limits on spend, privacy and actions that a prompt cannot override.

## Technologies

Python 3.12, Bifrost v2.5.1 (gateway: virtual keys, fallbacks, governance, logs), Tavily (search API), Gemini 3.5 Flash-Lite/Flash, Ollama (qwen2.5-coder) for local-only work, SQLite (budget ledger, journal), pytest, Typer/Rich.

## How AI is used

A cheap model works first and escalates to a stronger one only on evidence (repeated failures, stalls), with the reason printed. A local model handles confidential repositories. Tavily is used for third-party API documentation, one approved query at a time. Deterministic checks (syntax, lint, tests, read cache) replace LLM calls wherever possible; the receipt counts the calls avoided.

## AI tools used to build it

Claude Code (Anthropic) assisted with research, design and coding. The team reviewed and tested every change.
