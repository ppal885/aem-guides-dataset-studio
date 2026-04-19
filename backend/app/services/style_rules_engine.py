"""Pure-Python style rule evaluator for DITA XML content.

Runs configurable rules against extracted text — NO LLM dependency.
Each rule checks a specific writing-quality heuristic recommended for
DITA technical documentation.
"""

import re
import xml.etree.ElementTree as ET
from typing import Any

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger("style_rules_engine")

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_BANNED_TERMS: dict[str, str] = {
    "click on": "click",
    "in order to": "to",
    "please": "",
    "basically": "",
    "simple": "",
    "simply": "",
}

DEFAULT_REQUIRED_TERMS: dict[str, str] = {
    "choose": "select",
}

DEFAULT_RULES_CONFIG: dict[str, Any] = {
    "sentence_length": {"enabled": True, "severity": "warning", "max_words": 25},
    "passive_voice": {"enabled": True, "severity": "warning"},
    "future_tense": {"enabled": True, "severity": "warning"},
    "banned_terms": {"enabled": True, "severity": "warning", "terms": DEFAULT_BANNED_TERMS},
    "required_terms": {"enabled": True, "severity": "info", "terms": DEFAULT_REQUIRED_TERMS},
    "heading_case": {"enabled": True, "severity": "info"},
    "step_imperative": {"enabled": True, "severity": "error"},
    "shortdesc_length": {"enabled": True, "severity": "warning", "max_words": 50},
    "list_intro": {"enabled": True, "severity": "info"},
    "pronoun_ambiguity": {"enabled": True, "severity": "warning"},
}

# Common imperative verbs used in technical documentation
IMPERATIVE_VERBS = {
    "add", "apply", "assign", "attach", "back", "browse", "build", "cancel",
    "change", "check", "choose", "clear", "click", "close", "compare",
    "complete", "configure", "confirm", "connect", "copy", "create", "cut",
    "define", "delete", "deselect", "disable", "disconnect", "do", "double-click",
    "download", "drag", "edit", "enable", "enter", "ensure", "execute",
    "exit", "expand", "export", "find", "follow", "format", "generate",
    "go", "grant", "highlight", "hold", "hover", "identify", "import",
    "include", "insert", "install", "keep", "launch", "leave", "load",
    "locate", "log", "make", "manage", "map", "mark", "merge", "minimize",
    "modify", "monitor", "move", "name", "navigate", "note", "obtain",
    "open", "paste", "pause", "perform", "place", "point", "position",
    "press", "preview", "print", "proceed", "provide", "publish", "pull",
    "push", "put", "read", "rebuild", "record", "redo", "refresh",
    "register", "release", "reload", "remove", "rename", "repeat",
    "replace", "report", "request", "reset", "resize", "resolve",
    "restart", "restore", "retrieve", "return", "review", "right-click",
    "run", "save", "scroll", "search", "select", "send", "set", "sign",
    "skip", "sort", "specify", "start", "stop", "submit", "switch",
    "take", "tap", "test", "toggle", "type", "undo", "uninstall",
    "unzip", "update", "upgrade", "upload", "use", "validate", "verify",
    "view", "wait", "write", "zoom",
}

# Passive voice auxiliary verbs
_PASSIVE_AUX = r"\b(?:is|are|was|were|been|being|be)\b"

# Past participle heuristic: word ending in -ed, -en, -wn, -ght, -ne, -un, -lt
_PAST_PARTICIPLE = (
    r"\b[a-z]+(?:ed|en|wn|ght|lt)\b"
)

_PASSIVE_RE = re.compile(
    rf"{_PASSIVE_AUX}\s+(?:\w+\s+)?{_PAST_PARTICIPLE}", re.IGNORECASE
)

_FUTURE_RE = re.compile(r"\bwill\b", re.IGNORECASE)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_SENTENCE_START_PRONOUN_RE = re.compile(
    r"^(It|This|That|They)\s", re.MULTILINE
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_config(
    base: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    """Deep-merge *overrides* into a copy of *base*."""
    import copy
    merged = copy.deepcopy(base)
    if not overrides:
        return merged
    for rule_id, rule_overrides in overrides.items():
        if rule_id in merged and isinstance(rule_overrides, dict):
            merged[rule_id].update(rule_overrides)
        else:
            merged[rule_id] = rule_overrides
    return merged


def extract_text_from_xml(xml_str: str) -> str:
    """Return concatenated text content from an XML string, stripping tags."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return xml_str  # fall back to raw text
    parts: list[str] = []
    for elem in root.iter():
        if elem.text:
            parts.append(elem.text.strip())
        if elem.tail:
            parts.append(elem.tail.strip())
    return " ".join(parts)


def _element_text(elem: ET.Element) -> str:
    """Get all text (including children) of an element."""
    return "".join(elem.itertext()).strip()


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on terminal punctuation."""
    sentences = _SENTENCE_SPLIT_RE.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


# ---------------------------------------------------------------------------
# Individual rule implementations
# ---------------------------------------------------------------------------

Violation = dict[str, str]


def _make(rule_id: str, severity: str, location: str, message: str, suggestion: str) -> Violation:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "location": location,
        "message": message,
        "suggestion": suggestion,
    }


def check_sentence_length(text: str, cfg: dict) -> list[Violation]:
    max_words = cfg.get("max_words", 25)
    severity = cfg.get("severity", "warning")
    violations: list[Violation] = []
    for sentence in _split_sentences(text):
        word_count = len(sentence.split())
        if word_count > max_words:
            violations.append(_make(
                "sentence_length", severity,
                f"sentence: \"{sentence[:80]}...\"" if len(sentence) > 80 else f"sentence: \"{sentence}\"",
                f"Sentence has {word_count} words (max {max_words}).",
                "Break into shorter sentences for readability.",
            ))
    return violations


def check_passive_voice(text: str, cfg: dict) -> list[Violation]:
    severity = cfg.get("severity", "warning")
    violations: list[Violation] = []
    for match in _PASSIVE_RE.finditer(text):
        snippet = match.group(0)
        violations.append(_make(
            "passive_voice", severity,
            f"text: \"{snippet}\"",
            f"Passive voice detected: \"{snippet}\".",
            "Rewrite in active voice for clarity.",
        ))
    return violations


def check_future_tense(text: str, cfg: dict) -> list[Violation]:
    severity = cfg.get("severity", "warning")
    violations: list[Violation] = []
    for match in _FUTURE_RE.finditer(text):
        start = max(0, match.start() - 20)
        end = min(len(text), match.end() + 20)
        context = text[start:end].strip()
        violations.append(_make(
            "future_tense", severity,
            f"text: \"...{context}...\"",
            "Future tense (\"will\") found in procedural content.",
            "Use present tense or imperative mood in DITA procedures.",
        ))
    return violations


def check_banned_terms(text: str, cfg: dict) -> list[Violation]:
    severity = cfg.get("severity", "warning")
    terms: dict[str, str] = cfg.get("terms", DEFAULT_BANNED_TERMS)
    violations: list[Violation] = []
    text_lower = text.lower()
    for banned, replacement in terms.items():
        if banned.lower() in text_lower:
            suggestion = f"Replace \"{banned}\" with \"{replacement}\"." if replacement else f"Remove \"{banned}\"."
            violations.append(_make(
                "banned_terms", severity,
                f"term: \"{banned}\"",
                f"Banned term \"{banned}\" found.",
                suggestion,
            ))
    return violations


def check_required_terms(text: str, cfg: dict) -> list[Violation]:
    severity = cfg.get("severity", "info")
    terms: dict[str, str] = cfg.get("terms", DEFAULT_REQUIRED_TERMS)
    violations: list[Violation] = []
    text_lower = text.lower()
    for wrong, correct in terms.items():
        if wrong.lower() in text_lower:
            violations.append(_make(
                "required_terms", severity,
                f"term: \"{wrong}\"",
                f"Use \"{correct}\" instead of \"{wrong}\".",
                f"Replace \"{wrong}\" with \"{correct}\".",
            ))
    return violations


def check_heading_case(root: ET.Element, cfg: dict) -> list[Violation]:
    """Check that title elements use sentence case (only first word capitalised)."""
    severity = cfg.get("severity", "info")
    violations: list[Violation] = []
    for title_elem in root.iter("title"):
        title_text = _element_text(title_elem)
        if not title_text:
            continue
        words = title_text.split()
        if len(words) < 2:
            continue
        # Check words after the first — they should be lowercase unless proper-noun-like
        title_case_count = sum(
            1 for w in words[1:]
            if w[0].isupper() and not w.isupper() and len(w) > 3
        )
        if title_case_count >= 2:
            violations.append(_make(
                "heading_case", severity,
                f"title: \"{title_text}\"",
                "Title appears to use title case.",
                "Use sentence case for DITA headings (capitalise only the first word and proper nouns).",
            ))
    return violations


def check_step_imperative(root: ET.Element, cfg: dict) -> list[Violation]:
    """In <cmd> elements the first word should be an imperative verb."""
    severity = cfg.get("severity", "error")
    violations: list[Violation] = []
    for cmd_elem in root.iter("cmd"):
        cmd_text = _element_text(cmd_elem)
        if not cmd_text:
            continue
        first_word = cmd_text.split()[0].lower().rstrip(".,;:")
        if first_word not in IMPERATIVE_VERBS:
            violations.append(_make(
                "step_imperative", severity,
                f"cmd: \"{cmd_text[:80]}\"",
                f"Step command does not start with an imperative verb (found \"{first_word}\").",
                "Start <cmd> with an imperative verb (e.g., Click, Select, Enter).",
            ))
    return violations


def check_shortdesc_length(root: ET.Element, cfg: dict) -> list[Violation]:
    max_words = cfg.get("max_words", 50)
    severity = cfg.get("severity", "warning")
    violations: list[Violation] = []
    for sd in root.iter("shortdesc"):
        sd_text = _element_text(sd)
        if not sd_text:
            continue
        word_count = len(sd_text.split())
        sentence_count = len(_split_sentences(sd_text))
        if word_count > max_words:
            violations.append(_make(
                "shortdesc_length", severity,
                f"shortdesc: \"{sd_text[:80]}...\"" if len(sd_text) > 80 else f"shortdesc: \"{sd_text}\"",
                f"Short description has {word_count} words (max {max_words}).",
                "Keep shortdesc to 1-2 sentences and under 50 words.",
            ))
        elif sentence_count > 2:
            violations.append(_make(
                "shortdesc_length", severity,
                f"shortdesc: \"{sd_text[:80]}...\"" if len(sd_text) > 80 else f"shortdesc: \"{sd_text}\"",
                f"Short description has {sentence_count} sentences (max 2).",
                "Keep shortdesc to 1-2 sentences.",
            ))
    return violations


def check_list_intro(root: ET.Element, cfg: dict) -> list[Violation]:
    """Lists (<ul>, <ol>) should be preceded by introductory text."""
    severity = cfg.get("severity", "info")
    violations: list[Violation] = []
    for tag in ("ul", "ol"):
        for list_elem in root.iter(tag):
            parent = None
            # Walk to find parent (ElementTree doesn't store parent refs)
            for p in root.iter():
                if list_elem in list(p):
                    parent = p
                    break
            if parent is None:
                continue
            children = list(parent)
            idx = children.index(list_elem)
            # Check for preceding text: either parent text (if first child)
            # or a preceding sibling like <p>
            has_intro = False
            if idx == 0 and parent.text and parent.text.strip():
                has_intro = True
            elif idx > 0:
                prev = children[idx - 1]
                if prev.tag in ("p", "context", "info") and _element_text(prev):
                    has_intro = True
                if prev.tail and prev.tail.strip():
                    has_intro = True
            if not has_intro:
                violations.append(_make(
                    "list_intro", severity,
                    f"element: <{tag}>",
                    "List has no introductory sentence.",
                    "Add a lead-in sentence before the list.",
                ))
    return violations


def check_pronoun_ambiguity(text: str, cfg: dict) -> list[Violation]:
    severity = cfg.get("severity", "warning")
    violations: list[Violation] = []
    for sentence in _split_sentences(text):
        m = _SENTENCE_START_PRONOUN_RE.match(sentence)
        if m:
            pronoun = m.group(1)
            violations.append(_make(
                "pronoun_ambiguity", severity,
                f"sentence: \"{sentence[:80]}\"",
                f"Sentence starts with ambiguous pronoun \"{pronoun}\".",
                "Replace the pronoun with a specific noun for clarity.",
            ))
    return violations


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def evaluate(
    xml_text: str,
    rules_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run all enabled rules against *xml_text* and return aggregate results.

    Parameters
    ----------
    xml_text : str
        Raw DITA XML string.
    rules_config : dict, optional
        Tenant-configurable overrides merged on top of ``DEFAULT_RULES_CONFIG``.

    Returns
    -------
    dict with keys: score, violations, summary, passed_rules, total_rules.
    """
    cfg = _merge_config(DEFAULT_RULES_CONFIG, rules_config)

    # Attempt to parse XML for element-aware rules
    root: ET.Element | None = None
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("style_rules_engine_xml_parse_error: Falling back to text-only rules")

    # Extract plain text
    plain_text = extract_text_from_xml(xml_text) if root is not None else xml_text

    all_violations: list[Violation] = []
    total_rules = 0
    passed_rules = 0

    # --- text-based rules ---
    text_rules: list[tuple[str, Any]] = [
        ("sentence_length", check_sentence_length),
        ("passive_voice", check_passive_voice),
        ("future_tense", check_future_tense),
        ("banned_terms", check_banned_terms),
        ("required_terms", check_required_terms),
        ("pronoun_ambiguity", check_pronoun_ambiguity),
    ]

    for rule_id, fn in text_rules:
        rule_cfg = cfg.get(rule_id, {})
        if not rule_cfg.get("enabled", True):
            continue
        total_rules += 1
        violations = fn(plain_text, rule_cfg)
        if violations:
            all_violations.extend(violations)
        else:
            passed_rules += 1

    # --- XML-element-aware rules (only if parse succeeded) ---
    if root is not None:
        xml_rules: list[tuple[str, Any]] = [
            ("heading_case", check_heading_case),
            ("step_imperative", check_step_imperative),
            ("shortdesc_length", check_shortdesc_length),
            ("list_intro", check_list_intro),
        ]
        for rule_id, fn in xml_rules:
            rule_cfg = cfg.get(rule_id, {})
            if not rule_cfg.get("enabled", True):
                continue
            total_rules += 1
            violations = fn(root, rule_cfg)
            if violations:
                all_violations.extend(violations)
            else:
                passed_rules += 1

    # --- Score calculation ---
    error_count = sum(1 for v in all_violations if v["severity"] == "error")
    warning_count = sum(1 for v in all_violations if v["severity"] == "warning")
    info_count = sum(1 for v in all_violations if v["severity"] == "info")

    # Deductions: errors=-10, warnings=-5, info=-1, clamped to [0, 100]
    score = max(0, 100 - error_count * 10 - warning_count * 5 - info_count)

    return {
        "score": score,
        "violations": all_violations,
        "summary": {"errors": error_count, "warnings": warning_count, "info": info_count},
        "passed_rules": passed_rules,
        "total_rules": total_rules,
    }
