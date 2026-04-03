"""
Query Planner — generates targeted research queries from a Jira issue
BEFORE the authoring agent starts writing DITA.

This is the "thinking" step:
1. Reads the Jira issue
2. Generates 5 categories of queries
3. Author reviews + edits queries
4. Approved queries are executed against RAG + Tavily
5. Results injected into DITA generation context

Place at: backend/app/services/query_planner.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


# ── Query data structures ─────────────────────────────────────────────────────

@dataclass
class ResearchQuery:
    """A single research query with its category and purpose."""
    id: str
    category: str        # dita_elements | aem_guides | bugs_fixes | expert_examples | dita_spec
    query: str           # The actual search query
    purpose: str         # Why this query is needed
    source: str          # rag | tavily | both
    approved: bool = True

    def to_dict(self) -> dict:
        return {
            "id":       self.id,
            "category": self.category,
            "query":    self.query,
            "purpose":  self.purpose,
            "source":   self.source,
            "approved": self.approved,
        }


@dataclass
class QueryPlan:
    """Complete set of research queries for an issue."""
    issue_key:    str
    issue_summary: str
    queries:      list[ResearchQuery] = field(default_factory=list)
    reasoning:    str = ""           # Why these queries were chosen

    def to_dict(self) -> dict:
        return {
            "issue_key":     self.issue_key,
            "issue_summary": self.issue_summary,
            "reasoning":     self.reasoning,
            "queries":       [q.to_dict() for q in self.queries],
        }

    def approved_queries(self) -> list[ResearchQuery]:
        return [q for q in self.queries if q.approved]


# ── Category metadata ─────────────────────────────────────────────────────────

QUERY_CATEGORIES = {
    "dita_elements": {
        "label":       "DITA Elements",
        "description": "What DITA elements and structure are needed",
        "color":       "blue",
        "icon":        "code",
        "source":      "rag",
    },
    "aem_guides": {
        "label":       "AEM Guides",
        "description": "What AEM Guides says about this feature",
        "color":       "purple",
        "icon":        "book",
        "source":      "tavily",
    },
    "bugs_fixes": {
        "label":       "Known Bugs & Fixes",
        "description": "Known issues and solutions for this topic",
        "color":       "red",
        "icon":        "bug",
        "source":      "tavily",
    },
    "expert_examples": {
        "label":       "Expert Examples",
        "description": "Real DITA examples of this pattern",
        "color":       "green",
        "icon":        "star",
        "source":      "rag",
    },
    "dita_spec": {
        "label":       "DITA Spec Rules",
        "description": "Spec rules and constraints that apply",
        "color":       "amber",
        "icon":        "shield",
        "source":      "rag",
    },
}


# ── Rule-based query generation (no LLM, fast) ───────────────────────────────

def _extract_key_terms(issue: dict) -> list[str]:
    """Extract key technical terms from the issue."""
    summary = (issue.get("summary") or "").lower()
    desc    = (issue.get("description") or "").lower()
    labels  = [l.lower() for l in (issue.get("labels") or [])]
    text    = f"{summary} {desc}"

    DITA_TERMS = [
        "keyref", "conref", "keyscope", "ditaval", "xref", "mapref",
        "codeblock", "fig", "note", "task", "concept", "reference",
        "shortdesc", "prolog", "metadata", "topicref", "bookmap",
    ]
    AEM_TERMS = [
        "aem guides", "oxygen", "publishing", "baseline", "translation",
        "conditional", "profiling", "ditamap", "output preset", "uuid",
    ]

    found = []
    for term in DITA_TERMS + AEM_TERMS:
        if term in text or term in " ".join(labels):
            found.append(term)

    return found[:6]


def _build_rule_based_queries(issue: dict) -> list[ResearchQuery]:
    """Build queries using rules — fast, no LLM needed as base."""
    summary    = issue.get("summary", "")
    desc       = issue.get("description", "")[:300]
    issue_type = (issue.get("issue_type") or "").lower()
    labels     = issue.get("labels", [])
    issue_key  = issue.get("issue_key", "")

    key_terms  = _extract_key_terms(issue)
    terms_str  = " ".join(key_terms[:3]) if key_terms else summary[:50]

    queries = []

    # 1. DITA Elements query
    dita_type = _guess_dita_type(issue_type, labels, summary)
    queries.append(ResearchQuery(
        id       = "q_dita_elements",
        category = "dita_elements",
        query    = f"DITA 1.3 {dita_type} topic required elements {terms_str}",
        purpose  = f"Find required elements and valid structure for a {dita_type} topic",
        source   = "rag",
    ))

    # 2. AEM Guides query
    queries.append(ResearchQuery(
        id       = "q_aem_guides",
        category = "aem_guides",
        query    = f"AEM Guides {summary[:60]}",
        purpose  = f"Find what Adobe Experience League says about: {summary[:50]}",
        source   = "tavily",
    ))

    # 3. Bugs and fixes query
    fix_query = f"AEM Guides {terms_str} issue fix solution"
    if "bug" in issue_type or "defect" in issue_type:
        fix_query = f"AEM Guides {terms_str} bug fix workaround"
    queries.append(ResearchQuery(
        id       = "q_bugs_fixes",
        category = "bugs_fixes",
        query    = fix_query,
        purpose  = "Find known solutions, workarounds, and related bug reports",
        source   = "tavily",
    ))

    # 4. Expert examples query
    queries.append(ResearchQuery(
        id       = "q_expert_examples",
        category = "expert_examples",
        query    = f"DITA example {dita_type} {terms_str}",
        purpose  = f"Find validated DITA examples using {terms_str} patterns",
        source   = "rag",
    ))

    # 5. DITA spec rules query
    spec_query = f"DITA 1.3 specification {terms_str} rules constraints"
    if key_terms:
        spec_query = f"DITA 1.3 {key_terms[0]} element specification rules"
    queries.append(ResearchQuery(
        id       = "q_dita_spec",
        category = "dita_spec",
        query    = spec_query,
        purpose  = f"Find OASIS DITA spec rules for: {', '.join(key_terms[:2]) or terms_str}",
        source   = "rag",
    ))

    return queries


def _guess_dita_type(issue_type: str, labels: list, summary: str) -> str:
    """Quick guess at DITA topic type for query building."""
    text = f"{summary} {' '.join(labels)}".lower()
    if any(l.lower() in ("concept", "overview") for l in labels): return "concept"
    if any(l.lower() in ("reference", "api")    for l in labels): return "reference"
    if any(x in issue_type for x in ("bug", "task")):             return "task"
    if any(x in text for x in ("overview", "understand", "what")): return "concept"
    return "task"


# ── LLM-enhanced query generation ────────────────────────────────────────────

async def _enhance_queries_with_llm(
    issue: dict,
    base_queries: list[ResearchQuery],
) -> Optional[list[ResearchQuery]]:
    """
    Use LLM to improve the rule-based queries.
    Makes queries more specific and targeted to the actual issue content.
    """
    try:
        from app.services.llm_service import generate_json, is_llm_available
        if not is_llm_available():
            return None

        current = json.dumps([{
            "id":       q.id,
            "category": q.category,
            "query":    q.query,
            "purpose":  q.purpose,
        } for q in base_queries], indent=2)

        system = """You are a DITA technical documentation expert.
Improve these research queries to be more specific and useful for writing DITA content.
Make each query highly targeted to find exactly what's needed.

Output JSON only:
{
  "queries": [
    {
      "id": "q_dita_elements",
      "category": "dita_elements",
      "query": "improved specific query",
      "purpose": "what this will help us write"
    }
  ],
  "reasoning": "why you chose these queries"
}

Rules:
- Keep all 5 categories: dita_elements, aem_guides, bugs_fixes, expert_examples, dita_spec
- Make queries specific to the actual issue content
- queries should be 6-12 words
- Output JSON only"""

        user = f"""Jira Issue:
Key:         {issue.get('issue_key')}
Summary:     {issue.get('summary')}
Type:        {issue.get('issue_type')}
Labels:      {', '.join(issue.get('labels', []))}
Description: {(issue.get('description') or '')[:600]}

Current queries to improve:
{current}

Output improved queries as JSON:"""

        result = await generate_json(
            system, user,
            max_tokens=500,
            step_name="query_planner",
        )

        if not result or not isinstance(result, dict):
            return None

        enhanced = []
        for q_data in result.get("queries", []):
            qid      = q_data.get("id", "")
            category = q_data.get("category", "")
            query    = q_data.get("query", "")
            purpose  = q_data.get("purpose", "")

            if not query or category not in QUERY_CATEGORIES:
                continue

            # Find matching base query to preserve source
            base  = next((b for b in base_queries if b.id == qid), None)
            source = base.source if base else QUERY_CATEGORIES.get(category, {}).get("source", "rag")

            enhanced.append(ResearchQuery(
                id       = qid or f"q_{category}",
                category = category,
                query    = query,
                purpose  = purpose,
                source   = source,
            ))

        reasoning = result.get("reasoning", "")

        return enhanced if len(enhanced) >= 4 else None, reasoning

    except Exception as e:
        logger.debug_structured(
            "LLM query enhancement failed",
            extra_fields={"error": str(e)},
        )
        return None


# ── Main function ─────────────────────────────────────────────────────────────

async def generate_query_plan(issue: dict) -> QueryPlan:
    """
    Generate a research query plan for a Jira issue.

    Steps:
    1. Rule-based query generation (fast baseline)
    2. LLM enhancement (if available — makes queries more specific)
    3. Return QueryPlan for author review

    Author then reviews, edits, and approves queries
    before research is executed.
    """
    issue_key = issue.get("issue_key", "UNKNOWN")
    summary   = issue.get("summary", "")

    logger.info_structured(
        "Generating query plan",
        extra_fields={"issue_key": issue_key},
    )

    # Step 1: Rule-based (always works, fast)
    base_queries = _build_rule_based_queries(issue)
    reasoning    = "Rule-based query generation from issue type and labels"

    # Step 2: LLM enhancement (non-blocking)
    try:
        result = await _enhance_queries_with_llm(issue, base_queries)
        if result:
            if isinstance(result, tuple):
                enhanced, llm_reasoning = result
            else:
                enhanced, llm_reasoning = result, ""

            if enhanced and len(enhanced) >= 4:
                base_queries = enhanced
                reasoning    = llm_reasoning or "LLM-enhanced queries based on issue content"
    except Exception as e:
        logger.debug_structured(
            "LLM enhancement skipped",
            extra_fields={"error": str(e)},
        )

    plan = QueryPlan(
        issue_key     = issue_key,
        issue_summary = summary,
        queries       = base_queries,
        reasoning     = reasoning,
    )

    logger.info_structured(
        "Query plan generated",
        extra_fields={
            "issue_key": issue_key,
            "queries":   len(base_queries),
        },
    )
    return plan
