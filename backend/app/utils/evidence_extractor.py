"""Extract Jira evidence for retrieval and planning - prioritizes summary and Representative Sample."""
import os
import re
from typing import Optional

# Terms that trigger AEM Guides doc retrieval (avoid retrieval when evidence is generic)
AEM_GUIDES_TRIGGER_TERMS = (
    "keyref", "keydef", "keyscope", "ditamap", "ditaval", "conref", "dita",
    "web editor", "aem guides", "experience manager guides", "dita-ot",
    "topicref", "map hierarchy", "nested key",
    "table", "simpletable", "cals", "image", "media",
    "experience league", "scraped content", "glossary", "glossentry",
    "conrefend", "duplicate id", "cyclic",
)
USE_AEM_DOCS_ENRICHMENT = os.getenv("USE_AEM_DOCS_ENRICHMENT", "true").lower() in ("true", "1", "yes")


def pre_extract_representative_xml(primary: dict, max_items: int = 6, max_chars_per_item: int = 8000) -> list[str]:
    """
    Pre-extract Representative Sample XML from Jira description and attachments.
    Representative Sample snippets are often attached as .dita, .xml, .txt, .snippet,
    or inside ZIPs—not only in the description. Use this before calling the LLM
    to avoid hallucination. Returns list of XML snippets.
    """
    if not primary:
        return []
    snippets: list[str] = []
    seen: set[str] = set()

    def _add_snippet(s: str) -> bool:
        if not s or not _looks_like_dita(s):
            return False
        norm = s.strip()[:500]
        if norm in seen:
            return False
        seen.add(norm)
        snippets.append(s[:max_chars_per_item])
        return len(snippets) >= max_items

    description = (primary.get("description") or "").strip()
    if description:
        rep_match = re.search(
            r"Representative Sample\s*\n(.+?)(?=Support Investigation|Business Impact|Related|Requested|Attachments|$)",
            description,
            re.DOTALL | re.IGNORECASE,
        )
        if rep_match:
            sample = rep_match.group(1).strip()
            parts = re.split(r"(?=<(?:map|topic|keydef|topicref)[\s>])", sample, flags=re.IGNORECASE)
            for p in parts:
                if _add_snippet(p.strip()):
                    return snippets[:max_items]
        if not snippets and ("<!-- Map" in description or "<keydef" in description or "<map>" in description):
            idx = max(
                description.find("<!-- Map"),
                description.find("<keydef"),
                description.find("<map>"),
                0,
            )
            if idx >= 0:
                block = description[idx : idx + max_chars_per_item * 2]
                if _add_snippet(block):
                    return snippets[:max_items]

    for att in primary.get("attachments") or []:
        if len(snippets) >= max_items:
            break
        content = att.get("full_content") or att.get("excerpt") or ""
        if not content or not _looks_like_dita(content):
            continue
        parts = re.split(r"(?=<(?:map|topic|keydef|topicref)[\s>])", content, flags=re.IGNORECASE)
        for p in parts:
            if _add_snippet(p.strip()):
                return snippets[:max_items]

    return snippets[:max_items]


def _looks_like_dita(text: str) -> bool:
    """Check if text contains DITA-like tags."""
    t = text.lower()
    return any(
        tag in t
        for tag in ("<map", "<topic", "<keydef", "<topicref", "<keyref", "<section", "<body", "<p ")
    )


def extract_evidence_context(primary: dict, max_chars: int = 6000) -> str:
    """
    Build evidence context from Jira primary issue for recipe retrieval and planning.
    Prioritizes: summary, Issue Summary, Representative Sample (XML/code), Steps to Reproduce.
    Includes attachment content (DITA/XML) when Representative Sample is in attachments.
    """
    if not primary:
        return ""
    summary = (primary.get("summary") or "").strip()
    description = (primary.get("description") or "").strip()
    parts = [summary]

    if description:
        issue_summary_match = re.search(
            r"Issue Summary\s*\n(.+?)(?=Steps to Reproduce|Actual Behavior|Expected Behavior|Representative Sample|Support Investigation|Business Impact|Related|$)",
            description,
            re.DOTALL | re.IGNORECASE,
        )
        if issue_summary_match:
            parts.append(issue_summary_match.group(1).strip()[:1000])

        rep_match = re.search(
            r"Representative Sample\s*\n(.+?)(?=Support Investigation|Business Impact|Related|Requested|Attachments|$)",
            description,
            re.DOTALL | re.IGNORECASE,
        )
        if rep_match:
            sample = rep_match.group(1).strip()
            parts.append("Representative Sample: " + sample[:2500])
        elif "<!-- Map" in description or "<keydef" in description or "<map>" in description:
            idx = max(
                description.find("<!-- Map"),
                description.find("<keydef"),
                description.find("<map>"),
                0,
            )
            if idx >= 0:
                parts.append(description[idx : idx + 2500])

    for att in primary.get("attachments") or []:
        content = att.get("full_content") or att.get("excerpt") or ""
        if content and _looks_like_dita(content):
            parts.append(f"Attachment {att.get('filename', '')}: " + content[:2500])

    for c in primary.get("comments") or []:
        body = c.get("body_text", "") if isinstance(c, dict) else ""
        if body and _looks_like_dita(body):
            parts.append("Comment: " + body[:1500])

    combined = " ".join(p for p in parts if p)
    if len(combined) < 600 and description:
        combined = f"{summary} {description[:max_chars]}".strip()

    base_context = combined[:max_chars].strip()
    return enrich_evidence_with_docs(primary, base_context, max_chars=max_chars)


def enrich_evidence_with_docs(
    primary: dict,
    evidence_context: str,
    k: int = 3,
    max_chars: int = 6000,
) -> str:
    """
    When evidence mentions AEM Guides–related terms, retrieve relevant doc chunks
    and append to context. Set USE_AEM_DOCS_ENRICHMENT=false to disable.
    """
    if not USE_AEM_DOCS_ENRICHMENT or not evidence_context:
        return evidence_context
    text_lower = evidence_context.lower()
    if not any(term in text_lower for term in AEM_GUIDES_TRIGGER_TERMS):
        return evidence_context
    try:
        from app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
        docs = retrieve_relevant_docs(evidence_context, k=k, max_snippet_chars=1500)
        if not docs:
            return evidence_context
        formatted = format_docs_for_prompt(docs)
        if not formatted:
            return evidence_context
        extra = f"\n\nRelevant AEM Guides docs:\n{formatted}"
        return (evidence_context + extra)[:max_chars].strip()
    except Exception:
        return evidence_context
