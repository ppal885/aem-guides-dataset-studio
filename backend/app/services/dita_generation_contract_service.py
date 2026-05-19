from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.core.schemas_dita_generation_contract import (
    ArtifactContract,
    AttributeConstraint,
    ClarificationRequest,
    ConstructSemantic,
    ConstraintConflict,
    DomainDecomposition,
    DitaGenerationContract,
    ElementConstraint,
    FamilyDecision,
    FilenameRequirement,
    KeyedLinkRequirement,
    PrologMetadataConstraint,
    StructureRequirement,
    TopicrefAttributeDistributionConstraint,
)
from app.services.dita_attribute_catalog import get_attribute_spec
from app.services.dita_construct_semantics_service import (
    choose_family_hint,
    infer_construct_semantics,
    infer_domain_decomposition,
    primary_construct_semantic,
)
from app.services.dita_query_interpreter import extract_attribute_names, extract_element_names
from app.services.dita_spec_registry_service import get_element_spec
from app.services.dita_xml_headers import has_expected_dita_header
from app.generator.generate import sanitize_filename

_NON_DITA_OUTPUT_PATTERN = re.compile(
    r"\b(feature files?|gherkin|cucumber|step definitions?|page objects?|page object|playwright|selenium)\b",
    re.IGNORECASE,
)
_MAP_PATTERN = re.compile(r"\b(bookmap|ditamap|map)\b", re.IGNORECASE)
_GLOSSARY_PATTERN = re.compile(r"\b(glossary|glossaries|glossentry|glossentries)\b", re.IGNORECASE)
_TASK_PATTERN = re.compile(r"\btask(?:\s+topic)?s?\b", re.IGNORECASE)
_CONCEPT_PATTERN = re.compile(r"\bconcept(?:\s+topic)?s?\b", re.IGNORECASE)
_REFERENCE_PATTERN = re.compile(r"\breference(?:\s+topic)?s?\b", re.IGNORECASE)
_TOPIC_PATTERN = re.compile(r"\btopic(?:s)?\b", re.IGNORECASE)
_SUBJECT_PATTERN = re.compile(
    r"\b(?:about|for|on|regarding|covering)\s+([A-Za-z0-9][^.,;!?]+)",
    re.IGNORECASE,
)
_SUBJECT_TRIM_PATTERNS = (
    re.compile(r"\s+and\s+(?:keep|set|mark|make|include|add|use|using)\b", re.IGNORECASE),
    re.compile(r"\s+and\s+\d+\s+(?:concept|task|reference|topic|glossentry|glossary|map)\b", re.IGNORECASE),
    re.compile(r"\s+with\s+@?[A-Za-z_:][A-Za-z0-9_.:-]*\s*=", re.IGNORECASE),
    re.compile(r"\s+with\s+(?:yaml|json|xml|bash|shell|python|java|javascript|typescript|sql|codeblocks?|code\s+blocks?|tables?|simpletables?|properties|refsyn)\b", re.IGNORECASE),
    re.compile(r"\s+with\s+(?:prolog|metadata|processing-role|chunk|collection-type|linking|toc|print|keyscope|keydef|mapref|topicref|reltable|ditavalref)\b", re.IGNORECASE),
    re.compile(r"\s+using\s+(?:conref|conkeyref|keyref|tables?|simpletable|properties|codeblocks?|yaml|xref|link|keyscope|keydef|mapref|topicref|reltable|ditavalref)\b", re.IGNORECASE),
    re.compile(r"\s+plus\s+\d+\s+(?:concept|task|reference|topic|glossentry|glossary|map)\b", re.IGNORECASE),
)
_EXAMPLE_REQUEST_PATTERN = re.compile(r"\b(example|examples|demo|sample|scaffold|template|boilerplate)\b", re.IGNORECASE)
_XML_EXAMPLE_PATTERN = re.compile(r"\bxml\b", re.IGNORECASE)
_MINIMAL_DEMO_PATTERN = re.compile(r"\b(minimal|min|small|basic|simple)\s+(?:demo|example|bundle)?\b", re.IGNORECASE)
_FULL_DEMO_PATTERN = re.compile(r"\b(full|complete|comprehensive|rich)\s+(?:demo|example|bundle)?\b|\bfull\s+bundle\b", re.IGNORECASE)
_SINGLE_TOPIC_EXAMPLE_PATTERN = re.compile(
    r"\b(single|one|1)\s+(?:dita\s+)?(?:topic|concept|task|reference)\b",
    re.IGNORECASE,
)
_METADATA_CONTEXT_PATTERN = re.compile(r"\b(?:prolog(?:\s+(?:metadata|information))?|metadata)\b", re.IGNORECASE)
_GLOSSARY_USAGE_PATTERN = re.compile(
    r"\b(?:use|using|reference|referencing)\s+(?:those|the|these)?\s*(?:glossary\s+)?(?:terms|entries|acronyms|abbreviations|them)\b",
    re.IGNORECASE,
)
_COUNT_PATTERNS = {
    "glossentry": re.compile(r"\b(\d+)\s+(?:glossary|glossaries|glossentry|glossentries)\b", re.IGNORECASE),
    "task": re.compile(r"\b(\d+)\s+tasks?\b", re.IGNORECASE),
    "concept": re.compile(r"\b(\d+)\s+concepts?\b", re.IGNORECASE),
    "reference": re.compile(r"\b(\d+)\s+references?\b", re.IGNORECASE),
    "topic": re.compile(r"\b(\d+)\s+topics?\b", re.IGNORECASE),
}
_ATTRIBUTE_VALUE_TEMPLATE = r"(?:@?{name}\b\s*=\s*[\"'](?P<quoted>[^\"']+)[\"']|@?{name}\b\s*=\s*(?P<bare>[A-Za-z0-9_.:-]+))"
_XML_TAG_PATTERN = re.compile(r"<\s*/?\s*([A-Za-z][A-Za-z0-9_.:-]*)\b")
_TOPICREF_DISTRIBUTION_PATTERNS = (
    r"\b(?:keep|set|mark|make|with)\s+(?P<count>\d+)\s+topics?\b(?P<trailing>[^.?!\n]{0,120})",
    r"\b(?P<count>\d+)\s+topics?\s+(?P<trailing>[^.?!\n]{0,120})",
    r"\b(?P<count>\d+)\s+topicrefs?\s+(?P<trailing>[^.?!\n]{0,120})",
)

_TASK_FAMILY_SIGNALS = {
    "task",
    "taskbody",
    "prereq",
    "context",
    "steps",
    "steps-unordered",
    "step",
    "cmd",
    "info",
    "stepxmp",
    "stepresult",
    "substeps",
    "substep",
    "choicetable",
    "choices",
}
_REFERENCE_FAMILY_SIGNALS = {
    "reference",
    "refbody",
    "properties",
    "property",
    "proptype",
    "propvalue",
    "propdesc",
}
_CONCEPT_FAMILY_SIGNALS = {"concept", "conbody"}
_GLOSSARY_FAMILY_SIGNALS = {"glossentry", "glossdef", "glossbody", "glossalt"}
_MAP_FAMILY_SIGNALS = {
    "map",
    "bookmap",
    "topicref",
    "topicgroup",
    "topichead",
    "topicset",
    "mapref",
    "navref",
    "reltable",
    "relrow",
    "relcell",
    "keydef",
    "ditavalref",
    "subjectscheme",
    "subjectdef",
    "subjecthead",
    "enumerationdef",
    "attributedef",
    "topicmeta",
    "bookmeta",
}
_MAP_ATTRIBUTE_SIGNALS = {
    "chunk",
    "collection-type",
    "processing-role",
    "linking",
    "toc",
    "print",
    "keyscope",
    "keys",
    "keyref",
    "copy-to",
    "navtitle",
    "locktitle",
}
_MAP_SCOPED_EXAMPLE_CONSTRUCTS = {
    "keyscope",
    "keydef",
    "keyref",
    "keys",
    "mapref",
    "topicref",
    "topichead",
    "topicgroup",
    "navref",
    "reltable",
    "relrow",
    "relcell",
    "ditavalref",
    "ditaval",
    "subjectscheme",
    "subjectdef",
    "subjecthead",
    "enumerationdef",
    "attributedef",
}
_EXAMPLE_SHAPE_REQUIRED_CONSTRUCTS = {"keyscope"}
_SUPPORTED_METADATA_FIELDS = ("author", "audience", "keywords", "critdates", "permissions", "prodinfo")
_METADATA_FIELD_ALIASES = {
    "author": ("author", "author name"),
    "audience": ("audience",),
    "keywords": ("keywords", "keyword"),
    "critdates": ("critdates", "critical dates", "critical date"),
    "permissions": ("permissions", "permission"),
    "prodinfo": ("prodinfo", "product info", "product information"),
}
_STRUCTURE_PATTERNS: dict[str, re.Pattern[str]] = {
    "table": re.compile(r"\btables?\b", re.IGNORECASE),
    "simpletable": re.compile(r"\bsimpletable\b", re.IGNORECASE),
    "properties": re.compile(r"\bproperties\b", re.IGNORECASE),
    "codeblock": re.compile(r"\bcode\s*blocks?\b|\bcodeblock\b", re.IGNORECASE),
    "yaml": re.compile(r"\byaml\b", re.IGNORECASE),
    "keydef": re.compile(r"\bkeydefs?\b", re.IGNORECASE),
    "topicref": re.compile(r"\btopicrefs?\b", re.IGNORECASE),
    "reltable": re.compile(r"\breltable\b", re.IGNORECASE),
    "topichead": re.compile(r"\btopichead\b", re.IGNORECASE),
    "topicgroup": re.compile(r"\btopicgroup\b", re.IGNORECASE),
    "mapref": re.compile(r"\bmapref\b", re.IGNORECASE),
    "navref": re.compile(r"\bnavref\b", re.IGNORECASE),
    "ditavalref": re.compile(r"\bditavalref\b", re.IGNORECASE),
    "subjectScheme": re.compile(r"\bsubject\s+scheme\b|\bsubjectscheme\b", re.IGNORECASE),
    "xref": re.compile(r"\bxrefs?\b|\bxref\b", re.IGNORECASE),
    "related-links": re.compile(r"\brelated[- ]links?\b", re.IGNORECASE),
    "link": re.compile(r"\bexternal links?\b|\b<link\b|\blink\s+element\b", re.IGNORECASE),
    "refsyn": re.compile(r"\brefsyn\b", re.IGNORECASE),
    "pre": re.compile(r"\bpreformatted\b|\bpre\b", re.IGNORECASE),
    "msgblock": re.compile(r"\bmsgblock\b", re.IGNORECASE),
}
_CODEBLOCK_LANGUAGES = (
    "yaml",
    "json",
    "xml",
    "bash",
    "shell",
    "python",
    "java",
    "javascript",
    "typescript",
    "sql",
)
_CODEBLOCK_LANGUAGE_PATTERN = re.compile(
    r"\b(?:(?P<prefix>yaml|json|xml|bash|shell|python|java|javascript|typescript|sql)\s+code\s*blocks?|"
    r"code\s*blocks?\s+(?:containing|with|using|in)\s+(?P<suffix>yaml|json|xml|bash|shell|python|java|javascript|typescript|sql))\b",
    re.IGNORECASE,
)
_STRUCTURE_COUNT_PATTERN = re.compile(
    r"\b(?P<count>\d+)\s+(?P<name>tables?|simpletables?|code\s*blocks?|codeblocks?)\b",
    re.IGNORECASE,
)
_TABLE_COLUMNS_ROWS_PATTERN = re.compile(
    r"\b(?:tables?|simpletables?)\b[^.?!\n]{0,100}\b(?P<columns>\d+)\s+columns?\b[^.?!\n]{0,100}\b(?P<rows>\d+)\s+rows?\b",
    re.IGNORECASE,
)
_TABLE_ROWS_COLUMNS_PATTERN = re.compile(
    r"\b(?:tables?|simpletables?)\b[^.?!\n]{0,100}\b(?P<rows>\d+)\s+rows?\b[^.?!\n]{0,100}\b(?P<columns>\d+)\s+columns?\b",
    re.IGNORECASE,
)
_LOOSE_COLUMNS_ROWS_PATTERN = re.compile(
    r"\b(?P<columns>\d+)\s+columns?\b[^.?!\n]{0,80}\b(?P<rows>\d+)\s+rows?\b",
    re.IGNORECASE,
)
_LOOSE_ROWS_COLUMNS_PATTERN = re.compile(
    r"\b(?P<rows>\d+)\s+rows?\b[^.?!\n]{0,80}\b(?P<columns>\d+)\s+columns?\b",
    re.IGNORECASE,
)
_EXTERNAL_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_EXTERNAL_KEYDEF_XREF_PATTERN = re.compile(
    r"\b(?:external|web|url|urls|link|links|resource|resources)\b(?=[\s\S]{0,180}\bkeydefs?\b)(?=[\s\S]{0,240}\b(?:xrefs?|cross[- ]?references?|keyrefs?)\b)|"
    r"\bkeydefs?\b(?=[\s\S]{0,180}\b(?:external|web|url|urls|link|links|resource|resources)\b)(?=[\s\S]{0,240}\b(?:xrefs?|cross[- ]?references?|keyrefs?)\b)",
    re.IGNORECASE,
)
_XREF_VARIETY_PATTERN = re.compile(
    r"\b(?:all|every|different|various)\s+(?:types?|kinds?|forms?)\s+of\s+(?:xrefs?|cross[- ]?references?)\b|"
    r"\b(?:xrefs?|cross[- ]?references?)\b[^.?!\n]{0,100}\b(?:all|every|different|various)\s+(?:types?|kinds?|forms?)\b|"
    r"\b(?:all|every|different|various)\s+(?:xrefs?|cross[- ]?references?)\b",
    re.IGNORECASE,
)
_FILENAME_EXPLICIT_PATTERN = re.compile(
    r"\b(?:file\s*name|filename)\b\s*(?:as|is|=|:|called|named|should\s+be|with)?\s*(?:\"(?P<double>[^\"]+)\"|'(?P<single>[^']+)'|`(?P<backtick>[^`]+)`|(?P<bare>[A-Za-z0-9][^.,;\n]*?\.dita))",
    re.IGNORECASE,
)
_FILENAME_MENTION_PATTERN = re.compile(r"\b(?:file\s*name|filename)\b", re.IGNORECASE)
_SPECIAL_FILENAME_PATTERN = re.compile(r"\b(?:special\s+characters?|unsafe|invalid|windows[- ]unsafe)\b", re.IGNORECASE)
_METADATA_XML_MARKERS: dict[str, tuple[str, ...]] = {
    "author": ("<author",),
    "audience": ('name="audience"', "<audience"),
    "keywords": ("<keywords", "<keyword"),
    "critdates": ("<critdates", 'name="critdates"'),
    "permissions": ("<permissions", 'name="permissions"'),
    "prodinfo": ("<prodinfo", 'name="prodinfo"'),
}


def _extract_count(text: str, key: str) -> int | None:
    matcher = _COUNT_PATTERNS[key].search(text)
    if not matcher:
        return None
    try:
        return max(1, int(matcher.group(1)))
    except (TypeError, ValueError):
        return None


_WORD_NUM_TOPICS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
_WORD_NUMBER_TOPICS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(?:at\s+least|at\s+minimum)\s+(one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+topics?\b",
            re.IGNORECASE,
        ),
            "word",
    ),
    (
        re.compile(
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
            r"sixteen|seventeen|eighteen|nineteen|twenty)\s+or\s+more\s+topics?\b",
            re.IGNORECASE,
        ),
            "word",
    ),
    (
        re.compile(
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+separate\s+topics?\b",
            re.IGNORECASE,
        ),
            "word",
    ),
    (
        re.compile(
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+distinct\s+topics?\b",
            re.IGNORECASE,
        ),
            "word",
    ),
)


def _extract_word_number_topics_floor(text: str) -> int | None:
    """Spelled-out counts like 'at least three topics' (complements digit _extract_count)."""
    if not (text or "").strip():
        return None
    best: int | None = None
    for pat, _kind in _WORD_NUMBER_TOPICS_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        w = (m.group(1) or "").strip().lower()
        n = _WORD_NUM_TOPICS.get(w)
        if n is None:
            continue
        best = n if best is None else max(best, n)
    return best


def _extract_subject(text: str) -> str | None:
    matcher = _SUBJECT_PATTERN.search(text)
    if not matcher:
        return None
    subject = re.sub(r"\s+", " ", (matcher.group(1) or "").strip()).strip(" .,:;!?")
    for pattern in _SUBJECT_TRIM_PATTERNS:
        split_match = pattern.search(subject)
        if split_match:
            subject = subject[: split_match.start()].strip(" .,:;!?")
            break
    return subject or None


def _refine_subject_after_jira_followup(subject: str | None, *, full_source_text: str) -> str | None:
    """Replace vague 'on the jira … more topics' subjects with Jira Summary when present."""
    if not subject:
        return subject
    s = subject.strip()
    if not re.match(r"^(the|this)\s+jira\b", s, re.IGNORECASE):
        return subject
    if not re.search(r"\b(?:more|multiple|several|topics?|hierarchy|hierar)\b", s, re.IGNORECASE):
        return subject
    m = re.search(r"(?:^|\n)\s*Summary:\s*([^\n]+)", full_source_text, re.IGNORECASE | re.MULTILINE)
    if m:
        candidate = re.sub(r"\s+", " ", (m.group(1) or "").strip())
        if candidate and len(candidate) <= 500:
            return candidate
    return subject


def _artifact_label(kind: str, count: int) -> str:
    if kind == "ditamap":
        return f"{count} DITA map{'s' if count != 1 else ''}"
    if kind == "ditaval":
        return f"{count} DITAVAL profile{'s' if count != 1 else ''}"
    if kind == "subjectscheme":
        return f"{count} subject scheme map{'s' if count != 1 else ''}"
    if kind == "glossentry":
        return f"{count} glossary entr{'y' if count == 1 else 'ies'}"
    if kind in {"concept", "task", "reference"}:
        return f"{count} {kind} topic{'s' if count != 1 else ''}"
    if kind == "topic":
        return f"{count} topic{'s' if count != 1 else ''}"
    return f"{count} {kind}"


def _normalize_topic_family(text: str) -> str:
    if _TASK_PATTERN.search(text):
        return "task"
    if _CONCEPT_PATTERN.search(text):
        return "concept"
    if _REFERENCE_PATTERN.search(text):
        return "reference"
    if _TOPIC_PATTERN.search(text):
        return "topic"
    return "auto"


def _extract_preferred_structures(text: str, explicit_elements: list[str]) -> list[str]:
    explicit = {str(item or "").strip().lower() for item in explicit_elements}
    preferred: list[str] = []
    for name, pattern in _STRUCTURE_PATTERNS.items():
        if name in explicit:
            continue
        if pattern.search(text or "") and name not in preferred:
            preferred.append(name)
    return preferred


def _normalize_structure_name(name: str) -> str:
    normalized = " ".join(str(name or "").lower().split())
    if normalized in {"code block", "code blocks", "codeblock", "codeblocks"}:
        return "codeblock"
    if normalized in {"simpletable", "simpletables"}:
        return "simpletable"
    if normalized in {"table", "tables"}:
        return "table"
    return normalized.replace(" ", "-")


def _extract_structure_requirements(text: str, preferred_structures: list[str]) -> list[StructureRequirement]:
    source_text = text or ""
    preferred = {str(item or "").strip().lower() for item in preferred_structures}
    requirements: dict[str, StructureRequirement] = {}

    def ensure(name: str) -> StructureRequirement:
        normalized = _normalize_structure_name(name)
        if normalized not in requirements:
            requirements[normalized] = StructureRequirement(structure_name=normalized)
        return requirements[normalized]

    for match in _STRUCTURE_COUNT_PATTERN.finditer(source_text):
        count = int(match.group("count"))
        name = _normalize_structure_name(match.group("name"))
        requirement = ensure(name)
        requirement.count = count

    table_match = (
        _TABLE_COLUMNS_ROWS_PATTERN.search(source_text)
        or _TABLE_ROWS_COLUMNS_PATTERN.search(source_text)
        or (
            _LOOSE_COLUMNS_ROWS_PATTERN.search(source_text)
            if {"table", "simpletable"} & preferred
            else None
        )
        or (
            _LOOSE_ROWS_COLUMNS_PATTERN.search(source_text)
            if {"table", "simpletable"} & preferred
            else None
        )
    )
    if table_match:
        table_name = "simpletable" if "simpletable" in preferred else "table"
        requirement = ensure(table_name)
        requirement.columns = int(table_match.group("columns"))
        requirement.rows = int(table_match.group("rows"))

    language_match = _CODEBLOCK_LANGUAGE_PATTERN.search(source_text)
    if language_match:
        language = str(language_match.group("prefix") or language_match.group("suffix") or "").lower()
        if language in _CODEBLOCK_LANGUAGES:
            requirement = ensure("codeblock")
            requirement.language = language

    return list(requirements.values())


def _format_structure_requirement(requirement: StructureRequirement) -> str:
    parts = [requirement.structure_name]
    if requirement.count is not None:
        parts.append(f"count={requirement.count}")
    if requirement.columns is not None:
        parts.append(f"columns={requirement.columns}")
    if requirement.rows is not None:
        parts.append(f"rows={requirement.rows}")
    if requirement.language:
        parts.append(f"language={requirement.language}")
    return " ".join(parts)


def _slug_key_name(value: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", value.lower())
    if not tokens:
        return "external-docs"
    useful = [token for token in tokens if token not in {"external", "link", "links", "url", "urls", "resource", "resources"}]
    if "api" in useful:
        return "external-api"
    if "support" in useful or "help" in useful:
        return "external-support"
    if "docs" in useful or "documentation" in useful or "document" in useful:
        return "external-docs"
    return "external-docs"


def _extract_external_keyed_link_requirements(text: str) -> list[KeyedLinkRequirement]:
    source_text = text or ""
    if not _EXTERNAL_KEYDEF_XREF_PATTERN.search(source_text):
        return []

    url_match = _EXTERNAL_URL_PATTERN.search(source_text)
    href = (url_match.group(0).strip(".,);]") if url_match else "https://example.com/docs")
    lowered = source_text.lower()
    href_lowered = href.lower()
    if ".pdf" in href_lowered or re.search(r"\bpdf\b", lowered):
        fmt = "pdf"
    elif ".docx" in href_lowered or ".doc" in href_lowered or re.search(r"\bdocx?\b", lowered):
        fmt = "doc"
    else:
        fmt = "html"
    scope = "peer" if re.search(r"\bpeer\b", lowered) else "external"
    key_name = _slug_key_name(source_text)
    return [
        KeyedLinkRequirement(
            key_name=key_name,
            href=href,
            format=fmt,
            scope=scope,
            link_text="External documentation",
            source="external_keydef_xref_intent",
        )
    ]


def _is_xref_variety_request(text: str) -> bool:
    source_text = text or ""
    return bool(_XREF_VARIETY_PATTERN.search(source_text))


def _ensure_dita_extension(filename: str) -> str:
    clean = str(filename or "").strip()
    if not clean:
        return "topic.dita"
    if not clean.lower().endswith((".dita", ".xml")):
        clean += ".dita"
    return clean


def _extract_filename_requirements(text: str) -> tuple[list[FilenameRequirement], bool]:
    source_text = text or ""
    match = _FILENAME_EXPLICIT_PATTERN.search(source_text)
    if not match:
        needs_clarification = bool(_FILENAME_MENTION_PATTERN.search(source_text) and _SPECIAL_FILENAME_PATTERN.search(source_text))
        return [], needs_clarification
    requested = str(match.group("double") or match.group("single") or match.group("backtick") or match.group("bare") or "").strip()
    requested = _ensure_dita_extension(requested)
    safe = sanitize_filename(requested, True)
    if not safe.lower().endswith((".dita", ".xml")):
        safe = f"{safe}.dita"
    return [
        FilenameRequirement(
            requested_name=requested,
            safe_name=safe,
            strategy="sanitize" if safe != requested else "preserve",
            reason=(
                "Unsafe filesystem characters were replaced in the physical filename."
                if safe != requested
                else "The requested filename is already safe for generation."
            ),
            source="filename_intent",
        )
    ], False


def _is_example_request(text: str, element_names: list[str], attribute_names: list[str]) -> bool:
    lowered_elements = {str(item or "").strip().lower() for item in element_names if str(item or "").strip()}
    lowered_attributes = {str(item or "").strip().lower() for item in attribute_names if str(item or "").strip()}
    if _EXAMPLE_REQUEST_PATTERN.search(text or ""):
        return True
    if _XML_EXAMPLE_PATTERN.search(text or "") and (
        lowered_elements & _MAP_SCOPED_EXAMPLE_CONSTRUCTS or lowered_attributes & _MAP_SCOPED_EXAMPLE_CONSTRUCTS
    ):
        return True
    return False


def _detect_example_shape(text: str) -> str:
    if _MINIMAL_DEMO_PATTERN.search(text or ""):
        return "minimal_demo"
    if _FULL_DEMO_PATTERN.search(text or ""):
        return "full_demo"
    return "unspecified"


def _detect_example_construct(element_names: list[str], attribute_names: list[str]) -> tuple[str | None, str | None]:
    lowered_attributes = [str(item or "").strip().lower() for item in attribute_names if str(item or "").strip()]
    lowered_elements = [str(item or "").strip().lower() for item in element_names if str(item or "").strip()]
    for name in lowered_attributes:
        if name in _MAP_SCOPED_EXAMPLE_CONSTRUCTS:
            return name, "bundle"
    for name in lowered_elements:
        if name in _MAP_SCOPED_EXAMPLE_CONSTRUCTS:
            return name, "bundle"
    return None, None


def _extract_metadata_value(text: str, field_name: str) -> str | None:
    all_fields = "|".join(re.escape(item) for item in _SUPPORTED_METADATA_FIELDS)
    pattern = re.compile(
        rf"\b{re.escape(field_name)}\s*=\s*(?:\"(?P<quoted>[^\"]+)\"|'(?P<single>[^']+)'|(?P<bare>.+?))(?=(?:,\s*(?:{all_fields})\b)|(?:\s+and\s+(?:{all_fields})\b)|[.;\n]|$)",
        re.IGNORECASE,
    )
    match = pattern.search(text or "")
    if not match:
        return None
    value = str(match.group("quoted") or match.group("single") or match.group("bare") or "").strip().strip(",")
    return value or None


def _extract_metadata_constraints(text: str) -> list[PrologMetadataConstraint]:
    if not _METADATA_CONTEXT_PATTERN.search(text or ""):
        return []
    constraints: list[PrologMetadataConstraint] = []
    for field_name in _SUPPORTED_METADATA_FIELDS:
        value = _extract_metadata_value(text, field_name)
        mentioned = bool(value)
        if not mentioned:
            aliases = _METADATA_FIELD_ALIASES.get(field_name, (field_name,))
            mentioned = any(re.search(rf"\b{re.escape(alias)}\b", text or "", re.IGNORECASE) for alias in aliases)
        if not mentioned:
            continue
        constraints.append(
            PrologMetadataConstraint(
                field_name=field_name,
                value=value,
            )
        )
    return constraints


def _missing_metadata_fields(metadata_constraints: list[PrologMetadataConstraint]) -> list[str]:
    return [item.field_name for item in metadata_constraints if not str(item.value or "").strip()]


def _needs_glossary_consuming_topics(text: str, wants_glossary: bool, topic_count: int) -> bool:
    if not wants_glossary:
        return False
    if topic_count > 0:
        return True
    return bool(_GLOSSARY_USAGE_PATTERN.search(text or ""))


def _infer_family_from_elements(element_names: list[str]) -> str | None:
    families: set[str] = set()
    for element_name in element_names:
        lowered = str(element_name or "").strip().lower()
        if lowered in _TASK_FAMILY_SIGNALS:
            families.add("task")
        elif lowered in _REFERENCE_FAMILY_SIGNALS:
            families.add("reference")
        elif lowered in _CONCEPT_FAMILY_SIGNALS:
            families.add("concept")
        elif lowered in _GLOSSARY_FAMILY_SIGNALS:
            families.add("glossentry")
        elif lowered in _MAP_FAMILY_SIGNALS:
            families.add("map")
    return next(iter(families)) if len(families) == 1 else None


def _extract_attribute_values(text: str, attribute_name: str) -> list[str]:
    values: list[str] = []

    def _append(value: str) -> None:
        clean = str(value or "").strip().strip(".,;:!?")
        if clean and clean not in values:
            values.append(clean)

    pattern = re.compile(_ATTRIBUTE_VALUE_TEMPLATE.format(name=re.escape(attribute_name)), re.IGNORECASE)
    for match in pattern.finditer(text):
        _append(str(match.group("quoted") or match.group("bare") or "").strip())

    natural_language_patterns = [
        re.compile(
            rf"(?:@?{re.escape(attribute_name)}\s+attribute|@?{re.escape(attribute_name)})\s+as\s+[\"']?(?P<value>[A-Za-z0-9_.:-]+)[\"']?",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?:set|use|with)\s+(?:the\s+)?@?{re.escape(attribute_name)}(?:\s+attribute)?\s+(?:(?:to|as)\s+)?[\"']?(?P<value>[A-Za-z0-9_.:-]+)[\"']?",
            re.IGNORECASE,
        ),
    ]
    for nl_pattern in natural_language_patterns:
        for match in nl_pattern.finditer(text):
            _append(str(match.group("value") or "").strip())
    return values


def _extract_topicref_attribute_distributions(
    text: str,
    required_attributes: list[AttributeConstraint],
    total_topic_count: int,
) -> list[TopicrefAttributeDistributionConstraint]:
    if total_topic_count <= 0:
        return []
    distributions: list[TopicrefAttributeDistributionConstraint] = []
    for constraint in required_attributes:
        attribute_name = str(constraint.attribute_name or "").strip().lower()
        if attribute_name not in _MAP_ATTRIBUTE_SIGNALS:
            continue
        values = [str(value or "").strip() for value in constraint.required_values if str(value or "").strip()]
        if not values:
            continue
        for value in values:
            matched_count: int | None = None
            for pattern_text in _TOPICREF_DISTRIBUTION_PATTERNS:
                pattern = re.compile(pattern_text, re.IGNORECASE)
                for match in pattern.finditer(text or ""):
                    trailing = str(match.group("trailing") or "")
                    if attribute_name not in trailing.lower() or value.lower() not in trailing.lower():
                        continue
                    try:
                        matched_count = max(1, min(total_topic_count, int(match.group("count") or "1")))
                    except (TypeError, ValueError):
                        matched_count = None
                    if matched_count is not None:
                        break
                if matched_count is not None:
                    break
            if matched_count is None and attribute_name == "processing-role" and value.lower() == "resource-only":
                matched_count = total_topic_count
            if matched_count is None:
                continue
            distributions.append(
                TopicrefAttributeDistributionConstraint(
                    attribute_name=attribute_name,
                    attribute_value=value,
                    count=matched_count,
                )
            )
    deduped: list[TopicrefAttributeDistributionConstraint] = []
    seen: set[tuple[str, str, int]] = set()
    for item in distributions:
        key = (item.attribute_name, item.attribute_value, item.count)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _collect_unknown_xml_tags(text: str, known_elements: list[str]) -> list[str]:
    known = {str(item).strip().lower() for item in known_elements if str(item).strip()}
    unknown: list[str] = []
    for match in _XML_TAG_PATTERN.finditer(text or ""):
        candidate = str(match.group(1) or "").strip().lower()
        if candidate and candidate not in known and candidate not in unknown:
            unknown.append(candidate)
    return unknown


def _element_scope(element_name: str) -> str:
    lowered = str(element_name or "").strip().lower()
    if lowered in _MAP_FAMILY_SIGNALS:
        return "bundle"
    return "artifact"


def _attribute_scope(attribute_name: str, spec: Any) -> str:
    if str(attribute_name or "").strip().lower() in _MAP_ATTRIBUTE_SIGNALS:
        return "bundle"
    supported = {str(item).strip().lower() for item in getattr(spec, "supported_elements", []) if str(item).strip()}
    if supported and supported.issubset(_MAP_FAMILY_SIGNALS):
        return "bundle"
    return "artifact"


def _supported_families_from_elements(elements: list[str]) -> set[str]:
    families: set[str] = set()
    for element_name in elements:
        implied = _infer_family_from_elements([element_name])
        if implied:
            families.add(implied)
    return families


def _strip_redundant_generic_topic_required_elements(
    required_elements: list[ElementConstraint],
    topic_family: str | None,
) -> None:
    """Drop artifact-level <topic> requirements when output is a specialized topic (task/concept/reference).

    Generic "topic" in prompts/registries must not force a literal `<topic>` element inside a `<task>` root.
    """
    fam = str(topic_family or "").strip().lower()
    if fam not in {"task", "concept", "reference"}:
        return
    required_elements[:] = [
        item
        for item in required_elements
        if not (
            str(item.name or "").strip().lower() == "topic"
            and str(getattr(item, "scope", None) or "artifact").lower() == "artifact"
        )
    ]


def _count_distinct_topicref_hrefs_to_bundle_files(
    map_texts: list[str],
    bundle_basenames_lower: set[str],
) -> int:
    """Count unique topicref @href targets that resolve to generated bundle files.

    Avoids false failures when a map repeats the same href or nesting duplicates naive `<topicref` counts.
    """
    targets: set[str] = set()
    for text in map_texts:
        for m in re.finditer(r"<topicref\b([^>]*)>", text or "", re.IGNORECASE):
            attrs = m.group(1) or ""
            href_match = re.search(r'\bhref\s*=\s*["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if not href_match:
                continue
            raw = href_match.group(1).strip()
            base = Path(raw.replace("\\", "/")).name.split("#")[0].strip().lower()
            if base and base in bundle_basenames_lower:
                targets.add(base)
    return len(targets)


def _append_missing_required_element(
    required_elements: list[ElementConstraint],
    element_name: str,
    *,
    scope: str = "artifact",
    implied_family: str | None = None,
    source: str = "construct_semantics",
) -> None:
    normalized = str(element_name or "").strip()
    if not normalized:
        return
    if any(str(item.name or "").strip().lower() == normalized.lower() for item in required_elements):
        return
    required_elements.append(
        ElementConstraint(
            name=normalized,
            scope=scope,  # type: ignore[arg-type]
            implied_family=implied_family,
            source=source,
        )
    )


def _append_missing_required_attribute(
    required_attributes: list[AttributeConstraint],
    attribute_name: str,
    *,
    scope: str = "bundle",
    implied_family: str | None = None,
    source: str = "construct_semantics",
) -> None:
    normalized = str(attribute_name or "").strip()
    if not normalized:
        return
    if any(str(item.attribute_name or "").strip().lower() == normalized.lower() for item in required_attributes):
        return
    required_attributes.append(
        AttributeConstraint(
            attribute_name=normalized,
            scope=scope,  # type: ignore[arg-type]
            implied_family=implied_family,
            source=source,
        )
    )


def _append_or_merge_required_attribute(
    required_attributes: list[AttributeConstraint],
    attribute_name: str,
    *,
    scope: str = "bundle",
    required_values: list[str] | None = None,
    supported_elements: list[str] | None = None,
    implied_family: str | None = None,
    source: str = "prompt",
) -> None:
    normalized = str(attribute_name or "").strip()
    if not normalized:
        return
    values = [str(value or "").strip() for value in (required_values or []) if str(value or "").strip()]
    elements = [str(value or "").strip() for value in (supported_elements or []) if str(value or "").strip()]
    for item in required_attributes:
        if str(item.attribute_name or "").strip().lower() != normalized.lower():
            continue
        for value in values:
            if value not in item.required_values:
                item.required_values.append(value)
        for element in elements:
            if element not in item.supported_elements:
                item.supported_elements.append(element)
        if implied_family and not item.implied_family:
            item.implied_family = implied_family
        return
    required_attributes.append(
        AttributeConstraint(
            attribute_name=normalized,
            scope=scope,  # type: ignore[arg-type]
            required_values=values,
            supported_elements=elements,
            implied_family=implied_family,
            source=source,
        )
    )


_MULTI_TOPIC_NL_PATTERN = re.compile(
    r"\b(?:more|multiple|several|many|extra|additional)\s+topics?\b|"
    r"\bmore\s+than\s+one\s+topic\b|"
    r"\bmore\s+data\b.*\b(?:topics?|hierarchy|hierar(?:chy|cy)|heirarchy|hyerarchy|hirarchy|hierachy)\b|"
    r"\b(?:bigger|larger|expanded?)\s+(?:bundle|set)\b.*\b(?:topics?|hierarchy|hierar(?:chy|cy)|heirarchy|hyerarchy|hirarchy|hierachy)\b|"
    r"\bnot\s+(?:just|only)\s+one\s+topics?\b|"
    r"\b(?:subtopics?|child\s+topics?|peer\s+topics?|sibling\s+topics?)\b|"
    r"\b(?:add|include)\s+(?:more|several|multiple)\s+topics?\b|"
    r"\b(?:couple|few)\s+more\s+topics?\b|"
    r"\b(?:topic\s+pack|bundle\s+of\s+topics?|collection\s+of\s+topics?|set\s+of\s+topics?|family\s+of\s+topics?|"
    r"full\s+outline\s+of\s+topics?)\b|"
    r"\b(?:information\s+architecture|IA)\s+(?:with|including|for)\s+(?:multiple|several|many)\s+topics?\b|"
    r"\b(?:expand|broaden)\s+coverage\b.{0,80}\btopics?\b|"
    r"\b(?:each|every)\s+(?:section|chapter)\s+(?:as|gets?)\s+(?:its\s+own\s+)?(?:a\s+)?topics?\b|"
    r"\bchapter\s+per\s+topics?\b|"
    r"\b(?:regenerate|redo)\s+with\s+(?:more|a\s+larger|a\s+bigger|larger|bigger)\b|"
    r"\bregenerate\b.{0,40}\bmore\b|"
    r"\bredo\s+with\s+a\s+larger\b|"
    r"\bscale\s+up\b.{0,80}\btopics?\b|"
    r"\bbigger\s+preview\b.{0,80}\btopics?\b|"
    r"\bsame\s+subject\b.{0,60}\bmore\s+topics?\b|"
    r"\b(?:more|extra)\s+(?:concept|task|reference)\s+topics?\b",
    re.IGNORECASE | re.DOTALL,
)
_HIERARCHY_MAP_NL_PATTERN = re.compile(
    r"\b(?:hierar(?:chy|cy)|hierarchical|heirarchy|hyerarchy|hirarchy|hierachy|"
    r"different\s+hierar(?:chy|cy)|different\s+(?:heirarchy|hyerarchy|hirarchy|hierachy)|"
    r"nested\s+(?:structure|topics?)|nest(?:ed|ing)\s+topics?|"
    r"topic\s+tree|outline\s+of\s+topics?|multi-?level|deeper\s+(?:hierarchy|tree)|branching\s+(?:structure|topics?)|"
    r"parent\s+and\s+child\s+topics?|(?:root|master)\s+map|map-?first|map\s+plus\s+topics?|structured\s+bundle|"
    r"navigable\s+(?:bundle|structure|outline|documentation|set)|"
    r"(?:table\s+of\s+contents|toc)\s+(?:with|including|and)\s+(?:topics?|topicrefs?|a\s+map)|"
    r"(?:table\s+of\s+contents|toc)\b.{0,120}\b(?:ditamap|bookmap|map|topics?)\b)\b",
    re.IGNORECASE | re.DOTALL,
)
_NL_SINGLE_TOPIC_STRONG = re.compile(
    r"\b(?:single\s+(?:dita\s+)?topic|one\s+topic\s+only|only\s+one\s+topic|just\s+one\s+topic|"
    r"exactly\s+one\s+topic|exactly\s+1\s+topic|a\s+single\s+page|only\s+a\s+snippet|standalone\s+topic)\b",
    re.IGNORECASE,
)


def _nl_topic_scale_bump_suppressed(text: str) -> bool:
    """Skip NL topic_count inflation when the user asked for a single artifact (unless multi/hierarchy NL also matches)."""
    if not _NL_SINGLE_TOPIC_STRONG.search(text):
        return False
    if _MULTI_TOPIC_NL_PATTERN.search(text) or _HIERARCHY_MAP_NL_PATTERN.search(text):
        return False
    return True


_NL_DOMAIN_TASK_FAMILY = re.compile(
    r"\b(?:"
    r"install(?:ation)?|set\s*up|setup|configur(?:e|ation)|deploy(?:ment)?|"
    r"upgrade|uninstall|troubleshoot(?:ing)?|migrat(?:e|ion)|provision(?:ing)?|"
    r"walkthrough|how-?to|operational\s+runbook|procedure|"
    r"(?:end-?)?user\s+(?:workflow|procedure)|"
    r"getting\s+started|first-?time\s+setup|runbook|playbook|(?:operational\s+|deployment\s+)?checklist"
    r")\b",
    re.IGNORECASE,
)
_NL_DOMAIN_CONCEPT_FAMILY = re.compile(
    r"\b(?:overview|introduction|rationale|background|"
    r"high-?level\s+architecture|understanding|concept(?:s)?\s+about|"
    r"big\s+picture|mental\s+model|why\s+it\s+matters|glossary-?style)\b",
    re.IGNORECASE,
)
_NL_DOMAIN_REFERENCE_FAMILY = re.compile(
    r"\b(?:parameter(?:s)?|syntax|command-?line|api\s+reference|reference\s+data|lookup\s+table|"
    r"REST|openapi|\bendpoints?\b|request\s*/\s*response|field\s+reference)\b",
    re.IGNORECASE,
)


def _infer_nl_domain_topic_family(text: str) -> str | None:
    """Infer task/concept/reference from domain language when map + NL scale-up otherwise stays generic topic."""
    if not (text or "").strip():
        return None
    lowered = text.lower()
    if _NL_DOMAIN_TASK_FAMILY.search(lowered):
        return "task"
    if _NL_DOMAIN_CONCEPT_FAMILY.search(lowered):
        return "concept"
    if _NL_DOMAIN_REFERENCE_FAMILY.search(lowered):
        return "reference"
    return None


def _family_conflicts(explicit_family: str | None, element_names: list[str]) -> list[ConstraintConflict]:
    if not explicit_family:
        return []
    explicit = explicit_family.lower()
    conflicts: list[ConstraintConflict] = []
    for element_name in element_names:
        lowered = str(element_name or "").strip().lower()
        implied = _infer_family_from_elements([lowered])
        if implied and implied not in {explicit, "map"}:
            conflicts.append(
                ConstraintConflict(
                    kind="family_structure_conflict",
                    requested=f"{explicit} + {lowered}",
                    reason=f"`{lowered}` implies `{implied}` structure, which conflicts with `{explicit}`.",
                    message=f"The requested `{explicit}` output cannot safely include `{lowered}`.",
                    suggested_families=[implied, explicit],
                )
            )
    return conflicts


def _build_summary(contract: DitaGenerationContract) -> str:
    if contract.status == "unsupported":
        return contract.summary or "This request mixes unsupported output types for the DITA generation flow."
    if contract.conflicts:
        return contract.summary or contract.conflicts[0].message
    if contract.example_request and contract.example_construct:
        shape = str(contract.example_shape or "unspecified").replace("_", " ")
        labels = ", ".join(item.label for item in contract.artifacts if item.label)
        if contract.example_shape_clarification_required:
            return f"`{contract.example_construct}` is a map-scoped DITA construct, so the example bundle shape needs to be chosen before generation."
        if contract.example_shape != "unspecified":
            return f"Previewing a {shape} for `{contract.example_construct}` with {labels}."
        if labels:
            return f"Previewing a construct-aware example for `{contract.example_construct}` with {labels}."
        return f"Previewing a construct-aware example for `{contract.example_construct}`."
    labels = ", ".join(item.label for item in contract.artifacts if item.label)
    summary = f"Previewing a DITA bundle with {labels}." if labels else "Previewing a DITA bundle."
    if contract.subject:
        summary += f" Topic domain: {contract.subject}."
    if contract.required_elements or contract.required_attributes:
        summary += " Explicit DITA constraints from the prompt are locked into the contract."
    if contract.topicref_attribute_distributions:
        rendered = ", ".join(
            f"{item.count} topicref{'s' if item.count != 1 else ''} with @{item.attribute_name}=\"{item.attribute_value}\""
            for item in contract.topicref_attribute_distributions
        )
        summary += f" Map topicref distribution: {rendered}."
    if contract.required_metadata:
        metadata_fields = ", ".join(item.field_name for item in contract.required_metadata)
        summary += f" Prolog metadata requested: {metadata_fields}."
    if contract.construct_semantics:
        summary += " Construct-aware planning: " + ", ".join(item.name for item in contract.construct_semantics) + "."
    if contract.domain_decomposition and contract.domain_decomposition.subtopics:
        summary += " Subject decomposition is available for more distinct topic coverage."
    if contract.glossary_usage_mode == "with_topics":
        summary += " Glossary entries will be paired with consuming topics."
    elif contract.glossary_usage_mode == "with_map_and_topics":
        summary += " Glossary entries will be paired with consuming topics and a map."
    return summary


def build_dita_generation_contract(
    *,
    text: str,
    instructions: str | None = None,
    screenshot_attached: bool = False,
    reference_attached: bool = False,
) -> DitaGenerationContract:
    source_text = (text or "").strip()
    clean_instructions = (instructions or "").strip() or None
    combined = "\n".join(part for part in [source_text, clean_instructions] if part).strip()

    if not source_text:
        return DitaGenerationContract(
            status="clarification_required",
            summary="Need a DITA generation request before I can preview the bundle.",
            clarification_needed=True,
            clarification_question="What DITA topic or bundle would you like me to generate?",
            clarification_request=ClarificationRequest(
                missing_field="request",
                question="What DITA topic or bundle would you like me to generate?",
            ),
        )

    unsupported = sorted({match.group(0).lower() for match in _NON_DITA_OUTPUT_PATTERN.finditer(combined)})
    if unsupported:
        return DitaGenerationContract(
            status="unsupported",
            summary="This flow generates DITA only, not test automation assets.",
            clarification_needed=True,
            clarification_question="I can generate DITA only here. What DITA topic, map, or glossary bundle do you want instead?",
            clarification_request=ClarificationRequest(
                missing_field="supported_dita_request",
                question="I can generate DITA only here. What DITA topic, map, or glossary bundle do you want instead?",
            ),
            warnings=[f"Unsupported output types requested: {', '.join(unsupported)}."],
            bundle_type="unsupported",
            topic_family="auto",
        )

    structure_text = source_text or combined
    wants_map = bool(_MAP_PATTERN.search(structure_text))
    wants_glossary = bool(_GLOSSARY_PATTERN.search(structure_text))
    explicit_family = _normalize_topic_family(structure_text)
    user_subject_source = re.split(r"\n---\s*\nJira / ticket context:\s*", source_text, maxsplit=1)[0].strip()
    subject = _extract_subject(user_subject_source) or _extract_subject(source_text) or _extract_subject(clean_instructions or "")
    subject = _refine_subject_after_jira_followup(subject, full_source_text=source_text)
    metadata_constraints = _extract_metadata_constraints(combined)
    missing_metadata_fields = _missing_metadata_fields(metadata_constraints)
    glossary_count = _extract_count(structure_text, "glossentry") or (1 if wants_glossary else 0)
    topic_count = (
        _extract_count(structure_text, "task")
        or _extract_count(structure_text, "concept")
        or _extract_count(structure_text, "reference")
        or _extract_count(structure_text, "topic")
        or 0
    )
    _word_topic_floor = _extract_word_number_topics_floor(combined)
    if _word_topic_floor is not None:
        topic_count = max(topic_count, _word_topic_floor)
    _suppress_nl_topic_bump = _nl_topic_scale_bump_suppressed(combined)
    # Natural-language scale-up (no numeric "5 topics" phrase): follow-ups like "more topics" / "different hierarchy".
    if _MULTI_TOPIC_NL_PATTERN.search(combined) and topic_count < 2 and not _suppress_nl_topic_bump:
        topic_count = max(topic_count, 5)
    if _HIERARCHY_MAP_NL_PATTERN.search(combined):
        wants_map = True
        if topic_count < 2 and not _suppress_nl_topic_bump:
            topic_count = max(topic_count, 4)
    xref_variety_request = _is_xref_variety_request(combined)
    if xref_variety_request:
        wants_map = True
        topic_count = max(topic_count, 2)
        if explicit_family == "reference":
            explicit_family = "topic"
    wants_glossary_consuming_topics = _needs_glossary_consuming_topics(combined, wants_glossary, topic_count)

    element_names = extract_element_names(combined)
    attribute_names = extract_attribute_names(combined)
    preferred_structures = _extract_preferred_structures(combined, element_names)
    unknown_tags = _collect_unknown_xml_tags(combined, element_names)
    construct_semantics = infer_construct_semantics(
        text=combined,
        element_names=element_names,
        attribute_names=attribute_names,
        preferred_structures=preferred_structures,
        explicit_family=explicit_family,
    )
    primary_construct = primary_construct_semantic(construct_semantics)
    keyed_link_requirements = _extract_external_keyed_link_requirements(combined)
    filename_requirements, filename_clarification_required = _extract_filename_requirements(combined)

    required_elements: list[ElementConstraint] = []
    warnings: list[str] = []
    for element_name in element_names:
        spec = get_element_spec(element_name)
        if spec is None:
            warnings.append(f"No structured DITA spec facts were found for `{element_name}`.")
            continue
        required_elements.append(
            ElementConstraint(
                name=spec.name,
                scope=_element_scope(spec.name),
                implied_family=_infer_family_from_elements([spec.name]),
                allowed_parents=list(spec.allowed_parents),
                supported_attributes=list(spec.supported_attributes),
            )
        )

    for unknown_tag in unknown_tags:
        warnings.append(f"The prompt references `<{unknown_tag}>`, but there is no structured DITA spec entry for it yet.")

    required_attributes: list[AttributeConstraint] = []
    conflicts: list[ConstraintConflict] = []
    map_required_by_attributes = False
    for attribute_name in attribute_names:
        spec = get_attribute_spec(attribute_name)
        if spec is None:
            conflicts.append(
                ConstraintConflict(
                    kind="unknown_attribute",
                    requested=attribute_name,
                    reason="No structured DITA attribute spec exists for this attribute.",
                    message=f"The requested attribute `@{attribute_name}` is not available in the DITA spec registry.",
                )
            )
            continue
        requested_values = _extract_attribute_values(combined, attribute_name)
        invalid_values = [
            value
            for value in requested_values
            if spec.all_valid_values and value not in {str(item).strip() for item in spec.all_valid_values}
        ]
        if invalid_values:
            conflicts.append(
                ConstraintConflict(
                    kind="invalid_attribute_value",
                    requested=f"@{attribute_name}={', '.join(invalid_values)}",
                    reason=f"Valid values are {', '.join(spec.all_valid_values[:8])}.",
                    message=f"The requested value for `@{attribute_name}` is not valid DITA for this registry.",
                )
            )
        implied_family = "map" if attribute_name in (_MAP_ATTRIBUTE_SIGNALS | {"keyscope"}) else None
        if implied_family == "map":
            map_required_by_attributes = True
            if (
                explicit_family
                and explicit_family not in {"auto", "topic", "map"}
                and topic_count <= 1
                and not wants_glossary
                and not wants_glossary_consuming_topics
                and not _MAP_PATTERN.search(structure_text)
            ):
                conflicts.append(
                    ConstraintConflict(
                        kind="attribute_family_conflict",
                        requested=f"@{attribute_name}",
                        reason=(
                            f"`@{attribute_name}` is a map-oriented attribute, but the prompt only requests a single "
                            f"`{explicit_family}` topic without an explicit map."
                        ),
                        message=(
                            f"The requested `{explicit_family}` output cannot safely require `@{attribute_name}` "
                            "unless the bundle also includes a DITA map."
                        ),
                        suggested_families=["map", explicit_family],
                    )
                )
        supported_families = _supported_families_from_elements(list(spec.supported_elements))
        if (
            explicit_family
            and explicit_family not in {"auto", "topic", "map"}
            and supported_families
            and len(supported_families) == 1
            and attribute_name not in _MAP_ATTRIBUTE_SIGNALS
            and "map" not in supported_families
            and explicit_family not in supported_families
        ):
            conflicts.append(
                ConstraintConflict(
                    kind="attribute_family_conflict",
                    requested=f"@{attribute_name}",
                    reason=(
                        f"`@{attribute_name}` is supported on {', '.join(sorted(supported_families))} structures, "
                        f"not `{explicit_family}`."
                    ),
                    message=f"The requested `{explicit_family}` output cannot safely require `@{attribute_name}`.",
                    suggested_families=sorted(supported_families)[:3],
                )
            )
        required_attributes.append(
            AttributeConstraint(
                attribute_name=spec.attribute_name,
                scope=_attribute_scope(attribute_name, spec),
                required_values=requested_values,
                supported_elements=list(spec.supported_elements),
                valid_values=list(spec.all_valid_values),
                implied_family=implied_family,
            )
        )

    for semantic in construct_semantics:
        implied_scope = "bundle" if semantic.include_map or semantic.bundle_strategy in {"map_bundle", "mixed_bundle"} else "artifact"
        for element_name in semantic.required_elements:
            _append_missing_required_element(
                required_elements,
                element_name,
                scope=implied_scope if semantic.family_hint == "map" or element_name.lower() in _MAP_FAMILY_SIGNALS else "artifact",
                implied_family=semantic.family_hint,
            )
        for attribute_name in semantic.required_attributes:
            _append_missing_required_attribute(
                required_attributes,
                attribute_name,
                scope="bundle" if semantic.include_map else "artifact",
                implied_family=semantic.family_hint,
            )
        for structure_name in semantic.preferred_structures:
            if structure_name not in preferred_structures:
                preferred_structures.append(structure_name)

    for requirement in keyed_link_requirements:
        wants_map = True
        _append_missing_required_element(required_elements, "keydef", scope="bundle", implied_family="map", source=requirement.source)
        _append_missing_required_element(required_elements, "topicref", scope="bundle", implied_family="map", source=requirement.source)
        _append_missing_required_element(required_elements, "xref", scope="artifact", implied_family="topic", source=requirement.source)
        _append_or_merge_required_attribute(
            required_attributes,
            "keys",
            scope="bundle",
            supported_elements=["keydef"],
            implied_family="map",
            source=requirement.source,
        )
        _append_or_merge_required_attribute(
            required_attributes,
            "href",
            scope="bundle",
            supported_elements=["keydef"],
            implied_family="map",
            source=requirement.source,
        )
        _append_or_merge_required_attribute(
            required_attributes,
            "scope",
            scope="bundle",
            required_values=[requirement.scope],
            supported_elements=["keydef"],
            implied_family="map",
            source=requirement.source,
        )
        _append_or_merge_required_attribute(
            required_attributes,
            "format",
            scope="bundle",
            required_values=[requirement.format],
            supported_elements=["keydef"],
            implied_family="map",
            source=requirement.source,
        )
        _append_or_merge_required_attribute(
            required_attributes,
            "keyref",
            scope="artifact",
            supported_elements=["xref"],
            implied_family="topic",
            source=requirement.source,
        )

    if xref_variety_request:
        wants_map = True
        _append_missing_required_element(required_elements, "topicref", scope="bundle", implied_family="map", source="xref_variety_intent")
        _append_missing_required_element(required_elements, "keydef", scope="bundle", implied_family="map", source="xref_variety_intent")
        _append_missing_required_element(required_elements, "xref", scope="artifact", implied_family="topic", source="xref_variety_intent")

    structure_requirements = _extract_structure_requirements(combined, preferred_structures)
    for requirement in structure_requirements:
        if requirement.structure_name not in preferred_structures:
            preferred_structures.append(requirement.structure_name)
        if requirement.structure_name == "codeblock" and requirement.language:
            outputclass_value = f"language-{requirement.language}"
            if not any(
                str(item.attribute_name or "").strip().lower() == "outputclass"
                and outputclass_value in {str(value or "").strip().lower() for value in item.required_values}
                for item in required_attributes
            ):
                required_attributes.append(
                    AttributeConstraint(
                        attribute_name="outputclass",
                        scope="artifact",
                        required_values=[outputclass_value],
                        supported_elements=["codeblock"],
                        implied_family="reference",
                        source="structure_requirement",
                    )
                )
    structure_family_hint = (
        "reference"
        if {
            str(item.structure_name or "").strip().lower()
            for item in structure_requirements
        }
        & {"codeblock", "table", "simpletable", "properties"}
        else None
    )

    topicref_attribute_distributions = _extract_topicref_attribute_distributions(
        combined,
        required_attributes,
        topic_count or 1,
    )

    inferred_family = _infer_family_from_elements([item.name for item in required_elements])
    example_request = _is_example_request(combined, element_names, attribute_names)
    example_shape = _detect_example_shape(combined)
    example_construct, construct_scope = _detect_example_construct(element_names, attribute_names)
    if primary_construct and not example_construct:
        example_construct = primary_construct.name if example_request else None
        if example_request and primary_construct.bundle_strategy in {"topic_bundle", "glossary_pack", "map_bundle", "mixed_bundle"}:
            construct_scope = "bundle"
        elif example_request:
            construct_scope = "artifact"
    compatible_families = sorted(
        {
            item.implied_family
            for item in required_elements
            if item.implied_family
        }
        | {
            item.implied_family
            for item in required_attributes
            if item.implied_family
        }
        | {
            item.family_hint
            for item in construct_semantics
            if item.family_hint
        }
    )
    semantic_family_hint = choose_family_hint(construct_semantics)
    if explicit_family == "auto":
        explicit_family = None
    if explicit_family and explicit_family != "topic":
        resolved_topic_family = explicit_family
    elif inferred_family and inferred_family != "map":
        resolved_topic_family = inferred_family
    elif structure_family_hint:
        resolved_topic_family = structure_family_hint
    elif semantic_family_hint and semantic_family_hint != "map":
        resolved_topic_family = semantic_family_hint
    elif wants_map and not (topic_count or wants_glossary_consuming_topics or wants_glossary):
        resolved_topic_family = "map"
    else:
        resolved_topic_family = "topic" if (topic_count or wants_glossary_consuming_topics) else None

    if example_construct in _MAP_SCOPED_EXAMPLE_CONSTRUCTS:
        wants_map = True
    if any(item.include_map for item in construct_semantics):
        wants_map = True
    if map_required_by_attributes:
        wants_map = True
    if semantic_family_hint == "map" and not resolved_topic_family:
        resolved_topic_family = "map"
    if keyed_link_requirements:
        wants_map = True
        if not resolved_topic_family or resolved_topic_family == "map":
            resolved_topic_family = "topic"
    if xref_variety_request:
        wants_map = True
        if not resolved_topic_family or resolved_topic_family == "map":
            resolved_topic_family = "topic"

    if (
        resolved_topic_family == "topic"
        and wants_map
        and (
            _MULTI_TOPIC_NL_PATTERN.search(combined)
            or _HIERARCHY_MAP_NL_PATTERN.search(combined)
        )
    ):
        hinted = _infer_nl_domain_topic_family(combined)
        if hinted:
            resolved_topic_family = hinted
        else:
            # Map + NL scale-up without concept/reference/procedure cues: task is the safest default bundle shape.
            resolved_topic_family = "task"

    family_conflict_elements = [item.name for item in required_elements]
    if wants_glossary_consuming_topics:
        family_conflict_elements = [name for name in family_conflict_elements if str(name or "").strip().lower() != "glossentry"]
    conflicts.extend(_family_conflicts(resolved_topic_family, family_conflict_elements))

    if example_request and example_construct in _MAP_SCOPED_EXAMPLE_CONSTRUCTS:
        resolved_topic_family = "map"
        if _SINGLE_TOPIC_EXAMPLE_PATTERN.search(combined or ""):
            conflicts.append(
                ConstraintConflict(
                    kind="map_scoped_example_conflict",
                    requested=f"{example_construct} single-topic example",
                    reason=f"`{example_construct}` is resolved in DITA maps and map branches, not in a standalone topic file.",
                    message=f"The requested `{example_construct}` example cannot be generated as a single topic.",
                    suggested_families=["minimal demo", "full demo"],
                )
            )
    elif example_request and primary_construct and primary_construct.bundle_strategy == "map_bundle":
        resolved_topic_family = "map"
        if _SINGLE_TOPIC_EXAMPLE_PATTERN.search(combined or ""):
            conflicts.append(
                ConstraintConflict(
                    kind="map_scoped_example_conflict",
                    requested=f"{primary_construct.name} single-topic example",
                    reason=f"`{primary_construct.name}` needs map-scoped supporting files, not a standalone topic file.",
                    message=f"The requested `{primary_construct.name}` example cannot be generated as a single topic.",
                    suggested_families=["map bundle", "topic bundle"],
                )
            )

    if metadata_constraints and wants_map and not (topic_count or wants_glossary_consuming_topics):
        conflicts.append(
            ConstraintConflict(
                kind="metadata_map_conflict",
                requested="prolog metadata on a map-only bundle",
                reason="Maps do not use topic prolog metadata in the same way as topic files.",
                message="The requested prolog metadata needs topic files, not a map-only bundle.",
                suggested_families=["concept", "task", "reference", "topic"],
            )
        )

    glossary_usage_mode = "standalone"
    if wants_glossary_consuming_topics:
        glossary_usage_mode = "with_map_and_topics" if wants_map else "with_topics"

    topic_family = resolved_topic_family or ("glossentry" if wants_glossary else "topic")
    family_decision = FamilyDecision(
        requested=_normalize_topic_family(source_text) if _normalize_topic_family(source_text) != "auto" else None,
        inferred=inferred_family,
        resolved=topic_family,
        reason="explicit prompt family" if _normalize_topic_family(source_text) not in {"auto", "topic"} else (
            "constraint-implied family" if inferred_family else (
                "structure-implied family" if structure_family_hint else "generic topic default"
            )
        ),
        source="prompt" if _normalize_topic_family(source_text) not in {"auto", "topic"} else (
            "constraints" if inferred_family else ("structure_requirements" if structure_family_hint else "default")
        ),
        compatible_families=compatible_families,
    )

    counts: dict[str, int] = {}
    artifacts: list[ArtifactContract] = []
    if example_request and primary_construct and primary_construct.example_counts and example_construct != "keyscope":
        for kind, value in primary_construct.example_counts.items():
            if int(value) <= 0:
                continue
            counts[kind] = int(value)
            artifact_family = "map" if kind in {"ditamap", "subjectscheme"} else ("topic" if kind == "topic" else kind)
            artifacts.append(
                ArtifactContract(
                    kind=kind,
                    count=int(value),
                    label=_artifact_label(kind, int(value)),
                    topic_family=artifact_family,
                )
            )
    if example_request and example_construct == "keyscope":
        if example_shape == "unspecified":
            artifacts.append(
                ArtifactContract(
                    kind="ditamap",
                    count=0,
                    label="keyscope demo bundle",
                    topic_family="map",
                )
            )
        else:
            keyscope_map_count = 2 if example_shape == "minimal_demo" else 3
            keyscope_topic_count = 4 if example_shape == "minimal_demo" else 6
            counts["ditamap"] = keyscope_map_count
            counts["topic"] = keyscope_topic_count
            artifacts.append(
                ArtifactContract(
                    kind="ditamap",
                    count=keyscope_map_count,
                    label=f"{keyscope_map_count} DITA map{'s' if keyscope_map_count != 1 else ''}",
                    topic_family="map",
                )
            )
            artifacts.append(
                ArtifactContract(
                    kind="topic",
                    count=keyscope_topic_count,
                    label=f"{keyscope_topic_count} topic files",
                    topic_family="topic",
                )
            )
    else:
        if wants_map and "ditamap" not in counts:
            counts["ditamap"] = 1
            artifacts.append(ArtifactContract(kind="ditamap", count=1, label=_artifact_label("ditamap", 1), topic_family="map"))
    if wants_glossary and not (example_request and example_construct == "keyscope") and "glossentry" not in counts:
        counts["glossentry"] = glossary_count
        artifacts.append(
            ArtifactContract(
                kind="glossentry",
                count=glossary_count,
                label=_artifact_label("glossentry", glossary_count),
                topic_family="glossentry",
            )
        )
    if example_request and example_construct == "keyscope":
        pass
    elif example_request and primary_construct and primary_construct.example_counts:
        pass
    elif wants_glossary_consuming_topics:
        planned_topics = topic_count or 1
        counts[topic_family] = planned_topics
        artifacts.append(
            ArtifactContract(
                kind=topic_family,
                count=planned_topics,
                label=_artifact_label(topic_family, planned_topics),
                topic_family=topic_family,
            )
        )
    elif not wants_glossary and topic_family != "map":
        planned_topics = topic_count or 1
        counts[topic_family] = planned_topics
        artifacts.append(
            ArtifactContract(
                kind=topic_family,
                count=planned_topics,
                label=_artifact_label(topic_family, planned_topics),
                topic_family=topic_family,
            )
        )

    bundle_type = "single_topic"
    if xref_variety_request:
        bundle_type = "map_bundle"
    elif example_request and example_construct == "keyscope":
        bundle_type = "map_bundle"
    elif wants_glossary and wants_glossary_consuming_topics:
        bundle_type = "mixed_bundle"
    elif wants_map and wants_glossary:
        bundle_type = "mixed_bundle"
    elif wants_glossary:
        bundle_type = "glossary_pack"
    elif primary_construct and primary_construct.bundle_strategy:
        bundle_type = primary_construct.bundle_strategy
    elif wants_map:
        bundle_type = "map_bundle"
    elif counts.get(topic_family, 0) > 1:
        bundle_type = "topic_bundle"

    decomposition_count = max(
        int(counts.get(topic_family, 0) or 0),
        int(counts.get("topic", 0) or 0),
        int(counts.get("reference", 0) or 0),
        int(counts.get("task", 0) or 0),
        int(counts.get("concept", 0) or 0),
        topic_count or 1,
    )
    domain_decomposition = infer_domain_decomposition(
        text=combined,
        subject=subject,
        count=decomposition_count,
        constructs=construct_semantics,
    )

    clarification_request: ClarificationRequest | None = None
    status: str = "preview_ready"
    assumptions: list[str] = []
    family_resolved_by_construct = bool(xref_variety_request) or bool(keyed_link_requirements) or bool(structure_family_hint) or any(
        item.family_hint in {"concept", "task", "reference", "glossentry", "map"}
        or (
            item.bundle_strategy in {"topic_bundle", "map_bundle", "glossary_bundle"}
            and (example_request or topic_count is None)
        )
        for item in construct_semantics
    )
    if wants_glossary and not subject:
        status = "clarification_required"
        clarification_request = ClarificationRequest(
            missing_field="subject",
            question=f"What subject or terminology domain should the {glossary_count} glossary entr{'y' if glossary_count == 1 else 'ies'} cover?",
        )
        warnings.append("Glossary requests need a subject or domain so the generated terms are coherent.")
    elif missing_metadata_fields:
        status = "clarification_required"
        clarification_request = ClarificationRequest(
            missing_field="prolog_metadata_values",
            question=(
                "What values should I use for these prolog metadata fields: "
                + ", ".join(missing_metadata_fields)
                + "?"
            ),
        )
        warnings.append("Requested prolog metadata fields need explicit values before generation.")
    elif filename_clarification_required:
        status = "clarification_required"
        clarification_request = ClarificationRequest(
            missing_field="file_name",
            question=(
                "What exact filename should I use? Unsafe characters will be sanitized in the physical file path "
                "while the topic title can preserve the original text."
            ),
        )
        warnings.append("The prompt asks for special characters in a filename but does not provide the exact filename.")
    elif example_request and example_construct in _EXAMPLE_SHAPE_REQUIRED_CONSTRUCTS and example_shape == "unspecified":
        status = "clarification_required"
        clarification_request = ClarificationRequest(
            missing_field="example_shape",
            question=(
                f"What example shape do you want for `{example_construct}`: "
                "minimal demo or full demo?"
            ),
            options=["minimal demo", "full demo"],
        )
        warnings.append(
            f"`{example_construct}` is a map-scoped DITA construct, so I need the example bundle shape before generating it."
        )
    elif topic_family == "topic" and not family_resolved_by_construct and ((counts.get("topic", 0) > 1 or wants_map) or wants_glossary_consuming_topics):
        status = "clarification_required"
        clarification_request = ClarificationRequest(
            missing_field="topic_family",
            question=(
                f"Do you want {counts.get('topic', 1)} concept, task, reference, or generic topic files"
                f"{' with a map' if wants_map else ''}"
                f"{' that use the glossary terms' if wants_glossary_consuming_topics else ''}?"
            ),
            options=["concept", "task", "reference", "topic"],
        )
        warnings.append(
            "Generic multi-topic requests are ambiguous because the bundle shape changes between concept, task, reference, and plain topic output."
        )
    elif conflicts:
        status = "clarification_required"
        first_conflict = conflicts[0]
        options = first_conflict.suggested_families or ([topic_family] if topic_family else [])
        question = (
            f"{first_conflict.message} "
            f"Do you want to switch to {', '.join(options)} or remove the conflicting DITA requirement?"
            if options
            else first_conflict.message
        )
        clarification_request = ClarificationRequest(
            missing_field="constraint_conflict",
            question=question,
            options=options,
        )

    if glossary_usage_mode == "with_map_and_topics":
        assumptions.append("The generated map will reference both the glossary entries and the consuming topics.")
    if example_request and example_construct == "keyscope" and example_shape in {"minimal_demo", "full_demo"}:
        assumptions.append(
            "The keyscope example will be generated as a multi-file DITA map bundle with scoped keydefs and consumer topics."
        )
    elif glossary_usage_mode == "with_topics":
        assumptions.append("The generated consuming topics must use the generated glossary terms or acronyms.")
    elif wants_map and wants_glossary:
        assumptions.append("The generated map will reference the generated glossary entries.")
    elif wants_map and not wants_glossary and not inferred_family and _normalize_topic_family(source_text) in {"auto", "topic"}:
        assumptions.append("Assuming the map will include at least one supporting topic file.")
    elif topic_family == "glossentry" and not wants_map:
        assumptions.append("A glossary-focused bundle may still include a supporting map if the generator decides it improves navigation.")
    if construct_semantics:
        assumptions.append(
            "Construct-aware planning is active for: "
            + ", ".join(item.name for item in construct_semantics)
            + "."
        )
    if xref_variety_request:
        assumptions.append(
            "The cross-reference bundle will include same-topic, cross-topic, fragment-target, external resource, local non-DITA, and keyref-based xrefs."
        )
    for requirement in keyed_link_requirements:
        assumptions.append(
            f"External resource `{requirement.href}` will be defined once with `<{requirement.definition_element} keys=\"{requirement.key_name}\">` in the map and consumed with `<{requirement.consumer_element} keyref=\"{requirement.key_name}\">` in the topic."
        )
    for requirement in filename_requirements:
        if requirement.safe_name != requirement.requested_name:
            assumptions.append(
                f"Requested filename `{requirement.requested_name}` will be generated as safe filename `{requirement.safe_name}`."
            )
    if domain_decomposition and domain_decomposition.subtopics:
        assumptions.append(
            "Subject decomposition will guide topic distinctness: "
            + ", ".join(domain_decomposition.subtopics[:5])
            + ("..." if len(domain_decomposition.subtopics) > 5 else "")
        )
    for distribution in topicref_attribute_distributions:
        assumptions.append(
            f"Defaulting the first {distribution.count} generated topicref{'s' if distribution.count != 1 else ''} to @{distribution.attribute_name}=\"{distribution.attribute_value}\" unless a later prompt revision names a different subset."
        )

    if screenshot_attached:
        assumptions.append("Screenshot evidence will guide content shape during generation.")
    if reference_attached:
        assumptions.append("Reference DITA will guide compatible style and serializer decisions.")
    for requirement in structure_requirements:
        if requirement.structure_name in {"table", "simpletable"} and requirement.columns and requirement.rows:
            assumptions.append(
                f"Generated {requirement.structure_name} structures should use {requirement.columns} columns and {requirement.rows} rows where applicable."
            )
        if requirement.structure_name == "codeblock" and requirement.language:
            assumptions.append(f"Generated codeblock content should use {requirement.language.upper()} examples where applicable.")

    generation_instructions_parts = [clean_instructions] if clean_instructions else []
    if subject:
        generation_instructions_parts.append(f"Subject focus: {subject}.")
    generation_instructions_parts.append(
        f"Content mode: {'grounded' if screenshot_attached or reference_attached else 'auto_hybrid'}."
    )
    if topic_family and topic_family != "auto":
        generation_instructions_parts.append(f"Resolved topic family: {topic_family}.")
    if construct_semantics:
        generation_instructions_parts.append(
            "Construct-aware plan: "
            + "; ".join(
                f"{item.name} ({item.category or 'dita construct'})"
                + (f" -> {item.bundle_strategy.replace('_', ' ')}" if item.bundle_strategy else "")
                for item in construct_semantics
            )
            + "."
        )
    if example_request and example_construct:
        generation_instructions_parts.append(
            f"Generate a construct-true example for `{example_construct}` using the resolved `{bundle_type.replace('_', ' ')}` strategy."
        )
    if example_shape != "unspecified":
        generation_instructions_parts.append(f"Requested example shape: {example_shape.replace('_', ' ')}.")
    if required_elements:
        generation_instructions_parts.append(
            "Required DITA elements: " + ", ".join(f"<{item.name}>" for item in required_elements) + "."
        )
    if required_attributes:
        rendered_attributes = []
        for item in required_attributes:
            if item.required_values:
                rendered_attributes.append(
                    f"@{item.attribute_name}={' '.join(item.required_values)}"
                )
            else:
                rendered_attributes.append(f"@{item.attribute_name}")
        generation_instructions_parts.append(
            "Required DITA attributes: " + ", ".join(rendered_attributes) + "."
        )
    if topicref_attribute_distributions:
        generation_instructions_parts.append(
            "Required map topicref distributions: "
            + ", ".join(
                f"{item.count} topicref{'s' if item.count != 1 else ''} with @{item.attribute_name}={item.attribute_value}"
                for item in topicref_attribute_distributions
            )
            + "."
        )
    if metadata_constraints:
        generation_instructions_parts.append(
            "Required prolog metadata: "
            + ", ".join(
                f"{item.field_name}={item.value}" if item.value else item.field_name
                for item in metadata_constraints
            )
            + "."
        )
    if preferred_structures:
        generation_instructions_parts.append(
            "Preferred structures from the prompt: " + ", ".join(preferred_structures) + "."
        )
    if structure_requirements:
        generation_instructions_parts.append(
            "Structure requirements from the prompt: "
            + "; ".join(_format_structure_requirement(item) for item in structure_requirements)
            + "."
        )
    if keyed_link_requirements:
        generation_instructions_parts.append(
            "Keyed external link requirements: "
            + "; ".join(
                f"define <{item.definition_element} keys=\"{item.key_name}\" href=\"{item.href}\" scope=\"{item.scope}\" format=\"{item.format}\"> in the map and consume it with <{item.consumer_element} keyref=\"{item.key_name}\">"
                for item in keyed_link_requirements
            )
            + "."
        )
    if xref_variety_request:
        generation_instructions_parts.append(
            "Xref variety requirement: include same-topic, cross-topic, fragment-target, external HTML, local PDF, external DOC, and map-keyed xref examples."
        )
    if filename_requirements:
        generation_instructions_parts.append(
            "Filename requirements: "
            + "; ".join(
                f"requested `{item.requested_name}` -> safe physical filename `{item.safe_name}`"
                for item in filename_requirements
            )
            + "."
        )
    if domain_decomposition and domain_decomposition.subtopics:
        generation_instructions_parts.append(
            "Domain decomposition subtopics: " + ", ".join(domain_decomposition.subtopics) + "."
        )
    if glossary_usage_mode != "standalone":
        generation_instructions_parts.append(
            "Glossary linkage mode: "
            + ("glossentries plus consuming topics and a map." if glossary_usage_mode == "with_map_and_topics" else "glossentries plus consuming topics.")
        )
    if wants_map:
        generation_instructions_parts.append("Include a DITA map when generating the bundle.")

    _strip_redundant_generic_topic_required_elements(required_elements, topic_family)

    contract = DitaGenerationContract(
        status=status,  # type: ignore[arg-type]
        clarification_needed=status != "preview_ready",
        clarification_question=clarification_request.question if clarification_request else None,
        clarification_request=clarification_request,
        warnings=warnings,
        assumptions=assumptions,
        conflicts=conflicts,
        content_mode="grounded" if screenshot_attached or reference_attached else "auto_hybrid",
        bundle_type=bundle_type,
        topic_family=topic_family,
        consuming_topic_family=topic_family if glossary_usage_mode != "standalone" else None,
        subject=subject,
        counts=counts,
        artifacts=artifacts,
        expected_outputs=[item.label for item in artifacts],
        include_map=wants_map,
        glossary_usage_mode=glossary_usage_mode,  # type: ignore[arg-type]
        example_request=example_request,
        example_construct=example_construct,
        construct_scope=construct_scope,  # type: ignore[arg-type]
        example_shape=example_shape,  # type: ignore[arg-type]
        example_shape_clarification_required=bool(
            example_request and example_construct in _EXAMPLE_SHAPE_REQUIRED_CONSTRUCTS and example_shape == "unspecified"
        ),
        construct_semantics=construct_semantics,
        domain_decomposition=domain_decomposition,
        required_elements=required_elements,
        required_attributes=required_attributes,
        topicref_attribute_distributions=topicref_attribute_distributions,
        required_metadata=metadata_constraints,
        preferred_structures=preferred_structures,
        structure_requirements=structure_requirements,
        keyed_link_requirements=keyed_link_requirements,
        filename_requirements=filename_requirements,
        forbidden_structures=[],
        influence_inputs=[name for name, enabled in (("screenshot", screenshot_attached), ("reference_dita", reference_attached)) if enabled],
        family_decision=family_decision,
        execution_text=source_text,
        execution_instructions="\n".join(part for part in generation_instructions_parts if part).strip() or None,
    )
    contract.summary = _build_summary(contract)
    return contract


def build_execution_contract(contract: DitaGenerationContract | dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(contract, dict):
        contract_model = DitaGenerationContract.model_validate(contract)
    else:
        contract_model = contract
    if contract_model.status != "preview_ready":
        return None
    return contract_model.model_dump(mode="json")


def _all_xml_ids(text_by_file: dict[str, str]) -> set[str]:
    ids: set[str] = set()
    for text in text_by_file.values():
        for match in re.finditer(r'\bid\s*=\s*["\']([^"\']+)["\']', text or "", re.IGNORECASE):
            value = str(match.group(1) or "").strip()
            if value:
                ids.add(value.lower())
    return ids


def _all_file_basenames(text_by_file: dict[str, str]) -> set[str]:
    basenames: set[str] = set()
    for file_name in text_by_file:
        normalized = str(file_name or "").replace("\\", "/").split("/")[-1].lower()
        if normalized:
            basenames.add(normalized)
    return basenames


def _target_id_from_dita_reference(value: str) -> str:
    target = str(value or "").strip()
    if "#" not in target:
        return ""
    fragment = target.split("#", 1)[1]
    if "/" in fragment:
        fragment = fragment.rsplit("/", 1)[-1]
    return fragment.strip().lower()


def _href_target_file(value: str) -> str:
    target = str(value or "").strip().split("#", 1)[0].replace("\\", "/")
    return target.split("/")[-1].lower()


def _quoted_attribute_values(text: str, attr_name: str) -> list[str]:
    values: list[str] = []
    pattern = re.compile(rf'\b{re.escape(attr_name)}\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
    for match in pattern.finditer(text or ""):
        value = str(match.group(1) or "").strip()
        if value:
            values.append(value)
    return values


def _max_table_columns(text: str) -> int:
    max_columns = 0
    for row in re.findall(r"<(?:row|strow)\b[^>]*>.*?</(?:row|strow)>", text or "", flags=re.IGNORECASE | re.DOTALL):
        entry_count = len(re.findall(r"<(?:entry|stentry)\b", row, flags=re.IGNORECASE))
        max_columns = max(max_columns, entry_count)
    for cols in re.findall(r"\bcols\s*=\s*[\"'](\d+)[\"']", text or "", flags=re.IGNORECASE):
        max_columns = max(max_columns, int(cols))
    return max_columns


def _table_row_count(text: str) -> int:
    return len(re.findall(r"<(?:row|strow)\b", text or "", flags=re.IGNORECASE))


def _construct_validation_issues(
    model: DitaGenerationContract,
    text_by_file: dict[str, str],
    root_names: dict[str, str],
) -> list[str]:
    issues: list[str] = []
    bundle_text = "\n".join(text_by_file.values())
    lowered_bundle = bundle_text.lower()
    xml_ids = _all_xml_ids(text_by_file)
    file_basenames = _all_file_basenames(text_by_file)
    construct_names = {
        str(item.name or "").strip().lower()
        for item in model.construct_semantics
        if str(item.name or "").strip()
    }
    validation_rules = {
        str(rule or "").strip().lower()
        for item in model.construct_semantics
        for rule in item.validation_rules
        if str(rule or "").strip()
    }

    if "conref_target_exists" in validation_rules:
        conrefs = _quoted_attribute_values(bundle_text, "conref")
        if not conrefs:
            issues.append("The construct contract required `@conref`, but no conref attribute was generated.")
        for value in conrefs:
            target_id = _target_id_from_dita_reference(value)
            if target_id and target_id not in xml_ids:
                issues.append(f"The generated `@conref` target `{target_id}` does not resolve to an ID in the bundle.")

    if "conref_range_start_and_end_exist" in validation_rules:
        conrefs = _quoted_attribute_values(bundle_text, "conref")
        conrefends = _quoted_attribute_values(bundle_text, "conrefend")
        if not conrefs or not conrefends:
            issues.append("The construct contract required a conref range, but `@conref` and `@conrefend` were not both generated.")
        for value in [*conrefs, *conrefends]:
            target_id = _target_id_from_dita_reference(value)
            if target_id and target_id not in xml_ids:
                issues.append(f"The generated conref range target `{target_id}` does not resolve to an ID in the bundle.")

    if {"conkeyref_keydef_exists", "keyref_keydef_exists"} & validation_rules:
        key_names: set[str] = set()
        for keys_value in _quoted_attribute_values(bundle_text, "keys"):
            key_names.update(part.strip().lower() for part in keys_value.split() if part.strip())
        attr_name = "conkeyref" if "conkeyref_keydef_exists" in validation_rules else "keyref"
        references = _quoted_attribute_values(bundle_text, attr_name)
        if not references:
            issues.append(f"The construct contract required `@{attr_name}`, but it was not generated.")
        if not key_names:
            issues.append(f"The construct contract required map key definitions for `@{attr_name}`, but no `@keys` value was generated.")
        for value in references:
            key_name = str(value or "").split("/", 1)[0].strip().lower()
            if key_name and key_names and key_name not in key_names:
                issues.append(f"The generated `@{attr_name}` value `{value}` does not match any generated `@keys` value.")

    for requirement in model.keyed_link_requirements:
        key_name = str(requirement.key_name or "").strip()
        key_lower = key_name.lower()
        href = str(requirement.href or "").strip()
        scope = str(requirement.scope or "external").strip().lower()
        fmt = str(requirement.format or "html").strip().lower()
        keydef_tags = re.findall(r"<keydef\b[^>]*>", bundle_text, flags=re.IGNORECASE)
        matching_keydefs = [
            tag
            for tag in keydef_tags
            if key_lower in {part.strip().lower() for value in _quoted_attribute_values(tag, "keys") for part in value.split() if part.strip()}
        ]
        if not matching_keydefs:
            issues.append(f"The keyed external-link contract required `<keydef keys=\"{key_name}\">`, but it was not generated.")
        for tag in matching_keydefs:
            href_values = _quoted_attribute_values(tag, "href")
            scope_values = {value.lower() for value in _quoted_attribute_values(tag, "scope")}
            format_values = {value.lower() for value in _quoted_attribute_values(tag, "format")}
            if not href_values:
                issues.append(f"The generated `<keydef keys=\"{key_name}\">` is missing `@href`.")
            elif href and href_values[0] != href:
                issues.append(f"The generated `<keydef keys=\"{key_name}\">` used `@href=\"{href_values[0]}\"` instead of `{href}`.")
            if scope not in scope_values:
                issues.append(f"The generated `<keydef keys=\"{key_name}\">` must use `scope=\"{scope}\"`.")
            if fmt not in format_values:
                issues.append(f"The generated `<keydef keys=\"{key_name}\">` must use `format=\"{fmt}\"`.")

        xref_tags = re.findall(r"<xref\b[^>]*>", bundle_text, flags=re.IGNORECASE)
        if not any(key_lower in {value.lower() for value in _quoted_attribute_values(tag, "keyref")} for tag in xref_tags):
            issues.append(f"The keyed external-link contract required `<xref keyref=\"{key_name}\">`, but no consuming xref was generated.")
        for tag in xref_tags:
            href_values = _quoted_attribute_values(tag, "href")
            keyref_values = _quoted_attribute_values(tag, "keyref")
            if href_values and href_values[0].lower().startswith(("http://", "https://")):
                issues.append(
                    "The keyed external-link contract requires `@keyref` indirection; do not put a direct external `@href` on `<xref>`."
                )
            if href_values and keyref_values and key_lower in {value.lower() for value in keyref_values}:
                issues.append(f"The consuming `<xref keyref=\"{key_name}\">` must not also carry `@href`.")

    if "xref_target_exists_or_external_scope" in validation_rules:
        xrefs = re.findall(r"<xref\b[^>]*>", bundle_text, flags=re.IGNORECASE)
        if not xrefs:
            issues.append("The construct contract required `<xref>`, but no xref was generated.")
        for xref in xrefs:
            href_values = _quoted_attribute_values(xref, "href")
            if not href_values:
                continue
            scope_values = {value.lower() for value in _quoted_attribute_values(xref, "scope")}
            format_values = {value.lower() for value in _quoted_attribute_values(xref, "format")}
            if scope_values & {"external", "peer"} or format_values - {"dita"}:
                continue
            target = href_values[0]
            target_file = _href_target_file(target)
            target_id = _target_id_from_dita_reference(target)
            if target_file and target_file not in file_basenames:
                issues.append(f"The generated `<xref>` target file `{target_file}` was not generated.")
            if target_id and target_id not in xml_ids:
                issues.append(f"The generated `<xref>` target ID `{target_id}` was not generated.")

    if "ditaval_file_exists" in validation_rules or "ditavalref_references_profile" in validation_rules:
        if not any(root == "val" for root in root_names.values()):
            issues.append("The construct contract required a DITAVAL profile, but no `<val>` file was generated.")
        ditavalrefs = re.findall(r"<ditavalref\b[^>]*>", bundle_text, flags=re.IGNORECASE)
        if not ditavalrefs:
            issues.append("The construct contract required `<ditavalref>`, but no ditavalref was generated.")
        for element in ditavalrefs:
            href_values = _quoted_attribute_values(element, "href")
            if not href_values or not href_values[0].lower().endswith(".ditaval"):
                issues.append("The generated `<ditavalref>` must reference a `.ditaval` profile with `@href`.")
            format_values = _quoted_attribute_values(element, "format")
            if format_values and format_values[0].lower() != "ditaval":
                issues.append('The generated `<ditavalref>` must use `format="ditaval"` when @format is specified.')

    if "subjectscheme_root" in validation_rules or "subjectdefs_exist" in validation_rules:
        if not any(root == "subjectscheme" for root in root_names.values()):
            issues.append("The construct contract required a subject scheme map, but no `<subjectScheme>` root was generated.")
        if "<subjectdef" not in lowered_bundle:
            issues.append("The construct contract required subject definitions, but no `<subjectdef>` element was generated.")
        if "enumeration_binding_exists" in validation_rules and ("<enumerationdef" not in lowered_bundle or "<attributedef" not in lowered_bundle):
            issues.append("The construct contract required an enumeration binding, but `<enumerationdef>` and `<attributedef>` were not both generated.")

    if "mapref_target_map_exists" in validation_rules:
        maprefs = re.findall(r"<mapref\b[^>]*>", bundle_text, flags=re.IGNORECASE)
        if not maprefs:
            issues.append("The construct contract required `<mapref>`, but no mapref was generated.")
        for element in maprefs:
            href_values = _quoted_attribute_values(element, "href")
            if href_values:
                target_file = _href_target_file(href_values[0])
                if target_file and target_file not in file_basenames:
                    issues.append(f"The generated `<mapref>` target map `{target_file}` was not generated.")

    if "reltable_has_relrow_relcell_topicrefs" in validation_rules:
        for token in ("<reltable", "<relrow", "<relcell", "<topicref"):
            if token not in lowered_bundle:
                issues.append(f"The construct contract required relationship-table markup, but `{token}>` was not generated.")

    if "refsyn_inside_reference" in validation_rules:
        reference_texts = [text.lower() for name, text in text_by_file.items() if root_names.get(name) == "reference"]
        if not reference_texts or not any("<refsyn" in text for text in reference_texts):
            issues.append("The construct contract required `<refsyn>` inside a reference topic, but that structure was not generated.")

    if "codeblock_in_block_context" in validation_rules and "<codeblock" not in lowered_bundle:
        issues.append("The construct contract required `<codeblock>`, but no codeblock was generated.")
    if "codeph_in_inline_context" in validation_rules and "<codeph" not in lowered_bundle:
        issues.append("The construct contract required `<codeph>`, but no codeph was generated.")

    map_only_constructs = construct_names & _MAP_SCOPED_EXAMPLE_CONSTRUCTS
    if map_only_constructs and any(root in {"topic", "concept", "task", "reference"} for root in root_names.values()) and not any(
        root in {"map", "bookmap", "subjectscheme", "val"} for root in root_names.values()
    ):
        issues.append(
            "The construct contract requested map-scoped DITA semantics, but generation produced only standalone topic files."
        )

    return list(dict.fromkeys(issue for issue in issues if issue))


def validate_generated_bundle_against_contract(
    *,
    contract: dict[str, Any] | DitaGenerationContract | None,
    generated_files: dict[str, str],
    enforce_headers: bool = False,
) -> list[str]:
    if contract is None:
        return []
    model = contract if isinstance(contract, DitaGenerationContract) else DitaGenerationContract.model_validate(contract)
    issues: list[str] = []
    if not generated_files:
        return ["No generated DITA files were produced for the reviewed contract."]

    root_names: dict[str, str] = {}
    text_by_file = {name: text or "" for name, text in generated_files.items()}
    for file_name, text in text_by_file.items():
        match = re.search(r"<\s*(map|bookmap|concept|task|reference|topic|glossentry|subjectscheme|val)\b", text, re.IGNORECASE)
        if match:
            root_names[file_name] = str(match.group(1) or "").strip().lower()
            if enforce_headers and not has_expected_dita_header(text, root_names[file_name]):
                issues.append(
                    f"{file_name} is missing the expected XML declaration and DITA doctype header for `{root_names[file_name]}`."
                )

    map_file_count = sum(1 for root in root_names.values() if root in {"map", "bookmap"})
    map_texts = [text for name, text in text_by_file.items() if root_names.get(name) in {"map", "bookmap"}]
    if model.include_map and map_file_count == 0:
        issues.append("The reviewed contract required a DITA map, but no generated map file was found.")
    expected_map_count = int(model.counts.get("ditamap", 0) or 0)
    if expected_map_count and map_file_count != expected_map_count:
        issues.append(
            f"The reviewed contract expected {expected_map_count} map file{'s' if expected_map_count != 1 else ''}, but generated {map_file_count}."
        )

    family = model.topic_family
    glossary_files = {
        name: text
        for name, text in text_by_file.items()
        if root_names.get(name) == "glossentry"
    }
    expected_glossary_count = int(model.counts.get("glossentry", 0) or 0)
    if expected_glossary_count and len(glossary_files) != expected_glossary_count:
        issues.append(
            f"The reviewed contract expected {expected_glossary_count} `glossentry` file{'s' if expected_glossary_count != 1 else ''}, but generated {len(glossary_files)}."
        )
    for artifact in model.artifacts:
        kind = str(artifact.kind or "").strip().lower()
        if not kind:
            continue
        if kind == "ditamap":
            actual_count = map_file_count
        elif kind == "ditaval":
            actual_count = sum(1 for root in root_names.values() if root == "val")
        elif kind == "subjectscheme":
            actual_count = sum(1 for root in root_names.values() if root == "subjectscheme")
        else:
            actual_count = sum(1 for root in root_names.values() if root == kind)
        if artifact.count and actual_count != artifact.count:
            issues.append(
                f"The reviewed contract expected {artifact.count} `{kind}` file{'s' if artifact.count != 1 else ''}, but generated {actual_count}."
            )
    if family in {"concept", "task", "reference", "topic", "glossentry", "subjectscheme", "ditaval"}:
        relevant_files = {
            name: text
            for name, text in text_by_file.items()
            if root_names.get(name) == ("val" if family == "ditaval" else family)
        }
        expected_count = int(model.counts.get(family, 0) or 0)
        if expected_count and len(relevant_files) != expected_count:
            issues.append(
                f"The reviewed contract expected {expected_count} `{family}` file{'s' if expected_count != 1 else ''}, but generated {len(relevant_files)}."
            )
        if model.include_map and map_texts and expected_count:
            bundle_topic_basenames = {
                name.lower()
                for name, root in root_names.items()
                if root in {"concept", "task", "reference", "topic", "glossentry"}
            }
            distinct_href_targets = _count_distinct_topicref_hrefs_to_bundle_files(map_texts, bundle_topic_basenames)
            if distinct_href_targets > 0:
                actual_topicrefs = distinct_href_targets
            else:
                actual_topicrefs = sum(text.lower().count("<topicref") for text in map_texts)
            if actual_topicrefs != expected_count:
                issues.append(
                    f"The reviewed contract expected {expected_count} topicref{'s' if expected_count != 1 else ''} in the generated map, but found {actual_topicrefs}."
                )
    else:
        relevant_files = text_by_file

    for constraint in model.required_elements:
        token = f"<{constraint.name}".lower()
        cname = str(constraint.name or "").strip().lower()
        if constraint.scope == "artifact" and relevant_files:
            missing: list[str] = []
            for name, text in relevant_files.items():
                lowered = text.lower()
                root = root_names.get(name, "")
                if cname == "topic" and root in {"task", "concept", "reference"}:
                    continue
                if token not in lowered:
                    missing.append(name)
            if missing:
                issues.append(
                    f"The required element `<{constraint.name}>` is missing from {', '.join(missing[:4])}."
                )
        elif constraint.scope == "bundle":
            if not any(token in text.lower() for text in text_by_file.values()):
                issues.append(f"The required bundle-level element `<{constraint.name}>` was not generated.")

    for constraint in model.required_attributes:
        attr_token = f"{constraint.attribute_name}=".lower()
        if constraint.scope == "artifact" and relevant_files:
            for file_name, text in relevant_files.items():
                lowered = text.lower()
                if attr_token not in lowered:
                    issues.append(f"The required attribute `@{constraint.attribute_name}` is missing from {file_name}.")
                    continue
                for value in constraint.required_values:
                    if f'{constraint.attribute_name}="{value.lower()}"' not in lowered and f"{constraint.attribute_name}='{value.lower()}'" not in lowered:
                        issues.append(
                            f"The required value `@{constraint.attribute_name}=\"{value}\"` is missing from {file_name}."
                        )
        elif constraint.scope == "bundle":
            bundle_text = "\n".join(text_by_file.values()).lower()
            if attr_token not in bundle_text:
                issues.append(f"The required attribute `@{constraint.attribute_name}` was not generated in the bundle.")
                continue
            for value in constraint.required_values:
                if f'{constraint.attribute_name}="{value.lower()}"' not in bundle_text and f"{constraint.attribute_name}='{value.lower()}'" not in bundle_text:
                    issues.append(
                        f"The required value `@{constraint.attribute_name}=\"{value}\"` was not generated in the bundle."
                    )

    bundle_text = "\n".join(text_by_file.values())
    lowered_bundle = bundle_text.lower()
    for requirement in model.structure_requirements:
        structure_name = str(requirement.structure_name or "").strip().lower()
        if structure_name == "codeblock":
            if "<codeblock" not in lowered_bundle:
                issues.append("The reviewed contract required `<codeblock>` structures, but no codeblock was generated.")
            if requirement.language:
                outputclass_value = f"language-{requirement.language}".lower()
                if outputclass_value not in lowered_bundle:
                    issues.append(
                        f"The reviewed contract required `{requirement.language}` codeblock examples, but no `outputclass=\"{outputclass_value}\"` codeblock marker was generated."
                    )
        if structure_name in {"table", "simpletable"}:
            token = "<simpletable" if structure_name == "simpletable" else "<table"
            if token not in lowered_bundle:
                issues.append(f"The reviewed contract required `<{structure_name}>` structures, but none were generated.")
            if requirement.columns and _max_table_columns(bundle_text) < requirement.columns:
                issues.append(
                    f"The reviewed contract required {requirement.columns} table columns, but the generated tables did not show that many columns."
                )
            if requirement.rows and _table_row_count(bundle_text) < requirement.rows:
                issues.append(
                    f"The reviewed contract required {requirement.rows} table rows, but the generated tables did not show that many rows."
                )

    for metadata_constraint in model.required_metadata:
        metadata_tokens = _METADATA_XML_MARKERS.get(metadata_constraint.field_name, ())
        expected_value = str(metadata_constraint.value or "").strip().lower()
        if not relevant_files:
            issues.append(
                f"The required prolog metadata `{metadata_constraint.field_name}` could not be validated because no `{family}` files were generated."
            )
            continue
        for file_name, text in relevant_files.items():
            lowered = text.lower()
            if not any(token in lowered for token in metadata_tokens):
                issues.append(
                    f"The required prolog metadata `{metadata_constraint.field_name}` is missing from {file_name}."
                )
                continue
            if expected_value and expected_value not in lowered:
                issues.append(
                    f"The required prolog metadata value `{metadata_constraint.field_name}={metadata_constraint.value}` is missing from {file_name}."
                )

    if model.glossary_usage_mode in {"with_topics", "with_map_and_topics"}:
        non_glossary_topic_count = len(
            [
                name
                for name, root in root_names.items()
                if root in {"concept", "task", "reference", "topic"} and name not in glossary_files
            ]
        )
        if non_glossary_topic_count == 0:
            issues.append("The reviewed glossary contract required consuming topic files, but none were generated.")
        if model.glossary_usage_mode == "with_map_and_topics" and map_file_count == 0:
            issues.append("The reviewed glossary contract required a map alongside consuming topics, but no map file was generated.")

    for distribution in model.topicref_attribute_distributions:
        attr_fragment = f'{distribution.attribute_name}="{distribution.attribute_value.lower()}"'
        alt_attr_fragment = f"{distribution.attribute_name}='{distribution.attribute_value.lower()}'"
        actual_count = sum(
            text.lower().count(attr_fragment) + text.lower().count(alt_attr_fragment)
            for text in map_texts
        )
        if actual_count != distribution.count:
            issues.append(
                "The reviewed contract expected "
                f"{distribution.count} topicref{'s' if distribution.count != 1 else ''} with "
                f"`@{distribution.attribute_name}=\"{distribution.attribute_value}\"`, but found {actual_count}."
            )

    issues.extend(_construct_validation_issues(model, text_by_file, root_names))

    return list(dict.fromkeys(issue for issue in issues if issue))
