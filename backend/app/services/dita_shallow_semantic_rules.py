"""
Domain-specific shallow semantics for DITA: valid XML but missing expected structure.

Rules fire only when the output (or plan/intent) indicates the relevant domain.

Summary (rule_id → meaning):
- shallow.table_alignment_prose_only — Align/cell wording in p/ul only; no table or align=.
- shallow.table_missing_tgroup — <table> without <tgroup> (non-simpletable).
- shallow.table_sparse_entries — Table with fewer than two entry cells.
- shallow.keyref_without_keydef — keyref in XML but no keydef in the dataset.
- shallow.conref_no_fragment — conref without #fragment in the URI.
- shallow.keyref_mentioned_not_modeled — Prose mentions keyref/conref/keydef but XML does not.
- shallow.glossref_without_glossentry — glossref without a glossentry topic.
- shallow.glossentry_missing_glossterm / glossdef — Incomplete glossentry.
- shallow.task_no_steps — Task without steps / steps-unordered.
- shallow.task_step_without_cmd — Steps without cmd elements.
- shallow.reference_prose_only_refbody — Reference refbody is only paragraphs.
- shallow.map_no_navigation — Map/bookmap with no topicref, mapref, keydef, reltable, etc.
- shallow.subjectscheme_no_definitions — subjectScheme without subjectdef/enumerationdef.
- shallow.schemeref_missing_href — schemeref text without href attribute.
"""
from __future__ import annotations

import re
from typing import Optional, Set

from app.core.schemas_dita_pipeline import GenerationPlan, IntentRecord, SemanticViolation

# --- Domain activation (output or plan/intent suggests this DITA concern) ---


def _plan_wants_table(plan: GenerationPlan) -> bool:
    names = {c.name.lower() for c in (plan.required_constructs or [])}
    return bool(names & {"table", "simpletable", "tgroup", "entry", "colspec"})


def _intent_wants_table_alignment(intent: Optional[IntentRecord]) -> bool:
    if not intent:
        return False
    if "table_alignment" in (intent.anti_fallback_signals or []):
        return True
    pats = intent.required_dita_patterns or []
    return "table" in pats or "simpletable" in pats


def _active_table_alignment(
    combined_lower: str,
    counts: dict[str, int],
    plan: GenerationPlan,
    intent: Optional[IntentRecord],
) -> bool:
    if _intent_wants_table_alignment(intent) or _plan_wants_table(plan):
        return True
    if counts.get("table", 0) + counts.get("simpletable", 0) > 0:
        return True
    # Prose about alignment + table vocabulary without yet having a table (still validate)
    if not any(
        t in combined_lower
        for t in (
            "align",
            "alignment",
            "colspec",
            "text alignment",
            "cell alignment",
            "justify",
            "tgroup",
        )
    ):
        return False
    return any(
        t in combined_lower
        for t in ("table", "entry", "row", "cell", "column", "thead", "tbody")
    )


def _active_keyref_conref(combined_lower: str, counts: dict[str, int], intent: Optional[IntentRecord]) -> bool:
    if counts.get("keydef", 0) or counts.get("keyref", 0):
        return True
    # attributes keyref= conref= conkeyref=
    if re.search(r"\bkeyref\s*=", combined_lower) or re.search(r"\bconref\s*=", combined_lower):
        return True
    if "conkeyref" in combined_lower or "conrefend" in combined_lower:
        return True
    if intent and "keyref" in (intent.required_dita_patterns or []):
        return True
    return False


def _active_glossary(combined_lower: str, counts: dict[str, int], intent: Optional[IntentRecord]) -> bool:
    if counts.get("glossentry", 0) or counts.get("glossref", 0) or counts.get("glossgroup", 0):
        return True
    if intent and getattr(intent, "content_intent", None) == "glossary":
        return True
    if intent and "glossary" in (intent.required_dita_patterns or []):
        return True
    return "glossentry" in combined_lower or "glossref" in combined_lower


def _active_task(counts: dict[str, int], plan: GenerationPlan, intent: Optional[IntentRecord]) -> bool:
    if counts.get("task", 0) > 0:
        return True
    if (plan.topic_type or "").lower() == "task":
        return True
    if intent and intent.dita_topic_type_guess == "task":
        return True
    if intent and intent.content_intent == "task_procedure":
        return True
    return False


def _active_reference(counts: dict[str, int], plan: GenerationPlan, intent: Optional[IntentRecord]) -> bool:
    if counts.get("reference", 0) > 0:
        return True
    if (plan.topic_type or "").lower() == "reference":
        return True
    if intent and intent.dita_topic_type_guess == "reference":
        return True
    if intent and intent.content_intent == "reference_material":
        return True
    return False


def _active_map(counts: dict[str, int], plan: GenerationPlan, intent: Optional[IntentRecord]) -> bool:
    if counts.get("map", 0) > 0 or counts.get("bookmap", 0) > 0:
        return True
    if (plan.topic_type or "").lower() in ("map_only", "map"):
        return True
    if intent and intent.dita_topic_type_guess == "map_only":
        return True
    if intent and intent.content_intent == "map_hierarchy":
        return True
    return False


def _active_subject_scheme(combined_lower: str, counts: dict[str, int]) -> bool:
    for k in (
        "subjectscheme",
        "subjectdef",
        "enumerationdef",
        "schemeref",
        "hasinstance",
        "attributedef",
    ):
        if counts.get(k, 0) > 0:
            return True
    return any(
        x in combined_lower
        for x in (
            "<subjectscheme",
            "<subjectdef",
            "<enumerationdef",
            "subject scheme",
            "controlled values",
        )
    )


# --- Shallow checks per domain ---


def _viol_table_alignment(combined: str, combined_lower: str, counts: dict[str, int]) -> list[SemanticViolation]:
    out: list[SemanticViolation] = []
    table_n = counts.get("table", 0) + counts.get("simpletable", 0)
    has_align_attr = bool(
        re.search(r'align\s*=\s*["\']?(?:left|right|center|justify|char)', combined_lower)
    )
    lists_align_values = bool(
        re.search(
            r"(?:<p>|<li>)[^<]{0,200}(?:left|right|center|justify|char|-dita-use-conref-target)",
            combined_lower,
        )
    )

    if lists_align_values and table_n == 0 and not has_align_attr:
        out.append(
            SemanticViolation(
                rule_id="shallow.table_alignment_prose_only",
                severity="error",
                message="Table alignment content appears as prose or list only—no <table> and no align= on colspec/entry.",
                repair_hint="Add a DITA <table> with tgroup/row/entry or set align on colspec/entry; avoid ul/p-only value lists.",
            )
        )

    if table_n > 0 and counts.get("tgroup", 0) == 0 and counts.get("simpletable", 0) == 0:
        out.append(
            SemanticViolation(
                rule_id="shallow.table_missing_tgroup",
                severity="warn",
                message="Found <table> but no <tgroup> (unusual for reference DITA tables).",
                repair_hint="Wrap columns in <tgroup cols=\"...\"> with colspec, thead/tbody, row, entry.",
            )
        )

    if table_n > 0 and counts.get("entry", 0) < 2:
        out.append(
            SemanticViolation(
                rule_id="shallow.table_sparse_entries",
                severity="warn",
                message="Table present but fewer than two <entry> elements—likely not a real reference grid.",
                repair_hint="Use at least two rows with entries demonstrating alignment or values.",
            )
        )

    return out


def _viol_keyref_conref(combined_lower: str, counts: dict[str, int]) -> list[SemanticViolation]:
    out: list[SemanticViolation] = []
    has_key_use = bool(re.search(r"\bkeyref\s*=\s*[\"'][^\"']+[\"']", combined_lower))
    has_con_use = bool(re.search(r"\bconref\s*=\s*[\"'][^\"']+[\"']", combined_lower))
    keydefs = counts.get("keydef", 0)

    if has_key_use and keydefs == 0:
        out.append(
            SemanticViolation(
                rule_id="shallow.keyref_without_keydef",
                severity="warn",
                message="keyref/conkeyref used but no <keydef> found in the dataset.",
                repair_hint="Add a map (or root map) with <keydef keys=\"...\" href=\"...\"/> for each key you reference.",
            )
        )

    if has_con_use:
        # conref without a plausible target fragment (very shallow)
        if not re.search(r"conref\s*=\s*[\"'][^\"']*#", combined_lower):
            out.append(
                SemanticViolation(
                    rule_id="shallow.conref_no_fragment",
                    severity="warn",
                    message="conref attribute present but no fragment id (#topic/element) in values—may not resolve.",
                    repair_hint="Use conref=\"path/to.dita#topicid/elementid\" (or equivalent) for addressable reuse.",
                )
            )

    mentions_keys_in_prose = bool(
        re.search(
            r"\b(?:keyref|keydef|keyscope|conref)\b",
            combined_lower,
        )
    )
    if mentions_keys_in_prose and not has_key_use and not has_con_use and keydefs == 0:
        out.append(
            SemanticViolation(
                rule_id="shallow.keyref_mentioned_not_modeled",
                severity="warn",
                message="Text mentions keyref/keydef/conref but XML does not show keyref/conref attributes or keydefs.",
                repair_hint="Model the scenario: keydef on a map and keyref on topicref or inline ph elements.",
            )
        )

    return out


def _viol_glossary(counts: dict[str, int]) -> list[SemanticViolation]:
    out: list[SemanticViolation] = []
    ge = counts.get("glossentry", 0)
    if counts.get("glossref", 0) > 0 and ge == 0:
        out.append(
            SemanticViolation(
                rule_id="shallow.glossref_without_glossentry",
                severity="warn",
                message="glossref present but no glossentry topic in output—glossary chain incomplete.",
                repair_hint="Add glossentry topics (or glossgroup) and point glossref href to them.",
            )
        )
    if ge == 0:
        return out
    if counts.get("glossterm", 0) < ge:
        out.append(
            SemanticViolation(
                rule_id="shallow.glossentry_missing_glossterm",
                severity="error",
                message="glossentry without matching <glossterm> coverage.",
                repair_hint="Each glossentry should include <glossterm> and <glossdef> (or nested topic pattern per your DITA version).",
            )
        )
    if counts.get("glossdef", 0) == 0:
        out.append(
            SemanticViolation(
                rule_id="shallow.glossentry_missing_glossdef",
                severity="error",
                message="glossentry present but no <glossdef>—not a usable glossary entry.",
                repair_hint="Add <glossdef> with definition content inside each glossentry.",
            )
        )
    return out


def _viol_task(counts: dict[str, int]) -> list[SemanticViolation]:
    out: list[SemanticViolation] = []
    if counts.get("task", 0) == 0:
        return out
    steps = counts.get("steps", 0) + counts.get("steps-unordered", 0)
    if steps == 0:
        out.append(
            SemanticViolation(
                rule_id="shallow.task_no_steps",
                severity="error",
                message="Task topic without <steps> or <steps-unordered>—procedural shell only.",
                repair_hint="Add ordered or unordered steps with <step> and <cmd> (and info/choices as needed).",
            )
        )
        return out

    cmd_n = counts.get("cmd", 0)
    step_n = counts.get("step", 0)
    if step_n > 0 and cmd_n == 0:
        out.append(
            SemanticViolation(
                rule_id="shallow.task_step_without_cmd",
                severity="warn",
                message="Steps present but no <cmd> elements—task may be narrative, not actionable.",
                repair_hint="Use <step><cmd>...</cmd></step> for each user action.",
            )
        )
    return out


def _viol_reference(counts: dict[str, int]) -> list[SemanticViolation]:
    out: list[SemanticViolation] = []
    if counts.get("reference", 0) == 0:
        return out
    refbody = counts.get("refbody", 0)
    if refbody == 0:
        return out
    props = counts.get("properties", 0)
    st = counts.get("simpletable", 0) + counts.get("table", 0)
    sect = counts.get("section", 0)
    p_n = counts.get("p", 0)
    if props == 0 and st == 0 and sect < 2 and p_n >= 4:
        out.append(
            SemanticViolation(
                rule_id="shallow.reference_prose_only_refbody",
                severity="warn",
                message="Reference topic refbody is paragraph-heavy with no properties or table—weak reference pattern.",
                repair_hint="Add <properties>/<property> for API-like metadata, or a reference <simpletable>/<table> for attributes.",
            )
        )
    return out


def _viol_map(counts: dict[str, int]) -> list[SemanticViolation]:
    out: list[SemanticViolation] = []
    map_n = counts.get("map", 0) + counts.get("bookmap", 0)
    if map_n == 0:
        return out
    nav = (
        counts.get("topicref", 0)
        + counts.get("mapref", 0)
        + counts.get("topichead", 0)
        + counts.get("topicgroup", 0)
        + counts.get("keydef", 0)
        + counts.get("reltable", 0)
        + counts.get("chapter", 0)
        + counts.get("part", 0)
        + counts.get("appendices", 0)
        + counts.get("frontmatter", 0)
        + counts.get("backmatter", 0)
    )
    if nav == 0:
        out.append(
            SemanticViolation(
                rule_id="shallow.map_no_navigation",
                severity="error",
                message="Map or bookmap has no topicref, mapref, topichead, keydef, or reltable—empty shell.",
                repair_hint="Add topicrefs (or keydefs for key-only maps) so the map structures content.",
            )
        )
    return out


def _viol_subject_scheme(combined_lower: str, counts: dict[str, int]) -> list[SemanticViolation]:
    out: list[SemanticViolation] = []
    ss = counts.get("subjectscheme", 0)
    if ss == 0 and "<subjectscheme" not in combined_lower:
        return out
    subjdef = counts.get("subjectdef", 0)
    enumdef = counts.get("enumerationdef", 0)
    if ss > 0 and subjdef == 0 and enumdef == 0:
        out.append(
            SemanticViolation(
                rule_id="shallow.subjectscheme_no_definitions",
                severity="error",
                message="subjectScheme map without subjectdef or enumerationdef—no taxonomy or controlled values.",
                repair_hint="Add <subjectdef> hierarchy and/or <enumerationdef> for attribute value bindings.",
            )
        )
    if "schemeref" in combined_lower and not re.search(r"schemeref\s*=\s*[\"'][^\"']+[\"']", combined_lower):
        out.append(
            SemanticViolation(
                rule_id="shallow.schemeref_missing_href",
                severity="warn",
                message="schemeref mentioned but no href attribute found.",
                repair_hint="Use schemeref href=\"...\" to link to the subject scheme map.",
            )
        )
    return out


def evaluate_domain_shallow_rules(
    combined: str,
    combined_lower: str,
    counts: dict[str, int],
    plan: GenerationPlan,
    intent: Optional[IntentRecord],
    *,
    domains: Optional[Set[str]] = None,
) -> list[SemanticViolation]:
    """
    Run shallow semantic rules for DITA domains. If ``domains`` is set, only those
    domain keys run: table_alignment, keyref_conref, glossary, task, reference, map, subject_scheme.
    """
    all_keys = {
        "table_alignment",
        "keyref_conref",
        "glossary",
        "task",
        "reference",
        "map",
        "subject_scheme",
    }
    active = domains if domains is not None else all_keys
    violations: list[SemanticViolation] = []

    if "table_alignment" in active and _active_table_alignment(combined_lower, counts, plan, intent):
        violations.extend(_viol_table_alignment(combined, combined_lower, counts))

    if "keyref_conref" in active and _active_keyref_conref(combined_lower, counts, intent):
        violations.extend(_viol_keyref_conref(combined_lower, counts))

    if "glossary" in active and _active_glossary(combined_lower, counts, intent):
        violations.extend(_viol_glossary(counts))

    if "task" in active and _active_task(counts, plan, intent):
        violations.extend(_viol_task(counts))

    if "reference" in active and _active_reference(counts, plan, intent):
        violations.extend(_viol_reference(counts))

    if "map" in active and _active_map(counts, plan, intent):
        violations.extend(_viol_map(counts))

    if "subject_scheme" in active and _active_subject_scheme(combined_lower, counts):
        violations.extend(_viol_subject_scheme(combined_lower, counts))

    return violations
