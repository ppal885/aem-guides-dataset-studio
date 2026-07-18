# Test Plan: GUIDES-SCHEMATRON-BAD

## 1. Evidence intake

- JIRA source: unavailable
- Documentation/spec evidence: unavailable
- Repository evidence: unavailable
- Automation evidence: unavailable
- Confidence: High

## 2. Requirement and behavior summary

- Current behavior / reproduction: bug.
- Requested/intended behavior: fixed.

## 3. Evidence map

| Evidence ID | Source | What it proves | Link / path |
| --- | --- | --- | --- |

## 4. Blast radius and risk analysis

### Execution/change-path narrative

Probably impacted.

### Mandatory classification table

| Area / component | Impact level | Why affected | Evidence | Regression action |
| --- | --- | --- | --- | --- |
| Validator | Direct | changed | E1 | needs testing |

### Failure/risk register

| Risk ID | Surface / failure mode | User/business impact | Likelihood | Priority | Evidence | Scenario / exclusion |
| --- | --- | --- | --- | --- | --- | --- |
| BR-1 | Empty file passes | bad | High | P1 | E1 |  |

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
| Publishing |  |  |

### Unknowns that can expand the scope

| Unknown | Why it matters | Decision-changing question |
| --- | --- | --- |

## 5. Prioritized scenarios

| Scenario ID | Ring | Priority | Title | Trace to risk / blast item | Automation layer | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| SC-001 | R1 - Direct | P1 | Test fix | BR-1 | UI | E1 |

## 15. Traceability and quality gates

- Review status: Review-ready
