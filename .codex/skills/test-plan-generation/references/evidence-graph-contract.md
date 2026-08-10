# Evidence Graph Contract

- Run `query_test_evidence_graph` only after the three direct `ask_dita_expert` probes and both direct `search_jira_history` searches. The graph connects and ranks already-grounded evidence; it does not replace source retrieval.
- Keep Jira/UAC, inspected implementation, verified design, direct documentation, and live Jira validation above graph-derived findings. Surface conflicts and retain the direct source.
- Use graph results only when a path contains underlying leaf citations. A graph path ID is traceability metadata, never evidence by itself.
- A historical Jira is similar only when the graph and direct review establish a shared root cause, behavior contract, error signature, API route, configuration key, or strong symptom plus DITA/output mechanism. Customer, component, domain, and feature overlap are ranking boosts only.
- Candidate claims, generated fallback oracles, caution outcomes, and area-only links cannot define Expected Behaviour or an acceptance criterion.
- Fold accepted graph findings into the existing Expected Behaviour, Known Jira Bugs / Past Similar Tickets, Regression Areas, Automation Coverage & Gaps, and Open Questions sections. Never add an Evidence Graph section.
- Every acceptance criterion must end with `Evidence: <underlying Jira, URL/chunk, DITA source, Figma node, attachment, or inspected code citation>`. Never cite only a graph path.
- Deduplicate graph and direct evidence by leaf/source identifier before scoring or counting support.
- Record one influence mode: `off`, `shadow`, or `augment`. `shadow` is the safe default: query and audit the graph, but never let it change planning seeds, repository scope, scores, citations, Expected Behaviour, acceptance criteria, scenarios, regressions, or automation verdicts.
- Use `augment` only after the deployment's shadow audits pass. Even then, graph output can supplement direct evidence only when a deduplicated leaf source independently supports the claim; it can never raise source authority.
- Record `evidence_graph` in the evidence manifest with `requested`, `tool`, `status`, `influence_mode`, `used_for_plan`, `generation_id`, exact `queries`, unique `path_ids`, deduplicated `leaf_citations`, and query runtime/cache metadata. Each leaf citation records `leaf_id`, `source_type`, `source_ref`, and `trust_tier`.
- In `off` or `shadow` mode, `used_for_plan` must be false. A true value is valid only in `augment` mode and only when at least one underlying leaf citation was actually used.
- If the graph is disabled, unavailable, or degraded, record the reason and continue in degraded mode when authoritative direct evidence already covers the behavior. Do not make graph availability alone a Draft blocker.
- A query budget warning or cache miss is operational telemetry, not evidence and not a Draft blocker. Preserve the direct-source result when graph latency exceeds its budget.
- Respect tenant and role boundaries. Use ticket-level cross-customer evidence only when authorized; otherwise use aggregate, redacted cross-customer signals.
