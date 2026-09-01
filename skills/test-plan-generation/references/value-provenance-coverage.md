# Value-Provenance Coverage (generic anti-miss gate)

A recurring miss: when a ticket is about a VALUE (property, metadata, attribute, config,
or state) written to an output/artifact, the ACs cover only ONE way the value is set -
usually the authoring UI or a preset - and ignore the other channels the value can
arrive through. The product reads the value from the repository, so a value set through
any channel must be handled.

## Value-provenance channels to enumerate

- **Authoring UI** (topic/map properties, preset UI).
- **Configuration / preset** (which names/values a preset supplies).
- **Source map/topic file** (metadata authored in the DITA source).
- **Repository node via CRX/DE** - `jcr:content/metadata` on the source asset, editable
  directly in CRX/DE or the DAM properties view. **This is the most commonly missed one.**
- **API / import** (assets or metadata created programmatically).
- **Migration** (values carried in from a prior version/deployment).

## Rule the gate enforces (`scripts/value_provenance_coverage.py`)

The check activates when the Acceptance Criteria concern a value written to/read from an
output (signals: metadata.xml, sourceProps, File (Asset) properties, metadata/property
value, "written to metadata", etc.). When active, at least one value-provenance channel
beyond the authoring UI must be addressed in the ACs - typically the repository/source
node (CRX/DE / jcr:content/metadata) - and the AC must assert the product uses the
correct source value. Non-value tickets are unaffected.

## Why this gate exists (the deeper lesson)

The other skill gates are structural/consistency validators: they check that a declared
block is well-formed, but they cannot force discovery of a dimension the author never
considered. Value provenance is a dimension that was silently skipped, so it needed a
HARD, signal-activated requirement (like the publishing DITA-OT/preset gate) rather than
another opt-in structural check. When a new recurring miss class is found, prefer a
signal-activated forcing gate over an opt-in block.

Backward-compatible: non-value tickets pass; value tickets that already cover a
provenance channel pass.
