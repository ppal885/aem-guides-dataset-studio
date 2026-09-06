# Customer CSV discovery (advisory only)

## Two different maps

The approved `data/aem_feature_map.json` contains Experience League domain truth.
Do not put customer fingerprints or mined historical cases into that map.

Customer checklists are corpus-side profile data in
`scripts/uac_eval/customer_profiles.json`, schema
`aem-guides-customer-discovery-map-v1`. `customer_discovery.py` loads that packet
from the Dataset Studio checkout (optionally selected by `AEM_STUDIO_REPO`).
A standalone client can instead attach the same packet under manifest
`customer_discovery_profiles`. Record its exact content-derived version; never
claim that a local packet was freshly retrieved from the VM.

No packet, malformed data, or unsupported governance produces a recorded gap and
no candidate. The loader does not fetch, approve, or rewrite profiles. A newly
installed client without the corpus-side packet does not silently have this data.

## Matching and use

The matcher is generic: exact issue-label membership OR an explicit component
plus a semantic input example from the profile. Customer names in prose are not
identity evidence. Input/language examples live in data, never axis-specific code.
A non-matching ticket receives no profile candidates.

Matched entries become `CUSTOMER_PROFILE` / `INVESTIGATION_CANDIDATE`, with source
`LEARNED`, promotion state `VALIDATING`, authority `SUPPORTING_DISCOVERY`, and
confidence at most 0.3. They carry profile version, source hash, matching current
evidence labels and source-case references. They do not become ACs, automatic
Human feedback events, mandatory acceptance scope or required product features.

The Phase 6.5 sweep adds these through the existing synthesizer. Unrepresented
items use the existing `REVIEW DISCOVERY` note. Represent each exact equivalence
key in coverage hypotheses; a broad axis cannot conceal another checklist item.
Apply current-source verification, OOS decisions and ordinary promotion gates.
Unresolved material decisions still require the normal ask-first clarification;
do not manufacture a verdict to get a green gate.

## Import safety

Use `scripts/uac_eval/ingest_customer_csv.py --csv <export.csv> --customer <label>
--dry-run` first. Repeated label/component columns are parsed by header position.
The importer preserves source AC text only where nonempty, never generates ACs,
and keeps all rows historical/supporting. `--apply` uses the existing configured
`jira_qa` and embedding services, with no generation/enrichment/LLM path.

Run on the intended host: updating a workstation's local Chroma does not update
the VM. Quiesce other index writers before maintenance. Preserve existing keys;
metadata-only reconciliation must retain original customers, document text,
embeddings and authorities. A write failure is not proof that a key was absent.
Keep raw CSV and audit exports outside publicly served dashboard files.

## Blinded proof

Select a held-out issue before generation and exclude its whole key from ingest
and every history retrieval, including previously indexed chunks. Do not expose
its historical AC to the author. Freeze the source-only input and discovery trace
first, then reveal Human reference solely for evaluator comparison. Distinguish
a successful advisory sweep from a completed canonical UAC; a mocked/offline run
cannot prove live VM learning or a postable plan.
