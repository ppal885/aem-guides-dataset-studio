"""Tests for the runtime UAC lint pass (ports the skill uac_linter's plan-text checks
into the canonical runtime so shipped plans meet the same quality bar)."""
from app.services.canonical_test_plan_reasoning_service import _lint_acceptance_criteria


def test_clean_acs_produce_no_findings():
    acs = [
        "The cross-reference label excludes the footnote callout text.",
        "The footnote body still renders exactly as authored on the page.",
        "The behaviour holds for Native PDF with DITA-OT processing on and off.",
    ]
    assert _lint_acceptance_criteria(acs) == []


def test_vague_behaviour_flagged():
    problems = _lint_acceptance_criteria(["The feature works correctly."])
    assert any(p.startswith("VAGUE_BEHAVIOR") for p in problems)


def test_vague_words_inside_a_specific_ac_are_not_flagged():
    # "works correctly" appears but the AC is specific and long enough - not filler.
    acs = [
        "The exported PDF works correctly for every locale by keeping the callout "
        "number identical between the table of contents entry and the target title."
    ]
    assert not any(p.startswith("VAGUE_BEHAVIOR") for p in _lint_acceptance_criteria(acs))


def test_duplicate_ac_flagged_on_normalized_text():
    acs = [
        "The label excludes the footnote callout text.",
        "the label excludes the footnote callout text",  # same, punctuation/case differ
    ]
    assert any(p.startswith("DUPLICATE_AC") for p in _lint_acceptance_criteria(acs))


def test_excessive_length_flagged():
    long_ac = " ".join(["word"] * 50) + "."
    problems = _lint_acceptance_criteria([long_ac])
    assert any(p.startswith("EXCESSIVE_LENGTH") for p in problems)


def test_advisory_only_no_mutation_of_inputs():
    acs = ["The feature works correctly."]
    before = list(acs)
    _lint_acceptance_criteria(acs)
    assert acs == before  # lint never rewrites the criteria
