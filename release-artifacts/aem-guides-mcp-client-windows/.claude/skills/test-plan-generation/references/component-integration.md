# Integration Component UAC Pack

Use this focused pack for Integration Jiras involving external content ingestion, asset/topic CRUD APIs, caller-supplied content or metadata, explicit GUID assignment, or UPDATE-as-UPSERT behavior. Current Jira/UAC evidence always overrides these historical patterns.

## Asset CRUD API Import Contract

### Evidence Boundary

- The supplied Jira is an enhancement request, not a complete accepted UAC. Unless a later accepted Jira field defines the contract, every generated criterion remains `[Proposed]`.
- The request explicitly prioritizes two capabilities: a caller-supplied GUID that is independent of the human-readable filename, and UPDATE operating as an opt-in UPSERT. Content and metadata in CREATE/UPDATE remain in scope but are secondary priorities.
- Customer names establish demand breadth only. They do not prove customer-specific payloads, permissions, status codes, or existing product behavior.
- `/libs/fmdita/clientlibs/api-docs/index/page.html` is an API-discovery surface. Its mention does not prove an endpoint, method, parameter name, or released capability.
- The user-supplied `CRUD API's in AEM Guides.pdf` documents a legacy, form-encoded CRUD surface but does not identify an AEM Guides release, deployment model, authentication/CSRF contract, or error-body schema. Treat it as documented-current evidence only after confirming the target build still exposes the endpoints.
- Keep filename, repository path, and GUID as separate identities. Never propose filename renaming as the oracle for successful explicit-GUID assignment.

### Documented Current API Baseline

- CREATE is documented as form-encoded `POST /bin/fmdita/xmleditor/create` with required `parent`, `name`, `title`, and `template`. The document does not define caller-supplied topic content, metadata, or a separate GUID field.
- GET/download is documented on form-encoded `POST /bin/referencelistener` with `operation=getdita`, `path`, and `type=UUID`; success returns a file stream. The PDF calls this a Get API even though its request line uses `POST`, so preserve that contradiction as a documentation issue rather than silently rewriting it.
- UPDATE is documented on form-encoded `POST /bin/referencelistener` with `editorData`, `operation=postDita`, `path`, and `createrev`; `createrev` controls revision creation and is documented with default `true`. It is not evidence of missing-target creation or UPSERT behavior.
- DELETE is documented as form-encoded `POST /bin/guides/assets/delete` with `path` and `force`. This delete-only `force` parameter must never be reused as evidence for the proposed UPDATE force-create control.
- The PDF documents HTTP 200 success for CREATE, GET/download, and DELETE, but does not define validation, not-found, conflict, permission, or partial-failure statuses. Do not convert HTTP 200 into a complete business-success oracle.

### Proposed Acceptance Pattern

- Given an existing client sends the documented template-only CREATE request with `parent`, `name`, `title`, and `template` and omits every new enhancement field | When the enhanced API processes the request | Then one DITA asset is created with the established template behavior and no new field becomes mandatory for that client.
- Given a CREATE request supplies a supported topic file, a human-readable filename, and valid topic content through the accepted content field | When creation succeeds | Then the persisted topic content matches the supplied payload rather than being limited to template content, and the filename remains unchanged.
- Given a CREATE request supplies supported metadata in the same call | When creation succeeds | Then the accepted metadata values are persisted on the created asset and can be read back with the created content.
- Given a CREATE request supplies a valid, available GUID separately from the filename | When creation succeeds | Then that exact GUID is assigned while the caller's filename is retained; the response and a later read identify the same single asset.
- Given UPDATE targets an existing asset | When UPDATE runs with the UPSERT control omitted, false, or true as allowed by the accepted contract | Then the existing asset is updated once and no duplicate asset is created.
- Given UPDATE targets a missing asset and force creation is omitted or false | When the call runs | Then no asset is created and the API returns the accepted not-found/creation-disabled outcome.
- Given UPDATE targets a missing asset and force creation is true | When the call runs with all required creation fields | Then exactly one asset is created using the accepted filename, content/template, metadata, and GUID rules.
- Given an existing client sends `operation=postDita` with `editorData`, `path`, and `createrev=false` or `true` for an existing asset | When UPDATE succeeds | Then content is updated at the same identity and revision creation follows the documented `createrev` value; UPSERT logic does not reinterpret that field.
- Given an existing client sends `operation=getdita`, `path`, and `type=UUID` | When GET/download succeeds | Then the same asset is returned as a file stream and the enhancement does not alter its content or identity.
- Given an existing client calls DELETE with `path` and the documented `force` state | When deletion is allowed by the existing contract | Then delete/reference handling remains unchanged and this field has no effect on UPDATE missing-target behavior.
- Given content, metadata, filename, GUID, or UPSERT validation fails before persistence | When the request completes | Then no partial new asset, duplicate identity, or partially updated metadata/content remains; if atomicity is not accepted by PM/engineering, keep this as an explicit Open Question rather than an assumed oracle.

### Required State Matrix

- First establish the target build's legacy baseline: template-only CREATE, file-stream GET/download, `editorData` UPDATE with `createrev=false/true`, and referenced/unreferenced DELETE with `force=false/true`, using the exact documented endpoints when they remain available.
- Exercise target `exists` and `missing` against force-create `omitted`, `false`, and `true`; distinguish `updated`, `created`, and `rejected` outcomes.
- Exercise content source as template-only and caller-content-only. Keep requests supplying both as an Open Question until precedence or mutual exclusion is accepted.
- Exercise GUID omitted/generated, valid explicit GUID, malformed GUID, and already-assigned GUID. Exact validation and conflict behavior require accepted API evidence.
- Exercise metadata omitted and supported metadata supplied. Add custom namespace, multi-value, protected, or invalid metadata only when the accepted schema defines those cases.
- Verify response identity and subsequent GET/read-back identity, persisted topic content, metadata, and repository filename; a successful HTTP response alone is insufficient.
- Keep `createrev` independent from the proposed UPSERT/force-create control: revision creation on an existing asset is not asset creation for a missing target.
- Keep DELETE `force` independent from the proposed UPDATE control: bypassing reference protection during delete is not permission to create a missing asset.
- Verify permissions, version creation, post-processing, reference integrity, and retry/concurrency only where the discovered endpoint or implementation proves those integration points.

### Required Open Questions

- Are the documented legacy endpoints still supported on the target build and hosting model, and is the enhancement additive to those endpoints or delivered through a versioned replacement? QA impact: the compatibility and migration matrix depends on this boundary.
- What are the exact request/response schema and final parameter names for CREATE content, CREATE/UPDATE metadata, explicit GUID, and UPDATE force creation? QA impact: automation cannot construct or validate the enhancement safely without them.
- Does CREATE reuse the documented UPDATE field name `editorData`, introduce `fileContent`, or use another type, and is it raw XML, encoded text, multipart, or form-encoded data? QA impact: payload fidelity and validation differ by representation.
- When template and caller content are both supplied, which wins or must the request be rejected? QA impact: silent precedence can create the wrong topic body.
- Which metadata properties and value types are writable, and is content/metadata/GUID persistence atomic on validation or post-processing failure? QA impact: partial assets require cleanup and can corrupt imports.
- Which GUID formats are accepted, who may assign them, and what happens for an existing GUID, an existing path, or a path/GUID mismatch? QA impact: identity collision behavior is central to external-system migration.
- What identifies the UPSERT target: repository path, filename, GUID, or a combination? What is the final force-create flag and default? It must not be confused with UPDATE `createrev` or DELETE `force`. QA impact: the exists/missing matrix depends on identity and default semantics.
- Which response status/body distinguishes `created`, `updated`, `not found`, `validation failed`, and `conflict`? QA impact: clients need deterministic branching and retry behavior.
- Is v1 limited to DITA topics, or does it include maps, bookmaps, DITAVAL, Markdown, and non-DITA assets? QA impact: do not expand the file-type matrix from the generic word `asset`.

### Same-Mechanism Retrieval

- Strong matches share caller-supplied topic content, metadata-in-create/update, independent filename/GUID assignment, or missing-target UPDATE-as-UPSERT semantics.
- Give highest weight to the same API operation plus the same identity or state transition, such as explicit-GUID collision or missing target with force creation.
- Reject editor CRUD, Assets UI creation, generic metadata, UUID display, translation import, or generic REST tickets without the same API payload and persistence mechanism.
