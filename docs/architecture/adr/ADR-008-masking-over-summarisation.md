# ADR-008: Masking over summarisation

- **Status:** Accepted
- **Context:** Observation masking halved cost in published experiments (arXiv 2508.21433), while LLM summaries made trajectories longer. Per-turn rewrites break the prompt cache.
- **Decision:** P0 uses batched, recoverable masking of old tool outputs (the stub keeps exit code, error signature and spill handle), only when the saving beats the cache rewrite. Compaction by a cheap model is P1, token-triggered, must shrink and must keep every must-keep line. The pinned task state is never masked or compacted.
- **Consequences:** + Cheap, deterministic, cache-friendly. − Very long sessions may still need compaction (P1) or a hand-off capsule.
