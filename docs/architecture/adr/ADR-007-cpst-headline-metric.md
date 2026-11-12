# ADR-007: Cost per solved task is the headline metric

- **Status:** Accepted (statistics refined in v5, reviews 08/09)
- **Context:** "X% fewer tokens" ignores accuracy; a cheap agent that fails is not cheap. With n ≈ 34 tasks, pass rates cannot be separated statistically.
- **Decision:** Headline = CPST (Σ $ over all tasks ÷ solved) plus the paired cost ratio on jointly solved tasks, with pass rate framed as **non-inferiority** (paired bootstrap CI, margin −10 pp). Baseline = mini-swe-agent with the same model, gateway, task text, caps and one price table applied to Bifrost logs; second reference = our all-off twin. Every lever is kept only if pass rate holds.
- **Consequences:** + A defensible, judge-checkable number. − Savings against a lean baseline may be modest; the narrative for each outcome is pre-agreed in [10](../10-evaluation.md).
