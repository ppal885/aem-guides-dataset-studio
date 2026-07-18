# Test Plan: GUIDES-SCHEMATRON-EMPTY-MULTIPLE

## 1. Evidence intake

- JIRA source: E1 Jira MCP issue for empty/multiple Schematron validation.
- Documentation/spec evidence: E2 Experience League validation docs.
- Repository evidence: E3 validator service branch inspection.
- Diff evidence: available
- Automation evidence: E4 existing validator UI smoke.
- Historical Jira evidence: E5 related reopened validation defects.
- Missing evidence: none.
- Confidence: High

## 2. Requirement and behavior summary

- Current behavior / reproduction: Empty or multiple Schematron files can produce misleading validation state.
- Requested/intended behavior: Empty Schematron is reported as invalid and multiple files are handled deterministically.
- User or technical entry point: Web Editor validation on Save.
- Acceptance criteria: Save validation reports actionable errors and does not corrupt dirty state.
- Existing behavior that must not regress: A single valid Schematron file still validates and Save persists content.

## 3. Evidence map

| Evidence ID | Source | What it proves | Link / path |
| --- | --- | --- | --- |
| E1 | Jira MCP | Customer reproduction for empty and multiple Schematron files | GUIDES-SCHEMATRON-EMPTY-MULTIPLE |
| E2 | Experience League RAG | Schematron validation is configured through editor/folder settings | https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/support-schematron-file |
| E3 | Repository diff | Validator branch now checks empty and multiple rule inputs | backend/app/services/schematron_validator.py:42 |
| E4 | Automation repo | Existing save smoke lacks validator oracle | tests/ui/test_save.py:10 |
| E5 | Jira MCP historical | Similar validation bugs reopened due weak UI-only oracle | GUIDES-10001 |

## 4. Blast radius and risk analysis

### Execution/change-path narrative

Save enters the Web Editor validation path, resolves folder profile Schematron configuration, loads one or more Schematron files, maps validator exceptions to API response payloads, and updates UI dirty/error state. The changed branch touches empty-file detection and multi-file ordering, so parser, validator, API mapping, persistence, and UI state need independent oracles.

### Mandatory classification table

| Area / component | Impact level | Why affected | Evidence | Regression action |
| --- | --- | --- | --- | --- |
| Schematron validator | Direct | Empty/multiple file branches changed | E3 | SC-001 SC-002 SC-003 |
| Web Editor Save validation | Downstream | UI consumes validation response and dirty state | E1 E4 | SC-004 |
| Folder profile inheritance | Shared-path | Same config resolver supplies Schematron files | E2 E3 | SC-005 |
| Native PDF publishing | Not impacted | No evidence publish path consumes editor validation response | E2 E3 | Excluded by EX-001 |

### Failure/risk register

| Risk ID | Surface / failure mode | User/business impact | Likelihood | Priority | Evidence | Scenario / exclusion |
| --- | --- | --- | --- | --- | --- | --- |
| BR-1 | Empty Schematron accepted as valid | Invalid rules silently pass | Medium | P1 | E1 E3 | SC-001 |
| BR-2 | Multiple Schematron order changes result | Authors see nondeterministic validation | Medium | P1 | E1 E3 | SC-002 |
| BR-3 | Backend reports error but UI shows success | Customer believes content is valid | Medium | P1 | E4 E5 | SC-004 |
| BR-4 | Folder profile override ignored | Wrong rules applied to folder content | Low | P2 | E2 E3 | SC-005 |

### Existing behavior that must remain unchanged

- R0 control behavior: Single valid Schematron file validates, Save persists topic, reopen shows no dirty state.

### Minimum direct regression

- R1 direct coverage: empty Schematron, multiple Schematron, malformed Schematron, and valid single Schematron.

### Shared-path regression

- R2 shared-path coverage: folder profile inheritance and workspace fallback.

### Downstream regression

- R3 downstream coverage: UI banner, API response, backend exception mapping, persistence/reopen, logs.

### Conditional regression

- R4 compatibility coverage: Cloud/on-prem pairwise only if config resolver differs.

### Explicit exclusions

| Area / component | Reason excluded | Evidence |
| --- | --- | --- |
| Native PDF publishing | Editor validation response is not consumed by publish path | E2 E3 |

### Unknowns that can expand the scope

| Unknown | Why it matters | Decision-changing question |
| --- | --- | --- |
| Cloud/on-prem resolver parity | Could add R4 release coverage | Does the same configuration resolver run in both deployments? |

## 5. Bug hypothesis register

| Hypothesis ID | Rank | Trigger / heuristic | Suspected bug | Evidence / signal | Confidence | Scenario / exclusion |
| --- | --- | --- | --- | --- | --- | --- |
| BH-001 | 1 | Empty input | Empty Schematron file bypasses parser and returns success | E1 E3 | High | SC-001 |
| BH-002 | 2 | Collection ordering | Multiple Schematron files validate in nondeterministic order | E1 E3 | Medium | SC-002 |
| BH-003 | 3 | Exception mapping | Backend exception is swallowed and UI shows success | E4 E5 | Medium | SC-004 |
| BH-004 | 4 | Configuration inheritance | Folder override fails back to workspace rules | E2 E3 | Medium | SC-005 |

## 6. Kill the Fix analysis

| Changed branch / contract | Escape mode | Test to kill incomplete fix | Evidence | Scenario / exclusion |
| --- | --- | --- | --- | --- |
| Empty file guard | Fix only checks null, not zero-byte file | Upload zero-byte Schematron and assert validator error code | E3 | SC-001 |
| Multiple file branch | Fix only handles two files in stable order | Validate three files with conflicting rule IDs | E3 | SC-002 |
| Error contract | Backend changed exception but API body remains generic | Assert API error code and UI banner match | E3 E4 | SC-004 |

## 7. Historical regression signals

| Historical Jira | Signal type | Why it matters | Risk / hypothesis influenced | Automation lesson |
| --- | --- | --- | --- | --- |
| GUIDES-10001 | Reopened validation bug | Prior fix had UI-only oracle and missed backend error code | BR-3 BH-003 | Add API/backend oracle, not just banner check |
| GUIDES-10002 | Customer escape | Empty validator config passed silently | BR-1 BH-001 | Add negative empty input to PR Gate |

## 8. Interaction matrix

| Interaction ID | Selected combination | Why this can exercise changed path | Risk / hypothesis | Scenario |
| --- | --- | --- | --- | --- |
| INT-001 | Empty Schematron + Save + folder profile | Exercises empty-file parser through config resolver | BR-1 BH-001 | SC-001 |
| INT-002 | Three Schematron files + duplicate rule ID + Save All | Exercises ordering and aggregation branch | BR-2 BH-002 | SC-002 |
| INT-003 | Malformed Schematron + API validation + UI banner | Exercises exception mapping across layers | BR-3 BH-003 | SC-004 |

## 9. Prioritized scenarios

Every scenario must trace to a requirement, risk, bug hypothesis, kill-the-fix item, interaction, or historical signal.

| Scenario ID | Ring | Pack | Priority | Title | Trace to risk / hypothesis / evidence | Automation layer | Oracle summary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SC-000 | R0 - Control | PR Gate | P1 | Save with one valid Schematron | E2 E4 | UI/API | UI no validation banner, API 200, repository version increments, reopen clean |
| SC-001 | R1 - Direct | PR Gate | P1 | Reject empty Schematron file | BR-1 BH-001 INT-001 E1 E3 | API/unit/UI | API 400 VALIDATION_EMPTY, backend exception mapped, UI banner names empty Schematron, no persistence |
| SC-002 | R1 - Direct | Component Regression | P1 | Deterministic multiple Schematron handling | BR-2 BH-002 INT-002 E1 E3 | API/integration | Stable ordered violations, duplicate rule reported once, logs include correlation ID |
| SC-003 | R1 - Direct | Component Regression | P2 | Malformed Schematron parser failure | BR-1 BH-001 E3 | Unit/API | Parser exception maps to validation error code and no dirty-state mutation |
| SC-004 | R3 - Downstream | Nightly | P1 | UI and backend error contract stay aligned | BR-3 BH-003 INT-003 E4 E5 | UI/API | UI banner text matches API error code, Save button remains enabled, logs include warning |
| SC-005 | R2 - Shared path | Release Regression | P2 | Folder profile override uses correct Schematron | BR-4 BH-004 E2 E3 | API/UI | API payload uses folder profile path, repository state unchanged on error |

## 10. Detailed test scenarios

- Scenario ID: SC-000
- Priority: P1
- Regression ring: R0
- Regression pack: PR Gate
- Requirement/risk/hypothesis trace: E2 E4 unchanged valid validation
- Preconditions: topic open with one valid Schematron configured
- Test data: valid topic and valid Schematron
- Steps: Save, inspect API response, reopen topic
- Expected result: Save succeeds, repository version increments, reopen has no dirty state
- Multi-layer oracle: UI no validation banner; API 200; repository version increments; reopen clean
- Failure injection if applicable: none
- Automation recommendation: Exact and strong UI/API smoke

- Scenario ID: SC-001
- Priority: P1
- Regression ring: R1
- Regression pack: PR Gate
- Requirement/risk/hypothesis trace: BR-1 BH-001 INT-001 E1 E3
- Preconditions: folder profile points to zero-byte Schematron
- Test data: valid topic and empty Schematron file
- Steps: Save topic, inspect validation API, inspect repository version and logs
- Expected result: Save is blocked with actionable validation error
- Multi-layer oracle: API 400 VALIDATION_EMPTY; backend exception mapped; UI banner names empty file; repository version unchanged; log has correlation ID
- Failure injection if applicable: zero-byte Schematron parser input
- Automation recommendation: Exact and strong API + UI PR Gate

- Scenario ID: SC-002
- Priority: P1
- Regression ring: R1
- Regression pack: Component Regression
- Requirement/risk/hypothesis trace: BR-2 BH-002 INT-002 E1 E3
- Preconditions: folder profile points to three Schematron files
- Test data: duplicate rule ID and conflicting rule set
- Steps: Run validation twice and compare response order
- Expected result: Violations are deterministic and duplicates are reported once
- Multi-layer oracle: API ordered violation list; backend aggregation count; log warning; no repository mutation
- Failure injection if applicable: duplicate rule IDs across multiple Schematron files
- Automation recommendation: Exact and strong integration test

- Scenario ID: SC-003
- Priority: P2
- Regression ring: R1
- Regression pack: Component Regression
- Requirement/risk/hypothesis trace: BR-1 BH-001 E3
- Preconditions: validator service available
- Test data: malformed Schematron XML
- Steps: Invoke validator API with malformed rule file
- Expected result: Parser failure is surfaced as validation error contract
- Multi-layer oracle: backend exception type; API error body; no dirty state mutation
- Failure injection if applicable: malformed XML parser fault
- Automation recommendation: Exact and strong unit/API

- Scenario ID: SC-004
- Priority: P1
- Regression ring: R3
- Regression pack: Nightly
- Requirement/risk/hypothesis trace: BR-3 BH-003 INT-003 E4 E5
- Preconditions: Web Editor open with malformed Schematron configured
- Test data: malformed Schematron and valid topic
- Steps: Save from UI, capture network response, inspect banner and logs
- Expected result: UI and backend report same actionable validation failure
- Multi-layer oracle: UI banner text; network error code; backend warning; repository unchanged; job/log correlation ID
- Failure injection if applicable: backend validation exception
- Automation recommendation: Exact but weak oracle until log assertion is added

- Scenario ID: SC-005
- Priority: P2
- Regression ring: R2
- Regression pack: Release Regression
- Requirement/risk/hypothesis trace: BR-4 BH-004 E2 E3
- Preconditions: global and folder profiles define different Schematron files
- Test data: topic under folder override
- Steps: Save topic and inspect resolver payload
- Expected result: folder profile Schematron wins over global fallback
- Multi-layer oracle: API payload contains folder path; UI shows folder-specific violation; repository unchanged on failure
- Failure injection if applicable: inherited configuration mismatch
- Automation recommendation: Partial until on-prem resolver is also covered

## 11. Automation strength assessment

| Existing / proposed check | Layer | Strength classification | Why | Gap / action |
| --- | --- | --- | --- | --- |
| Existing save smoke | UI | Exact but weak oracle | Saves topic but checks no validator API or repository state | Extend with SC-001 and SC-004 oracles |
| New empty Schematron API test | API | Exact and strong | Exact changed branch and explicit error code | Add to PR Gate |
| New multi-file aggregation test | API/integration | Exact and strong | Covers collection ordering and duplicate handling | Add to component regression |
| Existing mocked validator unit | Unit | Mocked-path only | Mocks parser and misses XML failure | Add real parser fixture |

## 12. Regression pack split

| Pack | Included scenarios | Entry criteria | Required oracle | Owner / cadence |
| --- | --- | --- | --- | --- |
| PR Gate | SC-000 SC-001 | Every validator PR | UI/API/repository oracles | Component team per PR |
| Component Regression | SC-002 SC-003 | Validator changes | API/backend/log oracles | Component team nightly candidate |
| Nightly | SC-004 | UI validation path touched | UI/network/log/repository oracles | QA nightly |
| Release Regression | SC-005 | Config resolver or release branch | API/UI/profile evidence | Release QA |
| Exploratory | CH-001 | Low confidence config parity | Notes and defect links | Senior QA |

## 13. Focused exploratory charters

| Charter ID | Target area | Mission | Data / setup | Stop condition | Risk addressed |
| --- | --- | --- | --- | --- | --- |
| CH-001 | Schematron profile inheritance | Try to find stale profile/cache states that apply wrong Schematron | global plus folder profile, empty/multiple/malformed files | 45 minutes or one credible defect | BR-4 BH-004 |

## 14. Residual Risk and Release Confidence

- Unavailable evidence: none.
- Unexecuted critical risks: none after SC-001 and SC-004 execute.
- Assumptions: same validator branch is used by Save and Save All.
- Residual risks accepted: Cloud/on-prem resolver parity remains R4 if deployment code differs.
- Exact information needed to improve confidence: confirm deployment-specific resolver implementation.
- Release confidence: High

## 15. Traceability and quality gates

- All Direct/Shared-path critical items covered or excluded: yes
- All P0/P1 risks covered or excluded: yes
- Bug hypotheses mapped: yes
- Kill-the-fix coverage complete or Draft-only: yes
- Reproduction/control/negative/recovery coverage present for bug plans: yes
- Multi-layer oracles present: yes
- Historical Jira search completed or marked unavailable: yes
- Exclusions evidence-backed: yes
- Unknowns labeled: yes
- Missing Jira/RAG/code evidence forces Draft: not applicable
- Review status: Review-ready
