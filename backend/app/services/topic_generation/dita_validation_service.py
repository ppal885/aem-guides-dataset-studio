"""
DitaValidationService — normalize, structural checks, folder validator, review snapshot, optional safe repair.

Isolated from chat service so benchmarks and orchestrator tests can inject mocks or call
validation without persisting chat messages.
"""

from __future__ import annotations

import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from app.core.schemas_chat_authoring import ChatDitaValidationResult, ChatSemanticPlan
from app.core.structured_logging import get_structured_logger
from app.services.dita_authoring_structure import validate_dita_topic_structure_categorized
from app.services.dita_xml_headers import normalize_dita_document
from app.services.smart_suggestions_service import build_review_snapshot, fix_all_safe
from app.utils.dita_validator import validate_dita_folder

logger = get_structured_logger(__name__)
_PLACEHOLDER_PHRASES = (
    "briefly introduce",
    "provide an overview",
    "present detailed information",
    "summarize the key points",
    "list the requirements",
    "configure the cluster settings",
    "use the user interface to",
)
_GENERIC_SECTION_TITLES = {"introduction", "body", "conclusion", "overview", "details", "summary"}


def _default_file_name(title: str, dita_type: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", (title or dita_type or "generated-topic").strip().lower()).strip(".-")
    return f"{base or 'generated-topic'}.dita"


def _local_name(tag: str) -> str:
    tag_value = tag.split("}")[-1] if "}" in tag else tag
    return tag_value.split(":")[-1].lower() if ":" in tag_value else tag_value.lower()


def _iter_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join(fragment.strip() for fragment in node.itertext() if fragment and fragment.strip()).strip()


def _quality_gate_issues(xml: str) -> list[str]:
    issues: list[str] = []
    lowered = (xml or "").strip().lower()
    if any(phrase in lowered for phrase in _PLACEHOLDER_PHRASES):
        issues.append("Generated XML contains placeholder or filler prose.")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return issues

    root_name = _local_name(root.tag)
    for node in root.iter():
        node_name = _local_name(node.tag)
        if node_name in {"section", "example"}:
            title_text = _iter_text(node.find("title"))
            body_text = _iter_text(node)
            body_without_title = body_text.replace(title_text, "", 1).strip() if title_text else body_text
            if title_text.strip().lower() in _GENERIC_SECTION_TITLES and any(
                phrase in body_without_title.lower() for phrase in _PLACEHOLDER_PHRASES
            ):
                issues.append(f"Generic section `{title_text}` is supported only by filler text.")
            if not body_without_title:
                issues.append(f"Section `{title_text or 'untitled'}` is empty.")
        if node_name == "p":
            paragraph_text = _iter_text(node)
            if paragraph_text and any(phrase in paragraph_text.lower() for phrase in _PLACEHOLDER_PHRASES):
                issues.append("Paragraph content includes placeholder guidance instead of source-backed text.")

    if root_name == "task":
        has_steps = any(_local_name(node.tag) in {"steps", "step", "substeps", "substep", "cmd"} for node in root.iter())
        if not has_steps:
            issues.append("Task topic is missing concrete steps or commands.")

    return list(dict.fromkeys(issue for issue in issues if issue))


def _reference_adoption_issues(xml: str, semantic_plan: ChatSemanticPlan) -> list[str]:
    decision = getattr(semantic_plan, "reference_adoption", None)
    policy = decision.serializer_policy if decision else None
    if not decision or not policy:
        return []

    issues: list[str] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return issues

    root_name = _local_name(root.tag)
    if root_name != (decision.target_root_type or root_name):
        issues.append(
            f"Generated root <{root_name}> does not match the reference adoption target <{decision.target_root_type}>."
        )

    if root_name == "task" and policy.preferred_taskbody_sequence:
        taskbody = next((node for node in root if _local_name(node.tag) == "taskbody"), None)
        child_names = [_local_name(child.tag) for child in list(taskbody or [])]
        for tag in ("prereq", "context", "result"):
            expected = tag in {item.lower() for item in policy.preferred_taskbody_sequence}
            has_section = any(section.name.strip().lower() in {tag, "prerequisite", "prerequisites"} for section in semantic_plan.sections)
            if expected and has_section and tag not in child_names:
                issues.append(f"Reference-guided task structure expected <{tag}> but it was not serialized.")

    if root_name == "reference" and policy.prefer_properties_layout:
        has_properties = any(_local_name(node.tag) == "properties" for node in root.iter())
        has_tables = any(_local_name(node.tag) in {"table", "simpletable"} for node in root.iter())
        if any("field" in section.name.lower() or "propert" in section.name.lower() for section in semantic_plan.sections):
            if not has_properties and not has_tables:
                issues.append(
                    "Reference-guided reference topic expected properties or parameter tables, but the output remained generic narrative only."
                )

    return list(dict.fromkeys(issue for issue in issues if issue))


class DitaValidationService:
    def _folder_validate(self, xml: str, *, file_name: str) -> dict:
        with tempfile.TemporaryDirectory(prefix="topic-gen-dita-") as tmpdir:
            path = Path(tmpdir) / file_name
            path.write_text(xml, encoding="utf-8")
            return validate_dita_folder(Path(tmpdir))

    async def validate_candidate(
        self,
        *,
        xml: str,
        semantic_plan: ChatSemanticPlan,
        tenant_id: str,
    ) -> tuple[str, ChatDitaValidationResult, dict]:
        normalized, dita_type = normalize_dita_document(xml, semantic_plan.dita_type)
        structural_errors, structural_warnings = validate_dita_topic_structure_categorized(
            normalized, expected_root=dita_type
        )
        issue = {
            "issue_key": "CHAT-AUTHORING",
            "summary": semantic_plan.title,
            "description": semantic_plan.purpose,
        }
        try:
            review = await build_review_snapshot(xml=normalized, issue=issue, tenant_id=tenant_id)
        except Exception as exc:
            logger.warning_structured(
                "dita_validation_review_snapshot_failed",
                extra_fields={"error": str(exc)},
                exc_info=True,
            )
            review = {
                "quality_score": None,
                "validation": [],
                "aem_guides_validation_errors": [],
            }

        validator = self._folder_validate(normalized, file_name=_default_file_name(semantic_plan.title, dita_type))
        validator_warnings = [str(item) for item in (validator.get("warnings") or [])]
        validator_warnings.extend(structural_warnings)
        quality_gate_issues = _quality_gate_issues(normalized)
        quality_gate_issues.extend(_reference_adoption_issues(normalized, semantic_plan))
        valid = (
            not validator["errors"]
            and not (review.get("aem_guides_validation_errors") or [])
            and not structural_errors
            and not quality_gate_issues
        )
        result = ChatDitaValidationResult(
            valid=valid,
            repaired=False,
            quality_score=int(review.get("quality_score") or 0) if review.get("quality_score") is not None else None,
            validator_errors=[str(item) for item in (validator.get("errors") or [])],
            validator_warnings=validator_warnings,
            structural_issues=structural_errors + quality_gate_issues,
            review_issues=list(review.get("validation") or []),
            aem_guides_validation_errors=[str(item) for item in (review.get("aem_guides_validation_errors") or [])],
            applied_repairs=[],
        )
        logger.info_structured(
            "dita_validation_candidate",
            extra_fields={
                "event": "dita_validation_candidate",
                "valid": valid,
                "validator_error_count": len(result.validator_errors),
                "structural_error_count": len(structural_errors),
            },
        )
        return normalized, result, review

    async def repair_once(
        self,
        *,
        xml: str,
        semantic_plan: ChatSemanticPlan,
        tenant_id: str,
    ) -> tuple[str, ChatDitaValidationResult, dict]:
        issue = {
            "issue_key": "CHAT-AUTHORING",
            "summary": semantic_plan.title,
            "description": semantic_plan.purpose,
        }
        try:
            repaired = await fix_all_safe(xml=xml, issue=issue, tenant_id=tenant_id)
        except Exception as exc:
            logger.error_structured(
                "dita_validation_repair_failed",
                extra_fields={"error": str(exc)},
                exc_info=True,
            )
            normalized, result, review = await self.validate_candidate(
                xml=xml, semantic_plan=semantic_plan, tenant_id=tenant_id
            )
            return normalized, result, review

        repaired_xml = str(repaired.get("xml") or xml)
        normalized, validation_result, review = await self.validate_candidate(
            xml=repaired_xml,
            semantic_plan=semantic_plan,
            tenant_id=tenant_id,
        )
        validation_result.repaired = repaired_xml.strip() != xml.strip()
        validation_result.applied_repairs = [str(item) for item in (repaired.get("applied_rule_ids") or [])]
        return normalized, validation_result, review
