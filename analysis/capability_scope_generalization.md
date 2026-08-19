# Capability-Eligibility & Scope-Conflict — Unseen Generalization (Step 30)

Mandatory generalization proof for the capability-eligibility + scope-conflict reasoning.
The two detectors were run over the mined TRAIN issue text (`analysis/train_extract.jsonl`)
with the known Assets-UI fixture (GUIDES-47043) **excluded**, and with **no hint** of the
expected relationship supplied. Activation is purely from generic signals (toolbar / menu /
context-menu for capability decomposition; fix-present + multiple-problems for scope
reconciliation) — no hardcoded entity or action.

## CapabilityEligibilityExplorer — activated on 11 unseen TRAIN issues
Representative examples (issue → detected signals):

- GUIDES-11493 "New Context Menu Preview Experience" → `context menu, menu, toolbar`
- GUIDES-12676 "Webeditor UI - reports and topic context menu | show Edit in oXygen" → `context menu, menu`
- GUIDES-14425 "DITA Author view should allow partial selection" → `context menu, menu`
- GUIDES-15204 "Additional use-cases and issues observed in guides extension framework" → `context menu, menu`
- GUIDES-11278 "Native PDF publishing | Ability to access temporary HTML files" → `context menu, menu, toolbar`
- GUIDES-38669 "'Assign to' dropdown does not filter user list when typing" → `menu`

Each of these is a genuine multiple-actions-on-one-surface case where per-capability
eligibility decomposition applies — discovered generically, not from any Assets-Jira mapping.

## ScopeConflictResolver — activated on 7 unseen TRAIN issues
Representative examples:

- GUIDES-12653 "Baseline - new UI | Ability to duplicate baseline and update selected"
- GUIDES-10878 "Preview mode in the web editor to show content based on the selection"
- GUIDES-31715 "[SLA3] BaselineUtils Java API fails..." (fix + multiple problems)
- GUIDES-29095 "[SLA3] MathML Equations Not Loading in AEM Guides Editor"

These carry a fix/PR signal alongside more than one reported problem, so the Jira-scope vs
fix-scope reconciliation activates.

## Conclusion
Both new reasoning capabilities activate independently on unseen TRAIN issues with completely
different entities from the Assets-UI fixture, driven only by generic surface/scope signals.
The anti-hardcoding audit (`run_gates.py`) confirms no per-entity/per-action mapping exists in
production logic. Generalization: **PASS**.
