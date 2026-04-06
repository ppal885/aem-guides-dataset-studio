"""Smart Shortdesc Generator service - generate DITA-compliant shortdesc elements
using information-typing rules and optional LLM enhancement."""

import json
import re
import xml.etree.ElementTree as ET
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# DITA topic root elements
TOPIC_ROOTS = {"topic", "concept", "task", "reference", "glossentry", "glossary"}

# Body element names per topic type
BODY_TAGS = {
    "task": "taskbody",
    "concept": "conbody",
    "reference": "refbody",
    "glossentry": "glossBody",
    "topic": "body",
}

MAX_SHORTDESC_WORDS = 50


# ---------------------------------------------------------------------------
# XML helpers (mirrors dita_enrichment_service patterns)
# ---------------------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    """Strip XML namespace from tag."""
    return tag.split("}")[-1] if "}" in tag else tag


def _get_title_text(root: ET.Element) -> str:
    """Extract title text from topic root."""
    for child in root:
        if _strip_ns(child.tag) == "title":
            return (child.text or "") + "".join(
                ET.tostring(c, encoding="unicode", method="text") for c in child
            )
    return ""


def _get_body_text(root: ET.Element, root_tag: str, max_len: int = 500) -> str:
    """Extract body text up to *max_len* characters."""
    body_tag = BODY_TAGS.get(root_tag, "body")
    body_el = None
    for child in root:
        if _strip_ns(child.tag) == body_tag:
            body_el = child
            break
    if body_el is None:
        # Fallback: try any element ending with "body"
        for child in root:
            if _strip_ns(child.tag).endswith("body"):
                body_el = child
                break
    if body_el is None:
        return ""
    raw = (body_el.text or "") + "".join(
        ET.tostring(c, encoding="unicode", method="text") for c in body_el
    )
    text = re.sub(r"\s+", " ", raw).strip()
    return text[:max_len]


def _has_shortdesc(root: ET.Element) -> bool:
    """Return True if the topic already contains a non-empty shortdesc."""
    for child in root:
        if _strip_ns(child.tag) == "shortdesc":
            text = (child.text or "") + "".join(
                ET.tostring(c, encoding="unicode", method="text") for c in child
            )
            if text.strip():
                return True
    return False


def _get_existing_shortdesc(root: ET.Element) -> Optional[str]:
    """Return existing shortdesc text or None."""
    for child in root:
        if _strip_ns(child.tag) == "shortdesc":
            text = (child.text or "") + "".join(
                ET.tostring(c, encoding="unicode", method="text") for c in child
            )
            text = text.strip()
            if text:
                return text
    return None


def _get_glossdef_text(root: ET.Element) -> Optional[str]:
    """For glossentry, extract glossdef text."""
    for child in root:
        if _strip_ns(child.tag) == "glossBody":
            for gc in child:
                if _strip_ns(gc.tag) == "glossdef":
                    text = (gc.text or "") + "".join(
                        ET.tostring(c, encoding="unicode", method="text") for c in gc
                    )
                    return re.sub(r"\s+", " ", text).strip()
    # Also check direct children (some glossentry structures)
    for child in root:
        if _strip_ns(child.tag) == "glossdef":
            text = (child.text or "") + "".join(
                ET.tostring(c, encoding="unicode", method="text") for c in child
            )
            return re.sub(r"\s+", " ", text).strip()
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_shortdesc(text: str) -> str:
    """Ensure shortdesc meets DITA constraints: max 50 words, no block elements,
    single sentence preferred. Returns cleaned text."""
    text = re.sub(r"\s+", " ", text).strip()
    # Remove any accidental XML/HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Truncate to 50 words
    words = text.split()
    if len(words) > MAX_SHORTDESC_WORDS:
        text = " ".join(words[:MAX_SHORTDESC_WORDS])
        # End with a period if truncated
        if not text.endswith("."):
            text = text.rstrip(",;:") + "."
    # Ensure it ends with punctuation
    if text and text[-1] not in ".!?":
        text += "."
    return text


# ---------------------------------------------------------------------------
# Rule-based fallback generation
# ---------------------------------------------------------------------------

_RULE_PREFIXES = {
    "task": [
        "Describes how to {title}.",
        "Learn how to {title_lower}.",
        "Steps to {title_lower}.",
    ],
    "concept": [
        "Explains {title_lower}.",
        "An overview of {title_lower}.",
        "Provides conceptual information about {title_lower}.",
    ],
    "reference": [
        "Lists {title_lower} details.",
        "Provides reference information for {title_lower}.",
        "Reference for {title_lower}.",
    ],
    "glossentry": [],  # handled via glossdef
    "topic": [
        "Describes {title_lower}.",
        "Information about {title_lower}.",
        "An overview of {title_lower}.",
    ],
}


def _first_sentence(text: str) -> str:
    """Extract first sentence from body text."""
    if not text:
        return ""
    # Split on sentence-ending punctuation followed by space or end
    m = re.match(r"(.+?[.!?])(?:\s|$)", text)
    if m:
        return m.group(1).strip()
    # No sentence boundary found; use first 50 words
    words = text.split()[:MAX_SHORTDESC_WORDS]
    return " ".join(words) + ("." if words else "")


def _rule_based_generate(topic_type: str, title: str, body_text: str) -> tuple[str, list[str]]:
    """Generate shortdesc and alternatives using rule-based templates.
    Returns (primary, alternatives)."""
    title_lower = title[0].lower() + title[1:] if title else "this topic"
    # Strip trailing period from title for template insertion
    title_clean = title.rstrip(".")
    title_lower_clean = title_lower.rstrip(".")

    if topic_type == "glossentry":
        # glossdef is the shortdesc; fallback to first sentence
        desc = _first_sentence(body_text) if body_text else f"Definition of {title_clean}."
        return _validate_shortdesc(desc), []

    templates = _RULE_PREFIXES.get(topic_type, _RULE_PREFIXES["topic"])
    results = []
    for t in templates:
        rendered = t.format(title=title_clean, title_lower=title_lower_clean)
        results.append(_validate_shortdesc(rendered))

    # If body text available, add a first-sentence variant
    if body_text:
        fs = _first_sentence(body_text)
        if fs:
            results.append(_validate_shortdesc(fs))

    primary = results[0] if results else f"Describes {title_lower_clean}."
    alternatives = results[1:] if len(results) > 1 else []
    return primary, alternatives


# ---------------------------------------------------------------------------
# LLM-powered generation
# ---------------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = """You are a DITA XML technical writing expert. Generate a concise shortdesc element for a DITA topic.

Rules:
- Maximum 50 words, ideally under 30 words
- Single sentence preferred
- No block-level elements (no <p>, <ul>, <ol>, <table>)
- Must be plain text suitable for a <shortdesc> element

Information typing guidelines:
- Task topics: outcome-focused, use "Describes how to..." or start with an action verb
- Concept topics: definition-focused, use "Explains..." or "An overview of..."
- Reference topics: scope-focused, use "Lists..." or "Provides reference for..."
- Glossentry topics: provide a concise definition

Respond with valid JSON only:
{
  "shortdesc": "The primary shortdesc text.",
  "alternatives": ["Alternative 1.", "Alternative 2."]
}"""


async def _llm_generate(topic_type: str, title: str, body_text: str) -> Optional[tuple[str, list[str]]]:
    """Try LLM generation. Returns (primary, alternatives) or None on failure."""
    try:
        from app.services.llm_service import generate_text
    except ImportError:
        return None

    user_prompt = (
        f"Topic type: {topic_type}\n"
        f"Title: {title}\n"
        f"Body (first 500 chars): {body_text[:500]}\n\n"
        "Generate a shortdesc and 2 alternatives."
    )

    try:
        raw = await generate_text(
            system_prompt=_LLM_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=300,
            step_name="shortdesc_generator",
        )
        # Parse JSON from LLM response
        # Strip markdown code fences if present
        cleaned = re.sub(r"```json\s*", "", raw)
        cleaned = re.sub(r"```\s*", "", cleaned)
        data = json.loads(cleaned.strip())
        primary = _validate_shortdesc(data.get("shortdesc", ""))
        alts = [_validate_shortdesc(a) for a in data.get("alternatives", []) if a]
        if primary:
            return primary, alts
    except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        logger.warning_structured(
            "LLM shortdesc generation failed, falling back to rules",
            extra_fields={"error": str(exc)},
        )
    except Exception as exc:
        logger.warning_structured(
            "LLM shortdesc generation error",
            extra_fields={"error": str(exc)},
        )
    return None


# ---------------------------------------------------------------------------
# XML snippet builder
# ---------------------------------------------------------------------------

def _build_xml_snippet(root_tag: str, title: str, shortdesc_text: str) -> str:
    """Build an XML snippet showing correct shortdesc placement."""
    body_tag = BODY_TAGS.get(root_tag, "body")
    topic_id = re.sub(r"[^a-zA-Z0-9_]", "_", title.lower())[:40] if title else "topic_1"
    return (
        f'<{root_tag} id="{topic_id}">\n'
        f"  <title>{title}</title>\n"
        f"  <shortdesc>{shortdesc_text}</shortdesc>\n"
        f"  <{body_tag}>\n"
        f"    <!-- body content -->\n"
        f"  </{body_tag}>\n"
        f"</{root_tag}>"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _parse_dita_xml(xml_string: str) -> ET.Element:
    """Parse DITA XML string, stripping DOCTYPE declarations that
    xml.etree cannot handle."""
    # Remove DOCTYPE line(s) so ET can parse
    cleaned = re.sub(r"<!DOCTYPE[^>]*>", "", xml_string)
    return ET.fromstring(cleaned)


async def generate_shortdesc(
    xml_string: str,
    use_llm: bool = True,
) -> dict:
    """Generate a DITA-compliant shortdesc for the provided topic XML.

    Returns:
        {
            "shortdesc": str,
            "topic_type": str,
            "has_existing": bool,
            "alternatives": list[str],
            "xml_snippet": str,
        }
    """
    # --- Parse XML ---
    try:
        root = _parse_dita_xml(xml_string)
    except ET.ParseError as exc:
        logger.warning_structured(
            "Malformed DITA XML in shortdesc generator",
            extra_fields={"error": str(exc)},
        )
        return {
            "shortdesc": "",
            "topic_type": "unknown",
            "has_existing": False,
            "alternatives": [],
            "xml_snippet": "",
            "error": f"Malformed XML: {exc}",
        }

    root_tag = _strip_ns(root.tag)
    if root_tag not in TOPIC_ROOTS:
        root_tag = "topic"  # treat unknown root as generic topic

    title = _get_title_text(root).strip()
    body_text = _get_body_text(root, root_tag)
    has_existing = _has_shortdesc(root)
    existing_text = _get_existing_shortdesc(root)

    # --- For glossentry, prefer glossdef ---
    if root_tag == "glossentry":
        glossdef = _get_glossdef_text(root)
        if glossdef:
            body_text = glossdef

    # --- Generate shortdesc ---
    primary: Optional[str] = None
    alternatives: list[str] = []

    if use_llm:
        llm_result = await _llm_generate(root_tag, title, body_text)
        if llm_result:
            primary, alternatives = llm_result

    # Fallback to rule-based
    if not primary:
        primary, alternatives = _rule_based_generate(root_tag, title, body_text)

    # Ensure we have 2-3 alternatives
    if len(alternatives) < 2:
        _, extra_alts = _rule_based_generate(root_tag, title, body_text)
        for alt in extra_alts:
            if alt != primary and alt not in alternatives:
                alternatives.append(alt)
            if len(alternatives) >= 3:
                break

    # Cap alternatives at 3
    alternatives = alternatives[:3]

    # Build XML snippet
    snippet = _build_xml_snippet(root_tag, title, primary)

    result = {
        "shortdesc": primary,
        "topic_type": root_tag,
        "has_existing": has_existing,
        "alternatives": alternatives,
        "xml_snippet": snippet,
    }

    if has_existing and existing_text:
        result["existing_shortdesc"] = existing_text

    logger.info_structured(
        "Shortdesc generated",
        extra_fields={
            "topic_type": root_tag,
            "has_existing": has_existing,
            "used_llm": use_llm and primary is not None,
            "title": title[:60],
        },
    )

    return result
