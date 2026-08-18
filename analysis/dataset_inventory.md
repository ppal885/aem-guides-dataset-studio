# QE Reasoning-Pattern Mining — Dataset Inventory (Step 0)

Metadata-only inventory of the two historical AEM Guides Jira CSV exports. **No
Acceptance-Criteria or comment TEXT is stored in the normalized index** — only
metadata and evidence-source availability flags. Full-text Human-UAC reconstruction
happens later, from TRAIN only, so the BLIND set stays clean (Step 18).

## Sources

| Dataset | File | Rows | Columns |
|---|---|---|---|
| customer_features | Jira 2026-08-18T03_57_32+0000.csv | 139 | 388 |
| abs | Jira 2026-08-17T20_59_43+0000.csv | 57 | 338 |

Repeated columns (multi-valued): `Labels` (16), `Comment` (58 features / fewer ABS),
`Component/s` (2), `Fix Version/s` (2), plus many `Custom field (...)` columns. The
inventory collapses each multi-valued field across its columns.

## Customer Features (139)

- Acceptance Criteria field populated: **62 / 139** (45%)
- `UAC_Done` label present: **86 / 139** (62%) — confirms UAC_Done > AC-field population
- Issues with comments: **139 / 139** (100%)
- Issue type: Customer Request (139)
- Status: Closed (137), UAT (2)
- Resolution: Fixed (133), Have New Info (1), Duplicate (1), Unresolved (2), Done (1), Complete (1)
- Primary component: Authoring (39), Publishing (30), Review (20), Asset Management (10), Translation (7), None (7), Platform (5), Oxygen (5), Native_PDF (4), Reports (2), Citation Management (2), Baseline (2), Miscellaneous (2), Learning (1), AI (1), Schematron (1), Editor (1)
- Top labels: customer-Features (139), Doc_Required (107), UAC_Done (86), Automated (71), Triaged (33), SWIFT (33), IBM (27), Workday (23), Shift_Left_Guides (21), MayoClinic (…)

## ABS (57)

- Acceptance Criteria field populated: **21 / 57** (37%)
- `UAC_Done` label present: **31 / 57** (54%)
- Issues with comments: **57 / 57** (100%)
- Issue type: Customer Request (57)
- Status: Closed (49), Open (5), In Progress (1), UAT (1), Ready (1)
- Resolution: Fixed (46), Unresolved (8), Rejected (1), Cannot Reproduce (1), Not a Bug (1)
- Primary component: Authoring (36), Publishing (6), Editor (3), Platform (3), Asset Management (2), Miscellaneous (2), Database (1), Baseline (1), None (3)
- Top labels: ABS (57), customer-Bugs (33), UAC_Done (31), fluffyjaws-investigation (21), Automated (18), Triaged (16), Won't_Automate (15), sla3 (15)

## Key column map (per issue)

`Issue key`, `Summary`, `Issue Type`, `Status`, `Resolution`, `Priority`,
`Component/s`, `Labels`, `Custom field (Acceptance Criteria)`, `Description`,
`Comment` (chronological, multi-column), `Fix Version/s`, `Created`, `Updated`,
customer via `Custom field (Customer Names)` / `(Customers)` / `(Beta Customer Name)`.
`UAC_Done` is a **label value**, not a column.

## Benchmark split (deterministic, Step 17)

Stratified by (primary_component x acceptance-criteria-populated), sorted-slice
60/20/20 — fully reproducible (no RNG; seed tag `aem-guides-qe-mining-v1`). Keys and
sha256 checksums saved under `benchmark/`.

| Dataset | TRAIN | VALIDATION | BLIND |
|---|---|---|---|
| customer_features | 84 | 26 | 29 |
| abs | 37 | 9 | 11 |

Files: `benchmark/customer_features_{train,validation,blind}.txt`,
`benchmark/abs_{train,validation,blind}.txt`, `benchmark/checksums.json`.

## Benchmark contamination status

**Clean.** Only metadata (types, status, components, labels, counts, availability
flags) was inspected globally. No AC/comment TEXT was read or stored, and the split
was frozen BEFORE any Human-UAC reconstruction. Mining (pattern discovery/ranking)
will read full text from TRAIN only; VALIDATION is for evaluation; BLIND stays sealed.

## Next step (per the roadmap)

BACKGROUND branch continues: pattern discovery + ranking from **TRAIN only** (Features
and ABS mined independently, then shared-pattern intersection) alongside the
architecture audit (generic schemas, evaluation harness) — then MINING FREEZE.
`analysis/pattern_traceability.csv` is the priority output (every pattern traced to
>=2 real TRAIN Jira, never invented).
