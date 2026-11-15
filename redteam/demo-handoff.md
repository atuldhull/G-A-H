# Recording gate and repeatable verification

The team confirmed on 2026-11-15 that feature freeze has **not** been declared.
Neither final clip has been recorded. Freeze, the build SHA and frozen demo
numbers must be recorded before capturing final footage.

Run `python -m redteam.runner --report security-report.json` using Python 3.12
installed outside the repository. The command exercises the normal Typer CLI
in disposable repositories with scripted model responses, synthetic credentials
and the real security handlers. It returns 1 for test failures and 2 when any
architecture case is blocked. A successful CI job can contain blocked cases;
read the artifact's per-case verdicts. These fixtures are not live-provider proof.

After freeze, record these two clips on the verified build:

1. Approval/red prompt: use a disposable README with the suggested command on
   line 40. Show the normal `run` path reading that line, the red approval with
   `README.md:40`, refusal, and an absent harmless execution indicator. Use a
   non-network command: a README-steered network action is denied before a prompt.
2. Confidential audit: with real local Bifrost and an installed allowed Ollama
   model, run a confidential synthetic task requesting cloud inference/web search.
   Show the local route, empty fallbacks, refused web search, then export the
   gateway records and run `crocodile audit --help` and the corresponding audit
   command with those records. Require matched client/gateway request IDs and
   actual Ollama provider evidence, zero confidential Tavily sends and canary hits.

Before recording, run root help and each command's help against the frozen build
to confirm arguments. Before sharing, inspect footage and transcripts for keys,
tokens, private paths and unrelated data; run text transcripts through
`crocodile.security.secrets.secret_scan`. Do not display credential-manager output.
Keep the build SHA, commands, exit statuses, evidence artifact and timestamps
beside the clips. Missing gateway records or unavailable services remain blockers.
