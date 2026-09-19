"""Deterministic, stage-owned reasoning for the canonical Test Plan runtime.

The service contains no entry-point routing and no arbitrary generation hook.
It converts normalized evidence into typed intermediate records.  The runtime
calls these methods in the one fixed order declared by ``CANONICAL_STAGE_ORDER``.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping

from app.core.schemas_canonical_test_plan_runtime import (
    AcceptanceCandidate,
    AcceptanceResolutionBatch,
    AcceptancePromotionDecision,
    AcceptanceSubPoint,
    AcceptanceSubPointKind,
    AbstractSignal,
    AbstractSignalKind,
    ApplicabilityState,
    AuthorityClass,
    AuthoritySubject,
    BehaviorGraph,
    BehaviorGraphEdge,
    BehaviorGraphNode,
    BehaviorChangeClass,
    BehaviorClassificationRecord,
    BehaviorHypothesis,
    BehaviorRelationType,
    BehavioralCoverageCandidate,
    BehavioralCoverageExpansion,
    SemanticDependencyKind,
    SemanticDependencyRecord,
    SemanticDependencySlot,
    CanonicalBehaviorModel,
    CanonicalEvidenceBundle,
    CandidateDedupDecision,
    CandidateLifecycleRecord,
    CandidateLifecycleStage,
    CandidateTerminalDisposition,
    ChangeSurface,
    ChangeSurfaceKind,
    ClaimSufficiencyRecord,
    ClarificationAnswerClass,
    ClarificationStatus,
    ClosureDimensionResult,
    ClosureDisposition,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    ContractPreservationState,
    CoverageDisposition,
    CoverageDispositionRecord,
    CoverageExpansionAxis,
    CoverageExpansionDisposition,
    CoverageExpansionTrigger,
    CurrentnessState,
    DirectedRetrievalRecord,
    DitaOtProcessingState,
    DomainActivation,
    DomainImpact,
    EvidenceLifecycleStatus,
    EvidenceRecord,
    EvidenceSourceType,
    FamilyActivationDecision,
    GateDecision,
    GateStatus,
    GeneratedOutputOracle,
    GenerationRequest,
    GitHubImplementationVerificationHandoff,
    HumanClarification,
    HypothesisState,
    InvestigationMateriality,
    IssueDomain,
    InvestigationFamilySatisfactionStatus,
    LifecycleOperation,
    MandatoryInvestigationFamily,
    MissingQuestion,
    MissingQuestionQualityReport,
    OpenQuestionClass,
    PatternLookupRuntimeStatus,
    PlanSection,
    PromotionStatus,
    PublishingTransformationStage,
    QeInvestigationPreparation,
    QuestionGenerationDiagnosticTrace,
    QuestionGenerationFailureReason,
    QuestionGenerationStepOutcome,
    QuestionGenerationTraceStep,
    QuestionGenerationTraceStage,
    QuestionResearchRecord,
    ReasoningPatternActivation,
    ReasoningQuestionFamily,
    RendererProjectionDecision,
    ResearchFindingEvidenceRole,
    ResearchRequirement,
    ResearchRequirementRecord,
    ResearchStatus,
    ResearchWorkerStatus,
    CanonicalRuntimeStage,
    RetrievalStatus,
    ScopeResolution,
    SemanticDimension,
    StructuredQEPlan,
    WrittenAcceptanceCriterion,
    SufficiencyStatus,
    VerificationState,
    stable_sha256,
)
from app.services.canonical_evidence_service import record_visible_to
from app.services.question_research_routing_service import (
    DOCUMENTATION_RESEARCH_SOURCES,
    JIRA_AUTHORITY_RESEARCH_SOURCES,
    QUESTION_RESEARCH_ROUTER,
)
from app.services.reasoning_evidence_provider import (
    AuthorizedSemanticEvidence,
    QuestionEvidenceStance,
)
from app.services.github_implementation_verification import (
    is_github_implementation_result_record,
)


_ACCEPTED_AUTHORITIES = {
    AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
    AuthorityClass.CONFIRMED_PRODUCT_DECISION,
}
_CONTRACT_AUTHORITIES = _ACCEPTED_AUTHORITIES | {
    AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    AuthorityClass.CUSTOMER_REQUEST,
}
_HUMAN_CONTRACT_SOURCES = {
    EvidenceSourceType.ACCEPTED_UAC,
    EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
    EvidenceSourceType.PRODUCT_DECISION,
}
_IMPLEMENTATION_SOURCES = {
    EvidenceSourceType.CURRENT_CODE,
    EvidenceSourceType.CURRENT_PR,
    EvidenceSourceType.IMPLEMENTATION_DIFF,
    EvidenceSourceType.CODE_DIFF,
    EvidenceSourceType.EXISTING_AUTOMATION,
}
_UI_SOURCES = {
    EvidenceSourceType.UI_OBSERVATION,
    EvidenceSourceType.OBSERVED_UI_FLOW,
    EvidenceSourceType.SCREENSHOT_REPRODUCTION,
}
_CURRENT_ISSUE_BEHAVIOR_SOURCES = {
    EvidenceSourceType.CURRENT_JIRA,
    EvidenceSourceType.JIRA_DESCRIPTION,
    EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
    EvidenceSourceType.CUSTOMER_REQUEST,
    EvidenceSourceType.CUSTOMER_WORKFLOW,
    EvidenceSourceType.BENCHMARK_PUBLIC_INPUT,
}
_SEMANTIC_HANDOFF_AUTHORITIES = {
    AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    AuthorityClass.SPECIFICATION_AUTHORITY,
    AuthorityClass.IMPLEMENTATION_CONFIRMED,
}

# Mandatory research routing lives in the reusable per-question contract
# (``app.services.question_research_routing_service``); the ticket-level batch
# methods below delegate to it one question at a time.

# Research states that leave the question without a terminal answer; coverage
# must keep such a question open instead of finalizing it.
_INCOMPLETE_RESEARCH_STATUSES = {
    ResearchStatus.PENDING,
    ResearchStatus.PARTIAL,
    ResearchStatus.NOT_FOUND,
    ResearchStatus.SOURCE_UNAVAILABLE,
    ResearchStatus.CONFLICTED,
}

# Existing-vs-New behavior classification.  Existing-behavior evidence
# (official documentation, current UI observation, current code and automation)
# establishes the documented baseline; the current Jira authority carries the
# requested behavior; the change set (PR/diff) carries what is being
# implemented now and is never historical documented behavior.
_EXISTING_BEHAVIOR_SOURCES = DOCUMENTATION_RESEARCH_SOURCES | {
    EvidenceSourceType.CURRENT_CODE,
    EvidenceSourceType.EXISTING_AUTOMATION,
}
_CHANGE_SET_SOURCES = {
    EvidenceSourceType.CURRENT_PR,
    EvidenceSourceType.IMPLEMENTATION_DIFF,
    EvidenceSourceType.CODE_DIFF,
}
# Evidence bound to the change under test, as opposed to the retrieved corpus.
# Documentation and specification chunks describe the product in general, so
# sharing vocabulary with one establishes topic relevance only; such a
# dimension reaches its answer through mandated research rather than by being
# declared resolved.
_CHANGE_BOUND_SOURCES = (
    _CURRENT_ISSUE_BEHAVIOR_SOURCES
    | _HUMAN_CONTRACT_SOURCES
    | _IMPLEMENTATION_SOURCES
    | _UI_SOURCES
)

# Dispositions that do not assert a resolved behavior and are not classified.
_UNRESOLVED_BEHAVIOR_DISPOSITIONS = {
    CoverageDisposition.OPEN_QUESTION,
    CoverageDisposition.PRODUCT_SCOPE_QUESTION,
    CoverageDisposition.ENGINEERING_DESIGN_DECISION,
    CoverageDisposition.OUT_OF_SCOPE,
    CoverageDisposition.UNSUPPORTED_INFERENCE,
}

_PRESERVATION_RE = re.compile(
    r"\bbackward[- ]?compatib\w*\b|"
    r"\b(?:must|shall|should|will)\b[^.]{0,80}?\b(?:remain|remains|remaining|"
    r"stay|stays|continue|continues|continuing)\b[^.]{0,60}?"
    r"(?:compatible|unchanged|intact|available|valid|preserved|"
    r"compatible|the same)\b|"
    r"\b(?:remain|remains|stay|stays|continue|continues)\b[^.]{0,60}?"
    r"(?:compatible|unchanged|intact|preserved)\b",
    re.IGNORECASE,
)


def _mandatory_research_open_rationale(
    related_questions: list[MissingQuestion],
    research_by_question: dict[str, QuestionResearchRecord],
) -> str | None:
    """Hard gate: why coverage must keep a material question open.

    Returns ``None`` when every related question's mandatory research is
    complete (or not required).  Otherwise returns the reason the Coverage
    Reasoner rejects finalizing the question.
    """

    for question in sorted(related_questions, key=lambda row: row.question_id):
        record = research_by_question.get(question.question_id)
        if record is None:
            continue
        if record.research_requirement == ResearchRequirement.NONE:
            continue
        if record.research_status not in _INCOMPLETE_RESEARCH_STATUSES:
            continue
        requirement = record.research_requirement.value.lower().replace("_", " ")
        if record.research_status == ResearchStatus.PENDING:
            return (
                f"Mandatory {requirement} research was classified but never "
                "executed; coverage cannot finalize this material question from "
                "the current Jira/configuration evidence alone."
            )
        if record.research_status == ResearchStatus.NOT_FOUND:
            return (
                f"Mandatory {requirement} research executed and found no answer; "
                "absence of evidence is not treated as the opposite behavior, so "
                "the question remains open."
            )
        if record.research_status == ResearchStatus.SOURCE_UNAVAILABLE:
            return (
                f"Mandatory {requirement} research could not run because the "
                "required source was unavailable; the question remains open."
            )
        if record.research_status == ResearchStatus.CONFLICTED:
            return (
                f"Mandatory {requirement} research produced conflicting evidence; "
                "the question remains open for a Human decision."
            )
        return (
            f"Mandatory {requirement} research only partially answered the "
            "question; the mandated source has not fully resolved it."
        )
    return None


# P3: research statuses that prove the mandated research actually terminated
# (or was never required) - only these may yield an ACCEPTANCE_TBD.  PENDING
# means research never executed: fail closed, never a final TBD.
_TBD_EXHAUSTED_RESEARCH_STATUSES = {
    ResearchStatus.PARTIAL,
    ResearchStatus.NOT_FOUND,
    ResearchStatus.SOURCE_UNAVAILABLE,
    ResearchStatus.CONFLICTED,
    ResearchStatus.NOT_REQUIRED,
    ResearchStatus.NOT_APPLICABLE,
}


def _acceptance_tbd_eligible(
    question: MissingQuestion,
    research_by_question: dict[str, QuestionResearchRecord],
    clarified_question_ids: set[str],
    established_question_ids: set[str] | None = None,
) -> bool:
    """P3: a blocking acceptance-decision question whose mandated research is
    exhausted (or not required) and that no clarification answered becomes a
    bounded ACCEPTANCE_TBD instead of a generic open question.  The runtime
    never invents the missing value."""

    if question.question_id in clarified_question_ids:
        return False
    if not question.blocking:
        return False
    if question.open_question_class != OpenQuestionClass.USER_ACCEPTANCE_DECISION:
        return False
    record = research_by_question.get(question.question_id)
    if record is None:
        # No research classification at all is never "research exhausted".
        return False
    if record.research_status in _TBD_EXHAUSTED_RESEARCH_STATUSES:
        return True
    # Research that terminated with an answer but established no
    # customer-stated desired behavior leaves the product decision open.  That
    # is a bounded TBD, never a generic open question that carries no research
    # at all - otherwise the terminated research is silently dropped.  Any
    # documented existing behavior it did find is emitted separately as a
    # PROPOSED baseline; it informs the decision without making it.
    return (
        record.research_status == ResearchStatus.ANSWER_FOUND
        and question.question_id not in (established_question_ids or set())
    )


# Decision semantics: research that terminated with an answer may establish
# the acceptance-bearing core of a blocking question.  A customer-stated
# desired behavior resolves it and grounds a PROPOSED candidate; documented
# existing behavior grounds a PROPOSED baseline candidate without resolving
# it.  Either way only the residual acceptance-changing decision (carried by
# convergence) remains a bounded TBD.  Observed behavior never qualifies here
# - observation is not a requirement; a QE run records what happened, not
# what the product owes.
_DESIRED_ESTABLISHING_RESEARCH_STATUSES = {
    ResearchStatus.ANSWER_FOUND,
    ResearchStatus.PARTIAL,
}
_DESIRED_ESTABLISHING_WORKER_STATUSES = {
    ResearchWorkerStatus.ANSWER_FOUND,
    ResearchWorkerStatus.PARTIAL,
}


# Roles that may ground an acceptance candidate.  A customer-stated desire is
# the requirement and decides the question; documented existing behavior is
# the baseline the requirement preserves or changes, so it informs the
# question without deciding it.  Observed behavior, supporting context and
# implementation evidence never qualify: observation is not a requirement and
# code is not a contract.
_DESIRED_ROLES = frozenset({ResearchFindingEvidenceRole.DESIRED_BEHAVIOR})
_EXISTING_ROLES = frozenset({ResearchFindingEvidenceRole.EXISTING_BEHAVIOR})
# Code is not a contract, so implementation evidence stays out of the
# acceptance lane above.  It is still the only source that establishes what
# the product does today on the changed path - the baseline a tester must
# re-verify - so it grounds INVESTIGATION coverage instead of being dropped.
_IMPLEMENTATION_ROLES = frozenset(
    {ResearchFindingEvidenceRole.IMPLEMENTATION_EVIDENCE}
)


def _establishing_claims(
    question: MissingQuestion,
    research_by_question: dict[str, QuestionResearchRecord],
    worker_results: list,
    roles: frozenset,
) -> list[tuple[str, list[str]]]:
    """Claims carrying one of `roles` that admitted research established for
    this question, as (claim, source_refs) pairs."""

    record = research_by_question.get(question.question_id)
    if (
        record is None
        or record.research_status not in _DESIRED_ESTABLISHING_RESEARCH_STATUSES
    ):
        return []
    claims: list[tuple[str, list[str]]] = []
    for result in worker_results or []:
        if result.question_id != question.question_id:
            continue
        if (
            record.research_request_ids
            and result.research_id not in record.research_request_ids
        ):
            continue
        if result.status not in _DESIRED_ESTABLISHING_WORKER_STATUSES:
            continue
        for finding in result.findings:
            if finding.evidence_role not in roles:
                continue
            claim = str(finding.claim).strip()
            if claim:
                claims.append((claim, list(finding.source_refs or [])))
    return claims


def desired_behavior_claims(
    question: MissingQuestion,
    research_by_question: dict[str, QuestionResearchRecord],
    worker_results: list,
) -> list[tuple[str, list[str]]]:
    """Customer-stated desired-behavior claims established by admitted
    research for this question, as (claim, source_refs) pairs."""

    return _establishing_claims(
        question, research_by_question, worker_results, _DESIRED_ROLES
    )


def existing_behavior_claims(
    question: MissingQuestion,
    research_by_question: dict[str, QuestionResearchRecord],
    worker_results: list,
) -> list[tuple[str, list[str]]]:
    """Documented existing-behavior claims established by admitted research
    for this question, as (claim, source_refs) pairs.  Documentation records
    the product's current contract, so it grounds a PROPOSED candidate - the
    behavior-classification lane then tags it EXISTING_CONFIRMED, PRESERVED
    or MODIFIED from the cited evidence source types."""

    return _establishing_claims(
        question, research_by_question, worker_results, _EXISTING_ROLES
    )


def implementation_behavior_claims(
    question: MissingQuestion,
    research_by_question: dict[str, QuestionResearchRecord],
    worker_results: list,
) -> list[tuple[str, list[str]]]:
    """Implementation-evidence claims established by admitted code research
    for this question, as (claim, source_refs) pairs.

    These never reach the acceptance lane: inspected code proves what the
    product does, not what it owes.  They ground INVESTIGATION coverage so
    the current behavior on the changed path stays visible to the tester."""

    return _establishing_claims(
        question, research_by_question, worker_results, _IMPLEMENTATION_ROLES
    )


def research_resolved_question_ids(
    questions: list[MissingQuestion],
    research_records: list[QuestionResearchRecord] | None,
    worker_results: list,
) -> set[str]:
    """Blocking questions whose acceptance decision was answered by admitted
    research, i.e. a customer-stated desired behavior was established.  They
    stop blocking; any residual acceptance-changing decision still surfaces
    through convergence as a bounded TBD.

    Documented existing behavior deliberately does NOT resolve a question.
    Documentation records what the product does today, which is the baseline
    a ticket preserves or changes - it is not the customer's decision about
    what the product should do.  Treating it as a resolution would suppress
    the bounded TBD for exactly the questions documentation could not answer
    (for example a finding that states no ordering rule is documented).  It
    still grounds a PROPOSED baseline candidate through
    ``documented_baseline_claims``; the two roles are separate."""

    research_by_question = {
        row.question_id: row for row in research_records or []
    }
    return {
        question.question_id
        for question in questions or []
        if question.blocking
        and desired_behavior_claims(question, research_by_question, worker_results)
    }


# A leading attribution clause ending in a colon ("The slide text explicitly
# states the customer position:", "On the same slide the customer (X)
# states:") is the researcher's framing, not the desired behavior.
_DESIRED_WRAPPER_RE = re.compile(
    r"^[^.]{0,120}?\b(?:states|says|reads|notes)\b[^:]{0,40}:\s*",
    re.IGNORECASE,
)
# Researchers sometimes prefix findings with a role tag ("DESIRED: ...",
# "OBSERVED: ..."): it is framing, not content.
_ROLE_TAG_RE = re.compile(
    r"^\s*(?:DESIRED|OBSERVED|CONTEXT|NOTE|BACKGROUND)\s*[:.\-]\s*",
    re.IGNORECASE,
)
# Meta/evidence sentences are provenance, never the contract: they mention
# the evidence itself instead of product behavior.
_META_SENTENCE_RE = re.compile(
    r"\b(?:verbatim|matches the jira|customer-stated|recorded as|"
    r"not (?:a|an) product requirement|acceptance truth|"
    r"provenance and prioritization)\b",
    re.IGNORECASE,
)
# "The customer (X) states they want Y" / "the customer wants Y": Y is the
# requirement; the wanting frame is attribution.
_WANT_FLIP_RE = re.compile(
    r"\b(?:the\s+customer\s*(?:\([^)]*\))?|customer|they)\s+"
    r"(?:explicitly\s+)?(?:states?|says?|notes?)(?:\s+they)?\s*"
    r"wants?\s+(?:that\s+)?",
    re.IGNORECASE,
)
# "... states on the slide that authors need X" - the need-frame variant of
# the same attribution pattern.
_NEED_FLIP_RE = re.compile(
    r"\b(?:states?|says?|notes?)\b[^.:]{0,60}?\bthat\s+"
    r"(?:authors?|users?|they|we)\s+"
    r"(?:need|needs|want|wants|should\s+(?:get|see|have))\s+",
    re.IGNORECASE,
)
_MODAL_RE = re.compile(r"\b(?:must|shall|should|will)\b", re.IGNORECASE)
_PARTICIPLE_TAIL_RE = re.compile(
    r",\s*(restored|carried over|added|shown|provided|available|displayed|"
    r"surfaced|reinstated|aligned|present)\b",
    re.IGNORECASE,
)


# Documentation findings lead with the researcher's own framing ("Documentation
# establishes that ...", "Per the documentation, ...").  That framing is
# provenance, not product behavior, and the Reviewer rejects it outright
# (_AC_META_PROSE_RE matches "documentation establishes").  Strip it here so
# only the observable outcome survives; the Reviewer gate stays untouched.
_EXISTING_WRAPPER_RE = re.compile(
    r"^\s*(?:"
    r"(?:the\s+)?(?:product\s+|existing\s+|current\s+)?doc(?:s|umentation)\s+"
    r"(?:establishes?|states?|records?|confirms?|describes?|documents?|says?|"
    r"notes?|shows?|indicates?)(?:\s+that)?"
    r"|(?:per|according\s+to|as\s+per)\s+the\s+doc(?:s|umentation)"
    r"|documented\s+[^:.]{0,80}:"
    r"|existing[_\s-]*behaviou?r"
    r"|current[_\s-]*behaviou?r"
    r"|documented[_\s-]*behaviou?r"
    r")\s*[,:.\-]?\s*",
    re.IGNORECASE,
)

# A documentation finding often ends by stating what the documentation does
# NOT establish ("The documentation does not state any ordering rule", "names
# no default sort field").  That is the absence of a contract, never a
# contract: it belongs to the bounded TBD's reasoning, never to an AC.
_DOC_DISCLAIMER_RE = re.compile(
    r"\b(?:"
    r"do(?:es)?\s+not\s+(?:state|specify|define|establish|document|mention)"
    r"|nor\s+does\s+it\s+(?:state|specify|define)"
    r"|names?\s+no\b"
    r"|is\s+not\s+(?:stated|specified|documented|established)"
    r"|not\s+documented\b"
    r"|no\s+(?:filter|control|option|rule)\s+for\b"
    r")",
    re.IGNORECASE,
)


def _drop_meta_sentences(text: str) -> str:
    """Drop provenance sentences, keeping the product-behavior ones.  If every
    sentence reads as provenance the original text is returned unchanged - the
    caller decides whether to keep or drop it."""

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]
    kept = [
        sentence
        for sentence in sentences
        if not _META_SENTENCE_RE.search(sentence)
    ]
    return " ".join(kept) if kept else text


def _bound_claim_text(text: str, limit: int = 320) -> str:
    """Bound a claim at a sentence boundary, never mid-word."""

    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "? ", "! "):
        pos = cut.rfind(sep)
        if pos > 80:
            return cut[: pos + 1].strip()
    return cut.rsplit(" ", 1)[0].rstrip() + "."


def _desired_claim_text(claim: str) -> str:
    """Normalize a DESIRED_BEHAVIOR finding into a short observable outcome:
    strip the attribution wrapper, prefer the researcher's distilled sentence
    over the verbatim customer quote, drop meta/evidence sentences, flip the
    wanting frame into a requirement modal, and bound at a sentence boundary
    (never mid-word)."""

    text = _ROLE_TAG_RE.sub("", str(claim).strip()).strip()
    text = _DESIRED_WRAPPER_RE.sub("", text).strip()
    if text.startswith(('"', "'")):
        quote_char = text[0]
        close = -1
        idx = text.find(quote_char, 1)
        while idx != -1:
            if idx + 1 >= len(text) or text[idx + 1] in " \t":
                close = idx
                break
            idx = text.find(quote_char, idx + 1)
        if close > 0:
            quoted = text[1:close].strip()
            trailing = text[close + 1 :].strip().lstrip("-–— ").strip()
            text = trailing or quoted
    text = _drop_meta_sentences(text)
    match = _WANT_FLIP_RE.search(text) or _NEED_FLIP_RE.search(text)
    if match:
        obj = text[match.end() :].strip().rstrip(".")
        # A quoted customer sentence trailing the object ("... side: 'The
        # outputs are ...'") is evidence for the object, never part of it.
        quote_trail = re.search(r"\s*[:;,\-–—]\s*[\"']", obj)
        if quote_trail:
            obj = obj[: quote_trail.start()].strip().rstrip(".")
        if obj:
            if _MODAL_RE.search(obj):
                text = obj[0].upper() + obj[1:] + "."
            else:
                tail = _PARTICIPLE_TAIL_RE.search(obj)
                if tail:
                    # "X, restored in Y" -> "X must be restored in Y."
                    head = obj[: tail.start()].strip()
                    text = (
                        head[0].upper()
                        + head[1:]
                        + " must be "
                        + tail.group(1).lower()
                        + obj[tail.end() :]
                        + "."
                    )
                else:
                    text = obj[0].upper() + obj[1:] + " must be present."
    return _bound_claim_text(text)


def _normalized_desired_claims(
    claims: list[tuple[str, list[str]]], limit: int = 2
) -> list[tuple[str, list[str]]]:
    """Normalize desired-behavior claims and keep the strongest distinct
    outcomes first (a distilled observable sentence beats a bare quote)."""

    normalized: list[tuple[str, list[str]]] = []
    for claim, refs in claims:
        text = _desired_claim_text(claim)
        if text and all(text != existing for existing, _ in normalized):
            normalized.append((text, refs))
    normalized.sort(key=lambda item: -min(len(item[0]), 320))
    return normalized[:limit]


def _balance_quotes(text: str) -> str:
    """A documentation finding is mostly quoted source text, so bounding it at
    a sentence boundary can land inside a quotation and leave a dangling
    fragment.  Prefer trimming back to the last sentence end whose quotes are
    balanced; otherwise close the quote so the candidate still reads as a
    complete statement."""

    if text.count('"') % 2 == 0:
        return text
    for match in reversed(list(re.finditer(r'[.!?]"?(?=\s|$)', text))):
        head = text[: match.end()].rstrip()
        if head.count('"') % 2 == 0 and len(head) >= 40:
            return head
    return text.rstrip() + '"'


def _existing_claim_text(claim: str) -> str:
    """Normalize an EXISTING_BEHAVIOR finding into a short observable outcome:
    strip the researcher's documentation framing, drop provenance sentences
    and sentences that state what the documentation does NOT establish, then
    bound at a sentence boundary.

    The customer-attribution flips (_WANT_FLIP_RE / _NEED_FLIP_RE) are
    deliberately not applied: documentation records what the product does, it
    never voices a customer want, so rewriting it into a "must" would invent a
    requirement the documentation does not state."""

    text = _ROLE_TAG_RE.sub("", str(claim).strip()).strip()
    # A finding can carry both a role tag and the framing sentence ("EXISTING
    # BEHAVIOR: Docs confirm ..."), so peel repeatedly - bounded, and only
    # while the substitution actually shortens the text.
    for _ in range(3):
        stripped = _EXISTING_WRAPPER_RE.sub("", text).strip()
        if stripped == text or not stripped:
            break
        text = stripped
    kept = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
        and not _DOC_DISCLAIMER_RE.search(sentence)
        and not _META_SENTENCE_RE.search(sentence)
    ]
    if not kept:
        return ""
    text = _bound_claim_text(" ".join(kept))
    text = _balance_quotes(text)
    if text:
        text = text[0].upper() + text[1:]
    return text


def _relevance_tokens(text: str) -> set[str]:
    """Content words normalized for matching: trailing sentence punctuation
    removed and a light plural fold, so "publish warnings." matches
    "warnings?" in the question."""

    tokens: set[str] = set()
    for token in _ac_content_words(text):
        token = token.strip(".")
        if len(token) <= 2:
            continue
        tokens.add(token)
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            tokens.add(token[:-1])
    return tokens


def _claim_relevance(text: str, question_tokens: set[str]) -> int:
    """How many meaningful question terms the claim actually speaks to.

    Documentation research returns everything it found about the feature
    area, so a report on a sorting question can carry findings about columns,
    filters and downloads.  Ranking by length (the desired-claim heuristic)
    would promote the most verbose finding; ranking by question overlap
    promotes the one that answers what was asked."""

    if not question_tokens:
        return 0
    return len(_relevance_tokens(text) & question_tokens)


def _normalized_existing_claims(
    claims: list[tuple[str, list[str]]],
    limit: int = 2,
    question_tokens: set[str] | None = None,
    require_relevance: bool = True,
) -> list[tuple[str, list[str]]]:
    """Normalize established-behavior claims, keeping the ones that actually
    speak to the question first.

    A claim that still reads as meta/evidence prose after normalization is
    dropped rather than emitted: the Reviewer gate (_AC_META_PROSE_RE) would
    fail the whole plan on it, and silently dropping one unusable claim is
    safer than failing a plan the rest of the research supports.

    `require_relevance` guards the acceptance lane only.  There, a claim that
    shares no term with the question means the research answered a different
    question, and grounding a contract on it would be wrong.  The
    investigation lane sets it False: those claims never become a contract,
    the research is already bound to this question's admitted request, and
    requiring the finding to echo the question's own phrasing discards
    exactly the current-behavior detail a tester needs - the code that
    answers "does X change this?" with "no" is the same code that establishes
    what the product actually does instead."""

    tokens = question_tokens or set()
    scored: list[tuple[int, int, str, list[str]]] = []
    for order, (claim, refs) in enumerate(claims):
        text = _existing_claim_text(claim)
        if not text or _AC_META_PROSE_RE.search(text):
            continue
        if any(text == seen for _, _, seen, _ in scored):
            continue
        scored.append((_claim_relevance(text, tokens), order, text, refs))
    # Most relevant first; ties keep the researcher's own ordering.
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [
        (text, refs)
        for score, _, text, refs in scored
        if score > 0 or not require_relevance
    ][:limit]


def documented_baseline_claims(
    question: MissingQuestion,
    research_by_question: dict[str, QuestionResearchRecord],
    worker_results: list,
    limit: int = 2,
) -> list[tuple[str, list[str]]]:
    """Documented existing behavior relevant to this question, normalized for
    the acceptance lane.

    These ground a PROPOSED baseline candidate but never resolve the
    question: documentation establishes what the product does today, not the
    decision about what it should do.  Any bounded TBD stays."""

    return _normalized_existing_claims(
        existing_behavior_claims(question, research_by_question, worker_results),
        limit=limit,
        question_tokens=_relevance_tokens(question.question),
    )


def verified_implementation_claims(
    question: MissingQuestion,
    research_by_question: dict[str, QuestionResearchRecord],
    worker_results: list,
    limit: int = 2,
) -> list[tuple[str, list[str]]]:
    """Current implementation behavior relevant to this question, normalized
    for the investigation lane.

    Code research answers "what does the product do today on this path".
    That is the baseline a tester re-verifies and the compatibility anchor a
    change must not break, so it must reach coverage.  It is never acceptance
    authority and never resolves the question: only a human decision or a
    customer-stated desire can do that, so any bounded TBD stays."""

    return _normalized_existing_claims(
        implementation_behavior_claims(
            question, research_by_question, worker_results
        ),
        limit=limit,
        question_tokens=_relevance_tokens(question.question),
        require_relevance=False,
    )


_DESIRED_PROPOSED_RATIONALE = (
    "Customer-stated desired behavior established by admitted research; "
    "proposed pending the product decision carried by convergence."
)
_EXISTING_PROPOSED_RATIONALE = (
    "Documented existing behavior established by admitted documentation "
    "research; proposed as the baseline the ticket preserves or changes. "
    "It does not decide the open acceptance question, which stays bounded."
)
_IMPLEMENTATION_ORACLE_RATIONALE = (
    "Current implementation behavior established by admitted code research; "
    "recorded as the baseline a tester re-verifies on the changed path. "
    "Code is not a product contract, so it never becomes acceptance "
    "coverage and never resolves the open acceptance question."
)


def _normalize_candidate_key(text: str) -> str:
    """Case/punctuation-insensitive key for deduplicating coverage candidates
    that say the same thing through different spacing or quoting."""

    return re.sub(r"[^a-z0-9]+", " ", str(text).casefold()).strip()


def _establishing_acceptance_claims(
    question: MissingQuestion,
    research_by_question: dict[str, QuestionResearchRecord],
    worker_results: list,
    limit: int = 2,
) -> list[tuple[str, list[str], str]]:
    """Normalized customer-stated desired behavior that answers this question,
    as (text, source_refs, rationale) triples.  Only a desire is a decision,
    so only these replace the question's open/TBD disposition."""

    return [
        (text, refs, _DESIRED_PROPOSED_RATIONALE)
        for text, refs in _normalized_desired_claims(
            desired_behavior_claims(
                question, research_by_question, worker_results
            ),
            limit=limit,
        )
    ]


# Reviewer contract: meta/evidence commentary inside an AC.  These markers
# describe the evidence, never the product behavior under test.
_RETRIEVAL_BOILERPLATE_RE = re.compile(
    r"(?:learning retrieval profile|use this for (?:jira-driven )?qa/test-plan "
    r"retrieval|high-signal topics and headings|retrieval terms\s*:)",
    re.IGNORECASE,
)

_AC_META_PROSE_RE = re.compile(
    r"\b(?:customer-stated|verbatim|states they want|states:|the slide|"
    r"the attachment shows|evidence shows|research found|"
    r"documentation establishes|as per slide)\b",
    re.IGNORECASE,
)

# Coverage lanes must report real dispositions.  A line that only says an
# internal record exists tells a tester nothing and is not coverage.  Match
# that exact bookkeeping phrasing only - "(see trace)" on its own is a
# legitimate citation suffix on a real disposition.
_COVERAGE_FILLER_RE = re.compile(
    r"internal evidence recorded for\s+\d+\s+closure records",
    re.IGNORECASE,
)


def _normalize_for_paraphrase(text: str) -> str:
    """Collapse a statement to compare meaning-bearing words only."""

    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text.lower()).split())


# Request grammar describes what someone WANTS, not what the product DOES.
# "Ability to view the topic list", "Need a way to export" and "Support for
# COUNT retention" cannot be passed or failed by exercising the product, so
# they are requests carried through verbatim, never acceptance criteria.
# Outcome grammar ("the export job writes a completion marker") is testable
# even when the ticket author happened to phrase the request that way, so this
# deliberately keys on the asking phrase rather than on text identity.
_AC_REQUEST_GRAMMAR_RE = re.compile(
    r"\b(?:ability to|abilities to|need(?:s)? (?:a|the) (?:way|ability|option)|"
    r"provide (?:a|the) (?:way|ability|option)|"
    r"there (?:should|must) be (?:a way|an option)|"
    r"would like (?:to|the)|want(?:s)? (?:a|the) (?:way|ability|option)|"
    r"request(?:ing)? (?:a|the) (?:way|ability|option)|"
    r"support for (?:adding|having|providing))\b",
    re.IGNORECASE,
)


def _is_request_not_outcome(statement: str) -> bool:
    """True when an AC asks for a capability instead of stating an outcome."""

    return bool(_AC_REQUEST_GRAMMAR_RE.search(statement))


# Deterministic request -> outcome reframe.  The canonical runtime has no LLM,
# so this replaces ONLY the asking phrase and preserves every remaining content
# word: it can never introduce behavior the evidence does not already carry.
# "Ability to view the topic list in map order" therefore becomes "A user can
# view the topic list in map order" - the same claim, stated as an outcome a
# tester can pass or fail.
_REQUEST_TO_OUTCOME_RE = re.compile(
    r"(?:^|\|\s*|[-–—:]\s*)(?:"
    r"(?:the\s+)?abilit(?:y|ies)\s+to|"
    r"need(?:s)?\s+(?:a|the)\s+(?:way|ability|option)\s+to|"
    r"provide\s+(?:a|the)\s+(?:way|ability|option)\s+to|"
    r"there\s+(?:should|must)\s+be\s+(?:a\s+way|an\s+option)\s+to|"
    r"would\s+like\s+to|"
    r"want(?:s)?\s+(?:a|the)\s+(?:way|ability|option)\s+to|"
    r"request(?:ing)?\s+(?:a|the)\s+(?:way|ability|option)\s+to"
    r")\s+",
    re.IGNORECASE,
)


def _derive_outcome_statement(statement: str) -> str | None:
    """Reframe request grammar as an observable outcome.

    Returns None when the asking phrase cannot be removed without guessing at
    the intended behavior.  A None result deliberately leaves the candidate
    non-observable so the promotion gate rejects it, rather than letting the
    Writer invent an outcome the evidence never established.
    """

    text = " ".join(statement.split())
    if not text:
        return None
    match = _REQUEST_TO_OUTCOME_RE.search(text)
    if match is None:
        return None
    remainder = text[match.end() :].strip()
    if not remainder:
        return None
    remainder = remainder[0].lower() + remainder[1:]
    derived = f"A user can {remainder}"
    if not derived.endswith((".", "!", "?")):
        derived += "."
    # A reframe that still reads as a request is not an outcome; fail closed.
    return None if _is_request_not_outcome(derived) else derived


def _as_outcome_sentence(clause: str) -> str:
    """Normalize an admitted clause into one sentence, content-preserving."""

    text = " ".join((clause or "").split())
    if not text:
        return text
    text = text[0].upper() + text[1:]
    if not text.endswith((".", "!", "?")):
        text += "."
    return text


# D2: an independent requirement clause carries its own subject and modal, so
# "<requirement A> and the <subject B> should <behavior B>" is two separately
# pass/fail contracts.  Splitting only on a modal-bearing conjunct keeps
# ordinary descriptive "and" phrases ("topics and maps") intact.
_INDEPENDENT_REQUIREMENT_RE = re.compile(
    r"\s+and\s+(?=(?:the|a|an|its|their|each|every|all)?\s*[\w\s,'\"-]{3,80}?"
    r"\b(?:should|must|shall|will|needs?\s+to|has\s+to|have\s+to)\b)",
    re.IGNORECASE,
)


def _split_independent_requirements(statement: str) -> list[str]:
    """Split a compound requirement into independently testable clauses.

    Returns the original statement unchanged when no conjunct carries its own
    modal requirement, so a descriptive "and" is never split.
    """

    text = " ".join((statement or "").split())
    if not text:
        return []
    parts = [part.strip(" ,;") for part in _INDEPENDENT_REQUIREMENT_RE.split(text)]
    parts = [part for part in parts if part]
    return parts or [text]


# D2/D1-c: phrasings that turn an unresolved capability into the decision QE
# actually needs, without asserting either answer.
_TBD_LEAD_RE = re.compile(
    r"^\s*(?:"
    # Longest-first: Python alternation is first-match-wins, so the generic
    # modal form below would otherwise consume "Would it " and strand
    # "be possible to ..." in the rewritten question.
    r"would\s+it\s+be\s+possible\s+to\s+"
    r"|is\s+it\s+possible\s+to\s+"
    r"|(?:could|can|would|will|may|should)\s+(?:we|you|it)\s+(?:also\s+)?(?:please\s+)?"
    r"|any\s+(?:chance|plan|plans)\s+(?:of|to|for)\s+"
    r"|how\s+about\s+"
    r")"
    r"(?:(?:add|have|support|provide|include|show|display|expose|allow|enable|get)"
    # "an" before "a", and the article must be followed by whitespace:
    # otherwise "an export" loses its "a" ("n export") and "add assets"
    # loses its first letter ("ssets").
    r"(?:ing)?\s+(?:also\s+)?(?:(?:an|a|the)\s+)?)?",
    re.IGNORECASE,
)


def _derive_tbd_question(statement: str) -> str | None:
    """Phrase unresolved material behavior as a bounded (TBD) question.

    The result always ends with '?' so it reads as the open decision rather
    than as an asserted outcome.  Returns None when there is nothing to ask.
    """

    text = " ".join((statement or "").split()).strip()
    if not text:
        return None
    stripped = _TBD_LEAD_RE.sub("", text)
    if stripped == text and text.endswith("?"):
        # Already phrased as the open decision - a planner question reaches
        # this lane verbatim.  Re-wrapping it would produce double-question
        # grammar ("Confirm the expected behavior for what ... mean?") and,
        # worse, a variant that no longer matches its own source, so the
        # dedup guard below misses it and the same question surfaces twice.
        return text[0].upper() + text[1:]
    remainder = stripped.strip(" ?.").strip()
    if not remainder:
        return None
    # Ordinary sentence capitalization is safe to fold, but a product name is
    # not: blindly lowercasing turns "COUNT-based retention" into "cOUNT-based"
    # and the "Generated Outputs" tab into "generated Outputs".  A further
    # capital later in the fragment marks it as a proper product term.
    if (
        len(remainder) > 1
        and remainder[0].isupper()
        and remainder[1].islower()
        and not any(word[:1].isupper() for word in remainder.split()[1:])
    ):
        remainder = remainder[0].lower() + remainder[1:]
    return f"Confirm the expected behavior for {remainder}?"

_TBD_HOST_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "confirm",
        "each",
        "expected",
        "for",
        "from",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "same",
        "should",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "to",
        "user",
        "was",
        "when",
        "with",
        "behavior",
    }
)


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", (text or "").casefold())
        if len(token) > 2 and token not in _TBD_HOST_STOPWORDS
    }


def _closest_criterion(
    question: str, written: list["WrittenAcceptanceCriterion"]
) -> "WrittenAcceptanceCriterion | None":
    """Pick the criterion an unresolved question belongs under.

    A TBD attaches only to a criterion it genuinely shares subject matter with;
    an unrelated question becomes its own criterion rather than being buried
    under a criterion it does not qualify.
    """

    question_tokens = _content_tokens(question)
    if not question_tokens:
        return None
    best: WrittenAcceptanceCriterion | None = None
    best_score = 0.0
    for criterion in written:
        if criterion.unresolved:
            continue
        overlap = question_tokens & _content_tokens(criterion.outcome)
        if not overlap:
            continue
        score = len(overlap) / len(question_tokens)
        if score > best_score:
            best_score = score
            best = criterion
    # Require real subject overlap, not one incidental shared noun.
    return best if best_score >= 0.34 else None


# Two acceptance criteria sharing this fraction of content words restate one
# product outcome.  Kept aligned with scripts/uac_eval/precision.py
# REDUNDANCY_JACCARD and the skill's AC-redundancy rule.
_AC_NEAR_DUPLICATE_JACCARD = 0.6
_AC_CONTENT_STOPWORDS = frozenset(
    "the a an and or of to in on for is are be that this it with as by from at "
    "should must will shall verify ensure when then given user able "
    "not no if into their its each any all both which while".split()
)


def _ac_content_words(statement: str) -> set[str]:
    """Return the words that actually distinguish one criterion from another."""

    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_.]+", statement.lower())
    return {
        token
        for token in tokens
        if token not in _AC_CONTENT_STOPWORDS and len(token) > 2
    }


def _absorb_near_duplicate(
    written: list["WrittenAcceptanceCriterion"],
    outcome: str,
    *,
    unresolved: bool,
    candidate_ids: list[str],
    fact_ids: list[str],
    disposition_ids: list[str],
    evidence_ids: list[str],
) -> bool:
    """Fold an outcome into the criterion it restates; report whether it merged.

    A Jira summary and its description routinely carry the same requirement in
    different words, so both reach the promotion gate as separate admitted
    candidates.  Rendering both produces two acceptance criteria a reviewer
    reads as one requirement written twice.  Merging keeps the wording that
    carries more of the source detail and unions every source binding, so no
    record becomes unaddressable and no admitted meaning is lost.

    A resolved outcome and an unresolved question are never folded together:
    that would silently settle a decision the evidence left open.
    """

    words = _ac_content_words(outcome)
    if not words:
        return False
    for index, existing in enumerate(written):
        if existing.unresolved != unresolved:
            continue
        existing_words = _ac_content_words(existing.outcome)
        if not existing_words:
            continue
        overlap = len(words & existing_words) / len(words | existing_words)
        if overlap < _AC_NEAR_DUPLICATE_JACCARD:
            continue
        merged = existing.model_dump(exclude={"criterion_id"})
        # Strictly more content words means strictly more of the source
        # survives.  On a tie neither wording is demonstrably richer, so the
        # incumbent is kept - promotion order is deterministic, and guessing
        # at "better English" would not be.
        if len(words) > len(existing_words):
            merged["outcome"] = outcome
        merged["source_candidate_ids"] = [
            *merged["source_candidate_ids"],
            *candidate_ids,
        ]
        merged["source_fact_ids"] = [*merged["source_fact_ids"], *fact_ids]
        merged["source_disposition_ids"] = [
            *merged["source_disposition_ids"],
            *disposition_ids,
        ]
        merged["evidence_ids"] = [*merged["evidence_ids"], *evidence_ids]
        written[index] = WrittenAcceptanceCriterion(**merged)
        return True
    return False


# Terminal-disposition -> render section.  Module-level so the routing contract
# is directly assertable: a bounded acceptance TBD must stay acceptance-lane
# rather than being diverted into a sibling "product decisions" section.
_DISPOSITION_SECTIONS: dict[CoverageDisposition, str] = {
    CoverageDisposition.SEMANTIC_REGRESSION: "semantic_coverage",
    CoverageDisposition.STRUCTURAL_REGRESSION: "structural_hierarchy_coverage",
    CoverageDisposition.REFERENCE_REGRESSION: "referenced_content_coverage",
    CoverageDisposition.CONFIGURATION_VARIANT: "configuration_state_coverage",
    CoverageDisposition.GENERATED_OUTPUT_VALIDATION: "generated_output_validation",
    CoverageDisposition.NEGATIVE_BOUNDARY: "negative_boundary_coverage",
    CoverageDisposition.FAILURE_RECOVERY: "failure_recovery_coverage",
    CoverageDisposition.LIFECYCLE_COVERAGE: "lifecycle_coverage",
    CoverageDisposition.CROSS_MODE_REGRESSION: "cross_mode_regression",
    CoverageDisposition.NFR_COVERAGE: "nfr_coverage",
    CoverageDisposition.PRODUCT_SCOPE_QUESTION: "product_decisions",
    # D1-c: a bounded TBD is acceptance-material.  The Writer renders it inside
    # the criterion it qualifies, so routing it here as well would duplicate it
    # into a sibling section - exactly the diversion D1 removes.
    CoverageDisposition.ACCEPTANCE_TBD: "acceptance_contract",
    CoverageDisposition.ENGINEERING_DESIGN_DECISION: "product_decisions",
    CoverageDisposition.OUT_OF_SCOPE: "explicit_out_of_scope",
    CoverageDisposition.INVESTIGATED_AND_REJECTED: "investigated_and_rejected",
    CoverageDisposition.IMPLEMENTATION_ORACLE: "transformation_processing_coverage",
    CoverageDisposition.TECHNICAL_NOTE: "technical_notes",
    CoverageDisposition.KNOWN_LIMITATION: "known_limitations",
    CoverageDisposition.OPEN_QUESTION: "evidence_gaps",
    CoverageDisposition.UNSUPPORTED_INFERENCE: "evidence_gaps",
}


def _convergence_detail_lines(conv: Any) -> list[str]:
    """Evidence-bearing detail for one product decision.

    Research that ran is only useful if what it established reaches the
    reader.  Both the blocked render (no criteria yet) and the normal render
    (criteria produced) show the same three lines, so a decision never loses
    its evidence merely because the run succeeded.
    """

    if conv is None:
        return []
    detail: list[str] = []
    shown = conv.pm_view[:1] or conv.dev_view[:1] or conv.qe_view[:1]
    for claim in shown:
        detail.append(f"- What the evidence shows: {claim}")
    for unknown in conv.acceptance_changing_unknowns[:1]:
        detail.append(f"- Still unknown: {unknown}")
    # The conflict worth showing is the one that can change the acceptance
    # contract, not whichever happened to sort first.
    from app.services.convergence_service import _ACCEPTANCE_CHANGING_CONFLICTS

    classes = list(conv.conflict_classes)
    if len(classes) != len(conv.conflicts):
        classes = [""] * len(conv.conflicts)
    ranked = sorted(
        zip(conv.conflicts, classes),
        key=lambda pair: pair[1] not in _ACCEPTANCE_CHANGING_CONFLICTS,
    )
    for conflict, _class in ranked[:1]:
        detail.append(f"- Conflict to resolve: {conflict}")
    return detail


_QE_CHECK_LEAD_RE = re.compile(r"^(?:verify|confirm|check)\b", re.I)
_QE_STATUS_PREFIX_RE = re.compile(r"^(?:proposed|confirmed):\s*", re.I)
_QE_ARTICLE_PREFIX_RE = re.compile(r"^(?:A|An|The|No|Each)\b")
_QE_TBD_QUESTION_RE = re.compile(r"\?\s*(?:\(TBD\))?\.?\s*$", re.I)


def _as_manual_qe_check(text: str) -> str:
    """Present an outcome as a concrete manual-QE verification check.

    The Writer retains the underlying product outcome.  This presentation-only
    wrapper gives testers the requested ``Verify that <named item> ...`` voice
    without admitting generic ``Verify that the system ...`` wording.
    """

    value = _QE_STATUS_PREFIX_RE.sub("", text.strip())
    if (
        not value
        or _QE_CHECK_LEAD_RE.match(value)
        or _QE_TBD_QUESTION_RE.search(value)
    ):
        return value
    article = _QE_ARTICLE_PREFIX_RE.match(value)
    if article:
        value = article.group(0).lower() + value[article.end():]
    return f"Verify that {value}"


def _render_written_criterion(criterion: "WrittenAcceptanceCriterion") -> str:
    """Flatten a written criterion into its human-facing QE check text.

    Sub-points stay attached to the criterion they qualify instead of being
    relocated to a sibling section, and an unresolved criterion keeps its
    (TBD) marker so it is never read as an asserted outcome.
    """

    outcome = criterion.outcome.strip()
    if criterion.unresolved and "(TBD)" not in outcome:
        outcome = f"{outcome} (TBD)"
    parts = [_as_manual_qe_check(outcome)]
    for sub_point in criterion.sub_points:
        text = sub_point.text.strip()
        if (
            sub_point.kind == AcceptanceSubPointKind.TBD_QUESTION
            and "(TBD)" not in text
        ):
            text = f"{text} (TBD)"
        parts.append(f"- {_as_manual_qe_check(text)}")
    return "\n".join(parts)


def _acceptance_source_line(
    fact_ids: list[str],
    facts_by_id: Mapping[str, Any],
    evidence_refs: list[str] | None = None,
) -> str:
    """Human-facing Source line for one acceptance criterion.

    Labels are derived only from the facts and admitted evidence refs that
    actually support THIS criterion, so a documentation source is never
    credited for behavior it does not establish - and, symmetrically, a
    documentation-established behavior is never credited to Jira alone.  A
    criterion with no external supporting source is reported as QE-derived.
    """

    labels: list[str] = []

    def add(label: str) -> None:
        if label not in labels:
            labels.append(label)

    for fact_id in fact_ids:
        fact = facts_by_id.get(fact_id)
        if fact is None:
            continue
        reference = str(getattr(fact, "source_reference", "") or "")
        lowered = reference.lower()
        if "attachment" in lowered:
            add("Jira attachments")
        elif lowered.startswith("jira:"):
            add("Jira")
        elif "experienceleague.adobe.com" in lowered:
            add("Experience League")
        elif lowered.startswith(("doc:", "learned-doc:")):
            add("Product documentation")
        elif lowered.startswith(("repo:", "code:", "github:")):
            add("Implementation evidence")
    # Admitted research cites its sources as documentation slugs rather than
    # contract facts, so a criterion grounded by researched documentation must
    # credit that documentation instead of silently inheriting the Jira label
    # of the question that triggered the research.
    for ref in evidence_refs or []:
        lowered = str(ref).lower()
        if lowered.startswith(("doc:", "learned-doc:")):
            add("Product documentation")
        elif lowered.startswith(("repo:", "code:", "github:")):
            add("Implementation evidence")
    if not labels:
        return "QE-derived coverage."
    return " + ".join(labels) + "."


_DOMAIN_SIGNALS: dict[IssueDomain, tuple[str, ...]] = {
    IssueDomain.PUBLISHING: (
        "publish",
        "output preset",
        "native pdf",
        "html5",
        "aem sites",
        "dita-ot",
        "dita ot",
        "generated page",
    ),
    IssueDomain.AUTHORING: (
        "authoring",
        "web editor",
        "editor",
        "full tags",
        "right panel",
    ),
    IssueDomain.CONTENT_MANAGEMENT: (
        "content management",
        "repository",
        "asset",
        "move asset",
        "rename asset",
        "delete asset",
        "move folder",
        "rename folder",
        "delete folder",
    ),
    IssueDomain.SEARCH_QUERY: (
        "query builder",
        "oak",
        "query engine",
        "search",
        "query",
    ),
    IssueDomain.WORKFLOW_JOB: ("workflow", "job", "queue", "executor", "scheduler"),
    IssueDomain.MIGRATION: ("migration", "migrate", "upgrade", "import"),
    IssueDomain.PERFORMANCE: (
        "performance",
        "bulk",
        "scale",
        "thousand",
        "concurrent",
        "large collection",
    ),
    IssueDomain.TRANSLATION: ("translation", "localization", "locale", "language copy"),
    IssueDomain.BASELINE: ("baseline", "version label"),
    IssueDomain.ASSETS: ("aem assets", "dam", "asset metadata"),
    IssueDomain.EXTENSION_FRAMEWORK: (
        "extension",
        "plugin",
        "customization",
        "extensibility",
    ),
    IssueDomain.API: (
        "api",
        "apis",
        "endpoint",
        "rest ",
        "request payload",
        "response code",
    ),
}

_OUT_OF_SCOPE_CLAUSE_RE = re.compile(
    r"\b(?:out\s+of\s+scope|not\s+in\s+scope|excluded\s+from\s+scope|"
    r"not\s+applicable|does\s+not\s+apply)\b",
    re.IGNORECASE,
)

_GENERATED_ARTIFACT_DELIVERY_SIGNALS = (
    "generate output",
    "output generation",
    "generated output",
    "generated artifact",
    "generated page",
    "publishing workflow",
    "publish job",
    "republish",
    "post generation",
    "output path",
    "download",
    "activation",
    "publication",
)

_CONTEXTUAL_GENERATED_ARTIFACT_DELIVERY_RE = re.compile(
    r"\bpublish(?:ed|es|ing)?\b.{0,40}"
    r"\b(?:documents?|pages?|maps?|topics?|outputs?|artifacts?|pdfs?|sites?)\b"
    r"|\b(?:documents?|pages?|maps?|topics?|outputs?|artifacts?|pdfs?|sites?)\b"
    r".{0,40}\bpublish(?:ed|es|ing)?\b",
    re.IGNORECASE,
)

_PUBLISHING_CONFIGURATION_ONLY_SIGNALS = (
    "configuration only",
    "ui only",
    "preset editor",
    "preset dialog",
    "field label",
    "dropdown",
)

# P1: scope-field questions are the only user-facing clarification surfaces the
# scope resolver may raise. Hoisted so the deterministic question id/revision is
# computable before questions are generated (clarification resume binds to it).
_SCOPE_FIELD_QUESTIONS: dict[str, tuple[str, bool]] = {
    "ENABLE_DITA_OT_PROCESSING": (
        "Is Enable DITA-OT Processing expected to be ON, OFF, both, or not applicable?",
        True,
    ),
    "PRIMARY_PRESET_TYPE": (
        "Which exact output preset owns this functionality?",
        True,
    ),
    "OUT_OF_SCOPE": ("What should explicitly be out of scope?", False),
    "SHARED_PATH_OUTPUTS": (
        "Which other presets intentionally share this behavior?",
        False,
    ),
}


def scope_question_revision(field: str) -> str:
    """Deterministic revision of a scope-field question (text + dimension)."""

    text = _SCOPE_FIELD_QUESTIONS[field][0]
    return stable_sha256({"question": text, "dimension": None})[:12]


def scope_question_id(field: str) -> str:
    """The deterministic MissingQuestion id a scope field would produce."""

    text, blocking = _SCOPE_FIELD_QUESTIONS[field]
    identity = {
        "question": text,
        "dimension": None,
        "authority_subject": AuthoritySubject.PRODUCT_CONTRACT,
        "target_source_types": _target_sources(AuthoritySubject.PRODUCT_CONTRACT),
        "blocking": blocking,
    }
    return f"question:{stable_sha256(identity)[:32]}"


# Generic materiality gate: an applicability/configuration dimension becomes
# a user-facing acceptance question only when admitted evidence indicates
# that changing the dimension can change an acceptance-material outcome.
# Mere existence of the setting, same-domain vocabulary, or an unknown value
# is NOT material interaction.  The interaction evidence must tie the
# dimension itself to conditional or differing behavior.
_DIMENSION_INTERACTION_BEHAVIOR_RE = re.compile(
    r"\b(?:enabled|disabled|differs?|different|changes?|changed|only|"
    r"respects|honours?|honors?|ignores?|both|either|modes?|depends|"
    r"depending|varies|vary|affects?)\b",
    re.IGNORECASE,
)

# Per-dimension identity signals (the scope dimensions the runtime owns).
_SCOPE_DIMENSION_SIGNALS: dict[str, tuple[str, ...]] = {
    "ENABLE_DITA_OT_PROCESSING": ("dita-ot", "dita ot", "dita_ot"),
    "PRIMARY_PRESET_TYPE": ("preset", "output type", "output format"),
}

# Human-readable dimension labels for research-first materiality probes.
_SCOPE_FIELD_DIMENSION_LABELS: dict[str, str] = {
    "ENABLE_DITA_OT_PROCESSING": "the processing mode",
    "PRIMARY_PRESET_TYPE": "the output preset choice",
}


def _dimension_interaction_present(
    semantic_units: list[str], field: str
) -> bool:
    """True only when the dimension is tied to conditional or differing
    behavior within a bounded window around its own mention - never from the
    dimension merely existing, and never from vocabulary in an unrelated
    sentence of the same unit."""

    signals = _SCOPE_DIMENSION_SIGNALS.get(field, ())
    if not signals:
        return False
    text = " ".join(semantic_units)
    for signal in signals:
        for match in re.finditer(re.escape(signal), text):
            start = max(0, match.start() - 60)
            window = text[start : match.end() + 60]
            if _DIMENSION_INTERACTION_BEHAVIOR_RE.search(window):
                return True
    return False


def _dimension_signal_present(semantic_units: list[str], field: str) -> bool:
    """True when admitted evidence mentions the dimension at all - a
    plausible evidence-bound relationship that warrants a bounded
    research-first materiality probe instead of silent suppression."""

    signals = _SCOPE_DIMENSION_SIGNALS.get(field, ())
    return any(
        signal in unit for unit in semantic_units for signal in signals
    )


# P1: authority classes whose human clarification may establish an
# acceptance-changing answer. Developer hypotheses, QE proposals, inferred or
# historical roles never admit a clarification.
_CLARIFICATION_ESTABLISHING_AUTHORITIES = frozenset(
    {
        AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
        AuthorityClass.CONFIRMED_PRODUCT_DECISION,
        AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
        AuthorityClass.SPECIFICATION_AUTHORITY,
        AuthorityClass.CUSTOMER_REQUEST,
    }
)

# P1 promotion-safety shapes (generic; no feature or ticket vocabulary).
_COMBINATION_CLAIM_RE = re.compile(
    r"\b(?:both|combined|combination|together|cross[- ]?product)\b", re.IGNORECASE
)
_RETENTION_STEM_RE = re.compile(r"\b(?:retain\w*|kept|keep(?:s|ing)?|preserv\w*|remain\w*)\b", re.IGNORECASE)
_REMOVAL_STEM_RE = re.compile(r"\b(?:remov\w+|delet\w+|purg\w+|prun\w+)\b", re.IGNORECASE)
_USABILITY_STEM_RE = re.compile(
    r"\b(?:open\w*|accessible|visible|usable|available|viewable|download\w*|readable)\b",
    re.IGNORECASE,
)
_BACKWARD_COMPAT_CLAIM_RE = re.compile(
    r"\b(?:backward[- ]?compat\w*|unchanged after (?:the )?upgrade|"
    r"existing (?:installations?|configurations?|behaviou?r)\b[^.]{0,60}"
    r"\b(?:unchanged|preserved|retained|unaffected)\b|"
    r"(?:remain|remains|stays?|stayed) (?:unchanged|compatible)|upgrade[- ]safe)\b",
    re.IGNORECASE,
)

# P1 (no noisy clone-grep coverage): raw code/retrieval fragments - paths,
# class/def dumps, call expressions, test-suite labels - are internal
# evidence/debug data and never become human-facing coverage prose.
_RAW_FRAGMENT_RE = re.compile(
    r"(?:[A-Za-z]:\\"
    r"|[\w.-]+/[\w./-]*\.(?:py|ts|tsx|jsx|java|json|xml|dita|ditamap|yml|yaml|toml)\b"
    r"|\bclass\s+[A-Z]\w*|\bdef\s+\w+\(|\b[A-Z][\w$]*\.[a-z][\w$]*\s*\("
    r"|\bFeature:\s)"
)

# D1-d: the most sub-points one criterion may absorb from regression-class
# coverage.  The contract stays scannable; anything beyond the bound is
# already represented by the coverage matrix in the trace.
_MAX_VARIANT_SUB_POINTS = 4

# D1-d: how much subject a regression variant must share with the outcome it
# qualifies, measured against the smaller of the two subjects.
_VARIANT_HOST_MIN_OVERLAP = 0.34


def _derive_variant_statement(candidate: str) -> str | None:
    """Reduce a regression-coverage row to a testable variant clause.

    Returns None when the row carries bookkeeping, a raw retrieval fragment,
    or meta prose instead of behavior a tester can check, so unreadable
    coverage is never pushed into the acceptance contract.
    """

    text = " ".join(candidate.split())
    if not text:
        return None
    if (
        _COVERAGE_FILLER_RE.search(text)
        or _RAW_FRAGMENT_RE.search(text)
        or _AC_META_PROSE_RE.search(text)
    ):
        return None
    # "DIMENSION: behavior" rows carry the dimension as an internal axis
    # label; the tester-facing clause keeps the behavior only.
    head, separator, tail = text.partition(": ")
    if separator and head.replace("_", "").isalpha() and head.isupper():
        text = tail.strip()
        if not text:
            return None
    if _is_request_not_outcome(text):
        return None
    # A fragment too short to carry a subject and an outcome is not coverage.
    if len(text.split()) < 4:
        return None
    if not text.endswith((".", "!", "?")):
        text += "."
    return text[0].upper() + text[1:]


def _closest_variant_host(
    variant: str, written: list["WrittenAcceptanceCriterion"]
) -> "WrittenAcceptanceCriterion | None":
    """Pick the criterion a regression variant qualifies, or None.

    A variant clause is usually longer than the outcome it qualifies, so
    scoring it against its own token count penalises exactly the detail that
    makes it useful.  The overlap is therefore normalised against the smaller
    subject, which keeps the "genuinely shared subject matter" requirement
    without punishing a specific clause for being specific.  No host means the
    behavior stays out of the contract - it never invents a parent.
    """

    variant_tokens = _content_tokens(variant)
    if not variant_tokens:
        return None
    best: WrittenAcceptanceCriterion | None = None
    best_score = 0.0
    for criterion in written:
        if criterion.unresolved:
            continue
        outcome_tokens = _content_tokens(criterion.outcome)
        if not outcome_tokens:
            continue
        overlap = variant_tokens & outcome_tokens
        # One incidental shared noun is coincidence, not shared subject.
        if len(overlap) < 2:
            continue
        score = len(overlap) / min(len(variant_tokens), len(outcome_tokens))
        if score > best_score:
            best_score = score
            best = criterion
    return best if best_score >= _VARIANT_HOST_MIN_OVERLAP else None

# UX1: human-question quality contract - a user-facing question must be a
# product behavior decision readable without repository context.  Raw
# evidence (paths, code symbols, env/constant dumps, arbitrary token lists)
# may trigger investigation but is never interpolated into question text.
_QUESTION_CONSTANT_RE = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")


# UX1: person-centric obligation/burden language ("you should check the
# log", "authors would need to ...", "I need to go to ...") describes a
# human workaround forced by CURRENT behavior - an observation/problem
# statement, never a product requirement.  The generic modal veto below
# ("should"/"must") must not rescue these: the modal attaches to the person,
# not to the product.
_HUMAN_BURDEN_RE = re.compile(
    r"\b(?:i|we|you|authors?|users?|administrators?|one)\s+"
    r"(?:would\s+)?(?:need|needs|have|has)\s+to\b"
    r"|\b(?:i|we|you|authors?|users?|administrators?)\s+(?:should|must)\b",
    re.IGNORECASE,
)

# UX1: product-directed imperative - a sentence that commands product
# behavior ("Provide an option ...", "The system shall ...").
_PRODUCT_IMPERATIVE_RE = re.compile(
    r"^\s*(?:provide|support|add|show|display|allow|enable|disable|remove|"
    r"delete|create|generate|retain|keep|preserve|exclude|include|hide|"
    r"expose|rename|move|copy|sync|validate|log|record|return|fail|retry)\b"
    r"|\b(?:the\s+)?(?:system|product|editor|output|preset|dialog|panel|"
    r"job|service|api|user\s+interface)\s+(?:shall|must|should|will)\b",
    re.IGNORECASE,
)

# UX1: current-state narrative markers ("the old UI ...", "currently ...")
# describe what the product already does; without an imperative they are
# context, never requirement candidates.
_CURRENT_STATE_MARKER_RE = re.compile(
    r"\b(?:old|existing|current(?:ly)?|today|as of now|previous(?:ly)?|"
    r"already)\b",
    re.IGNORECASE,
)

# UX1: declarative requirement shape - a behavior verb or modal directive.
# Distinguishes a stated contract ("Generated PDF output includes metadata")
# from a narrative fragment ("Outputs in the editor") in free-text
# description/summary fields.
_REQUIREMENT_SHAPE_RE = re.compile(
    r"\b(?:shall|must|should|will|would)\b"
    r"|\b(?:includes?|excludes?|contains?|removes?|deletes?|keeps?|retains?|"
    r"writes?|reads?|shows?|displays?|returns?|creates?|generates?|updates?|"
    r"saves?|stores?|persists?|sends?|receives?|processes?|produces?|"
    r"requires?|supports?|allows?|enables?|disables?|hides?|exposes?|"
    r"validates?|rejects?|fails?|retries|skips?|ignores?|"
    r"loads?|renders?|publishes?|exports?|imports?)\b",
    re.IGNORECASE,
)


def _human_question_safe(text: str) -> bool:
    """True when text is readable product language for a human question."""

    value = text.strip()
    if not value:
        return False
    if _RAW_FRAGMENT_RE.search(value):
        return False
    if _QUESTION_CONSTANT_RE.search(value):
        return False
    # Arbitrary numeric/token lists (grep result joins) are not question
    # language: more than two comma-separated fragments is a dump, not an
    # enumeration.
    if len([part for part in value.split(",") if part.strip()]) > 2:
        return False
    return True


# The question subject is the noun a researcher is asked about, so it must be
# product language.  `_human_question_safe` only rejects obvious raw fragments;
# retrieval bleed still admits test fixtures ("3_post_upgrade_scenarios.feature")
# and test-method identifiers ("RO1_shouldCorrectly_ReadAll_DitaProfiles") as if
# they named the behavior under acceptance.  A question built on one of those is
# unanswerable and comes back NOT_APPLICABLE, so it is rejected as a subject.
#
# The snake_case forms above are only half the bleed.  Java and TypeScript name
# test methods and accessors in camelCase, so
# "shouldThrowExceptionWhenInvalidPresetTypeInUpdateExistingPresets" and "getId"
# passed every check and became the subject of an entire planned question set.
# A camelCase test-method prefix and a bare accessor identifier are code
# artifacts in every codebase and never name a product behavior.
_PRODUCT_SUBJECT_REJECT_RE = re.compile(
    r"(?:\\"
    r"|\.(?:py|ts|tsx|jsx|java|json|xml|dita|ditamap|yml|yaml|toml|feature|md)\b"
    r"|^[A-Za-z]{1,4}\d+_"
    r"|\b(?:should|test|spec|scenario|fixture)_"
    r"|_(?:test|spec)\b"
    r"|[A-Za-z]_[A-Za-z]"
    r"|\b(?:should|test|it|when|given|verify|assert)[A-Z]"
    r"|\b(?:get|set|is|has)[A-Z][A-Za-z0-9]*\b"
    r"|\(\))"
)

# A subject is the noun a researcher looks up, not a sentence.  Contract facts
# are captured as whole source sentences ("Map title/dc:title shows entire
# booktitle element."), and substituting one into a question template produces a
# sentence nested inside a sentence that no worker can act on.  Cutting at the
# first finite verb leaves the subject noun phrase ("Map title/dc:title").
#
# The pattern is deliberately case-SENSITIVE and lowercase-only: a capitalized
# word inside a phrase belongs to a product name, not to a predicate, so
# "Topic List report" keeps its "List" while "TopicList report lists the topics"
# is cut at "lists".  It is also separate from `_REQUIREMENT_SHAPE_RE`, which
# classifies requirement shape elsewhere; widening that pattern would change
# promotion behavior rather than question wording.
_SUBJECT_FINITE_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|has|have|had|does|do|did|can|cannot|will|would|"
    r"shall|should|must|shows?|displays?|lists?|sorts?|contains?|includes?|"
    r"returns?|renders?|generates?|creates?|removes?|deletes?|retains?|"
    r"writes?|reads?|appears?|becomes?|remains?|occurs?|happens?|throws?)\b"
)

# A leading adverbial clause is scene-setting, not the subject itself.
_SUBJECT_LEADING_PREPOSITION_RE = re.compile(
    r"^(?:in|on|at|under|for|with|within|during|when|while|after|before|"
    r"currently|presently|today)\s+",
    re.IGNORECASE,
)


def _subject_noun_phrase(value: str) -> str:
    """Reduce a source-authored sentence to the noun phrase it is about."""

    normalized = value.strip().rstrip(" .;:,")
    match = _SUBJECT_FINITE_VERB_RE.search(normalized)
    if match is not None and match.start() > 0:
        head = normalized[: match.start()].strip().rstrip(" .;:,-")
        # A one-or-two character head is an article or fragment left behind by
        # an unusual sentence shape; keeping the original is more informative.
        if len(head) >= 3:
            normalized = head
    stripped = _SUBJECT_LEADING_PREPOSITION_RE.sub("", normalized).strip()
    if len(stripped) >= 3:
        normalized = stripped
    return normalized


def _product_subject_safe(text: str) -> bool:
    """True when text can name the behavior a research question is asked about."""

    value = text.strip()
    if not _human_question_safe(value):
        return False
    if _PRODUCT_SUBJECT_REJECT_RE.search(value):
        return False
    # A single forward slash is ordinary product wording that a reporter writes
    # as an alternation ("Map title/dc:title"); a leading slash or two or more
    # slashes is a repository or file path and never a behavior name.
    if value.startswith("/") or value.count("/") >= 2:
        return False
    return True


def _behavior_subject_from_facts(facts: ContractFactSet) -> str:
    """Return the ticket's own product subject for a human research question.

    Closure entities come from retrieval and are frequently unusable as a
    subject.  The issue itself always names what it is about, so the contract
    facts - never a feature taxonomy - supply the fallback subject.  An empty
    result means the caller keeps its own generic wording.
    """

    for fact_type in (
        ContractFactType.PRIMARY_PRODUCT_AREA,
        ContractFactType.HUMAN_TERMINOLOGY,
    ):
        for fact in facts.facts:
            if fact.fact_type != fact_type:
                continue
            candidate = _subject_noun_phrase(
                _bounded_behavior_subject(fact.literal, limit=80)
            )
            if candidate and _product_subject_safe(candidate):
                return candidate
    behavior_fact = _material_behavior_fact(facts)
    if behavior_fact is not None:
        candidate = _subject_noun_phrase(
            _bounded_behavior_subject(behavior_fact.literal, limit=80)
        )
        if candidate and _product_subject_safe(candidate):
            return candidate
    return ""


# P2: statement-shape signals for extractor classification (a statement of
# absence, difficulty, or manual burden describes the CURRENT problem).  The
# promotion guard itself never uses keywords - it uses the evidence role
# assigned here plus claim/evidence token coverage and authority.
_PROBLEM_SHAPE_RE = re.compile(
    r"\b(?:there is no|no easy way|not easy to|difficult to|hard to|cumbersome|"
    r"painful|fragile|error[- ]prone|time[- ]consuming|"
    r"does not (?:have|provide|offer|support|allow|include)|"
    r"do not (?:have|provide|offer|support|allow)|"
    r"lacks?|lack of|missing|cannot|can't|unable to|no way to|no option to|"
    r"not driven by|not supported|not available|no visibility|"
    r"manual(?:ly)?(?:\s+(?:process|step|workflow|approach|way))?)\b",
    re.IGNORECASE,
)
# Imperative language marks a requirement, not a problem statement, even when
# the sentence also describes a lack.
_IMPERATIVE_REQUIREMENT_RE = re.compile(
    r"\b(?:must|shall|should|required|needs? to|has to|have to|is expected to|"
    r"are expected to|provide|support|allow)\b",
    re.IGNORECASE,
)

# C2B-S1: claim-level sufficiency computation (deterministic, bounded rules
# over typed inputs - the single production sufficiency decision).

# Authority classes that can establish an expectation for a claim.  Anything
# else (historical, inferred, proposed, pending-review, unknown) may be
# evidence, but is not establishing for THIS claim on its own.
_ESTABLISHING_FACT_AUTHORITIES = frozenset(
    {
        AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
        AuthorityClass.CONFIRMED_PRODUCT_DECISION,
        AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
        AuthorityClass.SPECIFICATION_AUTHORITY,
        AuthorityClass.CUSTOMER_REQUEST,
        AuthorityClass.IMPLEMENTATION_CONFIRMED,
    }
)

# Implementation evidence establishes what the code does, not automatically
# what the product should do: a claim resting only on implementation evidence
# is capped at PARTIAL.
_IMPLEMENTATION_ONLY = frozenset({AuthorityClass.IMPLEMENTATION_CONFIRMED})

# Research status -> research completion sub-state (same vocabulary as the
# Skill S1 contract).
_RESEARCH_COMPLETION_MAP = {
    ResearchStatus.NOT_REQUIRED: "NOT_REQUIRED",
    ResearchStatus.NOT_APPLICABLE: "NOT_REQUIRED",
    ResearchStatus.PENDING: "PENDING",
    ResearchStatus.ANSWER_FOUND: "COMPLETED",
    ResearchStatus.PARTIAL: "PARTIAL",
    ResearchStatus.NOT_FOUND: "NOT_FOUND",
    ResearchStatus.SOURCE_UNAVAILABLE: "SOURCE_UNAVAILABLE",
    ResearchStatus.CONFLICTED: "CONFLICTED",
}

_RESEARCH_COMPLETION_RANK = {
    "PENDING": 6,
    "CONFLICTED": 5,
    "NOT_FOUND": 4,
    "SOURCE_UNAVAILABLE": 4,
    "PARTIAL": 3,
    "COMPLETED": 1,
    "NOT_REQUIRED": 0,
}

_CLARIFICATION_ESTABLISHING_CLASSES = frozenset(
    {
        ClarificationAnswerClass.EXPECTED_BEHAVIOR,
        ClarificationAnswerClass.PRODUCT_DECISION,
        ClarificationAnswerClass.SCOPE_VALUE,
    }
)

# C2B-C1: canonical coverage derivation - the single decision point mapping a
# runtime disposition to coverage class/priority/contract type.  Generic typed
# inputs only; no feature heuristics.
_C1_ACCEPTANCE_DISPOSITIONS = frozenset(
    {
        CoverageDisposition.ACCEPTANCE_CONTRACT,
        CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
    }
)
_C1_REGRESSION_DISPOSITIONS = frozenset(
    {
        CoverageDisposition.SEMANTIC_REGRESSION,
        CoverageDisposition.STRUCTURAL_REGRESSION,
        CoverageDisposition.REFERENCE_REGRESSION,
        CoverageDisposition.CROSS_MODE_REGRESSION,
        CoverageDisposition.CONFIGURATION_VARIANT,
        CoverageDisposition.NEGATIVE_BOUNDARY,
        CoverageDisposition.NFR_COVERAGE,
        CoverageDisposition.GENERATED_OUTPUT_VALIDATION,
        CoverageDisposition.LIFECYCLE_COVERAGE,
        CoverageDisposition.FAILURE_RECOVERY,
    }
)
_C1_INVESTIGATION_DISPOSITIONS = frozenset(
    {
        CoverageDisposition.IMPLEMENTATION_ORACLE,
        CoverageDisposition.TECHNICAL_NOTE,
        # Pending product/scope/design decisions and documented limitations
        # are investigation context: never acceptance coverage.
        CoverageDisposition.OPEN_QUESTION,
        CoverageDisposition.PRODUCT_SCOPE_QUESTION,
        CoverageDisposition.ENGINEERING_DESIGN_DECISION,
        CoverageDisposition.KNOWN_LIMITATION,
    }
)
# Dispositions intentionally outside the accepted coverage set: they stay
# visible in the trace with an exclusion reason and never reach the Writer.
_C1_EXCLUDED_DISPOSITIONS = frozenset(
    {
        CoverageDisposition.OUT_OF_SCOPE,
        CoverageDisposition.INVESTIGATED_AND_REJECTED,
        CoverageDisposition.UNSUPPORTED_INFERENCE,
    }
)

_C1_IMPACT_TEXT = {
    "P0": "Required to prove the primary accepted contract and prevent the "
    "reported regression.",
    "P1": "Materially related regression behavior for the accepted contract.",
    "SUPPORTING": "Supporting regression or investigation context.",
}


def _derive_c1(
    disposition: CoverageDisposition,
    *,
    has_direct_evidence: bool,
) -> tuple[str, str, str]:
    """Return (coverage_class, priority, acceptance_impact)."""

    if disposition in _C1_ACCEPTANCE_DISPOSITIONS:
        return "ACCEPTANCE", "P0", _C1_IMPACT_TEXT["P0"]
    if disposition == CoverageDisposition.ACCEPTANCE_TBD:
        # P3: acceptance-material but unresolved - stays acceptance-lane so it
        # is never silently demoted to regression/investigation.
        return (
            "ACCEPTANCE",
            "P0",
            "Acceptance-material; a bounded product decision remains "
            "unresolved (TBD).",
        )
    if disposition in _C1_REGRESSION_DISPOSITIONS:
        priority = "P1" if has_direct_evidence else "SUPPORTING"
        return "QE_REGRESSION", priority, _C1_IMPACT_TEXT[priority]
    if disposition in _C1_INVESTIGATION_DISPOSITIONS:
        return "INVESTIGATION", "SUPPORTING", _C1_IMPACT_TEXT["SUPPORTING"]
    if disposition in _C1_EXCLUDED_DISPOSITIONS:
        return (
            "",
            "EXCLUDED",
            "Explicitly outside the accepted coverage set; never promoted.",
        )
    return "", "", ""


def _derive_contract_type(
    disposition: CoverageDisposition, fact_types: set[ContractFactType]
) -> str:
    if (
        disposition == CoverageDisposition.NEGATIVE_BOUNDARY
        or ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS in fact_types
    ):
        return "NEGATIVE"
    if ContractFactType.COMPATIBILITY_REQUIREMENTS in fact_types:
        return "PRESERVATION"
    return "POSITIVE"


def _content_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.casefold()) if len(token) > 2}


def assess_claim_sufficiency(
    candidate: AcceptanceCandidate,
    *,
    facts_by_id: dict[str, ContractFact],
    dispositions_by_id: dict[str, CoverageDispositionRecord],
    research_by_question: dict[str, QuestionResearchRecord],
    classifications_by_disposition: dict[str, BehaviorClassificationRecord],
    evidence_currentness: dict[str, CurrentnessState],
    admitted_clarifications: list[HumanClarification],
) -> ClaimSufficiencyRecord:
    """Compute the single production sufficiency decision for one candidate.

    Bounded deterministic rules (spec C2B-S1 sections 4-8); no numeric
    confidence, no inference beyond the typed inputs.  Only ADMITTED
    clarifications participate - anything else is discarded defensively.
    """

    admitted_clarifications = [
        row
        for row in admitted_clarifications
        if row.status == ClarificationStatus.ADMITTED
    ]

    source_facts = [
        facts_by_id[fact_id]
        for fact_id in candidate.source_fact_ids
        if fact_id in facts_by_id
    ]
    linked_questions = sorted(
        {
            question_id
            for disposition_id in candidate.source_disposition_ids
            if disposition_id in dispositions_by_id
            for question_id in (
                dispositions_by_id[disposition_id].source_question_ids
            )
        }
    )
    research = [
        research_by_question[question_id]
        for question_id in linked_questions
        if question_id in research_by_question
    ]
    classifications = [
        classifications_by_disposition[disposition_id]
        for disposition_id in candidate.source_disposition_ids
        if disposition_id in classifications_by_disposition
    ]

    # Research completion: worst linked state wins.
    research_completion = "NOT_REQUIRED"
    for record in research:
        mapped = _RESEARCH_COMPLETION_MAP.get(record.research_status, "PENDING")
        if _RESEARCH_COMPLETION_RANK[mapped] > _RESEARCH_COMPLETION_RANK[
            research_completion
        ]:
            research_completion = mapped

    # Authority: an establishing clarification bound to a linked question
    # participates with its admitted authority; STALE/REJECTED never reach
    # this list (admission is upstream).
    clarification_lift = any(
        row.answer_classification in _CLARIFICATION_ESTABLISHING_CLASSES
        and (
            row.question_ref in linked_questions
            or f"clarification:{row.clarification_id}" in candidate.evidence_ids
        )
        for row in admitted_clarifications
    )
    problem_facts = [
        fact
        for fact in source_facts
        if fact.fact_type == ContractFactType.PROBLEM_STATEMENT
    ]

    def _establishes(fact: ContractFact) -> bool:
        if not fact.authoritative:
            return False
        if fact.authority_class not in _ESTABLISHING_FACT_AUTHORITIES:
            return False
        if fact.fact_type == ContractFactType.PROBLEM_STATEMENT:
            # A problem statement is establishing for the problem claim itself
            # (claim covered by the problem text), never for a claim extending
            # beyond it.
            return _content_tokens(candidate.statement) <= _content_tokens(
                fact.literal
            )
        return True

    establishing_facts = [fact for fact in source_facts if _establishes(fact)]
    authority_basis = ""
    if establishing_facts:
        authority_basis = max(
            (fact.authority_class.value for fact in establishing_facts),
        )
    elif clarification_lift:
        authority_basis = "HUMAN_CLARIFICATION"

    # Decision semantics: a research-derived candidate's establishing
    # evidence is the admitted research finding itself (validated at the
    # resume boundary: provenance, authority, lifecycle language), not a
    # contract fact.  The customer-stated desired behavior found by mandated
    # research is ticket-authority evidence; it establishes the claim the
    # same way an admitted human clarification does.  Research that is still
    # pending, conflicted, or found nothing never lifts.
    research_derived = any(
        dispositions_by_id[disposition_id].research_derived
        for disposition_id in candidate.source_disposition_ids
        if disposition_id in dispositions_by_id
    )
    research_lift = bool(
        research_derived
        and research_completion in {"COMPLETED", "PARTIAL"}
        and candidate.evidence_ids
    )
    if research_lift and not authority_basis:
        authority_basis = "ADMITTED_RESEARCH"

    # Currentness: only evidence that resolves into the bundle counts.
    currentness_values = {
        evidence_currentness[evidence_id]
        for fact in source_facts
        for evidence_id in fact.source_evidence_ids
        if evidence_id in evidence_currentness
    }
    if not currentness_values:
        currentness = "UNKNOWN"
    elif currentness_values <= {CurrentnessState.CURRENT}:
        currentness = "CURRENT"
    else:
        currentness = "STALE"

    contradictions: list[str] = []
    limitations: list[str] = []
    applicability = "APPLICABLE" if candidate.in_scope else "WRONG_APPLICABILITY"

    hard_insufficient: list[str] = []
    caps: list[str] = []
    conflicted = False

    if not candidate.in_scope:
        hard_insufficient.append("the claim is out of the established scope")
    if not source_facts and not clarification_lift and not research_lift:
        hard_insufficient.append("no evidence is bound to the claim")
    elif (
        not establishing_facts
        and not clarification_lift
        and not research_lift
    ):
        if problem_facts:
            hard_insufficient.append(
                "bound evidence establishes the problem, not a particular "
                "solution - the chosen solution needs its own establishing "
                "authority"
            )
        else:
            hard_insufficient.append(
                "bound evidence exists but none of it is establishing for this "
                "claim (observation/inference/historical authority only)"
            )
    elif problem_facts and not clarification_lift and not research_lift:
        # P2 guard: problem evidence plus unrelated establishing evidence must
        # not bleed into a claim whose behavior content nothing establishes.
        covered: set[str] = set()
        for fact in establishing_facts:
            covered |= _content_tokens(fact.literal)
        uncovered = _content_tokens(candidate.statement) - covered
        if uncovered:
            hard_insufficient.append(
                "the claim introduces behavior no establishing evidence covers "
                "- an established problem does not establish a particular "
                "solution"
            )
    if research_completion == "PENDING":
        hard_insufficient.append("mandatory research is still PENDING")
    if research_completion == "CONFLICTED":
        conflicted = True
        contradictions.append("research for a linked question is CONFLICTED")
    if research_completion in {"NOT_FOUND", "SOURCE_UNAVAILABLE"}:
        caps.append(
            "required research found no answer - NOT_FOUND is not proof of "
            "the opposite behavior"
        )
    if research_completion == "PARTIAL":
        caps.append("research is PARTIAL; only the established portion stands")
    if any(row.behavior_class == BehaviorChangeClass.CONFLICTED for row in classifications):
        conflicted = True
        contradictions.append("existing-vs-new classification is CONFLICTED")
    if any(row.behavior_class == BehaviorChangeClass.UNKNOWN for row in classifications):
        caps.append("existing-vs-new classification is UNKNOWN")
    if (
        establishing_facts
        and all(
            fact.authority_class in _IMPLEMENTATION_ONLY
            for fact in establishing_facts
        )
        and not clarification_lift
    ):
        caps.append(
            "implementation evidence establishes what code does, not "
            "automatically desired acceptance behavior"
        )
    if currentness == "STALE":
        caps.append(
            "stale evidence cannot establish a current-version-specific claim "
            "without compatibility evidence"
        )

    if conflicted:
        status = SufficiencyStatus.CONFLICTED
    elif hard_insufficient:
        status = SufficiencyStatus.INSUFFICIENT
    elif caps:
        status = SufficiencyStatus.PARTIAL
    else:
        status = SufficiencyStatus.SUFFICIENT

    # The established portion is exactly what the establishing evidence says -
    # never more than the claim, never invented.  For a research-lifted claim
    # the admitted research finding IS the portion, bounded by the claim.
    portion_literals = sorted({fact.literal for fact in establishing_facts})
    established_portion = ""
    if status == SufficiencyStatus.PARTIAL:
        established_portion = " / ".join(portion_literals)[:2000]
        if research_lift and not established_portion:
            established_portion = candidate.statement[:2000]

    reason_bits = []
    if status == SufficiencyStatus.SUFFICIENT:
        reason_bits.append(
            f"establishing evidence from {authority_basis or 'bound sources'}; "
            f"research {research_completion.lower()}; applicability "
            f"{applicability.lower()}; currentness {currentness.lower()}"
        )
    else:
        reason_bits.extend(hard_insufficient)
        reason_bits.extend(caps)
        reason_bits.extend(contradictions)

    return ClaimSufficiencyRecord(
        claim_ref=candidate.candidate_id,
        claim_text=candidate.statement[:2000],
        question_refs=linked_questions,
        coverage_refs=sorted(set(candidate.source_disposition_ids)),
        status=status,
        established_portion=established_portion,
        evidence_refs=sorted(set(candidate.evidence_ids)),
        research_refs=sorted({row.research_id for row in research}),
        authority_basis=authority_basis,
        applicability=applicability,
        currentness=currentness,
        research_completion=research_completion,
        contradictions=contradictions,
        limitations=limitations + caps,
        decision_reason="; ".join(reason_bits) or "no establishing evidence",
        claim_revision=stable_sha256({"claim": candidate.statement})[:12],
    )


_DITA_OT_CLARIFICATION_ANSWERS = {
    "on": DitaOtProcessingState.ON,
    "off": DitaOtProcessingState.OFF,
    "both": DitaOtProcessingState.BOTH,
    "not applicable": DitaOtProcessingState.NOT_APPLICABLE,
    "not_applicable": DitaOtProcessingState.NOT_APPLICABLE,
    "n/a": DitaOtProcessingState.NOT_APPLICABLE,
}


def _normalize_clarification_answer(answer: str) -> str:
    return re.sub(r"\s+", " ", str(answer or "").strip().casefold())


def _admit_scope_clarification(
    field: str, raw_clarifications: list[dict[str, Any]]
) -> HumanClarification | None:
    """Admission-lite for a scope-field clarification (runs before questions
    exist).  Returns the single admitted clarification or None; the full
    question-bound admission pass later re-derives the same verdict."""

    expected_revision = scope_question_revision(field)
    aliases = {field, scope_question_id(field)}
    candidates: list[HumanClarification] = []
    for raw in raw_clarifications:
        if not isinstance(raw, dict):
            continue
        try:
            row = HumanClarification.model_validate(raw)
        except Exception:
            continue
        if row.question_ref not in aliases:
            continue
        if row.question_revision != expected_revision:
            continue  # STALE - never silently rebind to a changed question
        if row.authority_role not in _CLARIFICATION_ESTABLISHING_AUTHORITIES:
            continue  # insufficient authority
        candidates.append(row)
    answers = {_normalize_clarification_answer(row.answer) for row in candidates}
    if len(candidates) != 1 or len(answers) != 1:
        return None  # none, or contradictory clarifications
    return candidates[0]

_CONTENT_LIFECYCLE_RE = re.compile(
    r"(?:\b(?:move|rename|delete)(?:d|s|ing)?\b.{0,30}"
    r"\b(?:asset|file|folder|topic|map|repository|content)\b|"
    r"\b(?:asset|file|folder|topic|map|repository|content)\b.{0,30}"
    r"\b(?:move|rename|delete)(?:d|s|ing)?\b)",
    re.IGNORECASE,
)

_IMPLEMENTATION_MECHANICS_RE = re.compile(
    r"(?:\b(?:fix|implementation|internal code|method|class|handler|worker|service)\b"
    r".{0,40}\b(?:use|uses|using|invoke|call|implement|store)\b|"
    r"\b(?:hashmap|concurrenthashmap|keyset pagination|custom index|"
    r"internal api version|framework status|incidental code constant)\b|"
    r"\b(?:implementation|engineering|code)\s+(?:detail|details|mechanic|mechanics|choice|choices)\b|"
    r"\b[A-Z][A-Za-z0-9_$]+\.[a-z][A-Za-z0-9_$]*\s*\()",
    re.IGNORECASE,
)

_REGRESSION_ONLY_RE = re.compile(
    r"\b(?:regression\s+(?:coverage|check|test|retest)|retest\s+only|"
    r"(?:qa|test|automation)\s+suite\s+(?:should\s+|must\s+)?"
    r"(?:continue\s+)?(?:cover|verify|validate|test|retest)(?:s|ed|ing)?|"
    r"automated\s+tests?\s+(?:should\s+|must\s+)?"
    r"(?:continue\s+to\s+)?(?:cover|verify|validate|test|retest)(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)

_NON_BEHAVIOR_CHANGE_RE = re.compile(
    r"\b(?:no|without)\s+(?:user[- ]visible|observable|product)\s+"
    r"behavio(?:u)?r\s+change\b|"
    r"\b(?:internal|code[- ]only|test[- ]only)\s+refactor(?:ing)?\b|"
    r"\brefactor(?:ing)?\s+only\b",
    re.IGNORECASE,
)

_SUMMARY_REFERENCE_RE = re.compile(r"(?:^|[.:$])(?:summary|title)$", re.IGNORECASE)

_DIMENSION_KEYWORDS: dict[SemanticDimension, tuple[str, ...]] = {
    SemanticDimension.GOVERNING_SEMANTICS: ("semantic", "specification", "defined"),
    SemanticDimension.CONTROLLING_ATTRIBUTES: ("attribute", "property", "flag"),
    SemanticDimension.GOVERNING_CONFIGURATION: (
        "config",
        "setting",
        "profile",
        "preset",
    ),
    SemanticDimension.DIRECT_CONSUMERS: ("consumer", "reader", "uses", "read"),
    SemanticDimension.SIBLING_CONSUMERS: ("sibling", "other consumer", "shared"),
    SemanticDimension.ALTERNATE_MECHANISMS: (
        "alternate",
        "alternative",
        "another mechanism",
    ),
    SemanticDimension.PARENT_CONTEXT: ("parent", "containing"),
    SemanticDimension.CHILD_CONTEXT: ("child", "nested"),
    SemanticDimension.HIERARCHY: ("hierarchy", "ancestor", "descendant"),
    SemanticDimension.SPECIALIZATIONS: ("specialization", "specialized", "bookmap"),
    SemanticDimension.REFERENCED_CONTENT: ("reference", "mapref", "topicref", "link"),
    SemanticDimension.NESTED_REFERENCED_CONTENT: ("nested map", "nested reference"),
    SemanticDimension.ALTERNATE_REPRESENTATION: (
        "alternate representation",
        "fallback title",
    ),
    SemanticDimension.FALLBACK: ("fallback", "raw name", "default behavior"),
    SemanticDimension.ABSENT_VALUE: ("missing", "absent", "not configured", "empty"),
    SemanticDimension.INVALID_VALUE: ("invalid", "unsupported", "malformed"),
    SemanticDimension.POSITIVE_STATE: ("enabled", "selected", "present", "success"),
    SemanticDimension.NEGATIVE_STATE: (
        "disabled",
        "not selected",
        "failure",
        "removed",
    ),
    SemanticDimension.LIFECYCLE: (
        "update",
        "delete",
        "move",
        "rename",
        "regenerate",
        "refresh",
    ),
    SemanticDimension.CROSS_SURFACE_SYNC: (
        "automatically",
        "without reload",
        "sync",
        "all views",
    ),
    # C1: value-centric families.  These keywords decide only whether supplied
    # evidence already resolves the dimension; they never define the dimension.
    SemanticDimension.VALUE_PROVENANCE: (
        "provenance",
        "comes from",
        "derived from",
        "populated from",
        "read from",
        "computed",
        "source of truth",
    ),
    SemanticDimension.VALUE_RESOLUTION_OR_INDIRECTION: (
        "resolved",
        "resolution",
        "indirect",
        "conref",
        "conkeyref",
        "keyref",
        "key scope",
        "reused content",
    ),
    # A bare "identity"/"uuid" token is ordinary AEM Guides vocabulary: every
    # asset carries a UUID, so matching it marked this dimension resolved from
    # incidental wording instead of from evidence about an identity change.
    # Only wording that denotes the change event itself may resolve it.
    SemanticDimension.IDENTITY_CHANGE: (
        "moved",
        "renamed",
        "relocated",
        "path change",
        "identity change",
        "uuid change",
        "re-parent",
    ),
    SemanticDimension.MUTATION_FRESHNESS: (
        "stale",
        "up to date",
        "recompute",
        "reindex",
        "cached",
        "after the source changes",
    ),
    SemanticDimension.BROKEN_RESOLUTION: (
        "unresolved",
        "broken",
        "missing target",
        "undefined key",
        "cannot be resolved",
        "dangling",
    ),
    SemanticDimension.DOWNSTREAM_PROCESSOR: ("processor", "transformer", "downstream"),
    SemanticDimension.GENERATED_OUTPUT: ("generated", "output", "artifact", "page"),
    SemanticDimension.PERSISTED_STATE: ("persist", "repository state", "stored", "cq:"),
    SemanticDimension.VERSION_APPLICABILITY: (
        "version",
        "upgrade",
        "backward compatible",
    ),
    SemanticDimension.DEPLOYMENT_APPLICABILITY: ("on-prem", "cloud", "deployment"),
    SemanticDimension.ROLE_PROFILE_APPLICABILITY: (
        "user",
        "role",
        "profile",
        "permission",
    ),
}

_QUESTION_TEXT: dict[SemanticDimension, str] = {
    SemanticDimension.GOVERNING_SEMANTICS: "What product or DITA rule governs {entity}?",
    SemanticDimension.CONTROLLING_ATTRIBUTES: "Which attributes control {entity}?",
    SemanticDimension.GOVERNING_CONFIGURATION: "Which configuration controls {entity}?",
    SemanticDimension.DIRECT_CONSUMERS: "Which consumers read or use {entity}?",
    SemanticDimension.SIBLING_CONSUMERS: "Which other consumers use the same source as {entity}?",
    SemanticDimension.ALTERNATE_MECHANISMS: "Does another supported mechanism provide {entity}?",
    SemanticDimension.PARENT_CONTEXT: "Can {entity} occur in a parent context?",
    SemanticDimension.CHILD_CONTEXT: "Can {entity} occur under child or nested content?",
    SemanticDimension.HIERARCHY: "How does hierarchy affect {entity}?",
    SemanticDimension.SPECIALIZATIONS: "Are specialized forms handled by the same path as {entity}?",
    SemanticDimension.REFERENCED_CONTENT: "Can referenced content reach {entity}?",
    SemanticDimension.NESTED_REFERENCED_CONTENT: "Can nested referenced content reach {entity}?",
    SemanticDimension.ALTERNATE_REPRESENTATION: "Is there another representation of {entity}?",
    SemanticDimension.VALUE_PROVENANCE: "Where does the value shown for {entity} come from?",
    SemanticDimension.VALUE_RESOLUTION_OR_INDIRECTION: "Can the value for {entity} be resolved indirectly through referenced or reused content?",
    SemanticDimension.IDENTITY_CHANGE: "What happens to the stored state for {entity} when the underlying item is moved or renamed?",
    SemanticDimension.MUTATION_FRESHNESS: "Does {entity} read an updated value after its source changes, or can an out-of-date value remain?",
    SemanticDimension.BROKEN_RESOLUTION: "What is shown for {entity} when the reference cannot be resolved?",
    SemanticDimension.FALLBACK: "What fallback is used for {entity}?",
    SemanticDimension.ABSENT_VALUE: "What happens when the value for {entity} is absent?",
    SemanticDimension.INVALID_VALUE: "What happens when the value for {entity} is invalid?",
    SemanticDimension.POSITIVE_STATE: "What is the expected enabled state for {entity}?",
    SemanticDimension.NEGATIVE_STATE: "What is the expected disabled or failure state for {entity}?",
    SemanticDimension.LIFECYCLE: "Which lifecycle operations affect {entity}?",
    SemanticDimension.CROSS_SURFACE_SYNC: "Which surfaces stay synchronized for {entity}, and which ones can show a different value?",
    SemanticDimension.DOWNSTREAM_PROCESSOR: "Which downstream processor consumes {entity}?",
    SemanticDimension.GENERATED_OUTPUT: "Which generated output proves {entity} is correct?",
    SemanticDimension.PERSISTED_STATE: "Which persisted state is written or read for {entity}?",
    SemanticDimension.VERSION_APPLICABILITY: "Which product versions support {entity}?",
    SemanticDimension.DEPLOYMENT_APPLICABILITY: "Which deployment modes support {entity}?",
    SemanticDimension.ROLE_PROFILE_APPLICABILITY: "Is {entity} user, role, or profile specific?",
}


# C1 behavioral coverage expansion.
#
# A requirement is described by what it *does* (a value is displayed, an order
# is defined, an identity is referenced), never by the product feature it names.
# These signals are ordinary requirement-shape English so the same table works
# for an ordering ticket, a reference-resolution ticket, and a configuration
# ticket alike.  Product vocabulary stays in `_DIMENSION_KEYWORDS`, which only
# decides whether supplied evidence already resolves a dimension.
_EXPANSION_TRIGGER_SIGNALS: dict[CoverageExpansionTrigger, tuple[str, ...]] = {
    CoverageExpansionTrigger.DISPLAYED_VALUE: (
        "display",
        "shown",
        "show",
        "listed",
        "column",
        "label",
        "title",
        "visible",
    ),
    CoverageExpansionTrigger.EXPORTED_VALUE: (
        "export",
        "download",
        "report",
        "generated file",
        "csv",
    ),
    CoverageExpansionTrigger.ORDERING_RULE: (
        "order",
        "sort",
        "sequence",
        "position",
        "hierarchy",
    ),
    CoverageExpansionTrigger.COMPARED_OR_FILTERED_VALUE: (
        "filter",
        "search",
        "compare",
        "match",
        "group",
    ),
    CoverageExpansionTrigger.PERSISTED_VALUE: (
        "persist",
        "stored",
        "saved",
        "metadata",
        "property",
    ),
    CoverageExpansionTrigger.RESOLVED_REFERENCE: (
        "reference",
        "referenced",
        "resolve",
        "resolved",
        "reuse",
        "reused",
        "link",
    ),
    CoverageExpansionTrigger.IDENTITY_REFERENCE: (
        "move",
        "moved",
        "rename",
        "renamed",
        "delete",
        "deleted",
        "path",
    ),
    CoverageExpansionTrigger.STATE_TRANSITION: (
        "state",
        "status",
        "transition",
        "enable",
        "disable",
    ),
    CoverageExpansionTrigger.CONFIGURATION_DEPENDENCY: (
        "configuration",
        "setting",
        "preset",
        "profile",
        "flag",
    ),
}

_EXPANSION_TRIGGER_AXES: dict[
    CoverageExpansionTrigger, tuple[CoverageExpansionAxis, ...]
] = {
    CoverageExpansionTrigger.DISPLAYED_VALUE: (
        CoverageExpansionAxis.VALUE_PROVENANCE,
        CoverageExpansionAxis.FALLBACK_AND_ABSENCE,
        CoverageExpansionAxis.VALUE_RESOLUTION_OR_INDIRECTION,
        CoverageExpansionAxis.MUTATION_AND_FRESHNESS,
    ),
    CoverageExpansionTrigger.EXPORTED_VALUE: (
        CoverageExpansionAxis.VALUE_PROVENANCE,
        CoverageExpansionAxis.CONSUMER_SURFACE_PARITY,
        CoverageExpansionAxis.FALLBACK_AND_ABSENCE,
    ),
    CoverageExpansionTrigger.ORDERING_RULE: (
        CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE,
        CoverageExpansionAxis.CONSUMER_SURFACE_PARITY,
        CoverageExpansionAxis.CONTEXT_AND_SCOPE,
        CoverageExpansionAxis.MUTATION_AND_FRESHNESS,
    ),
    CoverageExpansionTrigger.COMPARED_OR_FILTERED_VALUE: (
        CoverageExpansionAxis.VALUE_PROVENANCE,
        CoverageExpansionAxis.FALLBACK_AND_ABSENCE,
        CoverageExpansionAxis.CONSUMER_SURFACE_PARITY,
    ),
    CoverageExpansionTrigger.PERSISTED_VALUE: (
        CoverageExpansionAxis.VALUE_PROVENANCE,
        CoverageExpansionAxis.MUTATION_AND_FRESHNESS,
        CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE,
    ),
    CoverageExpansionTrigger.RESOLVED_REFERENCE: (
        CoverageExpansionAxis.VALUE_RESOLUTION_OR_INDIRECTION,
        CoverageExpansionAxis.CONTEXT_AND_SCOPE,
        CoverageExpansionAxis.NEGATIVE_AND_BROKEN_RESOLUTION,
        CoverageExpansionAxis.MUTATION_AND_FRESHNESS,
    ),
    CoverageExpansionTrigger.IDENTITY_REFERENCE: (
        CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE,
        CoverageExpansionAxis.NEGATIVE_AND_BROKEN_RESOLUTION,
        CoverageExpansionAxis.MUTATION_AND_FRESHNESS,
    ),
    CoverageExpansionTrigger.MULTIPLE_CONSUMER_SURFACES: (
        CoverageExpansionAxis.CONSUMER_SURFACE_PARITY,
        CoverageExpansionAxis.VALUE_PROVENANCE,
    ),
    CoverageExpansionTrigger.STATE_TRANSITION: (
        CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE,
        CoverageExpansionAxis.FALLBACK_AND_ABSENCE,
    ),
    CoverageExpansionTrigger.CONFIGURATION_DEPENDENCY: (
        CoverageExpansionAxis.CONTEXT_AND_SCOPE,
        CoverageExpansionAxis.FALLBACK_AND_ABSENCE,
        CoverageExpansionAxis.VALUE_PROVENANCE,
    ),
}

_EXPANSION_AXIS_DIMENSIONS: dict[
    CoverageExpansionAxis, tuple[SemanticDimension, ...]
] = {
    CoverageExpansionAxis.VALUE_PROVENANCE: (SemanticDimension.VALUE_PROVENANCE,),
    CoverageExpansionAxis.FALLBACK_AND_ABSENCE: (
        SemanticDimension.FALLBACK,
        SemanticDimension.ABSENT_VALUE,
    ),
    CoverageExpansionAxis.VALUE_RESOLUTION_OR_INDIRECTION: (
        SemanticDimension.VALUE_RESOLUTION_OR_INDIRECTION,
        SemanticDimension.REFERENCED_CONTENT,
        SemanticDimension.NESTED_REFERENCED_CONTENT,
    ),
    # Physical identity change and ordinary lifecycle state are separate
    # contracts: moving an asset is not the same product behavior as reordering
    # an entry, so they are never collapsed into one dimension.
    CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE: (
        SemanticDimension.LIFECYCLE,
        SemanticDimension.IDENTITY_CHANGE,
    ),
    CoverageExpansionAxis.CONTEXT_AND_SCOPE: (
        SemanticDimension.PARENT_CONTEXT,
        SemanticDimension.CHILD_CONTEXT,
        SemanticDimension.HIERARCHY,
    ),
    CoverageExpansionAxis.CONSUMER_SURFACE_PARITY: (
        SemanticDimension.CROSS_SURFACE_SYNC,
        SemanticDimension.DIRECT_CONSUMERS,
        SemanticDimension.SIBLING_CONSUMERS,
        SemanticDimension.ALTERNATE_REPRESENTATION,
    ),
    CoverageExpansionAxis.MUTATION_AND_FRESHNESS: (
        SemanticDimension.MUTATION_FRESHNESS,
        SemanticDimension.CROSS_SURFACE_SYNC,
    ),
    CoverageExpansionAxis.NEGATIVE_AND_BROKEN_RESOLUTION: (
        SemanticDimension.BROKEN_RESOLUTION,
        SemanticDimension.INVALID_VALUE,
        SemanticDimension.NEGATIVE_STATE,
    ),
}

_EXPANSION_AXIS_QUESTION: dict[CoverageExpansionAxis, str] = {
    CoverageExpansionAxis.VALUE_PROVENANCE: (
        "Where does the value shown for {subject} come from, and does every "
        "supported way of setting it behave the same?"
    ),
    CoverageExpansionAxis.FALLBACK_AND_ABSENCE: (
        "What is shown for {subject} when the expected value is missing or empty?"
    ),
    CoverageExpansionAxis.VALUE_RESOLUTION_OR_INDIRECTION: (
        "Can the value for {subject} be supplied indirectly through referenced "
        "or reused content, and is it resolved the same way?"
    ),
    CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE: (
        "How does {subject} behave after the underlying item is added, moved, "
        "renamed, reordered, or removed?"
    ),
    CoverageExpansionAxis.CONTEXT_AND_SCOPE: (
        "Does the behavior of {subject} change with the surrounding context, "
        "scope, or configuration it is used in?"
    ),
    CoverageExpansionAxis.CONSUMER_SURFACE_PARITY: (
        "Do all supported surfaces present the same set, order, and resolved "
        "value for {subject}?"
    ),
    CoverageExpansionAxis.MUTATION_AND_FRESHNESS: (
        "Does {subject} stay up to date after its source value changes?"
    ),
    CoverageExpansionAxis.NEGATIVE_AND_BROKEN_RESOLUTION: (
        "What does {subject} show when the expected source or reference cannot "
        "be resolved?"
    ),
}

_EXPANSION_AXIS_RATIONALE: dict[CoverageExpansionAxis, str] = {
    CoverageExpansionAxis.VALUE_PROVENANCE: (
        "A named value is not atomic until every channel that can set it is known."
    ),
    CoverageExpansionAxis.FALLBACK_AND_ABSENCE: (
        "Absence behavior is a separate product contract from the populated case."
    ),
    CoverageExpansionAxis.VALUE_RESOLUTION_OR_INDIRECTION: (
        "An indirectly supplied value can reach the same surface through a "
        "different resolution path."
    ),
    CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE: (
        "Changing an item's identity or lifecycle state can regress behavior "
        "that looked correct at creation time."
    ),
    CoverageExpansionAxis.CONTEXT_AND_SCOPE: (
        "The same value can behave differently depending on the context it is "
        "resolved in."
    ),
    CoverageExpansionAxis.CONSUMER_SURFACE_PARITY: (
        "Every surface that presents the behavior can diverge from the others."
    ),
    CoverageExpansionAxis.MUTATION_AND_FRESHNESS: (
        "A value that is correct once can go out of date after its source changes."
    ),
    CoverageExpansionAxis.NEGATIVE_AND_BROKEN_RESOLUTION: (
        "Broken and invalid inputs are a distinct contract from the positive path."
    ),
}


# Each dependency kind is decided by exactly one discovery axis, so a record is
# total by construction and an axis can never silently cover two dependencies.
_DEPENDENCY_KIND_AXIS: dict[SemanticDependencyKind, CoverageExpansionAxis] = {
    SemanticDependencyKind.PROVENANCE: CoverageExpansionAxis.VALUE_PROVENANCE,
    SemanticDependencyKind.PRECEDENCE_AND_FALLBACK: (
        CoverageExpansionAxis.FALLBACK_AND_ABSENCE
    ),
    SemanticDependencyKind.INDIRECTION_AND_RESOLUTION: (
        CoverageExpansionAxis.VALUE_RESOLUTION_OR_INDIRECTION
    ),
    SemanticDependencyKind.CONTEXT_DEPENDENCY: (
        CoverageExpansionAxis.CONTEXT_AND_SCOPE
    ),
    SemanticDependencyKind.IDENTITY: CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE,
    SemanticDependencyKind.LIFECYCLE_MUTATION: (
        CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE
    ),
    SemanticDependencyKind.FRESHNESS_AND_STALENESS: (
        CoverageExpansionAxis.MUTATION_AND_FRESHNESS
    ),
    SemanticDependencyKind.CONSUMER_PARITY: (
        CoverageExpansionAxis.CONSUMER_SURFACE_PARITY
    ),
    SemanticDependencyKind.UNRESOLVED_OR_NEGATIVE_BRANCH: (
        CoverageExpansionAxis.NEGATIVE_AND_BROKEN_RESOLUTION
    ),
}

_DEPENDENCY_KIND_RESEARCH_REASON: dict[SemanticDependencyKind, str] = {
    SemanticDependencyKind.PROVENANCE: (
        "Discovery raised this dependency; the channels that can set the value "
        "must be established from evidence before coverage decides it."
    ),
    SemanticDependencyKind.PRECEDENCE_AND_FALLBACK: (
        "Discovery raised this dependency; the precedence order and the value "
        "used when the preferred source is absent must be established."
    ),
    SemanticDependencyKind.INDIRECTION_AND_RESOLUTION: (
        "Discovery raised this dependency; whether the value can arrive through "
        "an indirect resolution path must be established."
    ),
    SemanticDependencyKind.CONTEXT_DEPENDENCY: (
        "Discovery raised this dependency; whether the resolved value depends "
        "on the context it is read in must be established."
    ),
    SemanticDependencyKind.IDENTITY: (
        "Discovery raised this dependency; whether the behavior survives a "
        "change to the underlying item's identity must be established."
    ),
    SemanticDependencyKind.LIFECYCLE_MUTATION: (
        "Discovery raised this dependency; the lifecycle operations that can "
        "change the stored state must be established."
    ),
    SemanticDependencyKind.FRESHNESS_AND_STALENESS: (
        "Discovery raised this dependency; whether an out-of-date value can "
        "survive an upstream change must be established."
    ),
    SemanticDependencyKind.CONSUMER_PARITY: (
        "Discovery raised this dependency; whether every consuming surface "
        "reports the same behavior must be established."
    ),
    SemanticDependencyKind.UNRESOLVED_OR_NEGATIVE_BRANCH: (
        "Discovery raised this dependency; the behavior when the value is "
        "invalid or cannot be resolved must be established."
    ),
}

_DEPENDENCY_KIND_NOT_APPLICABLE_REASON: dict[SemanticDependencyKind, str] = {
    SemanticDependencyKind.PROVENANCE: (
        "No evidence describes this subject carrying a value that is displayed, "
        "exported, ordered, compared or persisted, so it has no provenance to "
        "disposition."
    ),
    SemanticDependencyKind.PRECEDENCE_AND_FALLBACK: (
        "No evidence describes a preferred source that can be absent for this "
        "subject, so no precedence or fallback rule applies."
    ),
    SemanticDependencyKind.INDIRECTION_AND_RESOLUTION: (
        "No evidence describes this subject resolving a reference, so there is "
        "no indirect resolution path to disposition."
    ),
    SemanticDependencyKind.CONTEXT_DEPENDENCY: (
        "No evidence describes this subject being read in more than one "
        "context or scope, so context cannot change its behavior."
    ),
    SemanticDependencyKind.IDENTITY: (
        "No evidence describes this subject referencing an item by identity, "
        "so an identity change cannot affect it."
    ),
    SemanticDependencyKind.LIFECYCLE_MUTATION: (
        "No evidence describes a lifecycle operation acting on this subject's "
        "stored state, so no lifecycle mutation applies."
    ),
    SemanticDependencyKind.FRESHNESS_AND_STALENESS: (
        "No evidence describes this subject reading a value that another "
        "source can change afterwards, so it cannot go stale."
    ),
    SemanticDependencyKind.CONSUMER_PARITY: (
        "Evidence describes a single consuming surface for this subject, so "
        "there is no second surface that can diverge."
    ),
    SemanticDependencyKind.UNRESOLVED_OR_NEGATIVE_BRANCH: (
        "No evidence describes this subject accepting an input that can be "
        "invalid or unresolvable, so it has no negative branch."
    ),
}


def _flatten_strings(value: Any, path: str = "$") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            rows.extend(_flatten_strings(child, f"{path}.{key}"))
    elif isinstance(value, (list, tuple, set)):
        for index, child in enumerate(value):
            rows.extend(_flatten_strings(child, f"{path}[{index}]"))
    elif value is not None and not isinstance(value, bool):
        text = str(value).strip()
        if text:
            rows.append((path, text))
    return rows


_MAX_CODE_ENTITY_CHARS = 120
_CODE_FILE_SUFFIX_RE = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,9}$")
_CODE_SYMBOL_RE = re.compile(
    r"^[A-Za-z_$][A-Za-z0-9_$]*(?:[.:#][A-Za-z_$][A-Za-z0-9_$]*)*$"
)
_CAMEL_HUMP_RE = re.compile(r"[a-z0-9][A-Z]")
_NON_PATH_CHARS = frozenset("\"'`{}()[];,=<>|*?")


def _is_code_entity_literal(value: str) -> bool:
    """Return True when a literal names a file or code symbol rather than prose.

    Implementation evidence nests snippets, matched source lines, and test
    titles beneath keys such as ``matches`` or ``file``.  ``_flatten_strings``
    propagates an ancestor key into every descendant path, so an admitting path
    says nothing about the leaf itself.  A changed *entity* is therefore
    identified by the shape of its own value.
    """

    text = value.strip()
    if not text or len(text) > _MAX_CODE_ENTITY_CHARS:
        return False
    if any(char in text for char in "\r\n\t"):
        return False

    if "/" in text or "\\" in text:
        if _NON_PATH_CHARS & set(text):
            return False
        tail = re.split(r"[\\/]", text)[-1].strip()
        return bool(tail) and bool(_CODE_FILE_SUFFIX_RE.search(tail))

    if not _CODE_SYMBOL_RE.match(text):
        return False
    if any(separator in text for separator in "._:#$"):
        return True
    # A bare single token is only an entity when its own casing or digits mark
    # it as an identifier; otherwise it is an ordinary word such as "model".
    return bool(_CAMEL_HUMP_RE.search(text)) or any(char.isdigit() for char in text)


def _words(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", value.casefold())
        if token
        not in {
            "what",
            "which",
            "when",
            "where",
            "does",
            "this",
            "that",
            "with",
            "from",
            "must",
            "should",
            "expected",
        }
    }


def _record_text(record: EvidenceRecord) -> str:
    if is_github_implementation_result_record(record):
        # A verification result answers one bound implementation question.  It
        # must not be re-read as broad issue/domain/semantic discovery prose.
        return ""
    return "\n".join(text for _, text in _flatten_strings(record.content))


def _positive_scope_clauses(values: list[str]) -> list[str]:
    """Remove explicit scope exclusions before routing or NFR activation."""

    clauses: list[str] = []
    for value in values:
        for clause in re.split(r"(?:\r?\n|;|(?<=[.!?])\s+)", value):
            normalized = clause.strip()
            if normalized and not _OUT_OF_SCOPE_CLAUSE_RE.search(normalized):
                clauses.append(normalized)
    return clauses


def _semantic_text_units(values: list[str]) -> tuple[str, ...]:
    """Return stable, record-bounded text units for semantic signal checks.

    Context-sensitive regular expressions must never run across independently
    sourced facts.  Fact IDs contain evidence lineage (including tenant-bound
    IDs), so their sort order is not a semantic input.  Keeping every value in
    its own unit makes the result independent of that incidental ordering while
    still allowing order-insensitive token checks.
    """

    return tuple(
        sorted(
            {
                re.sub(r"\s+", " ", str(value)).strip().casefold()
                for value in values
                if str(value).strip()
            }
        )
    )


_SCOPE_PRIMARY_PATH_LEAVES: dict[ContractFactType, frozenset[str]] = {
    ContractFactType.PRIMARY_PRODUCT_AREA: frozenset(
        {"primary_product_area", "primary_component"}
    ),
    ContractFactType.PRIMARY_OUTPUT_TYPE: frozenset({"primary_output_type"}),
    ContractFactType.PRESET_TYPE: frozenset({"primary_preset_type"}),
}

_SCOPE_DIRECT_PATH_LEAVES: dict[ContractFactType, frozenset[str]] = {
    ContractFactType.PRIMARY_PRODUCT_AREA: frozenset(
        {"product_area", "component", "components"}
    ),
    ContractFactType.PRIMARY_OUTPUT_TYPE: frozenset(
        {"output", "outputs", "output_type", "output_types"}
    ),
    ContractFactType.PRESET_TYPE: frozenset(
        {"preset", "presets", "preset_type", "output_preset", "output_presets"}
    ),
}

_SCOPE_UNRESOLVED_FIELD: dict[ContractFactType, str] = {
    ContractFactType.PRIMARY_PRODUCT_AREA: "PRIMARY_PRODUCT_AREA",
    ContractFactType.PRIMARY_OUTPUT_TYPE: "PRIMARY_OUTPUT_TYPE",
    ContractFactType.PRESET_TYPE: "PRIMARY_PRESET_TYPE",
}


def _scope_source_path(source_reference: str) -> str:
    """Return only the semantic JSON path, excluding provider identity.

    Evidence references and fact IDs may contain tenant-bound provenance.  The
    flattened JSON path appended by contract extraction is stable for the same
    semantic input and is the only part allowed to influence scope precedence.
    """

    marker = source_reference.rfind(":$")
    return source_reference[marker + 1 :] if marker >= 0 else ""


def _scope_source_priority(fact: ContractFact) -> tuple[int, int]:
    """Rank root scope fields above nested supporting material."""

    path = _scope_source_path(fact.source_reference)
    segments = tuple(
        match.group(1).casefold().replace("-", "_")
        for match in re.finditer(r"(?:^\$|\.)([a-zA-Z0-9_-]+)(?:\[\d+\])?", path)
    )
    if not segments:
        return (0, 0)
    leaf = segments[-1]
    primary = leaf in _SCOPE_PRIMARY_PATH_LEAVES.get(fact.fact_type, ())
    direct = primary or leaf in _SCOPE_DIRECT_PATH_LEAVES.get(
        fact.fact_type, ()
    )
    top_level = len(segments) == 1
    if top_level and primary:
        source_tier = 4
    elif top_level and direct:
        source_tier = 3
    elif primary:
        source_tier = 2
    elif direct:
        source_tier = 1
    else:
        source_tier = 0
    return (source_tier, -len(segments))


def _scope_semantic_value(fact: ContractFact) -> str:
    value = fact.normalized_value
    return str(value if value not in (None, "") else fact.literal).strip()


def _scope_semantic_key(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", value.casefold()).strip()


def _units_contain_any(
    units: tuple[str, ...], signals: tuple[str, ...]
) -> bool:
    return any(signal in unit for unit in units for signal in signals)


def _units_match(units: tuple[str, ...], pattern: re.Pattern[str]) -> bool:
    return any(pattern.search(unit) is not None for unit in units)


def _bounded_behavior_subject(value: str, *, limit: int = 240) -> str:
    """Keep a source-authored behavior label readable and deterministically bounded."""

    normalized = re.sub(r"\s+", " ", value).strip()
    normalized = re.sub(
        r"^[*#\s]*(?:expected\s+behavio(?:u)?r|issue|summary)\s*[:\-]\s*",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    if len(normalized) <= limit:
        return normalized
    clipped = normalized[: limit + 1].rsplit(" ", 1)[0].rstrip(" .,:;-")
    return f"{clipped}…"


def _behavior_reference_rank(source_reference: str) -> int:
    normalized = source_reference.casefold()
    if normalized.endswith(":$.summary"):
        return 0
    if normalized.endswith(".summary"):
        return 1
    if normalized.endswith(".title"):
        return 2
    return 3


def _material_behavior_fact(
    facts: ContractFactSet,
    *,
    allowed_evidence_ids: set[str] | None = None,
) -> ContractFact | None:
    """Select one current-issue behavior signal without using feature taxonomies."""

    excluded = {
        (fact.literal.casefold(), tuple(fact.source_evidence_ids))
        for fact in facts.facts
        if fact.fact_type == ContractFactType.OUT_OF_SCOPE
    }
    candidates: list[ContractFact] = []
    for fact in facts.facts:
        if allowed_evidence_ids is not None and not allowed_evidence_ids.intersection(
            fact.source_evidence_ids
        ):
            continue
        is_summary = bool(_SUMMARY_REFERENCE_RE.search(fact.source_reference))
        if (
            fact.fact_type != ContractFactType.DIRECT_EXPECTED_BEHAVIOR
            and not is_summary
        ):
            continue
        literal = fact.literal.strip()
        if len(literal) < 8:
            continue
        if (literal.casefold(), tuple(fact.source_evidence_ids)) in excluded:
            continue
        if (
            _OUT_OF_SCOPE_CLAUSE_RE.search(literal)
            or _NON_BEHAVIOR_CHANGE_RE.search(literal)
            or _REGRESSION_ONLY_RE.search(literal)
        ):
            continue
        candidates.append(fact)
    if not candidates:
        return None
    candidates.sort(
        key=lambda fact: (
            _behavior_reference_rank(fact.source_reference),
            0
            if re.search(
                r"\b(?:expected|should|must|incorrect|fails?|broken)\b",
                fact.literal,
                re.IGNORECASE,
            )
            else 1,
            len(fact.literal),
            fact.fact_id,
        )
    )
    return candidates[0]


def _scale_detection_text(text: str) -> str:
    """Remove identifier digits that cannot establish workload cardinality."""

    text = re.sub(r"\b[A-Z][A-Z0-9]+-\d+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?:[A-Za-z]:[\\/]|/)(?:[^\s,;]+[\\/])*[^\s,;]*",
        " ",
        text,
    )
    return re.sub(
        r"\b(?:line|offset|port|status|http)\s*[:#-]?\s*\d+\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )


def _contains_domain_signal(text: str, signal: str) -> bool:
    normalized = signal.strip().casefold()
    if normalized in {"api", "apis"}:
        return bool(re.search(r"\bapis?\b", text))
    return normalized in text


def _contract_literals(path: str, literal: str) -> list[str]:
    """Split prose into source-exact clauses without paraphrasing it."""

    if any(
        token in path.casefold() for token in ("summary", "title", "label", "status")
    ):
        return [literal]
    parts = re.split(
        r"(?:\r?\n|\s*[;•]\s*|(?<=[.!?])\s+|"
        r"(?=\b(?:In scope|Out of scope|Enable DITA-OT Processing|Output preset type)\s*:))",
        literal,
        flags=re.IGNORECASE,
    )
    cleaned = [part.strip(" \t-*\u2022") for part in parts if part.strip(" \t-*\u2022")]
    return cleaned or [literal]


# A pasted stack trace / log dump is diagnostic noise, not an acceptance-relevant
# contract fact. Left intact it (a) mints junk "facts" out of individual frames and
# (b) can overflow bounded downstream fields (MissingQuestion behavior/oracle), which
# previously failed a whole run with HTTP 500. We keep the informative header lines
# ("<Exception>: message", "Caused by: ...") and drop the frame lines.
_STACK_FRAME_INLINE_RE = re.compile(r"\bat\s+[\w$.<>/]+\([^)]*\)")
_STACK_MORE_RE = re.compile(r"\.\.\.\s*\d+\s+more\b", re.IGNORECASE)
_STACK_SIGNATURE_RE = re.compile(
    r"(\bat\s+[\w$.<>/]+\([^)]*\)|Caused by:|\b[\w.]+(?:Exception|Error)\b\s*:)",
)


def _reduce_stack_frames(text: str) -> str:
    """Collapse a pasted stack trace to its header lines, leaving prose intact.

    No-op unless a stack-trace signature is present, so ordinary contract text is
    never altered.
    """

    if not text or not _STACK_SIGNATURE_RE.search(text):
        return text
    # Drop inline "at pkg.Class.method(File.java:NN)" frames and "... N more".
    reduced = _STACK_FRAME_INLINE_RE.sub(" ", text)
    reduced = _STACK_MORE_RE.sub(" ", reduced)
    # Drop any residual frame-only lines and collapse whitespace runs.
    kept_lines = [
        line
        for line in reduced.splitlines()
        if line.strip() and not re.fullmatch(r"\s*at\s+[\w$.<>/]+.*", line)
    ]
    reduced = "\n".join(kept_lines) if kept_lines else reduced
    reduced = re.sub(r"[ \t]{2,}", " ", reduced).strip()
    return reduced or text


def _is_contract_metadata(path: str, literal: str) -> bool:
    """Exclude transport/provenance identifiers before contract classification."""

    normalized_path = path.casefold().replace("[", ".").replace("]", "")
    leaf = normalized_path.rsplit(".", 1)[-1]
    if re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", literal.strip(), re.IGNORECASE):
        return True
    if leaf in {
        "id",
        "issue_key",
        "jira_key",
        "source",
        "lookup_source",
        "source_hash",
        "source_url",
        "canonical_url",
        "chunk_id",
        "snapshot_id",
        "fingerprint",
        "schema_version",
        "line",
        "line_number",
        "commit_sha",
        "head_sha",
        "post_sync_sha",
        "created",
        "updated",
        "timestamp",
        # R2: linked-issue linkage metadata is reference structure, never a
        # behavior fact ("In Progress" from a linked ticket's status is not a
        # status contract of the current ticket).
        "link_type",
        "direction",
        "target_status",
        "target_key",
        "target_summary",
        "mime_type",
        "size",
        "author",
    }:
        return True
    return any(
        marker in normalized_path
        for marker in (
            ".evidence_snapshot.",
            ".source_manifest.",
            ".query_runtime.",
            ".generation.id",
        )
    )


# Terminology facts exist to clarify the TICKET AUTHOR's words.  Retrieved
# documentation, specs, code, diffs, and automation text are evidence, not a
# human asking anything - quoted sentences inside them must never become
# "human term" clarification questions.
_TICKET_UNDERSTANDING_AUTHORITIES = frozenset(
    {
        AuthorityClass.CUSTOMER_REQUEST,
        AuthorityClass.USER_EXPECTATION,
        AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
        AuthorityClass.CONFIRMED_PRODUCT_DECISION,
    }
)

_NON_HUMAN_TERMINOLOGY_SOURCES = frozenset(
    {
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        EvidenceSourceType.DITA_SPECIFICATION,
        EvidenceSourceType.DITA_OT_DOCUMENTATION,
        EvidenceSourceType.AEM_ASSETS_PLATFORM_DOCUMENTATION,
        EvidenceSourceType.CURRENT_CODE,
        EvidenceSourceType.CURRENT_PR,
        EvidenceSourceType.EXISTING_AUTOMATION,
        EvidenceSourceType.HISTORICAL_JIRA,
        EvidenceSourceType.EVIDENCE_GRAPH_LEAF,
        EvidenceSourceType.MODEL_INFERENCE,
        EvidenceSourceType.IMPLEMENTATION_DIFF,
        EvidenceSourceType.CODE_DIFF,
        EvidenceSourceType.BENCHMARK_PUBLIC_INPUT,
        EvidenceSourceType.CODEX_MANIFEST,
        EvidenceSourceType.UNKNOWN,
    }
)

_TERMINOLOGY_FACT_TYPES = frozenset(
    {
        ContractFactType.HUMAN_TERMINOLOGY,
        ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED,
    }
)

_SCALAR_SCOPE_FACT_TYPES = frozenset(
    {
        ContractFactType.PRIMARY_PRODUCT_AREA,
        ContractFactType.PRIMARY_OUTPUT_TYPE,
        ContractFactType.PRESET_TYPE,
        ContractFactType.DITA_OT_PROCESSING_STATE,
        ContractFactType.DEPLOYMENT_MODE,
        ContractFactType.PRODUCT_VERSION,
        ContractFactType.FEATURE_STATE,
    }
)


# D1-a: a requested capability is still a requirement when the reporter phrases
# it politely as a question ("Could we add a where-used for each topic?").
# Classifying it as a human open question on the strength of the "?" alone
# removes a requested product capability from the acceptance contract entirely.
# These ask the PRODUCT to do something; a genuine open question asks the TEAM
# to decide something.
_REQUESTED_CAPABILITY_QUESTION_RE = re.compile(
    r"\b(?:"
    r"(?:could|can|would|will|may)\s+(?:we|you|it|the\s+\w+)\s+"
    r"(?:also\s+)?(?:please\s+)?"
    r"(?:add|have|support|provide|include|show|display|expose|allow|enable|get)"
    r"|is\s+it\s+possible\s+to"
    r"|would\s+it\s+be\s+possible\s+to"
    r"|any\s+(?:chance|plan|plans)\s+(?:of|to|for)"
    r"|how\s+about\s+(?:adding|having|supporting)"
    r")\b",
    re.IGNORECASE,
)


def _is_requested_capability(literal: str) -> bool:
    """True when a '?' sentence asks the product for a capability.

    Such a literal keeps its requirement character: it stays in the acceptance
    lane (as a bounded TBD when its semantics are unresolved) instead of being
    diverted to the human-open-question lane by punctuation alone.
    """

    return bool(_REQUESTED_CAPABILITY_QUESTION_RE.search(literal or ""))


def _fact_types(path: str, literal: str) -> list[ContractFactType]:
    key = path.casefold()
    text = literal.casefold()
    combined = f"{key} {text}"
    found: list[ContractFactType] = []
    mappings: tuple[tuple[ContractFactType, tuple[str, ...]], ...] = (
        (ContractFactType.OUT_OF_SCOPE, ("out_of_scope", "out of scope", "excluded")),
        (ContractFactType.IN_SCOPE, ("in_scope", "in scope", "applies to")),
        (
            ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
            ("expected", "acceptance", "requirement", "should", "must"),
        ),
        (
            ContractFactType.PRIMARY_PRODUCT_AREA,
            ("product_area", "component", "feature area"),
        ),
        (
            ContractFactType.PRIMARY_OUTPUT_TYPE,
            ("output_type", "output type", "native pdf", "html5"),
        ),
        (ContractFactType.PRESET_TYPE, ("preset_type", "preset type", "output preset")),
        (ContractFactType.DITA_OT_PROCESSING_STATE, ("dita_ot", "dita-ot", "dita ot")),
        (ContractFactType.DEPLOYMENT_MODE, ("deployment", "on-prem", "cloud service")),
        (
            ContractFactType.PRODUCT_VERSION,
            ("fix version", "affects version", "product_version"),
        ),
        (
            ContractFactType.FEATURE_STATE,
            ("feature_state", "enabled", "disabled", "toggle"),
        ),
        (ContractFactType.EXACT_LABELS, ("label", "toggle name", "display name")),
        (ContractFactType.EXACT_DEFAULTS, ("default", "by default")),
        (ContractFactType.EXACT_STATUS_NAMES, ("status", "state name")),
        (ContractFactType.COLORS, ("color", "colour")),
        (ContractFactType.COUNTS, ("count", "number of", " documents", " pages")),
        (ContractFactType.LIMITS, ("limit", "maximum", "minimum", "timeout", "retry")),
        (
            ContractFactType.COMPATIBILITY_REQUIREMENTS,
            ("compatible", "upgrade", "existing behavior"),
        ),
        (
            ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS,
            ("must not", "should not", "without ", "no "),
        ),
        (
            ContractFactType.HUMAN_OPEN_QUESTIONS,
            ("open_question", "open question", "?"),
        ),
        (
            ContractFactType.ENGINEERING_DESIGN_QUESTIONS,
            ("design question", "implementation question"),
        ),
    )
    for fact_type, signals in mappings:
        if any(signal in combined for signal in signals):
            found.append(fact_type)
    # D1-a: a "?" alone must not convert a requested product capability into a
    # human open question.  The explicit open-question path keys (and an
    # explicit design question) still classify; bare punctuation does not.
    if (
        ContractFactType.HUMAN_OPEN_QUESTIONS in found
        and _is_requested_capability(literal)
        and not any(
            signal in combined for signal in ("open_question", "open question")
        )
    ):
        found = [
            fact_type
            for fact_type in found
            if fact_type != ContractFactType.HUMAN_OPEN_QUESTIONS
        ]
        if ContractFactType.DIRECT_EXPECTED_BEHAVIOR not in found:
            found.append(ContractFactType.DIRECT_EXPECTED_BEHAVIOR)
    if re.search(r"(?:\b\d+(?:\.\d+)?\b|#[0-9a-f]{3,8}\b)", literal, re.IGNORECASE):
        found.append(ContractFactType.EXACT_VALUES)
    if re.search(r"['\"“”][^'\"“”]{2,80}['\"“”]", literal):
        found.append(ContractFactType.HUMAN_TERMINOLOGY)
    slash_term = bool(
        re.search(
            r"\b[a-z][a-z0-9 _-]{1,30}/[a-z][a-z0-9 _-]{1,30}\b", literal, re.IGNORECASE
        )
        and not re.search(r"(?:https?://|/content/|/libs/|\\)", literal, re.IGNORECASE)
        # R2: MIME-type tokens (image/png, text/html) are metadata values,
        # not human terminology requiring clarification.
        and not re.fullmatch(
            r"\s*[a-z]+/[a-z0-9][a-z0-9.+-]*\s*", literal, re.IGNORECASE
        )
    )
    if slash_term:
        found.extend(
            [
                ContractFactType.HUMAN_TERMINOLOGY,
                ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED,
            ]
        )
    # P2: a statement-shaped problem/gap (absence, difficulty, manual burden)
    # without imperative requirement language is evidence role
    # PROBLEM_STATEMENT - it establishes the problem, never a solution.
    # UX1: person-centric burden language forces the problem role even when a
    # generic modal is present, because the modal attaches to the person.
    if (
        _PROBLEM_SHAPE_RE.search(literal)
        and not _IMPERATIVE_REQUIREMENT_RE.search(literal)
    ) or _HUMAN_BURDEN_RE.search(literal):
        found = [
            row
            for row in found
            if row
            not in {
                ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS,
            }
        ]
        found.append(ContractFactType.PROBLEM_STATEMENT)
    if not found and any(token in key for token in ("summary", "description", "title")):
        # UX1/R2: the summary/description/title catch-all is shape-aware.
        # Only a requirement-shaped literal (imperative, modal, or declarative
        # behavior verb) becomes a promotion-eligible expected-behavior fact.
        # Current-state narrative without an imperative is context; fragments
        # under four words ("is fixed by", "relates to") are structural noise
        # and produce no fact at all.
        imperative = bool(_PRODUCT_IMPERATIVE_RE.search(literal))
        if len(literal.split()) < 4:
            pass
        elif _CURRENT_STATE_MARKER_RE.search(literal) and not imperative:
            found.append(ContractFactType.CONTEXT_STATEMENT)
        elif imperative or _REQUIREMENT_SHAPE_RE.search(literal):
            found.append(ContractFactType.DIRECT_EXPECTED_BEHAVIOR)
        else:
            found.append(ContractFactType.CONTEXT_STATEMENT)
    return list(dict.fromkeys(found))


def _normalized_fact_value(fact_type: ContractFactType, literal: str) -> str:
    """Produce a scope-friendly value without changing the preserved literal."""

    scoped_types = {
        ContractFactType.IN_SCOPE,
        ContractFactType.OUT_OF_SCOPE,
        ContractFactType.PRIMARY_PRODUCT_AREA,
        ContractFactType.PRIMARY_OUTPUT_TYPE,
        ContractFactType.PRESET_TYPE,
        ContractFactType.DITA_OT_PROCESSING_STATE,
        ContractFactType.DEPLOYMENT_MODE,
        ContractFactType.PRODUCT_VERSION,
        ContractFactType.FEATURE_STATE,
    }
    if fact_type in scoped_types and ":" in literal:
        value = literal.split(":", 1)[1].strip(" .;-")
        if value:
            return value
    if fact_type == ContractFactType.PRIMARY_OUTPUT_TYPE:
        match = re.search(
            r"\b(native\s+pdf|aem\s+sites|html5|json|pdf)\b",
            literal,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
    if fact_type == ContractFactType.DEPLOYMENT_MODE:
        match = re.search(
            r"\b(on[- ]?prem(?:ises)?|cloud service|cloud)\b", literal, re.IGNORECASE
        )
        if match:
            return match.group(1)
    return literal


def _is_authoritative(record: EvidenceRecord) -> bool:
    return record.authority_subject == AuthoritySubject.PRODUCT_CONTRACT and (
        record.requirement_authority in _CONTRACT_AUTHORITIES
        or record.source_type in _HUMAN_CONTRACT_SOURCES
        or record.source_type
        in {EvidenceSourceType.JIRA_DESCRIPTION, EvidenceSourceType.CURRENT_JIRA}
    )


def _relation_for_surface(kind: ChangeSurfaceKind) -> BehaviorRelationType:
    return {
        ChangeSurfaceKind.CHANGED_BEHAVIOR: BehaviorRelationType.GOVERNED_BY,
        ChangeSurfaceKind.READS: BehaviorRelationType.READ_BY,
        ChangeSurfaceKind.WRITES: BehaviorRelationType.WRITTEN_BY,
        ChangeSurfaceKind.CALLERS: BehaviorRelationType.CALLS,
        ChangeSurfaceKind.CALLEES: BehaviorRelationType.CALLS,
        ChangeSurfaceKind.CONSUMERS: BehaviorRelationType.CONSUMED_BY,
        ChangeSurfaceKind.CONFIG_DEPENDENCIES: BehaviorRelationType.CONFIGURED_BY,
        ChangeSurfaceKind.GENERATED_ARTIFACTS: BehaviorRelationType.GENERATED_BY,
        ChangeSurfaceKind.SHARED_PROCESSORS: BehaviorRelationType.PROCESSED_BY,
        ChangeSurfaceKind.ERROR_PATHS: BehaviorRelationType.EXECUTED_BY,
        ChangeSurfaceKind.PERSISTED_STATE: BehaviorRelationType.PERSISTS_THROUGH,
        ChangeSurfaceKind.DOWNSTREAM_DECISION_CONSUMERS: BehaviorRelationType.CONSUMED_BY,
        ChangeSurfaceKind.CHANGED_ENTITY: BehaviorRelationType.DEFINED_BY,
    }[kind]


_RELATION_KEYS: dict[str, BehaviorRelationType] = {
    **{item.value.casefold(): item for item in BehaviorRelationType},
    "consumers": BehaviorRelationType.CONSUMED_BY,
    "consumer": BehaviorRelationType.CONSUMED_BY,
    "reads": BehaviorRelationType.READ_BY,
    "readers": BehaviorRelationType.READ_BY,
    "writes": BehaviorRelationType.WRITTEN_BY,
    "writers": BehaviorRelationType.WRITTEN_BY,
    "callers": BehaviorRelationType.CALLS,
    "callees": BehaviorRelationType.CALLS,
    "config_dependencies": BehaviorRelationType.CONFIGURED_BY,
    "generated_artifacts": BehaviorRelationType.GENERATED_BY,
    "shared_processors": BehaviorRelationType.PROCESSED_BY,
    "persisted_state": BehaviorRelationType.PERSISTS_THROUGH,
    "downstream_decision_consumers": BehaviorRelationType.CONSUMED_BY,
    "parent": BehaviorRelationType.PARENT_OF,
    "children": BehaviorRelationType.CHILD_OF,
    "references": BehaviorRelationType.REFERENCES,
    "specializations": BehaviorRelationType.SPECIALIZED_BY,
}


def _explicit_relationships(
    value: Any,
    *,
    fallback_source: str,
    context: str = "",
) -> list[tuple[str, str, BehaviorRelationType]]:
    """Read typed relationships from arbitrary structured evidence fields."""

    rows: list[tuple[str, str, BehaviorRelationType]] = []
    if isinstance(value, dict):
        local_context = next(
            (
                str(value[key]).strip()
                for key in (
                    "entity",
                    "symbol",
                    "path",
                    "name",
                    "class",
                    "function",
                    "component",
                    "state",
                )
                if key in value
                and isinstance(value[key], (str, int, float))
                and str(value[key]).strip()
            ),
            context or fallback_source,
        )
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_").replace(" ", "_")
            relation = _RELATION_KEYS.get(normalized)
            if relation is not None:
                for _, target in _flatten_strings(child):
                    if target != local_context:
                        rows.append((local_context, target[:500], relation))
            rows.extend(
                _explicit_relationships(
                    child,
                    fallback_source=fallback_source,
                    context=local_context,
                )
            )
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            rows.extend(
                _explicit_relationships(
                    child,
                    fallback_source=fallback_source,
                    context=context,
                )
            )
    return rows


def _subject_for_dimension(dimension: SemanticDimension) -> AuthoritySubject:
    if dimension in {
        SemanticDimension.GOVERNING_SEMANTICS,
        SemanticDimension.CONTROLLING_ATTRIBUTES,
        SemanticDimension.PARENT_CONTEXT,
        SemanticDimension.CHILD_CONTEXT,
        SemanticDimension.HIERARCHY,
        SemanticDimension.SPECIALIZATIONS,
        SemanticDimension.REFERENCED_CONTENT,
        SemanticDimension.NESTED_REFERENCED_CONTENT,
        SemanticDimension.FALLBACK,
    }:
        return AuthoritySubject.DITA_SEMANTICS
    if dimension == SemanticDimension.CROSS_SURFACE_SYNC:
        return AuthoritySubject.CURRENT_UI
    if dimension in {
        SemanticDimension.DIRECT_CONSUMERS,
        SemanticDimension.SIBLING_CONSUMERS,
        SemanticDimension.DOWNSTREAM_PROCESSOR,
        SemanticDimension.PERSISTED_STATE,
        # C1: how a value is actually produced, resolved, re-resolved, kept
        # fresh, or left dangling is established by reading the implementation,
        # not by asking for a product decision.  Without these entries the
        # dimensions fall through to the PRODUCT_CONTRACT default below and
        # their mandatory research misroutes to documentation.
        SemanticDimension.VALUE_PROVENANCE,
        SemanticDimension.VALUE_RESOLUTION_OR_INDIRECTION,
        SemanticDimension.BROKEN_RESOLUTION,
        SemanticDimension.IDENTITY_CHANGE,
        SemanticDimension.MUTATION_FRESHNESS,
    }:
        return AuthoritySubject.ACTUAL_IMPLEMENTATION
    return AuthoritySubject.PRODUCT_CONTRACT


def _relation_for_dimension(
    dimension: SemanticDimension | None,
) -> BehaviorRelationType:
    return {
        SemanticDimension.GOVERNING_CONFIGURATION: BehaviorRelationType.CONFIGURED_BY,
        SemanticDimension.CONTROLLING_ATTRIBUTES: BehaviorRelationType.CONTROLLING_ATTRIBUTE,
        SemanticDimension.DIRECT_CONSUMERS: BehaviorRelationType.CONSUMED_BY,
        SemanticDimension.SIBLING_CONSUMERS: BehaviorRelationType.SIBLING_CONSUMER_OF,
        SemanticDimension.ALTERNATE_MECHANISMS: BehaviorRelationType.ALTERNATE_MECHANISM_TO,
        SemanticDimension.PARENT_CONTEXT: BehaviorRelationType.PARENT_OF,
        SemanticDimension.CHILD_CONTEXT: BehaviorRelationType.CHILD_OF,
        SemanticDimension.SPECIALIZATIONS: BehaviorRelationType.SPECIALIZED_BY,
        SemanticDimension.REFERENCED_CONTENT: BehaviorRelationType.REFERENCES,
        SemanticDimension.NESTED_REFERENCED_CONTENT: BehaviorRelationType.REFERENCES,
        SemanticDimension.DOWNSTREAM_PROCESSOR: BehaviorRelationType.PROCESSED_BY,
        SemanticDimension.GENERATED_OUTPUT: BehaviorRelationType.GENERATED_BY,
        SemanticDimension.PERSISTED_STATE: BehaviorRelationType.PERSISTS_THROUGH,
        SemanticDimension.CROSS_SURFACE_SYNC: BehaviorRelationType.SYNCHRONIZED_WITH,
        SemanticDimension.VERSION_APPLICABILITY: BehaviorRelationType.VERSION_DEPENDENT,
        SemanticDimension.DEPLOYMENT_APPLICABILITY: BehaviorRelationType.DEPLOYMENT_DEPENDENT,
        SemanticDimension.ROLE_PROFILE_APPLICABILITY: BehaviorRelationType.ROLE_DEPENDENT,
    }.get(dimension, BehaviorRelationType.DEFINED_BY)


def _target_sources(subject: AuthoritySubject) -> list[EvidenceSourceType]:
    return {
        AuthoritySubject.DITA_SEMANTICS: [
            EvidenceSourceType.DITA_SPECIFICATION,
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
            EvidenceSourceType.DITA_OT_DOCUMENTATION,
        ],
        AuthoritySubject.ACTUAL_IMPLEMENTATION: [
            EvidenceSourceType.CURRENT_PR,
            EvidenceSourceType.IMPLEMENTATION_DIFF,
            EvidenceSourceType.CURRENT_CODE,
            EvidenceSourceType.EXISTING_AUTOMATION,
        ],
        AuthoritySubject.CURRENT_UI: [
            EvidenceSourceType.UI_OBSERVATION,
            EvidenceSourceType.OBSERVED_UI_FLOW,
            EvidenceSourceType.SCREENSHOT_REPRODUCTION,
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        ],
        AuthoritySubject.PRODUCT_CONTRACT: [
            EvidenceSourceType.ACCEPTED_UAC,
            EvidenceSourceType.PRODUCT_DECISION,
            EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
            EvidenceSourceType.JIRA_DESCRIPTION,
            EvidenceSourceType.CUSTOMER_REQUEST,
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        ],
    }[subject]


# A contract fact must read as observable behaviour, not a raw evidence span. These
# shapes are evidence the miner pulled from the description/RAG/attachments (a screenshot
# ref, a doc-chunk lead-in, a bare number/version, a code line, a config-PID dump, a URL).
# Left as facts they flow through as coverage candidates and render as an evidence dump.
_EVIDENCE_IMAGE_RE = re.compile(r"\.(?:png|jpe?g|gif|bmp|svg)\b|\|thumbnail", re.I)
_EVIDENCE_DOCLEAD_RE = re.compile(
    r"^(?:documented purpose|learn about|configure |source page\b|how to use this in rag|"
    r"detected dita constructs|learned feature behaviou?r|publishing/output contexts)|"
    r"\| Adobe Experience Manager|"
    r"release of adobe experience manager|"  # release-note doc titles
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}\s+release\b",
    re.I,
)
_EVIDENCE_BARE_NUM_RE = re.compile(r"^[\d.\s]+$|^\d{4}\.\d")
_EVIDENCE_CODELINE_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9]+\.[a-z][A-Za-z0-9_]*\(|"     # Class.method(
    r"\b[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*\(|"           # camelCase(
    r"=\s*PropertiesUtil|\bimport\s|\.java\b|[A-Za-z]:\\\\|/src/|https?://|"
    r"\b\w+(?:\.\w+)+\s*=\s*(?:true|false)\b|"         # dotted config property = true/false
    r"\b\w+\.\w+\.\w+\.\w+\b"                          # 4-part dotted config PID
)


def _is_behavioural_literal(literal: str) -> bool:
    """True when a literal reads as observable behaviour rather than raw evidence."""

    s = (literal or "").strip()
    if len(s) < 6:
        return False
    if _EVIDENCE_IMAGE_RE.search(s):
        return False
    if _EVIDENCE_DOCLEAD_RE.search(s):
        return False
    if _EVIDENCE_BARE_NUM_RE.match(s):
        return False
    if _EVIDENCE_CODELINE_RE.search(s):
        return False
    return True


# A traceability anchor / evidence ID: a jira/UAC anchor prefix, an embedded UAC anchor,
# or a bare hex hash. These are record identifiers, never acceptance sentences.
_STRUCTURAL_ID_RE = re.compile(
    r"^(?:jira:)"          # jira anchor prefix (e.g. jira:GUIDES-33605:uac:<hash>)
    r"|:uac[:\-]"          # embedded UAC anchor (e.g. JIRA:GUIDES-1:UAC:UAC-14:<hash>)
    r"|^[0-9a-f]{16,}$",   # bare hex hash
    re.I,
)
# A bare snake_case dimension/axis tag with no whitespace (e.g. toolbar_customization,
# uuid_variant, locked_state). A real acceptance criterion contains prose, not a lone tag.
_BARE_TAG_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


def _is_structural_noise_literal(literal: str) -> bool:
    """True when a literal is a traceability ID or a bare dimension tag rather than an
    acceptance sentence.

    Applied to EVERY source (including accepted UAC / product decisions), because an
    anchor ID or a snake_case tag is structurally never a valid acceptance criterion no
    matter where it came from. Without this guard these tokens became contract facts,
    then acceptance candidates, then got promoted and rendered as acceptance-contract
    bullets (observed on GUIDES-33605: 95 bullets = 17 real ACs + 78 IDs/tags). Narrow by
    design: a real AC contains spaces and prose and will not match. See
    docs/specs/g1-runtime-consolidation.md."""

    s = (literal or "").strip()
    if not s:
        return False
    if " " in s or "\t" in s:
        # Prose. Only reject if it is a short concatenated anchor (<=2 tokens) that is
        # still an ID, never a genuine multi-word sentence.
        return bool(_STRUCTURAL_ID_RE.search(s)) and len(s.split()) <= 2
    if _STRUCTURAL_ID_RE.search(s) or _BARE_TAG_RE.match(s):
        return True
    # A lone single token with no whitespace - a bare dimension/axis label such as
    # "negative", "iframe", "ordering", "scope", "state" - is never an acceptance
    # sentence. Restricted to a single all-letter token (3-24 chars) so it cannot touch
    # multi-word prose, numbers, versions, or code-shaped values handled elsewhere.
    if re.fullmatch(r"[A-Za-z]{3,24}", s):
        return True
    return False


# Vague filler that states no observable outcome. Mirrors the skill uac_linter's
# VAGUE_BEHAVIOR class so shipped runtime plans are held to the same bar.
_VAGUE_AC_RE = re.compile(
    r"\b(?:works?\s+correctly|should\s+work|behaves?\s+as\s+expected|"
    r"works?\s+as\s+expected|functions?\s+correctly)\b",
    re.I,
)
_LINT_MAX_AC_WORDS = 45  # aligns with precision.py VERBOSE_WORDS
_LINT_MAX_AC_COUNT = 10  # aligns with the skill's ac_contract.AC_PRESENTATION_CAP


def _lint_acceptance_criteria(statements: list[str]) -> list[str]:
    """Deterministic, advisory quality checks on the promoted acceptance criteria.

    Ports the plan-text-only subset of the skill's uac_linter into the runtime, which
    otherwise never lints the plans it ships (the linter only runs when authoring THROUGH
    the skill). ADVISORY only: findings are surfaced in the plan; a fact-grounded AC is
    never rewritten or dropped here (that would need judgement the LLM-free runtime avoids).
    Checks: DUPLICATE_AC (same normalized outcome twice), VAGUE_BEHAVIOR (short filler with
    no observable outcome), EXCESSIVE_LENGTH (paragraph-length criterion)."""
    problems: list[str] = []
    seen: dict[str, str] = {}
    for statement in statements:
        text = statement.strip()
        if not text:
            continue
        words = len(re.findall(r"\w+", text))
        key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        if key and key in seen:
            problems.append(
                f"DUPLICATE_AC: \"{text[:70]}\" repeats an earlier acceptance criterion"
            )
        elif key:
            seen[key] = text
        if words < 8 and _VAGUE_AC_RE.search(text):
            problems.append(
                f"VAGUE_BEHAVIOR: \"{text[:70]}\" states no observable product outcome"
            )
        if words > _LINT_MAX_AC_WORDS:
            problems.append(
                f"EXCESSIVE_LENGTH: an acceptance criterion runs {words} words — split "
                f"or tighten it (\"{text[:50]}...\")"
            )
    ac_count = len([s for s in statements if s.strip()])
    if ac_count > _LINT_MAX_AC_COUNT:
        problems.append(
            f"AC_COUNT_CAP: {ac_count} acceptance criteria — the presented UAC should be "
            f"consolidated to at most {_LINT_MAX_AC_COUNT}; merge related criteria (senior-QA "
            "style) and keep granular detail as sub-points or in the linked full record"
        )
    return problems


def _plain_candidate(value: str) -> str:
    """Humanize ontology prefixes while preserving the entity wording."""

    prefix, separator, remainder = value.partition(": ")
    if separator and re.fullmatch(r"[A-Z_]+", prefix):
        return f"{prefix.replace('_', ' ').capitalize()}: {remainder}"
    return value


def _scope_clause_value(value: str) -> str:
    _, separator, remainder = value.partition(":")
    selected = remainder if separator else value
    return selected.strip(" .;:-").casefold()


_CONTRADICTION_NEGATORS = {
    "disable",
    "disabled",
    "exclude",
    "excluded",
    "never",
    "no",
    "not",
    "off",
    "remove",
    "removed",
    "without",
}
_CONTRADICTION_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "be",
    "for",
    "in",
    "is",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "when",
    "with",
}


def _contract_terms(value: str) -> tuple[set[str], bool]:
    tokens = set(re.findall(r"[a-z0-9_-]+", value.casefold()))
    negative = bool(tokens & _CONTRADICTION_NEGATORS)
    return tokens - _CONTRADICTION_NEGATORS - _CONTRADICTION_STOP_WORDS, negative


def _contradicts_accepted_contract(
    candidate: str, accepted_literals: list[str]
) -> bool:
    """Detect only explicit polarity conflicts with a materially overlapping AC.

    The high overlap threshold deliberately avoids treating unrelated additional
    coverage as a contradiction.  Such additions are rejected separately when
    a Human Accepted Contract is active.
    """

    candidate_terms, candidate_negative = _contract_terms(candidate)
    if not candidate_terms:
        return False
    for literal in accepted_literals:
        accepted_terms, accepted_negative = _contract_terms(literal)
        if candidate_negative == accepted_negative or not accepted_terms:
            continue
        overlap = candidate_terms & accepted_terms
        denominator = min(len(candidate_terms), len(accepted_terms))
        if denominator and len(overlap) / denominator >= 0.6:
            return True
    return False


def _semantic_candidate_key(value: str) -> tuple[str, ...]:
    """Return a conservative outcome key for near-duplicate source wording.

    Only grammatical filler is removed.  Token order and every product noun
    remain significant so actor/object reversals and output/page distinctions
    cannot silently collapse into one acceptance candidate.
    """

    raw_terms = re.findall(r"[a-z0-9_-]+", value.casefold())
    negative = any(term in _CONTRADICTION_NEGATORS for term in raw_terms)
    terms = [
        term
        for term in raw_terms
        if term not in _CONTRADICTION_NEGATORS and term not in _CONTRADICTION_STOP_WORDS
    ]
    polarity = "__NEGATIVE__" if negative else "__POSITIVE__"
    return (polarity, *terms)


def _candidate_terminal_disposition(
    decision: AcceptancePromotionDecision,
) -> CandidateTerminalDisposition:
    if decision.status == PromotionStatus.PROMOTED:
        return CandidateTerminalDisposition.AC
    if decision.status == PromotionStatus.BLOCKED:
        return CandidateTerminalDisposition.OPEN_QUESTION
    if not decision.scope_established:
        return CandidateTerminalDisposition.OUT_OF_SCOPE
    return CandidateTerminalDisposition.INVESTIGATED_AND_REJECTED


def _canonical_product_versions(values: list[str]) -> set[str]:
    """Normalize explicit product-version labels without broadening their scope."""

    normalized: set[str] = set()
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "").strip().casefold())
        if not text:
            continue
        matches = re.findall(
            r"\b\d+(?:\.\d+){1,3}(?:\s*(?:sp|service pack)\s*\d+)?\b",
            text,
        )
        normalized.update(re.sub(r"\s+", " ", match) for match in matches)
        if not matches:
            normalized.add(text)
    return normalized


def _canonical_deployment_modes(values: list[str]) -> set[str]:
    """Collapse only well-known Cloud/on-prem spelling variants."""

    normalized: set[str] = set()
    for value in values:
        text = re.sub(r"[_\s-]+", " ", str(value or "").strip().casefold())
        if not text:
            continue
        recognized = False
        if re.search(r"\bon\s*prem(?:ise|ises)?\b", text):
            normalized.add("on-prem")
            recognized = True
        if re.search(r"\bcloud(?:\s+service)?\b", text):
            normalized.add("cloud")
            recognized = True
        if not recognized:
            normalized.add(text)
    return normalized


def _implementation_scope_axes(
    record: EvidenceRecord,
) -> tuple[set[str], set[str]]:
    versions = _canonical_product_versions(
        [record.product_version, *record.version_scope.product_versions]
    )
    deployments = _canonical_deployment_modes(
        [record.deployment_model, record.version_scope.deployment_model]
    )
    return versions, deployments


def _implementation_evidence_matches_scope(
    record: EvidenceRecord,
    scope: ScopeResolution | None,
) -> bool:
    """Fail closed when implementation evidence cannot prove the active scope."""

    if (
        scope is None
        or record.authority_subject != AuthoritySubject.ACTUAL_IMPLEMENTATION
    ):
        return True
    expected_versions = _canonical_product_versions(scope.product_versions)
    expected_deployments = _canonical_deployment_modes(scope.deployment_modes)
    actual_versions, actual_deployments = _implementation_scope_axes(record)
    return bool(
        (not expected_versions or expected_versions & actual_versions)
        and (not expected_deployments or expected_deployments & actual_deployments)
    )


def _implementation_scope_fully_covered(
    records: list[EvidenceRecord],
    question: MissingQuestion,
    scope: ScopeResolution | None,
) -> bool:
    """Require every requested version/deployment branch before confirmation."""

    if (
        scope is None
        or question.authority_subject != AuthoritySubject.ACTUAL_IMPLEMENTATION
    ):
        return True
    expected_versions = _canonical_product_versions(scope.product_versions)
    expected_deployments = _canonical_deployment_modes(scope.deployment_modes)
    if not expected_versions and not expected_deployments:
        return True
    actual_versions: set[str] = set()
    actual_deployments: set[str] = set()
    for record in records:
        versions, deployments = _implementation_scope_axes(record)
        actual_versions.update(versions)
        actual_deployments.update(deployments)
    return bool(
        (not expected_versions or expected_versions.issubset(actual_versions))
        and (
            not expected_deployments
            or expected_deployments.issubset(actual_deployments)
        )
    )


def _parse_authorization_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _semantic_handoff_is_current(
    handoff: AuthorizedSemanticEvidence,
    *,
    request: GenerationRequest,
    record: EvidenceRecord,
    question: MissingQuestion,
    retrieval: DirectedRetrievalRecord,
    local_evidence_ids: set[str],
    now: datetime,
) -> bool:
    """Revalidate the complete stage-10 authorization at its final consumer."""

    authorization = handoff.authorization
    attestation = authorization.source_attestation
    assessment = authorization.question_assessment
    binding = attestation.binding
    query = handoff.query
    provenance = handoff.provenance
    disposition = handoff.disposition
    content = record.content if isinstance(record.content, Mapping) else {}
    expected_source_reference_sha256 = stable_sha256(
        {
            "source_reference": record.source_reference,
            "source_locator": record.source_location,
            "source_native_id": record.source_native_id,
        }
    )
    expected_correlation_id = (
        "fj-shadow:"
        + stable_sha256(
            {
                "request_id": request.request_id,
                "question_id": question.question_id,
            }
        )[:32]
    )
    allowed = set(request.allowed_sources)
    expected_source_types = sorted(
        (
            source_type
            for source_type in question.target_source_types
            if not allowed or source_type in allowed
        ),
        key=lambda value: value.value,
    )
    verified_at = _parse_authorization_time(attestation.verified_at)
    attestation_expiry = _parse_authorization_time(attestation.expires_at)
    assessed_at = _parse_authorization_time(assessment.assessed_at)
    assessment_expiry = _parse_authorization_time(assessment.expires_at)
    expected_revision = next(
        (
            value
            for value in (
                record.version_scope.repository_revision,
                record.product_version,
                record.dita_version,
                record.version_scope.dita_version,
            )
            if str(value or "").strip()
        ),
        "",
    )
    is_preexisting_local_duplicate = record.evidence_id in local_evidence_ids
    lifecycle_is_valid = (
        record.inspected
        and record.lifecycle_status
        in {
            EvidenceLifecycleStatus.INSPECTED,
            EvidenceLifecycleStatus.USED,
        }
        if is_preexisting_local_duplicate
        else (
            record.retrieval_pass == "reasoning-directed-provider"  # noqa: S105
            and record.lifecycle_status == EvidenceLifecycleStatus.INSPECTED
            and record.inspected
            and not record.used
            and record.verification_status == attestation.verification_status
        )
    )
    if (
        authorization.question_assessment.binding != binding
        or assessment.source_attestation_id != attestation.attestation_id
        or binding.request_id != request.request_id
        or binding.tenant_id != request.tenant_id
        or binding.principal_scope_sha256
        != stable_sha256(request.principal.model_dump(mode="json"))
        or binding.question_id != question.question_id
        or binding.question_sha256 != stable_sha256(question.question)
        or binding.query_id != query.query_id
        or binding.evidence_id != record.evidence_id
        or binding.content_sha256 != record.content_sha256
        or binding.source_type != record.source_type
        or binding.authority_subject != record.authority_subject
        or binding.currentness != record.currentness
        or binding.requirement_authority != record.requirement_authority
        or record.requirement_authority not in _SEMANTIC_HANDOFF_AUTHORITIES
        or binding.version_scope_sha256
        != stable_sha256(record.version_scope.model_dump(mode="json"))
        or binding.visibility_sha256
        != stable_sha256(record.visibility.model_dump(mode="json"))
        or binding.source_reference_sha256 != expected_source_reference_sha256
        or binding.temporal_policy_sha256
        != stable_sha256(query.temporal_boundary.model_dump(mode="json"))
        or binding.authority_requirement_sha256
        != stable_sha256(query.authority_requirement.model_dump(mode="json"))
        or binding.provenance_id != provenance.provenance_id
        or provenance.applicability != ApplicabilityState.APPLICABLE
        or binding.disposition_id != disposition.disposition_id
        or binding.provider != provenance.provider
        or binding.provider_contract_version != provenance.provider_contract_version
        or binding.provider_call_id != provenance.provider_call_id
        or binding.correlation_id != provenance.correlation_id
        or query.question_id != question.question_id
        or query.question != question.question
        or query.dimension != question.dimension
        or query.authority_requirement.subject != question.authority_subject
        or query.requested_evidence_types != expected_source_types
        or query.jira_reference != request.jira_key
        or query.correlation_id != expected_correlation_id
        or query.blocking != question.blocking
        or (
            query.context_evidence_ids
            and not set(query.context_evidence_ids).issubset(
                retrieval.matched_evidence_ids
            )
        )
        or query.query_id not in record.retrieved_by_query
        or provenance.evidence_id != record.evidence_id
        or disposition.evidence_id != record.evidence_id
        or disposition.source_type != record.source_type
        or disposition.source_reference_sha256 != expected_source_reference_sha256
        or disposition.content_sha256
        != stable_sha256({"text": str(content.get("text") or "")})
        or disposition.provider_hit_sha256 != binding.provider_hit_sha256
        or assessment.assessed_content_sha256 != record.content_sha256
        or not lifecycle_is_valid
        or not record_visible_to(record, request.principal)
        or verified_at is None
        or verified_at > now
        or (attestation_expiry is not None and attestation_expiry <= now)
        or assessed_at is None
        or assessed_at > now
        or assessment_expiry is None
        or assessment_expiry <= now
    ):
        return False
    if record.currentness == CurrentnessState.VERSION_SPECIFIC:
        return bool(
            attestation.verification_status == VerificationState.VERIFIED_REVISION
            and expected_revision
            and attestation.source_revision == expected_revision
        )
    if record.currentness == CurrentnessState.ENVIRONMENT_SPECIFIC:
        return bool(
            (
                record.deployment_model
                or record.environment
                or record.version_scope.deployment_model
                or record.version_scope.environment
            )
            and attestation.verification_status
            in {VerificationState.VERIFIED_LIVE, VerificationState.VERIFIED_SOURCE}
        )
    return bool(
        record.currentness == CurrentnessState.CURRENT
        and attestation.verification_status
        in {VerificationState.VERIFIED_LIVE, VerificationState.VERIFIED_SOURCE}
    )


class CanonicalTestPlanReasoningService:
    """Typed transformations used by the canonical runtime in fixed order."""

    def extract_contract_facts(
        self, bundle: CanonicalEvidenceBundle
    ) -> ContractFactSet:
        facts: list[ContractFact] = []
        for record in bundle.records:
            if record.authority_subject != AuthoritySubject.PRODUCT_CONTRACT:
                continue
            for path, source_literal in _flatten_strings(record.content):
                source_literal = _reduce_stack_frames(source_literal)
                for literal in _contract_literals(path, source_literal):
                    if not literal.strip():
                        # A whitespace-only source value (e.g. an empty AC line or a
                        # non-breaking-space metadata value) must never become a fact:
                        # an authoritative fact with empty literal fails ContractIntegrityGate
                        # and hard-blocks the whole plan (no output). Skip it here.
                        continue
                    if _RETRIEVAL_BOILERPLATE_RE.search(literal):
                        # Corpus retrieval-metadata boilerplate ("Learning retrieval
                        # profile for ...", "Use this for QA/test-plan retrieval
                        # when ...", "High-signal topics and headings: ...") is text
                        # synthesized to make a chunk findable.  It is not a product
                        # statement and must never be presented to a reader as
                        # configuration, scope, or coverage evidence.
                        continue
                    if _is_contract_metadata(path, literal):
                        continue
                    fact_types = _fact_types(path, literal)
                    is_scalar_scope_fact = bool(
                        _SCALAR_SCOPE_FACT_TYPES.intersection(fact_types)
                    )
                    if (
                        _is_structural_noise_literal(literal)
                        and not is_scalar_scope_fact
                    ):
                        # A traceability anchor ID or a bare dimension tag is never an
                        # acceptance sentence. Filter it from EVERY source (including
                        # accepted UAC) so it cannot become a fact -> candidate ->
                        # promoted acceptance-contract bullet. Filtering at extraction
                        # keeps the completeness invariant intact (facts are counted from
                        # extraction output, so no orphan disposition downstream).
                        continue
                    _accepted_source = record.source_type in {
                        EvidenceSourceType.ACCEPTED_UAC,
                        EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
                        EvidenceSourceType.PRODUCT_DECISION,
                    }
                    if (
                        not _accepted_source
                        and not is_scalar_scope_fact
                        and not _is_behavioural_literal(literal)
                    ):
                        # An evidence-noise span from a lower-authority record (a
                        # screenshot ref, doc-chunk lead-in, bare number, code line,
                        # config-PID) must not become a contract fact; it renders as an
                        # evidence dump in the coverage sections. Accepted UAC / product
                        # decisions are never filtered.
                        continue
                    if len(literal) > 2000:
                        literal = literal[:2000]
                    if record.source_type in _NON_HUMAN_TERMINOLOGY_SOURCES:
                        fact_types = [
                            fact_type
                            for fact_type in fact_types
                            if fact_type not in _TERMINOLOGY_FACT_TYPES
                            # Retrieved documentation/spec/code is research
                            # evidence; its sentences are never the ticket's
                            # own expected behavior or narrative context.
                            and fact_type
                            not in {
                                ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                                ContractFactType.CONTEXT_STATEMENT,
                            }
                        ]
                    if (
                        record.source_type
                        in {
                            EvidenceSourceType.ACCEPTED_UAC,
                            EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
                            EvidenceSourceType.PRODUCT_DECISION,
                        }
                        and len(literal) >= 4
                        and not any(
                            token in path.casefold()
                            for token in (
                                "fingerprint",
                                "snapshot_id",
                                "evidence_ref",
                                "source_clause_id",
                                "automation_consumption",
                                "schema_version",
                                "uac_id",
                                "priority",
                                "confidence",
                            )
                        )
                        and ContractFactType.DIRECT_EXPECTED_BEHAVIOR not in fact_types
                        and ContractFactType.PROBLEM_STATEMENT not in fact_types
                    ):
                        fact_types.insert(0, ContractFactType.DIRECT_EXPECTED_BEHAVIOR)
                    for fact_type in fact_types:
                        ambiguous = (
                            fact_type
                            == ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED
                        )
                        facts.append(
                            ContractFact(
                                fact_type=fact_type,
                                literal=literal,
                                normalized_value=_normalized_fact_value(
                                    fact_type, literal
                                ),
                                source_evidence_ids=[record.evidence_id],
                                source_reference=f"{record.source_reference}:{path}",
                                authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                                authority_class=record.requirement_authority,
                                authoritative=_is_authoritative(record),
                                preservation_state=(
                                    ContractPreservationState.EXPLICITLY_FLAGGED_AS_AMBIGUOUS
                                    if ambiguous
                                    else ContractPreservationState.PRESERVED
                                ),
                                ambiguity="Human terminology requires clarification."
                                if ambiguous
                                else "",
                            )
                        )
        has_accepted = any(
            fact.authority_class in _ACCEPTED_AUTHORITIES
            or any(
                record.evidence_id in fact.source_evidence_ids
                and record.source_type == EvidenceSourceType.ACCEPTED_UAC
                for record in bundle.records
            )
            for fact in facts
        )
        has_human = any(
            record.source_type in _HUMAN_CONTRACT_SOURCES for record in bundle.records
        )
        has_authoritative = any(fact.authoritative for fact in facts)
        mode = (
            ContractMode.HUMAN_ACCEPTED_CONTRACT
            if has_accepted
            else ContractMode.PARTIAL_HUMAN_CONTRACT
            if has_human
            else ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT
            if has_authoritative
            else ContractMode.INSUFFICIENT_EVIDENCE_FOR_CONTRACT
        )
        return ContractFactSet(contract_mode=mode, facts=facts)

    def contract_integrity_gate(self, facts: ContractFactSet) -> GateDecision:
        failures: list[str] = []
        for fact in facts.facts:
            if not fact.authoritative:
                continue
            if fact.preservation_state == ContractPreservationState.LOST:
                failures.append(f"Authoritative fact was lost: {fact.fact_id}")
            if not fact.literal.strip():
                failures.append(
                    f"Authoritative source wording is empty: {fact.fact_id}"
                )
            if not fact.source_evidence_ids:
                failures.append(f"Authoritative fact has no source: {fact.fact_id}")
        if facts.contract_mode == ContractMode.INSUFFICIENT_EVIDENCE_FOR_CONTRACT:
            failures.append("No authoritative product-contract fact is available.")
        return GateDecision(
            gate="ContractIntegrityGate",
            status=GateStatus.FAILED if failures else GateStatus.PASSED,
            failures=failures,
            checked_ids=facts.authoritative_fact_ids,
        )

    def route_domains(
        self, bundle: CanonicalEvidenceBundle, facts: ContractFactSet
    ) -> list[DomainActivation]:
        positive_values = [
            fact.literal
            for fact in facts.facts
            if fact.fact_type != ContractFactType.OUT_OF_SCOPE
        ] + [_record_text(record) for record in bundle.records]
        text = " ".join(_positive_scope_clauses(positive_values)).casefold()
        padded = f" {text} "
        scale_text = _scale_detection_text(padded)
        activations: list[DomainActivation] = []
        for domain, signals in _DOMAIN_SIGNALS.items():
            matched = sorted(
                {
                    signal.strip()
                    for signal in signals
                    if _contains_domain_signal(padded, signal)
                }
            )
            if domain == IssueDomain.PERFORMANCE and re.search(
                r"\b(?:\d{1,3}(?:,\d{3})+|\d{4,}|\d+(?:\.\d+)?\s*k)\b"
                r".{0,40}\b(?:documents?|pages?|items?|maps?|topics?)\b",
                scale_text,
            ):
                matched.append("explicit-high-cardinality")
            if (
                domain == IssueDomain.CONTENT_MANAGEMENT
                and _CONTENT_LIFECYCLE_RE.search(padded)
            ):
                matched.append("content-lifecycle-operation")
            if matched:
                activations.append(
                    DomainActivation(
                        domain=domain,
                        confidence=min(0.98, 0.65 + 0.08 * len(matched)),
                        evidence_ids=[
                            record.evidence_id
                            for record in bundle.records
                            if any(
                                _contains_domain_signal(
                                    " ".join(
                                        _positive_scope_clauses([_record_text(record)])
                                    ).casefold(),
                                    signal,
                                )
                                for signal in signals
                            )
                        ],
                        matched_signals=matched,
                    )
                )
        if not activations:
            activations.append(
                DomainActivation(
                    domain=IssueDomain.OTHER,
                    confidence=0.5,
                    matched_signals=["fallback"],
                )
            )
        return sorted(activations, key=lambda row: row.domain.value)

    def resolve_scope(
        self,
        facts: ContractFactSet,
        domains: list[DomainActivation],
        clarifications: list[dict[str, Any]] | None = None,
    ) -> ScopeResolution:
        by_type: dict[ContractFactType, list[ContractFact]] = defaultdict(list)
        # Scope is a TICKET decision, never a documentation statement.  Retrieved
        # product documentation legitimately says things like "Applies to folders
        # under Experience Manager DAM"; that sentence describes the doc's own
        # subject, not this ticket's scope.  Admitting it made an unrelated
        # Experience League page define in-scope/deployment for the run.  Docs
        # still establish existing behavior everywhere else - they just cannot
        # declare what this ticket covers.
        _SCOPE_DEFINING_TYPES = {
            ContractFactType.IN_SCOPE,
            ContractFactType.OUT_OF_SCOPE,
            ContractFactType.DEPLOYMENT_MODE,
        }
        for fact in facts.facts:
            if (
                fact.fact_type in _SCOPE_DEFINING_TYPES
                and fact.authority_class not in _TICKET_UNDERSTANDING_AUTHORITIES
            ):
                continue
            by_type[fact.fact_type].append(fact)
        publishing = any(row.domain == IssueDomain.PUBLISHING for row in domains)
        active_domains = {row.domain for row in domains}
        semantic_units = _semantic_text_units(
            [
                fact.literal
                for fact in facts.facts
                if fact.fact_type != ContractFactType.OUT_OF_SCOPE
            ]
        )
        dita_ot = DitaOtProcessingState.NOT_APPLICABLE
        if publishing:
            configuration_only = (
                _units_contain_any(
                    semantic_units, _PUBLISHING_CONFIGURATION_ONLY_SIGNALS
                )
                and not _units_contain_any(
                    semantic_units, _GENERATED_ARTIFACT_DELIVERY_SIGNALS
                )
                and not _units_match(
                    semantic_units, _CONTEXTUAL_GENERATED_ARTIFACT_DELIVERY_RE
                )
            )
            dita_scope_units = _semantic_text_units(
                [
                    fact.literal
                    for fact in by_type[ContractFactType.DITA_OT_PROCESSING_STATE]
                    if not fact.literal.casefold().startswith("out of scope")
                ]
            )
            on = _units_match(
                dita_scope_units,
                re.compile(r"dita[- ]?ot.{0,30}\b(on|enabled|true)\b"),
            )
            off = _units_match(
                dita_scope_units,
                re.compile(r"dita[- ]?ot.{0,30}\b(off|disabled|false)\b"),
            )
            dita_ot = (
                DitaOtProcessingState.NOT_APPLICABLE
                if configuration_only
                else DitaOtProcessingState.BOTH
                if on and off
                else DitaOtProcessingState.ON
                if on
                else DitaOtProcessingState.OFF
                if off
                else DitaOtProcessingState.UNRESOLVED
            )
        dita_ot_basis = ""
        applied_clarification_ids: list[str] = []
        if publishing:
            if configuration_only:
                dita_ot_basis = "CONFIGURATION_ONLY"
            elif dita_ot != DitaOtProcessingState.UNRESOLVED:
                dita_ot_basis = "EVIDENCE"
            if dita_ot == DitaOtProcessingState.UNRESOLVED:
                # P1 resume: an admitted human clarification bound to this exact
                # scope question resolves it without re-deriving from the ticket.
                admitted = _admit_scope_clarification(
                    "ENABLE_DITA_OT_PROCESSING", clarifications or []
                )
                if admitted is not None:
                    mapped = _DITA_OT_CLARIFICATION_ANSWERS.get(
                        _normalize_clarification_answer(admitted.answer)
                    )
                    if mapped is not None:
                        dita_ot = mapped
                        dita_ot_basis = "HUMAN_CLARIFICATION"
                        applied_clarification_ids.append(admitted.clarification_id)
            if dita_ot == DitaOtProcessingState.UNRESOLVED:
                # Materiality gate (generic): the processing toggle becomes a
                # user-facing acceptance question only when admitted evidence
                # ties the dimension itself to conditional or differing
                # behavior.  Same-domain vocabulary ("outputs", "processing")
                # or an unknown value is NOT material interaction; without it
                # the dimension is NOT_APPLICABLE to this acceptance contract
                # with an auditable basis, never a blocking question.
                if not _dimension_interaction_present(
                    semantic_units, "ENABLE_DITA_OT_PROCESSING"
                ):
                    dita_ot = DitaOtProcessingState.NOT_APPLICABLE
                    dita_ot_basis = "NO_MATERIAL_INTERACTION_EVIDENCE"
        out_literals = {
            fact.literal.casefold() for fact in by_type[ContractFactType.OUT_OF_SCOPE]
        }
        selection_conflicts: set[ContractFactType] = set()

        def selected_literal(fact_type: ContractFactType) -> str:
            candidates = [
                fact
                for fact in by_type[fact_type]
                if fact.literal.casefold() not in out_literals
                and not fact.literal.casefold().startswith("out of scope")
            ]
            if not candidates:
                return ""

            def precedence(fact: ContractFact) -> tuple[int, int, int, int]:
                return (
                    fact.authority_class in _ACCEPTED_AUTHORITIES,
                    fact.authoritative,
                    *_scope_source_priority(fact),
                )

            highest_precedence = max(precedence(fact) for fact in candidates)
            highest_candidates = [
                fact for fact in candidates if precedence(fact) == highest_precedence
            ]
            semantic_values = {
                _scope_semantic_key(_scope_semantic_value(fact))
                for fact in highest_candidates
            }
            if len(semantic_values) != 1:
                selection_conflicts.add(fact_type)
                return ""

            return min(
                (_scope_semantic_value(fact) for fact in highest_candidates),
                key=lambda value: (value.casefold(), value),
            )

        product_area = selected_literal(ContractFactType.PRIMARY_PRODUCT_AREA)
        output_type = selected_literal(ContractFactType.PRIMARY_OUTPUT_TYPE)
        preset = selected_literal(ContractFactType.PRESET_TYPE)
        normalized_out_scope = " ".join(
            str(fact.normalized_value or fact.literal)
            for fact in by_type[ContractFactType.OUT_OF_SCOPE]
        ).casefold()
        shared_path_outputs = sorted(
            {
                fact.literal
                for fact in facts.facts
                if "share" in fact.literal.casefold()
                and any(
                    token in fact.literal.casefold()
                    for token in ("preset", "output", "processor", "resolver")
                )
            }
        )
        unresolved: list[str] = []
        dimension_materiality: dict[str, str] = {}
        if publishing and dita_ot == DitaOtProcessingState.UNRESOLVED:
            unresolved.append("ENABLE_DITA_OT_PROCESSING")
            dimension_materiality["ENABLE_DITA_OT_PROCESSING"] = "MATERIAL"
        elif dita_ot_basis == "NO_MATERIAL_INTERACTION_EVIDENCE":
            # Three-way gate: no dimension signal at all is plainly
            # non-material; a bare mention without a behavior tie is
            # UNRESOLVED_MATERIALITY - a bounded research-first probe decides
            # before any human question (never a blocking TBD by default).
            if _dimension_signal_present(
                semantic_units, "ENABLE_DITA_OT_PROCESSING"
            ):
                dimension_materiality["ENABLE_DITA_OT_PROCESSING"] = (
                    "UNRESOLVED_MATERIALITY:RESEARCH_FIRST"
                )
            else:
                dimension_materiality["ENABLE_DITA_OT_PROCESSING"] = (
                    "NON_MATERIAL_TO_CURRENT_ACCEPTANCE:NO_MATERIAL_INTERACTION_EVIDENCE"
                )
        # PRIMARY_PRESET_TYPE: unknown preset is a blocking question only when
        # evidence ties preset/output-type choice to conditional or differing
        # behavior; merely being a publishing ticket is not material.
        if publishing and not preset:
            if _dimension_interaction_present(
                semantic_units, "PRIMARY_PRESET_TYPE"
            ):
                unresolved.append("PRIMARY_PRESET_TYPE")
                dimension_materiality["PRIMARY_PRESET_TYPE"] = "MATERIAL"
            elif _dimension_signal_present(semantic_units, "PRIMARY_PRESET_TYPE"):
                dimension_materiality["PRIMARY_PRESET_TYPE"] = (
                    "UNRESOLVED_MATERIALITY:RESEARCH_FIRST"
                )
            else:
                dimension_materiality["PRIMARY_PRESET_TYPE"] = (
                    "NON_MATERIAL_TO_CURRENT_ACCEPTANCE:NO_MATERIAL_INTERACTION_EVIDENCE"
                )
        if publishing and not by_type[ContractFactType.OUT_OF_SCOPE]:
            unresolved.append("OUT_OF_SCOPE")
        if publishing and not shared_path_outputs:
            unresolved.append("SHARED_PATH_OUTPUTS")
        unresolved.extend(
            _SCOPE_UNRESOLVED_FIELD[fact_type]
            for fact_type in sorted(selection_conflicts, key=lambda row: row.value)
        )
        return ScopeResolution(
            primary_product_area=product_area,
            primary_publishing_mode=output_type or preset,
            primary_preset_type=preset,
            primary_output_type=output_type,
            enable_dita_ot_processing=dita_ot,
            dita_ot_resolution_basis=dita_ot_basis,
            applied_clarification_ids=applied_clarification_ids,
            dimension_materiality=dimension_materiality,
            aem_sites_implementation=(
                ApplicabilityState.NOT_APPLICABLE
                if "aem sites" in normalized_out_scope
                else ApplicabilityState.APPLICABLE
                if any("aem sites" in unit for unit in semantic_units)
                else ApplicabilityState.UNRESOLVED
                if publishing
                else ApplicabilityState.NOT_APPLICABLE
            ),
            in_scope=[
                str(fact.normalized_value or fact.literal)
                for fact in by_type[ContractFactType.IN_SCOPE]
            ],
            out_of_scope=[
                str(fact.normalized_value or fact.literal)
                for fact in by_type[ContractFactType.OUT_OF_SCOPE]
            ],
            shared_path_outputs=shared_path_outputs,
            execution_interfaces=sorted(
                ({"API"} if IssueDomain.API in active_domains else set())
                | ({"UI"} if IssueDomain.AUTHORING in active_domains else set())
            ),
            product_versions=[
                str(fact.normalized_value or fact.literal)
                for fact in by_type[ContractFactType.PRODUCT_VERSION]
            ],
            deployment_modes=[
                str(fact.normalized_value or fact.literal)
                for fact in by_type[ContractFactType.DEPLOYMENT_MODE]
            ],
            unresolved_fields=unresolved,
            source_fact_ids=[fact.fact_id for fact in facts.facts],
        )

    def extract_change_surfaces(
        self, bundle: CanonicalEvidenceBundle, facts: ContractFactSet
    ) -> list[ChangeSurface]:
        surfaces: list[ChangeSurface] = []
        key_map: dict[str, ChangeSurfaceKind] = {
            "changed_entity": ChangeSurfaceKind.CHANGED_ENTITY,
            "changed_entities": ChangeSurfaceKind.CHANGED_ENTITY,
            "files": ChangeSurfaceKind.CHANGED_ENTITY,
            "path": ChangeSurfaceKind.CHANGED_ENTITY,
            "symbol": ChangeSurfaceKind.CHANGED_ENTITY,
            "reads": ChangeSurfaceKind.READS,
            "writes": ChangeSurfaceKind.WRITES,
            "callers": ChangeSurfaceKind.CALLERS,
            "callees": ChangeSurfaceKind.CALLEES,
            "consumers": ChangeSurfaceKind.CONSUMERS,
            "config_dependencies": ChangeSurfaceKind.CONFIG_DEPENDENCIES,
            "generated_artifacts": ChangeSurfaceKind.GENERATED_ARTIFACTS,
            "shared_processors": ChangeSurfaceKind.SHARED_PROCESSORS,
            "error_paths": ChangeSurfaceKind.ERROR_PATHS,
            "persisted_state": ChangeSurfaceKind.PERSISTED_STATE,
            "downstream_decision_consumers": ChangeSurfaceKind.DOWNSTREAM_DECISION_CONSUMERS,
        }
        for record in bundle.records:
            if (
                record.source_type not in _IMPLEMENTATION_SOURCES
                or is_github_implementation_result_record(record)
            ):
                continue
            for path, literal in _flatten_strings(record.content):
                kind = next(
                    (value for key, value in key_map.items() if key in path.casefold()),
                    None,
                )
                if kind is None and not any(
                    token in path.casefold() for token in ("match", "file", "source")
                ):
                    continue
                resolved_kind = kind or ChangeSurfaceKind.CHANGED_ENTITY
                if (
                    resolved_kind == ChangeSurfaceKind.CHANGED_ENTITY
                    and not _is_code_entity_literal(literal)
                ):
                    # Snippets, matched lines, and test titles inherit an
                    # admitting path from their parent key.  Admitting them as
                    # entities floods directed retrieval with non-entity terms.
                    continue
                surfaces.append(
                    ChangeSurface(
                        kind=resolved_kind,
                        entity=literal[:500],
                        source_evidence_ids=[record.evidence_id],
                        confidence=record.evidence_confidence,
                    )
                )
        if not surfaces:
            current_issue_evidence_ids = {
                record.evidence_id
                for record in bundle.records
                if record.source_type in _CURRENT_ISSUE_BEHAVIOR_SOURCES
            }
            behavior_fact = _material_behavior_fact(
                facts,
                allowed_evidence_ids=current_issue_evidence_ids,
            )
            if behavior_fact is not None:
                source_confidence = max(
                    (
                        record.evidence_confidence
                        for record in bundle.records
                        if record.evidence_id in behavior_fact.source_evidence_ids
                    ),
                    default=0.5,
                )
                surfaces.append(
                    ChangeSurface(
                        kind=ChangeSurfaceKind.CHANGED_BEHAVIOR,
                        entity=_bounded_behavior_subject(behavior_fact.literal),
                        source_evidence_ids=behavior_fact.source_evidence_ids,
                        confidence=max(0.5, source_confidence),
                    )
                )
            else:
                area = next(
                    (
                        fact.literal
                        for fact in facts.facts
                        if fact.fact_type == ContractFactType.PRIMARY_PRODUCT_AREA
                    ),
                    "AEM Guides behavior",
                )
                surfaces.append(
                    ChangeSurface(
                        kind=ChangeSurfaceKind.CHANGED_ENTITY,
                        entity=area,
                        source_evidence_ids=facts.source_evidence_ids,
                        confidence=0.5,
                    )
                )
        return sorted(
            {row.surface_id: row for row in surfaces}.values(),
            key=lambda row: row.surface_id,
        )

    def extract_abstract_signals(
        self, surfaces: list[ChangeSurface]
    ) -> list[AbstractSignal]:
        """Lift changed behavior into a feature-neutral semantic signal."""

        signals = [
            AbstractSignal(
                kind=AbstractSignalKind.CHANGED_BEHAVIOR,
                subject=surface.entity,
                source_surface_ids=[surface.surface_id],
                source_evidence_ids=surface.source_evidence_ids,
                confidence=surface.confidence,
            )
            for surface in surfaces
            if surface.kind == ChangeSurfaceKind.CHANGED_BEHAVIOR
        ]
        return sorted(
            {row.signal_id: row for row in signals}.values(),
            key=lambda row: row.signal_id,
        )

    def route_reasoning_patterns(
        self, signals: list[AbstractSignal]
    ) -> list[ReasoningPatternActivation]:
        """Route a changed behavior to its governing semantic question family."""

        activations = [
            ReasoningPatternActivation(
                question_family=ReasoningQuestionFamily.GOVERNING_SEMANTICS,
                semantic_dimension=SemanticDimension.GOVERNING_SEMANTICS,
                source_signal_ids=[signal.signal_id],
                subject=signal.subject,
            )
            for signal in signals
            if signal.kind == AbstractSignalKind.CHANGED_BEHAVIOR
        ]
        return sorted(
            {row.activation_id: row for row in activations}.values(),
            key=lambda row: row.activation_id,
        )

    def build_behavior_graph(
        self,
        bundle: CanonicalEvidenceBundle,
        facts: ContractFactSet,
        surfaces: list[ChangeSurface],
    ) -> BehaviorGraph:
        nodes: list[BehaviorGraphNode] = []
        edges: list[BehaviorGraphEdge] = []
        evidence_nodes: dict[str, BehaviorGraphNode] = {}
        graph_records = [
            record
            for record in bundle.records
            if not is_github_implementation_result_record(record)
        ]
        for record in graph_records:
            node = BehaviorGraphNode(
                label=record.source_reference,
                node_type="EVIDENCE_SOURCE",
                source_evidence_ids=[record.evidence_id],
                authoritative=_is_authoritative(record),
            )
            evidence_nodes[record.evidence_id] = node
            nodes.append(node)
        for fact in facts.facts:
            fact_node = BehaviorGraphNode(
                label=fact.literal[:500],
                node_type=f"CONTRACT_FACT:{fact.fact_type.value}",
                source_evidence_ids=fact.source_evidence_ids,
                authoritative=fact.authoritative,
            )
            nodes.append(fact_node)
            for evidence_id in fact.source_evidence_ids:
                source_node = evidence_nodes.get(evidence_id)
                if source_node:
                    record = next(
                        row for row in graph_records if row.evidence_id == evidence_id
                    )
                    edges.append(
                        BehaviorGraphEdge(
                            source_node_id=fact_node.node_id,
                            target_node_id=source_node.node_id,
                            relation=BehaviorRelationType.DEFINED_BY,
                            provenance_evidence_ids=[evidence_id],
                            authority_subject=fact.authority_subject,
                            authority_class=fact.authority_class,
                            currentness=record.currentness,
                            confidence=record.evidence_confidence,
                            verification_state=(
                                HypothesisState.CONFIRMED
                                if fact.authoritative
                                else HypothesisState.INFERRED_HIGH_CONFIDENCE
                            ),
                        )
                    )
        for surface in surfaces:
            surface_node = BehaviorGraphNode(
                label=surface.entity,
                node_type=f"CHANGE_SURFACE:{surface.kind.value}",
                source_evidence_ids=surface.source_evidence_ids,
            )
            nodes.append(surface_node)
            for evidence_id in surface.source_evidence_ids:
                source_node = evidence_nodes.get(evidence_id)
                if not source_node:
                    continue
                record = next(
                    row for row in graph_records if row.evidence_id == evidence_id
                )
                edges.append(
                    BehaviorGraphEdge(
                        source_node_id=surface_node.node_id,
                        target_node_id=source_node.node_id,
                        relation=_relation_for_surface(surface.kind),
                        provenance_evidence_ids=[evidence_id],
                        authority_subject=record.authority_subject
                        or AuthoritySubject.ACTUAL_IMPLEMENTATION,
                        authority_class=record.requirement_authority,
                        currentness=record.currentness,
                        confidence=surface.confidence,
                        verification_state=(
                            HypothesisState.CONFIRMED
                            if record.verification_status.value.startswith("verified")
                            else HypothesisState.INFERRED_HIGH_CONFIDENCE
                        ),
                    )
                )
        relationship_nodes: dict[tuple[str, str], BehaviorGraphNode] = {
            (row.node_type, row.label): row for row in nodes
        }
        for record in graph_records:
            for source_label, target_label, relation in _explicit_relationships(
                record.content,
                fallback_source=record.source_reference,
            ):
                source_key = ("BEHAVIOR_ENTITY", source_label)
                target_key = ("BEHAVIOR_ENTITY", target_label)
                source_node = relationship_nodes.get(source_key)
                if source_node is None:
                    source_node = BehaviorGraphNode(
                        label=source_label,
                        node_type="BEHAVIOR_ENTITY",
                        source_evidence_ids=[record.evidence_id],
                    )
                    relationship_nodes[source_key] = source_node
                    nodes.append(source_node)
                target_node = relationship_nodes.get(target_key)
                if target_node is None:
                    target_node = BehaviorGraphNode(
                        label=target_label,
                        node_type="BEHAVIOR_ENTITY",
                        source_evidence_ids=[record.evidence_id],
                    )
                    relationship_nodes[target_key] = target_node
                    nodes.append(target_node)
                edges.append(
                    BehaviorGraphEdge(
                        source_node_id=source_node.node_id,
                        target_node_id=target_node.node_id,
                        relation=relation,
                        provenance_evidence_ids=[record.evidence_id],
                        authority_subject=record.authority_subject
                        or AuthoritySubject.ACTUAL_IMPLEMENTATION,
                        authority_class=record.requirement_authority,
                        currentness=record.currentness,
                        confidence=record.evidence_confidence,
                        verification_state=(
                            HypothesisState.CONFIRMED
                            if record.evidence_confidence >= 0.8
                            and record.source_type != EvidenceSourceType.MODEL_INFERENCE
                            else HypothesisState.INFERRED_HIGH_CONFIDENCE
                        ),
                    )
                )
        return BehaviorGraph(nodes=nodes, edges=edges)

    def build_behavior_model(
        self,
        domains: list[DomainActivation],
        scope: ScopeResolution,
        surfaces: list[ChangeSurface],
        graph: BehaviorGraph,
        facts: ContractFactSet,
    ) -> CanonicalBehaviorModel:
        domain_values = [row.domain for row in domains]
        entities = list(dict.fromkeys(row.entity for row in surfaces))[:12]
        behavior_units = _semantic_text_units(
            [
                fact.literal
                for fact in facts.facts
                if fact.fact_type != ContractFactType.OUT_OF_SCOPE
            ]
            + entities
        )
        publishing = IssueDomain.PUBLISHING in domain_values
        delivery_state = ApplicabilityState.NOT_APPLICABLE
        if publishing:
            if _units_contain_any(
                behavior_units, _GENERATED_ARTIFACT_DELIVERY_SIGNALS
            ) or _units_match(
                behavior_units, _CONTEXTUAL_GENERATED_ARTIFACT_DELIVERY_RE
            ):
                delivery_state = ApplicabilityState.APPLICABLE
            elif _units_contain_any(
                behavior_units, _PUBLISHING_CONFIGURATION_ONLY_SIGNALS
            ):
                delivery_state = ApplicabilityState.NOT_APPLICABLE
            else:
                delivery_state = ApplicabilityState.UNRESOLVED
        publishing_stages = {
            stage: ApplicabilityState.NOT_APPLICABLE
            for stage in PublishingTransformationStage
        }
        if publishing:
            for stage in (
                PublishingTransformationStage.PRESET,
                PublishingTransformationStage.PROFILE_CONFIG,
            ):
                publishing_stages[stage] = ApplicabilityState.APPLICABLE
            for stage in PublishingTransformationStage:
                if stage not in {
                    PublishingTransformationStage.PRESET,
                    PublishingTransformationStage.PROFILE_CONFIG,
                }:
                    publishing_stages[stage] = delivery_state
        oracles = (
            [
                GeneratedOutputOracle.ARTIFACT_EXISTS,
                GeneratedOutputOracle.CONTENT_CORRECT,
                GeneratedOutputOracle.HIERARCHY_CORRECT,
                GeneratedOutputOracle.LINKS_CORRECT,
                GeneratedOutputOracle.METADATA_CORRECT,
                GeneratedOutputOracle.OUTPUT_PATH_CORRECT,
                GeneratedOutputOracle.NO_DUPLICATES,
                GeneratedOutputOracle.NO_ORPHANS,
                GeneratedOutputOracle.NO_STALE_OUTPUT,
                GeneratedOutputOracle.STATUS_MATCHES_REAL_OUTPUT,
            ]
            if delivery_state == ApplicabilityState.APPLICABLE
            else []
        )
        conditional_oracles = {
            "title": GeneratedOutputOracle.TITLE_CORRECT,
            "order": GeneratedOutputOracle.ORDER_CORRECT,
            "navigation": GeneratedOutputOracle.NAVIGATION_CORRECT,
            "locale": GeneratedOutputOracle.LOCALE_CORRECT,
            "activation": GeneratedOutputOracle.ACTIVATION_STATE_CORRECT,
            "unchanged": GeneratedOutputOracle.UNCHANGED_CONTENT_NOT_REWRITTEN,
        }
        if delivery_state == ApplicabilityState.APPLICABLE:
            oracles.extend(
                oracle
                for signal, oracle in conditional_oracles.items()
                if any(signal in unit for unit in behavior_units)
            )
        lifecycle_signals: dict[LifecycleOperation, tuple[str, ...]] = {
            LifecycleOperation.FIRST_GENERATION: ("first generation",),
            LifecycleOperation.REGENERATION: ("regeneration", "regenerate"),
            LifecycleOperation.NO_CHANGE_REGENERATION: ("no-change", "no change"),
            LifecycleOperation.UPDATE: ("update",),
            LifecycleOperation.DELETE: ("delete", "removed"),
            LifecycleOperation.MOVE: ("move",),
            LifecycleOperation.RENAME: ("rename",),
            LifecycleOperation.SAVE_REOPEN: ("save", "reopen"),
            LifecycleOperation.REFRESH: ("refresh", "reload"),
            LifecycleOperation.REPUBLISH: ("republish",),
            LifecycleOperation.ACTIVATION: ("activation", "activate"),
            LifecycleOperation.CANCEL: ("cancel",),
            LifecycleOperation.RETRY: ("retry",),
            LifecycleOperation.FAILURE_THEN_RECOVERY: ("recovery", "recover"),
            LifecycleOperation.REPEATED_MEANINGFUL_CHANGES: ("repeated",),
        }
        lifecycle = [
            operation
            for operation, signals in lifecycle_signals.items()
            if any(signal in unit for unit in behavior_units for signal in signals)
        ]
        return CanonicalBehaviorModel(
            primary_entities=entities,
            domains=domain_values,
            graph=graph,
            publishing_transformation_stages=publishing_stages,
            generated_artifact_delivery=delivery_state,
            generated_output_oracles=list(dict.fromkeys(oracles)),
            lifecycle_operations=lifecycle,
        )

    def expand_behavioral_coverage(
        self,
        model: CanonicalBehaviorModel,
        surfaces: list[ChangeSurface],
        facts: ContractFactSet,
    ) -> BehavioralCoverageExpansion:
        """Widen *discovery* to the behaviors that depend on the stated ask.

        The literal requirement is never the whole product contract: a named
        field is not atomic until its provenance, absence, indirect resolution,
        identity changes, contexts and consumer surfaces have been considered.
        This stage derives those dependent behaviors from requirement shape
        alone, so the same reasoning applies to any feature family.

        Discovery is not acceptance.  Nothing here promotes an acceptance
        criterion; it only makes a dependent behavior material so the existing
        closure, research and promotion pipeline must dispose of it explicitly.
        """

        entities = list(dict.fromkeys(row.entity for row in surfaces))[:12]
        units = _semantic_text_units(
            [
                fact.literal
                for fact in facts.facts
                if fact.fact_type != ContractFactType.OUT_OF_SCOPE
            ]
            + entities
            + list(model.primary_entities or [])
        )
        triggers: set[CoverageExpansionTrigger] = {
            trigger
            for trigger, signals in _EXPANSION_TRIGGER_SIGNALS.items()
            if _units_contain_any(units, signals)
        }
        consumer_surfaces = {
            row.entity
            for row in surfaces
            if row.kind
            in {
                ChangeSurfaceKind.CONSUMERS,
                ChangeSurfaceKind.DOWNSTREAM_DECISION_CONSUMERS,
            }
        }
        # Two independent readings of the same behavior can diverge, whether the
        # second surface is declared structurally or implied by the requirement
        # describing both a displayed and an exported form of one value.
        if len(consumer_surfaces) > 1 or {
            CoverageExpansionTrigger.DISPLAYED_VALUE,
            CoverageExpansionTrigger.EXPORTED_VALUE,
        } <= triggers:
            triggers.add(CoverageExpansionTrigger.MULTIPLE_CONSUMER_SURFACES)

        subjects = list(dict.fromkeys((model.primary_entities or []) + entities))[:4]
        if not subjects:
            subjects = ["the requested behavior"]

        axis_triggers: dict[CoverageExpansionAxis, CoverageExpansionTrigger] = {}
        for trigger in sorted(triggers, key=lambda row: row.value):
            for axis in _EXPANSION_TRIGGER_AXES[trigger]:
                axis_triggers.setdefault(axis, trigger)

        candidates: list[BehavioralCoverageCandidate] = []
        for axis, trigger in sorted(
            axis_triggers.items(), key=lambda item: item[0].value
        ):
            for subject in subjects:
                candidates.append(
                    BehavioralCoverageCandidate(
                        axis=axis,
                        subject=subject,
                        trigger=trigger,
                        dimensions=list(_EXPANSION_AXIS_DIMENSIONS[axis]),
                        question=_EXPANSION_AXIS_QUESTION[axis].format(subject=subject),
                        rationale=_EXPANSION_AXIS_RATIONALE[axis],
                    )
                )
        return BehavioralCoverageExpansion(
            candidates=candidates,
            triggers=sorted(triggers, key=lambda row: row.value),
            dependency_records=self._record_semantic_dependencies(
                candidates, activated_axes=set(axis_triggers)
            ),
        )

    def _record_semantic_dependencies(
        self,
        candidates: list[BehavioralCoverageCandidate],
        *,
        activated_axes: set[CoverageExpansionAxis],
    ) -> list[SemanticDependencyRecord]:
        """Give every material subject an explicit, total dependency record.

        Completeness here means *decided*, not *covered*: a dependency whose
        axis evidence never fired is recorded ``NOT_APPLICABLE`` with the
        concrete reason, and a dependency discovery did raise is recorded
        ``RESEARCH_REQUIRED`` and handed to the existing question/research
        pipeline.  Nothing is promoted, and no dependency can be dropped by
        staying silent.
        """

        by_subject: dict[str, list[BehavioralCoverageCandidate]] = defaultdict(list)
        for candidate in candidates:
            if candidate.material:
                by_subject[candidate.subject].append(candidate)

        records: list[SemanticDependencyRecord] = []
        for subject, subject_candidates in sorted(by_subject.items()):
            candidates_by_axis: dict[
                CoverageExpansionAxis, list[BehavioralCoverageCandidate]
            ] = defaultdict(list)
            for candidate in subject_candidates:
                candidates_by_axis[candidate.axis].append(candidate)

            slots: list[SemanticDependencySlot] = []
            for kind in SemanticDependencyKind:
                axis = _DEPENDENCY_KIND_AXIS[kind]
                matched = candidates_by_axis.get(axis, [])
                if matched:
                    slots.append(
                        SemanticDependencySlot(
                            kind=kind,
                            disposition=(
                                CoverageExpansionDisposition.RESEARCH_REQUIRED
                            ),
                            reason=_DEPENDENCY_KIND_RESEARCH_REASON[kind],
                            dimensions=sorted(
                                {
                                    dimension
                                    for candidate in matched
                                    for dimension in candidate.dimensions
                                },
                                key=lambda row: row.value,
                            ),
                            candidate_ids=[row.candidate_id for row in matched],
                        )
                    )
                    continue
                slots.append(
                    SemanticDependencySlot(
                        kind=kind,
                        disposition=CoverageExpansionDisposition.NOT_APPLICABLE,
                        reason=_DEPENDENCY_KIND_NOT_APPLICABLE_REASON[kind],
                    )
                )
            records.append(SemanticDependencyRecord(subject=subject, slots=slots))
        return records

    def explore_semantic_closure(
        self,
        bundle: CanonicalEvidenceBundle,
        model: CanonicalBehaviorModel,
        signals: list[AbstractSignal] | None = None,
        activations: list[ReasoningPatternActivation] | None = None,
        mandatory_families: list[MandatoryInvestigationFamily] | None = None,
        expansion: BehavioralCoverageExpansion | None = None,
    ) -> list[ClosureDimensionResult]:
        signals = signals or []
        activations = activations or []
        mandatory_families = mandatory_families or []
        applicable = self.applicable_semantic_dimensions(
            bundle, model, expansion=expansion
        )
        applicable.update(
            row.family_id
            for row in mandatory_families
            if row.activation_decision
            in {
                FamilyActivationDecision.ACTIVATE_BLOCKING,
                FamilyActivationDecision.ACTIVATE_NON_BLOCKING,
            }
        )
        unresolved_activation_dimensions = {
            row.family_id
            for row in mandatory_families
            if row.activation_decision
            == FamilyActivationDecision.UNRESOLVED_APPLICABILITY
        }
        rows: list[ClosureDimensionResult] = []
        activated_subjects = [
            activation.subject
            for activation in activations
            if activation.question_family == ReasoningQuestionFamily.GOVERNING_SEMANTICS
            and any(
                signal.signal_id in activation.source_signal_ids for signal in signals
            )
        ]
        entities = list(
            dict.fromkeys((model.primary_entities or []) + activated_subjects)
        ) or ["AEM Guides behavior"]
        for entity in entities:
            for dimension in SemanticDimension:
                is_applicable = dimension in applicable
                applicability_unresolved = (
                    dimension in unresolved_activation_dimensions
                    or (
                        dimension == SemanticDimension.GENERATED_OUTPUT
                        and model.generated_artifact_delivery
                        == ApplicabilityState.UNRESOLVED
                    )
                )
                # A keyword hit proves the record shares vocabulary with the
                # dimension, not that it answers it for the change under test.
                # Most of a bundle is retrieved documentation, so treating any
                # hit as resolution marked nearly every dimension covered and
                # the question was never asked.  Corpus hits stay attached as
                # topic evidence; only change-bound evidence resolves.
                evidence_ids: list[str] = []
                resolving_ids: list[str] = []
                for record in bundle.records:
                    text = _record_text(record).casefold()
                    if not any(
                        keyword in text
                        for keyword in _DIMENSION_KEYWORDS[dimension]
                    ):
                        continue
                    evidence_ids.append(record.evidence_id)
                    if record.source_type in _CHANGE_BOUND_SOURCES:
                        resolving_ids.append(record.evidence_id)
                if applicability_unresolved:
                    disposition = ClosureDisposition.UNRESOLVED_AND_EXPOSED
                    rationale = (
                        "Current applicability is unresolved, so this material family "
                        "cannot be silently activated or discarded."
                    )
                elif not is_applicable:
                    disposition = ClosureDisposition.NOT_APPLICABLE
                    rationale = (
                        "The activated domains do not make this dimension material."
                    )
                elif resolving_ids:
                    disposition = ClosureDisposition.COVERED
                    rationale = "Direct supplied evidence addresses this dimension."
                elif evidence_ids:
                    disposition = ClosureDisposition.UNRESOLVED_AND_EXPOSED
                    rationale = (
                        "Retrieved documentation shares this dimension's vocabulary "
                        "but no evidence bound to the change under test resolves it."
                    )
                else:
                    disposition = ClosureDisposition.UNRESOLVED_AND_EXPOSED
                    rationale = "The dimension is applicable but the supplied evidence does not resolve it."
                rows.append(
                    ClosureDimensionResult(
                        entity=entity,
                        dimension=dimension,
                        applicability=(
                            ApplicabilityState.UNRESOLVED
                            if applicability_unresolved
                            else ApplicabilityState.APPLICABLE
                            if is_applicable
                            else ApplicabilityState.NOT_APPLICABLE
                        ),
                        disposition=disposition,
                        evidence_ids=evidence_ids,
                        rationale=rationale,
                    )
                )
        return rows

    def applicable_semantic_dimensions(
        self,
        bundle: CanonicalEvidenceBundle,
        model: CanonicalBehaviorModel,
        expansion: BehavioralCoverageExpansion | None = None,
    ) -> set[SemanticDimension]:
        """Return the existing deterministic domain/model family set."""

        combined = " ".join(
            _record_text(record) for record in bundle.records
        ).casefold()
        domains = set(model.domains)
        dita_like = bool(
            re.search(
                r"\b(dita|topicref|mapref|bookmap|ditaval|attribute|specialization)\b",
                combined,
            )
        )
        publishing = IssueDomain.PUBLISHING in domains
        ui = bool(_UI_SOURCES & {record.source_type for record in bundle.records})
        implementation = bool(
            _IMPLEMENTATION_SOURCES & {record.source_type for record in bundle.records}
        )
        applicable: set[SemanticDimension] = {
            SemanticDimension.GOVERNING_SEMANTICS,
            SemanticDimension.POSITIVE_STATE,
            SemanticDimension.NEGATIVE_STATE,
            SemanticDimension.LIFECYCLE,
            SemanticDimension.VERSION_APPLICABILITY,
            SemanticDimension.DEPLOYMENT_APPLICABILITY,
        }
        if dita_like:
            applicable.update(
                {
                    SemanticDimension.CONTROLLING_ATTRIBUTES,
                    SemanticDimension.PARENT_CONTEXT,
                    SemanticDimension.CHILD_CONTEXT,
                    SemanticDimension.HIERARCHY,
                    SemanticDimension.SPECIALIZATIONS,
                    SemanticDimension.REFERENCED_CONTENT,
                    SemanticDimension.NESTED_REFERENCED_CONTENT,
                    SemanticDimension.FALLBACK,
                    SemanticDimension.ABSENT_VALUE,
                    SemanticDimension.INVALID_VALUE,
                }
            )
        if publishing:
            applicable.update(
                {
                    SemanticDimension.GOVERNING_CONFIGURATION,
                    SemanticDimension.REFERENCED_CONTENT,
                    SemanticDimension.DOWNSTREAM_PROCESSOR,
                    SemanticDimension.PERSISTED_STATE,
                }
            )
        if model.generated_artifact_delivery == ApplicabilityState.APPLICABLE:
            applicable.add(SemanticDimension.GENERATED_OUTPUT)
        if ui:
            applicable.update(
                {
                    SemanticDimension.GOVERNING_CONFIGURATION,
                    SemanticDimension.CROSS_SURFACE_SYNC,
                    SemanticDimension.ROLE_PROFILE_APPLICABILITY,
                    SemanticDimension.FALLBACK,
                }
            )
        if implementation:
            applicable.update(
                {
                    SemanticDimension.DIRECT_CONSUMERS,
                    SemanticDimension.SIBLING_CONSUMERS,
                    SemanticDimension.DOWNSTREAM_PROCESSOR,
                    SemanticDimension.PERSISTED_STATE,
                }
            )
        if expansion is not None:
            # Behavioral coverage expansion only widens what must be decided.
            # It never marks a dimension covered and never promotes anything.
            applicable.update(expansion.activated_dimensions)
        return applicable

    def generate_missing_questions(
        self,
        closure: list[ClosureDimensionResult],
        scope: ScopeResolution,
        facts: ContractFactSet,
        investigation: QeInvestigationPreparation | None = None,
        bundle: CanonicalEvidenceBundle | None = None,
    ) -> list[MissingQuestion]:
        questions: list[MissingQuestion] = []
        families = {
            row.family_id: row
            for row in (investigation.mandatory_families if investigation else [])
            if row.activation_decision != FamilyActivationDecision.DO_NOT_ACTIVATE
        }
        unresolved_by_dimension: dict[
            SemanticDimension, list[ClosureDimensionResult]
        ] = defaultdict(list)
        for row in closure:
            if row.disposition == ClosureDisposition.UNRESOLVED_AND_EXPOSED:
                unresolved_by_dimension[row.dimension].append(row)
        for dimension, unresolved_rows in sorted(
            unresolved_by_dimension.items(), key=lambda item: item[0].value
        ):
            subject = _subject_for_dimension(dimension)
            raw_entities = list(
                dict.fromkeys(row.entity for row in unresolved_rows)
            )
            clean_entities = [
                entity for entity in raw_entities if _human_question_safe(entity)
            ]
            # UX1: raw evidence entities (grep fragments, paths, token dumps)
            # never reach human question text.  When every entity is raw, the
            # question is projected to its typed behavior dimension; the raw
            # evidence stays in the trace via source_closure_ids.
            #
            # #51: the per-entity check is not enough - joining many
            # individually clean tokens reconstitutes a comma dump
            # ("skip_feature_if_flag, before_feature, 2688, ...").  More than
            # two joined entities is an enumeration dump, so the question
            # names the typed behavior dimension instead; the final question
            # text is re-validated as a fail-safe either way.
            #
            # A subject-less question cannot be researched: a worker asked
            # "where does the value shown for the affected behavior come from"
            # has nothing to look up and returns NOT_APPLICABLE, so the
            # mandated research never happens.  Entities that survive the raw
            # check but still name a test fixture or test method are the same
            # defect with a misleading subject.  Both cases fall back to the
            # subject the issue itself states, and only an issue that names no
            # subject at all keeps the generic wording.
            subject_entities = [
                entity for entity in clean_entities if _product_subject_safe(entity)
            ]
            if 1 <= len(subject_entities) <= 2:
                entity_text = ", ".join(subject_entities)
            else:
                entity_text = (
                    _behavior_subject_from_facts(facts) or "the affected behavior"
                )
            question_text = _QUESTION_TEXT[dimension].format(entity=entity_text)
            if not _human_question_safe(question_text):
                fallback_subject = (
                    _behavior_subject_from_facts(facts) or "the affected behavior"
                )
                question_text = _QUESTION_TEXT[dimension].format(
                    entity=fallback_subject
                )
                if not _human_question_safe(question_text):
                    question_text = _QUESTION_TEXT[dimension].format(
                        entity="the affected behavior"
                    )
            family = families.get(dimension)
            target_sources = list(_target_sources(subject))
            if family is not None:
                for source in family.preferred_evidence_sources:
                    if source not in target_sources:
                        target_sources.append(source)
            # Closure already decided this dimension is applicable and left it
            # unresolved for a material entity; that decision is the materiality
            # judgement.  Falling back to the schema's P2 default re-decides it
            # here as immaterial, which classifies the mandated research
            # NOT_APPLICABLE and means the question is never researched at all.
            family_materiality = (
                family.materiality if family is not None else None
            )
            dimension_materiality = (
                family_materiality
                if family_materiality is InvestigationMateriality.P0
                else InvestigationMateriality.P1
            )
            questions.append(
                MissingQuestion(
                    question=question_text,
                    dimension=dimension,
                    authority_subject=subject,
                    target_source_types=target_sources,
                    materiality=dimension_materiality,
                    blocking=(
                        family.activation_decision
                        == FamilyActivationDecision.ACTIVATE_BLOCKING
                        if family
                        else False
                    ),
                    open_question_class=(
                        OpenQuestionClass.USER_ACCEPTANCE_DECISION
                        if family is not None
                        and family.activation_decision
                        == FamilyActivationDecision.ACTIVATE_BLOCKING
                        else OpenQuestionClass.RESEARCH_REQUIRED
                    ),
                    source_closure_ids=[row.closure_id for row in unresolved_rows],
                    investigation_terms=raw_entities,
                )
            )
        for field in scope.unresolved_fields:
            question, blocking = _SCOPE_FIELD_QUESTIONS.get(
                field, (f"What is the intended value for {field}?", True)
            )
            questions.append(
                MissingQuestion(
                    question=question,
                    authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                    target_source_types=_target_sources(
                        AuthoritySubject.PRODUCT_CONTRACT
                    ),
                    blocking=blocking,
                    open_question_class=OpenQuestionClass.USER_ACCEPTANCE_DECISION,
                )
            )
        # Research-first materiality probes (UX1/materiality gate): a dimension
        # mentioned in evidence without an established behavior interaction is
        # researched ("does it change this behavior?") before any value/scope
        # question may reach the human.  Non-blocking; never a TBD; never a
        # promotion block.
        for field, decision in sorted(scope.dimension_materiality.items()):
            if not decision.startswith("UNRESOLVED_MATERIALITY"):
                continue
            label = _SCOPE_FIELD_DIMENSION_LABELS.get(field, field)
            questions.append(
                MissingQuestion(
                    question=(
                        f"Does {label} change the behavior under acceptance "
                        "here, given that existing evidence mentions it "
                        "without establishing an interaction?"
                    ),
                    authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
                    target_source_types=sorted(
                        {
                            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
                            EvidenceSourceType.DITA_SPECIFICATION,
                            EvidenceSourceType.DITA_OT_DOCUMENTATION,
                            EvidenceSourceType.CURRENT_CODE,
                            EvidenceSourceType.CURRENT_PR,
                            EvidenceSourceType.IMPLEMENTATION_DIFF,
                        },
                        key=lambda row: row.value,
                    ),
                    blocking=False,
                    open_question_class=OpenQuestionClass.RESEARCH_REQUIRED,
                    materiality=InvestigationMateriality.P1,
                )
            )
        for fact in facts.facts:
            if fact.fact_type != ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED:
                continue
            questions.append(
                MissingQuestion(
                    question=f'What exact product behavior does the human term "{fact.literal}" mean?',
                    authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                    target_source_types=_target_sources(
                        AuthoritySubject.PRODUCT_CONTRACT
                    ),
                    blocking=True,
                    open_question_class=OpenQuestionClass.USER_ACCEPTANCE_DECISION,
                    source_fact_ids=[fact.fact_id],
                )
            )
        # P2: an established problem with no established solution earns exactly
        # one neutral product-decision question - it names the gap and never
        # embeds a proposed solution.
        problem_facts = [
            fact
            for fact in facts.facts
            if fact.fact_type == ContractFactType.PROBLEM_STATEMENT
            and fact.authoritative
        ]
        # The gap anchor is the ticket's own problem statement, chosen
        # deterministically: description/current-ticket sources before
        # comments before attachments before anything else, then fact id.
        # Extraction order must never pick the anchor (run-to-run identity
        # stability), and a quoted implementation step inside a comment is
        # not the customer problem.
        _ANCHOR_SOURCE_RANK = {
            EvidenceSourceType.JIRA_DESCRIPTION: 0,
            EvidenceSourceType.CURRENT_JIRA: 0,
            EvidenceSourceType.CUSTOMER_REQUEST: 0,
            EvidenceSourceType.BUSINESS_IMPACT: 0,
            EvidenceSourceType.JIRA_COMMENT: 2,
            EvidenceSourceType.LINKED_JIRA: 2,
            EvidenceSourceType.JIRA_ATTACHMENT: 3,
            EvidenceSourceType.SCREENSHOT_REPRODUCTION: 3,
        }
        if bundle is not None and problem_facts:
            record_type_by_id = {
                record.evidence_id: record.source_type
                for record in bundle.records
            }

            def _anchor_rank(fact) -> tuple[int, str]:
                ranks = [
                    _ANCHOR_SOURCE_RANK.get(
                        record_type_by_id.get(evidence_id), 1
                    )
                    for evidence_id in fact.source_evidence_ids
                ]
                return (min(ranks, default=1), fact.fact_id)

            problem_facts = sorted(problem_facts, key=_anchor_rank)
        if (
            problem_facts
            and facts.contract_mode != ContractMode.HUMAN_ACCEPTED_CONTRACT
        ):
            problem_tokens: set[str] = set()
            for fact in problem_facts:
                problem_tokens |= _content_tokens(fact.literal)
            solution_authorities = {
                AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
                AuthorityClass.CONFIRMED_PRODUCT_DECISION,
                AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
                AuthorityClass.SPECIFICATION_AUTHORITY,
            }
            # A retrieved documentation/spec record carries specification-grade
            # authority for WHAT IT DOCUMENTS, but it is not the ticket's
            # answer: only facts sourced from the ticket's own accepted
            # records (accepted UAC / product or engineering decision) may
            # establish that the reported gap is already addressed.
            accepted_evidence_ids: set[str] | None = None
            if bundle is not None:
                accepted_evidence_ids = {
                    record.evidence_id
                    for record in bundle.records
                    if record.source_type
                    in {
                        EvidenceSourceType.ACCEPTED_UAC,
                        EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
                        EvidenceSourceType.PRODUCT_DECISION,
                        EvidenceSourceType.ENGINEERING_DECISION,
                    }
                }
            solution_established = any(
                fact.authority_class in solution_authorities
                and fact.fact_type != ContractFactType.PROBLEM_STATEMENT
                and not _content_tokens(fact.literal) <= problem_tokens
                and (
                    accepted_evidence_ids is None
                    or bool(
                        set(fact.source_evidence_ids) & accepted_evidence_ids
                    )
                )
                for fact in facts.facts
            )
            if not solution_established:
                anchor = re.sub(
                    r"^(?:description|summary|title)\s*:\s*",
                    "",
                    problem_facts[0].literal.strip(),
                    flags=re.IGNORECASE,
                ).rstrip(".")
                # Truncate at a word boundary so the question never ends
                # mid-word.
                if len(anchor) > 160:
                    anchor = anchor[:160].rsplit(" ", 1)[0].rstrip()
                questions.append(
                    MissingQuestion(
                        question=(
                            "Which established product behavior or product "
                            f"decision addresses this gap: {anchor}?"
                        ),
                        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                        target_source_types=_target_sources(
                            AuthoritySubject.PRODUCT_CONTRACT
                        ),
                        blocking=True,
                        open_question_class=(
                            OpenQuestionClass.USER_ACCEPTANCE_DECISION
                        ),
                        source_fact_ids=[problem_facts[0].fact_id],
                    )
                )
        # UX1: equivalent questions (identical canonical text, e.g. several
        # raw-fragment entities projected to the same typed dimension)
        # collapse to one question; their internal lineage and investigation
        # terms merge so no evidence binding is silently discarded.
        deduped: dict[str, MissingQuestion] = {}
        for row in questions:
            existing = deduped.get(row.question_id)
            if existing is None:
                deduped[row.question_id] = row
                continue
            merged = existing.model_copy(
                update={
                    "source_closure_ids": sorted(
                        set(existing.source_closure_ids)
                        | set(row.source_closure_ids)
                    ),
                    "source_fact_ids": sorted(
                        set(existing.source_fact_ids) | set(row.source_fact_ids)
                    ),
                    "investigation_terms": sorted(
                        set(existing.investigation_terms)
                        | set(row.investigation_terms)
                    ),
                }
            )
            deduped[row.question_id] = merged
        return sorted(deduped.values(), key=lambda row: row.question_id)

    def admit_clarifications(
        self,
        raw_clarifications: list[dict[str, Any]],
        questions: list[MissingQuestion],
    ) -> tuple[list[HumanClarification], list[str]]:
        """Admit human clarifications against this run's exact questions.

        A clarification binds one question (by deterministic id or scope-field
        alias) at one revision.  Rules: unknown binding -> REJECTED; revision
        mismatch -> STALE (never silently rebound); authority outside the
        establishing set -> REJECTED; two clarifications with different answers
        for the same question -> both REJECTED (contradictory); otherwise
        ADMITTED.  Malformed entries become errors, never silent drops.
        """

        by_id = {row.question_id: row for row in questions}
        alias_fields: dict[str, str] = {}
        for field in _SCOPE_FIELD_QUESTIONS:
            alias_fields[field] = field
            alias_fields[scope_question_id(field)] = field

        parsed: list[HumanClarification] = []
        errors: list[str] = []
        for index, raw in enumerate(raw_clarifications):
            try:
                parsed.append(HumanClarification.model_validate(raw))
            except Exception as exc:
                errors.append(
                    f"human_clarifications[{index}] is not a valid clarification: "
                    f"{exc.__class__.__name__}"
                )

        results: list[HumanClarification] = []
        groups: dict[str, list[HumanClarification]] = defaultdict(list)
        for row in parsed:
            if row.question_ref in by_id:
                groups[by_id[row.question_ref].question_id].append(row)
            elif row.question_ref in alias_fields:
                groups[alias_fields[row.question_ref]].append(row)
            else:
                row.status = ClarificationStatus.REJECTED
                row.admission_detail = (
                    "the bound question does not exist in this run - a "
                    "clarification is evidence for its exact question only"
                )
                results.append(row)

        for key, rows in sorted(groups.items()):
            question = by_id.get(key)
            expected_revision = (
                question.question_revision
                if question is not None
                else scope_question_revision(key)
            )
            admitted_candidates: list[HumanClarification] = []
            for row in rows:
                if row.question_revision != expected_revision:
                    row.status = ClarificationStatus.STALE
                    row.admission_detail = (
                        "the question revision changed after the clarification "
                        "was recorded - not rebound"
                    )
                    results.append(row)
                    continue
                if row.authority_role not in _CLARIFICATION_ESTABLISHING_AUTHORITIES:
                    row.status = ClarificationStatus.REJECTED
                    row.admission_detail = (
                        f"authority {row.authority_role.value} cannot establish "
                        f"a {row.answer_classification.value} answer"
                    )
                    results.append(row)
                    continue
                admitted_candidates.append(row)
            answers = {
                _normalize_clarification_answer(row.answer)
                for row in admitted_candidates
            }
            if len(answers) > 1:
                for row in admitted_candidates:
                    row.status = ClarificationStatus.REJECTED
                    row.admission_detail = (
                        "contradictory clarifications for the same question - "
                        "the disagreement is preserved, not chosen"
                    )
                    results.append(row)
                continue
            for row in admitted_candidates:
                row.status = ClarificationStatus.ADMITTED
                row.admission_detail = (
                    f"admitted for question {key}"
                    + (
                        " (consumed during scope resolution)"
                        if question is None
                        else ""
                    )
                )
                results.append(row)
        return sorted(results, key=lambda row: row.clarification_id), errors

    def build_question_generation_trace(
        self,
        *,
        bundle: CanonicalEvidenceBundle,
        facts: ContractFactSet,
        surfaces: list[ChangeSurface],
        signals: list[AbstractSignal],
        activations: list[ReasoningPatternActivation],
        closure: list[ClosureDimensionResult],
        questions: list[MissingQuestion],
        investigation: QeInvestigationPreparation | None = None,
    ) -> QuestionGenerationDiagnosticTrace:
        """Build ordered, content-minimal proof of question-generation lineage."""

        current_issue_evidence_ids = {
            record.evidence_id
            for record in bundle.records
            if record.source_type in _CURRENT_ISSUE_BEHAVIOR_SOURCES
        }
        material_behavior_expected = (
            _material_behavior_fact(
                facts,
                allowed_evidence_ids=current_issue_evidence_ids,
            )
            is not None
        )
        behavior_surfaces = [
            row for row in surfaces if row.kind == ChangeSurfaceKind.CHANGED_BEHAVIOR
        ]
        governing_activations = [
            row
            for row in activations
            if row.question_family == ReasoningQuestionFamily.GOVERNING_SEMANTICS
        ]
        governing_subjects = {row.subject for row in governing_activations}
        governing_closure = [
            row
            for row in closure
            if row.dimension == SemanticDimension.GOVERNING_SEMANTICS
            and row.entity in governing_subjects
        ]
        governing_questions = [
            row
            for row in questions
            if row.dimension == SemanticDimension.GOVERNING_SEMANTICS
            and any(subject in row.question for subject in governing_subjects)
        ]

        surface_failure = (
            QuestionGenerationFailureReason.SIGNAL_MISSING
            if material_behavior_expected and not behavior_surfaces
            else None
        )
        signal_failure = (
            QuestionGenerationFailureReason.SIGNAL_MISSING
            if material_behavior_expected and behavior_surfaces and not signals
            else None
        )
        router_failure = (
            QuestionGenerationFailureReason.PATTERN_NOT_ACTIVATED
            if signals and not governing_activations
            else None
        )
        closure_failure = (
            QuestionGenerationFailureReason.CLOSURE_TRAVERSAL_STOPPED
            if governing_activations and not governing_closure
            else None
        )
        unresolved_governing = [
            row
            for row in governing_closure
            if row.disposition == ClosureDisposition.UNRESOLVED_AND_EXPOSED
        ]
        question_failure = (
            QuestionGenerationFailureReason.QUESTION_FAMILY_NOT_GENERATED
            if unresolved_governing and not governing_questions
            else None
        )

        steps = [
            QuestionGenerationTraceStep(
                stage=QuestionGenerationTraceStage.CHANGE_SURFACE_EXTRACTOR,
                sequence=1,
                outcome=(
                    QuestionGenerationStepOutcome.FAILED
                    if surface_failure
                    else QuestionGenerationStepOutcome.PRODUCED
                    if behavior_surfaces
                    else QuestionGenerationStepOutcome.NO_MATERIAL_SIGNAL
                ),
                input_ids=facts.source_evidence_ids,
                output_ids=[row.surface_id for row in behavior_surfaces],
                failure_reason=surface_failure,
                detail_code=(
                    "SOURCE_ANCHORED_CHANGED_BEHAVIOR"
                    if behavior_surfaces
                    else "NO_MATERIAL_CHANGED_BEHAVIOR"
                ),
            ),
            QuestionGenerationTraceStep(
                stage=QuestionGenerationTraceStage.ABSTRACT_SIGNAL_EXTRACTOR,
                sequence=2,
                outcome=(
                    QuestionGenerationStepOutcome.FAILED
                    if signal_failure
                    else QuestionGenerationStepOutcome.PRODUCED
                    if signals
                    else QuestionGenerationStepOutcome.NO_MATERIAL_SIGNAL
                ),
                input_ids=[row.surface_id for row in behavior_surfaces],
                output_ids=[row.signal_id for row in signals],
                failure_reason=signal_failure,
                detail_code="CHANGED_BEHAVIOR_SIGNAL",
            ),
            QuestionGenerationTraceStep(
                stage=QuestionGenerationTraceStage.REASONING_PATTERN_ROUTER,
                sequence=3,
                outcome=(
                    QuestionGenerationStepOutcome.FAILED
                    if router_failure
                    else QuestionGenerationStepOutcome.ACTIVATED
                    if governing_activations
                    else QuestionGenerationStepOutcome.NO_MATERIAL_SIGNAL
                ),
                input_ids=[row.signal_id for row in signals],
                output_ids=[row.activation_id for row in governing_activations],
                failure_reason=router_failure,
                detail_code="CHANGED_BEHAVIOR_TO_GOVERNING_SEMANTICS",
            ),
            QuestionGenerationTraceStep(
                stage=(
                    QuestionGenerationTraceStage.SEMANTIC_BEHAVIORAL_CLOSURE_EXPLORER
                ),
                sequence=4,
                outcome=(
                    QuestionGenerationStepOutcome.FAILED
                    if closure_failure
                    else QuestionGenerationStepOutcome.TRAVERSED
                    if governing_closure
                    else QuestionGenerationStepOutcome.NO_MATERIAL_SIGNAL
                ),
                input_ids=[row.activation_id for row in governing_activations],
                output_ids=[row.closure_id for row in governing_closure],
                failure_reason=closure_failure,
                detail_code="GOVERNING_SEMANTICS_CLOSURE",
            ),
            QuestionGenerationTraceStep(
                stage=QuestionGenerationTraceStage.MISSING_QUESTION_GENERATOR,
                sequence=5,
                outcome=(
                    QuestionGenerationStepOutcome.FAILED
                    if question_failure
                    else QuestionGenerationStepOutcome.GENERATED
                    if governing_questions
                    else QuestionGenerationStepOutcome.RESOLVED_WITHOUT_QUESTION
                    if governing_closure and not unresolved_governing
                    else QuestionGenerationStepOutcome.NO_MATERIAL_SIGNAL
                ),
                input_ids=[row.closure_id for row in governing_closure],
                output_ids=[row.question_id for row in governing_questions],
                failure_reason=question_failure,
                detail_code="GOVERNING_SEMANTICS_QUESTION_FAMILY",
            ),
        ]
        first_failure = next(
            (row.failure_reason for row in steps if row.failure_reason), None
        )
        return QuestionGenerationDiagnosticTrace(
            steps=steps,
            earliest_failure=first_failure,
            recovered_failure=(
                QuestionGenerationFailureReason.SIGNAL_MISSING
                if behavior_surfaces
                else None
            ),
            governing_pattern_ids=[row.pattern_id for row in governing_activations],
            pattern_provider_status=(
                investigation.pattern_lookup.status if investigation else None
            ),
            matched_human_pattern_ids=(
                [row.pattern_id for row in investigation.matched_human_patterns]
                if investigation
                else []
            ),
            mandatory_family_ids=(
                [
                    row.family_id
                    for row in investigation.mandatory_families
                    if row.activation_decision
                    != FamilyActivationDecision.DO_NOT_ACTIVATE
                ]
                if investigation
                else []
            ),
            family_activation_decisions=(
                {
                    row.family_id: row.activation_decision
                    for row in investigation.mandatory_families
                }
                if investigation
                else {}
            ),
        )

    def classify_research_requirements(
        self,
        questions: list[MissingQuestion],
        facts: ContractFactSet,
    ) -> list[ResearchRequirementRecord]:
        """Classify the mandatory research route of every planned question.

        Runs immediately after question planning and before any directed
        research, so the Coverage Reasoner can prove a documentation- or
        implementation-dependent question was never answered from inference
        alone.  This ticket-level batch is a thin loop over the reusable
        per-question routing contract in ``QUESTION_RESEARCH_ROUTER``; a later
        Question Planner invokes the same contract one question at a time.
        Source authority is not changed: classification only names the research
        the question's own evidence path already requires.
        """

        router = QUESTION_RESEARCH_ROUTER
        return [
            router.classify(
                router.build_request(question),
                question=question,
                contract_mode=facts.contract_mode,
            )
            for question in sorted(questions, key=lambda row: row.question_id)
        ]

    def resolve_question_research(
        self,
        questions: list[MissingQuestion],
        requirements: list[ResearchRequirementRecord],
        retrievals: list[DirectedRetrievalRecord],
        hypotheses: list[BehaviorHypothesis],
        *,
        evidence: CanonicalEvidenceBundle | None = None,
        implementation_handoffs: list[GitHubImplementationVerificationHandoff]
        | None = None,
        unresolved_implementation_handoff_ids: list[str] | None = None,
        pattern_provider_status: PatternLookupRuntimeStatus | None = None,
        worker_results: list | None = None,
    ) -> list[QuestionResearchRecord]:
        """Resolve the terminal research status of every planned question.

        Batch loop over the per-question ``QuestionResearchRouter.resolve``
        contract.  ``NOT_FOUND`` means the mandated research executed and found
        no answer; it never asserts that the opposite behavior is true.
        """

        requirements_by_question = {row.question_id: row for row in requirements}
        records: list[QuestionResearchRecord] = []
        for question in sorted(questions, key=lambda row: row.question_id):
            requirement = requirements_by_question.get(question.question_id)
            if requirement is None:
                raise RuntimeError(
                    "Research requirement classification is mandatory before "
                    f"research status resolution: {question.question_id}"
                )
            records.append(
                QUESTION_RESEARCH_ROUTER.resolve(
                    requirement,
                    retrievals=retrievals,
                    hypotheses=hypotheses,
                    evidence=evidence,
                    implementation_handoffs=implementation_handoffs or [],
                    unresolved_implementation_handoff_ids=(
                        unresolved_implementation_handoff_ids or []
                    ),
                    pattern_provider_status=pattern_provider_status,
                    worker_results=worker_results or [],
                )
            )
        return records

    def retrieve_for_questions(
        self, bundle: CanonicalEvidenceBundle, questions: list[MissingQuestion]
    ) -> list[DirectedRetrievalRecord]:
        retrievals: list[DirectedRetrievalRecord] = []
        for question in questions:
            # UX1: investigation probes use the raw evidence terms that
            # triggered the question (paths/fragments stay internal); the
            # human-facing question text is never the only probe.
            query_terms = _words(question.question)
            for term in question.investigation_terms:
                query_terms |= _words(term)
            candidates: list[EvidenceRecord] = []
            for record in bundle.records:
                if is_github_implementation_result_record(record):
                    continue
                if record.source_type not in question.target_source_types:
                    continue
                record_terms = _words(_record_text(record))
                if query_terms & record_terms:
                    candidates.append(record)
            retrievals.append(
                DirectedRetrievalRecord(
                    question_id=question.question_id,
                    query=question.question,
                    authority_subject=question.authority_subject,
                    target_source_types=question.target_source_types,
                    matched_evidence_ids=[record.evidence_id for record in candidates],
                    status=RetrievalStatus.USED
                    if candidates
                    else RetrievalStatus.UNAVAILABLE,
                    reason=(
                        "Targeted supplied evidence matched the question."
                        if candidates
                        else "No supplied evidence matched; absence is not treated as rejection."
                    ),
                )
            )
        return retrievals

    def verify_hypotheses(
        self,
        bundle: CanonicalEvidenceBundle,
        questions: list[MissingQuestion],
        retrievals: list[DirectedRetrievalRecord],
        model: CanonicalBehaviorModel,
        *,
        scope: ScopeResolution | None = None,
        request: GenerationRequest | None = None,
        semantic_evidence: list[AuthorizedSemanticEvidence] | None = None,
        local_evidence_ids: set[str] | None = None,
    ) -> tuple[list[BehaviorHypothesis], CanonicalBehaviorModel]:
        records = {row.evidence_id: row for row in bundle.records}
        question_by_id = {row.question_id: row for row in questions}
        retrieval_by_question = {row.question_id: row for row in retrievals}
        provider_record_ids = {
            row.evidence_id
            for row in bundle.records
            if row.retrieval_pass == "reasoning-directed-provider"  # noqa: S105
        }
        authorizations_by_pair: dict[
            tuple[str, str], list[AuthorizedSemanticEvidence]
        ] = defaultdict(list)
        authorized_evidence_ids: set[str] = set()
        authorization_now = datetime.now(timezone.utc)
        for handoff in semantic_evidence or []:
            authorization = handoff.authorization
            binding = authorization.source_attestation.binding
            record = records.get(binding.evidence_id)
            question = question_by_id.get(binding.question_id)
            retrieval = retrieval_by_question.get(binding.question_id)
            if (
                request is None
                or record is None
                or question is None
                or retrieval is None
                or not _semantic_handoff_is_current(
                    handoff,
                    request=request,
                    record=record,
                    question=question,
                    retrieval=retrieval,
                    local_evidence_ids=set(local_evidence_ids or ()),
                    now=authorization_now,
                )
            ):
                continue
            authorizations_by_pair[(binding.question_id, binding.evidence_id)].append(
                handoff
            )
            authorized_evidence_ids.add(binding.evidence_id)
        provider_evidence_ids = provider_record_ids | authorized_evidence_ids
        provider_conflict_ids: set[str] = set()
        for conflict in bundle.authority_conflicts:
            conflict_ids = set(conflict.selected_evidence_ids) | set(
                conflict.competing_evidence_ids
            )
            if conflict_ids & provider_evidence_ids:
                provider_conflict_ids |= conflict_ids
        if bundle.currentness_conflicts:
            provider_conflict_claims = {
                claim_key
                for row in bundle.records
                if row.evidence_id in provider_evidence_ids
                for claim_key in row.claim_keys
                if claim_key in bundle.currentness_conflicts
            }
            provider_conflict_ids |= {
                row.evidence_id
                for row in bundle.records
                if set(row.claim_keys) & provider_conflict_claims
            }
        hypotheses: list[BehaviorHypothesis] = []
        for retrieval in retrievals:
            question = question_by_id[retrieval.question_id]
            all_matched = [
                records[evidence_id] for evidence_id in retrieval.matched_evidence_ids
            ]
            supporting_rows: list[EvidenceRecord] = []
            support_confidence: dict[str, float] = {}
            contradicting_ids: set[str] = set()
            for row in all_matched:
                if not _implementation_evidence_matches_scope(row, scope):
                    continue
                authorizations = authorizations_by_pair.get(
                    (retrieval.question_id, row.evidence_id),
                    [],
                )
                if authorizations:
                    stances = {
                        handoff.authorization.question_assessment.stance
                        for handoff in authorizations
                    }
                    if QuestionEvidenceStance.CONTRADICTS in stances:
                        contradicting_ids.add(row.evidence_id)
                        continue
                    supports = [
                        handoff
                        for handoff in authorizations
                        if handoff.authorization.question_assessment.stance
                        == QuestionEvidenceStance.SUPPORTS
                    ]
                    if supports:
                        supporting_rows.append(row)
                        support_confidence[row.evidence_id] = max(
                            handoff.authorization.question_assessment.assessment_confidence
                            for handoff in supports
                        )
                    continue
                if row.evidence_id in provider_record_ids:
                    continue
                supporting_rows.append(row)
                support_confidence[row.evidence_id] = row.evidence_confidence
            supporting_ids = [row.evidence_id for row in supporting_rows]
            conflict_ids = (
                set(supporting_ids) & provider_conflict_ids & provider_evidence_ids
            )
            contradicting_ids |= conflict_ids
            supporting_ids = sorted(set(supporting_ids) - contradicting_ids)
            if contradicting_ids:
                state = HypothesisState.UNRESOLVED
                confidence = 0.0
            elif not supporting_ids:
                state = HypothesisState.UNRESOLVED
                confidence = 0.0
            elif not _implementation_scope_fully_covered(
                supporting_rows,
                question,
                scope,
            ):
                state = HypothesisState.UNRESOLVED
                confidence = 0.0
            elif any(
                support_confidence[evidence_id] >= 0.8 for evidence_id in supporting_ids
            ):
                state = HypothesisState.CONFIRMED
                confidence = max(
                    support_confidence[evidence_id] for evidence_id in supporting_ids
                )
            else:
                state = HypothesisState.INFERRED_HIGH_CONFIDENCE
                confidence = max(
                    support_confidence[evidence_id] for evidence_id in supporting_ids
                )
            hypotheses.append(
                BehaviorHypothesis(
                    statement=question.question,
                    state=state,
                    supporting_evidence_ids=supporting_ids,
                    contradicting_evidence_ids=sorted(contradicting_ids),
                    derived_from_question_id=question.question_id,
                    confidence=confidence,
                )
            )
        nodes = list(model.graph.nodes)
        edges = list(model.graph.edges)
        evidence_nodes = {
            evidence_id: node
            for node in nodes
            if node.node_type == "EVIDENCE_SOURCE"
            for evidence_id in node.source_evidence_ids
        }
        provider_ids_in_retrievals = {
            evidence_id
            for hypothesis in hypotheses
            for evidence_id in (
                list(hypothesis.supporting_evidence_ids)
                + list(hypothesis.contradicting_evidence_ids)
            )
            if evidence_id in provider_evidence_ids
        }
        contradiction_ids_in_retrievals = {
            evidence_id
            for hypothesis in hypotheses
            for evidence_id in hypothesis.contradicting_evidence_ids
        }
        graph_evidence_ids = (
            provider_ids_in_retrievals | contradiction_ids_in_retrievals
        )
        for evidence_id in sorted(graph_evidence_ids):
            if evidence_id in evidence_nodes:
                continue
            record = records[evidence_id]
            evidence_node = BehaviorGraphNode(
                label=record.source_reference,
                node_type="EVIDENCE_SOURCE",
                source_evidence_ids=[record.evidence_id],
                authoritative=_is_authoritative(record),
            )
            nodes.append(evidence_node)
            evidence_nodes[evidence_id] = evidence_node
        for hypothesis in hypotheses:
            hypothesis_evidence_ids = sorted(
                set(hypothesis.supporting_evidence_ids)
                | set(hypothesis.contradicting_evidence_ids)
            )
            if not hypothesis_evidence_ids:
                continue
            question = question_by_id[hypothesis.derived_from_question_id]
            hypothesis_node = BehaviorGraphNode(
                label=hypothesis.statement,
                node_type="VERIFIED_HYPOTHESIS",
                source_evidence_ids=hypothesis_evidence_ids,
                authoritative=(
                    hypothesis.state == HypothesisState.CONFIRMED
                    and not hypothesis.contradicting_evidence_ids
                ),
            )
            nodes.append(hypothesis_node)
            for evidence_id in hypothesis.supporting_evidence_ids:
                evidence_node = evidence_nodes.get(evidence_id)
                if evidence_node is None:
                    continue
                record = records[evidence_id]
                edges.append(
                    BehaviorGraphEdge(
                        source_node_id=hypothesis_node.node_id,
                        target_node_id=evidence_node.node_id,
                        relation=_relation_for_dimension(question.dimension),
                        provenance_evidence_ids=[evidence_id],
                        authority_subject=question.authority_subject,
                        authority_class=record.requirement_authority,
                        currentness=record.currentness,
                        confidence=hypothesis.confidence,
                        verification_state=hypothesis.state,
                    )
                )
            for evidence_id in hypothesis.contradicting_evidence_ids:
                evidence_node = evidence_nodes.get(evidence_id)
                if evidence_node is None:
                    continue
                record = records[evidence_id]
                contradiction_confidence = max(
                    (
                        handoff.authorization.question_assessment.assessment_confidence
                        for handoff in authorizations_by_pair.get(
                            (question.question_id, evidence_id),
                            [],
                        )
                        if handoff.authorization.question_assessment.stance
                        == QuestionEvidenceStance.CONTRADICTS
                    ),
                    default=0.0,
                )
                edges.append(
                    BehaviorGraphEdge(
                        source_node_id=hypothesis_node.node_id,
                        target_node_id=evidence_node.node_id,
                        relation=BehaviorRelationType.CONTRADICTED_BY,
                        provenance_evidence_ids=[evidence_id],
                        authority_subject=question.authority_subject,
                        authority_class=record.requirement_authority,
                        currentness=record.currentness,
                        confidence=contradiction_confidence,
                        verification_state=HypothesisState.UNRESOLVED,
                    )
                )
        enriched_model = model.model_copy(
            update={"graph": BehaviorGraph(nodes=nodes, edges=edges)}
        )
        return hypotheses, enriched_model

    def model_domain_impact(
        self,
        bundle: CanonicalEvidenceBundle,
        domains: list[DomainActivation],
        model: CanonicalBehaviorModel,
    ) -> list[DomainImpact]:
        # UX1: NFR activation is domain-bound.  A scale/performance signal
        # activates a domain only when the signal co-occurs in that domain's
        # own evidence records (trigger + domain applicability + material
        # change impact).  A ticket-wide generic signal never fans out across
        # every domain.
        nfr_signal_terms = (
            "bulk",
            "thousand",
            "large query",
            "deep hierarchy",
            "many references",
            "concurrency",
            "repeated processing",
        )
        cardinality_re = re.compile(
            r"\b(?:\d{1,3}(?:,\d{3})+|\d{4,}|\d+(?:\.\d+)?\s*k)\b"
            r".{0,40}\b(?:documents?|pages?|items?|maps?|topics?)\b"
        )
        record_signals: dict[str, list[str]] = {}
        for record in bundle.records:
            scale_text = _scale_detection_text(
                " ".join(_positive_scope_clauses([_record_text(record)])).casefold()
            )
            signals = [
                signal for signal in nfr_signal_terms if signal in scale_text
            ]
            if cardinality_re.search(scale_text):
                signals.append("explicit high cardinality")
            if signals:
                record_signals[record.evidence_id] = signals
        impacts: list[DomainImpact] = []
        for activation in domains:
            domain_nfr_evidence = sorted(
                evidence_id
                for evidence_id in activation.evidence_ids
                if evidence_id in record_signals
            )
            domain_signals = sorted(
                {
                    signal
                    for evidence_id in domain_nfr_evidence
                    for signal in record_signals[evidence_id]
                }
            )
            impacts.append(
                DomainImpact(
                    domain=activation.domain,
                    materially_affected_entities=model.primary_entities,
                    observable_outcomes=(
                        model.generated_output_oracles
                        if activation.domain == IssueDomain.PUBLISHING
                        else ["VISIBLE_BEHAVIOR_MATCHES_CONTRACT"]
                    ),
                    nfr_applicable=bool(domain_signals),
                    nfr_triggers=domain_signals,
                    nfr_evidence_ids=domain_nfr_evidence,
                    nfr_materiality_basis=(
                        "Scale/performance signal co-occurs with this domain's "
                        "own evidence: " + ", ".join(domain_signals)
                        if domain_signals
                        else ""
                    ),
                    evidence_ids=activation.evidence_ids,
                )
            )
        return impacts

    def classify_coverage(
        self,
        facts: ContractFactSet,
        closure: list[ClosureDimensionResult],
        impacts: list[DomainImpact],
        hypotheses: list[BehaviorHypothesis],
        scope: ScopeResolution,
        questions: list[MissingQuestion],
        research_records: list[QuestionResearchRecord] | None = None,
        clarified_question_ids: set[str] | None = None,
        worker_results: list | None = None,
    ) -> list[CoverageDispositionRecord]:
        clarified_question_ids = clarified_question_ids or set()
        research_by_question = {
            row.question_id: row for row in research_records or []
        }
        # Decision semantics: a blocking question whose admitted research
        # established the customer-stated desired behavior no longer blocks
        # the established portion - it grounds a PROPOSED candidate and only
        # its residual acceptance-changing decision stays a bounded TBD.
        desired_resolved_ids = research_resolved_question_ids(
            questions, research_records, worker_results or []
        )
        rows: list[CoverageDispositionRecord] = []
        out_scope_values = [_scope_clause_value(value) for value in scope.out_of_scope]
        for fact in facts.facts:
            if fact.fact_type == ContractFactType.CONTEXT_STATEMENT:
                # UX1: narrative context informs issue understanding only; it
                # is not a behavior and receives no coverage disposition, so
                # it can never become an acceptance candidate.
                continue
            if fact.fact_type == ContractFactType.OUT_OF_SCOPE:
                disposition = CoverageDisposition.OUT_OF_SCOPE
            elif any(
                value and value in fact.literal.casefold() for value in out_scope_values
            ):
                disposition = CoverageDisposition.OUT_OF_SCOPE
            elif fact.fact_type == ContractFactType.PROBLEM_STATEMENT:
                # P2: a problem/gap statement is context (Known limitations),
                # never an acceptance candidate - it establishes the problem,
                # not a particular solution.
                disposition = CoverageDisposition.KNOWN_LIMITATION
            elif fact.fact_type in {
                ContractFactType.HUMAN_OPEN_QUESTIONS,
                ContractFactType.ENGINEERING_DESIGN_QUESTIONS,
                ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED,
            }:
                disposition = CoverageDisposition.OPEN_QUESTION
            elif fact.fact_type == ContractFactType.DIRECT_EXPECTED_BEHAVIOR:
                if _REGRESSION_ONLY_RE.search(fact.literal):
                    disposition = CoverageDisposition.SEMANTIC_REGRESSION
                else:
                    disposition = (
                        CoverageDisposition.ACCEPTANCE_CONTRACT
                        if fact.authority_class in _ACCEPTED_AUTHORITIES
                        else CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
                    )
            elif fact.fact_type == ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS:
                disposition = CoverageDisposition.NEGATIVE_BOUNDARY
            else:
                disposition = CoverageDisposition.CONFIGURATION_VARIANT
            rows.append(
                CoverageDispositionRecord(
                    candidate=fact.literal,
                    disposition=disposition,
                    source_fact_ids=[fact.fact_id],
                    evidence_ids=fact.source_evidence_ids,
                    rationale="Classified from an explicitly preserved contract fact.",
                    coverage_class=_derive_c1(disposition, has_direct_evidence=True)[0],
                    priority=_derive_c1(disposition, has_direct_evidence=True)[1],
                    acceptance_impact=_derive_c1(
                        disposition, has_direct_evidence=True
                    )[2],
                    contract_type=_derive_contract_type(
                        disposition, {fact.fact_type}
                    ),
                    applicability="APPLICABLE",
                )
            )
        dimension_disposition = {
            SemanticDimension.GENERATED_OUTPUT: CoverageDisposition.GENERATED_OUTPUT_VALIDATION,
            SemanticDimension.REFERENCED_CONTENT: CoverageDisposition.REFERENCE_REGRESSION,
            SemanticDimension.NESTED_REFERENCED_CONTENT: CoverageDisposition.REFERENCE_REGRESSION,
            SemanticDimension.PARENT_CONTEXT: CoverageDisposition.STRUCTURAL_REGRESSION,
            SemanticDimension.CHILD_CONTEXT: CoverageDisposition.STRUCTURAL_REGRESSION,
            SemanticDimension.HIERARCHY: CoverageDisposition.STRUCTURAL_REGRESSION,
            SemanticDimension.SPECIALIZATIONS: CoverageDisposition.SEMANTIC_REGRESSION,
            SemanticDimension.LIFECYCLE: CoverageDisposition.LIFECYCLE_COVERAGE,
            SemanticDimension.NEGATIVE_STATE: CoverageDisposition.NEGATIVE_BOUNDARY,
            SemanticDimension.INVALID_VALUE: CoverageDisposition.NEGATIVE_BOUNDARY,
            SemanticDimension.DOWNSTREAM_PROCESSOR: CoverageDisposition.IMPLEMENTATION_ORACLE,
            SemanticDimension.PERSISTED_STATE: CoverageDisposition.IMPLEMENTATION_ORACLE,
            SemanticDimension.DIRECT_CONSUMERS: CoverageDisposition.IMPLEMENTATION_ORACLE,
            SemanticDimension.SIBLING_CONSUMERS: CoverageDisposition.IMPLEMENTATION_ORACLE,
        }
        closure_groups: dict[
            tuple[SemanticDimension, ClosureDisposition], list[ClosureDimensionResult]
        ] = defaultdict(list)
        for item in closure:
            if item.disposition != ClosureDisposition.NOT_APPLICABLE:
                closure_groups[(item.dimension, item.disposition)].append(item)
        questions_by_closure_id: dict[str, list[MissingQuestion]] = defaultdict(list)
        for question in questions:
            for closure_id in question.source_closure_ids:
                questions_by_closure_id[closure_id].append(question)
        hypotheses_by_question: dict[str, list[BehaviorHypothesis]] = defaultdict(list)
        for hypothesis in hypotheses:
            if hypothesis.derived_from_question_id:
                hypotheses_by_question[hypothesis.derived_from_question_id].append(
                    hypothesis
                )
        linked_hypothesis_ids: set[str] = set()
        for (dimension, closure_disposition), items in sorted(
            closure_groups.items(),
            key=lambda item: (item[0][0].value, item[0][1].value),
        ):
            related_questions = sorted(
                {
                    question.question_id: question
                    for item in items
                    for question in questions_by_closure_id.get(item.closure_id, [])
                }.values(),
                key=lambda row: row.question_id,
            )
            related_hypotheses = sorted(
                {
                    hypothesis.hypothesis_id: hypothesis
                    for question in related_questions
                    for hypothesis in hypotheses_by_question.get(
                        question.question_id, []
                    )
                }.values(),
                key=lambda row: row.hypothesis_id,
            )
            linked_hypothesis_ids.update(
                hypothesis.hypothesis_id for hypothesis in related_hypotheses
            )
            hypothesis_states = {row.state for row in related_hypotheses}
            if HypothesisState.UNRESOLVED in hypothesis_states:
                disposition = CoverageDisposition.OPEN_QUESTION
                rationale = (
                    "The material hypothesis remains unresolved after targeted "
                    "retrieval and verification."
                )
            elif len(hypothesis_states) > 1:
                disposition = CoverageDisposition.OPEN_QUESTION
                rationale = (
                    "Material hypotheses have conflicting terminal states and "
                    "require a visible decision."
                )
            elif related_hypotheses and hypothesis_states == {HypothesisState.REJECTED}:
                disposition = CoverageDisposition.INVESTIGATED_AND_REJECTED
                rationale = "Targeted evidence rejected the material hypothesis."
            elif related_hypotheses:
                disposition = dimension_disposition.get(
                    dimension, CoverageDisposition.SEMANTIC_REGRESSION
                )
                rationale = (
                    "Targeted evidence verified applicability; the result remains "
                    "QE coverage and is not promoted to product acceptance."
                )
            elif closure_disposition == ClosureDisposition.INVESTIGATED_AND_REJECTED:
                disposition = CoverageDisposition.INVESTIGATED_AND_REJECTED
                rationale = items[0].rationale
            elif closure_disposition == ClosureDisposition.UNRESOLVED_AND_EXPOSED:
                disposition = CoverageDisposition.OPEN_QUESTION
                rationale = items[0].rationale
            else:
                disposition = dimension_disposition.get(
                    dimension, CoverageDisposition.SEMANTIC_REGRESSION
                )
                rationale = items[0].rationale
            if disposition != CoverageDisposition.OPEN_QUESTION:
                research_override = _mandatory_research_open_rationale(
                    related_questions,
                    research_by_question,
                )
                if research_override is not None:
                    # P3: an exhausted-research blocking product decision is a
                    # bounded ACCEPTANCE_TBD, not a generic open question.
                    if any(
                        _acceptance_tbd_eligible(
                            row,
                            research_by_question,
                            clarified_question_ids,
                            desired_resolved_ids,
                        )
                        for row in related_questions
                    ):
                        disposition = CoverageDisposition.ACCEPTANCE_TBD
                        rationale = research_override
                    else:
                        disposition = CoverageDisposition.OPEN_QUESTION
                        rationale = research_override
            elif disposition == CoverageDisposition.OPEN_QUESTION and any(
                _acceptance_tbd_eligible(
                    row,
                    research_by_question,
                    clarified_question_ids,
                    desired_resolved_ids,
                )
                for row in related_questions
            ):
                # P3: an already-open closure row for a blocking product
                # decision with exhausted research upgrades to a bounded
                # ACCEPTANCE_TBD - acceptance-lane, never promoted.
                disposition = CoverageDisposition.ACCEPTANCE_TBD
                rationale = (
                    "Acceptance-material decision remains unresolved after "
                    "mandatory research terminated; the missing value is "
                    "never invented."
                )
            entities = ", ".join(dict.fromkeys(item.entity for item in items))
            candidate = f"{dimension.value}: {entities}"
            if _RAW_FRAGMENT_RE.search(entities):
                # P1: raw clone-grep/retrieval fragments stay in the trace and
                # evidence ids; human-facing coverage gets an interpreted
                # pointer, never the raw fragment dump.
                evidence_count = len({item.closure_id for item in items})
                candidate = (
                    f"{dimension.value}: internal evidence recorded for "
                    f"{evidence_count} closure "
                    f"record{'s' if evidence_count != 1 else ''} (see trace)"
                )
            if (
                disposition == CoverageDisposition.OPEN_QUESTION
                and len(related_questions) == 1
            ):
                candidate = related_questions[0].question
            c1_class, c1_priority, c1_impact = _derive_c1(
                disposition,
                has_direct_evidence=bool(
                    HypothesisState.CONFIRMED in hypothesis_states
                    or [item for item in items if item.evidence_ids]
                ),
            )
            rows.append(
                CoverageDispositionRecord(
                    candidate=candidate,
                    disposition=disposition,
                    source_closure_ids=[item.closure_id for item in items],
                    source_question_ids=[
                        question.question_id for question in related_questions
                    ],
                    source_hypothesis_ids=[
                        hypothesis.hypothesis_id for hypothesis in related_hypotheses
                    ],
                    evidence_ids=[
                        evidence_id
                        for item in items
                        for evidence_id in item.evidence_ids
                    ]
                    + [
                        evidence_id
                        for hypothesis in related_hypotheses
                        for evidence_id in (
                            hypothesis.supporting_evidence_ids
                            + hypothesis.contradicting_evidence_ids
                            + hypothesis.verification_evidence_ids
                        )
                    ],
                    rationale=rationale,
                    coverage_class=c1_class,
                    priority=c1_priority,
                    acceptance_impact=c1_impact,
                    contract_type=_derive_contract_type(disposition, set()),
                    applicability="APPLICABLE",
                )
            )
        for impact in impacts:
            if impact.nfr_applicable:
                rows.append(
                    CoverageDispositionRecord(
                        candidate=f"Validate {impact.domain.value} under: {', '.join(impact.nfr_triggers)}",
                        disposition=CoverageDisposition.NFR_COVERAGE,
                        # UX1: the row cites the domain-bound evidence that
                        # established the material scale/performance
                        # relationship; no carpet coverage, no invented SLA.
                        evidence_ids=impact.nfr_evidence_ids or impact.evidence_ids,
                        rationale=(
                            "NFR coverage is activated by domain-bound "
                            "change-impact evidence; no SLA is invented. "
                            + impact.nfr_materiality_basis
                        ),
                        coverage_class="QE_REGRESSION",
                        priority="P1",
                        acceptance_impact=_C1_IMPACT_TEXT["P1"],
                        contract_type="POSITIVE",
                        applicability="APPLICABLE",
                    )
                )
        questions_by_id = {row.question_id: row for row in questions}
        for hypothesis in hypotheses:
            if hypothesis.hypothesis_id in linked_hypothesis_ids:
                continue
            question = questions_by_id.get(hypothesis.derived_from_question_id)
            if hypothesis.state == HypothesisState.UNRESOLVED:
                disposition = CoverageDisposition.OPEN_QUESTION
                rationale = "The material hypothesis remains unresolved."
            elif hypothesis.state == HypothesisState.REJECTED:
                disposition = CoverageDisposition.INVESTIGATED_AND_REJECTED
                rationale = "Targeted evidence rejected the material hypothesis."
            elif question is not None and question.dimension is not None:
                disposition = dimension_disposition.get(
                    question.dimension, CoverageDisposition.SEMANTIC_REGRESSION
                )
                rationale = (
                    "Targeted evidence verified applicability; the result remains "
                    "QE coverage and is not promoted to product acceptance."
                )
            else:
                disposition = CoverageDisposition.OPEN_QUESTION
                rationale = (
                    "Evidence was found, but no canonical answer value was extracted; "
                    "the material product decision remains visible."
                )
            if disposition != CoverageDisposition.OPEN_QUESTION and question is not None:
                research_override = _mandatory_research_open_rationale(
                    [question],
                    research_by_question,
                )
                if research_override is not None:
                    if _acceptance_tbd_eligible(
                        question,
                        research_by_question,
                        clarified_question_ids,
                        desired_resolved_ids,
                    ):
                        disposition = CoverageDisposition.ACCEPTANCE_TBD
                    else:
                        disposition = CoverageDisposition.OPEN_QUESTION
                    rationale = research_override
            elif (
                disposition == CoverageDisposition.OPEN_QUESTION
                and question is not None
                and _acceptance_tbd_eligible(
                    question,
                    research_by_question,
                    clarified_question_ids,
                    desired_resolved_ids,
                )
            ):
                # P3: an already-open row for a blocking product decision with
                # exhausted research upgrades to a bounded ACCEPTANCE_TBD - it
                # stays acceptance-lane instead of a generic open question.
                disposition = CoverageDisposition.ACCEPTANCE_TBD
                rationale = (
                    "Acceptance-material decision remains unresolved after "
                    "mandatory research terminated; the missing value is "
                    "never invented."
                )
            if (
                disposition == CoverageDisposition.OPEN_QUESTION
                and question is not None
                and question.question_id in desired_resolved_ids
            ):
                # Decision semantics: admitted research established this
                # question's acceptance-bearing core - the customer's stated
                # desired behavior.  The hypothesis is answered by it, so its
                # one terminal disposition is the PROPOSED candidate, not an
                # open question.  Only the residual acceptance-changing
                # decision (carried by the convergence record) may stay a
                # bounded TBD.
                established = _establishing_acceptance_claims(
                    question,
                    research_by_question,
                    worker_results or [],
                    limit=1,
                )
                if established:
                    proposed_text, refs, proposed_rationale = established[0]
                    p_class, p_priority, p_impact = _derive_c1(
                        CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                        has_direct_evidence=True,
                    )
                    rows.append(
                        CoverageDispositionRecord(
                            candidate=proposed_text,
                            disposition=(
                                CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
                            ),
                            source_question_ids=[question.question_id],
                            source_hypothesis_ids=[hypothesis.hypothesis_id],
                            source_fact_ids=list(question.source_fact_ids),
                            evidence_ids=[
                                ref for ref in refs if str(ref).strip()
                            ],
                            rationale=proposed_rationale,
                            coverage_class=p_class,
                            priority=p_priority,
                            acceptance_impact=p_impact,
                            contract_type="POSITIVE",
                            applicability="APPLICABLE",
                            research_derived=True,
                        )
                    )
                    continue
            c1_class, c1_priority, c1_impact = _derive_c1(
                disposition,
                has_direct_evidence=hypothesis.state == HypothesisState.CONFIRMED,
            )
            rows.append(
                CoverageDispositionRecord(
                    candidate=hypothesis.statement,
                    disposition=disposition,
                    source_question_ids=(
                        [hypothesis.derived_from_question_id]
                        if hypothesis.derived_from_question_id
                        else []
                    ),
                    source_hypothesis_ids=[hypothesis.hypothesis_id],
                    evidence_ids=(
                        hypothesis.supporting_evidence_ids
                        + hypothesis.contradicting_evidence_ids
                        + hypothesis.verification_evidence_ids
                    ),
                    rationale=rationale,
                    coverage_class=c1_class,
                    priority=c1_priority,
                    acceptance_impact=c1_impact,
                    contract_type=_derive_contract_type(disposition, set()),
                    applicability="APPLICABLE",
                )
            )
        # P3: blocking acceptance-decision questions with exhausted research
        # but no hypothesis/closure linkage still earn a bounded ACCEPTANCE_TBD
        # coverage row, so the unresolved dimension is a first-class canonical
        # artifact (not merely rendered prose) and can never promote.
        linked_question_ids = {
            question_id
            for row in rows
            for question_id in row.source_question_ids
        }
        for question in questions:
            if question.question_id in linked_question_ids:
                continue
            if question.question_id in desired_resolved_ids:
                # Decision semantics: research established this blocking
                # question's acceptance-bearing core - the customer's stated
                # desired behavior.  That established portion grounds a
                # PROPOSED candidate (never Confirmed); any residual
                # acceptance-changing decision stays visible through the
                # convergence record's bounded TBD.
                established = _establishing_acceptance_claims(
                    question,
                    research_by_question,
                    worker_results or [],
                    limit=2,
                )
                for proposed_text, refs, proposed_rationale in established:
                    candidate = proposed_text
                    if len(candidate) > 400:
                        candidate = (
                            candidate[:400].rsplit(" ", 1)[0].rstrip() + "."
                        )
                    c1_class, c1_priority, c1_impact = _derive_c1(
                        CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                        has_direct_evidence=True,
                    )
                    rows.append(
                        CoverageDispositionRecord(
                            candidate=candidate,
                            disposition=(
                                CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
                            ),
                            source_question_ids=[question.question_id],
                            source_fact_ids=list(question.source_fact_ids),
                            evidence_ids=[
                                ref for ref in refs if str(ref).strip()
                            ],
                            rationale=proposed_rationale,
                            coverage_class=c1_class,
                            priority=c1_priority,
                            acceptance_impact=c1_impact,
                            contract_type="POSITIVE",
                            applicability="APPLICABLE",
                            research_derived=True,
                        )
                    )
                if established:
                    continue
                # Every establishing claim normalized away (for example a
                # documentation finding that stayed meta prose).  Falling
                # through keeps the question in the acceptance lane as a
                # bounded TBD rather than dropping it from coverage entirely.
            # Documented existing behavior relevant to this question grounds a
            # PROPOSED baseline candidate so documentation research reaches
            # the acceptance lane instead of being dropped.  These rows are
            # additive: the question is NOT resolved by them, so its bounded
            # TBD is still emitted below and the product decision stays open.
            for baseline_text, baseline_refs in documented_baseline_claims(
                question,
                research_by_question,
                worker_results or [],
                limit=2,
            ):
                b_class, b_priority, b_impact = _derive_c1(
                    CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                    has_direct_evidence=True,
                )
                rows.append(
                    CoverageDispositionRecord(
                        candidate=baseline_text,
                        disposition=(
                            CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
                        ),
                        source_question_ids=[question.question_id],
                        source_fact_ids=list(question.source_fact_ids),
                        evidence_ids=[
                            ref for ref in baseline_refs if str(ref).strip()
                        ],
                        rationale=_EXISTING_PROPOSED_RATIONALE,
                        coverage_class=b_class,
                        priority=b_priority,
                        acceptance_impact=b_impact,
                        contract_type="POSITIVE",
                        applicability="APPLICABLE",
                        research_derived=True,
                    )
                )
            if not _acceptance_tbd_eligible(
                question,
                research_by_question,
                clarified_question_ids,
                desired_resolved_ids,
            ):
                continue
            c1_class, c1_priority, c1_impact = _derive_c1(
                CoverageDisposition.ACCEPTANCE_TBD,
                has_direct_evidence=False,
            )
            rows.append(
                CoverageDispositionRecord(
                    candidate=question.question,
                    disposition=CoverageDisposition.ACCEPTANCE_TBD,
                    source_question_ids=[question.question_id],
                    source_fact_ids=list(question.source_fact_ids),
                    rationale=(
                        "Acceptance-material decision remains unresolved after "
                        "mandatory research terminated; the missing value is "
                        "never invented."
                    ),
                    coverage_class=c1_class,
                    priority=c1_priority,
                    acceptance_impact=c1_impact,
                    contract_type="POSITIVE",
                    applicability="APPLICABLE",
                )
            )
        # Admitted documentation research must reach the acceptance lane even
        # when its question already carries hypothesis/closure linkage.  The
        # baseline emission above lives inside the P3 unlinked-question loop,
        # so a question that documentation research actually ANSWERED was
        # skipped by the `linked_question_ids` guard and its documented
        # behavior - the columns, filters, sort and download scoping a tester
        # must re-verify - never became coverage.  This pass is additive and
        # deduplicated by candidate text: it resolves nothing and changes no
        # existing row's disposition.
        already_covered = {
            _normalize_candidate_key(row.candidate) for row in rows
        }
        for question in questions:
            for baseline_text, baseline_refs in documented_baseline_claims(
                question,
                research_by_question,
                worker_results or [],
                limit=6,
            ):
                key = _normalize_candidate_key(baseline_text)
                if key in already_covered:
                    continue
                already_covered.add(key)
                b_class, b_priority, b_impact = _derive_c1(
                    CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                    has_direct_evidence=True,
                )
                rows.append(
                    CoverageDispositionRecord(
                        candidate=baseline_text,
                        disposition=(
                            CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
                        ),
                        source_question_ids=[question.question_id],
                        source_fact_ids=list(question.source_fact_ids),
                        evidence_ids=[
                            ref for ref in baseline_refs if str(ref).strip()
                        ],
                        rationale=_EXISTING_PROPOSED_RATIONALE,
                        coverage_class=b_class,
                        priority=b_priority,
                        acceptance_impact=b_impact,
                        contract_type="POSITIVE",
                        applicability="APPLICABLE",
                        research_derived=True,
                    )
                )
        # Admitted code research must reach coverage for the same reason the
        # documentation pass above exists: research that runs and then never
        # surfaces is wasted.  IMPLEMENTATION_EVIDENCE findings are excluded
        # from both acceptance grounding paths by design (code is not a
        # contract), which previously left them with no disposition at all -
        # so the current sort, the existing columns and filters, and the
        # surfaces a change must keep compatible silently vanished from the
        # plan.  These rows land in the INVESTIGATION lane
        # (IMPLEMENTATION_ORACLE), are deduplicated by candidate text, resolve
        # no question and change no existing row's disposition.
        for question in questions:
            for impl_text, impl_refs in verified_implementation_claims(
                question,
                research_by_question,
                worker_results or [],
                limit=20,
            ):
                key = _normalize_candidate_key(impl_text)
                if key in already_covered:
                    continue
                already_covered.add(key)
                i_class, i_priority, i_impact = _derive_c1(
                    CoverageDisposition.IMPLEMENTATION_ORACLE,
                    has_direct_evidence=True,
                )
                rows.append(
                    CoverageDispositionRecord(
                        candidate=impl_text,
                        disposition=CoverageDisposition.IMPLEMENTATION_ORACLE,
                        source_question_ids=[question.question_id],
                        source_fact_ids=list(question.source_fact_ids),
                        evidence_ids=[
                            ref for ref in impl_refs if str(ref).strip()
                        ],
                        rationale=_IMPLEMENTATION_ORACLE_RATIONALE,
                        coverage_class=i_class,
                        priority=i_priority,
                        acceptance_impact=i_impact,
                        contract_type="POSITIVE",
                        applicability="APPLICABLE",
                        research_derived=True,
                    )
                )
        return sorted(
            {row.disposition_id: row for row in rows}.values(),
            key=lambda row: row.disposition_id,
        )

    def classify_behavior_changes(
        self,
        facts: ContractFactSet,
        dispositions: list[CoverageDispositionRecord],
        evidence: CanonicalEvidenceBundle,
    ) -> list[BehaviorClassificationRecord]:
        """Classify every resolved behavior as existing vs new.

        Documentation establishes current product behavior; the current ticket
        proposes new behavior.  "Documented today" is never confused with
        "required after this fix": a behavior matched only by existing
        documentation is a confirmed baseline, and a behavior only the ticket
        requests stays a new requirement no matter how much documentation the
        retrieval matched on adjacent topics.
        """

        records_by_id = {row.evidence_id: row for row in evidence.records}
        conflict_ids = {
            evidence_id
            for conflict in evidence.authority_conflicts
            for evidence_id in (
                list(conflict.selected_evidence_ids)
                + list(conflict.competing_evidence_ids)
            )
        }
        rows: list[BehaviorClassificationRecord] = []
        for disposition in sorted(dispositions, key=lambda row: row.disposition_id):
            if disposition.disposition in _UNRESOLVED_BEHAVIOR_DISPOSITIONS:
                continue
            linked = [
                records_by_id[evidence_id]
                for evidence_id in disposition.evidence_ids
                if evidence_id in records_by_id
            ]
            existing_ids = sorted(
                row.evidence_id
                for row in linked
                if row.source_type in _EXISTING_BEHAVIOR_SOURCES
            )
            # A documented-baseline row is grounded by an admitted
            # DOC_RESEARCHER EXISTING_BEHAVIOR finding, whose source_refs are
            # documentation slugs (`doc:<slug>`) rather than bundle evidence
            # ids, so they never resolve through `records_by_id`.  Without
            # this, documentation that genuinely establishes current product
            # behavior would classify UNKNOWN and could never ground the
            # baseline the ticket preserves or changes.
            if (
                not existing_ids
                and disposition.research_derived
                and disposition.rationale == _EXISTING_PROPOSED_RATIONALE
            ):
                existing_ids = sorted(
                    str(ref)
                    for ref in disposition.evidence_ids
                    if str(ref).startswith("doc:")
                )
            requested_ids = sorted(
                row.evidence_id
                for row in linked
                if row.source_type in JIRA_AUTHORITY_RESEARCH_SOURCES
            )
            change_ids = sorted(
                row.evidence_id
                for row in linked
                if row.source_type in _CHANGE_SET_SOURCES
            )
            if set(disposition.evidence_ids) & conflict_ids:
                behavior_class = BehaviorChangeClass.CONFLICTED
                rationale = (
                    "Existing and requested sources disagree on this behavior; "
                    "a Human must settle the conflict."
                )
            elif existing_ids and (requested_ids or change_ids):
                if _PRESERVATION_RE.search(disposition.candidate):
                    behavior_class = BehaviorChangeClass.PRESERVED_EXISTING_BEHAVIOR
                    rationale = (
                        "Documented current behavior the ticket requires to remain "
                        "compatible after the change."
                    )
                else:
                    behavior_class = BehaviorChangeClass.MODIFIED_EXISTING_BEHAVIOR
                    rationale = (
                        "Documented current behavior the ticket explicitly changes."
                    )
            elif existing_ids:
                behavior_class = BehaviorChangeClass.EXISTING_CONFIRMED
                rationale = (
                    "Existing documentation or current implementation establishes "
                    "this baseline behavior; the ticket does not change it."
                )
            elif requested_ids or change_ids:
                behavior_class = BehaviorChangeClass.NEW_REQUIREMENT
                rationale = (
                    "Only the current ticket or its change set establishes this "
                    "behavior; no existing documentation claims it."
                )
            else:
                behavior_class = BehaviorChangeClass.UNKNOWN
                rationale = (
                    "No existing-behavior or current-ticket evidence classifies "
                    "this behavior; it remains unresolved until researched."
                )
            rows.append(
                BehaviorClassificationRecord(
                    disposition_id=disposition.disposition_id,
                    behavior_class=behavior_class,
                    existing_evidence_ids=existing_ids,
                    requested_evidence_ids=requested_ids,
                    change_evidence_ids=change_ids,
                    rationale=rationale,
                )
            )
        return rows

    def resolve_acceptance_contract_with_trace(
        self,
        facts: ContractFactSet,
        dispositions: list[CoverageDispositionRecord],
        questions: list[MissingQuestion],
        resolved_question_ids: set[str] | None = None,
        research_records: list[QuestionResearchRecord] | None = None,
        behavior_classifications: list[BehaviorClassificationRecord] | None = None,
        evidence_records: list[Any] | None = None,
        clarifications: list[HumanClarification] | None = None,
    ) -> AcceptanceResolutionBatch:
        facts_by_id = {row.fact_id: row for row in facts.facts}
        accepted_literals = [
            row.literal
            for row in facts.facts
            if row.authority_class in _ACCEPTED_AUTHORITIES
            and row.fact_type == ContractFactType.DIRECT_EXPECTED_BEHAVIOR
        ]
        # P1 resume: a question resolved by an admitted human clarification no
        # longer blocks; every other unresolved question keeps blocking.
        resolved_question_ids = resolved_question_ids or set()
        blocking_ids = [
            row.question_id
            for row in questions
            if row.blocking and row.question_id not in resolved_question_ids
        ]        # P3: claim-level dependency.  A candidate is blocked only by
        # unresolved blocking questions actually linked to its source coverage
        # dispositions; independent sufficiently-established claims must not
        # inherit ticket-wide blocking.  The disposition linkage IS the
        # dependency record - an unlinked claim has no dependency.
        def _dependent_blocking_ids(row: CoverageDispositionRecord) -> list[str]:
            linked = set(row.source_question_ids)
            return sorted(
                question_id for question_id in blocking_ids if question_id in linked
            )

        discovered_candidates: list[AcceptanceCandidate] = []
        for row in dispositions:
            if row.disposition not in {
                CoverageDisposition.ACCEPTANCE_CONTRACT,
                CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            }:
                continue
            source_facts = [
                facts_by_id[fact_id]
                for fact_id in row.source_fact_ids
                if fact_id in facts_by_id
            ]
            accepted_human_contract = any(
                fact.authority_class in _ACCEPTED_AUTHORITIES for fact in source_facts
            )
            exact_types = {
                ContractFactType.EXACT_VALUES,
                ContractFactType.COUNTS,
                ContractFactType.LIMITS,
                ContractFactType.COLORS,
                ContractFactType.EXACT_DEFAULTS,
                ContractFactType.EXACT_STATUS_NAMES,
            }
            has_exactness = bool(
                re.search(
                    r"(?:\b\d+(?:\.\d+)?\b|#[0-9a-f]{3,8}\b)",
                    row.candidate,
                    re.IGNORECASE,
                )
            )
            supporting_exact_facts = [
                fact
                for fact in facts.facts
                if fact.fact_type in exact_types and fact.literal == row.candidate
            ]
            exact_supported = (
                not has_exactness
                or bool(supporting_exact_facts)
                and all(fact.authoritative for fact in supporting_exact_facts)
            )
            # Stage 18 owns the requirement -> acceptance transition.  Copying
            # the ticket's request text verbatim loses the observable outcome,
            # so request grammar is reframed here.  When it cannot be reframed
            # the candidate stays non-observable and the promotion gate - whose
            # observability check is otherwise unreachable - correctly stops it.
            candidate_statement = row.candidate
            if _is_request_not_outcome(candidate_statement):
                derived = _derive_outcome_statement(candidate_statement)
                if derived is not None:
                    candidate_statement = derived
            candidate_observable = bool(
                candidate_statement.strip()
            ) and not _is_request_not_outcome(candidate_statement)
            discovered_candidates.append(
                AcceptanceCandidate(
                    statement=candidate_statement,
                    contract_mode=facts.contract_mode,
                    accepted_human_contract=accepted_human_contract,
                    source_fact_ids=row.source_fact_ids,
                    source_disposition_ids=[row.disposition_id],
                    evidence_ids=row.evidence_ids,
                    in_scope=True,
                    observable=candidate_observable,
                    regression_only=bool(_REGRESSION_ONLY_RE.search(row.candidate)),
                    implementation_mechanics_only=bool(
                        _IMPLEMENTATION_MECHANICS_RE.search(row.candidate)
                    ),
                    exact_values_supported=exact_supported,
                    contradicts_human_contract=(
                        not accepted_human_contract
                        and _contradicts_accepted_contract(
                            row.candidate, accepted_literals
                        )
                    ),
                    unresolved_decision_ids=(
                        [] if accepted_human_contract
                        else _dependent_blocking_ids(row)
                    ),
                )
            )
        grouped: dict[tuple[str, ...], list[AcceptanceCandidate]] = defaultdict(list)
        for candidate in discovered_candidates:
            grouped[_semantic_candidate_key(candidate.statement)].append(candidate)

        final_candidates: list[AcceptanceCandidate] = []
        dedup_decisions: list[CandidateDedupDecision] = []
        for semantic_key, group in sorted(grouped.items(), key=lambda item: item[0]):
            if len(group) == 1:
                final_candidates.append(group[0])
                continue

            def candidate_rank(candidate: AcceptanceCandidate) -> tuple[bool, bool, int, str]:
                return (
                    candidate.accepted_human_contract,
                    all(
                        facts_by_id[fact_id].authoritative
                        for fact_id in candidate.source_fact_ids
                        if fact_id in facts_by_id
                    ),
                    -len(candidate.statement),
                    candidate.statement,
                )

            selected = max(group, key=candidate_rank)
            accepted_human_contract = any(
                row.accepted_human_contract for row in group
            )
            survivor = AcceptanceCandidate(
                statement=selected.statement,
                contract_mode=selected.contract_mode,
                accepted_human_contract=accepted_human_contract,
                source_fact_ids=sorted(
                    {value for row in group for value in row.source_fact_ids}
                ),
                source_disposition_ids=sorted(
                    {value for row in group for value in row.source_disposition_ids}
                ),
                evidence_ids=sorted(
                    {value for row in group for value in row.evidence_ids}
                ),
                in_scope=all(row.in_scope for row in group),
                observable=all(row.observable for row in group),
                regression_only=any(row.regression_only for row in group),
                implementation_mechanics_only=any(
                    row.implementation_mechanics_only for row in group
                ),
                exact_values_supported=all(
                    row.exact_values_supported for row in group
                ),
                contradicts_human_contract=any(
                    row.contradicts_human_contract for row in group
                ),
                unresolved_decision_ids=(
                    []
                    if accepted_human_contract
                    else sorted(
                        {
                            value
                            for row in group
                            for value in row.unresolved_decision_ids
                        }
                    )
                ),
            )
            final_candidates.append(survivor)
            dedup_decisions.append(
                CandidateDedupDecision(
                    merged_candidate_ids=[row.candidate_id for row in group],
                    surviving_candidate_id=survivor.candidate_id,
                    merge_reason=(
                        "Candidates have the same polarity and ordered outcome terms "
                        "after grammatical filler is removed."
                    ),
                    semantic_equivalence_basis=" | ".join(semantic_key),
                )
            )
        # P2/P1 resume: an admitted, sufficiently-authoritative clarification
        # that answers a blocking question with new behavior content becomes a
        # candidate bound to that clarification - the human decision is the
        # evidence; nothing is invented by the Writer.
        admitted_clarifications = [
            row
            for row in clarifications or []
            if row.status == ClarificationStatus.ADMITTED
        ]
        blocking_question_ids = {row.question_id for row in questions if row.blocking}
        covered_tokens: set[str] = set()
        for row in final_candidates:
            covered_tokens |= _content_tokens(row.statement)
        for row in admitted_clarifications:
            if row.answer_classification not in _CLARIFICATION_ESTABLISHING_CLASSES:
                continue
            if row.question_ref not in blocking_question_ids:
                continue
            if row.authority_role not in _CLARIFICATION_ESTABLISHING_AUTHORITIES:
                continue
            if _content_tokens(row.answer) <= covered_tokens:
                continue
            synthesized = AcceptanceCandidate(
                statement=row.answer,
                contract_mode=facts.contract_mode,
                accepted_human_contract=False,
                source_fact_ids=[],
                source_disposition_ids=[],
                evidence_ids=[f"clarification:{row.clarification_id}"],
                in_scope=True,
                observable=bool(row.answer.strip()),
                exact_values_supported=True,
                contradicts_human_contract=False,
                unresolved_decision_ids=[],
            )
            discovered_candidates.append(synthesized)
            final_candidates.append(synthesized)
            covered_tokens |= _content_tokens(row.answer)

        # C2B-S1: one validated sufficiency decision per surviving candidate,
        # computed once here and consumed by the promotion gate and the C2A
        # replay projection - no second sufficiency representation anywhere.
        sufficiency_records: list[ClaimSufficiencyRecord] = []
        if research_records is not None:
            research_by_question = {
                row.question_id: row for row in research_records
            }
            classifications_by_disposition = {
                row.disposition_id: row for row in behavior_classifications or []
            }
            dispositions_by_id = {row.disposition_id: row for row in dispositions}
            evidence_currentness = {
                row.evidence_id: row.currentness
                for row in evidence_records or []
                if getattr(row, "evidence_id", None) is not None
            }
            admitted = [
                row
                for row in clarifications or []
                if row.status == ClarificationStatus.ADMITTED
            ]
            for candidate in final_candidates:
                sufficiency_records.append(
                    assess_claim_sufficiency(
                        candidate,
                        facts_by_id=facts_by_id,
                        dispositions_by_id=dispositions_by_id,
                        research_by_question=research_by_question,
                        classifications_by_disposition=classifications_by_disposition,
                        evidence_currentness=evidence_currentness,
                        admitted_clarifications=admitted,
                    )
                )
            # C2B-C1: stamp the sufficiency link onto each covered disposition
            # (a link, excluded from the disposition identity hash).
            record_by_coverage = {}
            for record in sufficiency_records:
                for ref in record.coverage_refs:
                    record_by_coverage[ref] = record
            for row in dispositions:
                link = record_by_coverage.get(row.disposition_id)
                if link is not None:
                    row.sufficiency_ref = link.sufficiency_id
                    row.applicability = link.applicability
        return AcceptanceResolutionBatch(
            discovered_candidates=discovered_candidates,
            candidates=final_candidates,
            dedup_decisions=dedup_decisions,
            sufficiency=sufficiency_records,
        )

    def resolve_acceptance_contract(
        self,
        facts: ContractFactSet,
        dispositions: list[CoverageDispositionRecord],
        questions: list[MissingQuestion],
    ) -> list[AcceptanceCandidate]:
        """Compatibility projection of the traced acceptance resolution."""

        return self.resolve_acceptance_contract_with_trace(
            facts, dispositions, questions
        ).candidates

    def behavioral_completeness_gate(
        self,
        closure: list[ClosureDimensionResult],
        questions: list[MissingQuestion],
        scope: ScopeResolution,
        hypotheses: list[BehaviorHypothesis],
        dispositions: list[CoverageDispositionRecord],
        question_quality: MissingQuestionQualityReport | None = None,
        research_requirements: list[ResearchRequirementRecord] | None = None,
        research_records: list[QuestionResearchRecord] | None = None,
        behavior_classifications: list[BehaviorClassificationRecord] | None = None,
        expansion: BehavioralCoverageExpansion | None = None,
    ) -> GateDecision:
        questions_by_id = {row.question_id: row for row in questions}
        question_closure_ids = {
            closure_id
            for question in questions
            for closure_id in question.source_closure_ids
        }
        dispositions_by_closure_id: dict[str, list[CoverageDispositionRecord]] = (
            defaultdict(list)
        )
        dispositions_by_hypothesis_id: dict[str, list[CoverageDispositionRecord]] = (
            defaultdict(list)
        )
        for disposition in dispositions:
            for closure_id in disposition.source_closure_ids:
                dispositions_by_closure_id[closure_id].append(disposition)
            for hypothesis_id in disposition.source_hypothesis_ids:
                dispositions_by_hypothesis_id[hypothesis_id].append(disposition)
        failures: list[str] = []
        if expansion is not None:
            # Invariant: no silent candidate loss.  Expansion declaring a
            # behavior material while closure answers NOT_APPLICABLE for every
            # entity is exactly the silent drop this stage exists to prevent.
            decided_dimensions = {
                row.dimension
                for row in closure
                if row.applicability != ApplicabilityState.NOT_APPLICABLE
            }
            for dimension in sorted(
                expansion.activated_dimensions, key=lambda row: row.value
            ):
                if dimension not in decided_dimensions:
                    failures.append(
                        "Behavioral coverage expansion marked a dependent behavior "
                        "material but closure dropped it without a disposition: "
                        f"{dimension.value}"
                    )
            # Silence is never coverage: a subject discovery proved material
            # must carry an explicit decision for every dependency kind.
            for subject in expansion.undispositioned_subjects:
                failures.append(
                    "Behavioral coverage expansion marked a subject material but "
                    "no semantic dependency record dispositions it: "
                    f"{subject}"
                )
            for record in expansion.dependency_records:
                for slot in record.slots:
                    if (
                        slot.disposition
                        != CoverageExpansionDisposition.RESEARCH_REQUIRED
                    ):
                        continue
                    undecided = [
                        dimension
                        for dimension in slot.dimensions
                        if dimension not in decided_dimensions
                    ]
                    if undecided:
                        failures.append(
                            "A semantic dependency requires research but closure "
                            "never decided its behavior: "
                            f"{record.subject} / {slot.kind.value} "
                            f"({', '.join(row.value for row in undecided)})"
                        )
        if research_requirements is not None:
            research_by_question = {
                row.question_id: row for row in research_records or []
            }
            for requirement in research_requirements:
                if (
                    not requirement.material
                    or requirement.research_requirement == ResearchRequirement.NONE
                ):
                    continue
                record = research_by_question.get(requirement.question_id)
                if record is None:
                    failures.append(
                        "Mandatory research routing was skipped for a material "
                        f"question: {requirement.question_id}"
                    )
                    continue
                if record.requirement_id != requirement.requirement_id:
                    failures.append(
                        "Research traceability is broken for a material question: "
                        f"{requirement.question_id}"
                    )
                if record.research_status == ResearchStatus.PENDING:
                    failures.append(
                        f"Mandatory {requirement.research_requirement.value} research "
                        "is still PENDING for a material question: "
                        f"{requirement.question_id}"
                    )
                elif not record.research_request_ids and (
                    record.research_status
                    not in {
                        ResearchStatus.NOT_REQUIRED,
                        ResearchStatus.NOT_APPLICABLE,
                    }
                ):
                    failures.append(
                        "Mandatory research for a material question has no research "
                        f"request: {requirement.question_id}"
                    )
        if behavior_classifications is not None:
            finalizing_ids = {
                row.disposition_id
                for row in dispositions
                if row.disposition not in _UNRESOLVED_BEHAVIOR_DISPOSITIONS
            }
            class_by_disposition: dict[str, BehaviorClassificationRecord] = {}
            for classification in behavior_classifications:
                if classification.disposition_id in class_by_disposition:
                    failures.append(
                        "Duplicate behavior classification for a coverage decision: "
                        f"{classification.disposition_id}"
                    )
                class_by_disposition[classification.disposition_id] = (
                    classification
                )
            for disposition_id in sorted(set(class_by_disposition) - finalizing_ids):
                failures.append(
                    "Behavior classification targets an unknown or unresolved "
                    f"coverage decision: {disposition_id}"
                )
            for disposition_id in sorted(finalizing_ids - set(class_by_disposition)):
                failures.append(
                    "Resolved behavior is missing its existing-vs-new "
                    f"classification: {disposition_id}"
                )
            for row in dispositions:
                classification = class_by_disposition.get(row.disposition_id)
                if classification is None:
                    continue
                if classification.behavior_class in {
                    BehaviorChangeClass.UNKNOWN,
                    BehaviorChangeClass.CONFLICTED,
                } and row.disposition in {
                    CoverageDisposition.ACCEPTANCE_CONTRACT,
                    CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                }:
                    failures.append(
                        f"{classification.behavior_class.value} behavior cannot "
                        "ground an acceptance contract until it is resolved: "
                        f"{row.disposition_id}"
                    )
        nonblocking_unsatisfied_families: set[SemanticDimension] = set()
        if question_quality is not None:
            for family in question_quality.family_satisfaction:
                if (
                    family.status == InvestigationFamilySatisfactionStatus.UNSATISFIED
                    and family.activation_decision
                    == FamilyActivationDecision.ACTIVATE_NON_BLOCKING
                ):
                    nonblocking_unsatisfied_families.add(family.family_id)
                if (
                    family.status == InvestigationFamilySatisfactionStatus.UNSATISFIED
                    and family.activation_decision
                    == FamilyActivationDecision.ACTIVATE_BLOCKING
                ):
                    failures.append(
                        "Blocking investigation family has no valid contextual question "
                        "or evidence-backed resolution: "
                        f"{family.family_id.value}"
                    )
        for row in closure:
            if row.applicability == ApplicabilityState.NOT_APPLICABLE:
                continue
            if row.disposition == ClosureDisposition.NOT_APPLICABLE:
                failures.append(f"Applicable dimension was discarded: {row.closure_id}")
            terminal_rows = dispositions_by_closure_id.get(row.closure_id, [])
            if len(terminal_rows) != 1:
                failures.append(
                    "Material closure requires exactly one terminal disposition: "
                    f"{row.closure_id} (found {len(terminal_rows)})"
                )
            if (
                row.disposition == ClosureDisposition.UNRESOLVED_AND_EXPOSED
                and row.closure_id not in question_closure_ids
                and row.dimension not in nonblocking_unsatisfied_families
            ):
                failures.append(
                    f"Unresolved closure is not exposed by exact lineage: {row.closure_id}"
                )
        for hypothesis in hypotheses:
            terminal_rows = dispositions_by_hypothesis_id.get(
                hypothesis.hypothesis_id, []
            )
            if len(terminal_rows) != 1:
                failures.append(
                    "Material hypothesis requires exactly one terminal disposition: "
                    f"{hypothesis.hypothesis_id} (found {len(terminal_rows)})"
                )
                continue
            disposition = terminal_rows[0].disposition
            question = questions_by_id.get(hypothesis.derived_from_question_id)
            if hypothesis.state == HypothesisState.UNRESOLVED and disposition not in {
                CoverageDisposition.OPEN_QUESTION,
                CoverageDisposition.PRODUCT_SCOPE_QUESTION,
                # P3: a bounded acceptance TBD IS the exposed form of an
                # unresolved acceptance-material hypothesis.
                CoverageDisposition.ACCEPTANCE_TBD,
            }:
                failures.append(
                    "Unresolved material hypothesis is not exposed as an open "
                    f"question: {hypothesis.hypothesis_id}"
                )
            elif hypothesis.state == HypothesisState.REJECTED and disposition not in {
                CoverageDisposition.INVESTIGATED_AND_REJECTED,
                CoverageDisposition.OUT_OF_SCOPE,
            }:
                failures.append(
                    "Rejected material hypothesis lacks a rejected/out-of-scope "
                    f"disposition: {hypothesis.hypothesis_id}"
                )
            elif (
                hypothesis.state
                in {
                    HypothesisState.CONFIRMED,
                    HypothesisState.INFERRED_HIGH_CONFIDENCE,
                }
                and question is not None
                and question.dimension is not None
                and disposition
                not in {
                    CoverageDisposition.SEMANTIC_REGRESSION,
                    CoverageDisposition.STRUCTURAL_REGRESSION,
                    CoverageDisposition.CONFIGURATION_VARIANT,
                    CoverageDisposition.REFERENCE_REGRESSION,
                    CoverageDisposition.GENERATED_OUTPUT_VALIDATION,
                    CoverageDisposition.NEGATIVE_BOUNDARY,
                    CoverageDisposition.FAILURE_RECOVERY,
                    CoverageDisposition.CROSS_MODE_REGRESSION,
                    CoverageDisposition.LIFECYCLE_COVERAGE,
                    CoverageDisposition.NFR_COVERAGE,
                    CoverageDisposition.IMPLEMENTATION_ORACLE,
                    CoverageDisposition.TECHNICAL_NOTE,
                }
            ):
                failures.append(
                    "Verified material hypothesis did not reach QE regression "
                    f"coverage: {hypothesis.hypothesis_id}"
                )
        if (
            scope.enable_dita_ot_processing == DitaOtProcessingState.UNRESOLVED
            and not any("DITA-OT" in row.question for row in questions)
        ):
            failures.append("Publishing DITA-OT scope is unresolved but hidden.")
        return GateDecision(
            gate="BehavioralCompletenessGate",
            status=GateStatus.FAILED if failures else GateStatus.PASSED,
            failures=failures,
            checked_ids=sorted(
                {row.closure_id for row in closure}
                | {row.question_id for row in questions}
                | {
                    row.requirement_id for row in research_requirements or []
                }
                | {row.research_id for row in research_records or []}
                | {
                    row.classification_id
                    for row in behavior_classifications or []
                }
                | (
                    {
                        f"family:{row.family_id.value}"
                        for row in question_quality.family_satisfaction
                    }
                    if question_quality is not None
                    else set()
                )
            ),
        )

    def acceptance_promotion_gate(
        self,
        candidates: list[AcceptanceCandidate],
        facts: ContractFactSet,
        scope: ScopeResolution,
        dispositions: list[CoverageDispositionRecord],
        behavior_classifications: list[BehaviorClassificationRecord] | None = None,
        sufficiency: list[ClaimSufficiencyRecord] | None = None,
        clarifications: list[HumanClarification] | None = None,
    ) -> tuple[GateDecision, list[AcceptancePromotionDecision]]:
        facts_by_id = {row.fact_id: row for row in facts.facts}
        dispositions_by_id = {row.disposition_id: row for row in dispositions}
        classification_by_disposition = {
            row.disposition_id: row for row in behavior_classifications or []
        }
        sufficiency_by_claim = {
            row.claim_ref: row for row in sufficiency or []
        }
        decisions: list[AcceptancePromotionDecision] = []
        integrity_failures: list[str] = []
        for candidate in candidates:
            source_facts = [
                facts_by_id[fact_id]
                for fact_id in candidate.source_fact_ids
                if fact_id in facts_by_id
            ]
            # P2: an admitted, authority-sufficient human clarification that a
            # candidate is bound to is establishing ticket-scope evidence.
            clarification_supported = any(
                f"clarification:{row.clarification_id}" in candidate.evidence_ids
                and row.status == ClarificationStatus.ADMITTED
                and row.answer_classification in _CLARIFICATION_ESTABLISHING_CLASSES
                and row.authority_role in _CLARIFICATION_ESTABLISHING_AUTHORITIES
                for row in (clarifications or [])
            )
            authority_supported = (
                bool(source_facts) and all(
                    row.authoritative for row in source_facts
                )
            ) or clarification_supported
            source_dispositions = [
                dispositions_by_id[disposition_id]
                for disposition_id in candidate.source_disposition_ids
                if disposition_id in dispositions_by_id
            ]
            missing_disposition_ids = sorted(
                set(candidate.source_disposition_ids) - set(dispositions_by_id)
            )
            acceptance_disposition_supported = clarification_supported or (
                bool(source_dispositions) and all(
                    row.disposition
                    in {
                        CoverageDisposition.ACCEPTANCE_CONTRACT,
                        CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                    }
                    for row in source_dispositions
                )
            )
            belongs_to_human_contract = (
                facts.contract_mode != ContractMode.HUMAN_ACCEPTED_CONTRACT
                or candidate.accepted_human_contract
            )
            ticket_scope_supported = (
                candidate.accepted_human_contract
                or clarification_supported
                or any(
                    row.authority_class == AuthorityClass.CUSTOMER_REQUEST
                    for row in source_facts
                )
            )
            # C2B-C1: only ACCEPTANCE-class canonical coverage may promote.
            # QE_REGRESSION never becomes an AC merely because its evidence is
            # sufficient; INVESTIGATION never becomes an AC.
            candidate_text = candidate.statement.casefold()
            scope_established = (
                candidate.in_scope
                and ticket_scope_supported
                and not any(
                    value and value in candidate_text
                    for value in map(_scope_clause_value, scope.out_of_scope)
                )
            )
            unresolved = bool(candidate.unresolved_decision_ids)
            unresolved_classification = any(
                row.behavior_class
                in {BehaviorChangeClass.UNKNOWN, BehaviorChangeClass.CONFLICTED}
                for disposition_id in candidate.source_disposition_ids
                for row in [classification_by_disposition.get(disposition_id)]
                if row is not None
            )
            reasons: list[str] = []
            # C2B-C1: only ACCEPTANCE-class canonical coverage may promote.
            # QE_REGRESSION never becomes an AC merely because its evidence is
            # sufficient; INVESTIGATION never becomes an AC.
            classed = [row for row in source_dispositions if row.coverage_class]
            if (
                classed
                and not clarification_supported
                and not any(
                    row.coverage_class == "ACCEPTANCE" for row in classed
                )
            ):
                reasons.append(
                    "Only ACCEPTANCE-class canonical coverage may promote; "
                    "QE_REGRESSION/INVESTIGATION coverage never becomes an AC."
                )
            if (
                any(row.priority == "EXCLUDED" for row in classed)
                and not clarification_supported
            ):
                reasons.append(
                    "EXCLUDED coverage is intentionally outside current "
                    "coverage and never promotes."
                )
            if missing_disposition_ids:
                reasons.append(
                    "Acceptance candidate references an unavailable coverage disposition."
                )
                integrity_failures.append(
                    f"{candidate.candidate_id}: missing source dispositions "
                    + ", ".join(missing_disposition_ids)
                )
            if not acceptance_disposition_supported:
                reasons.append(
                    "Non-acceptance coverage disposition cannot be promoted to acceptance."
                )
                integrity_failures.append(
                    f"{candidate.candidate_id}: source disposition is not acceptance eligible"
                )
            if any(
                row.disposition == CoverageDisposition.ACCEPTANCE_TBD
                for row in source_dispositions
            ):
                # P3: a bounded TBD is acceptance-lane but never promotable
                # until its product decision is resolved.
                reasons.append(
                    "Unresolved acceptance dimension (TBD) cannot promote "
                    "until its product decision is resolved."
                )
            if not authority_supported:
                reasons.append("Intended behavior lacks product-contract authority.")
            if not belongs_to_human_contract:
                reasons.append(
                    "Human Accepted AC exists; this candidate is not part of that accepted contract."
                )
            if not scope_established:
                reasons.append(
                    "The candidate lacks current-ticket applicability or conflicts "
                    "with established scope."
                )
            if not candidate.observable:
                reasons.append("The expected result is not observable.")
            if candidate.regression_only:
                reasons.append("Regression coverage cannot be promoted to acceptance.")
            if candidate.implementation_mechanics_only:
                reasons.append(
                    "Implementation mechanics cannot define product acceptance."
                )
            if not candidate.exact_values_supported:
                reasons.append("An exact value is unsupported by authority.")
            # P1 / S1-C1 parity: generic safety rules on the promoted statement.
            statement_text = candidate.statement
            if _COMBINATION_CLAIM_RE.search(statement_text) and not any(
                _COMBINATION_CLAIM_RE.search(fact.literal) for fact in source_facts
            ):
                # Individually established dimensions never prove their
                # cross-product: a combined-behavior claim needs a source that
                # itself establishes the combination.
                reasons.append(
                    "Combined configuration behavior lacks combination evidence - "
                    "individually established controls do not prove their "
                    "cross-product."
                )
            if (
                _RETENTION_STEM_RE.search(statement_text)
                and _REMOVAL_STEM_RE.search(statement_text)
                and _USABILITY_STEM_RE.search(statement_text)
            ) and not any(
                _RETENTION_STEM_RE.search(fact.literal)
                and _USABILITY_STEM_RE.search(fact.literal)
                for fact in source_facts
            ):
                # Retaining an object after removing a child/resource does not
                # establish the object stays openable/usable/visible.
                reasons.append(
                    "Retained-object usability after removal requires separate "
                    "evidence - structural retention alone does not establish it."
                )
            if _BACKWARD_COMPAT_CLAIM_RE.search(statement_text) and not any(
                fact.fact_type == ContractFactType.COMPATIBILITY_REQUIREMENTS
                or _BACKWARD_COMPAT_CLAIM_RE.search(fact.literal)
                for fact in source_facts
            ):
                # A displayed default never proves upgrade/migration behavior.
                reasons.append(
                    "Backward-compatible/default behavior lacks compatibility "
                    "evidence - a new default does not prove upgrade behavior."
                )
            # C2B-S1: the validated sufficiency artifact gates promotion.
            # INSUFFICIENT/CONFLICTED never promote; PARTIAL promotes only the
            # explicitly bounded established portion (candidate evidence must
            # stay within the portion's evidence bindings).
            sufficiency_record = sufficiency_by_claim.get(candidate.candidate_id)
            if sufficiency_record is not None:
                if sufficiency_record.status == SufficiencyStatus.INSUFFICIENT:
                    reasons.append(
                        "Claim evidence is INSUFFICIENT (sufficiency artifact "
                        f"{sufficiency_record.sufficiency_id})."
                    )
                elif sufficiency_record.status == SufficiencyStatus.CONFLICTED:
                    reasons.append(
                        "Claim evidence is CONFLICTED (sufficiency artifact "
                        f"{sufficiency_record.sufficiency_id})."
                    )
                elif sufficiency_record.status == SufficiencyStatus.PARTIAL:
                    if not sufficiency_record.established_portion:
                        reasons.append(
                            "PARTIAL claim lacks an explicit established portion."
                        )
                    elif not set(candidate.evidence_ids) <= set(
                        sufficiency_record.evidence_refs
                    ):
                        reasons.append(
                            "Candidate exceeds the bounded established portion - "
                            "evidence outside the portion's bindings."
                        )
            if unresolved:
                reasons.append("A blocking product decision remains unresolved.")
            if unresolved_classification:
                reasons.append(
                    "The existing-vs-new behavior classification is unresolved."
                )
                unresolved = True
            # P2 defense in depth: a candidate resting only on problem/gap
            # statements can never promote (Reviewer failure class
            # PROBLEM_TO_SOLUTION_PROMOTION).  A research-derived candidate
            # is exempt: the admitted research finding IS the establishing
            # evidence for the desired behavior, so the solution does not
            # rest on the problem statement alone.
            research_backed = any(
                row.research_derived
                for row in source_dispositions
            )
            if (
                source_facts
                and all(
                    fact.fact_type == ContractFactType.PROBLEM_STATEMENT
                    for fact in source_facts
                )
                and not research_backed
            ):
                reasons.append(
                    "PROBLEM_TO_SOLUTION_PROMOTION: an established problem does "
                    "not establish a particular solution - the solution needs "
                    "its own establishing authority."
                )
            if candidate.contradicts_human_contract:
                reasons.append("The candidate contradicts Human Accepted AC.")
            promotable = not reasons
            status = (
                PromotionStatus.PROMOTED
                if promotable
                else PromotionStatus.BLOCKED
                if unresolved
                else PromotionStatus.REJECTED
            )
            resulting = (
                CoverageDisposition.ACCEPTANCE_CONTRACT
                if promotable and candidate.accepted_human_contract
                else CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
                if promotable
                else CoverageDisposition.OPEN_QUESTION
                if unresolved
                else CoverageDisposition.UNSUPPORTED_INFERENCE
            )
            decisions.append(
                AcceptancePromotionDecision(
                    candidate_id=candidate.candidate_id,
                    status=status,
                    resulting_disposition=resulting,
                    authority_supported=authority_supported,
                    scope_established=scope_established,
                    observable=candidate.observable,
                    exact_values_supported=candidate.exact_values_supported,
                    contradicts_human_contract=candidate.contradicts_human_contract,
                    sufficiency_ref=(
                        sufficiency_record.sufficiency_id
                        if sufficiency_record is not None
                        else ""
                    ),
                    reasons=reasons,
                )
            )
        failures = [
            f"{row.candidate_id}: {reason}"
            for row in decisions
            if row.status == PromotionStatus.PROMOTED and row.reasons
            for reason in row.reasons
        ]
        blocking_failures = [
            f"{row.candidate_id}: {reason}"
            for row in decisions
            if row.status == PromotionStatus.BLOCKED
            for reason in row.reasons
        ]
        if not candidates:
            blocking_failures.append(
                "No supported acceptance-contract candidate is available."
            )
            if scope.unresolved_fields:
                blocking_failures.append(
                    "Material scope remains unresolved: "
                    + ", ".join(scope.unresolved_fields)
                )
        if candidates and not any(
            row.status == PromotionStatus.PROMOTED for row in decisions
        ):
            blocking_failures.append(
                "No acceptance-contract candidate passed the promotion gate."
            )
        status = (
            GateStatus.FAILED
            if failures or integrity_failures
            else GateStatus.BLOCKED
            if facts.contract_mode == ContractMode.INSUFFICIENT_EVIDENCE_FOR_CONTRACT
            or blocking_failures
            else GateStatus.PASSED
        )
        return (
            GateDecision(
                gate="AcceptancePromotionGate",
                status=status,
                failures=failures + integrity_failures + blocking_failures,
                checked_ids=sorted(
                    {row.candidate_id for row in candidates}
                    | {
                        disposition_id
                        for row in candidates
                        for disposition_id in row.source_disposition_ids
                    }
                ),
            ),
            decisions,
        )

    def build_candidate_lifecycle(
        self,
        resolution: AcceptanceResolutionBatch,
        promotions: list[AcceptancePromotionDecision],
    ) -> list[CandidateLifecycleRecord]:
        """Prove every discovered acceptance candidate reaches one terminal state."""

        promotion_by_candidate: dict[str, AcceptancePromotionDecision] = {}
        for decision in promotions:
            if decision.candidate_id in promotion_by_candidate:
                raise RuntimeError(
                    "Material acceptance candidate has multiple promotion decisions: "
                    f"{decision.candidate_id}"
                )
            promotion_by_candidate[decision.candidate_id] = decision
        final_by_id = {row.candidate_id: row for row in resolution.candidates}
        if set(promotion_by_candidate) != set(final_by_id):
            missing = sorted(set(final_by_id) - set(promotion_by_candidate))
            extra = sorted(set(promotion_by_candidate) - set(final_by_id))
            detail = []
            if missing:
                detail.append("missing=" + ",".join(missing))
            if extra:
                detail.append("unexpected=" + ",".join(extra))
            raise RuntimeError(
                "Every finalized acceptance candidate requires exactly one terminal "
                "promotion decision (" + "; ".join(detail) + ")"
            )
        merge_by_member = {
            candidate_id: decision
            for decision in resolution.dedup_decisions
            for candidate_id in decision.merged_candidate_ids
        }
        rows: list[CandidateLifecycleRecord] = []
        for discovered in resolution.discovered_candidates:
            merge = merge_by_member.get(discovered.candidate_id)
            canonical_id = (
                merge.surviving_candidate_id if merge else discovered.candidate_id
            )
            canonical = final_by_id.get(canonical_id)
            if canonical is None:
                raise RuntimeError(
                    "Discovered material candidate has no canonical survivor: "
                    f"{discovered.candidate_id}"
                )
            promotion = promotion_by_candidate[canonical_id]
            evidence_required = not canonical.accepted_human_contract
            evidence_collected = bool(canonical.evidence_ids)
            stages = [
                CandidateLifecycleStage.CANDIDATE_DISCOVERED,
                CandidateLifecycleStage.APPLICABILITY_EVALUATED,
            ]
            if evidence_collected:
                stages.append(CandidateLifecycleStage.EVIDENCE_COLLECTED)
            stages.append(CandidateLifecycleStage.FINAL_DISPOSITION)
            rows.append(
                CandidateLifecycleRecord(
                    discovered_candidate_id=discovered.candidate_id,
                    canonical_candidate_id=canonical_id,
                    stages=stages,
                    evidence_required=evidence_required,
                    evidence_collected=evidence_collected,
                    final_disposition=_candidate_terminal_disposition(promotion),
                    promotion_status=promotion.status,
                    dedup_decision_id=merge.decision_id if merge else "",
                )
            )
        return sorted(rows, key=lambda row: row.lifecycle_id)

    def _bind_acceptance_records(
        self,
        section_items: dict[str, list[tuple[str, str]]],
        statement: str,
        candidate: AcceptanceCandidate,
        classification_by_disposition: Mapping[str, Any],
        lifecycle_by_canonical: Mapping[str, list[Any]],
    ) -> None:
        """Attach every record id that justifies a criterion to its text.

        A criterion the Writer split into two statements keeps the same
        bindings on each part, so completeness projection stays exhaustive and
        no supporting record becomes unaddressable.
        """

        items = section_items["acceptance_contract"]
        items.append((statement, candidate.candidate_id))
        items.extend(
            (statement, disposition_id)
            for disposition_id in candidate.source_disposition_ids
        )
        items.extend(
            (statement, classification_by_disposition[disposition_id].classification_id)
            for disposition_id in candidate.source_disposition_ids
            if disposition_id in classification_by_disposition
        )
        items.extend((statement, fact_id) for fact_id in candidate.source_fact_ids)
        for lifecycle_row in lifecycle_by_canonical[candidate.candidate_id]:
            items.append((statement, lifecycle_row.discovered_candidate_id))
            items.append((statement, lifecycle_row.lifecycle_id))
            if lifecycle_row.dedup_decision_id:
                items.append((statement, lifecycle_row.dedup_decision_id))

    def write_acceptance_criteria(
        self,
        candidates: list[AcceptanceCandidate],
        promotions: list[AcceptancePromotionDecision],
        facts: ContractFactSet,
        dispositions: list[CoverageDispositionRecord] | None = None,
    ) -> list[WrittenAcceptanceCriterion]:
        """D2 Writer: turn admitted candidates into testable acceptance criteria.

        The promotion gate decides WHAT may be an acceptance criterion; this
        stage decides HOW it reads.  It is deterministic by design - the
        canonical runtime has no LLM - so every transformation preserves the
        admitted content words and can only restructure them:

        * a compound request carrying two independent requirements is split so
          each observable outcome is separately pass/fail;
        * request grammar is reframed as an outcome;
        * a requested capability whose expected behavior is not established by
          authoritative evidence is kept in the contract as a bounded (TBD)
          question instead of being relocated or asserted;
        * applicable same-outcome variants attach as sub-points.

        It never admits a candidate the promotion gate rejected, and never
        invents behavior absent from the admitted statement.
        """

        facts_by_id = {row.fact_id: row for row in facts.facts}
        candidate_by_id = {row.candidate_id: row for row in candidates}
        dispositions_by_id = {
            row.disposition_id: row for row in (dispositions or [])
        }
        written: list[WrittenAcceptanceCriterion] = []
        seen_outcomes: set[str] = set()

        for decision in promotions:
            if decision.status != PromotionStatus.PROMOTED:
                continue
            candidate = candidate_by_id.get(decision.candidate_id)
            if candidate is None:
                continue
            source_line = _acceptance_source_line(
                list(candidate.source_fact_ids),
                facts_by_id,
                list(candidate.evidence_ids),
            )
            proposed = (
                facts.contract_mode == ContractMode.HUMAN_ACCEPTED_CONTRACT
                and decision.resulting_disposition
                == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
            )
            # An unresolved requested capability stays acceptance-lane, phrased
            # as the decision QE still needs.  Splitting it would fabricate
            # resolved sub-requirements the evidence never established.
            if _is_requested_capability(candidate.statement):
                question = _derive_tbd_question(candidate.statement)
                if question is None:
                    continue
                key = question.casefold()
                if key in seen_outcomes:
                    continue
                if _absorb_near_duplicate(
                    written,
                    question,
                    unresolved=True,
                    candidate_ids=[candidate.candidate_id],
                    fact_ids=list(candidate.source_fact_ids),
                    disposition_ids=list(candidate.source_disposition_ids),
                    evidence_ids=list(candidate.evidence_ids),
                ):
                    continue
                seen_outcomes.add(key)
                written.append(
                    WrittenAcceptanceCriterion(
                        outcome=question,
                        unresolved=True,
                        source_line=source_line,
                        source_candidate_ids=[candidate.candidate_id],
                        source_fact_ids=list(candidate.source_fact_ids),
                        source_disposition_ids=list(candidate.source_disposition_ids),
                        evidence_ids=list(candidate.evidence_ids),
                    )
                )
                continue

            for clause in _split_independent_requirements(candidate.statement):
                outcome = _derive_outcome_statement(clause) or _as_outcome_sentence(
                    clause
                )
                if proposed and not outcome.startswith("Proposed: "):
                    outcome = f"Proposed: {outcome}"
                key = outcome.casefold()
                if key in seen_outcomes:
                    continue
                if _absorb_near_duplicate(
                    written,
                    outcome,
                    unresolved=False,
                    candidate_ids=[candidate.candidate_id],
                    fact_ids=list(candidate.source_fact_ids),
                    disposition_ids=list(candidate.source_disposition_ids),
                    evidence_ids=list(candidate.evidence_ids),
                ):
                    continue
                seen_outcomes.add(key)
                written.append(
                    WrittenAcceptanceCriterion(
                        outcome=outcome,
                        source_line=source_line,
                        source_candidate_ids=[candidate.candidate_id],
                        source_fact_ids=list(candidate.source_fact_ids),
                        source_disposition_ids=list(candidate.source_disposition_ids),
                        evidence_ids=list(candidate.evidence_ids),
                    )
                )

        # D1-c: acceptance-material but unresolved coverage renders as a (TBD)
        # question INSIDE the contract.  It is attached to the criterion it
        # relates to, and only becomes its own criterion when nothing relates.
        for row in dispositions or []:
            if row.disposition != CoverageDisposition.ACCEPTANCE_TBD:
                continue
            question = _derive_tbd_question(row.candidate)
            if question is None:
                continue
            if any(
                question.casefold() == existing.outcome.casefold()
                or any(
                    question.casefold() == sub.text.casefold()
                    for sub in existing.sub_points
                )
                for existing in written
            ):
                continue
            host = _closest_criterion(question, written)
            sub_point = AcceptanceSubPoint(
                text=question,
                kind=AcceptanceSubPointKind.TBD_QUESTION,
                source_fact_ids=list(row.source_fact_ids),
                source_disposition_ids=[row.disposition_id],
                evidence_ids=list(row.evidence_ids),
            )
            if host is None:
                written.append(
                    WrittenAcceptanceCriterion(
                        outcome=question,
                        unresolved=True,
                        source_line=_acceptance_source_line(
                            list(row.source_fact_ids), facts_by_id
                        ),
                        source_fact_ids=list(row.source_fact_ids),
                        source_disposition_ids=[row.disposition_id],
                        evidence_ids=list(row.evidence_ids),
                    )
                )
                continue
            # Rebuild rather than mutate: criterion_id is a content hash the
            # model derives at validation, so an in-place edit would leave it
            # pointing at the pre-merge content.
            written[written.index(host)] = WrittenAcceptanceCriterion(
                outcome=host.outcome,
                sub_points=[*host.sub_points, sub_point],
                unresolved=host.unresolved,
                source_line=host.source_line,
                source_candidate_ids=list(host.source_candidate_ids),
                source_fact_ids=[*host.source_fact_ids, *row.source_fact_ids],
                source_disposition_ids=[
                    *host.source_disposition_ids,
                    row.disposition_id,
                ],
                evidence_ids=[*host.evidence_ids, *row.evidence_ids],
            )

        # D1-d: applicable regression-class coverage belongs INSIDE the flat
        # acceptance contract, as a sub-point of the outcome it qualifies.
        # Leaving it in a separate QE-regression lane loses it outright,
        # because the flat contract renders no such lane.  It attaches only to
        # a criterion it genuinely qualifies and never becomes a criterion of
        # its own, so C2B-C1 promotion authority is unchanged: regression
        # coverage still cannot assert an acceptance outcome by itself.
        for row in dispositions or []:
            if (
                row.coverage_class != "QE_REGRESSION"
                or row.priority != "P1"
                or row.applicability != "APPLICABLE"
            ):
                continue
            variant = _derive_variant_statement(row.candidate)
            if variant is None:
                continue
            if any(
                variant.casefold() == existing.outcome.casefold()
                or any(
                    variant.casefold() == sub.text.casefold()
                    for sub in existing.sub_points
                )
                for existing in written
            ):
                continue
            host = _closest_variant_host(variant, written)
            if host is None:
                # No acceptance outcome this behavior qualifies.  Inventing a
                # parent would assert coverage the evidence never established.
                continue
            if (
                sum(
                    1
                    for sub in host.sub_points
                    if sub.kind == AcceptanceSubPointKind.CONFIRMED_VARIANT
                )
                >= _MAX_VARIANT_SUB_POINTS
            ):
                continue
            sub_point = AcceptanceSubPoint(
                text=variant,
                kind=AcceptanceSubPointKind.CONFIRMED_VARIANT,
                source_fact_ids=list(row.source_fact_ids),
                source_disposition_ids=[row.disposition_id],
                evidence_ids=list(row.evidence_ids),
            )
            written[written.index(host)] = WrittenAcceptanceCriterion(
                outcome=host.outcome,
                sub_points=[*host.sub_points, sub_point],
                unresolved=host.unresolved,
                source_line=host.source_line,
                source_candidate_ids=list(host.source_candidate_ids),
                source_fact_ids=[*host.source_fact_ids, *row.source_fact_ids],
                source_disposition_ids=[
                    *host.source_disposition_ids,
                    row.disposition_id,
                ],
                evidence_ids=[*host.evidence_ids, *row.evidence_ids],
            )
        # Merging and TBD attachment both widen a criterion's fact set, so the
        # Source line is recomputed from the final bindings.  A criterion must
        # never credit fewer - or more - sources than it actually rests on.
        for index, criterion in enumerate(written):
            recomputed = _acceptance_source_line(
                list(criterion.source_fact_ids),
                facts_by_id,
                list(criterion.evidence_ids),
            )
            if not recomputed or recomputed == criterion.source_line:
                continue
            written[index] = criterion.model_copy(
                update={"source_line": recomputed}
            )
        _ = dispositions_by_id
        return written

    def render_final_plan(
        self,
        request: GenerationRequest,
        facts: ContractFactSet,
        scope: ScopeResolution,
        model: CanonicalBehaviorModel,
        closure: list[ClosureDimensionResult],
        questions: list[MissingQuestion],
        impacts: list[DomainImpact],
        dispositions: list[CoverageDispositionRecord],
        candidates: list[AcceptanceCandidate],
        promotions: list[AcceptancePromotionDecision],
        gates: list[GateDecision],
        acceptance_resolution: AcceptanceResolutionBatch | None = None,
        candidate_lifecycle: list[CandidateLifecycleRecord] | None = None,
        research_records: list[QuestionResearchRecord] | None = None,
        behavior_classifications: list[BehaviorClassificationRecord] | None = None,
        clarifications: list[HumanClarification] | None = None,
        research_resolved_question_ids: set[str] | None = None,
        waiting_for_research: bool = False,
        convergence: list | None = None,
        written_acceptance_criteria: list[WrittenAcceptanceCriterion] | None = None,
    ) -> tuple[StructuredQEPlan, str]:
        if research_records is not None:
            incomplete_research_question_ids = {
                row.question_id
                for row in research_records
                if row.research_requirement != ResearchRequirement.NONE
                and row.research_status in _INCOMPLETE_RESEARCH_STATUSES
            }
            if incomplete_research_question_ids:
                open_states = {
                    CoverageDisposition.OPEN_QUESTION,
                    CoverageDisposition.PRODUCT_SCOPE_QUESTION,
                    CoverageDisposition.ENGINEERING_DESIGN_DECISION,
                    # P3: a bounded TBD is NOT finalization - it keeps the
                    # unresolved decision visible; the renderer may carry it.
                    CoverageDisposition.ACCEPTANCE_TBD,
                }
                for disposition in dispositions:
                    if disposition.disposition in open_states:
                        continue
                    # An INVESTIGATION-lane row is not a finalization either:
                    # it carries no acceptance or regression claim, can never
                    # be promoted to an AC, and is precisely how research that
                    # ran but could not settle the question stays visible.
                    # Suppressing it would discard the completed half of a
                    # multi-source question and re-hide exactly what the
                    # mandated research found.  Acceptance- and
                    # regression-bearing dispositions stay fail-closed.
                    if disposition.coverage_class == "INVESTIGATION":
                        continue
                    offending = sorted(
                        set(disposition.source_question_ids)
                        & incomplete_research_question_ids
                    )
                    if offending:
                        raise RuntimeError(
                            "FinalQEPlanRenderer must not compensate for missing "
                            f"mandatory research: {disposition.disposition_id} "
                            f"finalizes {disposition.disposition.value} for "
                            "question(s) "
                            + ", ".join(offending)
                            + " whose mandatory research is incomplete."
                        )
        acceptance_resolution = acceptance_resolution or AcceptanceResolutionBatch(
            discovered_candidates=candidates,
            candidates=candidates,
        )
        candidate_lifecycle = candidate_lifecycle or self.build_candidate_lifecycle(
            acceptance_resolution, promotions
        )
        candidate_by_id = {row.candidate_id: row for row in candidates}
        classification_by_disposition: dict[str, BehaviorClassificationRecord] = {
            row.disposition_id: row for row in behavior_classifications or []
        }
        if behavior_classifications is not None:
            documented_anywhere = {
                evidence_id
                for row in behavior_classifications
                for evidence_id in row.existing_evidence_ids
            }
            for decision in promotions:
                if decision.status != PromotionStatus.PROMOTED:
                    continue
                promoted_candidate = candidate_by_id[decision.candidate_id]
                linked_classifications = [
                    classification_by_disposition[disposition_id]
                    for disposition_id in promoted_candidate.source_disposition_ids
                    if disposition_id in classification_by_disposition
                ]
                if any(
                    row.behavior_class
                    in {BehaviorChangeClass.UNKNOWN, BehaviorChangeClass.CONFLICTED}
                    for row in linked_classifications
                ):
                    raise RuntimeError(
                        "FinalQEPlanRenderer must not write an acceptance "
                        "criterion whose existing-vs-new classification is "
                        f"unresolved: {promoted_candidate.candidate_id}"
                    )
                if linked_classifications and all(
                    row.behavior_class == BehaviorChangeClass.NEW_REQUIREMENT
                    for row in linked_classifications
                ):
                    documented = sorted(
                        set(promoted_candidate.evidence_ids) & documented_anywhere
                    )
                    if documented:
                        raise RuntimeError(
                            "FinalQEPlanRenderer must not attribute existing "
                            "documentation to a new requirement: "
                            f"{promoted_candidate.candidate_id} cites "
                            + ", ".join(documented)
                        )
        lifecycle_by_canonical: dict[str, list[CandidateLifecycleRecord]] = (
            defaultdict(list)
        )
        for lifecycle_row in candidate_lifecycle:
            lifecycle_by_canonical[lifecycle_row.canonical_candidate_id].append(
                lifecycle_row
            )
        disposition_sections: dict[CoverageDisposition, str] = dict(
            _DISPOSITION_SECTIONS
        )
        titles = {
            "issue_understanding": "Summary",
            "product_scope": "Publishing / product scope",
            "acceptance_contract": (
                "Acceptance contract"
                if facts.contract_mode == ContractMode.HUMAN_ACCEPTED_CONTRACT
                else "Proposed acceptance contract"
            ),
            "finalization": "Finalization",
            "product_decisions": "Product decisions required",
            "semantic_coverage": "Semantic coverage",
            "structural_hierarchy_coverage": "Structural / hierarchy coverage",
            "referenced_content_coverage": "Referenced content coverage",
            "configuration_state_coverage": "Configuration / state coverage",
            "transformation_processing_coverage": "Transformation / processing coverage",
            "generated_output_validation": "Generated output validation",
            "reference_link_integrity": "Reference / link integrity",
            "negative_boundary_coverage": "Negative / boundary coverage",
            "failure_recovery_coverage": "Failure / recovery coverage",
            "lifecycle_coverage": "Lifecycle coverage",
            "cross_mode_regression": "Cross-mode regression",
            "nfr_coverage": "NFR coverage",
            "explicit_out_of_scope": "Explicit out of scope",
            "investigated_and_rejected": "Investigated and rejected",
            "technical_notes": "Technical notes",
            "known_limitations": "Known limitations",
            "evidence_gaps": "Evidence gaps",
            "coverage_gate_result": "Coverage gate result",
        }
        section_items: dict[str, list[tuple[str, str]]] = defaultdict(list)
        # Dispositions suppressed from the human-facing evidence-gaps lane
        # (settled research or planner boilerplate with no evidence linkage)
        # remain in the trace; the render invariant exempts them explicitly.
        skipped_open_dispositions: set[str] = set()
        # Issue understanding is WHAT THE TICKET STATES: only facts carrying
        # a ticket/human authority class belong.  Retrieved documentation may
        # establish existing product behavior downstream, but a doc-chunk
        # sentence is never the issue's own understanding.
        understanding = [
            row
            for row in facts.facts
            if row.fact_type
            in {
                ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                # UX1: narrative context is the legitimate issue-understanding
                # source for thin tickets (no requirement signal, no promotion).
                ContractFactType.CONTEXT_STATEMENT,
            }
            and row.authority_class in _TICKET_UNDERSTANDING_AUTHORITIES
        ]
        for fact in understanding:
            section_items["issue_understanding"].append((fact.literal, fact.fact_id))
        for item in scope.in_scope:
            section_items["product_scope"].append((f"In scope: {item}", ""))
        if scope.primary_preset_type:
            section_items["product_scope"].append(
                (f"Preset: {scope.primary_preset_type}", "")
            )
        for interface in scope.execution_interfaces:
            section_items["product_scope"].append(
                (f"Execution interface: {interface}", "")
            )
        if scope.enable_dita_ot_processing != DitaOtProcessingState.NOT_APPLICABLE:
            section_items["product_scope"].append(
                (
                    f"Enable DITA-OT Processing: {scope.enable_dita_ot_processing.value}",
                    "",
                )
            )
        promoted_ids: list[str] = []
        acceptance_sources: dict[str, str] = {}
        facts_by_id = {row.fact_id: row for row in facts.facts}
        # D2: the Writer owns the human-facing wording.  The renderer stays a
        # presenter - it substitutes the written outcome for the raw candidate
        # statement and keeps every record-id binding, so a split criterion is
        # still fully addressable in the completeness projection.
        written_by_candidate: dict[str, list[WrittenAcceptanceCriterion]] = {}
        for criterion in written_acceptance_criteria or []:
            for candidate_id in criterion.source_candidate_ids:
                written_by_candidate.setdefault(candidate_id, []).append(criterion)
        # D1-c: a bounded TBD now renders inside the acceptance contract, so its
        # own records must be addressable there instead of in a sibling section.
        for criterion in written_acceptance_criteria or []:
            rendered = _render_written_criterion(criterion)
            acceptance_sources.setdefault(rendered.strip(), criterion.source_line)
            tbd_records = [
                record_id
                for sub_point in criterion.sub_points
                if sub_point.kind == AcceptanceSubPointKind.TBD_QUESTION
                for record_id in (
                    *sub_point.source_disposition_ids,
                    *sub_point.source_fact_ids,
                )
            ]
            if criterion.unresolved and not criterion.source_candidate_ids:
                tbd_records.extend(criterion.source_disposition_ids)
                tbd_records.extend(criterion.source_fact_ids)
                section_items["acceptance_contract"].append((rendered, ""))
            for record_id in tbd_records:
                if record_id:
                    section_items["acceptance_contract"].append((rendered, record_id))
        for decision in promotions:
            if decision.status == PromotionStatus.PROMOTED:
                candidate = candidate_by_id[decision.candidate_id]
                promoted_ids.append(candidate.candidate_id)
                statement = candidate.statement
                if (
                    facts.contract_mode == ContractMode.HUMAN_ACCEPTED_CONTRACT
                    and decision.resulting_disposition
                    == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
                ):
                    statement = f"Proposed: {statement}"
                authored = written_by_candidate.get(candidate.candidate_id) or []
                statements = [
                    _render_written_criterion(criterion) for criterion in authored
                ] or [_as_manual_qe_check(statement)]
                for rendered in statements:
                    acceptance_sources.setdefault(
                        rendered.strip(),
                        _acceptance_source_line(
                            list(candidate.source_fact_ids),
                            facts_by_id,
                            list(candidate.evidence_ids),
                        ),
                    )
                for statement in statements:
                    self._bind_acceptance_records(
                        section_items,
                        statement,
                        candidate,
                        classification_by_disposition,
                        lifecycle_by_canonical,
                    )
                statement = statements[0]
            else:
                candidate = candidate_by_id[decision.candidate_id]
                reason = "; ".join(decision.reasons) or "Not promoted."
                rejected_text = f"{candidate.statement} — {reason}"
                # Preserve the established public markdown projection.  The
                # typed lifecycle carries the more precise terminal state.
                section_key = "evidence_gaps"
                section_items[section_key].append(
                    (rejected_text, candidate.candidate_id)
                )
                section_items[section_key].extend(
                    (rejected_text, disposition_id)
                    for disposition_id in candidate.source_disposition_ids
                )
                section_items[section_key].extend(
                    (rejected_text, fact_id) for fact_id in candidate.source_fact_ids
                )
                for lifecycle_row in lifecycle_by_canonical[candidate.candidate_id]:
                    section_items[section_key].append(
                        (rejected_text, lifecycle_row.discovered_candidate_id)
                    )
                    section_items[section_key].append(
                        (rejected_text, lifecycle_row.lifecycle_id)
                    )
                    if lifecycle_row.dedup_decision_id:
                        section_items[section_key].append(
                            (rejected_text, lifecycle_row.dedup_decision_id)
                        )
        open_dispositions = {
            CoverageDisposition.OPEN_QUESTION,
            CoverageDisposition.PRODUCT_SCOPE_QUESTION,
            CoverageDisposition.ENGINEERING_DESIGN_DECISION,
            # P3: a bounded TBD keeps its question in the open set.
            CoverageDisposition.ACCEPTANCE_TBD,
        }
        linked_question_ids = {
            question_id
            for disposition in dispositions
            for question_id in disposition.source_question_ids
        }
        open_question_ids = {
            question_id
            for disposition in dispositions
            if disposition.disposition in open_dispositions
            for question_id in disposition.source_question_ids
        }
        resolved_question_ids = linked_question_ids - open_question_ids
        clarified_question_ids = {
            row.question_ref
            for row in clarifications or []
            if row.status == ClarificationStatus.ADMITTED
        }
        # R2: research-resolved questions are handled in the loop below: when
        # their research answer promoted acceptance coverage they are released;
        # when nothing promoted, the acceptance decision still needs the human.
        #
        # Decision-quality product questions: convergence converts each
        # residual acceptance-changing uncertainty into one concrete product
        # decision (established behavior + undecided point + what QE must
        # decide).  The raw Jira problem prose is never the human question,
        # and lifecycle/currentness or evidence-quality conflicts never
        # become a product-decision question by themselves.
        convergence_by_question = {
            row.question_id: row for row in (convergence or [])
        }
        decision_question_ids: set[str] = set()
        # A decision-quality line represents its question's TBD disposition;
        # the disposition id rides on the decision line so the render
        # invariant (every disposition lands in a section) still holds.
        tbd_disposition_by_question: dict[str, str] = {}
        for disposition in dispositions:
            if disposition.disposition == CoverageDisposition.ACCEPTANCE_TBD:
                for question_id in disposition.source_question_ids:
                    tbd_disposition_by_question.setdefault(
                        question_id, disposition.disposition_id
                    )
        represented_tbd_disposition_ids: set[str] = set()
        for conv in convergence or []:
            if not conv.decision:
                continue
            if (
                conv.question_id in resolved_question_ids
                or conv.question_id in clarified_question_ids
            ):
                # A question whose coverage was resolved is never reopened by
                # a research unknown alone; only a live evidence conflict
                # (product-contract or implementation) stays visible.
                from app.services.convergence_service import (
                    _ACCEPTANCE_CHANGING_CONFLICTS,
                )
                if not any(
                    conflict_class in _ACCEPTANCE_CHANGING_CONFLICTS
                    for conflict_class in conv.conflict_classes
                ):
                    continue
            record_id = tbd_disposition_by_question.get(
                conv.question_id, conv.question_id
            )
            if record_id in tbd_disposition_by_question.values():
                represented_tbd_disposition_ids.add(record_id)
            section_items["product_decisions"].append(
                ("\n".join([conv.decision, *_convergence_detail_lines(conv)]), record_id)
            )
            decision_question_ids.add(conv.question_id)
        # Developer-perspective findings: implementation-lane conflicts
        # (code-internal contradictions, requirement-vs-code mismatches) are
        # recorded as technical notes - never as product decisions.
        for conv in convergence or []:
            for finding in getattr(conv, "implementation_findings", None) or []:
                section_items["technical_notes"].append(
                    (f"Implementation finding: {finding}", conv.convergence_id)
                )
        research_by_question = {
            row.question_id: row for row in research_records or []
        }
        dimension_by_question = {
            row.question_id: row.dimension for row in questions
        }
        for question in questions:
            if question.question_id in resolved_question_ids:
                continue
            if question.question_id in clarified_question_ids:
                continue
            if question.question_id in decision_question_ids:
                # The decision-quality line already represents this question.
                continue
            conv = convergence_by_question.get(question.question_id)
            if question.blocking and conv is not None and not conv.decision:
                # G2: convergence is the authoritative TBD/clarification
                # eligibility gate.  A research-answered question, a
                # lifecycle/currentness-only conflict, or an evidence-quality
                # limitation never surfaces as a product-decision TBD.
                continue
            # R2 release nuance: a research-resolved question whose answer
            # could not promote (e.g. documented but not yet accepted product
            # decision) must remain visible when nothing was promoted - the
            # acceptance decision still belongs to the human.
            if (
                question.question_id in set(research_resolved_question_ids or ())
                and promoted_ids
            ):
                continue
            key = "product_decisions" if question.blocking else "evidence_gaps"
            if key == "evidence_gaps":
                # Generic planner boilerplate is not an evidence gap: a
                # non-blocking question surfaces only when material evidence
                # shows it can change acceptance behavior.  A question whose
                # mandated research terminated with an answer is settled only
                # after its coverage question resolved. A research answer can
                # establish a baseline yet still leave a material product
                # decision unanswered, which must remain visible.
                research = research_by_question.get(question.question_id)
                if research is not None and research.research_status in {
                    ResearchStatus.ANSWER_FOUND,
                    ResearchStatus.PARTIAL,
                } and question.question_id not in open_question_ids:
                    continue
                if (
                    research is not None
                    and research.research_status
                    in {
                        ResearchStatus.NOT_APPLICABLE,
                        ResearchStatus.NOT_REQUIRED,
                    }
                    and question.dimension is None
                ):
                    continue
            section_items[key].append((question.question, question.question_id))
        # P1: clarification audit - stale/rejected clarifications stay visible;
        # admitted ones live in the trace (L1 lineage), never in AC source lines.
        for clarification in clarifications or []:
            if clarification.status in {
                ClarificationStatus.STALE,
                ClarificationStatus.REJECTED,
            }:
                section_items["evidence_gaps"].append(
                    (
                        f"Clarification for {clarification.question_ref} not "
                        f"applied ({clarification.status.value}): "
                        f"{clarification.admission_detail}",
                        clarification.clarification_id,
                    )
                )
        for disposition in dispositions:
            if disposition.disposition in {
                CoverageDisposition.ACCEPTANCE_CONTRACT,
                CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            }:
                continue
            is_open_disposition = disposition.disposition in {
                CoverageDisposition.OPEN_QUESTION,
                CoverageDisposition.PRODUCT_SCOPE_QUESTION,
                CoverageDisposition.ENGINEERING_DESIGN_DECISION,
                CoverageDisposition.ACCEPTANCE_TBD,
            }
            if (
                disposition.disposition == CoverageDisposition.ACCEPTANCE_TBD
                and disposition.disposition_id in represented_tbd_disposition_ids
            ):
                # Represented by the decision-quality line built from the
                # convergence record - the raw question prose is never the
                # human-facing product decision.
                continue
            key = disposition_sections.get(disposition.disposition)
            if key is None:
                raise RuntimeError(
                    "FinalQEPlanRenderer has no section for disposition: "
                    f"{disposition.disposition.value}"
                )
            if key == "evidence_gaps" and disposition.source_question_ids:
                # Same rule as the question loop: settled or boilerplate
                # planner questions are not evidence gaps.  Boilerplate =
                # planner-family question (no dimension) whose research is
                # not applicable/required; dimension-linked questions carry
                # real investigation linkage and stay visible.
                settled = False
                boilerplate = False
                for question_id in disposition.source_question_ids:
                    research = research_by_question.get(question_id)
                    if research is None:
                        continue
                    if research.research_status in {
                        ResearchStatus.ANSWER_FOUND,
                        ResearchStatus.PARTIAL,
                    }:
                        settled = True
                    elif (
                        research.research_status
                        in {
                            ResearchStatus.NOT_APPLICABLE,
                            ResearchStatus.NOT_REQUIRED,
                        }
                        and dimension_by_question.get(question_id) is None
                    ):
                        boilerplate = True
                if (settled and not is_open_disposition) or boilerplate:
                    # Settled questions are answered, not gaps; boilerplate
                    # rows without any evidence linkage are planner noise.
                    # The disposition still lands in the trace (the render
                    # invariant counts it via the plan's disposition list).
                    skipped_open_dispositions.add(disposition.disposition_id)
                    continue
            disposition_text = _plain_candidate(disposition.candidate)
            section_items[key].append((disposition_text, disposition.disposition_id))
            classification = classification_by_disposition.get(
                disposition.disposition_id
            )
            if classification is not None:
                section_items[key].append(
                    (disposition_text, classification.classification_id)
                )
            section_items[key].extend(
                (disposition_text, fact_id) for fact_id in disposition.source_fact_ids
            )
        for item in scope.out_of_scope:
            section_items["explicit_out_of_scope"].append((item, ""))
        for oracle in model.generated_output_oracles:
            section_items["generated_output_validation"].append(
                (oracle.replace("_", " ").title(), oracle)
            )
        for gate in gates:
            detail = f"{gate.gate.value}: {gate.status.value}"
            if gate.failures:
                detail += f" — {'; '.join(gate.failures)}"
            section_items["coverage_gate_result"].append((detail, gate.gate.value))

        # Zero-AC finalization gate: a plan must never leave the acceptance contract
        # silently empty. When nothing was promoted, state the finalization outcome and
        # WHY in a human-visible section instead of just omitting the contract heading
        # (the reason otherwise hides in "Coverage gate result"). Every item carries an
        # empty record id, so this does not affect the completeness-invariant projection
        # checks below.
        if not section_items["acceptance_contract"]:
            material_contract = (
                facts.contract_mode == ContractMode.HUMAN_ACCEPTED_CONTRACT
                or any(
                    row.fact_type == ContractFactType.DIRECT_EXPECTED_BEHAVIOR
                    for row in facts.facts
                )
            )
            block_reasons: list[str] = []
            for decision in promotions:
                if decision.status != PromotionStatus.PROMOTED:
                    for reason in decision.reasons:
                        if reason and reason not in block_reasons:
                            block_reasons.append(reason)
            unresolved = [q.question for q in questions if q.blocking]
            if not material_contract:
                state = (
                    "NO_ACCEPTANCE_CONTRACT_REQUIRED: no material customer/product "
                    "contract was extracted from the evidence."
                )
            elif block_reasons or unresolved:
                state = (
                    "NEEDS_REVIEW: a material contract exists but no acceptance criteria "
                    "were promoted — resolve the items below, then re-run."
                )
            else:
                state = (
                    "NEEDS_REVIEW: a material contract exists but no acceptance criteria "
                    "were promoted."
                )
            section_items["finalization"].append((state, ""))
            for reason in block_reasons[:6]:
                section_items["finalization"].append((f"Blocked: {reason}", ""))
            for question in unresolved[:6]:
                section_items["finalization"].append(
                    (f"Unresolved product decision: {question}", "")
                )

        # Runtime UAC lint pass: apply the skill uac_linter's plan-text checks to the
        # promoted acceptance criteria so shipped runtime plans meet the same quality bar
        # (the skill linter only runs when authoring through the skill, not on VM output).
        # Advisory: findings surface in the coverage-gate section; no AC is mutated.
        promoted_statements: list[str] = []
        seen_promoted: set[str] = set()
        for statement, _record in section_items["acceptance_contract"]:
            normalized = statement.strip()
            if normalized and normalized not in seen_promoted:
                seen_promoted.add(normalized)
                promoted_statements.append(normalized)
        for lint_problem in _lint_acceptance_criteria(promoted_statements):
            section_items["coverage_gate_result"].append(
                (f"AcceptanceContractLint: {lint_problem}", "acceptance_contract_lint")
            )

        # Reviewer contract (deterministic): a promoted AC that still carries
        # meta/evidence commentary or the customer's raw problem prose is not
        # an observable outcome - the final UAC is rejected, never repaired
        # in place.  This appends a FAILED gate before the branch below reads
        # the gate list.
        reviewer_failures = [
            "Acceptance criterion is meta/evidence commentary, not an "
            f"observable product outcome: {statement[:120]}"
            for statement in promoted_statements
            if _AC_META_PROSE_RE.search(statement)
        ]

        # An accepted human contract IS the ticket text, and UAC fidelity
        # requires preserving it exactly.  Only a contract the runtime
        # proposed itself can be rejected for asking instead of asserting.
        if facts.contract_mode != ContractMode.HUMAN_ACCEPTED_CONTRACT:
            reviewer_failures.extend(
                "Acceptance criterion requests a capability instead of "
                f"stating a testable product outcome: {statement[:120]}"
                for statement in promoted_statements
                if _is_request_not_outcome(statement)
            )

        # Coverage lanes that only announce an internal record are not
        # coverage.  They are suppressed from the human-facing markdown at
        # render time rather than failing the plan: the closure records stay
        # in the structured plan and the trace, so nothing is lost, but a
        # content-free bullet never reaches the tester.
        if reviewer_failures:
            gates.append(
                GateDecision(
                    gate=CanonicalRuntimeStage.FINAL_QE_PLAN_RENDERER,
                    status=GateStatus.FAILED,
                    failures=reviewer_failures,
                    checked_ids=sorted(seen_promoted),
                )
            )

        order = list(titles)
        sections: list[PlanSection] = []
        for key in order:
            items = section_items.get(key, [])
            if not items:
                continue
            deduped: dict[str, set[str]] = {}
            for text, record_id in items:
                normalized_text = text.strip()
                if key == "product_decisions" and not normalized_text.startswith(
                    "(TBD)"
                ):
                    # The final UAC distinguishes established behavior from
                    # unresolved decisions: every open product decision is
                    # marked (TBD) in both render paths.
                    normalized_text = f"(TBD) {normalized_text}"
                deduped.setdefault(normalized_text, set())
                if record_id:
                    deduped[normalized_text].add(record_id)
            sections.append(
                PlanSection(
                    section_key=key,
                    title=titles[key],
                    items=list(deduped),
                    source_record_ids=sorted(
                        {
                            record_id
                            for record_ids in deduped.values()
                            for record_id in record_ids
                        }
                    ),
                )
            )
        sections_by_source_id: dict[str, list[PlanSection]] = defaultdict(list)
        for section in sections:
            for source_id in section.source_record_ids:
                sections_by_source_id[source_id].append(section)
        renderer_decisions: list[RendererProjectionDecision] = []
        for lifecycle_row in candidate_lifecycle:
            matching_sections = sections_by_source_id.get(
                lifecycle_row.discovered_candidate_id, []
            )
            if len(matching_sections) != 1:
                raise RuntimeError(
                    "FinalQEPlanRenderer requires exactly one projection for finalized "
                    f"candidate {lifecycle_row.discovered_candidate_id}; found "
                    f"{len(matching_sections)}"
                )
            section = matching_sections[0]
            renderer_decisions.append(
                RendererProjectionDecision(
                    discovered_candidate_id=lifecycle_row.discovered_candidate_id,
                    canonical_candidate_id=lifecycle_row.canonical_candidate_id,
                    final_disposition=lifecycle_row.final_disposition,
                    section_key=section.section_key,
                    source_record_ids=section.source_record_ids,
                    dedup_decision_id=lifecycle_row.dedup_decision_id,
                )
            )
        plan = StructuredQEPlan(
            jira_key=request.jira_key,
            contract_mode=facts.contract_mode,
            sections=sections,
            contract_fact_ids=[row.fact_id for row in facts.facts],
            closure_ids=[row.closure_id for row in closure],
            coverage_disposition_ids=[row.disposition_id for row in dispositions],
            behavior_classification_ids=[
                row.classification_id for row in behavior_classifications or []
            ],
            promoted_candidate_ids=promoted_ids,
            open_question_ids=sorted(
                open_question_ids
                | {
                    row.question_id
                    for row in questions
                    if row.question_id not in linked_question_ids
                }
            ),
            candidate_lifecycle=candidate_lifecycle,
            dedup_decisions=acceptance_resolution.dedup_decisions,
            renderer_decisions=renderer_decisions,
            gate_decisions=gates,
        )
        lines = [f"# {request.jira_key} — QE plan", ""]
        if any(
            gate.status in {GateStatus.BLOCKED, GateStatus.FAILED}
            for gate in gates
        ):
            # UX1: blocked is a first-class output state.  The structured plan
            # above keeps every intermediate artifact for trace/debug; the
            # human-facing markdown is a compact clarification document and
            # never mimics a successful plan (no coverage matrices, no gate
            # internals, no acceptance-looking content).
            understanding_items = [
                text.strip()
                for text, _record_id in section_items.get("issue_understanding", [])
                if text.strip()
            ]
            if understanding_items:
                lines.extend(["## Issue understanding", ""])
                lines.extend(
                    f"- {text}"
                    for text in dict.fromkeys(understanding_items)
                )
                lines.append("")
            lines.extend(["## Generation status", ""])
            reviewer_failures = [
                failure
                for gate in gates
                if gate.gate == CanonicalRuntimeStage.FINAL_QE_PLAN_RENDERER
                and gate.status == GateStatus.FAILED
                for failure in gate.failures
            ]
            if reviewer_failures:
                # The reviewer rejected the drafted UAC (meta/evidence prose
                # in the contract, or an implementation finding promoted to a
                # product decision): say so plainly, never mimic success.
                lines.append(
                    "- The drafted UAC failed review and was rejected."
                )
                for failure in reviewer_failures[:4]:
                    lines.append(f"- Review finding: {failure}")
                lines.append("")
            elif waiting_for_research:
                # A5 host mediation: required research is dispatched to the
                # host and unanswered - this is research in progress, never a
                # product-decision request and never a plan-shaped document.
                lines.append(
                    "- Required research is still in progress; no product "
                    "decision is being requested yet."
                )
                lines.append(
                    "- No Acceptance Criteria were generated because required "
                    "research has not returned."
                )
                lines.append("")
            else:
                lines.append("- UAC needs product clarification.")
                lines.append(
                    "- No Acceptance Criteria were generated because required "
                    "product decisions remain unresolved."
                )
                lines.append("")
            decision_texts: list[str] = []
            decision_entries: list[tuple[str, str]] = []
            for text, record_id in section_items.get("product_decisions", []):
                normalized = " ".join(text.split())
                if normalized and normalized.casefold() not in {
                    seen.casefold() for seen, _rid in decision_entries
                }:
                    decision_entries.append((normalized, record_id))
            decision_texts = [text for text, _rid in decision_entries]
            # While waiting for host research, product decisions are not yet
            # presented as user asks - research may resolve them.
            if decision_texts and not waiting_for_research:
                convergence_by_question = {
                    row.question_id: row for row in (convergence or [])
                }
                # Entries whose text IS the convergence decision already
                # carry the established/undecided lines inside them.
                decision_record_ids = {
                    row.question_id for row in (convergence or []) if row.decision
                }
                lines.extend(["## Open product decisions", ""])
                for normalized, record_id in decision_entries:
                    lines.append(f"- (TBD) {normalized}")
                    if record_id in decision_record_ids:
                        continue
                    # Conversational, evidence-bearing clarification: attach
                    # what research established and any conflict, so QE can
                    # answer in context instead of reading raw tickets.
                    conv = convergence_by_question.get(record_id)
                    for detail in _convergence_detail_lines(conv):
                        lines.append(f"  {detail}")
                lines.append("")
            lines.extend(["## Acceptance criteria", ""])
            lines.append(
                "- None generated until required research completes."
                if waiting_for_research
                else "- None generated until the blocking decisions are resolved."
            )
            lines.append("")
        else:
            for section in sections:
                # Bookkeeping lines announce that an internal record exists
                # without dispositioning anything, so they are not shown to
                # the tester.  The closure records remain in the structured
                # plan and the trace.
                visible_items = [
                    item
                    for item in section.items
                    if not _COVERAGE_FILLER_RE.search(item)
                ]
                if not visible_items:
                    continue
                lines.extend([f"## {section.title}", ""])
                if section.section_key == "acceptance_contract":
                    # Human-facing acceptance contract: a flat, individually
                    # referenceable criterion followed by the sources that
                    # actually support it.  Capped at ten points - a longer
                    # list is not readable as a sign-off contract, and the
                    # full set stays in the structured plan and the trace.
                    for index, item in enumerate(visible_items[:10], start=1):
                        source_line = acceptance_sources.get(
                            item.strip(), "QE-derived coverage."
                        )
                        # D1: sub-points render under the criterion they
                        # qualify, so a material (TBD) question stays inside
                        # the acceptance contract instead of moving to a
                        # sibling section.
                        outcome, _, sub_block = item.partition("\n")
                        lines.append(f"- AC-{index:02d}: {outcome}")
                        for sub_line in sub_block.splitlines():
                            if sub_line.strip():
                                lines.append(f"  {sub_line.strip()}")
                        lines.append(f"  **Source:** {source_line}")
                        lines.append("")
                    if len(visible_items) > 10:
                        lines.append(
                            f"- {len(visible_items) - 10} further criteria are "
                            "retained in the structured plan."
                        )
                else:
                    if section.section_key == "issue_understanding":
                        # The summary reads as prose, not as a bullet dump of
                        # the raw ticket sentences.
                        lines.extend(visible_items)
                        lines.append("")
                        continue
                    if section.section_key == "product_decisions":
                        # A decision carries its evidence as sub-points, so the
                        # reader sees what research established next to the
                        # decision it still has to make.
                        for item in visible_items:
                            head, _, sub_block = item.partition("\n")
                            lines.append(f"- {head}")
                            for sub_line in sub_block.splitlines():
                                if sub_line.strip():
                                    lines.append(f"  {sub_line.strip()}")
                        lines.append("")
                        continue
                    lines.extend(f"- {item}" for item in visible_items)
                lines.append("")
        rendered = "\n".join(lines).rstrip() + "\n"
        rendered_source_ids = {
            record_id for section in sections for record_id in section.source_record_ids
        }
        missing_disposition_ids = sorted(
            row.disposition_id
            for row in dispositions
            if row.disposition_id not in rendered_source_ids
            and row.disposition_id not in skipped_open_dispositions
        )
        if missing_disposition_ids:
            raise RuntimeError(
                "FinalQEPlanRenderer dropped terminal coverage dispositions: "
                + ", ".join(missing_disposition_ids)
            )
        missing_authoritative_fact_ids = [
            fact.fact_id
            for fact in facts.facts
            if fact.authoritative and fact.fact_id not in rendered_source_ids
        ]
        if missing_authoritative_fact_ids:
            raise RuntimeError(
                "FinalQEPlanRenderer dropped authoritative contract facts: "
                + ", ".join(missing_authoritative_fact_ids)
            )
        return plan, rendered


CANONICAL_REASONING_SERVICE = CanonicalTestPlanReasoningService()


__all__ = ["CANONICAL_REASONING_SERVICE", "CanonicalTestPlanReasoningService"]
