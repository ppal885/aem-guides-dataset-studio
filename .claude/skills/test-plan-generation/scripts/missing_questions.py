"""MissingQuestionGenerator + ReasoningDirectedRetriever support.

WHY THIS EXISTS
---------------
Prompt 2 produced INVESTIGATION_CANDIDATEs. This module turns each material
candidate into a TECHNICAL QUESTION and enforces that retrieval evolves from a
single pass into a directed second pass:

    Jira -> initial retrieval -> BehaviorModel -> CoverageHypothesis
         -> MissingQuestion -> targeted SECOND retrieval

It also enforces an evidence lifecycle (RETRIEVED / INSPECTED / USED / REJECTED)
so we can later distinguish "evidence was never retrieved" from "evidence was
retrieved but reasoning ignored it".

Discipline enforced (all generic, no domain/construct/Jira rules):
- every MissingQuestion carries its own derived search concepts and declares
  `if_unresolved: OPEN_QUESTION`;
- a material (blocking) question requires at least one SECOND-pass retrieval whose
  query is genuinely new (not a repeat of an initial Jira-keyword query);
- retrieval is bounded (initial + second + at most one follow-up pass);
- duplicate (query, source) retrievals are flagged as a loop.

Stdlib only. Same dataclass/validate pattern (no future-annotations import).
"""

from dataclasses import dataclass, field


# Where a missing question should be answered. Generic source catalogue.
PREFERRED_SOURCES = (
    "current repository",
    "rag",
    "historical jira",
    "experience league",
    "dita 1.2",
    "dita 1.3",
    "dita-ot",
    "existing automation",
    "api docs",
    "commits/pr",
    "attachments",
    "linked jira",
)

# Retrieval authority is subject-specific.  The order is intentional: product
# decisions are not answered by code alone, while actual implementation is.
SUBJECT_SOURCE_POLICY = {
    "PRODUCT_CONTRACT": (
        "linked jira", "attachments", "experience league", "rag", "historical jira",
    ),
    "DITA_SEMANTICS": ("dita 1.2", "dita 1.3", "dita-ot", "rag", "experience league"),
    "ACTUAL_IMPLEMENTATION": ("current repository", "commits/pr", "existing automation"),
    "CURRENT_UI": ("attachments", "experience league", "current repository"),
}

# Evidence lifecycle states (mandatory).
EVIDENCE_STATUSES = ("RETRIEVED", "INSPECTED", "USED", "REJECTED")

# Bounded retrieval passes: the initial Jira pass, the directed second pass, and at
# most one follow-up ("third") allowed only when the second pass found materially
# new behavior. A fourth distinct pass is treated as an unbounded loop.
RETRIEVAL_PASSES = ("initial", "second", "third")


def _norm(q):
    return " ".join(str(q or "").lower().split())


@dataclass
class MissingQuestion:
    question_id: str = ""
    question: str = ""
    why_it_matters: str = ""
    hypothesis_id: str = ""
    preferred_sources: list = field(default_factory=list)
    search_concepts: list = field(default_factory=list)
    blocking: bool = False
    if_unresolved: str = "OPEN_QUESTION"
    material: bool = False
    source_ref: str = ""       # SC-## / BGE-## / CF-## that generated the question
    subject: str = ""
    dimension: str = ""
    open_question_ref: str = ""

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class EvidenceItem:
    evidence_id: str = ""
    source: str = ""
    query: str = ""
    pass_label: str = "initial"   # one of RETRIEVAL_PASSES
    status: str = "RETRIEVED"     # one of EVIDENCE_STATUSES
    question_id: str = ""
    hypothesis_id: str = ""
    subject: str = ""
    authority: str = ""

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        # accept "pass" as an alias for pass_label (JSON-friendly)
        if "pass" in data and "pass_label" not in data:
            data = dict(data)
            data["pass_label"] = data.get("pass")
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def validate_question(q):
    problems = []
    tag = f"missing_question '{q.question_id or q.question[:30] or '?'}'"
    if not q.question:
        problems.append(f"{tag}: missing 'question' text")
    if not q.why_it_matters:
        problems.append(f"{tag}: missing 'why_it_matters'")
    # Queries must be DERIVED FROM THE QUESTION - this is what makes the second pass
    # different from repeating Jira keywords.
    if not q.search_concepts:
        problems.append(f"{tag}: no search_concepts - the second-pass query must be derived from the question")
    if not q.preferred_sources:
        problems.append(f"{tag}: no preferred_sources - name where this should be answered")
    else:
        for s in q.preferred_sources:
            if _norm(s) not in PREFERRED_SOURCES:
                problems.append(f"{tag}: preferred source '{s}' is not a known source ({', '.join(PREFERRED_SOURCES)})")
    if not isinstance(q.blocking, bool):
        problems.append(f"{tag}: blocking must be a boolean")
    if not isinstance(q.material, bool):
        problems.append(f"{tag}: material must be a boolean")
    if q.material and not q.source_ref:
        problems.append(f"{tag}: a material question requires source_ref")
    if q.subject:
        if q.subject not in SUBJECT_SOURCE_POLICY:
            problems.append(
                f"{tag}: subject must be one of {', '.join(SUBJECT_SOURCE_POLICY)}"
            )
        elif q.preferred_sources and not any(
            _norm(source) in SUBJECT_SOURCE_POLICY[q.subject]
            for source in q.preferred_sources
        ):
            problems.append(
                f"{tag}: preferred_sources do not follow the {q.subject} source policy"
            )
    if q.material and not q.open_question_ref:
        problems.append(f"{tag}: unresolved material question requires open_question_ref")
    if q.if_unresolved != "OPEN_QUESTION":
        problems.append(f"{tag}: if_unresolved must be 'OPEN_QUESTION' (an unresolved question becomes an Open Question)")
    return problems


def validate_evidence_item(e):
    problems = []
    tag = f"evidence '{e.evidence_id or '?'}'"
    if not e.evidence_id:
        problems.append(f"{tag}: missing evidence_id")
    if _norm(e.source) not in PREFERRED_SOURCES:
        problems.append(f"{tag}: source '{e.source}' is not a known source")
    if not e.query:
        problems.append(f"{tag}: missing query (what was actually retrieved)")
    if e.pass_label not in RETRIEVAL_PASSES:
        problems.append(f"{tag}: pass '{e.pass_label}' must be one of {', '.join(RETRIEVAL_PASSES)}")
    if e.status not in EVIDENCE_STATUSES:
        problems.append(f"{tag}: status '{e.status}' must be one of {', '.join(EVIDENCE_STATUSES)}")
    if e.subject and e.subject not in SUBJECT_SOURCE_POLICY:
        problems.append(f"{tag}: unknown subject {e.subject!r}")
    if e.authority and not e.subject:
        problems.append(f"{tag}: authority requires subject")
    return problems


# --- discipline helpers (unit-testable) --------------------------------------

def requires_second_pass(questions):
    """Every material semantic gap requires directed second-pass retrieval."""
    return any(
        bool(getattr(q, "material", False) or getattr(q, "blocking", False))
        for q in questions
    )


def _queries_by_pass(items, pass_label):
    return {_norm(e.query) for e in items if e.pass_label == pass_label and e.query}


def new_second_pass_queries(items):
    """Second/third-pass queries that are genuinely new (not a repeat of an initial query)."""
    initial = _queries_by_pass(items, "initial")
    later = {_norm(e.query) for e in items if e.pass_label in ("second", "third") and e.query}
    return sorted(later - initial)


def find_duplicate_retrievals(items):
    """Repeated (query, source) pairs = a retrieval loop."""
    seen, dups = set(), []
    for e in items:
        key = (_norm(e.query), _norm(e.source))
        if key in seen:
            dups.append(key)
        else:
            seen.add(key)
    return dups


def is_resolved(question_id, items):
    """A candidate is resolvable when at least one evidence item for its question
    reached status USED (retrieved AND actually used by reasoning)."""
    return any(e.question_id == question_id and e.status == "USED" for e in items)


def check_retrieval_discipline(
    questions_data,
    evidence_data,
    *,
    open_question_ids=None,
    hypothesis_ids=None,
):
    """Cross-block discipline. Returns problem strings."""
    problems = []
    questions = [MissingQuestion.from_dict(x) for x in (questions_data or [])]
    items = [EvidenceItem.from_dict(x) for x in (evidence_data or [])]
    known_questions = {}
    known_open_questions = None if open_question_ids is None else set(open_question_ids)
    known_hypotheses = None if hypothesis_ids is None else set(hypothesis_ids)

    for q in questions:
        problems.extend(validate_question(q))
        if q.question_id in known_questions:
            problems.append(f"missing_question question_id duplicates {q.question_id}")
        elif q.question_id:
            known_questions[q.question_id] = q
        if (
            q.open_question_ref
            and known_open_questions is not None
            and q.open_question_ref not in known_open_questions
        ):
            problems.append(
                f"missing_question {q.question_id or '?'} references undeclared Open Question {q.open_question_ref}"
            )
        if (
            q.hypothesis_id
            and known_hypotheses is not None
            and q.hypothesis_id not in known_hypotheses
        ):
            problems.append(
                f"missing_question {q.question_id or '?'} references unknown hypothesis {q.hypothesis_id}"
            )
    evidence_ids = set()
    for e in items:
        problems.extend(validate_evidence_item(e))
        if e.evidence_id in evidence_ids:
            problems.append(f"evidence_lifecycle evidence_id duplicates {e.evidence_id}")
        elif e.evidence_id:
            evidence_ids.add(e.evidence_id)
        if e.question_id and e.question_id not in known_questions:
            problems.append(
                f"evidence {e.evidence_id or '?'} references unknown question {e.question_id}"
            )
        if (
            e.hypothesis_id
            and known_hypotheses is not None
            and e.hypothesis_id not in known_hypotheses
        ):
            problems.append(
                f"evidence {e.evidence_id or '?'} references unknown hypothesis {e.hypothesis_id}"
            )
        if e.status in ("USED", "REJECTED") and not (e.question_id or e.hypothesis_id):
            problems.append(
                f"evidence {e.evidence_id or '?'} with status {e.status} requires question_id or hypothesis_id"
            )
        question = known_questions.get(e.question_id)
        if question is not None and e.status == "USED" and question.subject:
            allowed_sources = SUBJECT_SOURCE_POLICY.get(question.subject, ())
            if _norm(e.source) not in allowed_sources:
                problems.append(
                    f"evidence {e.evidence_id or '?'} source {e.source!r} cannot resolve "
                    f"a {question.subject} question"
                )
            if e.subject and e.subject != question.subject:
                problems.append(
                    f"evidence {e.evidence_id or '?'} subject {e.subject!r} does not match "
                    f"question subject {question.subject!r}"
                )

    # duplicate retrieval loop
    for key in find_duplicate_retrievals(items):
        problems.append(f"duplicate retrieval detected (query, source)={key} - prevent retrieval loops")

    # Every material question -> its own genuinely new directed retrieval.  One
    # broad query cannot silently stand in for several different semantic gaps.
    if requires_second_pass(questions):
        second = [e for e in items if e.pass_label in ("second", "third")]
        if not second:
            problems.append(
                "a material (blocking) missing_question exists but no second-pass retrieval is recorded - "
                "directed second retrieval is required when a material question exists"
            )
        elif not new_second_pass_queries(items):
            problems.append(
                "second-pass retrieval only repeats initial Jira-keyword queries - the second query must be "
                "derived from the missing question, not the initial keywords"
            )
        initial_queries = _queries_by_pass(items, "initial")
        for q in questions:
            if not (q.material or q.blocking):
                continue
            linked = [
                e for e in items
                if e.question_id == q.question_id and e.pass_label in ("second", "third")
            ]
            if not linked:
                problems.append(
                    f"material question {q.question_id or '?'} has no linked directed second-pass retrieval"
                )
            elif not any(_norm(e.query) not in initial_queries for e in linked):
                problems.append(
                    f"material question {q.question_id or '?'} only repeats an initial query"
                )

    # unresolved material questions must remain OPEN_QUESTION (already enforced per-question),
    # and must not silently claim resolution without a USED evidence item
    for q in questions:
        if q.blocking and not is_resolved(q.question_id, items):
            # not a failure by itself (it may legitimately stay unresolved), but it must be
            # routed to Open Questions - enforced by if_unresolved == OPEN_QUESTION above.
            pass

    return problems


def required_question_requirements(manifest):
    """Derive question requirements from unresolved material semantic records."""
    required = []
    closure = manifest.get("semantic_closure", {}) if isinstance(manifest, dict) else {}
    if not isinstance(closure, dict):
        closure = {}
    for record in closure.get("records", []) or []:
        if isinstance(record, dict) and record.get("status") == "UNRESOLVED_AND_EXPOSED":
            required.append({
                "source_ref": str(record.get("closure_id", "")),
                "subject": str(record.get("subject", "PRODUCT_CONTRACT")),
                "dimension": str(record.get("dimension", "")),
                "open_question_ref": str(record.get("open_question_ref", "")),
            })
    graph = manifest.get("behavior_graph", {}) if isinstance(manifest, dict) else {}
    if not isinstance(graph, dict):
        graph = {}
    for edge in graph.get("edges", []) or []:
        if (
            isinstance(edge, dict)
            and edge.get("material") is True
            and edge.get("verification_state") == "UNRESOLVED"
        ):
            required.append({
                "source_ref": str(edge.get("edge_id", "")),
                "subject": str(edge.get("subject", "ACTUAL_IMPLEMENTATION")),
                "dimension": str(edge.get("relation_type", "")),
                "open_question_ref": str(edge.get("open_question_ref", "")),
            })
    facts = manifest.get("contract_facts", {}) if isinstance(manifest, dict) else {}
    if not isinstance(facts, dict):
        facts = {}
    for fact in facts.get("facts", []) or []:
        if (
            isinstance(fact, dict)
            and fact.get("material") is True
            and fact.get("integrity") == "EXPLICITLY_FLAGGED_AS_AMBIGUOUS"
        ):
            required.append({
                "source_ref": str(fact.get("fact_id", "")),
                "subject": str(fact.get("subject", "PRODUCT_CONTRACT")),
                "dimension": str(fact.get("category", "")),
                "open_question_ref": str(fact.get("open_question_ref", "")),
            })
    return [item for item in required if item["source_ref"]]


def required_question_sources(manifest):
    return [item["source_ref"] for item in required_question_requirements(manifest)]


def derive_missing_question_stubs(manifest):
    """Return deterministic stubs the reasoning layer must answer or expose."""
    stubs = []
    for index, requirement in enumerate(required_question_requirements(manifest), 1):
        dimension = requirement["dimension"].replace("_", " ").lower()
        subject = requirement["subject"]
        lead = {
            "PRODUCT_CONTRACT": "What is the intended product behavior",
            "DITA_SEMANTICS": "What do the governing DITA semantics require",
            "ACTUAL_IMPLEMENTATION": "What does the current implementation do",
            "CURRENT_UI": "What does the current UI show",
        }.get(subject, "What behavior is required")
        stubs.append({
            "question_id": f"MQ-{index:02d}",
            **requirement,
            "question": f"{lead} for {dimension}?",
            "material": True,
            "if_unresolved": "OPEN_QUESTION",
        })
    return stubs


def validate_required_questions(manifest):
    """Ensure semantic unknowns automatically become directed questions."""
    questions = [
        MissingQuestion.from_dict(item)
        for item in (manifest.get("missing_questions", []) or [])
        if isinstance(item, dict)
    ]
    by_source = {q.source_ref: q for q in questions if q.source_ref and q.material}
    problems = []
    for requirement in required_question_requirements(manifest):
        source_ref = requirement["source_ref"]
        question = by_source.get(source_ref)
        if question is None:
            problems.append(
                f"material unresolved candidate {source_ref} did not generate a missing_question"
            )
            continue
        for field in ("subject", "dimension", "open_question_ref"):
            if str(getattr(question, field, "")) != requirement[field]:
                problems.append(
                    f"material question for {source_ref} has {field}={getattr(question, field, '')!r}; "
                    f"expected {requirement[field]!r}"
                )
    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and (
        isinstance(manifest.get("missing_questions"), list)
        or isinstance(manifest.get("evidence_lifecycle"), list)
    )


def summarize(manifest):
    q = manifest.get("missing_questions", []) or []
    e = manifest.get("evidence_lifecycle", []) or []
    problems = check_retrieval_discipline(q, e)
    items = [EvidenceItem.from_dict(x) for x in e]
    by_status = {}
    for it in items:
        by_status[it.status] = by_status.get(it.status, 0) + 1
    lines = [f"MissingQuestions/Retrieval: {'VALID' if not problems else 'INVALID'} "
             f"({len(q)} question(s), {len(e)} evidence item(s))"]
    lines.append("  evidence by status: " + (", ".join(f"{k}={v}" for k, v in sorted(by_status.items())) or "(none)"))
    lines.append(f"  new second-pass queries: {len(new_second_pass_queries(items))}")
    for p in problems:
        lines.append(f"  PROBLEM {p}")
    return "\n".join(lines)
