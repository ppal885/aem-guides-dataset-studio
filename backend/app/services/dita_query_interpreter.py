"""Interpret DITA spec questions into structured query modes."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.dita_attribute_catalog import list_attribute_names
from app.services.dita_spec_registry_service import list_element_names

_ATTRIBUTE_STOPWORDS = frozenset({"attribute", "dita", "xml", "topic", "map", "tag", "tags"})
_ATTRIBUTE_ALIASES = {
    "chunking": "chunk",
    "chunked": "chunk",
}
_CONTEXTUAL_ATTRIBUTE_NAMES = frozenset(
    {
        "audience",
        "platform",
        "product",
        "props",
        "otherprops",
        "rev",
        "deliverytarget",
        "outputclass",
        "importance",
        "scale",
        "width",
        "height",
    }
)
_CONTEXTUAL_ELEMENT_NAMES = frozenset({"i", "b", "u", "data"})
_TOKEN_PATTERN = re.compile(r"@?[A-Za-z_:][A-Za-z0-9_.:-]*")
_ATTRIBUTE_PATTERN = re.compile(
    r"@([A-Za-z_:][A-Za-z0-9_.:-]*)|"
    r"\battribute\s+`?@?([A-Za-z_:][A-Za-z0-9_.:-]*)`?\b|"
    r"\b`?@?([A-Za-z_:][A-Za-z0-9_.:-]*)`?\s+attribute\b",
    re.IGNORECASE,
)
_CONTENT_MODEL_PATTERN = re.compile(
    r"\b("
    r"what\s+can\s+go\s+inside|"
    r"what\s+can\s+go\s+in|"
    r"what\s+is\s+allowed\s+in|"
    r"what\s+may\s+appear\s+in|"
    r"content\s+model(?:\s+of|\s+for)?|"
    r"children\s+of"
    r")\b",
    re.IGNORECASE,
)
_PLACEMENT_PATTERN = re.compile(
    r"\b("
    r"where\s+can|"
    r"where\s+does|"
    r"where\s+is|"
    r"which\s+elements?\s+can\s+contain|"
    r"which\s+parents?\s+contain"
    r")\b",
    re.IGNORECASE,
)
_VALID_VALUES_PATTERN = re.compile(
    r"\b("
    r"valid\s+values?|"
    r"allowed\s+values?|"
    r"what\s+values?\s+can|"
    r"what\s+does\s+@?[A-Za-z_:][A-Za-z0-9_.:-]*\s+have"
    r")\b",
    re.IGNORECASE,
)
_EXAMPLE_PATTERN = re.compile(r"\b(example|sample|snippet)\b", re.IGNORECASE)
_COMPARISON_PATTERN = re.compile(r"\b(vs\.?|versus|compare|difference\s+between)\b", re.IGNORECASE)


@dataclass(frozen=True)
class DitaQueryIntent:
    mode: str
    raw_query: str
    element_names: list[str]
    attribute_names: list[str]
    wants_examples: bool


def _normalize_token(text: str) -> str:
    normalized = str(text or "").strip().strip("`'\"?.,;:!()[]{}<>").lstrip("@").replace("_", "-").lower()
    return _ATTRIBUTE_ALIASES.get(normalized, normalized)


def extract_attribute_names(query: str) -> list[str]:
    text = (query or "").strip()
    if not text:
        return []

    known = set(list_attribute_names())
    matches: list[str] = []

    def add(candidate: str) -> None:
        normalized = _normalize_token(candidate)
        if normalized.endswith("'s"):
            normalized = normalized[:-2]
        if not normalized or normalized in _ATTRIBUTE_STOPWORDS:
            return
        if normalized in known and normalized not in matches:
            matches.append(normalized)

    for match in _ATTRIBUTE_PATTERN.finditer(text):
        candidate = next((group for group in match.groups() if group), "")
        if candidate:
            add(candidate)

    for token in _TOKEN_PATTERN.findall(text):
        normalized = _normalize_token(token)
        if (
            normalized in _CONTEXTUAL_ATTRIBUTE_NAMES
            and not str(token or "").startswith("@")
            and not re.search(rf"@?{re.escape(str(token))}\s*=", text, re.IGNORECASE)
        ):
            continue
        add(token)

    return matches


def extract_element_names(query: str, explicit_elements: list[str] | None = None) -> list[str]:
    known = set(list_element_names())
    known_attributes = set(list_attribute_names())
    matches: list[str] = []
    explicit_normalized = {_normalize_token(item) for item in explicit_elements or []}
    candidates = list(explicit_elements or [])
    candidates.extend(_TOKEN_PATTERN.findall(query or ""))

    for candidate in candidates:
        normalized = _normalize_token(candidate)
        explicit_element_mention = normalized in explicit_normalized or re.search(
            rf"<\s*{re.escape(str(candidate).lstrip('<').lstrip('/'))}\b|\b{re.escape(str(candidate))}\s+element\b",
            query or "",
            re.IGNORECASE,
        )
        if normalized in known_attributes and not explicit_element_mention:
            continue
        if normalized in _CONTEXTUAL_ELEMENT_NAMES and not explicit_element_mention:
            continue
        if normalized == "table" and not explicit_element_mention:
            if re.search(r"\btable\s+of\s+contents\b", query or "", re.IGNORECASE):
                continue
        if normalized == "example" and not re.search(r"<\s*example\b|\bexample\s+element\b", query or "", re.IGNORECASE):
            continue
        if normalized in known and normalized not in matches:
            matches.append(normalized)
    return matches


def interpret_dita_query(query: str, explicit_elements: list[str] | None = None) -> DitaQueryIntent:
    raw_query = (query or "").strip()
    lowered = raw_query.lower()
    attribute_names = extract_attribute_names(raw_query)
    element_names = extract_element_names(raw_query, explicit_elements=explicit_elements)
    wants_examples = bool(_EXAMPLE_PATTERN.search(lowered))

    if _COMPARISON_PATTERN.search(lowered):
        if len(attribute_names) >= 2:
            mode = "attribute_comparison"
        elif len(element_names) >= 2:
            mode = "element_comparison"
        elif attribute_names:
            mode = "attribute_definition"
        elif element_names:
            mode = "element_definition"
        else:
            mode = "generic_lookup"
    elif attribute_names:
        if _VALID_VALUES_PATTERN.search(lowered):
            mode = "attribute_values"
        else:
            mode = "attribute_definition"
    elif element_names:
        if _CONTENT_MODEL_PATTERN.search(lowered):
            mode = "content_model_query"
        elif _PLACEMENT_PATTERN.search(lowered):
            mode = "allowed_usage_query"
        elif wants_examples:
            mode = "example_request"
        else:
            mode = "element_definition"
    else:
        mode = "generic_lookup"

    return DitaQueryIntent(
        mode=mode,
        raw_query=raw_query,
        element_names=element_names,
        attribute_names=attribute_names,
        wants_examples=wants_examples,
    )
