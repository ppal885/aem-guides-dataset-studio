# Platform UAC Contracts

Load this focused pack when the component router returns `Platform` or current evidence
activates the asset-upload conflict signals named below. Current accepted scope and
verified evidence remain the authority. The patterns below are generic investigation
rules; they contain no historical-ticket authority.

## Asset Upload Conflict Evidence Contract

Activate this contract only when current evidence involves asset upload, overwrite or
re-upload, duplicate detection, a same-name/name or path conflict, Create Asset, an
upload conflict, or a conflict endpoint. Do not activate it for unrelated files,
generic duplicate wording, or a product name alone.

### Required independent dimensions

- **Content identity duplicate detection:** Determine whether matching content identity
  (for example, a matching checksum) is detected. Keep it separate from a collision
  caused by an existing name or repository path, even when one UI flow displays both.
  This is a required investigation and disposition, not automatic acceptance coverage:
  when the affected path does not enter duplicate detection, record
  `OUT_OF_SCOPE` or `NOT_APPLICABLE` with the inspected path evidence instead of adding
  a duplicate-detection AC.
- **Name/path conflict:** Determine the behavior for an existing name or target path
  independently of content identity. Do not use a duplicate-detection result as its
  expected outcome.
- **Request dispatch:** A configuration provider, service registration, or class name
  shows configuration or a candidate implementation only. It does not prove that a
  request reaches that handler. Inspect request-dispatch evidence that joins the
  actual handler to the upload route. If that evidence is unavailable, record an Open
  Question or evidence gap; do not assert handler behavior.
- **Deployment:** Record every named deployment independently. When both AEM as a
  Cloud Service and On-premise are named, map the upload behavior to each one with
  its own evidence, explicit scope boundary, preservation record, or Open Question.
  A Cloud fix and an evidence-backed On-premise preservation can be valid different
  dispositions. Never copy a result from one deployment to the other as assumed parity.
- **Affected path and baseline actions:** Name the affected deployment, product surface,
  and exact behavior path. Do not call the scope merely "the dialog" or a broad
  product category. Record baseline dialog actions separately, including actions that
  bypass the changed path; an unaffected action is a preservation/investigation
  disposition, not automatic acceptance coverage.
- **Product-surface ownership and terminology:** Name a native AEM Assets action as
  native Assets behavior and source that ownership. In particular, **Create Version**
  and the overwrite/conflict flow **Overwrite Files** are native AEM Assets actions;
  the latter is not “Replace.” Neither is a Guides action by default. Use a
  Guides-owned surface only when inspected evidence proves that ownership; an
  integration with Assets does not by itself transfer ownership.
- **Documentation scope:** Record the deployment and product surface each document
  actually covers before using it. A Cloud-only document cannot establish
  On-premise behavior. A document for one product's upload surface cannot establish
  another product's dialog or endpoint unless the source explicitly covers it.

### Gate record

When this contract is active, populate the existing miss-probe coverage gate's
`asset_upload_conflict` block with schema
`aem-guides-asset-upload-conflict-v1`.

- `affected_behavior` must name the affected `deployment`, `product_surface`,
  `surface_owner`, exact `path`, and disposition, reason, and evidence. A native
  Assets surface records its source-backed `product_action` and
  `surface_ownership_evidence_refs`; use `Overwrite Files` for its overwrite flow,
  `Create Version` for its native version flow, and never `Replace`. A claimed Guides
  owner also needs ownership evidence, including when it claims either native action.
  `COVERED` maps to an AC. Use `NATIVE_AEM_ASSETS`, `AEM_GUIDES`, or `UNRESOLVED`
  for `surface_owner`; `UNRESOLVED` requires an Open Question.
- Declare `baseline_actions`. Each named action records whether it is affected or
  unaffected by the named path and its own disposition. If no distinct baseline action
  exists, an empty list needs an evidence-backed reason.
- Its `dimensions` object must disposition
  `content_identity_duplicate_detection`, `name_path_conflict`, and
  `request_handler_route` as `COVERED`, `OPEN_QUESTION`, `OUT_OF_SCOPE`, or
  `NOT_APPLICABLE`, or `PRESERVED`, with a reason.
- This is an **investigation/disposition contract**, not an AC-expansion rule.
  `COVERED` requires an AC. `OPEN_QUESTION` requires an Open Question. `OUT_OF_SCOPE`,
  `NOT_APPLICABLE`, and `PRESERVED` require a concrete evidence-based reason and
  evidence reference, but no AC merely because the probe matched.
- A covered handler/route dimension records `actual_handler` with `handler`, `route`,
  `source_ref`, and `evidence_kind: REQUEST_DISPATCH`. Record configuration artifacts
  separately; they cannot fill those dispatch fields.
- Each named item in `deployments` has its own disposition. A covered deployment has
  AC and evidence references; an unresolved deployment has an Open Question; a
  preserved or out-of-scope deployment has evidence for that boundary. A claimed parity
  or difference needs its own source reference.
- Declare `documentation_sources` even when it is empty; use an empty list only when
  no documentation supports the contract. Each listed source records
  `deployment_scope` and `surface_scope`. Every `supports` item names the same scoped
  deployment and surface it is used to establish.

## Bulk Same-Name Asset Overwrite and Session Contract

Activate only when current evidence combines a bulk or batch asset import with same-name overwrite/re-upload and an observable terminal-state, session, authentication, CSRF, or stuck-processing symptom. A ticket key, customer name, old batch count, or old release cannot activate this contract.

Apply the Asset Upload Conflict Evidence Contract first. This bulk/session contract
adds terminal-state, authentication, and asset-integrity investigation; it does not
merge content-identity duplicate detection with a same-name or path conflict.

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
