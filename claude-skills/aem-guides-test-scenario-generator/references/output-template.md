# Output Template

Use this structure for JIRA-driven AEM Guides test plans. Bug discovery and regression prevention are the primary objectives.

# Test Plan: <JIRA key or title>

## 1. Evidence intake

- JIRA source:
- Documentation/spec evidence:
- Repository evidence:
- Diff evidence: available / unavailable
- Automation evidence:
- Historical Jira evidence:
- Missing evidence:
- Confidence:

## 2. Requirement and behavior summary

- Current behavior / reproduction:
- Requested/intended behavior:
- User or technical entry point:
- Acceptance criteria:
- Existing behavior that must not regress:

## 3. Evidence map

| Evidence ID | Source | What it proves | Link / path |
| --- | --- | --- | --- |

## 4. Blast radius and risk analysis

### Execution/change-path narrative

Describe the entry point, current/suspected implementation path, upstream callers, shared services, persistence/cache/state/asynchronous boundaries, error handling, downstream consumers, existing tests, compatibility dimensions, exclusions, and unknowns.

### Mandatory classification table

| Area / component | Impact level | Why affected | Evidence | Regression action |
| --- | --- | --- | --- | --- |

### Failure/risk register

| Risk ID | Surface / failure mode | User/business impact | Likelihood | Priority | Evidence | Scenario / exclusion |
| --- | --- | --- | --- | --- | --- | --- |

### Existing behavior that must remain unchanged

- R0 control behavior:

### Minimum direct regression

- R1 direct coverage:

### Shared-path regression

- R2 shared-path coverage:

### Downstream regression

- R3 downstream coverage:

### Conditional regression

- R4 compatibility coverage:

### Explicit exclusions

| Area / component | Reason excluded | Evidence |
| --- | --- | --- |

### Unknowns that can expand the scope

| Unknown | Why it matters | Decision-changing question |
| --- | --- | --- |

## 5. Bug hypothesis register

| Hypothesis ID | Rank | Trigger / heuristic | Suspected bug | Evidence / signal | Confidence | Scenario / exclusion |
| --- | --- | --- | --- | --- | --- | --- |

## 6. Kill the Fix analysis

| Changed branch / contract | Escape mode | Test to kill incomplete fix | Evidence | Scenario / exclusion |
| --- | --- | --- | --- | --- |

If no diff was inspected, write: `Diff not inspected; fix-escape coverage is Draft-only until changed branches and error contracts are mapped.`

## 7. Historical regression signals

| Historical Jira | Signal type | Why it matters | Risk / hypothesis influenced | Automation lesson |
| --- | --- | --- | --- | --- |

## 8. Interaction matrix

| Interaction ID | Selected combination | Why this can exercise changed path | Risk / hypothesis | Scenario |
| --- | --- | --- | --- | --- |

## 9. Prioritized scenarios

Every scenario must trace to a requirement, risk, bug hypothesis, kill-the-fix item, interaction, or historical signal.

| Scenario ID | Ring | Pack | Priority | Title | Trace to risk / hypothesis / evidence | Automation layer | Oracle summary |
| --- | --- | --- | --- | --- | --- | --- | --- |

## 10. Detailed test scenarios

For each scenario include Scenario ID, Priority, Regression ring, Regression pack, Requirement/risk/hypothesis trace, Preconditions, Test data, Steps, Expected result, Multi-layer oracle, Failure injection if applicable, and Automation recommendation.

Bug plans must include reproduction, R0 control, negative, and recovery coverage.

## 11. Automation strength assessment

| Existing / proposed check | Layer | Strength classification | Why | Gap / action |
| --- | --- | --- | --- | --- |

Allowed classifications: Exact and strong, Exact but weak oracle, Partial, Obsolete, Mocked-path only, Missing.

## 12. Regression pack split

| Pack | Included scenarios | Entry criteria | Required oracle | Owner / cadence |
| --- | --- | --- | --- | --- |

Packs: PR Gate, Component Regression, Nightly, Release Regression, Exploratory.

## 13. Focused exploratory charters

| Charter ID | Target area | Mission | Data / setup | Stop condition | Risk addressed |
| --- | --- | --- | --- | --- | --- |

## 14. Residual Risk and Release Confidence

- Unavailable evidence:
- Unexecuted critical risks:
- Assumptions:
- Residual risks accepted:
- Exact information needed to improve confidence:
- Release confidence: Low / Medium / High

## 15. Traceability and quality gates

- All Direct/Shared-path critical items covered or excluded:
- All P0/P1 risks covered or excluded:
- Bug hypotheses mapped:
- Kill-the-fix coverage complete or Draft-only:
- Reproduction/control/negative/recovery coverage present for bug plans:
- Multi-layer oracles present:
- Historical Jira search completed or marked unavailable:
- Exclusions evidence-backed:
- Unknowns labeled:
- Missing Jira/RAG/code evidence forces Draft:
- Review status: Draft / Review-ready
