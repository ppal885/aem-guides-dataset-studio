# Open Questions Catalog

Use this before writing the `Open Questions` section. Ask only questions that affect QA sign-off, expected behaviour, environment setup, or scenario coverage.

## Rules

- Do not ask questions already answered by Jira, RAG, Figma, PR, repo evidence, comments, or acceptance criteria.
- Prefer specific, answerable questions over broad prompts.
- Keep questions plain English and tester-facing.
- Group related unknowns in one bullet when possible.
- Prefix each real question `- OQ-##:` using unique, contiguous IDs starting at `OQ-01`, preserve source order, and include literal `QA impact:` describing what each plausible answer changes. Use the same ordered IDs in the evidence manifest.
- If no meaningful unknown remains, write exactly `- No open questions from current evidence` as the only bullet and record an empty manifest list.

## Permission And Role Questions

- Which user roles must be covered: admin, author, reviewer, publisher, translation manager, or restricted DAM/editor user?
- Should the behaviour differ for users with read-only, edit, delete, publish, translation, or workflow permissions?
- Are folder-level permissions, project-level permissions, or profile-level permissions part of the acceptance criteria?
- Should denied users see hidden actions, disabled actions, or a visible error message?

## XML Editor Config Questions

- Which XML Editor profile or folder profile must be used for validation?
- Are any editor settings, toolbar actions, content references, keyspace settings, map settings, or review settings required?
- Should behaviour be verified in the old editor, new editor, or both?
- Are custom templates, custom DITA specialization, subject scheme, validation, or Schematron settings involved?

## AEM Config Questions

- Which AEM deployment type is in scope: Cloud Service, 6.5 on-premise, AMS, or both cloud and on-premise?
- Which AEM configs must be enabled or disabled: workflows, launchers, DAM update asset, upload restrictions, duplicate detection, versioning, indexing, replication, or OSGi configs?
- Are there runmode, tenant, folder-level, or permissions differences that must be tested?
- Are author, publish, preview, or Dynamic Media environments part of the expected flow?

## Test Data And Environment Matrix Questions

- Which exact test data is required: DITA topic/map/bookmap, assets, mixed file types, large files, localized content, baseline fixtures, review tasks, translation projects, or existing customer-like content?
- Which environment matrix is mandatory: Cloud, on-premise, AMS, old UI, new UI, browser, OS, service pack, feature flag, tenant, or build type?
- Should QA create fresh content, reuse migrated/old content, or validate both fresh and upgraded/migrated fixtures?
- Which setup preconditions must be recorded: post-processing state, indexing completion, workflow status, permissions, profile settings, output preset, or external service config?

## Backend/API Contract Questions

- Which API endpoint, method, query/body parameters, encoding rules, response fields, status codes, and error bodies are in scope?
- Should batch requests isolate one bad item from the rest, de-duplicate repeated inputs, preserve ordering, or return partial success?
- Which logs should appear or not appear, and should validation use UI status, API response, repository state, Splunk, or service logs?
- Are backward-compatible response shapes required for existing UI callers, automation clients, or integrations?

## Operational Incident And Recovery Questions

- Is the requested outcome immediate cleanup/service restoration, a permanent product safeguard, workflow/config correction, resource increase, or all of these?
- Which exact output type, environment/build, workflows, job/output UUIDs, target paths, queue states, and customer-like fixture sizes are in scope?
- What completion SLA applies, and how long may a job remain in Waiting, Executing, Post Publishing, cancellation requested, or another non-terminal state before it is considered stuck?
- Which measurable defensive-progress bound applies (items, pages, cursor repeats, no-progress attempts, elapsed time, or resource use), what is its approved value/source, and what exact state is reported when it fires?
- Which exception/error categories are retryable versus terminal; what are the maximum attempts, delay/backoff source, short-circuit rule, exhausted terminal result, and aggregate log limit across attempts?
- Which recurrence source owns retry behavior: scheduler/deployment trigger, queue retry/redelivery, or an in-run loop? Could more than one source cause duplicate or overlapping execution?
- Which failure phases are in scope: resource/session acquisition, query creation/execution, result iteration, item mutation/delete, save/commit, refresh/cleanup, and final result reporting? What persisted and visible state must each leave?
- For concurrent operations targeting the same or overlapping destinations, should the system serialize, lock, retry, fail fast, or isolate jobs by path?
- What must happen to partial writes, previously valid output, temporary nodes, history nodes, workflow instances, and queued successor jobs after failure or cancellation?
- Must Waiting jobs auto-resume after recovery, or is an explicit retry/restart required?
- Which exact nodes/workflows may cleanup remove, and what correlation, backup, approval, audit, rollback, and unrelated-state preservation checks are mandatory?
- How should author-pod restart, deployment, workflow restart, network interruption, timeout, and repeated cancellation affect active and queued jobs?
- Is cooperative cancellation distinct from service/pod shutdown, and what exact terminal state, checkpoint/rollback behavior, and successor-job behavior applies to each?
- During traversal or paging, what snapshot semantics apply when source content is added, deleted, renamed, or updated? What no-skip/no-duplicate oracle proves correctness without prescribing a paging implementation?
- Which trigger/caller matrix is required (single-item action, full-profile/bulk action, manual invocation, schedule, deployment, restart), and which environments/build families implement each path?
- When failure occurs before a path/page/item is known, which explicit fallback value and correlation fields must logs/status expose?
- Which CPU, memory, heap, indexing, repository, and workflow metrics decide whether a resource increase is required rather than a code/config fix?
- Which correlation IDs, job/output/workflow UUIDs, target paths, stage timings, retry counts, terminal reasons, and log messages must QA capture?
- What generated-output oracle is required beyond UI/build success: page/file count, links, assets, metadata, navigation, output history, workflow completion, or orphan-state checks?
- Can destructive failure and cleanup scenarios run only on a production-equivalent clone, and which production checks are safe after engineering-approved remediation?
- What deterministic test hook injects each failure/retry/cancel/shutdown/partial-write condition, which endpoint/state is polled, where does the timeout come from, what output-integrity oracle is asserted, and how is cleanup guaranteed?

## On-Premise Release Upgrade Impact Questions

- Which exact on-premise source and target versions/service packs must be tested, including the starting build and upgraded build?
- Which existing customer configs must be retained after upgrade: XML Editor settings, `ui-config.json`, custom CSS, templates, snippets, labels, shortcuts, DITA attributes, DITA elements, OSGi configs, workflow configs, or folder profiles?
- Which defaults changed in the target release, and should QA verify fresh-install defaults separately from upgraded-instance retained values?
- Are manual post-upgrade steps, config merges, cache/index rebuilds, package installs, or compatibility scripts required before validation?
- Should upgrade impact be compared against Cloud behaviour, older on-prem behaviour, or both?
- Which backward-compatibility or rollback risks must be covered if the upgraded instance contains old maps, topics, baselines, presets, or custom editor configuration?

## Translation Config Questions

- Which translation provider/configuration must be used for the ticket?
- Are translation projects, language copies, language roots, baseline/versioning, review states, or translation memory involved?
- Should tests cover source maps/topics, translated output paths, post-processing rules, or translation dashboard status?
- Should cloud and on-premise translation behaviour be verified separately?

## DITA Questions

- Which DITA constructs are in scope: map, bookmap, topic, task, concept, reference, keyref, conref, conkeyref, xref, reltable, ditaval, subject scheme, metadata, or specialization?
- Are invalid DITA, broken references, duplicate IDs, conditional processing, chunking, copy-to, or profiling required as negative coverage?
- Should test data include nested maps, large maps, reusable topics, mixed media, or localized content?
- Which DITA version or product-supported subset matters for this Jira?

## DITA-OT, Publishing, PDF, And HTML5 Questions

- Which output types must be verified: PDF, Native PDF, PDF2, HTML5, AEM Sites, or custom output preset?
- Which publishing engine/version is expected: DITA-OT, AEM Guides publishing, Native PDF, or a custom plugin?
- Which output preset, transformation scenario, CSS, template, ditaval, baseline, or metadata settings must be used?
- What output oracle should be checked: generated files, navigation, TOC, links, images, variables, index terms, numbering, styling, language, accessibility, or logs?
- Should failures be validated in UI status, publishing logs, generated output, or backend job status?

## Native AEM Site Baseline Metadata Questions

- Confirm the output type is Native AEM Site only and old AEM Site is out of scope.
- Which baseline types must be tested: static baseline, dynamic baseline, old baseline, new baseline, or all of these?
- Which output preset and `metadatalist` fields are expected, including custom metadata fields?
- Is `Use map properties` enabled at preset level, and which map metadata should fall back to topic level when topic metadata is missing?
- Should incremental publishing, full publishing, and copy-to topics all be verified against baseline metadata resolution?
- Which metadata should explicitly remain out of scope, such as multimedia metadata or chunked content modes?
