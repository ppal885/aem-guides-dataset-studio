# Human-Feedback Delta Learner (UACFIX-08)

Classify Human edits (AI_BEFORE -> HUMAN_AFTER) into learning types instead of treating
every edit as a discovery miss. **Human feedback is the only supervisory learning
truth** - AI critique, FluffyJaws output, automated review, and model suggestions are
NOT learning truth and can never be promoted.

## Delta types (`human_feedback_delta.deltas[].delta_type`)

COVERAGE_ADDED, COVERAGE_REMOVED, SCOPE_NARROWED, SCOPE_EXPANDED, DISPOSITION_CHANGED,
OPEN_QUESTION_ADDED, OPEN_QUESTION_REMOVED, LANGUAGE_SIMPLIFIED, AC_MERGED, AC_SPLIT,
ORACLE_CHANGED, PRIORITY_CHANGED, IMPLEMENTATION_DETAIL_REMOVED.

## Learning pattern classes (`pattern_class`)

DISCOVERY_PATTERN, SCOPE_PATTERN, DISPOSITION_PATTERN, QUESTION_PATTERN,
RENDERING_LANGUAGE_PATTERN, TESTABILITY_PATTERN, NEGATIVE_BOUNDARY_PATTERN,
ENTRY_POINT_PATTERN, REPRO_DIMENSION_PATTERN. Do not put every delta in one family.

## Rules the gate enforces (`scripts/human_feedback_delta.py`)

- **Human-only supervision.** `source` is HUMAN / AI_REVIEW / FLUFFYJAWS / MODEL; a
  non-Human source can never be VALIDATING or APPROVED.
- **Language != discovery.** A presentation delta (LANGUAGE_SIMPLIFIED, AC_MERGED,
  AC_SPLIT, IMPLEMENTATION_DETAIL_REMOVED) must not be a DISCOVERY_PATTERN - route it to
  RENDERING_LANGUAGE_PATTERN / TESTABILITY_PATTERN. Keep reasoning completeness separate
  from presentation simplicity.
- **First-failure link.** A COVERAGE_ADDED delta must record `first_failed_stage` (from
  debug_qe_miss) - one of DISCOVERY, VERSION_EVIDENCE, CONFLICT_RESOLUTION, SCOPE,
  ENTRY_POINT, REPRO_DIMENSION, CANDIDATE_COMPLETENESS, SYNTHESIS, RENDERING - so the
  lesson targets the stage that actually failed (do not add a discovery rule when the
  real failure was renderer wording).
- **Promotion governance.** `promotion_state` is CANDIDATE / VALIDATING / APPROVED /
  REJECTED / EXPLORATORY / ROLLED_BACK. APPROVED requires a HUMAN source AND (>=2
  independent `human_cases`, OR a `normative_invariant`, OR a `severe_p0_p1` failure) AND
  `counterexample_search_done=true` (attach hard negatives before promotion).

## Scope learning

Scope corrections improve the ScopeApplicabilityGate patterns; they do not disable valid
investigation. Internal investigation may stay broad; the final scope becomes precise.

## Backward compatibility

Absent `human_feedback_delta` is a clean pass.
