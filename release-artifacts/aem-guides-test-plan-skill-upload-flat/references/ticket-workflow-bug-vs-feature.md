# Ticket workflow — Bug vs Feature Request

The unified pipeline classifies each Jira ticket and **orchestrates** Pre-UAC, scoring, default scenarios, and QE handoff differently.

## Classification

| Category | Typical Jira types | Signals |
| --- | --- | --- |
| **Bug** | Bug, Defect, Incident | Actual + Expected, repro/failure language |
| **Feature request** | Customer Request, Feature Request, Story, Enhancement | Requested enhancement, empty Expected, business need |
| **Other** | Task, unclassified | PM must confirm type |

Stage: `ticket_workflow` (after `ticket_intake`, before `pre_uac_product_brief`).

Output: `ticket_workflow` in `{KEY}-pipeline-result.json` and **Type:** line in draft plan header.

## Orchestration differences

| Stage | Bug | Feature request |
| --- | --- | --- |
| **Pre-UAC TW-* checks** | Repro env, log oracle, regression scope | PM scope, UI surfaces, min shippable |
| **Default S-* rows** | S-01 Primary repro, S-02 R0 control, S-03 Negative | S-01 Happy path, S-02 Regression, S-03 Edge |
| **Must-run gate** | Customer repro + P0 regression | PM-agreed expected + P0 capability |
| **Score adjust** | +5 if Actual+Expected; −8 if Actual missing | −10 if Expected missing |
| **QE next actions** | Confirm repro on Author | Route PM — agree Expected Result |

## Agent rules

1. Read `ticket_workflow.ticket_category` before refining `{KEY}-test-plan.md`.
2. Do not write final AC for **feature requests** until Expected Result is agreed.
3. For **bugs**, S-01 must trace to customer repro; use log line as pass/fail oracle when present.
4. Re-classification runs again after UAC intelligence merges Jira fields.
