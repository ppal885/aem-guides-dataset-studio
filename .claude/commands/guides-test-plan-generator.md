---
description: Generate an evidence-grounded AEM Guides test plan from a Jira key.
argument-hint: GUIDES-12345
---

You are running the registered AEM Guides Test Plan Generator workflow for authorized Adobe team members.

Input Jira key or arguments:

```text
$ARGUMENTS
```

Steps:

1. Extract exactly one Jira key from `$ARGUMENTS`, for example `GUIDES-12345`. If no key is present, ask for one and stop.
2. Call the MCP tool `guides_test_plan_generator` with:
   - `jira_key`: the extracted key
   - `tenant_id`: `kone` unless the user provided another tenant
   - `evidence_k`: `8`
3. Use the returned MCP evidence packet plus `claude-skills/aem-guides-test-scenario-generator/SKILL.md`.
4. Generate the final test plan in this chat. Do not merely dump the packet.
5. Mandatory output requirements:
   - Include `## 4. Blast radius and risk analysis` exactly.
   - Perform blast-radius analysis before scenario design.
   - Cite official Experience League `source_url` or `canonical_url` values from the MCP packet.
   - Separate confirmed evidence from unknowns and assumptions.
   - Include R0 unchanged-behavior controls plus R1/R2/R3/R4 coverage where evidence supports it.
   - Cover or explicitly exclude every high/critical Direct, Shared-path, Downstream, Compatibility, and Observability/Recovery risk.
   - Mark the plan `Draft` unless evidence, traceability, and blast-radius gates are complete.
6. If a local plan file is written, validate it with `claude-skills/aem-guides-test-scenario-generator/scripts/validate_test_plan.py` before calling it review-ready.

Final answer should be the test plan, not setup instructions.
