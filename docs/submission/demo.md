# Demo video

**https://www.youtube.com/watch?v=TlRELesKAsM** (unlisted, 2:08, 1080p, burned-in subtitles).

Each team member presents two scenes. The terminal scenes are real runs recorded on 20 Nov 2026 on a small
demo project (`pricing.py` with 3 bugs and 3 tests), with the person at the keyboard answering the
approval prompts. Nothing is mocked; the cards show real test output and real gateway logs.

| Time | Presenter | Scene | What is on screen |
|---|---|---|---|
| 0:00 | Atul | Introduction | Title card, the README |
| 0:13 | Ritika | The problem | 3-task development pilot: 8.1K vs 63.2K tokens per task |
| 0:31 | Atul | Live fix | Quote (~$0.006 estimated), typed test approval, one edit, tests green: solved in 1 step, 1,588 + 147 tokens, $0.0008439 |
| 0:46 | Ritika | Declining approval | Typed `n` at the test prompt: `TESTS NOT RUN (no consent)`, `UNVERIFIED`, never a fake pass |
| 0:59 | Vivek | Bifrost and confidential mode | Bifrost's own log of the two runs (including a 503 that was retried); 5 confidential-mode tests passing |
| 1:12 | Vivek | Budgets and Tavily | 7 budget and Tavily tests passing |
| 1:31 | Tharun | Results | Pilot table, then the 54-task results |
| 1:50 | Tharun | Proof and links | Receipt cost equals Bifrost's logged cost; red-team 15 / 15; repository link |
