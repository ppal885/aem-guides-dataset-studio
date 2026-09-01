# Baseline-Aware Publishing Metadata Contract

Use this generic reference when current evidence connects a publishing output to baseline/version selection and metadata propagation. It does not make Native AEM Site, any baseline type, metadata key, preset field, copy-to behavior, or incremental mode automatically in scope.

## Scope Resolution

- Record the exact output type, preset, DITA-OT state, baseline type, source/target deployment, metadata configuration, propagation option, content types, and full/incremental mode from current source facts.
- For every candidate mode or surface, mark `IN_SCOPE`, `OUT_OF_SCOPE`, or `UNRESOLVED`. Do not import an old output matrix.
- Treat working copy, selected baseline version, generated content, and generated metadata as distinct identities.
- Treat static/dynamic baselines, old/new baseline records, copy-to, incremental publishing, and map-to-topic propagation as separate dimensions. Include each only when current evidence or a verified shared path makes it applicable.

## Generic Behavior Relationships

- When accepted scope says a baseline controls output, content and metadata must resolve from the same approved version unless an explicit exception is authorized.
- Only metadata fields selected by the current preset/configuration should propagate. A remembered field name or old preset structure is not authority.
- Standard and custom metadata use the same version/selection rules only when verified consumers share that path.
- A map-to-topic fallback must not overwrite topic metadata unless the approved precedence contract says it should.
- Incremental output must not silently mix baseline and working-copy identity. Disposition unchanged-content rewrite and stale-output behavior in the generated-output contract.
- Copy-to or alias identity requires explicit source, destination, version, content, and metadata rules; do not assume parity with direct topic references.

## Test Oracles

- Inspect the generated output, not only job status. Verify source version, metadata presence/absence, value, target path, content/metadata identity consistency, duplicates, stale output, and unrelated-field preservation.
- Change working-copy content/metadata after creating the selected baseline and confirm the generated result follows the approved identity source.
- Use metadata values that differ across candidate sources so fallback or mixed-version output is visible.
- Verify positive and negative propagation: configured versus unconfigured fields, topic value present versus absent, and each current-evidence baseline/publish mode.
- Preserve output-specific behavior for modes declared out of scope; do not turn cross-mode regression into an AC without verified shared-path impact.

## Required Open Questions

- Which output type/preset and DITA-OT mode are in scope?
- Which baseline types and existing/new baseline records must be supported?
- Which metadata source/configuration and exact propagation precedence apply?
- Are full, incremental, copy-to, and map-to-topic fallback paths in scope?
- What is the expected result for missing versions, missing metadata, stale generated output, and mixed-version conflicts?
- Which output modes share the implementation path and require regression coverage?
