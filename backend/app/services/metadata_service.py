"""Entity extraction and AEM Guides domain classification for QA copilot."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.tool_models import ExtractedEntities


@dataclass(frozen=True)
class DomainDefinition:
    canonical: str
    aliases: tuple[str, ...]
    output_type: str | None = None
    editor_type: str | None = None


DOMAIN_DEFINITIONS: tuple[DomainDefinition, ...] = (
    DomainDefinition("conkeyref", ("conkeyref", "con keyref", "con-keyref")),
    DomainDefinition("conref", ("conref", "content reference", "content refs")),
    DomainDefinition("keyref", ("keyref", "key ref", "key-reference")),
    DomainDefinition("ditaval", ("ditaval", "dita val", "conditions", "conditional processing")),
    DomainDefinition("native pdf", ("native pdf", "pdf template", "pdf publish"), output_type="Native PDF"),
    DomainDefinition("publishing", ("publishing", "publish", "output generation", "rendition"), output_type="Publishing"),
    DomainDefinition("sites", ("sites", "aem sites", "site output"), output_type="AEM Sites"),
    DomainDefinition("baseline", ("baseline", "baselines", "version baseline")),
    DomainDefinition("translation", ("translation", "localization", "l10n")),
    DomainDefinition("review", ("review", "review workflow")),
    DomainDefinition("web editor", ("web editor", "new editor", "editor", "authoring ui"), editor_type="Web Editor"),
    DomainDefinition("uuid", ("uuid", "guid", "identifier")),
    DomainDefinition("metadata", ("metadata", "properties", "prolog")),
    DomainDefinition("chunking", ("chunking", "chunk", "chunks")),
    DomainDefinition("glossary", ("glossary", "glossentry", "abbreviation")),
    DomainDefinition("bookmap", ("bookmap", "book map")),
    DomainDefinition("image handling", ("image handling", "image paste", "paste image", "images", "image", "asset reference")),
    DomainDefinition("rendition issues", ("rendition issues", "rendition", "output mismatch"), output_type="Publishing"),
)

_CONNECTOR_WORDS = {
    "ke",
    "ka",
    "ki",
    "for",
    "customer",
    "client",
    "jira",
    "this",
    "is",
    "related",
    "old",
    "bugs",
    "bug",
    "issues",
    "tickets",
    "ticket",
    "automation",
    "scenario",
    "scenarios",
    "uac",
    "points",
    "point",
    "escalation",
    "escalations",
    "se",
    "mein",
    "me",
    "in",
    "dikhao",
    "karo",
    "banao",
    "find",
    "previous",
    "similar",
    "last",
    "past",
    "batao",
    "show",
    "tell",
    "me",
    "the",
}

_FEATURE_STOP_WORDS = {
    *_CONNECTOR_WORDS,
    "aur",
    "and",
    "old",
    "latest",
    "purane",
    "purana",
    "previous",
    "similar",
    "regression",
    "regressions",
    "day",
    "days",
    "din",
    "week",
    "weeks",
    "month",
    "months",
    "quarter",
    "year",
    "years",
    "environment",
    "env",
    "cloud",
    "on",
    "prem",
    "on prem",
    "premise",
    "onprem",
    "stage",
    "staging",
    "prod",
    "production",
    "local",
    "dev",
}

_LEADING_QUERY_WORDS = {
    "please",
    "pls",
    "kindly",
    "mujhe",
    "mere",
    "show",
    "tell",
    "find",
    "fetch",
    "list",
    "can",
    "could",
    "would",
    "you",
    "do",
}

_CUSTOMER_FEATURE_PATTERN = re.compile(
    r"(?P<customer>[A-Za-z][A-Za-z0-9&._'\-\s]{1,80}?)\s+"
    r"(?:(?:customer|client)\s+)?(?:ke|ka|ki)\s+"
    r"(?P<feature>[A-Za-z0-9][A-Za-z0-9&._'/\-\s]{0,120})",
    flags=re.IGNORECASE,
)

_EXPLICIT_CUSTOMER_FEATURE_PATTERN = re.compile(
    r"(?:customer|client)\s+(?P<customer>[A-Za-z][A-Za-z0-9&._'\-\s]{1,80}?)\s+"
    r"(?:ke|ka|ki|for|related\s+to)\s+"
    r"(?P<feature>[A-Za-z0-9][A-Za-z0-9&._'/\-\s]{0,120})",
    flags=re.IGNORECASE,
)

_JIRA_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b", flags=re.IGNORECASE)
_CONTEXT_ONLY_DOMAINS = {"web editor"}
_OUTPUT_CONTEXT_DOMAINS = {"publishing", "sites", "rendition issues"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _contains_key_phrase(text_key: str, needle: str) -> bool:
    needle_key = _norm_key(needle)
    if not needle_key:
        return False
    return f" {needle_key} " in f" {text_key} "


class MetadataService:
    """Extract customer/domain intent without hardcoding customer names."""

    def classify_domain(self, message: str, *, preferred_text: str | None = None) -> DomainDefinition | None:
        preferred_matches = self._domain_matches(preferred_text or "")
        if preferred_matches:
            return self._select_domain(preferred_matches)
        return self._select_domain(self._domain_matches(message))

    def _domain_matches(self, message: str) -> list[tuple[DomainDefinition, str, int]]:
        haystack = f" {_norm_key(message)} "
        if not haystack.strip():
            return []
        out: list[tuple[DomainDefinition, str, int]] = []
        aliases: list[tuple[str, DomainDefinition]] = []
        for definition in DOMAIN_DEFINITIONS:
            aliases.extend((alias, definition) for alias in definition.aliases)
        for alias, definition in aliases:
            needle = f" {_norm_key(alias)} "
            idx = haystack.find(needle)
            if idx >= 0:
                out.append((definition, alias, idx))
        return out

    def _select_domain(self, matches: list[tuple[DomainDefinition, str, int]]) -> DomainDefinition | None:
        if not matches:
            return None
        unique: dict[str, tuple[DomainDefinition, str, int]] = {}
        for definition, alias, idx in matches:
            prev = unique.get(definition.canonical)
            if prev is None or len(alias) > len(prev[1]) or idx < prev[2]:
                unique[definition.canonical] = (definition, alias, idx)
        candidates = list(unique.values())
        concrete = [m for m in candidates if m[0].canonical not in _CONTEXT_ONLY_DOMAINS]
        if concrete:
            candidates = concrete
        entity_first = [
            m
            for m in candidates
            if m[0].canonical not in _OUTPUT_CONTEXT_DOMAINS
            and m[0].canonical not in _CONTEXT_ONLY_DOMAINS
        ]
        if entity_first:
            candidates = entity_first
        candidates.sort(key=lambda item: (item[2], -len(item[1])))
        return candidates[0][0]

    def extract_entities(self, message: str) -> ExtractedEntities:
        msg = _norm(message)
        relation_customer, relation_feature = self._extract_customer_feature_relation(msg)
        standalone_feature = None if relation_feature else self._extract_standalone_feature_phrase(msg)
        preferred_feature = relation_feature or standalone_feature
        domain = self.classify_domain(msg, preferred_text=preferred_feature)
        feature = domain.canonical if domain else preferred_feature
        customer = relation_customer or self._extract_customer(msg, feature)
        request_types = self._extract_request_types(msg)
        issue_type = self._extract_issue_type(msg)
        environment = self._extract_environment(msg)
        editor_type = self._extract_editor_type(msg, domain)
        output_type = self._extract_output_type(msg, domain)
        time_window_days = self._extract_time_window_days(msg)
        source_jira_key = self._extract_source_jira_key(msg)
        escalation_only = self._extract_escalation_only(msg)
        notes = self._extract_notes(msg, source_jira_key)

        confidence = 0.35
        if customer:
            confidence += 0.25
        if feature:
            confidence += 0.25
        if request_types:
            confidence += 0.1
        if issue_type or environment or time_window_days or source_jira_key or escalation_only:
            confidence += 0.05

        return ExtractedEntities(
            customer=customer,
            feature=feature,
            request_type=request_types or ["qa_intelligence"],
            issue_type=issue_type,
            environment=environment,
            editor_type=editor_type,
            output_type=output_type,
            time_window_days=time_window_days,
            source_jira_key=source_jira_key,
            escalation_only=escalation_only,
            confidence=min(confidence, 0.98),
            extraction_path="rules",
            notes=notes,
        )

    def _extract_customer_feature_relation(self, message: str) -> tuple[str | None, str | None]:
        """Parse dynamic Hinglish patterns like '<customer> ke <feature> related bugs'."""
        for pattern in (_EXPLICIT_CUSTOMER_FEATURE_PATTERN, _CUSTOMER_FEATURE_PATTERN):
            match = pattern.search(message)
            if not match:
                continue
            raw_feature = match.group("feature")
            feature = self._clean_feature_candidate(raw_feature)
            customer = self._clean_customer_candidate(match.group("customer"), feature)
            if customer and feature:
                return customer, feature
        return None, None

    def _extract_standalone_feature_phrase(self, message: str) -> str | None:
        patterns = (
            r"(?:mein|me|in)\s+(?P<feature>[A-Za-z0-9][A-Za-z0-9&._'/\-\s]{0,100}?)\s+related\b",
            r"(?P<feature>[A-Za-z0-9][A-Za-z0-9&._'/\-\s]{0,100}?)\s+related\b",
            r"(?P<feature>[A-Za-z0-9][A-Za-z0-9&._'/\-\s]{0,100}?)\s+ke\s+(?:old|purane|previous|related|bugs?|issues?|regressions?|uac|automation)\b",
            r"(?P<feature>[A-Za-z0-9][A-Za-z0-9&._'/\-\s]{0,100}?)\s+(?:bugs?|issues?|regressions?|tickets?)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = self._clean_feature_candidate(match.group("feature"))
            if candidate:
                return candidate
        return None

    def _extract_customer(self, message: str, feature: str | None) -> str | None:
        patterns = (
            r"(?P<customer>[A-Za-z][A-Za-z0-9&._\-\s]{1,80}?)\s+(?:ke|ka|ki)\s+",
            r"(?:customer|client)\s+(?P<customer>[A-Za-z][A-Za-z0-9&._\-\s]{1,80}?)(?:\s+(?:ke|ka|ki|for|related)|$)",
        )
        for pat in patterns:
            match = re.search(pat, message, flags=re.IGNORECASE)
            if match:
                cleaned = self._clean_customer_candidate(match.group("customer"), feature)
                if cleaned:
                    return cleaned

        domain_aliases = [alias for d in DOMAIN_DEFINITIONS for alias in d.aliases]
        alias_pattern = "|".join(re.escape(a) for a in sorted(domain_aliases, key=len, reverse=True))
        match = re.search(
            rf"\b(?P<customer>[A-Z][A-Za-z0-9&._\-]{{1,40}})\b(?:\s+\w+){{0,3}}\s+(?:{alias_pattern})\b",
            message,
            flags=re.IGNORECASE,
        )
        if match:
            if _norm_key(match.group("customer")) in {"new", "web", "map", "xml"}:
                return None
            return self._clean_customer_candidate(match.group("customer"), feature)
        return None

    def _clean_customer_candidate(self, raw: str, feature: str | None) -> str | None:
        raw = _norm(raw)
        if not raw:
            return None
        words = [w for w in re.split(r"\s+", raw) if w]
        kept: list[str] = []
        feature_key = _norm_key(feature or "")
        for word in words:
            key = _norm_key(word)
            if not kept and key in _LEADING_QUERY_WORDS:
                continue
            if not key or key in _CONNECTOR_WORDS or key == feature_key:
                continue
            kept.append(word.strip(".,:;\"'()[]{}"))
        candidate = _norm(" ".join(kept)).strip(".,:;\"'")
        if not candidate:
            return None
        if _norm_key(candidate) in _CONNECTOR_WORDS:
            return None
        if _JIRA_KEY_PATTERN.fullmatch(candidate):
            return None
        if self.classify_domain(candidate):
            return None
        return candidate[:80]

    def _clean_feature_candidate(self, raw: str) -> str | None:
        raw = _norm(raw)
        if not raw:
            return None
        words: list[str] = []
        for word in re.split(r"\s+", raw):
            cleaned = word.strip(".,:;\"'()[]{}")
            key = _norm_key(cleaned)
            if not key:
                continue
            if key in _FEATURE_STOP_WORDS:
                break
            words.append(cleaned)
        candidate = _norm(" ".join(words)).strip(".,:;\"'")
        if not candidate:
            return None
        if _norm_key(candidate) in _FEATURE_STOP_WORDS:
            return None
        if _JIRA_KEY_PATTERN.fullmatch(candidate):
            return None
        return candidate[:80]

    def _extract_request_types(self, message: str) -> list[str]:
        text = _norm_key(message)
        rules = {
            "historical_bug_search": ("old bug", "bugs", "bug", "issues", "tickets", "regression", "regressions"),
            "automation_generation": ("automation", "scenario", "scenarios", "behave", "gherkin", "test cases"),
            "uac_generation": ("uac", "uac points", "discussion", "acceptance", "sign off"),
            "pattern_analysis": ("pattern", "patterns", "root cause", "common"),
            "similar_issue_search": ("similar", "related", "previous"),
            "customer_escalation_search": ("customer escalation", "customer escalations", "escalation", "escalations"),
        }
        out: list[str] = []
        for req, needles in rules.items():
            if any(_contains_key_phrase(text, n) for n in needles):
                out.append(req)
        return out

    def _extract_issue_type(self, message: str) -> str | None:
        text = _norm_key(message)
        issue_types = {
            "Bug": ("bug", "bugs", "defect", "regression", "regressions", "issue", "issues"),
            "Story": ("story", "stories", "feature request"),
            "Task": ("task", "tasks"),
            "Epic": ("epic",),
        }
        for issue_type, needles in issue_types.items():
            if any(_contains_key_phrase(text, n) for n in needles):
                return issue_type
        return None

    def _extract_environment(self, message: str) -> str | None:
        text = _norm_key(message)
        envs = {
            "Cloud": ("cloud", "aem cloud", "aemaacs", "aem as a cloud service", "cs"),
            "On-Prem": ("on prem", "on premise", "onprem", "ams"),
            "Stage": ("stage", "staging"),
            "Production": ("prod", "production"),
            "Local": ("local", "dev"),
        }
        for env, needles in envs.items():
            if any(_contains_key_phrase(text, n) for n in needles):
                return env
        return None

    def _extract_editor_type(self, message: str, domain: DomainDefinition | None) -> str | None:
        text = _norm_key(message)
        if "new editor" in text:
            return "New Editor"
        if "web editor" in text or "authoring ui" in text:
            return "Web Editor"
        if "map editor" in text:
            return "Map Editor"
        if "xml editor" in text:
            return "XML Editor"
        return domain.editor_type if domain else None

    def _extract_output_type(self, message: str, domain: DomainDefinition | None) -> str | None:
        text = _norm_key(message)
        if "native pdf" in text:
            return "Native PDF"
        if "pdf" in text:
            return "PDF"
        if "publishing" in text or "publish" in text or "output generation" in text:
            return "Publishing"
        if "sites" in text or "aem sites" in text:
            return "AEM Sites"
        return domain.output_type if domain else None

    def _extract_time_window_days(self, message: str) -> int | None:
        text = _norm_key(message)
        patterns = (
            (r"\b(?:last|past|previous|pichle)\s+(?P<count>\d{1,4})\s+(?P<unit>days?|din|weeks?|months?|years?)\b", 1),
            (r"\b(?P<count>\d{1,4})\s+(?P<unit>days?|din|weeks?|months?|years?)\s+(?:old|window|lookback)\b", 1),
        )
        for pattern, _ in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            count = int(match.group("count"))
            unit = match.group("unit")
            multiplier = 1
            if unit.startswith("week"):
                multiplier = 7
            elif unit.startswith("month"):
                multiplier = 30
            elif unit.startswith("year"):
                multiplier = 365
            return min(count * multiplier, 3650)
        if _contains_key_phrase(text, "last quarter"):
            return 90
        return None

    def _extract_source_jira_key(self, message: str) -> str | None:
        match = _JIRA_KEY_PATTERN.search(message or "")
        return match.group(1).upper() if match else None

    def _extract_escalation_only(self, message: str) -> bool:
        text = _norm_key(message)
        return any(
            _contains_key_phrase(text, phrase)
            for phrase in (
                "customer escalation",
                "customer escalations",
                "escalation",
                "escalations",
                "sev 1",
                "sev1",
                "p1 escalation",
            )
        )

    def _extract_notes(self, message: str, source_jira_key: str | None) -> list[str]:
        text = _norm_key(message)
        notes: list[str] = []
        if not source_jira_key and (
            _contains_key_phrase(text, "this jira")
            or _contains_key_phrase(text, "is jira")
            or _contains_key_phrase(text, "current jira")
        ):
            notes.append("query_references_current_jira_without_explicit_key")
        return notes
