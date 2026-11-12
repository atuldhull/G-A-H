# ADR-004: Anything that executes repo code needs approval

- **Status:** Accepted (new in v5, review 07 C1/H1/H12)
- **Context:** v4.1 ran `pytest --collect-only` in `quote`, and the reproduce, baseline and verification-ladder steps ran tests automatically. Collection imports `conftest.py`, so a malicious repo ran code before any approval. A green edit followed by an auto-run test also laundered code execution.
- **Decision:** pytest (incl. collection), repro/oracle and baseline runs, the ladder's test rung and ruff with repo config are commands. Only `tools/tests.py` may build a pytest argv. The test-runner argv is approved once per session behind a red "THIS EXECUTES CODE FROM THE REPO" panel listing conftest/config files and their hashes. Consent is voided by config changes or by an edit with a non-empty exec surface. `quote` is static. Ruff runs `--isolated --no-cache` with no fixes; fixes (P1) are an in-memory diff the user approves. Edits to test files and conftest are red.
- **Consequences:** + Closes the largest R4 hole; reward hacking via test edits is visible. − One extra red prompt per session; without consent the ladder stops at syntax/lint and the receipt says so.
