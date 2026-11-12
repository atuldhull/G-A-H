# ADR-001: Bifrost is the only path to any model

- **Status:** Accepted (v5, 12 Nov 2026)
- **Context:** PS-01 sponsors Bifrost. We need per-user keys and budgets, provider failover, usage with cached-token counts, and logs we can audit. Calling providers directly would duplicate all of that and leave no server-side cap.
- **Decision:** Every model call goes through Bifrost v2.5.1+ on `127.0.0.1:8080` via `egress.py`, with a per-user virtual key, a provider-prefixed model id and an explicit `fallbacks` list. No provider SDK or key lives in Crocodile's process. Bifrost `max_retries: 0`; the client owns retries.
- **Consequences:** + Server-side VK budget as an independent second wall; failover and routing info for free; one log source for bench costs. − Bifrost's own budget check can overshoot under concurrency (so we add our reservation, ADR-005); fallbacks fire on any error, so we must classify errors for the banner; we depend on a pinned version and must verify several behaviours on day 0 ([09](../09-bifrost-and-tavily.md) §6).
