# ADR-006: Confidential mode = two keys + local model allowlist

- **Status:** Accepted (allowlist added in v5, review 07 C3)
- **Context:** Peers' "local-only" modes still held the cloud key, left web search on, or defaulted to cloud when a marker was missing. Ollama cloud models (`:cloud`, `-cloud`) are proxied by the local daemon, so a loopback check alone proves nothing.
- **Decision:** Mode is decided from realpaths before any prompt text is read, and is sticky per repo id. In confidential mode the client loads only the local VK (public VK and Tavily key never loaded, `web_docs` unregistered); the Bifrost local VK allows only Ollama. Model ids must be exact entries of a local allowlist; `:cloud`/`-cloud`/`/`/`@` tags and a non-loopback `OLLAMA_HOST` are refused in the client and in `doctor`. Every request is logged at the single egress point; `audit` checks the log, Bifrost logs and canaries.
- **Consequences:** + Two independent blocks plus an audit trail. − Local models are slower and weaker; context must be fitted to `OLLAMA_CONTEXT_LENGTH`; claims are limited to "the agent's egress".
