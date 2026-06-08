# DITA screenshot authoring — differentiation vs reference-only tools

This document tracks how **AEM Guides Studio** differentiates from generic “screenshot → topic” products (e.g. Oxygen-style reference generation) and what to build next.

## Shipped in codebase (this iteration)

| Capability | Rationale |
|------------|-----------|
| **AEM-aligned acceptance criteria** | Acceptance-style sections serialize as DITA **`<postreq>`** with an ordered list — closer to task completion / release-gate language than a generic `<section>`. |
| **Safe link guidance** | After generation, **`link_recommendations`** lists xref/conref/keyref issues and **map-first** actions without inventing repository paths. |
| **Screenshot + Jira + reference** | Optional **`jira_context`** on the authoring form is merged into the pipeline prompt (length-capped, validated), persisted on the user turn for **regenerate**, while the visible chat line stays the main instruction. |

## Prioritized roadmap

1. **Project-aware style memory (multi-reference)** — Persist aggregated `ReferenceStyleProfile` (or embeddings of structural habits) per tenant/project; merge N reference topics before serialization. *Architecture: session or project-scoped style store + versioned profile in trace/debug.*
2. **Map-aware insertion suggestions** — Parse active `ditamap` (or AEM TOC) and return “insert after topic X / under navtitle Y” as structured hints, not raw XML. *Architecture: map upload or CCMS path + graph of topicrefs.*
3. **Validation-driven auto-repair (structured)** — Expand repair stages with categorized diffs (already partially modeled via `ValidationDiffSnapshot` / repair API); tie repairs to acceptance criteria coverage. *Architecture: repair orchestrator + idempotent repair log in `debug`.*
4. **Structured observability & scoring** — Uniform metrics: vision confidence, validator delta, link-rec count, style adherence score; export per `authoring_trace_id`. *Architecture: metrics event sink + benchmark harness alignment.*
5. **Acceptance-criteria → task backlog** — Optional export of `<postreq>` items to JSON/work-item schema for Jira/Azure DevOps (outbound only, credentialed). *Architecture: separate integration service, no secrets in browser.*
6. **AEM Guides-specific optimizations** — DITAval snippets, keydef templates, conditional profiling hints in the semantic plan when tenant config enables them.

## Architecture hooks to keep stable

- **`ChatAuthoringRequestPayload`**: optional structured inputs (`jira_context`, later `map_context`, `style_memory_id`).
- **`ChatDitaAuthoringResult`**: machine-readable sidecars (`link_recommendations`, `debug` trace fields) for UI and benchmarks.
- **Governance**: continue hashing/redacting free text in logs; keep Jira paste under the same injection/control-char validation as other chat inputs.
