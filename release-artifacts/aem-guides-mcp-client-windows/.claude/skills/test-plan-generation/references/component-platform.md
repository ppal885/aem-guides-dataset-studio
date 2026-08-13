# Platform UAC Contracts

Load this focused pack only when the component router returns `Platform` for a covered mechanism. Current Jira/UAC remains the authority.

## Bulk Same-Name Asset Overwrite and Session Contract - GUIDES-30459

Use this as **candidate historical learning only**. `GUIDES-30459` was closed because the failure was unclear or could not be reproduced consistently; it has no accepted UAC, confirmed root cause, implemented-fix evidence, or verified QA oracle.

### Evidence Boundary

- The reported fixture is AEM 6.5 On-Prem with Guides 5.0 UUID. The supplied evidence conflicts on AEM SP21 versus SP22, so the exact service-pack boundary is an Open Question.
- Initial upload of roughly 200 assets reportedly completes. Re-uploading the same names to overwrite them can show a generic error plus a forced login redirect, or an indefinitely pending loader.
- Smaller batches below roughly 100 reportedly complete with a conflict warning. Treat `100` and `200` only as observed test fixtures, never as a supported product threshold or SLA.
- The observed network path includes `POST /bin/fmdita/import`, repeated CSRF-token requests, and a later login redirect. These are failure signatures, not proof that Guides import, CSRF handling, session expiry, CDN behavior, or Assets post-processing is the root cause.
- Raising upload-related limits and changing the Product Assets Upload Process are diagnostic matrix inputs. Neither is an accepted fix or root-cause conclusion.

### Proposed Acceptance Contract

- With an authenticated author and an existing same-name asset set, an overwrite batch reaches an observable terminal success or failure state; it does not remain indefinitely pending.
- Starting the overwrite must not silently redirect an otherwise authenticated author to the login page. If authentication really expires, the UI must distinguish that state from an import failure and preserve a recoverable user action.
- A failed overwrite exits processing and presents an actionable error instead of only a generic message, stuck loader, or forced logout.
- A successful overwrite is verified by reading back every targeted asset's binary/content identity and repository state. An HTTP success response or disappearing loader alone is insufficient.
- The initial-upload control remains valid for the same fixture, and retrying an overwrite does not create duplicate assets or an ambiguous partial result.
- Batch boundaries, timeout values, memory/CPU targets, atomicity, partial-success semantics, retry behavior, and supported maximum file count remain Open Questions until current product evidence defines them.

### Test Matrix

- Compare initial upload with same-name overwrite using identical asset sets and clean sessions.
- Exercise an observed smaller batch and the reported 200-asset batch without turning those counts into product limits.
- Capture `/bin/fmdita/import`, CSRF, login redirect, UI loader/error, repository read-back, and server logs on the same timestamped run.
- Repeat with the supplied upload-limit and Product Assets Upload Process configurations only as diagnostics; do not accept a configuration change unless it produces repeatable terminal behavior and complete asset integrity.
- If testing after an upgrade or on another topology, keep environment/version conclusions separate from the original On-Prem report.

### Historical Similarity Rule

- Retain another Jira only when it shares same-name overwrite/bulk import plus the `/bin/fmdita/import` route, terminal-state failure, session/login redirect, CSRF loop, or a verified common root cause.
- A generic large-file upload, DAM workflow, timeout, or performance issue is area-only similarity.
- `GUIDES-14743` may be a risk signal for `/bin/fmdita/import` stuck-pending behavior, but without verified common root cause/fix/oracle it cannot supply expected behavior or a Confirmed AC.

### Open Questions

- Which AEM service pack and exact Guides build reproduce the issue?
- What is the supported batch-size, request-size, timeout, and resource envelope for this import path?
- Is the expected overwrite result atomic, partially reportable, or retryable per asset?
- Which layer owns the login redirect: session expiry, CSRF handling, CDN/authentication, Assets processing, or Guides import?
- What exact UI and API contract distinguishes success, validation conflict, partial failure, authentication expiry, and server failure?

### Reject

- Do not claim data loss, a fixed threshold, an asynchronous implementation, a missing index, or a Product Assets Upload Process root cause without direct evidence.
- Do not promote a non-reproducible closed Jira into a trusted behavior claim.
- Do not convert `200 assets` or `under 100` into performance acceptance numbers.
