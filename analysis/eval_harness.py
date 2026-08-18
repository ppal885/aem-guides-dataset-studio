"""Evaluation harness for Pre-UAC plans vs reconstructed Human-UAC.

Scores a generated plan against the human-accepted requirements for one Jira using
DETERMINISTIC, mapping-driven metrics. The semantic decision "does generated item X
cover human requirement Y" is supplied as an input verdict (the evaluator/LLM makes
that call); this harness only computes reproducible aggregate metrics from those
verdicts, so the same input always yields the same score.

It consumes a scoring-input JSON and never reads the raw Jira CSVs, so it runs on
TRAIN and VALIDATION without touching BLIND (no contamination).

Metrics (per the mining spec): behavioural recall, open-question recall,
available-evidence-missed, inferable-but-not-explored, unsupported-assertion rate,
false-positive exploration rate. Stdlib only.
"""

import json
import sys

# How a human requirement was handled by the generated plan.
OUTCOME_CLASSES = (
    "COVERED_EQUIVALENTLY",
    "AVAILABLE_EVIDENCE_MISSED",
    "INFERABLE_BUT_NOT_EXPLORED",
    "CORRECTLY_DISCOVERED_AS_OPEN_QUESTION",
    "HUMAN_DOMAIN_ONLY",
    "POST_GENERATION_EVIDENCE",
    "UNSUPPORTED_AI_COVERAGE",
)
# Human requirements the system cannot fairly be expected to have known pre-UAC.
NOT_FAIRLY_EXPECTED_OUTCOMES = frozenset({"HUMAN_DOMAIN_ONLY", "POST_GENERATION_EVIDENCE"})
DISCOVERABILITY = (
    "AVAILABLE_EVIDENCE_MISSED", "INFERABLE_BUT_NOT_EXPLORED", "REQUIRES_TARGETED_RETRIEVAL",
    "HUMAN_PRODUCT_DECISION", "CUSTOMER_DOMAIN_ONLY", "POST_GENERATION_EVIDENCE",
    "NOT_REASONABLY_DISCOVERABLE",
)
GENERATED_KINDS = ("ACCEPTANCE_CRITERION", "SCENARIO", "OPEN_QUESTION", "REGRESSION", "NFR")


def validate_input(data):
    problems = []
    if not isinstance(data, dict):
        return ["scoring input must be a JSON object"]
    humans = data.get("human_requirements")
    generated = data.get("generated_items")
    matches = data.get("matches")
    if not isinstance(humans, list) or not humans:
        problems.append("human_requirements must be a non-empty list")
        humans = []
    if not isinstance(generated, list):
        problems.append("generated_items must be a list")
        generated = []
    if not isinstance(matches, list):
        problems.append("matches must be a list")
        matches = []
    human_ids = set()
    for h in humans:
        if not isinstance(h, dict) or not h.get("id"):
            problems.append("each human_requirement needs an id")
            continue
        human_ids.add(h["id"])
        if h.get("discoverability") and h["discoverability"] not in DISCOVERABILITY:
            problems.append(f"human_requirement {h['id']}: invalid discoverability '{h['discoverability']}'")
    gen_ids = set()
    for g in generated:
        if not isinstance(g, dict) or not g.get("id"):
            problems.append("each generated_item needs an id")
            continue
        gen_ids.add(g["id"])
        if g.get("kind") not in GENERATED_KINDS:
            problems.append(f"generated_item {g['id']}: kind must be one of {', '.join(GENERATED_KINDS)}")
    seen = set()
    for m in matches:
        if not isinstance(m, dict):
            problems.append("each match must be an object")
            continue
        hid = m.get("human_id")
        if hid not in human_ids:
            problems.append(f"match references unknown human_id '{hid}'")
        if hid in seen:
            problems.append(f"human requirement '{hid}' has more than one match verdict")
        seen.add(hid)
        if m.get("outcome") not in OUTCOME_CLASSES:
            problems.append(f"match {hid}: outcome must be one of {', '.join(OUTCOME_CLASSES)}")
        gid = m.get("generated_id")
        if gid and gid not in gen_ids:
            problems.append(f"match {hid}: references unknown generated_id '{gid}'")
    return problems


def _rate(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def score(data):
    """Return a deterministic metrics dict. Assumes validate_input passed."""
    humans = data.get("human_requirements", [])
    generated = data.get("generated_items", [])
    outcome_by_human = {m["human_id"]: m["outcome"] for m in data.get("matches", []) if isinstance(m, dict) and m.get("human_id")}

    # a human requirement with no recorded verdict is treated as missed
    fair, covered, missed, inferable = 0, 0, 0, 0
    human_domain_only, post_generation = 0, 0
    oq_total, oq_recalled = 0, 0
    for h in humans:
        outcome = outcome_by_human.get(h["id"], "AVAILABLE_EVIDENCE_MISSED")
        if outcome == "HUMAN_DOMAIN_ONLY":
            human_domain_only += 1
        if outcome == "POST_GENERATION_EVIDENCE":
            post_generation += 1
        if outcome not in NOT_FAIRLY_EXPECTED_OUTCOMES:
            fair += 1
            if outcome == "COVERED_EQUIVALENTLY":
                covered += 1
            elif outcome == "AVAILABLE_EVIDENCE_MISSED":
                missed += 1
            elif outcome == "INFERABLE_BUT_NOT_EXPLORED":
                inferable += 1
        if (h.get("type") == "OPEN_QUESTION") or (h.get("requirement_type") == "OPEN_QUESTION"):
            oq_total += 1
            if outcome in ("CORRECTLY_DISCOVERED_AS_OPEN_QUESTION", "COVERED_EQUIVALENTLY"):
                oq_recalled += 1

    acs = [g for g in generated if g.get("kind") == "ACCEPTANCE_CRITERION"]
    acs_no_evidence = [g for g in acs if not (g.get("evidence") or [])]
    matched_gen_ids = {m.get("generated_id") for m in data.get("matches", []) if m.get("outcome") == "COVERED_EQUIVALENTLY"}
    unsupported_gen = [g for g in generated
                       if g.get("kind") in ("ACCEPTANCE_CRITERION", "SCENARIO")
                       and g["id"] not in matched_gen_ids and not (g.get("evidence") or [])]

    return {
        "human_requirements_total": len(humans),
        "fairly_expected": fair,
        "human_domain_only": human_domain_only,
        "post_generation_evidence": post_generation,
        "behavioural_recall": _rate(covered, fair),
        "available_evidence_missed": missed,
        "available_evidence_missed_rate": _rate(missed, fair),
        "inferable_but_not_explored": inferable,
        "open_question_recall": _rate(oq_recalled, oq_total),
        "unsupported_assertion_rate": _rate(len(acs_no_evidence), len(acs)),
        "false_positive_exploration": len(unsupported_gen),
        "generated_total": len(generated),
    }


def evaluate(data):
    problems = validate_input(data)
    if problems:
        return {"valid": False, "problems": problems}
    return {"valid": True, "metrics": score(data)}


# --- self-tests --------------------------------------------------------------

def _selftest():
    def check(name, cond):
        assert cond, f"FAILED: {name}"
        print(f"ok: {name}")

    data = {
        "human_requirements": [
            {"id": "H1", "type": "ACCEPTANCE_BEHAVIOR", "discoverability": "AVAILABLE_EVIDENCE_MISSED"},
            {"id": "H2", "type": "REGRESSION", "discoverability": "INFERABLE_BUT_NOT_EXPLORED"},
            {"id": "H3", "type": "OPEN_QUESTION", "discoverability": "HUMAN_PRODUCT_DECISION"},
            {"id": "H4", "type": "ACCEPTANCE_BEHAVIOR", "discoverability": "CUSTOMER_DOMAIN_ONLY"},
        ],
        "generated_items": [
            {"id": "G1", "kind": "ACCEPTANCE_CRITERION", "evidence": ["Jira description"]},
            {"id": "G2", "kind": "ACCEPTANCE_CRITERION", "evidence": []},
            {"id": "G3", "kind": "OPEN_QUESTION", "evidence": ["Jira comment"]},
        ],
        "matches": [
            {"human_id": "H1", "outcome": "COVERED_EQUIVALENTLY", "generated_id": "G1"},
            {"human_id": "H2", "outcome": "INFERABLE_BUT_NOT_EXPLORED"},
            {"human_id": "H3", "outcome": "CORRECTLY_DISCOVERED_AS_OPEN_QUESTION", "generated_id": "G3"},
            {"human_id": "H4", "outcome": "HUMAN_DOMAIN_ONLY"},
        ],
    }
    r = evaluate(data)
    check("valid input scores", r["valid"] is True)
    m = r["metrics"]
    # H4 is HUMAN_DOMAIN_ONLY -> excluded from fair denominator (3 fair: H1,H2,H3)
    check("human_domain_only excluded from denominator", m["fairly_expected"] == 3 and m["human_domain_only"] == 1)
    check("behavioural recall is 1/3", m["behavioural_recall"] == round(1 / 3, 4))
    check("open-question recall is 1/1", m["open_question_recall"] == 1.0)
    check("unsupported assertion rate is 1/2 (G2 has no evidence)", m["unsupported_assertion_rate"] == 0.5)
    check("inferable-but-not-explored counted", m["inferable_but_not_explored"] == 1)

    bad = {"human_requirements": [], "generated_items": [], "matches": []}
    check("empty human_requirements is rejected", evaluate(bad)["valid"] is False)
    badm = {"human_requirements": [{"id": "H1"}], "generated_items": [], "matches": [{"human_id": "H9", "outcome": "COVERED_EQUIVALENTLY"}]}
    check("unknown human_id in match is rejected", any("unknown human_id" in p for p in evaluate(badm)["problems"]))
    print("\nALL EVAL-HARNESS SELF-TESTS PASSED")


def main(argv):
    if argv and argv[0] == "--selftest":
        _selftest()
        return 0
    if not argv:
        print("usage: eval_harness.py <scoring-input.json> | --selftest", file=sys.stderr)
        return 2
    data = json.loads(open(argv[0], encoding="utf-8").read())
    print(json.dumps(evaluate(data), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
