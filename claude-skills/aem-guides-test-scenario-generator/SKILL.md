---
name: aem-guides-test-scenario-generator
description: >
  Deprecated compatibility alias for AEM Guides Test Plan and Pre-UAC requests. Delegate every
  request to the canonical test-plan-generation skill; do not run the former packet-driven,
  three-section, score-routed workflow.
---

# Deprecated Compatibility Alias

This skill no longer owns Test Plan reasoning, retrieval policy, acceptance criteria,
validation, rendering, persistence, or Jira mutation.

For every invocation:

1. Load and follow the installed `test-plan-generation` skill in full.
2. Use its canonical evidence manifest, reasoning contracts, preflight receipt, canonical runtime,
   final renderer, and authorization rules.
3. Route any retained packet or backend response through `CanonicalTestPlanRuntime`; treat the
   result only as normalized evidence or a compatibility projection.
4. Never call the former legacy composer, score router, validator, registry writer, or
   three-section renderer as an independent generation path.
5. Never publish, index, save, or post to Jira unless the canonical runtime completed, all canonical
   gates passed, the output is bound to the verified input artifacts, and the requested mutation has
   its required authorization.

This alias contains no independent scripts, references, validator, renderer, or evaluation path.
If the canonical skill is not installed or cannot be loaded, stop and report that the compatibility
alias cannot safely run.
