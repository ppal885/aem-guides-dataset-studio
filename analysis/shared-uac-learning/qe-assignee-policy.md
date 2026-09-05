# Ticket-scoped QE Assignee review authority

Implemented locally in `codex/shared-uac-feedback-learning`; not deployed to the VM.

## Verified source

On 2026-09-06 the authenticated live Jira page for
[GUIDES-50368](https://jira.corp.adobe.com/browse/GUIDES-50368) showed **Sachin Shukla**
in **QE Assignee**, DOM field `customfield_18512-val`. The same field ID is present
in tracked `backend/scripts/post_acs_to_jira.py` for comment tagging. The configured
Jira MCP's normalized issue response did not include this field, so the page was
used to verify it. The standard Assignee is a separate field and is not the review
authority. No Jira field, comment, label, or approval was changed.

The example's person and ticket are audit evidence only, not production selectors.
Production uses the raw `JiraClient.get_issue_with_names` contract with a bounded,
TLS-verified read and checks the live field name before comparing stable identity.
The actual server-side Jira user-key mapping for Sachin has not been provisioned
or tested against the VM; the page's display name is not an authentication claim.

## Behavior

- Any authenticated tenant teammate can submit selected Human feedback.
- Binding and all review actions require the current live **QE Assignee**.
- Personal server-configured `jira_identity` pins the Jira server and exactly one
  stable Jira user key (Data Center) or account ID (Cloud). Display names, email,
  client-supplied claims, admin roles and ordinary Assignee do not substitute.
- Missing mapping, an unavailable Jira, a changed/missing/ambiguous field, inactive
  account, cross-tenant request or identity mismatch cannot approve anything.
- Every binding/review request, including an idempotent retry, checks Jira again.
  Reassignment changes the next request's reviewer; it does not erase a valid past
  decision. The decision stores the observed identity, field, server and check time.
- Shared/service/development credentials cannot review. Global Jira credentials
  can be used only for an explicitly configured active tenant pinned to that server.
- Each supporting correction must already have its own QE-approved revision.
  Derived lessons pin that revision; revocation/supersession stops reuse immediately
  through SQL eligibility. The full supporting source-case lineage remains subject
  to source exclusions and benchmark protections.
- Previous role-only approval records stay immutable but require QE re-review.
  `reuse_eligible` and `publication_review_status` distinguish publication eligibility
  from the original audit state and physical index state. A dependent vector may
  remain stored and report `INDEXED`; it cannot be returned as eligible learning.

## Validation and safety

Focused tests use synthetic Jira responses and isolated SQL, not production
approvals. The final regression run has **301 passed and one pre-existing
classification failure**. All 31 new live-QE authorization unit tests and 10
identity/lineage/error-redaction tests pass. All five repository copies byte-match.
Standard skill self-tests still stop at the same eight pre-existing hardcoding
findings in unchanged `coverage_forcing.py`; these are not waived or repaired.
Final counts and logs are recorded in `validation-report.json`.

The original dirty checkout, dashboard, eval metric calculations and corpora are
protected by `verify_safety.py`. Repository skill copies are synchronized separately;
conflicting real global installations remain untouched. No commit, push, VM
migration, deployment, personal credential creation or live learning approval has
been performed.
