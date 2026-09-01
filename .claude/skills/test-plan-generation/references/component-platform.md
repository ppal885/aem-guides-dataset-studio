# Platform UAC Contracts

Load this focused pack only when the component router returns `Platform` for a covered mechanism. Current accepted scope and verified evidence remain the authority. The patterns below are generic investigation rules; they contain no historical-ticket authority.

## Bulk Same-Name Asset Overwrite and Session Contract

Activate only when current evidence combines a bulk or batch asset import with same-name overwrite/re-upload and an observable terminal-state, session, authentication, CSRF, or stuck-processing symptom. A ticket key, customer name, old batch count, or old release cannot activate this contract.

### Evidence Boundary

- Preserve the exact deployment, AEM service pack, Guides build, authentication topology, import API, batch cardinality, file mix, and configuration values from current evidence. Conflicts become Open Questions; do not choose an old value from memory.
- Treat login redirects, CSRF retries, generic errors, pending loaders, and import endpoint traffic as failure signatures. They do not prove which layer is the root cause.
- Configuration changes and raised limits are diagnostic matrix inputs unless accepted evidence identifies them as the supported fix or contract.
- A reported small or large batch is a reproduction fixture, not a supported maximum, SLA, timeout, or resource ceiling.

### Proposed Acceptance Contract

- With an authenticated author and an existing same-name asset set, an overwrite batch reaches an observable terminal success, partial-success, or failure state defined by accepted evidence; it does not remain indefinitely pending.
- Starting an overwrite must not silently redirect an otherwise authenticated author to login. If authentication expires, the UI/API distinguishes that state from an import failure and provides the approved recovery action.
- A failed overwrite exits processing and presents an actionable result instead of only a generic message, stuck loader, or forced logout.
- A successful overwrite is verified by reading back every targeted asset's content identity and repository state. An HTTP success response or disappearing loader alone is insufficient.
- The initial-upload control remains valid for the same current fixture, and retrying an overwrite does not create duplicate assets or an unexplained partial result.
- Batch limits, timeouts, resources, atomicity, partial-success semantics, retry behavior, and supported file counts remain Open Questions until an approved source defines them.

### Test Matrix

- Compare initial upload with same-name overwrite using identical source assets and controlled session state.
- Exercise cardinalities explicitly supplied by current evidence plus one justified boundary. Do not import counts from historical examples.
- Correlate the import request, CSRF/authentication events, UI terminal state, repository read-back, and server logs in the same timestamped run.
- Treat configuration changes as controlled diagnostic variants. Accept them only when they produce repeatable terminal behavior and complete asset integrity under the approved contract.
- When testing another deployment or release, keep its result separate from the source environment rather than silently generalizing.

### Historical Similarity Rule

- Retain another issue only when it shares the overwrite/import mechanism plus a matching terminal-state signature, authentication transition, or verified common execution path/root cause.
- A generic large-file upload, DAM workflow, timeout, or performance issue is area-only similarity.
- Historical evidence may propose a retrieval hypothesis. It cannot provide a workload, expected outcome, threshold, or Confirmed AC unless the exact fact is current, applicable, source-backed, and authorized for that subject.

### Open Questions

- Which deployment, AEM service pack, and Guides build reproduce the issue?
- What workload, request size, timeout, and resource envelope is approved for this import path?
- Is the expected overwrite result atomic, partially reportable, or retryable per asset?
- Which layer owns the terminal failure: session expiry, CSRF handling, CDN/authentication, Assets processing, or Guides import?
- What exact UI and API contract distinguishes success, validation conflict, partial failure, authentication expiry, and server failure?

### Reject

- Do not claim data loss, a fixed threshold, an asynchronous implementation, a missing index, or a configuration root cause without direct evidence.
- Do not promote a non-reproducible historical issue into a trusted behavior claim.
- Do not convert observed batch sizes or durations into performance acceptance numbers.
