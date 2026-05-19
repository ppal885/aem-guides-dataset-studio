from __future__ import annotations

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from app.services.dita_authoring_structure import validate_dita_topic_structure_categorized
from app.services.dita_xml_headers import strip_xml_prolog
from app.services.reference_dita_analyzer import analyze_reference_dita
from app.utils.dita_validator import validate_dita_folder

from app.benchmarks.authoring_eval.fingerprints import extract_reference_fingerprints, over_copying_score
from app.benchmarks.authoring_eval.models import BenchmarkCase, DimensionScores


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower() if tag else ""


def score_xml_valid_folder(xml: str, *, file_name: str = "topic.dita") -> bool:
    """DTD-level folder validation (same helper style as chat authoring)."""
    if not (xml or "").strip():
        return False
    with tempfile.TemporaryDirectory(prefix="bench-dita-") as tmpdir:
        path = Path(tmpdir) / file_name
        path.write_text(xml, encoding="utf-8")
        result = validate_dita_folder(Path(tmpdir))
        return not (result.get("errors") or [])


def score_structural_ok(xml: str, *, expected_root: str) -> bool:
    errors, _warnings = validate_dita_topic_structure_categorized(xml, expected_root=expected_root)
    return len(errors) == 0


def score_topic_type_match(actual: str, expected: str | None) -> bool | None:
    if expected is None:
        return None
    return (actual or "").strip().lower() == expected.strip().lower()


def _count_xref_conref_elements(xml: str) -> int:
    body = strip_xml_prolog(xml or "")
    if not body.strip():
        return 0
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return 0
    n = 0
    for elem in root.iter():
        tag = _local(elem.tag)
        if tag == "xref" and elem.get("href"):
            n += 1
        if elem.get("conref"):
            n += 1
    return n


def unresolved_xref_conref_rate(xml: str, *, expected_root: str) -> float:
    errors, _w = validate_dita_topic_structure_categorized(xml, expected_root=expected_root)
    unresolved = sum(1 for e in errors if "Unresolved xref" in e or "Unresolved conref" in e)
    denom = max(1, _count_xref_conref_elements(xml))
    return min(1.0, unresolved / denom)


def style_adherence_score(generated_xml: str, reference_raw: str | None, *, expected_dita_type: str) -> float | None:
    """
    Compare lightweight structural habits between reference and generated topics.

    Returns None if no reference text; otherwise 0–1 (higher is closer to reference habits).
    """
    if not (reference_raw or "").strip():
        return None
    prof_ref, _ = analyze_reference_dita(reference_raw)
    pw = " ".join(prof_ref.parse_warnings or []).lower()
    if prof_ref.parse_warnings and ("parse error" in pw or "empty" in pw):
        return None
    if not prof_ref.root_local_name:
        return None

    prof_gen, _ = analyze_reference_dita(generated_xml)
    gw = " ".join(prof_gen.parse_warnings or []).lower()
    if prof_gen.parse_warnings and ("parse error" in gw or "empty" in gw):
        return 0.0

    parts: list[float] = []

    # Root type alignment with expectation (reference should match task of benchmark)
    if prof_ref.root_local_name == expected_dita_type:
        parts.append(1.0 if prof_gen.root_local_name == expected_dita_type else 0.4)
    else:
        parts.append(1.0 if prof_gen.root_local_name == expected_dita_type else 0.5)

    habits_ref = set(prof_ref.structural_habits or [])
    habits_gen = set(prof_gen.structural_habits or [])
    if habits_ref:
        j = len(habits_ref & habits_gen) / len(habits_ref)
        parts.append(j)
    else:
        parts.append(0.7)

    # Child order (top-level under root): Jaccard on ordered unique tags
    co_ref = prof_ref.child_order_top_level or []
    co_gen = prof_gen.child_order_top_level or []
    if co_ref and co_gen:
        set_r, set_g = set(co_ref), set(co_gen)
        inter = len(set_r & set_g)
        union = len(set_r | set_g)
        parts.append(inter / union if union else 0.0)
    else:
        parts.append(0.6)

    return sum(parts) / len(parts)


def pipeline_repair_used(debug: dict[str, Any] | None) -> bool:
    if not debug:
        return False
    trace = debug.get("pipeline_trace") or debug.get("pipeline_stages") or []
    for row in trace:
        if not isinstance(row, dict):
            continue
        if row.get("stage") != "repair_optional":
            continue
        det = row.get("detail") or {}
        if det.get("repaired"):
            return True
    return False


def build_dimension_scores(
    *,
    case: BenchmarkCase,
    generated_xml: str,
    result_status: str,
    generated_dita_type: str,
    reference_raw: str | None,
    debug: dict[str, Any] | None,
) -> tuple[DimensionScores, dict[str, Any]]:
    exp = case.expected_dita_type
    root = generated_dita_type or exp or "topic"

    xml_valid = score_xml_valid_folder(generated_xml, file_name=f"{case.id}.dita")
    structural = score_structural_ok(generated_xml, expected_root=root)
    topic_ok = score_topic_type_match(generated_dita_type, exp)
    style = style_adherence_score(generated_xml, reference_raw, expected_dita_type=root)

    fp = (
        extract_reference_fingerprints(reference_raw)
        if (reference_raw or "").strip()
        else {"ids": set(), "hrefs": set(), "conrefs": set()}
    )
    copy_risk, copy_reasons = over_copying_score(
        generated_xml,
        ref_ids=fp["ids"],
        ref_hrefs=fp["hrefs"],
        ref_conrefs=fp["conrefs"],
    )
    unres = unresolved_xref_conref_rate(generated_xml, expected_root=root)
    repair = pipeline_repair_used(debug)

    insertion: bool | None = None
    if case.expect_saved_to_aem:
        insertion = result_status == "saved"

    scores = DimensionScores(
        xml_valid=xml_valid,
        structural_ok=structural,
        topic_type_correct=topic_ok,
        style_adherence=style,
        over_copying_risk=copy_risk,
        unresolved_xref_conref_rate=unres,
        pipeline_repair_used=repair,
        insertion_success=insertion,
        regeneration_observed=None,
        edit_after_generation_observed=None,
    )
    extras: dict[str, Any] = {"over_copying_reasons": copy_reasons}
    return scores, extras


def apply_case_assertions(case: BenchmarkCase, dims: DimensionScores) -> list[str]:
    """Return human-readable failures for automated gates."""
    failures: list[str] = []
    if not dims.xml_valid:
        failures.append("assert_xml_valid")
    if not dims.structural_ok:
        failures.append("assert_structural_ok")
    if dims.topic_type_correct is False:
        failures.append("assert_topic_type")
    if case.expect_saved_to_aem and not (dims.insertion_success is True):
        failures.append("assert_insertion_success")
    if dims.over_copying_risk > 0:
        failures.append("assert_no_reference_leak")
    if dims.unresolved_xref_conref_rate > 0:
        failures.append("assert_no_unresolved_xref_conref")
    return failures
