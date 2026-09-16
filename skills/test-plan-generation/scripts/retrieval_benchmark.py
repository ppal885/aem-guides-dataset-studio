"""Question-level retrieval benchmark (RAG-Q1) - offline evaluation + metrics.

WHY THIS EXISTS
---------------
Evaluates question-bound retrieval and evidence admission on a controlled
offline fixture dataset - never on final generated UAC prose, never against a
live index.  Retrieval and admission are measured separately:

- retrieval metrics describe which candidates the ranked list surfaced;
- admission metrics describe what the admission ceiling allowed - a hard
  negative being RETRIEVED is not necessarily a retrieval failure, but a hard
  negative being ADMITTED as decisive evidence is a serious admission failure.

The most important quality metric is DECISIVE_EVIDENCE_MISADMISSION_RATE:
cases where non-decisive or wrong-applicability evidence is admitted as
decisive.  High recall with unsafe admission is not acceptable.

Each benchmark item carries: question_id, question, product_context,
applicability, expected_source_class, known_decisive_sources (when
available), acceptable_supporting_sources, hard_negative_sources (each tagged
with a kind), an unanswerable flag, and a fixture candidate list (ranked
structural facts, not prose).  Admission decisions come from
``retrieval_admission.max_admissible_relationship`` - the same ceiling the
production gate enforces - so the benchmark measures the contract, not a
parallel implementation.

Live smoke (``--live``) only reports the existing read-only gateway status
through ``offline_retrieval.retrieval_status``; it never reindexes, writes
the corpus, or enables providers, and a connectivity PASS is not
semantic-quality proof.

Named domains are evaluation fixtures only; nothing here is referenced by
production reasoning.  Stdlib only.
"""
from __future__ import annotations

import json
import sys

import retrieval_admission

EVAL_K = 5


def _cand(source_id, rank, relationship_facts, **over):
    """A fixture candidate: structural facts only, no UAC prose."""

    row = {
        "retrieval_result_id": f"RR-{source_id}",
        "source_id": source_id,
        "chunk_id": f"{source_id}#c1",
        "rank": rank,
        "retrieval_score": round(0.99 - 0.03 * rank, 3),
        "source_type": "OFFICIAL_PRODUCT_DOC",
        "applicability": "CONFIRMED",
        "fetched": True,
        "limitations": [],
    }
    row.update(relationship_facts)
    row.update(over)
    return row


# --------------------------------------------------------------------------
# Offline fixture dataset.  candidate "hint" fields drive the admission
# ceiling; hard negatives are tagged with kind for the admission metrics.
# --------------------------------------------------------------------------
BENCHMARK = [
    {
        "question_id": "BENCH-OH-1",
        "domain": "output-history",
        "question": "Which configuration property controls how long entries "
                    "are retained?",
        "product_context": "current release",
        "applicability": "current release, same console",
        "expected_source_class": "OFFICIAL_PRODUCT_DOC",
        "known_decisive_sources": ["DOC-OH-RETENTION"],
        "acceptable_supporting_sources": ["DOC-OH-OVERVIEW"],
        "hard_negative_sources": ["DOC-OH-NEARBY-PROP", "DOC-OH-OLD-RELEASE"],
        "unanswerable": False,
        "request": {"subject_key": "retention-period-property"},
        "candidates": [
            _cand("DOC-OH-RETENTION", 1,
                  {"subject_key": "retention-period-property"}),
            _cand("DOC-OH-OVERVIEW", 2, {}, applicability="UNCLEAR"),
            _cand("DOC-OH-NEARBY-PROP", 3,
                  {"subject_key": "display-limit-property"}),
            _cand("DOC-OH-OLD-RELEASE", 4, {}, applicability="WRONG"),
            _cand("BLOG-OH", 5, {}, fetched=False,
                  source_type="OTHER_APPROVED_SOURCE"),
        ],
        "hard_negative_kinds": {"DOC-OH-NEARBY-PROP": "NEARBY_PROPERTY",
                                "DOC-OH-OLD-RELEASE": "WRONG_VERSION"},
    },
    {
        "question_id": "BENCH-NPDF-1",
        "domain": "native-pdf",
        "question": "Which engine produces the PDF in the current flow?",
        "product_context": "current release, native engine surface",
        "applicability": "native engine surface",
        "expected_source_class": "OFFICIAL_PRODUCT_DOC",
        "known_decisive_sources": ["DOC-NPDF-ENGINE"],
        "acceptable_supporting_sources": [],
        "hard_negative_sources": ["DOC-LEGACY-ENGINE"],
        "unanswerable": False,
        "request": {},
        "candidates": [
            _cand("DOC-LEGACY-ENGINE", 1, {}, applicability="WRONG"),
            _cand("DOC-NPDF-ENGINE", 2, {}),
        ],
        "hard_negative_kinds": {"DOC-LEGACY-ENGINE": "WRONG_SURFACE"},
    },
    {
        "question_id": "BENCH-TRANSL-1",
        "domain": "translation",
        "question": "Does the review state persist across a refresh?",
        "product_context": "current release",
        "applicability": "current release",
        "expected_source_class": "JIRA_EXPECTED_RESULT",
        "known_decisive_sources": ["JIRA-CUR-EXPECTED"],
        "acceptable_supporting_sources": ["JIRA-HIST-PERSIST"],
        "hard_negative_sources": ["JIRA-HIST-RESET"],
        "unanswerable": False,
        "request": {},
        "candidates": [
            _cand("JIRA-CUR-EXPECTED", 1, {}, source_type="JIRA_EXPECTED_RESULT"),
            _cand("JIRA-HIST-PERSIST", 2, {}, source_type="HISTORICAL_JIRA",
                  is_historical=True, applicability="UNCLEAR"),
            _cand("JIRA-HIST-RESET", 3, {}, source_type="HISTORICAL_JIRA",
                  is_historical=True, applicability="WRONG"),
        ],
        "hard_negative_kinds": {"JIRA-HIST-RESET": "HISTORICAL"},
    },
    {
        "question_id": "BENCH-ED-1",
        "domain": "editor",
        "question": "Where is the setting toggled in the current editor?",
        "product_context": "current release, new editor surface",
        "applicability": "new editor surface",
        "expected_source_class": "OFFICIAL_PRODUCT_DOC",
        "known_decisive_sources": ["DOC-EDITOR-NEW"],
        "acceptable_supporting_sources": [],
        "hard_negative_sources": ["DOC-EDITOR-OLD"],
        "unanswerable": False,
        "request": {},
        "candidates": [
            _cand("DOC-EDITOR-NEW", 1, {}),
            _cand("DOC-EDITOR-OLD", 2, {}, applicability="WRONG"),
        ],
        "hard_negative_kinds": {"DOC-EDITOR-OLD": "WRONG_SURFACE"},
    },
    {
        "question_id": "BENCH-ASSETS-1",
        "domain": "assets-view",
        "question": "Is the action available in the current assets surface?",
        "product_context": "cloud deployment",
        "applicability": "cloud assets surface",
        "expected_source_class": "OFFICIAL_PRODUCT_DOC",
        "known_decisive_sources": ["DOC-ASSETS-CLOUD"],
        "acceptable_supporting_sources": [],
        "hard_negative_sources": ["DOC-ASSETS-65"],
        "unanswerable": False,
        "request": {},
        "candidates": [
            _cand("DOC-ASSETS-CLOUD", 1, {}),
            _cand("DOC-ASSETS-65", 2, {}, applicability="WRONG"),
        ],
        "hard_negative_kinds": {"DOC-ASSETS-65": "WRONG_VERSION"},
    },
    {
        "question_id": "BENCH-BLINK-1",
        "domain": "broken-links",
        "question": "Which key format does the report export?",
        "product_context": "current release",
        "applicability": "current release",
        "expected_source_class": "OFFICIAL_PRODUCT_DOC",
        "known_decisive_sources": ["DOC-BLINK-EXPORT"],
        "acceptable_supporting_sources": [],
        "hard_negative_sources": ["DOC-BLINK-NEARBY"],
        "unanswerable": False,
        "request": {},
        "candidates": [
            _cand("DOC-BLINK-EXPORT", 1, {}),
            _cand("DOC-BLINK-NEARBY", 2, {}, applicability="NOT_ASSESSED"),
        ],
        "hard_negative_kinds": {"DOC-BLINK-NEARBY": "NEARBY_DOCUMENTATION"},
    },
    {
        "question_id": "BENCH-MAP-1",
        "domain": "map-console",
        "question": "Which baseline applies when publishing from the console?",
        "product_context": "current release",
        "applicability": "current release",
        "expected_source_class": "OFFICIAL_PRODUCT_DOC",
        "known_decisive_sources": ["DOC-MAP-BASELINE"],
        "acceptable_supporting_sources": [],
        "hard_negative_sources": ["DOC-MAP-SUPERSEDED"],
        "unanswerable": False,
        "request": {},
        "candidates": [
            _cand("DOC-MAP-SUPERSEDED", 1, {}, stale=True),
            _cand("DOC-MAP-BASELINE", 2, {}),
        ],
        "hard_negative_kinds": {"DOC-MAP-SUPERSEDED": "SUPERSEDED"},
    },
    {
        "question_id": "BENCH-DITAOT-1",
        "domain": "dita-ot",
        "question": "Which transtype does the legacy pipeline produce?",
        "product_context": "current release, legacy pipeline surface",
        "applicability": "legacy pipeline surface",
        "expected_source_class": "OFFICIAL_PRODUCT_DOC",
        "known_decisive_sources": ["DOC-DITAOT-TRANSTYPE"],
        "acceptable_supporting_sources": [],
        "hard_negative_sources": ["DOC-NPDF-TRANSTYPE"],
        "unanswerable": False,
        "request": {},
        "candidates": [
            _cand("DOC-DITAOT-TRANSTYPE", 1, {}),
            _cand("DOC-NPDF-TRANSTYPE", 2, {}, applicability="WRONG"),
        ],
        "hard_negative_kinds": {"DOC-NPDF-TRANSTYPE": "WRONG_SURFACE"},
    },
    {
        "question_id": "BENCH-PUB-1",
        "domain": "publishing",
        "question": "Is the output regenerated when only metadata changed?",
        "product_context": "current release",
        "applicability": "current release",
        "expected_source_class": "OFFICIAL_PRODUCT_DOC",
        "known_decisive_sources": ["DOC-PUB-REGEN"],
        "acceptable_supporting_sources": ["DOC-PUB-PARTIAL"],
        "hard_negative_sources": ["DOC-PUB-TOPIC"],
        "unanswerable": False,
        "request": {},
        "candidates": [
            _cand("DOC-PUB-REGEN", 1, {}),
            _cand("DOC-PUB-PARTIAL", 2, {}, applicability="UNCLEAR"),
            _cand("DOC-PUB-TOPIC", 3, {}, applicability="NOT_ASSESSED",
                  fetched=False),
        ],
        "hard_negative_kinds": {"DOC-PUB-TOPIC": "TOPIC_ONLY"},
    },
    {
        "question_id": "BENCH-DITA-1",
        "domain": "dita-semantics",
        "question": "Which element governs the navigation title fallback?",
        "product_context": "current release",
        "applicability": "current release, current spec version",
        "expected_source_class": "SPECIFICATION",
        "known_decisive_sources": ["SPEC-DITA-NAVTITLE"],
        "acceptable_supporting_sources": [],
        "hard_negative_sources": ["DOC-DITA-OLDREV"],
        "unanswerable": False,
        "request": {},
        "candidates": [
            _cand("SPEC-DITA-NAVTITLE", 1, {}, source_type="SPECIFICATION"),
            _cand("DOC-DITA-OLDREV", 2, {}, stale=True),
        ],
        "hard_negative_kinds": {"DOC-DITA-OLDREV": "SUPERSEDED"},
    },
    # Unanswerable questions: the corpus contains no decisive answer; the
    # expected outcome is NOT_FOUND/PARTIAL, never hallucinated decisiveness.
    {
        "question_id": "BENCH-UNANS-1",
        "domain": "output-history",
        "question": "What is the exact upper bound of the new retention "
                    "count?",
        "product_context": "current release",
        "applicability": "current release",
        "expected_source_class": "OFFICIAL_PRODUCT_DOC",
        "known_decisive_sources": [],
        "acceptable_supporting_sources": [],
        "hard_negative_sources": ["DOC-OH-NEARBY-PROP"],
        "unanswerable": True,
        "request": {"subject_key": "retention-count-bound"},
        "candidates": [
            _cand("DOC-OH-NEARBY-PROP", 1,
                  {"subject_key": "display-limit-property"}),
            _cand("DOC-OH-OVERVIEW-2", 2,
                  {"subject_key": "display-limit-property"}),
        ],
        "hard_negative_kinds": {"DOC-OH-NEARBY-PROP": "NEARBY_PROPERTY"},
    },
    {
        "question_id": "BENCH-UNANS-2",
        "domain": "translation",
        "question": "Does the service throttle concurrent review imports?",
        "product_context": "current release",
        "applicability": "current release",
        "expected_source_class": "OFFICIAL_PRODUCT_DOC",
        "known_decisive_sources": [],
        "acceptable_supporting_sources": [],
        "hard_negative_sources": ["FORUM-TRANSL-GUESS"],
        "unanswerable": True,
        "request": {},
        "candidates": [
            _cand("FORUM-TRANSL-GUESS", 1, {}, fetched=False,
                  applicability="NOT_ASSESSED",
                  source_type="OTHER_APPROVED_SOURCE"),
        ],
        "hard_negative_kinds": {"FORUM-TRANSL-GUESS": "TOPIC_ONLY"},
    },
]


def _request_for(item):
    req = {
        "request_id": f"REQ-{item['question_id']}",
        "question_id": item["question_id"],
        "research_id": f"RSH-{item['question_id']}",
        "query": item["question"],
        "required_source_type": item["expected_source_class"],
        "product_context": item["product_context"],
        "applicability": item["applicability"],
        "requested_claim": item["question"],
        "top_k": EVAL_K,
        "retrieval_mode": "OFFLINE_RETRIEVAL_EVAL",
        "budget": {"queries_per_question": 1,
                   "chunks_retrieved": len(item["candidates"]),
                   "chunks_fetched": sum(1 for c in item["candidates"]
                                         if c.get("fetched")),
                   "research_rounds": 1},
    }
    req.update(item.get("request") or {})
    return req


def _admit(candidate, request):
    """The admission decision under evaluation: the gate's ceiling."""

    return retrieval_admission.max_admissible_relationship(candidate, request)


def evaluate(benchmark=None):
    """Run the offline benchmark; return (metrics, problems)."""

    items = benchmark if benchmark is not None else BENCHMARK
    problems = []

    # The fixture manifest must itself satisfy the production gate.
    manifest = {
        "question_plan": {"items": [
            {"question_id": item["question_id"], "category": "EXPECTED_OUTCOME",
             "question": item["question"], "why_material": "benchmark",
             "triggering_evidence_ids": [], "acceptance_impact": "evaluation",
             "applicability": "APPLICABLE", "research_requirement": "NONE",
             "status": "RESOLVED"}
            for item in items
        ]},
        "retrieval_requests": {"items": [_request_for(item) for item in items]},
        "retrieval_results": {"items": []},
    }
    admitted = {}  # question_id -> [(candidate, relationship)]
    h1_items = []
    for item in items:
        request = _request_for(item)
        for cand in item["candidates"]:
            row = dict(cand)
            row["retrieval_result_id"] = (
                f"RR-{item['question_id']}-{cand['source_id']}")
            row["request_id"] = request["request_id"]
            row["question_id"] = item["question_id"]
            relationship = _admit(cand, request)
            row["relationship"] = relationship
            if relationship == "DECISIVE":
                row["supported_claim"] = row.get(
                    "supported_claim") or f"claim from {row['source_id']}"
                row["decisiveness"] = row.get(
                    "decisiveness") or "directly establishes the claim"
            manifest["retrieval_results"]["items"].append(row)
            admitted.setdefault(item["question_id"], []).append(
                (cand, relationship))
            if cand.get("is_historical"):
                # RAG-retrieved historical Jira still routes through H1.
                h1_items.append({
                    "history_id": f"H1-{cand['source_id']}",
                    "question_id": item["question_id"],
                    "jira_key_or_source_id": cand["source_id"],
                    "relationship": "SUPPORTING_PRECEDENT"
                    if cand["source_id"] in item["acceptable_supporting_sources"]
                    else "NOT_APPLICABLE",
                    "feature_match": "SAME", "surface_match": "SAME",
                    "version_match": "SAME", "configuration_match": "SAME",
                    "failure_mode_match": "SIMILAR",
                    "expected_behavior_match": "SIMILAR",
                    "currentness": "STALE",
                    "superseded_status": "NOT_SUPERSEDED",
                    "human_accepted_ac_available": False,
                    "applicability": item["applicability"],
                    "authority_role": "HISTORICAL_JIRA",
                    "allowed_use": "SUPPORT_ANSWER"
                    if cand["source_id"] in item["acceptable_supporting_sources"]
                    else "NONE",
                    "reason": "benchmark historical binding",
                    "limitations": ["Historical; not current authority."],
                })
    if h1_items:
        manifest["historical_jira_assessment"] = {"items": h1_items}

    problems.extend(retrieval_admission.validate(manifest))

    # ---- Retrieval metrics (what the ranked list surfaced) ------------------
    recall_hits = 0
    rr_sum = 0.0
    decisive_recall_hits = 0
    applicable_recall_hits = 0
    hard_negative_retrieved = 0
    answerable = 0
    for item in items:
        ranked = sorted(item["candidates"], key=lambda c: c["rank"])[:EVAL_K]
        top_ids = [c["source_id"] for c in ranked]
        decisive = item["known_decisive_sources"]
        if item["unanswerable"]:
            if any(s in top_ids for s in item["hard_negative_sources"]):
                hard_negative_retrieved += 1
            continue
        answerable += 1
        if any(s in top_ids for s in decisive):
            recall_hits += 1
        first = next((c["rank"] for c in ranked
                      if c["source_id"] in decisive), None)
        if first:
            rr_sum += 1.0 / first
        admitted_decisive = {
            c["source_id"]
            for c, rel in admitted[item["question_id"]]
            if rel in retrieval_admission.ESTABLISHING_RELATIONSHIPS
        }
        if any(s in admitted_decisive for s in decisive):
            decisive_recall_hits += 1
        acceptable = set(decisive) | set(item["acceptable_supporting_sources"])
        if any(c["source_id"] in acceptable
               and c.get("applicability") == "CONFIRMED" for c in ranked):
            applicable_recall_hits += 1
        if any(s in top_ids for s in item["hard_negative_sources"]):
            hard_negative_retrieved += 1

    # ---- Admission metrics (what the ceiling allowed) -----------------------
    wrong_version_admitted = wrong_version_total = 0
    wrong_surface_admitted = wrong_surface_total = 0
    topic_as_proof = 0
    fetched_compliant = fetched_total = 0
    decisive_admissions = 0
    decisive_misadmissions = 0
    unanswerable_false = 0
    unanswerable_total = 0
    for item in items:
        kinds = item.get("hard_negative_kinds", {})
        if item["unanswerable"]:
            unanswerable_total += 1
        for cand, relationship in admitted[item["question_id"]]:
            sid = cand["source_id"]
            kind = kinds.get(sid)
            establishing = (
                relationship in retrieval_admission.ESTABLISHING_RELATIONSHIPS)
            if kind == "WRONG_VERSION":
                wrong_version_total += 1
                if establishing:
                    wrong_version_admitted += 1
            if kind == "WRONG_SURFACE":
                wrong_surface_total += 1
                if establishing:
                    wrong_surface_admitted += 1
            if kind in ("TOPIC_ONLY", "NEARBY_PROPERTY", "NEARBY_DOCUMENTATION",
                        "SUPERSEDED", "HISTORICAL") and establishing:
                topic_as_proof += 1
            if establishing:
                fetched_total += 1
                if cand.get("fetched"):
                    fetched_compliant += 1
            if relationship == "DECISIVE":
                decisive_admissions += 1
                if sid not in item["known_decisive_sources"]:
                    decisive_misadmissions += 1
            if item["unanswerable"] and establishing:
                unanswerable_false += 1

    def rate(num, den):
        return round(num / den, 4) if den else 0.0

    metrics = {
        "retrieval": {
            "recall_at_k": rate(recall_hits, answerable),
            "mrr": round(rr_sum / answerable, 4) if answerable else 0.0,
            "decisive_evidence_recall_at_k": rate(decisive_recall_hits,
                                                  answerable),
            "applicable_evidence_recall_at_k": rate(applicable_recall_hits,
                                                    answerable),
            "hard_negative_retrieval_rate": rate(hard_negative_retrieved,
                                                 len(items)),
        },
        "admission": {
            "wrong_version_admission_rate": rate(wrong_version_admitted,
                                                 wrong_version_total),
            "wrong_surface_admission_rate": rate(wrong_surface_admitted,
                                                 wrong_surface_total),
            "topic_match_as_proof_rate": rate(
                topic_as_proof,
                sum(1 for item in items for c in item["candidates"])),
            "fetch_before_use_compliance": rate(fetched_compliant,
                                                fetched_total),
            "decisive_evidence_misadmission_rate": rate(
                decisive_misadmissions, decisive_admissions),
            "unanswerable_false_answer_rate": rate(unanswerable_false,
                                                   unanswerable_total),
        },
        "counts": {
            "questions": len(items),
            "answerable": answerable,
            "unanswerable": unanswerable_total,
            "candidates": sum(len(i["candidates"]) for i in items),
            "decisive_admissions": decisive_admissions,
        },
    }
    return metrics, problems


def live_smoke():
    """Read-only connectivity status of the existing gateway - never a
    semantic-quality proof, never a write/reindex."""

    try:
        import offline_retrieval
    except Exception:  # pragma: no cover - defensive
        return {"status": "SKIP", "reason": "gateway module unavailable"}
    status = offline_retrieval.retrieval_status()
    return {
        "status": "LIVE_READ_ONLY_RETRIEVAL_SMOKE",
        "note": "connectivity status only - not semantic-quality proof; no "
                "reindex, no corpus write, no provider changes",
        "gateway": status,
    }


def main():  # pragma: no cover - CLI helper
    live = "--live" in sys.argv
    metrics, problems = evaluate()
    print(json.dumps(metrics, indent=2, sort_keys=True))
    if live:
        print(json.dumps(live_smoke(), indent=2, sort_keys=True))
    else:
        print(json.dumps({"live_smoke": "NOT_RUN (pass --live for the "
                          "read-only connectivity status)"}))
    for problem in problems:
        print(f"FAIL: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
