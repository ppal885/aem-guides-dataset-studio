"""Question-level RAG retrieval quality and evidence admission (RAG-Q1).

WHY THIS EXISTS
---------------
Retrieval is not evidence.  A document mentioning the same feature is not
automatically an answer to a material Question, a search snippet is not
fetched source evidence, a fetched source is not automatically decisive, and
a decisive source is not automatically authoritative.  This module extends
the existing retrieval path (``offline_retrieval.py``'s read-only fail-open
gateway, ``relevance_prioritizer.py``'s behavioural ranking, the R1 Doc
Researcher, and the H1 historical-Jira assessment) with question-bound
retrieval and per-candidate admission assessment.  It does NOT build another
RAG system, replace the vector store, re-index, or change source authority.

Manifest blocks (both optional, backward-compatible):

``retrieval_requests.items[]`` - every retrieval request binds to:

    request_id, question_id, research_id, query (the ACTUAL query used),
    required_source_type, product_context, applicability, requested_claim,
    top_k (bounded), retrieval_mode (PRODUCTION / OFFLINE_RETRIEVAL_EVAL /
    LIVE_READ_ONLY_RETRIEVAL_SMOKE), optional rewritten_query (the Question
    binding fields never change under rewriting), optional budget
    (queries_per_question, chunks_retrieved, chunks_fetched, research_rounds).

``retrieval_results.items[]`` - every retrieved candidate records:

    retrieval_result_id, request_id, question_id, source_id, chunk_id, rank,
    retrieval_score (discovery metadata, never authority), source_type,
    source_version/currentness, applicability (CONFIRMED / UNCLEAR / WRONG /
    NOT_ASSESSED), relationship, supported_claim, decisiveness,
    limitations[], fetched (exact evidence fetched via the authorized
    read-only interface before material use), optional fetched_evidence_id,
    subject_key (exact configuration/property identity), question_revision
    (staleness), is_historical (routes through H1).

Relationships (closed enum):

- TOPIC_MATCH - related terminology/functionality, does not materially answer
  the Question.  Discovery only; cannot make S1 SUFFICIENT.
- RELEVANT - materially concerns the Question's functionality but does not
  establish the requested claim; may refine research, identify terminology,
  or locate another source.  Alone cannot establish an acceptance answer.
- SUPPORTS_CLAIM - consistent with a material part of the answer; may be
  partial/indirect/missing applicability.  S1 determines final sufficiency.
- DECISIVE - directly establishes the requested claim for the applicable
  product context and Question, SUBJECT TO source authority.  Never
  automatically authoritative and never automatically SUFFICIENT.

Admission ceiling (``max_admissible_relationship``) - the structural maximum
a candidate may be admitted at, given the recorded facts:

- NOT_ASSESSED applicability           -> TOPIC_MATCH
- WRONG applicability                  -> TOPIC_MATCH (never SUPPORTS_CLAIM+)
- UNCLEAR applicability                -> SUPPORTS_CLAIM at best (never DECISIVE)
- not fetched                          -> RELEVANT at best (snippets are discovery)
- subject_key mismatch with the request -> TOPIC_MATCH (exact configuration
  identity is required before property-specific evidence is admitted)
- stale question/source revision       -> TOPIC_MATCH
- otherwise                            -> DECISIVE at most

Hard rules enforced by ``validate`` (all generic; structural only - the gate
proves admission safety, not semantic relevance):

- every request binds an existing question_id and records the actual query;
- every result binds an existing request for the same question;
- relationship is never above the admission ceiling (retrieval score never
  converts into authority);
- SUPPORTS_CLAIM/DECISIVE require fetched exact evidence (fetch before
  material use);
- DECISIVE requires CONFIRMED applicability, a non-empty supported_claim and
  decisiveness;
- historical Jira results (is_historical) require an H1 assessment for the
  same question+source before SUPPORTS_CLAIM/DECISIVE - retrieval never
  bypasses H1;
- S1: a SUFFICIENT question never rests on TOPIC_MATCH/RELEVANT evidence;
- L1: only fetched SUPPORTS_CLAIM/DECISIVE evidence reaches AC lineage /
  final Source lines; unused retrieved chunks stay auditable outside it.

Backward-compatible: absent both blocks -> clean pass.
Generic only.  Stdlib only.
"""
from __future__ import annotations

RELATIONSHIPS = ("TOPIC_MATCH", "RELEVANT", "SUPPORTS_CLAIM", "DECISIVE")
_REL_RANK = {r: i for i, r in enumerate(RELATIONSHIPS)}

RETRIEVAL_MODES = (
    "PRODUCTION",
    "OFFLINE_RETRIEVAL_EVAL",
    "LIVE_READ_ONLY_RETRIEVAL_SMOKE",
)

APPLICABILITY_STATES = ("CONFIRMED", "UNCLEAR", "WRONG", "NOT_ASSESSED")

#: Retrieval is bounded; top_k never grows indefinitely to force an answer.
MAX_TOP_K = 20

BUDGET_FIELDS = (
    "queries_per_question",
    "chunks_retrieved",
    "chunks_fetched",
    "research_rounds",
)

# Relationships whose evidence may contribute to sufficiency/coverage/lineage.
ESTABLISHING_RELATIONSHIPS = frozenset({"SUPPORTS_CLAIM", "DECISIVE"})


def is_present(manifest):
    return isinstance(manifest, dict) and (
        isinstance(manifest.get("retrieval_requests"), dict)
        or isinstance(manifest.get("retrieval_results"), dict)
    )


def _nonempty(value):
    return bool(value.strip()) if isinstance(value, str) else bool(value)


def max_admissible_relationship(result, request=None):
    """Return the structural admission ceiling for a candidate.

    The ceiling depends only on recorded structural facts (applicability
    state, fetch status, subject identity, staleness) - never on the
    retrieval score.
    """

    applicability = result.get("applicability")
    if applicability in (None, "NOT_ASSESSED"):
        return "TOPIC_MATCH"
    if applicability == "WRONG":
        return "TOPIC_MATCH"
    if not result.get("fetched"):
        return "RELEVANT"
    if request is not None:
        required_subject = request.get("subject_key")
        result_subject = result.get("subject_key")
        if required_subject and result_subject and required_subject != result_subject:
            return "TOPIC_MATCH"
        if required_subject and not result_subject:
            return "RELEVANT"
    if result.get("stale"):
        return "TOPIC_MATCH"
    if applicability == "UNCLEAR":
        return "SUPPORTS_CLAIM"
    return "DECISIVE"


def _chain_context(manifest):
    ctx = {"questions": {}, "sufficiency": {}, "ac_lineage": [],
           "h1": {}}
    plan = manifest.get("question_plan")
    if isinstance(plan, dict):
        for source in (plan.get("items"),
                       (plan.get("overflow") or {}).get("items")):
            if isinstance(source, list):
                for row in source:
                    if isinstance(row, dict) and row.get("question_id"):
                        ctx["questions"][row["question_id"]] = row
    sufficiency = manifest.get("evidence_sufficiency")
    if isinstance(sufficiency, dict):
        for row in sufficiency.get("question_assessments", []):
            if isinstance(row, dict):
                ref = row.get("question_ref") or row.get("question_id")
                if ref:
                    ctx["sufficiency"][ref] = row
    lineage = manifest.get("requirement_lineage")
    if isinstance(lineage, dict) and isinstance(lineage.get("ac_lineage"), list):
        ctx["ac_lineage"] = [
            row for row in lineage["ac_lineage"] if isinstance(row, dict)
        ]
    h1 = manifest.get("historical_jira_assessment")
    if isinstance(h1, dict):
        for row in h1.get("items", []):
            if isinstance(row, dict):
                key = (row.get("question_id"),
                       str(row.get("jira_key_or_source_id") or ""))
                ctx["h1"][key] = row
    return ctx


def validate(manifest):
    problems = []
    if not is_present(manifest):
        return problems

    ctx = _chain_context(manifest)
    requests = (manifest.get("retrieval_requests") or {}).get("items", [])
    results = (manifest.get("retrieval_results") or {}).get("items", [])
    if not isinstance(requests, list):
        return ["retrieval_requests.items must be a list"]
    if not isinstance(results, list):
        return ["retrieval_results.items must be a list"]

    # ---- Retrieval requests: question-bound --------------------------------
    request_by_id = {}
    seen_requests = set()
    for i, req in enumerate(requests):
        tag = f"retrieval_requests.items[{i}]"
        if not isinstance(req, dict):
            problems.append(f"{tag}: each retrieval request must be an object")
            continue
        request_id = req.get("request_id")
        if not _nonempty(request_id):
            problems.append(f"{tag}: missing request_id")
            continue
        if request_id in seen_requests:
            problems.append(f"{tag}: duplicate request_id '{request_id}'")
        seen_requests.add(request_id)
        request_by_id[request_id] = (tag, req)

        question_id = req.get("question_id")
        if not _nonempty(question_id):
            problems.append(f"{tag}: missing question_id - retrieval is "
                            "question-bound, never generic ticket-wide")
        elif ctx["questions"] and question_id not in ctx["questions"]:
            problems.append(
                f"{tag}: question_id '{question_id}' does not exist in the "
                "Question Plan"
            )
        if not _nonempty(req.get("research_id")):
            problems.append(f"{tag}: missing research_id - research binds to "
                            "retrieval")
        if not _nonempty(req.get("query")):
            problems.append(f"{tag}: missing query - record the actual query "
                            "used")
        if not _nonempty(req.get("requested_claim")):
            problems.append(f"{tag}: missing requested_claim - the claim the "
                            "Question seeks")
        for field in ("required_source_type", "product_context", "applicability"):
            if not _nonempty(req.get(field)):
                problems.append(f"{tag}: missing {field}")
        mode = req.get("retrieval_mode")
        if mode not in RETRIEVAL_MODES:
            problems.append(
                f"{tag}: retrieval_mode '{mode}' must be one of "
                f"{', '.join(RETRIEVAL_MODES)} - offline evaluation and live "
                "read-only smoke are reported separately"
            )
        top_k = req.get("top_k")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            problems.append(f"{tag}: top_k must be a positive integer")
        elif top_k > MAX_TOP_K:
            problems.append(
                f"{tag}: top_k {top_k} exceeds the retrieval budget "
                f"({MAX_TOP_K}) - no answer is a valid result; do not "
                "increase top_k to force one"
            )
        budget = req.get("budget")
        if budget is not None:
            if not isinstance(budget, dict):
                problems.append(f"{tag}: budget must be an object")
            else:
                for field in BUDGET_FIELDS:
                    value = budget.get(field)
                    if value is not None and (
                        not isinstance(value, int) or isinstance(value, bool)
                        or value < 0
                    ):
                        problems.append(
                            f"{tag}: budget.{field} must be a non-negative "
                            "integer"
                        )
        # Query rewriting never changes the Question's binding/meaning.
        if req.get("rewritten_query") is not None and not _nonempty(
            req.get("rewritten_query")
        ):
            problems.append(f"{tag}: rewritten_query must be non-empty when "
                            "recorded")

    # ---- Retrieval results: per-candidate admission -------------------------
    seen_results = set()
    result_rows = []
    for i, row in enumerate(results):
        tag = f"retrieval_results.items[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{tag}: each retrieval result must be an object")
            continue
        result_id = row.get("retrieval_result_id")
        if not _nonempty(result_id):
            problems.append(f"{tag}: missing retrieval_result_id")
            continue
        if result_id in seen_results:
            problems.append(f"{tag}: duplicate retrieval_result_id "
                            f"'{result_id}'")
        seen_results.add(result_id)

        request_id = row.get("request_id")
        request = None
        if not _nonempty(request_id):
            problems.append(f"{tag}: missing request_id - every candidate "
                            "binds to its retrieval request")
        elif request_id not in request_by_id:
            problems.append(f"{tag}: request_id '{request_id}' does not exist")
        else:
            request = request_by_id[request_id][1]

        question_id = row.get("question_id")
        if not _nonempty(question_id):
            problems.append(f"{tag}: missing question_id")
        elif request is not None and question_id != request.get("question_id"):
            problems.append(
                f"{tag}: question_id '{question_id}' does not match the bound "
                f"request's question '{request.get('question_id')}'"
            )

        for field in ("source_id", "chunk_id", "source_type"):
            if not _nonempty(row.get(field)):
                problems.append(f"{tag}: missing {field}")
        rank = row.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            problems.append(f"{tag}: rank must be a positive integer")
        score = row.get("retrieval_score")
        if score is not None and (
            not isinstance(score, (int, float)) or isinstance(score, bool)
        ):
            problems.append(f"{tag}: retrieval_score must be numeric when "
                            "present - and is discovery metadata, never "
                            "authority")
        applicability = row.get("applicability")
        if applicability not in APPLICABILITY_STATES:
            problems.append(
                f"{tag}: applicability '{applicability}' must be one of "
                f"{', '.join(APPLICABILITY_STATES)} - assess applicability "
                "before admitting evidence"
            )
        relationship = row.get("relationship")
        if relationship not in RELATIONSHIPS:
            problems.append(
                f"{tag}: relationship '{relationship}' must be one of "
                f"{', '.join(RELATIONSHIPS)}"
            )
            continue
        if not isinstance(row.get("limitations"), list):
            problems.append(f"{tag}: limitations must be a list")

        ceiling = max_admissible_relationship(row, request)
        result_rows.append((tag, row, request, relationship, ceiling))

        if _REL_RANK[relationship] > _REL_RANK[ceiling]:
            why = {
                "TOPIC_MATCH": "applicability is unassessed/wrong, the subject "
                "identity differs, or the retrieval is stale",
                "RELEVANT": "the exact evidence was not fetched - a search "
                "snippet is discovery, not source evidence",
                "SUPPORTS_CLAIM": "applicability is UNCLEAR and cannot be "
                "treated as confirmed",
            }.get(ceiling, "")
            problems.append(
                f"{tag}: relationship '{relationship}' exceeds the admission "
                f"ceiling '{ceiling}' ({why})"
            )

        if relationship in ESTABLISHING_RELATIONSHIPS:
            if not row.get("fetched"):
                problems.append(
                    f"{tag}: fetch before material use - '{relationship}' "
                    "requires the exact evidence/chunk fetched through the "
                    "authorized read-only interface"
                )
        if relationship == "DECISIVE":
            if applicability != "CONFIRMED":
                problems.append(
                    f"{tag}: DECISIVE requires CONFIRMED applicability for "
                    "the current product context"
                )
            if not _nonempty(row.get("supported_claim")):
                problems.append(
                    f"{tag}: DECISIVE requires supported_claim - the exact "
                    "claim the fetched source establishes"
                )
            if not _nonempty(row.get("decisiveness")):
                problems.append(
                    f"{tag}: DECISIVE requires a decisiveness statement - "
                    "decisive is not automatically authoritative"
                )

        # Historical Jira retrieved via RAG still routes through H1.
        if row.get("is_historical") and relationship in ESTABLISHING_RELATIONSHIPS:
            key = (question_id, str(row.get("source_id") or ""))
            if key not in ctx["h1"]:
                problems.append(
                    f"{tag}: retrieved historical Jira requires an H1 "
                    "assessment for the same question+source before "
                    f"'{relationship}' - retrieval never bypasses H1"
                )

    # ---- S1 integration -----------------------------------------------------
    for tag, row, request, relationship, ceiling in result_rows:
        question_id = row.get("question_id")
        assessment = ctx["sufficiency"].get(question_id)
        if assessment is None:
            continue
        status = (assessment.get("sufficiency_status")
                  or assessment.get("sufficiency"))
        evidence_ids = {str(v) for v in assessment.get("evidence_ids", [])}
        cited = {str(row.get("chunk_id")), str(row.get("source_id"))} & evidence_ids
        if cited and status == "SUFFICIENT" and relationship not in ESTABLISHING_RELATIONSHIPS:
            problems.append(
                f"{tag}: {relationship} evidence cannot make "
                f"'{question_id}' SUFFICIENT - a topic match is not an answer"
            )

    # ---- L1 integration -----------------------------------------------------
    for tag, row, request, relationship, ceiling in result_rows:
        identifiers = {str(row.get("chunk_id")), str(row.get("source_id"))}
        for lineage in ctx["ac_lineage"]:
            refs = {str(v) for v in lineage.get("evidence_refs", [])}
            if identifiers & refs and not (
                row.get("fetched") and relationship in ESTABLISHING_RELATIONSHIPS
            ):
                problems.append(
                    f"{tag}: unused/unfetched retrieval never enters AC "
                    f"lineage or final Source lines ('{lineage.get('ac_id')}')"
                )

    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "retrieval admission: NOT PRESENT (clean pass)"
    requests = (manifest.get("retrieval_requests") or {}).get("items", []) or []
    results = (manifest.get("retrieval_results") or {}).get("items", []) or []
    by_rel = {}
    for row in results:
        if isinstance(row, dict):
            rel = row.get("relationship", "?")
            by_rel[rel] = by_rel.get(rel, 0) + 1
    parts = ", ".join(f"{k}={v}" for k, v in sorted(by_rel.items())) or "none"
    return (f"retrieval admission: {len(requests)} request(s), "
            f"{len(results)} candidate(s) ({parts})")


def main():  # pragma: no cover - CLI helper
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: retrieval_admission.py MANIFEST.json")
        return 2
    manifest = json.load(open(sys.argv[1], encoding="utf-8"))
    problems = validate(manifest)
    print(summarize(manifest))
    for problem in problems:
        print(f"FAIL: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
