# Integration Component UAC Pack

Use this generic pack for current Integration issues involving external content ingestion, asset/topic CRUD APIs, caller-supplied content or metadata, explicit identity assignment, or UPDATE-as-UPSERT behavior. Current accepted scope and verified current API/implementation evidence control every endpoint, field, status, default, and supported type. Historical tickets and supplied-document examples are regression fixtures only.

## Asset CRUD API Import Contract

### Activation and Authority

- Activate only when current evidence names an API operation plus an asset/topic payload, identity, metadata, or missing-target state transition. The word `API`, a historical issue key, or an old API document alone is insufficient.
- Treat a supplied API document as evidence for the target build only after confirming current deployment/release applicability and the actual handler. Preserve document/code contradictions as gaps.
- Keep filename, repository path, product identity/GUID, version identity, and response identifier separate. A rename is not proof of explicit identity assignment.
- Keep CREATE, READ/download, UPDATE, DELETE, and UPSERT controls independent. A same-named field on another operation does not establish shared semantics.

### Current Baseline First

- Discover and record each current endpoint, HTTP method, content type, operation selector, required/optional field, default, status/body contract, authentication/CSRF rule, permission, and supported asset type from current evidence.
- Run the verified legacy/current request before testing an enhancement. New optional fields must not become mandatory or change the established result for an unchanged client.
- Read back persisted identity, path, content, metadata, version, and repository state. Transport success alone is not a business-success oracle.
- If the target handler or response contract cannot be inspected, keep current-behavior claims unresolved; never copy an endpoint, parameter, default, or status from a historical example.

### Generic State Matrix

- For CREATE, disposition template/default content, caller content, metadata, identity omitted/generated, valid explicit identity, malformed identity, collision, and path/identity mismatch only when current scope names those inputs.
- For UPDATE, test existing and missing targets against the current operation's omitted/default/false/true creation control when such a control is accepted. Do not infer its name or default.
- For an existing target, verify one intended asset is updated and no duplicate identity appears.
- For a missing target with creation disabled, verify no asset is created and the approved not-found/creation-disabled result is returned.
- For a missing target with creation enabled, verify exactly one asset is created using the approved filename/path/content/template/metadata/identity rules.
- Keep version/revision creation on an existing target separate from missing-target creation.
- Keep delete reference-bypass/force behavior separate from UPDATE creation behavior.
- For failures before or during persistence, apply only the approved atomic, partial-success, cleanup, and retry contract. If unresolved, expose the decision instead of assuming all-or-nothing behavior.

### Compatibility and Boundaries

- Preserve unchanged-client compatibility for each verified current request shape.
- Verify request identity matches response identity and subsequent read-back identity.
- Add permissions, version creation, post-processing, reference integrity, retry, concurrency, and file-type matrices only when current code/contract exposes those links.
- Keep external migration demand separate from current product capability. Customer breadth does not prove payload, permission, or status semantics.

### Required Open Questions

- What are the target deployment/release and current endpoint, method, content type, request fields, defaults, and response schema?
- Is the enhancement additive to an existing operation or delivered through a versioned replacement?
- Which content and metadata representations are accepted, and what happens when multiple content sources are supplied?
- Which identity formats are accepted, who may assign them, and how are identity/path collisions resolved?
- What identifies an UPDATE target, and what exact control/default governs missing-target creation?
- Which statuses/bodies distinguish created, updated, not found, validation failure, permission failure, conflict, partial failure, and retryable failure?
- Which asset types are in scope? Do not expand from the generic word `asset`.
- What atomicity, cleanup, idempotency, and retry behavior is approved for persistence or post-processing failures?

### Same-Mechanism Retrieval

- Strong matches share the same API operation and payload/identity/persistence state transition.
- Give highest weight to the same handler, request field, identity collision, or existing-versus-missing target branch.
- Reject editor UI CRUD, Assets UI creation, generic metadata, identity display, translation import, or generic REST issues without the same API path and transition.
- Historical evidence may create a hypothesis only after same-mechanism verification. It cannot directly authorize an endpoint, parameter, default, status, threshold, or AC.
