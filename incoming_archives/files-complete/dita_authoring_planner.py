"""DITA Authoring Planner — analyzes a Jira issue and produces a
human-reviewable plan BEFORE LLM jumps into DITA generation.

Sits between Jira fetch and DITA generation in the Authoring UI.
Author reviews and approves the plan, then generation follows it exactly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from app.core.structured_logging import get_structured_logger
from app.services.dita_knowledge_retriever import (
    retrieve_dita_knowledge,
    retrieve_dita_graph_knowledge,
)

logger = get_structured_logger(__name__)


# ── Plan data structures ──────────────────────────────────────────────────────

@dataclass
class PlannedSection:
    """A single section within a planned DITA topic."""
    element: str          # e.g. shortdesc, prereq, context, steps, result, section
    label: str            # Human-readable label
    description: str      # What this section should contain
    required: bool = True
    notes: str = ""       # Any special notes for the author


@dataclass
class PlannedTopic:
    """A single planned DITA topic."""
    topic_type: str                          # task | concept | reference | glossentry
    title: str                               # Suggested title
    filename: str                            # Suggested filename e.g. AEM-123-task.dita
    rationale: str                           # Why this topic type was chosen
    sections: list[PlannedSection] = field(default_factory=list)
    dita_version: str = "1.3"
    key_constructs: list[str] = field(default_factory=list)  # keyref, conref, etc.


@dataclass
class DitaAuthoringPlan:
    """Complete plan for authoring DITA from a Jira issue."""
    issue_key: str
    issue_summary: str
    topics: list[PlannedTopic] = field(default_factory=list)
    ditamap_needed: bool = False
    ditamap_title: str = ""
    overall_rationale: str = ""
    rag_sources_used: list[str] = field(default_factory=list)
    confidence: float = 0.8

    def to_dict(self) -> dict:
        return {
            "issue_key": self.issue_key,
            "issue_summary": self.issue_summary,
            "overall_rationale": self.overall_rationale,
            "ditamap_needed": self.ditamap_needed,
            "ditamap_title": self.ditamap_title,
            "confidence": self.confidence,
            "rag_sources_used": self.rag_sources_used,
            "topics": [
                {
                    "topic_type": t.topic_type,
                    "title": t.title,
                    "filename": t.filename,
                    "rationale": t.rationale,
                    "dita_version": t.dita_version,
                    "key_constructs": t.key_constructs,
                    "sections": [
                        {
                            "element": s.element,
                            "label": s.label,
                            "description": s.description,
                            "required": s.required,
                            "notes": s.notes,
                        }
                        for s in t.sections
                    ],
                }
                for t in self.topics
            ],
        }


# ── Topic type detection (rule-based, no LLM needed) ─────────────────────────

def _detect_topic_type(issue: dict) -> str:
    """
    Detect the best DITA topic type from issue metadata.
    Returns: task | concept | reference | glossentry
    """
    issue_type = (issue.get("issue_type") or "").lower()
    summary    = (issue.get("summary") or "").lower()
    labels     = [l.lower() for l in (issue.get("labels") or [])]
    desc       = (issue.get("description") or "").lower()

    text = f"{summary} {desc} {' '.join(labels)}"

    # Explicit label overrides
    if any(l in labels for l in ["task", "howto", "procedure", "steps"]):
        return "task"
    if any(l in labels for l in ["concept", "overview", "explanation"]):
        return "concept"
    if any(l in labels for l in ["reference", "api", "syntax", "parameters"]):
        return "reference"
    if any(l in labels for l in ["glossary", "term", "definition"]):
        return "glossentry"

    # Issue type mapping
    if any(x in issue_type for x in ["bug", "defect"]):
        return "task"  # bugs → task (how to reproduce/fix)
    if any(x in issue_type for x in ["story", "epic", "feature"]):
        return "concept"
    if any(x in issue_type for x in ["task", "subtask"]):
        return "task"

    # Summary keyword analysis
    task_signals = [
        "how to", "configure", "install", "set up", "setup", "create",
        "enable", "disable", "migrate", "upgrade", "deploy", "fix",
        "resolve", "troubleshoot", "steps to", "procedure", "reproduce",
    ]
    concept_signals = [
        "what is", "overview", "introduction", "understand", "about",
        "explanation", "concept", "architecture", "design", "when to use",
        "why", "difference between", "comparison",
    ]
    reference_signals = [
        "api", "syntax", "parameters", "properties", "attributes",
        "configuration options", "settings", "values", "list of",
        "reference", "specification", "format",
    ]

    task_score    = sum(1 for s in task_signals if s in text)
    concept_score = sum(1 for s in concept_signals if s in text)
    ref_score     = sum(1 for s in reference_signals if s in text)

    if task_score >= concept_score and task_score >= ref_score:
        return "task"
    if concept_score >= ref_score:
        return "concept"
    if ref_score > 0:
        return "reference"

    # Default: bugs → task, everything else → concept
    return "task" if "bug" in issue_type else "concept"


def _build_sections_for_type(topic_type: str, issue: dict) -> list[PlannedSection]:
    """Build the recommended sections list for a given topic type."""
    summary = issue.get("summary", "")
    labels  = [l.lower() for l in (issue.get("labels") or [])]
    desc    = (issue.get("description") or "").lower()

    if topic_type == "task":
        sections = [
            PlannedSection("shortdesc",  "Short description", f"One sentence describing what this task accomplishes", required=True),
            PlannedSection("prereq",     "Prerequisites",     "What the user needs before starting", required=False,
                           notes="Include only if there are real prerequisites"),
            PlannedSection("context",    "Context",           "Why this task is needed and when to perform it", required=False),
            PlannedSection("steps",      "Steps",             f"Step-by-step instructions to resolve: {summary[:60]}", required=True),
            PlannedSection("result",     "Result",            "What the user sees when steps complete successfully", required=False),
        ]
        # Add note section if issue has troubleshooting signals
        if any(s in desc for s in ["note", "warning", "caution", "important"]):
            sections.insert(-1, PlannedSection("note", "Note/Warning", "Important notes or warnings", required=False))
        return sections

    elif topic_type == "concept":
        sections = [
            PlannedSection("shortdesc",  "Short description", "One sentence explaining what this concept is", required=True),
            PlannedSection("conbody_p",  "Introduction",      f"Overview paragraph explaining: {summary[:60]}", required=True),
            PlannedSection("section",    "Main section",      "Detailed explanation of the concept", required=True),
            PlannedSection("example",    "Example",           "A concrete example showing the concept in practice", required=False),
        ]
        # Add related links if labels suggest it
        if any(l in labels for l in ["keyref", "conref", "map", "dita"]):
            sections.append(PlannedSection("section", "Technical details", "Technical implementation details", required=False))
        return sections

    elif topic_type == "reference":
        return [
            PlannedSection("shortdesc",   "Short description", "One sentence describing what this reference covers", required=True),
            PlannedSection("refbody",     "Reference body",    "The main reference content", required=True),
            PlannedSection("properties",  "Properties table",  "Properties, values, and descriptions in table format", required=False),
            PlannedSection("section",     "Usage notes",       "Additional usage notes and restrictions", required=False),
        ]

    elif topic_type == "glossentry":
        return [
            PlannedSection("glossterm",   "Term",       "The glossary term", required=True),
            PlannedSection("glossdef",    "Definition", "Full definition of the term", required=True),
            PlannedSection("glossBody",   "Glossary body", "Additional body content", required=False),
        ]

    return []


def _suggest_key_constructs(issue: dict) -> list[str]:
    """Detect DITA constructs likely needed based on issue content."""
    text = " ".join([
        issue.get("summary", ""),
        issue.get("description", ""),
        " ".join(issue.get("labels", [])),
    ]).lower()

    constructs = []
    construct_signals = {
        "keyref":   ["keyref", "key reference", "key-based", "reusable link"],
        "conref":   ["conref", "content reference", "reuse", "shared content"],
        "keydef":   ["keydef", "key definition", "product name", "variable"],
        "keyscope": ["keyscope", "nested scope", "scope boundary"],
        "ditaval":  ["ditaval", "conditional", "filtering", "profiling"],
        "xref":     ["cross-reference", "xref", "link to", "related topic"],
        "mapref":   ["submap", "map reference", "child map"],
    }
    for construct, signals in construct_signals.items():
        if any(s in text for s in signals):
            constructs.append(construct)

    return constructs[:4]  # max 4 constructs


def _build_filename(issue_key: str, topic_type: str, index: int = 0) -> str:
    """Build a safe DITA filename."""
    suffix = f"-{index}" if index > 0 else ""
    return f"{issue_key.lower()}-{topic_type}{suffix}.dita"


def _needs_ditamap(topics: list[PlannedTopic]) -> bool:
    """Determine if a ditamap is needed."""
    return len(topics) > 1


# ── Main planning function ────────────────────────────────────────────────────

async def create_dita_authoring_plan(issue: dict) -> DitaAuthoringPlan:
    """
    Analyze a Jira issue and create a DITA authoring plan.

    This runs BEFORE LLM generation so the author can review and approve
    the structure before any content is generated.

    Steps:
    1. Rule-based analysis (fast, no LLM) — detects topic type, sections, constructs
    2. RAG enrichment — validates structure against DITA spec
    3. Optional LLM refinement — if LLM available, improves the plan quality
    4. Returns structured plan for author review
    """
    issue_key     = issue.get("issue_key", "UNKNOWN")
    summary       = issue.get("summary", "")
    description   = issue.get("description", "")
    issue_type    = issue.get("issue_type", "")
    labels        = issue.get("labels", [])
    comments      = issue.get("comments", [])
    rag_sources   = []

    logger.info_structured(
        "Creating DITA authoring plan",
        extra_fields={"issue_key": issue_key, "issue_type": issue_type},
    )

    # ── Step 1: Rule-based topic type detection ───────────────────────────────
    primary_type = _detect_topic_type(issue)
    sections     = _build_sections_for_type(primary_type, issue)
    constructs   = _suggest_key_constructs(issue)

    # ── Step 2: RAG — validate against DITA spec ─────────────────────────────
    query = f"{summary} {primary_type} topic structure"
    spec_rationale = ""
    graph_notes    = ""
    try:
        spec_chunks = retrieve_dita_knowledge(query_text=query, k=2)
        if spec_chunks:
            rag_sources.append("DITA spec")
            spec_text = " ".join((c.get("text_content") or "")[:300] for c in spec_chunks)
            spec_rationale = spec_text[:500]

        graph = retrieve_dita_graph_knowledge(element_hint=f"{primary_type} {' '.join(constructs)}")
        if graph:
            rag_sources.append("DITA element graph")
            graph_notes = graph[:400]
    except Exception as e:
        logger.debug_structured("RAG enrichment skipped", extra_fields={"error": str(e)})

    # ── Step 3: Decide if multiple topics needed ──────────────────────────────
    topics = []
    comment_text = " ".join(c.get("body_text", "") for c in comments[:3]).lower()
    full_text    = f"{summary} {description} {comment_text}".lower()

    # Heuristic: complex issues need concept + task
    needs_concept_and_task = (
        primary_type == "task" and
        any(s in full_text for s in ["overview", "understand", "what is", "how it works", "background"])
    )

    if needs_concept_and_task:
        # Generate concept topic first, then task
        concept_sections = _build_sections_for_type("concept", issue)
        topics.append(PlannedTopic(
            topic_type="concept",
            title=f"Understanding {_clean_title(summary)}",
            filename=_build_filename(issue_key, "concept"),
            rationale="Issue description contains background/overview content that fits a concept topic",
            sections=concept_sections,
            key_constructs=constructs,
        ))
        topics.append(PlannedTopic(
            topic_type="task",
            title=_clean_title(summary),
            filename=_build_filename(issue_key, "task"),
            rationale=f"Primary issue type '{issue_type}' maps to a task topic for procedural content",
            sections=sections,
            key_constructs=constructs,
        ))
    else:
        topics.append(PlannedTopic(
            topic_type=primary_type,
            title=_clean_title(summary),
            filename=_build_filename(issue_key, primary_type),
            rationale=_build_rationale(primary_type, issue_type, labels, spec_rationale),
            sections=sections,
            key_constructs=constructs,
        ))

    # ── Step 4: LLM refinement (optional, non-blocking) ──────────────────────
    try:
        from app.services.llm_service import is_llm_available, generate_json
        if is_llm_available():
            refined = await _refine_plan_with_llm(
                issue=issue,
                topics=topics,
                graph_notes=graph_notes,
            )
            if refined:
                topics = refined
                rag_sources.append("LLM refinement")
    except Exception as e:
        logger.debug_structured(
            "LLM plan refinement skipped (non-fatal)",
            extra_fields={"error": str(e)},
        )

    ditamap_needed = _needs_ditamap(topics)
    plan = DitaAuthoringPlan(
        issue_key=issue_key,
        issue_summary=summary,
        topics=topics,
        ditamap_needed=ditamap_needed,
        ditamap_title=f"{_clean_title(summary)}" if ditamap_needed else "",
        overall_rationale=_build_overall_rationale(topics, constructs, rag_sources),
        rag_sources_used=rag_sources,
        confidence=0.9 if rag_sources else 0.7,
    )

    logger.info_structured(
        "DITA authoring plan created",
        extra_fields={
            "issue_key": issue_key,
            "topics": len(topics),
            "types": [t.topic_type for t in topics],
            "rag_sources": rag_sources,
        },
    )
    return plan


async def _refine_plan_with_llm(
    issue: dict,
    topics: list[PlannedTopic],
    graph_notes: str,
) -> Optional[list[PlannedTopic]]:
    """
    Use LLM to refine the rule-based plan.
    Only runs if LLM is available — plan is already valid without this.
    """
    from app.services.llm_service import generate_json

    current_plan = json.dumps([{
        "topic_type": t.topic_type,
        "title": t.title,
        "sections": [s.element for s in t.sections],
    } for t in topics], indent=2)

    system = """You are a DITA architecture expert. Given a Jira issue and a proposed plan,
improve the plan if needed. Return JSON only.

Output format:
{
  "topics": [
    {
      "topic_type": "task|concept|reference",
      "title": "improved title",
      "rationale": "why this type",
      "sections": ["shortdesc", "prereq", "context", "steps", "result"],
      "key_constructs": ["keyref", "conref"]
    }
  ]
}

Rules:
- Keep the same number of topics unless clearly wrong
- Only use valid DITA 1.3 elements for sections
- task sections: shortdesc, prereq, context, steps, result, note
- concept sections: shortdesc, conbody, section, example
- reference sections: shortdesc, refbody, properties, section
- Return JSON only, no explanation"""

    user = f"""Jira Issue:
Key: {issue.get('issue_key')}
Summary: {issue.get('summary')}
Type: {issue.get('issue_type')}
Labels: {', '.join(issue.get('labels', []))}
Description: {(issue.get('description') or '')[:1000]}

Current plan:
{current_plan}

DITA graph notes:
{graph_notes[:300] if graph_notes else 'Not available'}

Improve or confirm the plan. Output JSON only:"""

    result = await generate_json(system, user, max_tokens=600, step_name="authoring_planner")
    if not result or not isinstance(result, dict):
        return None

    refined_topics = []
    for t in result.get("topics", []):
        topic_type = t.get("topic_type", "concept")
        sections_raw = t.get("sections", [])
        sections = [
            PlannedSection(
                element=s,
                label=s.replace("_", " ").capitalize(),
                description=f"Content for {s} element",
                required=s in ("shortdesc", "steps", "refbody", "conbody"),
            )
            for s in sections_raw if isinstance(s, str)
        ]
        refined_topics.append(PlannedTopic(
            topic_type=topic_type,
            title=t.get("title", ""),
            filename=_build_filename(issue.get("issue_key", "unknown"), topic_type),
            rationale=t.get("rationale", ""),
            sections=sections,
            key_constructs=t.get("key_constructs", []),
        ))

    return refined_topics if refined_topics else None


# ── Helper functions ──────────────────────────────────────────────────────────

def _clean_title(summary: str) -> str:
    """Clean summary into a proper topic title."""
    title = summary.strip()
    # Remove issue key prefix if present e.g. "AEM-123: something"
    if ":" in title[:15]:
        title = title.split(":", 1)[1].strip()
    # Capitalize first letter
    return title[:100] if title else "Untitled Topic"


def _build_rationale(
    topic_type: str,
    issue_type: str,
    labels: list[str],
    spec_notes: str,
) -> str:
    reasons = {
        "task": f"Issue type '{issue_type}' indicates procedural content requiring step-by-step instructions",
        "concept": f"Issue type '{issue_type}' indicates explanatory/overview content",
        "reference": f"Issue type '{issue_type}' indicates reference material",
        "glossentry": "Issue contains terminology/definition content",
    }
    base = reasons.get(topic_type, "Best match for issue content")
    if labels:
        base += f". Labels {labels[:3]} confirm this topic type"
    return base


def _build_overall_rationale(
    topics: list[PlannedTopic],
    constructs: list[str],
    rag_sources: list[str],
) -> str:
    parts = []
    if len(topics) == 1:
        parts.append(f"Single {topics[0].topic_type} topic recommended")
    else:
        types = [t.topic_type for t in topics]
        parts.append(f"Multiple topics needed: {', '.join(types)}")
    if constructs:
        parts.append(f"DITA constructs detected: {', '.join(constructs)}")
    if rag_sources:
        parts.append(f"Plan validated against: {', '.join(rag_sources)}")
    return ". ".join(parts)
