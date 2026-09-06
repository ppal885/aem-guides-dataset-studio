# Current run snapshot (Phase A/B) — UAC-GENERATOR-PERFORMANCE-MASTER-01

Source of truth: scripts/uac_eval/judge_pipeline_collapse_excess_local30.json
(LOCAL backend, n=30, seed 5, calibrated collapse-excess precision). This is the real
run behind the dashboard's F1 93 / cov 88.8 / prec 95.7 / halluc 1.

CAVEAT: this baseline is a LOCAL run, not the VM. A qualification comparison must be
VM-vs-VM.

| metric | pipeline |
|---|---|
| coverage | 88.8 |
| precision | 95.7 |
| combined F1 | 93.0 |
| hallucinations | 1.0 |

## Weak-tail buckets (generation-only signals; NO human reference exposed)
- LOW_COVERAGE (<90): 9 ['GUIDES-37733', 'GUIDES-29815', 'GUIDES-28171', 'GUIDES-28214', 'GUIDES-19701', 'GUIDES-33605', 'GUIDES-14786', 'GUIDES-42582', 'GUIDES-23965']
- LOW_PRECISION (<90): 4 ['GUIDES-29815', 'GUIDES-38412', 'GUIDES-34084', 'GUIDES-29093']
- OVER_DECOMPOSED (od>0 or dup>0): 6 ['GUIDES-27789', 'GUIDES-29815', 'GUIDES-28171', 'GUIDES-38412', 'GUIDES-14786', 'GUIDES-29093']
- NO_CONTRACT (0 AC, no section): 2 ['GUIDES-28214', 'GUIDES-28237']
- HALLUCINATION (judge>0): 7 ['GUIDES-27789', 'GUIDES-28171', 'GUIDES-28214', 'GUIDES-33605', 'GUIDES-28748', 'GUIDES-42582', 'GUIDES-28237']
- STRONG_CONTROL (100/100): 14 ['GUIDES-8979', 'GUIDES-40399', 'GUIDES-33731', 'GUIDES-32872', 'GUIDES-19703', 'GUIDES-28104', 'GUIDES-45983', 'GUIDES-28748', 'GUIDES-33515', 'GUIDES-49386', 'GUIDES-26516', 'GUIDES-37843', 'GUIDES-33794', 'GUIDES-23128']

## Architecture reality (grep over backend/)
Of the ~20 components section 1 says to "reuse", only ONE exists:
  - debug_qe_miss -> backend/app/services/qe_miss_diagnostic_service.py (+ PFIX19 test)
Absent: Pattern MCP, domain classifier, AuthoringCapabilityGraph, DITASemanticGraph,
Publishing/BackendService/UIState/Assets/PerformanceScale/ConfigurationBranch Reasoners,
EntryPointCandidate, resolve_evidence_conflict, CandidateLedger, OracleResolver,
FluffyJaws provider (per project memory: integration NOT complete).

## What is measurable today vs not
Measurable: coverage/precision/combined/hallucination (judge), over-decomposition,
redundancy, no-contract — all in the eval JSON.
NOT measurable yet (blocks the section-30 release gates): P0/P1 material-miss recall,
silent-candidate-drop, silent-family-drop, entry-point recall, oracle accuracy — there is
no labeled held-out set with ATOMIC expected requirements, and no plan-replay for clean
A/B (generation is non-deterministic).
