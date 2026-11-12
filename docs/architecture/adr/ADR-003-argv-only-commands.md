# ADR-003: Argv-only commands, no shell-string classification

- **Status:** Accepted
- **Context:** Public bypasses of "read-only shell" allowlists (lone `&`, newline, `$()`, wrapper programs) hit Gemini CLI, Cline forks, Roo Code, Codex and Claude Code, and peers repeat the bug. Parsing a shell string correctly is not achievable in our time box.
- **Decision:** `run_cmd` takes `argv: list[str]` and runs with `shell=False` after absolute exe resolution. No command string is ever auto-approved; every `run_cmd` is at least amber. A shell or interpreter with `-c` is shown verbatim with "unparsed script" (tree-sitter explainer is P1, display only). Free exploration uses in-process tools and fixed git read templates. `shlex` is never used for decisions.
- **Consequences:** + The whole bypass class lands in ASK, never ALLOW. − More prompts; mitigated by free in-process reads and the per-session test consent (ADR-004).
