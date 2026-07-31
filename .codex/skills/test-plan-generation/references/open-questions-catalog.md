# Open Questions Catalog

Use this before writing the `Open Questions` section. Ask only questions that affect QA sign-off, expected behaviour, environment setup, or scenario coverage.

## Rules

- Do not ask questions already answered by Jira, RAG, Figma, PR, repo evidence, comments, or acceptance criteria.
- Prefer specific, answerable questions over broad prompts.
- Keep questions plain English and tester-facing.
- Group related unknowns in one bullet when possible.
- If no meaningful unknown remains, write `No open questions from current evidence`.

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
