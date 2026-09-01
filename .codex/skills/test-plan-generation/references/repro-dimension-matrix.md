# Reproduction-Dimension Matrix (UACFIX-05)

Customer-only or configuration-dependent defects must be investigated systematically
across the dimensions that actually differ - not by random regression expansion. Build
the matrix only for materially relevant dimensions.

## Dimensions (extensible)

PRODUCT_VERSION, DEPLOYMENT, OUTPUT_TYPE, PRESET, ENGINE, TEMPLATE, PAGE_LAYOUT,
DITA_OT_MODE, DITA_VERSION, MAP_VS_BOOKMAP, LOCALE, ROLE, FEATURE_FLAG,
CUSTOM_CONFIGURATION, INPUT_REPRESENTATION, EDITOR_MODE, ENTRY_POINT, DATASET_SIZE,
CONCURRENCY, BROWSER, PERSISTED_STATE, EXISTING_OUTPUT_STATE.

## Cell fields (`repro_matrix.cells[]`)

`dimension`, `customer_value`, `internal_test_value`, `known_good_value`,
`known_bad_value`, `evidence`, `materiality` (MATERIAL / IMMATERIAL),
`repro_status`, `coverage_status`, optional `open_question_ref`.

- `repro_status`: REPRO_CONFIRMED, NOT_REPRODUCED, NOT_TESTED, NOT_APPLICABLE,
  CUSTOMER_ONLY, CONFIGURATION_DEPENDENT, VERSION_DEPENDENT, UNRESOLVED.
- `coverage_status`: COVERED_BY_AC, CONFIGURATION_REGRESSION, OPEN_QUESTION,
  REJECTED, NOT_TESTED.

## Rules the gate enforces (`scripts/repro_dimension_matrix.py`)

- **Only material dimensions belong in the matrix.** An IMMATERIAL cell is flagged as
  overexpansion - do not test every possible combination; activate dimensions from the
  current Jira, domain reasoning, implementation/config branches, and Human evidence.
- **Customer reproduces, internal does not => not invalid.** A MATERIAL cell whose
  repro_status is CUSTOMER_ONLY, UNRESOLVED, or NOT_REPRODUCED must reference an Open
  Question (the unresolved differing dimension) and must NOT be coverage_status
  REJECTED. Identify the differing dimension; generate a Missing Question.
- Each cell needs a valid dimension, repro_status, materiality, coverage_status, and
  non-empty evidence; dimensions must be unique.

## Final UAC effect

Matrix findings become an AC, a configuration regression, an Open Question, or
Rejected per verified applicability. Do NOT render the whole matrix into the
customer-facing UAC - keep it in the internal manifest.

## Backward compatibility

Absent `repro_matrix` is a clean pass.
