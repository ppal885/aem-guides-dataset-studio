# Native AEM Site Baseline Metadata Reference

Use this when Jira scope mentions Native AEM Site, baseline publishing, metadata propagation, output preset metadata, copy-to, or incremental publishing metadata.

## Scope

- Scope is Native AEM Site only.
- Metadata should resolve according to the selected baseline version.
- Working copy behaviour should remain unchanged.
- Metadata should continue to be picked only from fields configured in the output preset's `metadatalist`.
- Custom metadata should be supported.
- Static baseline validation and dynamic baseline validation are both in scope.
- Incremental publishing using a baseline should continue to resolve metadata from the baseline version and should not fall back to the current working copy.
- Copy-to scenarios are in scope.
- Topic content and topic metadata should resolve from the same version.
- When `Use map properties` is enabled at preset level, map metadata should pass to topic level only when that metadata does not exist on the topic.
- Metadata propagation must be validated with both new baseline and old baseline.

## Out Of Scope

- Old AEM Site output.
- Chunked content publishing modes such as by-topic and to-content.
- Metadata of multimedia assets.

## QA Behaviour Rules

- Treat baseline version as the source of truth for both content and metadata.
- Treat working copy metadata as a regression risk; it must not leak into baseline publishing.
- Verify metadata source per configured field in `metadatalist`; do not expect non-configured fields to publish.
- Verify custom metadata the same way as standard metadata: selected version, configured field, correct propagation.
- Verify map-to-topic metadata fallback only when the topic does not already have that metadata.
- Verify old and new baselines separately because metadata propagation can regress differently across existing and newly created baseline data.

## Scenario Ideas

- Publish Native AEM Site with a static baseline after changing working copy metadata -> published metadata matches the baseline version, not the working copy.
- Publish Native AEM Site with a dynamic baseline after changing working copy metadata -> published metadata resolves from the dynamic baseline selection.
- Run incremental publish using a baseline after changing topic metadata in the working copy -> incremental output keeps baseline metadata and does not fall back to current metadata.
- Publish with `metadatalist` containing selected standard and custom fields -> only configured metadata fields appear in the generated Native AEM Site output.
- Publish with `Use map properties` enabled and topic metadata missing -> map metadata propagates to the topic output.
- Publish with `Use map properties` enabled and topic metadata present -> topic metadata wins and map metadata does not overwrite it.
- Validate copy-to topics under a baseline -> copied topic content and metadata resolve from the same baseline version.
- Compare old baseline and new baseline publishing -> metadata propagation remains correct for both baseline ages.
