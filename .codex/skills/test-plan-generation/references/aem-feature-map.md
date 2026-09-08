# AEM/Guides Feature Map

## Purpose

Use `data/aem_feature_map.json` as a curated domain checklist when current evidence
mentions a shared AEM or AEM Guides flow. The map helps discovery ask about native
features that may ride that flow even when a Jira ticket does not name them.

The map is advisory. A matched entry creates an `INVESTIGATION_CANDIDATE`; it does
not establish current Jira scope, implementation applicability, acceptance truth,
or an Acceptance Criterion.

## Authority and governance

- Every shipped feature entry must be `HUMAN_APPROVED`.
- Every entry must cite first-party Adobe Experience League documentation.
- The map may describe stable product feature families and shared flows only.
- Never add a Jira key, customer name, code symbol, repository path, copied Human
  UAC, or ticket-specific value to the production map.
- Model suggestions, AI reviews, and retrieved analogies may propose a curation
  change, but they cannot add or approve a production entry.
- Review deployment and configuration qualifications before approving an entry.
  A documented feature can be optional, disabled, deployment-specific, or limited
  to supported content types.

## Runtime flow

1. `dimension_synthesizer._evidence_texts()` creates `(label, text)` evidence pairs.
2. `feature_map.candidates_for()` performs case-insensitive matching against a
   surface's explicit `match` phrases.
3. A surface with no match contributes nothing.
4. A matched surface emits each approved native feature in coverage-hypothesis
   item shape with:
   - `status=INVESTIGATION_CANDIDATE`;
   - `generator=FEATURE_MAP`;
   - a canonical coverage `dimension` plus the original
     `implied_dimension_axis` used by clarification;
   - the surface, feature, shared flow, and Experience League reference;
   - the evidence labels and matched phrases that activated it.
5. `dimension_synthesizer.review_notes()` surfaces candidates without an exact,
   evidence-backed terminal decision through the existing `REVIEW DISCOVERY` path
   (compatibility exit unchanged; receipt non-postable). Tags alone do not clear it.
6. Normal evidence retrieval, applicability verification, disposition, and
   acceptance-promotion rules still apply. There is no Feature Map-to-AC shortcut.

The loader is fail-open for plan generation. Missing, malformed, unsupported, or
unapproved map content produces no candidates and never hard-fails a plan.

## Curated surfaces

### Asset upload and DAM processing

The `ASSET_UPLOAD_DAM` checklist covers:

- duplicate detection;
- versioning and Timeline;
- DAM Update Asset workflows where that workflow exists;
- processing and metadata profiles;
- metadata schemas and mandatory properties;
- Smart Tags for supported Cloud Service asset types;
- asset expiry behavior;
- configured upload restrictions where the deployment supports them.

Important qualifications:

- Native duplicate detection is disabled by default. Investigate it only under a
  configuration where it is enabled.
- DAM Update Asset is an AEM 6.5/on-premise workflow. AEM as a Cloud Service uses
  asset microservices for native processing.
- Smart Tags depend on deployment and supported asset type.
- A same-path Replace choice can remove existing metadata and earlier changes.
  Verify the documented result for the selected action; do not assume preservation.

Official sources:

- [Detect duplicate assets](https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/admin/detect-duplicate-assets)
- [Add assets and handle an existing file](https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/manage/add-assets)
- [Manage digital assets, Timeline, and versions](https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/manage/manage-digital-assets)
- [Process assets using workflows](https://experienceleague.adobe.com/en/docs/experience-manager-65-lts/content/assets/using/assets-workflow)
- [Changes in AEM Assets as a Cloud Service](https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/assets-cloud-changes)
- [Configure and use asset microservices](https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/manage/asset-microservices-configure-and-use)
- [Metadata profiles](https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/manage/metadata-profiles)
- [Metadata schemas](https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/manage/metadata-schemas)
- [Smart Tags](https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/manage/smart-tags)
- [Digital Rights Management and asset expiration](https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/assets/manage/drm)
- [Configure asset upload restrictions](https://experienceleague.adobe.com/en/docs/experience-manager-65/content/assets/administer/configuring-asset-upload-restrictions)

### Publishing output

The `PUBLISHING_OUTPUT` checklist covers output-preset consumers, baseline version
selection, condition presets, and configured post-generation workflows.

Official sources:

- [Understanding output presets](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/output-presets-aemg/generate-output-understand-presets)
- [Use a baseline for publishing](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/generate-output-use-baseline-for-publishing)
- [Use condition presets](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/conditional-content/generate-output-use-condition-presets)
- [Use a post-generation workflow](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/knowledge-base/kb-articles/workflows/using-post-generation-workflow)

### Native PDF content

The `NATIVE_PDF_CONTENT` checklist keeps **Variables** and **Variable Sets** as
separate candidates. Current evidence must name the Native PDF engine; a generic
language label, Editor operation, HTML5 preset, or DITA-OT PDF path alone must not
activate this surface. The sibling feature does not have to appear in the ticket
headline. Activation is a retrieval lead, not proof that it shares the changed path.

- **Variables** can appear in Native PDF page-layout headers, footers, or bodies.
  Inspect the placements used by the affected output and verify their shared-path
  applicability before deciding coverage.
- **Variable Sets** choose alternate values through the output preset's **Variable
  set** field. **(Default)** publishes default values; a selected custom set supplies
  that set's values.
- **Language Variables** are a different feature. Their output-language and fallback
  rules do not establish automatic language-based selection of a Variable Set.
  Similar names are not evidence that the mechanisms are equivalent.
- These two candidates are not substitutes for one another. Record each candidate's
  exact identity and disposition. One generic consumer or configuration record does
  not show that both features were considered.
- Keep a narrow publishing fix narrow: this checklist does not automatically add
  Variables editor CRUD, import/export, every page placement, or other PDF engines
  to acceptance scope. A scoped preservation check still needs current evidence.

This entry records the Human-requested Variables/Variable Sets discovery correction;
its documented source was checked on 2026-09-09. It does not claim a RAG retrieval,
an executed product test, or automatic acceptance approval for a future ticket.

Official sources:

- [Variables in the PDF output](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/output-gen-config/config-native-pdf-publish/native-pdf-variables)
- [Support for language variables](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/output-gen-config/config-native-pdf-publish/native-pdf-language-variables)

### Translation

The `TRANSLATION` checklist covers reference status, project modes and XLIFF
round trips, and completed-project cleanup.

Official sources:

- [View translation status](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translation-view-trans-state-6234)
- [Translate documents from the Map Console](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translate-documents-web-editor)

## Updating the map

For every proposed entry:

1. Confirm that the source is an official Experience League page.
2. Name the generic surface and shared flow.
3. Write generic match phrases, not implementation identifiers.
4. State the deployment, configuration, content-type, or lifecycle qualification
   in the candidate when one exists.
5. Treat a vector-distance hit as a URL candidate only. Similarity cannot confirm
   that the page supports the feature and cannot grant Human approval.
6. After Human review of both the feature and its source, set the draft entry's
   `approval_status` to `HUMAN_APPROVED`, `url_confirmed` to `true`, and
   `reference_urls` to the reviewed canonical Experience League URL or URLs. A
   surface draft may remain `PENDING_APPROVAL` while selected entries are approved.
7. Keep unapproved, partially populated, or source-mismatched entries out of the
   governed map. The confirmation utility reports already-active, merge-eligible,
   URL-candidate, and unresolved entries as separate sets. A valid source approval
   recorded before the current reference-label contract is reported separately as
   legacy/read-only; it cannot authorize a new merge.
8. Add a positive match, adjacent non-match, fail-open, and copy-parity test.
9. Run the complete self-tests and production anti-hardcoding audit before release.
