# ADR-005: Reservation priced at the chain maximum

- **Status:** Accepted (refined in v5, review 07 H7/H8)
- **Context:** Check-then-record budgets (peers, and Bifrost itself) overshoot under parallel sessions. Failover can switch to a pricier model; long prompts hit higher price tiers; timeouts may still be billed.
- **Decision:** Before every call, atomically (`BEGIN IMMEDIATE`) reserve `worst input price × input estimate + output price × max_tokens`, maximised over every chain member at the tier of the counted prompt (unknown count → highest tier). Shrink `max_tokens` before refusing; a reservation never exceeds remaining. Near the limit, bound input by request bytes. Held rows use leases, not TTLs; a sent-then-failed call stays held until Bifrost logs settle it. Egress refuses calls without a held reservation. Limits come from admin-only `limits.yaml`; the VK budget is the server-side cap.
- **Consequences:** + Σ settled + held ≤ limit by construction; 0 overshoot in the race demo; failover cannot overspend. − Pessimistic reservations step down earlier near the limit; the single-machine demo only binds an honest user (stated).
