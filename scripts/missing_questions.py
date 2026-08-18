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
    return problems


# --- discipline helpers (unit-testable) --------------------------------------

def requires_second_pass(questions):
    """A directed second pass is required iff a material (blocking) question exists."""
    return any(bool(getattr(q, "blocking", False)) for q in questions)


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


def check_retrieval_discipline(questions_data, evidence_data):
    """Cross-block discipline. Returns problem strings."""
    problems = []
    questions = [MissingQuestion.from_dict(x) for x in (questions_data or [])]
    items = [EvidenceItem.from_dict(x) for x in (evidence_data or [])]

    for q in questions:
        problems.extend(validate_question(q))
    for e in items:
        problems.extend(validate_evidence_item(e))

    # duplicate retrieval loop
    for key in find_duplicate_retrievals(items):
        problems.append(f"duplicate retrieval detected (query, source)={key} - prevent retrieval loops")

    # material question -> a genuinely new second-pass retrieval must exist
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

    # unresolved material questions must remain OPEN_QUESTION (already enforced per-question),
    # and must not silently claim resolution without a USED evidence item
    for q in questions:
        if q.blocking and not is_resolved(q.question_id, items):
            # not a failure by itself (it may legitimately stay unresolved), but it must be
            # routed to Open Questions - enforced by if_unresolved == OPEN_QUESTION above.
            pass

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
