"""Semantic validation: recipe/plan compliance + shallow paragraph-only detection."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

from app.core.schemas_dita_pipeline import GenerationPlan, IntentRecord, SemanticValidationReport, SemanticViolation
from app.generator.recipe_manifest import RecipeSpec
from app.services.dita_shallow_semantic_rules import evaluate_domain_shallow_rules
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def _local_name(tag: str) -> str:
    if not tag:
        return ""
    t = tag.split("}")[-1] if "}" in tag else tag
    return t.split(":")[-1].lower()


def _count_elements(xml_str: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        root = ET.fromstring(xml_str)
        for el in root.iter():
            name = _local_name(el.tag)
            counts[name] = counts.get(name, 0) + 1
    except ET.ParseError:
        pass
    return counts


def _gather_topic_xml_from_dir(scenario_dir: Path) -> tuple[str, dict[str, int]]:
    """Concatenate .dita / .xml topic-like files and aggregate element counts."""
    combined = ""
    total_counts: dict[str, int] = {}
    for path in sorted(scenario_dir.rglob("*")):
        if not path.is_file():
            continue
        suf = path.suffix.lower()
        if suf not in (".dita", ".xml", ".ditamap"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        combined += "\n" + text
        for k, v in _count_elements(
            re.sub(r"<\?xml[^?]*\?>", "", text, flags=re.I)[:500000]
        ).items():
            total_counts[k] = total_counts.get(k, 0) + v
    return combined, total_counts


def _gather_from_bytes_dict(files: Dict[str, bytes]) -> tuple[str, dict[str, int]]:
    combined = ""
    total_counts: dict[str, int] = {}
    for path, content in files.items():
        p = str(path).lower()
        if not p.endswith((".dita", ".xml", ".ditamap")):
            continue
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            continue
        combined += "\n" + text
        body = re.sub(r"<\?xml[^?]*\?>", "", text, flags=re.I)
        body = re.sub(r"<!DOCTYPE[^>]*>", "", body, flags=re.I)
        for k, v in _count_elements(body[:500000]).items():
            total_counts[k] = total_counts.get(k, 0) + v
    return combined, total_counts


def detect_shallow_output(
    combined_lower: str,
    construct_counts: dict[str, int],
    plan: GenerationPlan,
    intent: Optional[IntentRecord] = None,
) -> tuple[bool, list[SemanticViolation]]:
    """True if paragraph-heavy and missing required structures."""
    violations: list[SemanticViolation] = []
    shallow = False

    p_count = construct_counts.get("p", 0)
    table_count = construct_counts.get("table", 0) + construct_counts.get("simpletable", 0)

    for req in plan.required_constructs:
        name = req.name.lower()
        need = req.min_count
        got = construct_counts.get(name, 0)
        if name == "table":
            got = table_count
        if got < need:
            violations.append(
                SemanticViolation(
                    rule_id=f"required_construct:{name}",
                    severity="error",
                    message=f"Missing required construct '{name}': need {need}, found {got}",
                    repair_hint=f"Add at least {need} <{name}> element(s) with valid DITA structure.",
                )
            )

    if intent and "table_alignment" in intent.anti_fallback_signals:
        has_align_attr = bool(
            re.search(r'align\s*=\s*["\'](?:left|right|center|justify|char)', combined_lower)
        )
        if table_count == 0 and not has_align_attr:
            violations.append(
                SemanticViolation(
                    rule_id="table_alignment_semantics",
                    severity="error",
                    message="Table alignment intent requires <table> or align= on colspec/entry.",
                    repair_hint="Include a reference <table> with tgroup/row/entry or show align on colspec/entry.",
                )
            )

    if any(v.rule_id.startswith("required_construct:") for v in violations):
        shallow = True
    elif table_count == 0 and p_count >= 4 and any(
        r.name.lower() in ("table", "simpletable") for r in plan.required_constructs
    ):
        shallow = True
        violations.append(
            SemanticViolation(
                rule_id="shallow_p_only",
                severity="error",
                message="Many paragraphs but no table though plan requires tabular content.",
                repair_hint="Replace prose value lists with a DITA <table> and tgroup.",
            )
        )

    return shallow, violations


def validate_generation_semantics(
    plan: GenerationPlan,
    spec: RecipeSpec,
    *,
    scenario_dir: Optional[Path] = None,
    files_bytes: Optional[Dict[str, bytes]] = None,
    intent: Optional[IntentRecord] = None,
) -> SemanticValidationReport:
    """
    Validate output on disk (scenario folder) or in-memory file dict.
    """
    if scenario_dir is not None:
        combined, counts = _gather_topic_xml_from_dir(scenario_dir)
    elif files_bytes is not None:
        combined, counts = _gather_from_bytes_dict(files_bytes)
    else:
        return SemanticValidationReport(ok=False, shallow_output=True, violations=[
            SemanticViolation(rule_id="no_input", severity="error", message="No files to validate")
        ])

    combined_lower = combined.lower()
    shallow, violations = detect_shallow_output(combined_lower, counts, plan, intent)

    domain_violations = evaluate_domain_shallow_rules(
        combined, combined_lower, counts, plan, intent
    )
    violations.extend(domain_violations)
    if domain_violations:
        shallow = shallow or any(
            v.rule_id.startswith("shallow.") and v.severity == "error" for v in domain_violations
        )

    seen_rule_ids: set[str] = set()
    merged_rules: list[dict] = []
    for src in (plan.validation_rules or [], spec.validation_rules or []):
        for rule in src:
            if isinstance(rule, dict):
                merged_rules.append(rule)
    for rule in merged_rules:
        rid = str(rule.get("id") or "custom")
        if rid in seen_rule_ids:
            continue
        seen_rule_ids.add(rid)
        when = str(rule.get("when") or "")
        if when and intent:
            if "table_alignment" in when and "table_alignment" not in (intent.anti_fallback_signals or []):
                continue
        req = rule.get("require") or {}
        sev = rule.get("severity") or "error"
        if isinstance(req, dict) and "regex" in req:
            pat = str(req["regex"])
            try:
                if not re.search(pat, combined, re.IGNORECASE | re.DOTALL):
                    violations.append(
                        SemanticViolation(
                            rule_id=rid,
                            severity="warn" if sev == "warn" else "error",
                            message=f"Validation rule {rid} regex not matched",
                            repair_hint=str(rule.get("hint") or "Adjust XML to satisfy recipe validation_rules."),
                        )
                    )
            except re.error:
                pass

    err_count = sum(1 for v in violations if v.severity == "error")
    ok = err_count == 0
    report = SemanticValidationReport(
        ok=ok,
        shallow_output=shallow and not ok,
        violations=violations,
        construct_counts=counts,
    )
    if not ok:
        logger.warning_structured(
            "Semantic validation failed",
            extra_fields={
                "recipe_id": plan.recipe_id,
                "violation_count": len(violations),
                "shallow": shallow,
            },
        )
    return report
