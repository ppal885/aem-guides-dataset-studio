"""Shared generate-from-text execution for API routes and chat tools."""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request

from app.core.observability import get_observability_logger
from app.core.structured_logging import get_structured_logger
from app.core.validation import sanitize_error_for_client
from app.core.schemas_ai import GeneratorInvocationPlan, SelectedRecipe
from app.db.dataset_run_models import DatasetRun
from app.db.session import SessionLocal
from app.services.ai_executor_service import execute_plan
from app.services.bundle_builder_service import build_bundle
from app.services.dita_auto_fix_service import auto_fix_dita_folder
from app.services.dita_enrichment_service import enrich_dita_folder
from app.services.doc_retriever_service import check_rag_readiness
from app.services.dita_generation_contract_service import validate_generated_bundle_against_contract
from app.services.jira_generate_resolve import resolve_text_for_generate_from_text
from app.services.llm_service import (
    clear_llm_trace,
    generate_json,
    is_llm_available,
    start_llm_trace,
    summarize_llm_trace,
)
from app.services.recipe_pipeline_service import run_recipe_pipeline
from app.storage import get_storage
from app.utils.dita_validator import validate_dita_folder
from app.utils.evidence_extractor import pre_extract_representative_xml
from app.services.dataset_packager_service import package_bundle

logger = get_structured_logger(__name__)
obs_log = get_observability_logger("dita_generation")

generate_progress_store: dict[str, dict[str, Any]] = {}

GENERATE_FROM_TEXT_USE_PIPELINE = os.environ.get("GENERATE_FROM_TEXT_USE_PIPELINE", "false").lower() in ("true", "1", "yes")
GENERATE_FROM_TEXT_USE_INTENT_PIPELINE = os.environ.get(
    "GENERATE_FROM_TEXT_USE_INTENT_PIPELINE", "true"
).lower() in ("true", "1", "yes")
DITA_GENERATION_ENABLE_BUILD_VALIDATION = os.environ.get(
    "DITA_GENERATION_ENABLE_BUILD_VALIDATION", "false"
).lower() in ("true", "1", "yes")
DITA_GENERATION_BUILD_VALIDATOR = os.environ.get("DITA_GENERATION_BUILD_VALIDATOR", "DITA-OT").strip() or "DITA-OT"
_XREF_VARIETY_REQUEST_PATTERN = re.compile(
    r"\b(?:all|every|different|various)\s+(?:types?|kinds?|forms?)\s+of\s+(?:xrefs?|cross[- ]?references?)\b|"
    r"\b(?:xrefs?|cross[- ]?references?)\b[^.?!\n]{0,100}\b(?:all|every|different|various)\s+(?:types?|kinds?|forms?)\b|"
    r"\b(?:all|every|different|various)\s+(?:xrefs?|cross[- ]?references?)\b",
    re.IGNORECASE,
)
_SUPPORTED_DETERMINISTIC_ELEMENTS: dict[str, set[str]] = {
    "task": {"task", "taskbody", "prereq", "context", "steps", "step", "cmd", "info", "substeps", "substep", "result", "choicetable", "stepxmp"},
    "concept": {"concept", "conbody", "section", "p"},
    "reference": {"reference", "refbody", "refsyn", "properties", "property", "proptype", "propvalue", "propdesc", "simpletable", "section", "table", "codeblock"},
    "topic": {"topic", "body", "section", "p", "shortdesc", "title"},
    "glossentry": {"glossentry", "glossterm", "glossdef", "glossbody", "glossbody", "alt"},
}
_SUPPORTED_DETERMINISTIC_STRUCTURES: dict[str, set[str]] = {
    "task": {"choicetable"},
    "concept": set(),
    "reference": {"properties", "simpletable", "table", "codeblock", "yaml"},
    "topic": set(),
    "glossentry": set(),
}
_DETERMINISTIC_SINGLE_MAP_CONSTRUCT_RECIPES: dict[str, str] = {
    "topicref": "maps.topicref_basic",
    "topichead": "maps.topichead_basic",
    "topicgroup": "maps.topicgroup_basic",
}


def update_generate_progress(run_id: str, **kwargs: Any) -> None:
    """Update progress dict for run_id. Merges kwargs into existing state."""
    if run_id not in generate_progress_store:
        generate_progress_store[run_id] = {}
    generate_progress_store[run_id].update(kwargs)


def set_generate_progress(run_id: str, payload: dict[str, Any]) -> None:
    generate_progress_store[run_id] = dict(payload)


def write_scenario_metadata(
    scenario_dir: Path,
    jira_id: str,
    scenario_type: str,
    generator_recipes: list[str],
    evidence: list[str],
) -> None:
    metadata = {
        "jira_id": jira_id,
        "scenario_type": scenario_type,
        "generator_recipes": generator_recipes,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "evidence": evidence,
    }
    (scenario_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _extract_jira_field(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return (match.group(1) or "").strip() if match else ""


def _extract_jira_section(text: str, heading_pattern: str) -> str:
    match = re.search(heading_pattern, text, re.IGNORECASE)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(
        r"\n(?:##\s|h[1-6]\.\s|(?:Issue\s+(?:Summary|Description)|Steps?\s+to|Expected|Actual|Acceptance|Environment|Comments?)\s*\n)",
        text[start:],
        re.IGNORECASE,
    )
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end].strip()[:3000]


def build_evidence_pack_from_text(
    text: str,
    run_id: str,
    *,
    forced_issue_key: str | None = None,
) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {"primary": {"summary": "", "description": "", "issue_key": "TEXT"}, "similar": []}

    issue_key = forced_issue_key or f"TEXT-{run_id[:8]}"

    issue_type = _extract_jira_field(text, r"^Issue\s+Type:\s*(.+)$")
    priority = _extract_jira_field(text, r"^Priority:\s*(.+)$")
    status = _extract_jira_field(text, r"^Status:\s*(.+)$")
    labels_raw = _extract_jira_field(text, r"^Labels:\s*(.+)$")
    labels = [label.strip() for label in labels_raw.split(",") if label.strip()] if labels_raw else []
    components_raw = _extract_jira_field(text, r"^Components:\s*(.+)$")
    components = [component.strip() for component in components_raw.split(",") if component.strip()] if components_raw else []

    acceptance_criteria = _extract_jira_section(text, r"##\s*Acceptance\s+Criteria\s*\n")
    steps_to_reproduce = _extract_jira_section(text, r"##\s*Steps?\s+to\s+Reproduce\s*\n")
    expected_behavior = _extract_jira_section(text, r"##\s*Expected\s+(?:Behavior|Result|Outcome)\s*\n")
    actual_behavior = _extract_jira_section(text, r"##\s*(?:Actual\s+(?:Behavior|Result|Outcome)|Current\s+Behavior)\s*\n")
    environment = _extract_jira_section(text, r"##\s*Environment\s*\n")

    summary = ""
    description = text

    if forced_issue_key:
        summary_match = re.search(
            r"##\s*Issue\s+Summary\s*\n(.*?)(?=\n\s*##\s*Issue\s+Description|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        description_match = re.search(
            r"##\s*Issue\s+Description\s*\n(.*?)(?=\n\s*##\s|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if summary_match:
            summary = (summary_match.group(1) or "").strip()[:500]
        if description_match:
            description = (description_match.group(1) or "").strip()
    else:
        description_heading = re.search(r"(?:h3\.\s*)?Issue\s+Description\s*\n", text, re.IGNORECASE)
        summary_heading = re.search(r"(?:h3\.\s*)?Issue\s+Summary\s*\n", text, re.IGNORECASE)
        if description_heading or summary_heading:
            parts = re.split(
                r"\n(?:h3\.\s*)?(?:Issue\s+Summary|Issue\s+Description)\s*\n",
                text,
                maxsplit=1,
                flags=re.IGNORECASE,
            )
            if len(parts) >= 2:
                summary = (parts[0] or "").strip()[:500]
                description = (parts[1] or "").strip()
            else:
                summary = (parts[0] or "").strip()[:500]
                description = ""
        else:
            summary = text[:500].strip()
            # For plain-language requests (no Jira Issue Summary/Description headers), always preserve the
            # full request in `description`. Historically we left description empty when len(text) <= 500,
            # which made the LLM DITA prompt's Description block blank and let retrieved RAG snippets
            # override the user's actual topic.
            description = text.strip()

    primary: dict[str, Any] = {
        "summary": summary,
        "description": description,
        "issue_key": issue_key,
    }
    if issue_type:
        primary["issue_type"] = issue_type
    if priority:
        primary["priority"] = priority
    if status:
        primary["status"] = status
    if labels:
        primary["labels"] = labels
    if components:
        primary["components"] = components
    if acceptance_criteria:
        primary["acceptance_criteria"] = acceptance_criteria
    if steps_to_reproduce:
        primary["steps_to_reproduce"] = steps_to_reproduce
    if expected_behavior:
        primary["expected_behavior"] = expected_behavior
    if actual_behavior:
        primary["actual_behavior"] = actual_behavior
    if environment:
        primary["environment"] = environment

    return {"primary": primary, "similar": []}


_XML_EXAMPLE_MAX_CHARS = 1200


def _summarize_generated_bundle(scenario_outputs: dict[str, Path]) -> dict[str, Any]:
    files: list[str] = []
    example_paths: list[Path] = []
    map_files = 0
    dita_files = 0
    topic_files = 0
    for scenario_dir in scenario_outputs.values():
        if not scenario_dir.exists():
            continue
        for path in sorted(scenario_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".dita", ".ditamap", ".xml"}:
                continue
            dita_files += 1
            if path.suffix.lower() == ".ditamap":
                map_files += 1
            else:
                topic_files += 1
                if len(example_paths) < 2:
                    example_paths.append(path)
            files.append(path.name)
    representative_files = files[:6]
    # Read up to 2 topic files as XML examples (truncated)
    xml_examples: list[dict[str, str]] = []
    for ep in example_paths:
        try:
            text = ep.read_text(encoding="utf-8", errors="ignore")
            if len(text) > _XML_EXAMPLE_MAX_CHARS:
                text = text[:_XML_EXAMPLE_MAX_CHARS] + "\n<!-- ... truncated ... -->"
            xml_examples.append({"filename": ep.name, "xml": text})
        except Exception:
            pass
    parts: list[str] = []
    if map_files:
        parts.append(f"{map_files} map file{'s' if map_files != 1 else ''}")
    if topic_files:
        parts.append(f"{topic_files} topic file{'s' if topic_files != 1 else ''}")
    if not parts and dita_files:
        parts.append(f"{dita_files} DITA file{'s' if dita_files != 1 else ''}")
    summary = (
        f"Generated a DITA bundle with {' and '.join(parts)}."
        if parts
        else "Generated a DITA bundle."
    )
    return {
        "bundle_summary": summary,
        "artifact_counts": {
            "total_files": dita_files,
            "map_files": map_files,
            "topic_files": topic_files,
        },
        "representative_files": representative_files,
        "xml_examples": xml_examples,
    }


def _contract_count(contract: dict[str, Any], key: str, default: int = 1) -> int:
    counts = contract.get("counts") if isinstance(contract.get("counts"), dict) else {}
    try:
        value = int(counts.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(1, value)


def _contract_single_map_construct_recipe(contract: dict[str, Any]) -> tuple[str, str] | None:
    """Return a deterministic recipe for one map-scoped construct when the contract is exact enough."""
    if not isinstance(contract, dict):
        return None
    if str(contract.get("topic_family") or "").strip().lower() != "map":
        return None
    construct_names = {
        str(item.get("name") or "").strip().lower()
        for item in (contract.get("construct_semantics") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    example_construct = str(contract.get("example_construct") or "").strip().lower()
    if example_construct:
        construct_names.add(example_construct)
    semantic_recipe_ids: dict[str, str] = {}
    for item in (contract.get("construct_semantics") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        recipe_id = str(item.get("deterministic_recipe_id") or "").strip()
        if name and recipe_id and name in _DETERMINISTIC_SINGLE_MAP_CONSTRUCT_RECIPES:
            semantic_recipe_ids[name] = recipe_id
    recipe_registry = {**_DETERMINISTIC_SINGLE_MAP_CONSTRUCT_RECIPES, **semantic_recipe_ids}
    selected_constructs = construct_names & set(recipe_registry)
    if len(selected_constructs) != 1:
        return None
    unsupported_constructs = construct_names - selected_constructs - {"topicref", "map", "topic"}
    if unsupported_constructs:
        return None
    construct = next(iter(selected_constructs))
    return construct, recipe_registry[construct]


def _configured_count_for_selected_recipe(selected: SelectedRecipe) -> int:
    params = selected.params or {}
    for key in ("topic_count", "entry_count"):
        try:
            if key in params:
                return max(1, int(params.get(key) or 1))
        except (TypeError, ValueError):
            continue
    return 1


def _normalize_draft_items(value: object, count: int) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("content") or item.get("text") or "").strip()
        elif isinstance(item, list):
            # LLM returned list-of-section-dicts for a single topic; join content fields
            parts = []
            for s in item:
                if isinstance(s, dict):
                    parts.append(str(s.get("content") or s.get("text") or "").strip())
                elif isinstance(s, str):
                    parts.append(s.strip())
            text = " ".join(p for p in parts if p)
        else:
            continue
        if text:
            items.append(text)
        if len(items) >= count:
            break
    return items


def _normalize_draft_sections(value: object, count: int) -> list[list[dict]]:
    """Extract structured per-topic sections when LLM returns list-of-section-dicts per topic."""
    if not isinstance(value, list):
        return []
    result: list[list[dict]] = []
    for item in value:
        if isinstance(item, list) and item and all(isinstance(s, dict) for s in item):
            sections = []
            for s in item:
                title = str(s.get("section_title") or s.get("title") or "").strip()
                content = str(s.get("content") or s.get("text") or "").strip()
                if content:
                    sections.append({"title": title, "content": content})
            if sections:
                result.append(sections)
        if len(result) >= count:
            break
    return result


def _normalize_draft_steps(value: object, count: int) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    steps_by_topic: list[list[str]] = []
    for item in value[:count]:
        if not isinstance(item, list):
            continue
        steps = [str(step or "").strip() for step in item if str(step or "").strip()]
        if steps:
            steps_by_topic.append(steps)
    return steps_by_topic


async def _maybe_apply_llm_deterministic_drafts(
    *,
    selected: SelectedRecipe,
    contract: dict[str, Any] | None,
    trace_id: str,
    jira_id: str,
) -> tuple[SelectedRecipe, dict[str, Any]]:
    recipe_id = str(selected.recipe_id or "").strip()
    if recipe_id not in {"task_topics", "concept_topics", "reference_topics", "topic_topics", "glossary"}:
        return selected, {"llm_draft_used": False, "path": "deterministic_only", "fields": []}
    if not is_llm_available():
        return selected, {"llm_draft_used": False, "path": "deterministic_only", "fields": []}

    contract = contract or {}
    subject = str(contract.get("subject") or "").strip()
    count = _configured_count_for_selected_recipe(selected)
    if count <= 0:
        return selected, {"llm_draft_used": False, "path": "deterministic_only", "fields": []}

    family = str(contract.get("topic_family") or "").strip() or recipe_id.replace("_topics", "")
    metadata_fields = [
        str(item.get("field_name") or "").strip()
        for item in (contract.get("required_metadata") or [])
        if isinstance(item, dict) and str(item.get("field_name") or "").strip()
    ]
    required_elements = [
        str(item.get("name") or "").strip()
        for item in (contract.get("required_elements") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    required_attributes = [
        str(item.get("attribute_name") or "").strip()
        for item in (contract.get("required_attributes") or [])
        if isinstance(item, dict) and str(item.get("attribute_name") or "").strip()
    ]
    construct_semantics = [
        str(item.get("name") or "").strip()
        for item in (contract.get("construct_semantics") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    domain_subtopics = [
        str(item).strip()
        for item in ((contract.get("domain_decomposition") or {}).get("subtopics") or [])
        if str(item).strip()
    ]

    system_prompt = (
        "You draft structured content for deterministic DITA generators.\n"
        "Return strict JSON only.\n"
        "Do not return XML.\n"
        "Keep outputs concrete, domain-specific, and concise.\n"
        "Honor the requested family and avoid placeholders like Topic 1."
    )
    user_prompt = json.dumps(
        {
            "task": "Draft content fields for a deterministic DITA bundle generator.",
            "topic_family": family,
            "subject": subject or None,
            "count": count,
            "required_metadata": metadata_fields,
            "required_elements": required_elements,
            "required_attributes": required_attributes,
            "construct_semantics": construct_semantics,
            "domain_subtopics": domain_subtopics,
            "expected_fields": (
                ["titles", "shortdescs", "terms", "definitions", "acronyms"]
                if recipe_id == "glossary"
                else (
                    ["titles", "shortdescs", "steps_by_topic"]
                    if recipe_id == "task_topics"
                    else ["titles", "shortdescs", "body_snippets", "property_seeds", "detail_snippets"]
                )
            ),
            "rules": [
                "Return arrays sized for the requested count when possible.",
                "Keep titles unique and user-facing.",
                "Keep shortdescs one sentence each.",
                "When domain_subtopics are present, align one item to each subtopic before inventing broader themes.",
                "Only include fields that fit the requested family.",
            ],
        },
        ensure_ascii=False,
    )

    try:
        draft = await generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=2200,
            step_name="dita_deterministic_draft",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        logger.warning_structured(
            "Deterministic DITA draft stage fell back to seeded content",
            extra_fields={"jira_id": jira_id, "recipe_id": recipe_id, "error": str(exc)},
        )
        return selected, {
            "llm_draft_used": False,
            "path": "deterministic_only",
            "fields": [],
            "warning": "LLM draft stage failed, so seeded deterministic content was used.",
        }

    params = dict(selected.params or {})
    applied_fields: list[str] = []
    titles = _normalize_draft_items(draft.get("titles"), count)
    shortdescs = _normalize_draft_items(draft.get("shortdescs"), count)
    body_snippets = _normalize_draft_items(draft.get("body_snippets"), count)
    body_sections = _normalize_draft_sections(draft.get("body_snippets"), count)
    property_seeds = _normalize_draft_items(draft.get("property_seeds"), count)
    detail_snippets = _normalize_draft_items(draft.get("detail_snippets"), count)
    terms = _normalize_draft_items(draft.get("terms"), count)
    definitions = _normalize_draft_items(draft.get("definitions"), count)
    acronyms = _normalize_draft_items(draft.get("acronyms"), count)
    steps_by_topic = _normalize_draft_steps(draft.get("steps_by_topic"), count)

    if titles:
        params["content_titles"] = titles
        applied_fields.append("titles")
    if shortdescs:
        params["content_shortdescs"] = shortdescs
        applied_fields.append("shortdescs")
    if recipe_id in {"topic_topics", "concept_topics"}:
        if body_sections:
            params["content_sections_by_topic"] = body_sections
            applied_fields.append("body_sections")
        elif body_snippets:
            params["content_body_snippets"] = body_snippets
            applied_fields.append("body_snippets")
    if recipe_id == "task_topics" and steps_by_topic:
        params["content_steps_by_topic"] = steps_by_topic
        applied_fields.append("steps_by_topic")
    if recipe_id == "reference_topics" and property_seeds:
        params["content_property_seeds"] = property_seeds
        applied_fields.append("property_seeds")
    if recipe_id == "reference_topics" and detail_snippets:
        params["content_detail_snippets"] = detail_snippets
        applied_fields.append("detail_snippets")
    if recipe_id == "glossary" and terms:
        params["content_terms"] = terms
        applied_fields.append("terms")
    if recipe_id == "glossary" and definitions:
        params["content_definitions"] = definitions
        applied_fields.append("definitions")
    if recipe_id == "glossary" and acronyms:
        params["content_acronyms"] = acronyms
        applied_fields.append("acronyms")

    if not applied_fields:
        return selected, {"llm_draft_used": False, "path": "deterministic_only", "fields": []}

    return (
        SelectedRecipe(
            recipe_id=selected.recipe_id,
            params=params,
            evidence_used=list(selected.evidence_used or []),
        ),
        {
            "llm_draft_used": True,
            "path": "deterministic_plus_llm_draft",
            "fields": applied_fields,
            "step_name": "dita_deterministic_draft",
        },
    )


_SUBJECT_GUIDED_THEME_SPECS: list[dict[str, str]] = [
    {
        "slug": "overview",
        "label": "overview",
        "topic_focus": "the overall landscape, purpose, and practical context",
        "concept_focus": "the foundational concepts and how the major parts fit together",
        "reference_focus": "baseline settings, key fields, and expected values",
        "task_focus": "initial setup and first-use steps",
    },
    {
        "slug": "architecture",
        "label": "architecture",
        "topic_focus": "the main building blocks and their responsibilities",
        "concept_focus": "the structure, relationships, and internal organization",
        "reference_focus": "structural options, dependencies, and supporting fields",
        "task_focus": "structural setup and configuration steps",
    },
    {
        "slug": "operations",
        "label": "operations",
        "topic_focus": "day-to-day operational workflows and usage patterns",
        "concept_focus": "the operating model and common working patterns",
        "reference_focus": "operational parameters, defaults, and runtime details",
        "task_focus": "routine operational actions and verification",
    },
    {
        "slug": "configuration",
        "label": "configuration",
        "topic_focus": "configuration choices and their downstream impact",
        "concept_focus": "configuration concepts and the tradeoffs behind them",
        "reference_focus": "configuration properties, accepted values, and notes",
        "task_focus": "configuration changes and validation steps",
    },
    {
        "slug": "integration",
        "label": "integration",
        "topic_focus": "integration points and how related systems connect",
        "concept_focus": "integration boundaries and shared responsibilities",
        "reference_focus": "integration fields, endpoints, and supporting metadata",
        "task_focus": "integration setup and dependency checks",
    },
    {
        "slug": "maintenance",
        "label": "maintenance",
        "topic_focus": "maintenance needs, routine care, and lifecycle concerns",
        "concept_focus": "maintenance concepts and long-term upkeep patterns",
        "reference_focus": "maintenance settings, schedules, and support details",
        "task_focus": "maintenance procedures and post-change checks",
    },
    {
        "slug": "security",
        "label": "security",
        "topic_focus": "security concerns, controls, and safe operating guidance",
        "concept_focus": "security boundaries, risk areas, and protection models",
        "reference_focus": "security-related fields, restrictions, and expected values",
        "task_focus": "security hardening and validation steps",
    },
    {
        "slug": "troubleshooting",
        "label": "troubleshooting",
        "topic_focus": "common problems, diagnostics, and recovery paths",
        "concept_focus": "failure patterns and the causes behind them",
        "reference_focus": "diagnostic fields, status values, and remediation notes",
        "task_focus": "diagnostic checks and corrective actions",
    },
    {
        "slug": "comparison",
        "label": "comparison",
        "topic_focus": "how important options compare in practice",
        "concept_focus": "the differences between major approaches and models",
        "reference_focus": "comparative fields, characteristics, and evaluation notes",
        "task_focus": "selection steps and decision checkpoints",
    },
    {
        "slug": "optimization",
        "label": "optimization",
        "topic_focus": "performance tuning, efficiency, and best practices",
        "concept_focus": "optimization concepts and the levers that influence outcomes",
        "reference_focus": "tuning properties, thresholds, and optimization notes",
        "task_focus": "optimization changes and outcome verification",
    },
    {
        "slug": "governance",
        "label": "governance",
        "topic_focus": "governance expectations, standards, and control points",
        "concept_focus": "governance models, policy boundaries, and ownership",
        "reference_focus": "governance fields, policies, and compliance notes",
        "task_focus": "governance checks and approval-oriented actions",
    },
    {
        "slug": "examples",
        "label": "examples",
        "topic_focus": "real-world examples, scenarios, and practical illustrations",
        "concept_focus": "illustrative scenarios that clarify the broader concepts",
        "reference_focus": "example values, scenario-specific details, and usage notes",
        "task_focus": "scenario-based steps and example-driven validation",
    },
]


def _subject_guided_theme(index: int) -> dict[str, str]:
    if not _SUBJECT_GUIDED_THEME_SPECS:
        return {
            "slug": "overview",
            "label": "overview",
            "topic_focus": "the overall landscape",
            "concept_focus": "the core concepts",
            "reference_focus": "the key fields and expected values",
            "task_focus": "the primary workflow",
        }
    return _SUBJECT_GUIDED_THEME_SPECS[(max(1, index) - 1) % len(_SUBJECT_GUIDED_THEME_SPECS)]


def _normalized_subtopics(subtopics: list[str] | None, count: int) -> list[str]:
    if not subtopics:
        return []
    cleaned = [re.sub(r"\s+", " ", str(item or "").strip()).strip(" .,:;!?") for item in subtopics]
    return [item for item in cleaned if item][: max(1, count)]


def _subject_guided_titles(subject: str, family: str, count: int, subtopics: list[str] | None = None) -> list[str]:
    clean_subject = re.sub(r"\s+", " ", (subject or "").strip()).strip(" .,:;!?")
    if not clean_subject:
        return []
    title_subject = clean_subject[:1].upper() + clean_subject[1:]
    normalized_subtopics = _normalized_subtopics(subtopics, count)
    if count <= 1:
        if normalized_subtopics:
            focus = normalized_subtopics[0][:1].upper() + normalized_subtopics[0][1:]
            if family == "task":
                return [f"{title_subject}: {focus}"]
            if family == "reference":
                return [f"{title_subject} reference: {focus}"]
            if family == "concept":
                return [f"{title_subject}: {focus}"]
            return [f"{title_subject}: {focus}"]
        if family == "task":
            return [f"How to work with {title_subject}"]
        if family == "concept":
            return [f"Understanding {title_subject}"]
        if family == "reference":
            return [f"{title_subject} reference"]
        return [title_subject]
    titles: list[str] = []
    for index in range(1, count + 1):
        if index <= len(normalized_subtopics):
            focus = normalized_subtopics[index - 1][:1].upper() + normalized_subtopics[index - 1][1:]
            if family == "task":
                titles.append(f"{title_subject}: {focus}")
            elif family == "reference":
                titles.append(f"{title_subject} reference: {focus}")
            else:
                titles.append(f"{title_subject}: {focus}")
            continue
        theme = _subject_guided_theme(index)
        if family == "task":
            titles.append(f"{title_subject} {theme['label']} task {index:02d}")
        elif family == "concept":
            titles.append(f"{title_subject} {theme['label']} concept {index:02d}")
        elif family == "reference":
            titles.append(f"{title_subject} {theme['label']} reference {index:02d}")
        elif family == "topic":
            titles.append(f"{title_subject} {theme['label']} {index:02d}")
        else:
            titles.append(f"{title_subject} topic {index:02d}")
    return titles


def _subject_guided_shortdescs(subject: str, family: str, count: int, subtopics: list[str] | None = None) -> list[str]:
    clean_subject = re.sub(r"\s+", " ", (subject or "").strip()).strip(" .,:;!?")
    if not clean_subject:
        return []
    normalized_subtopics = _normalized_subtopics(subtopics, count)
    shortdescs: list[str] = []
    for index in range(1, max(1, count) + 1):
        if index <= len(normalized_subtopics):
            focus = normalized_subtopics[index - 1]
            if family == "task":
                shortdescs.append(
                    f"Procedure guidance for {clean_subject}, focused on {focus}."
                )
            elif family == "reference":
                shortdescs.append(
                    f"Reference details for {clean_subject}, focused on {focus}."
                )
            elif family == "topic":
                shortdescs.append(
                    f"Topic guidance for {clean_subject}, focused on {focus}."
                )
            else:
                shortdescs.append(
                    f"Conceptual guidance for {clean_subject}, focused on {focus}."
                )
            continue
        theme = _subject_guided_theme(index)
        if family == "task":
            shortdescs.append(
                f"Procedure guidance for {clean_subject} with emphasis on {theme['task_focus']}."
            )
        elif family == "reference":
            shortdescs.append(
                f"Reference details for {clean_subject}, focusing on {theme['reference_focus']}."
            )
        elif family == "topic":
            shortdescs.append(
                f"Plain-topic guidance for {clean_subject}, focusing on {theme['topic_focus']}."
            )
        else:
            shortdescs.append(
                f"Conceptual guidance for {clean_subject}, focusing on {theme['concept_focus']}."
            )
    return shortdescs


def _subject_guided_topic_body_snippets(subject: str, count: int, subtopics: list[str] | None = None) -> list[str]:
    clean_subject = re.sub(r"\s+", " ", (subject or "").strip()).strip(" .,:;!?")
    if not clean_subject:
        return []
    normalized_subtopics = _normalized_subtopics(subtopics, count)
    snippets: list[str] = []
    for index in range(1, max(1, count) + 1):
        if index <= len(normalized_subtopics):
            focus = normalized_subtopics[index - 1]
            snippets.append(
                f"This topic focuses on {focus} in {clean_subject}. "
                f"It explains what teams should understand, document, and verify for that part of {clean_subject}."
            )
            continue
        theme = _subject_guided_theme(index)
        snippets.append(
            f"This topic focuses on {clean_subject} and explains {theme['topic_focus']}. "
            f"It highlights what teams should understand when documenting {clean_subject} in DITA."
        )
    return snippets


def _subject_guided_concept_body_snippets(subject: str, count: int, subtopics: list[str] | None = None) -> list[str]:
    clean_subject = re.sub(r"\s+", " ", (subject or "").strip()).strip(" .,:;!?")
    if not clean_subject:
        return []
    normalized_subtopics = _normalized_subtopics(subtopics, count)
    snippets: list[str] = []
    for index in range(1, max(1, count) + 1):
        if index <= len(normalized_subtopics):
            focus = normalized_subtopics[index - 1]
            snippets.append(
                f"This concept explains {focus} for {clean_subject}. "
                f"It connects that area back to the broader {clean_subject} model and the decisions teams need to understand."
            )
            continue
        theme = _subject_guided_theme(index)
        snippets.append(
            f"This concept explains {theme['concept_focus']} for {clean_subject}. "
            f"It connects that perspective back to the broader {clean_subject} domain."
        )
    return snippets


def _subject_guided_reference_property_seeds(subject: str, count: int, subtopics: list[str] | None = None) -> list[str]:
    clean_subject = re.sub(r"\s+", " ", (subject or "").strip()).strip(" .,:;!?").lower()
    if not clean_subject:
        return []
    slug = re.sub(r"[^a-z0-9]+", "-", clean_subject).strip("-") or "reference"
    normalized_subtopics = _normalized_subtopics(subtopics, count)
    if normalized_subtopics:
        return [
            f"{slug}-{re.sub(r'[^a-z0-9]+', '-', item.lower()).strip('-') or f'section-{index:02d}'}"
            for index, item in enumerate(normalized_subtopics, start=1)
        ]
    return [f"{slug}-{_subject_guided_theme(index)['slug']}-{index:02d}" for index in range(1, max(1, count) + 1)]


def _subject_guided_reference_detail_snippets(subject: str, count: int, subtopics: list[str] | None = None) -> list[str]:
    clean_subject = re.sub(r"\s+", " ", (subject or "").strip()).strip(" .,:;!?")
    if not clean_subject:
        return []
    title_subject = clean_subject[:1].upper() + clean_subject[1:]
    normalized_subtopics = _normalized_subtopics(subtopics, count)
    snippets: list[str] = []
    for index in range(1, max(1, count) + 1):
        if index <= len(normalized_subtopics):
            focus = normalized_subtopics[index - 1]
            snippets.append(
                f"This reference topic documents {focus} for {title_subject}. "
                f"It captures field-level details, expected values, and implementation notes teams need when working with {focus}."
            )
            continue
        theme = _subject_guided_theme(index)
        snippets.append(
            f"This reference topic documents {theme['reference_focus']} for {title_subject}. "
            f"It captures field-level details, expected values, and implementation notes for area {index:02d}."
        )
    return snippets


def _subject_guided_task_steps(subject: str, count: int, subtopics: list[str] | None = None) -> list[list[str]]:
    clean_subject = re.sub(r"\s+", " ", (subject or "").strip()).strip(" .,:;!?")
    if not clean_subject:
        return []
    normalized_subtopics = _normalized_subtopics(subtopics, count)
    kubernetes_like = bool(re.search(r"\bkubernetes\b|\bk8s\b", clean_subject, re.IGNORECASE))
    steps_by_topic: list[list[str]] = []
    for index in range(1, max(1, count) + 1):
        if index <= len(normalized_subtopics):
            focus = normalized_subtopics[index - 1]
            if kubernetes_like:
                steps_by_topic.append(
                    [
                        f"Review the current Kubernetes state for {focus}.",
                        f"Run the relevant kubectl commands or edit the manifest for {focus}.",
                        f"Apply the change or inspection for {focus} and capture the resulting status.",
                        f"Verify the expected cluster behavior for {focus} before closing the task.",
                    ]
                )
            else:
                steps_by_topic.append(
                    [
                        f"Review the current state for {focus} in {clean_subject}.",
                        f"Open the tools, files, or settings related to {focus}.",
                        f"Apply the change or inspection for {focus} and capture the result.",
                        f"Verify the expected outcome for {focus} before closing the task.",
                    ]
                )
            continue
        theme = _subject_guided_theme(index)
        label = theme["label"]
        steps_by_topic.append(
            [
                f"Review the {label} requirements for {clean_subject}.",
                f"Open the relevant {clean_subject} controls, files, or settings for {label}.",
                f"Apply the {label} changes and verify the expected behavior.",
                f"Record the final {label} state for {clean_subject}.",
            ]
        )
    return steps_by_topic


def _subject_guided_glossary_terms(subject: str, count: int) -> list[str]:
    clean_subject = re.sub(r"\s+", " ", (subject or "").strip()).strip(" .,:;!?")
    if not clean_subject:
        return []
    title_subject = clean_subject[:1].upper() + clean_subject[1:]
    if count <= 1:
        return [f"{title_subject} term"]
    return [f"{title_subject} term {index:02d}" for index in range(1, count + 1)]


def _subject_guided_glossary_definitions(subject: str, count: int) -> list[str]:
    clean_subject = re.sub(r"\s+", " ", (subject or "").strip()).strip(" .,:;!?")
    if not clean_subject:
        return []
    return [
        f"A glossary definition covering {clean_subject} terminology item {index:02d}."
        for index in range(1, max(1, count) + 1)
    ]


def _subject_guided_glossary_acronyms(subject: str, count: int) -> list[str]:
    clean_subject = re.sub(r"[^A-Za-z0-9]+", " ", (subject or "").strip()).strip()
    if not clean_subject:
        return []
    tokens = [token[:1].upper() for token in clean_subject.split()[:3] if token]
    base = "".join(tokens) or "GLS"
    return [f"{base}{index:02d}" for index in range(1, max(1, count) + 1)]


def _is_family_implied_required_element(contract: dict[str, Any], item: Any) -> bool:
    if not isinstance(contract, dict) or not isinstance(item, dict):
        return False
    name = str(item.get("name") or "").strip().lower()
    if not name:
        return False
    topic_family = str(contract.get("topic_family") or "").strip().lower()
    include_map = bool(contract.get("include_map"))
    if topic_family in {"topic", "concept", "task", "reference", "glossentry"} and name == topic_family:
        return True
    if include_map and name in {"map", "ditamap", "bookmap"}:
        return True
    return False


def _contract_metadata_values(contract: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    if not isinstance(contract, dict):
        return values
    for item in contract.get("required_metadata") or []:
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field_name") or "").strip().lower()
        field_value = str(item.get("value") or "").strip()
        if field_name and field_value:
            values[field_name] = field_value
    return values


def _contract_topicref_attribute_distributions(contract: dict[str, Any]) -> list[dict[str, Any]]:
    distributions: list[dict[str, Any]] = []
    if not isinstance(contract, dict):
        return distributions
    for item in contract.get("topicref_attribute_distributions") or []:
        if not isinstance(item, dict):
            continue
        attribute_name = str(item.get("attribute_name") or "").strip().lower()
        attribute_value = str(item.get("attribute_value") or "").strip()
        try:
            count = max(1, int(item.get("count") or 1))
        except (TypeError, ValueError):
            count = 1
        if not attribute_name or not attribute_value:
            continue
        distributions.append(
            {
                "attribute_name": attribute_name,
                "attribute_value": attribute_value,
                "count": count,
            }
        )
    return distributions


def _contract_domain_subtopics(contract: dict[str, Any]) -> list[str]:
    if not isinstance(contract, dict):
        return []
    decomposition = contract.get("domain_decomposition") or {}
    if not isinstance(decomposition, dict):
        return []
    return [str(item).strip() for item in (decomposition.get("subtopics") or []) if str(item).strip()]


def _contract_supported_map_required_attributes(contract: dict[str, Any]) -> list[dict[str, Any]]:
    supported: list[dict[str, Any]] = []
    if not isinstance(contract, dict):
        return supported
    for item in contract.get("required_attributes") or []:
        if not isinstance(item, dict):
            continue
        attribute_name = str(item.get("attribute_name") or "").strip().lower()
        scope = str(item.get("scope") or "").strip().lower()
        values = [str(value or "").strip() for value in (item.get("required_values") or []) if str(value or "").strip()]
        if attribute_name == "processing-role" and scope == "bundle" and values:
            supported.append(
                {
                    "attribute_name": attribute_name,
                    "scope": scope,
                    "required_values": values,
                }
            )
    return supported


def _contract_keyed_link_requirements(contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(contract, dict):
        return []
    return [item for item in (contract.get("keyed_link_requirements") or []) if isinstance(item, dict)]


def _contract_filename_requirements(contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(contract, dict):
        return []
    return [item for item in (contract.get("filename_requirements") or []) if isinstance(item, dict)]


def _contract_is_xref_variety_request(contract: dict[str, Any]) -> bool:
    if not isinstance(contract, dict):
        return False
    construct_names = {
        str(item.get("name") or "").strip().lower()
        for item in (contract.get("construct_semantics") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    required_element_names = {
        str(item.get("name") or "").strip().lower()
        for item in (contract.get("required_elements") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    if "xref" not in construct_names and "xref" not in required_element_names:
        return False
    text = "\n".join(
        str(part or "")
        for part in (
            contract.get("execution_text"),
            contract.get("execution_instructions"),
            contract.get("summary"),
        )
    )
    return bool(_XREF_VARIETY_REQUEST_PATTERN.search(text))


def _contract_supported_deterministic_required_attributes(contract: dict[str, Any]) -> list[dict[str, Any]]:
    supported = _contract_supported_map_required_attributes(contract)
    if not isinstance(contract, dict):
        return supported
    structure_requirements = [
        item
        for item in (contract.get("structure_requirements") or [])
        if isinstance(item, dict)
    ]
    language_markers = {
        f"language-{str(item.get('language') or '').strip().lower()}"
        for item in structure_requirements
        if str(item.get("structure_name") or "").strip().lower() == "codeblock"
        and str(item.get("language") or "").strip()
    }
    for item in contract.get("required_attributes") or []:
        if not isinstance(item, dict):
            continue
        attribute_name = str(item.get("attribute_name") or "").strip().lower()
        scope = str(item.get("scope") or "").strip().lower()
        values = {str(value or "").strip().lower() for value in (item.get("required_values") or []) if str(value or "").strip()}
        supported_elements = {str(value or "").strip().lower() for value in (item.get("supported_elements") or []) if str(value or "").strip()}
        if (
            attribute_name == "outputclass"
            and scope == "artifact"
            and values
            and values.issubset(language_markers)
            and (not supported_elements or "codeblock" in supported_elements)
        ):
            supported.append(item)
    return supported


def _contract_supported_deterministic_construct_semantics(
    contract: dict[str, Any],
    construct_semantics: list[dict[str, Any]],
) -> bool:
    topic_family = str(contract.get("topic_family") or "").strip().lower()
    structure_names = {
        str(item.get("structure_name") or "").strip().lower()
        for item in (contract.get("structure_requirements") or [])
        if isinstance(item, dict) and str(item.get("structure_name") or "").strip()
    }
    required_contract_constructs = {
        str(item.get("name") or "").strip().lower()
        for item in construct_semantics
        if bool(item.get("requires_contract_path")) and str(item.get("name") or "").strip()
    }
    if not required_contract_constructs:
        return True
    if topic_family == "reference" and required_contract_constructs.issubset({"codeblock"}) and "codeblock" in structure_names:
        return True
    return False


def _contract_requires_llm_path(contract: dict[str, Any]) -> bool:
    if not isinstance(contract, dict):
        return False
    topic_family = str(contract.get("topic_family") or "").strip().lower()
    bundle_type = str(contract.get("bundle_type") or "").strip().lower()
    glossary_usage_mode = str(contract.get("glossary_usage_mode") or "standalone").strip().lower()
    construct_semantics = [
        item
        for item in (contract.get("construct_semantics") or [])
        if isinstance(item, dict)
    ]
    if topic_family == "map":
        return True
    if glossary_usage_mode != "standalone":
        return True
    if any(bool(item.get("requires_contract_path")) for item in construct_semantics) and not _contract_supported_deterministic_construct_semantics(contract, construct_semantics):
        return True
    if bundle_type in {"mixed_bundle", "map_bundle"} and topic_family not in {"task", "concept", "reference", "glossentry"}:
        return True
    preferred_structures = {
        str(item or "").strip().lower()
        for item in (contract.get("preferred_structures") or [])
        if str(item or "").strip()
    }
    if preferred_structures and not preferred_structures.issubset(_SUPPORTED_DETERMINISTIC_STRUCTURES.get(topic_family, set())):
        return True
    effective_required_elements = [
        item
        for item in (contract.get("required_elements") or [])
        if not _is_family_implied_required_element(contract, item)
    ]
    supported_elements = _SUPPORTED_DETERMINISTIC_ELEMENTS.get(topic_family, set())
    if any(str(item.get("name") or "").strip().lower() not in supported_elements for item in effective_required_elements if isinstance(item, dict)):
        return True
    raw_required_attributes = contract.get("required_attributes") or []
    supported_attributes = _contract_supported_deterministic_required_attributes(contract)
    if raw_required_attributes and len(supported_attributes) != len(raw_required_attributes):
        return True
    return bundle_type in {"mixed_bundle", "map_bundle"} and topic_family not in {"task", "concept", "reference", "topic", "glossentry"}


def _contract_required_constructs(contract: dict[str, Any]) -> list[dict[str, Any]]:
    required_constructs: list[dict[str, Any]] = []
    topic_family = str(contract.get("topic_family") or "").strip().lower()
    include_map = bool(contract.get("include_map"))
    counts = contract.get("counts") if isinstance(contract.get("counts"), dict) else {}
    if include_map:
        required_constructs.append({"name": "map", "min_count": 1})
    if topic_family in {"topic", "concept", "task", "reference", "glossentry"}:
        min_count = 1
        try:
            min_count = max(1, int(counts.get(topic_family, 1) or 1))
        except (TypeError, ValueError):
            min_count = 1
        required_constructs.append({"name": topic_family, "min_count": min_count})
    for item in contract.get("required_elements") or []:
        if not isinstance(item, dict):
            continue
        element_name = str(item.get("name") or "").strip().lower()
        if element_name:
            required_constructs.append({"name": element_name, "min_count": 1})
    for item in contract.get("construct_semantics") or []:
        if not isinstance(item, dict):
            continue
        construct_name = str(item.get("name") or "").strip().lower()
        if construct_name:
            required_constructs.append({"name": construct_name, "min_count": 1})
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in required_constructs:
        key = (str(item["name"]), int(item["min_count"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _contract_instruction_text(contract: dict[str, Any]) -> str:
    lines: list[str] = []
    subject = str(contract.get("subject") or "").strip()
    bundle_type = str(contract.get("bundle_type") or "").strip().replace("_", " ")
    topic_family = str(contract.get("topic_family") or "").strip()
    if bundle_type:
        lines.append(f"Generate a {bundle_type}.")
    if topic_family:
        lines.append(f"Use `{topic_family}` as the DITA topic family unless the contract explicitly includes a map.")
    if subject:
        lines.append(f"Keep the content focused on `{subject}`.")
    construct_names = [
        str(item.get("name") or "").strip()
        for item in (contract.get("construct_semantics") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    if construct_names:
        lines.append("Honor these DITA construct semantics: " + ", ".join(construct_names) + ".")
        companions = [
            str(companion).strip()
            for item in (contract.get("construct_semantics") or [])
            if isinstance(item, dict)
            for companion in (item.get("required_companion_artifacts") or [])
            if str(companion).strip()
        ]
        if companions:
            lines.append("Required companion artifacts: " + ", ".join(dict.fromkeys(companions)) + ".")
        validation_rules = [
            str(rule).strip()
            for item in (contract.get("construct_semantics") or [])
            if isinstance(item, dict)
            for rule in (item.get("validation_rules") or [])
            if str(rule).strip()
        ]
        if validation_rules:
            lines.append("Post-generation validation rules: " + ", ".join(dict.fromkeys(validation_rules)) + ".")
    required_elements = [
        f"<{str(item.get('name') or '').strip()}>"
        for item in (contract.get("required_elements") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    if required_elements:
        lines.append("Required DITA elements: " + ", ".join(required_elements) + ".")
    required_attributes: list[str] = []
    for item in contract.get("required_attributes") or []:
        if not isinstance(item, dict):
            continue
        attr_name = str(item.get("attribute_name") or "").strip()
        if not attr_name:
            continue
        values = [str(value).strip() for value in (item.get("required_values") or []) if str(value).strip()]
        if values:
            required_attributes.append(f"@{attr_name}=" + "|".join(values))
        else:
            required_attributes.append(f"@{attr_name}")
    if required_attributes:
        lines.append("Required DITA attributes: " + ", ".join(required_attributes) + ".")
    topicref_attribute_distributions = _contract_topicref_attribute_distributions(contract)
    if topicref_attribute_distributions:
        lines.append(
            "Required map topicref distributions: "
            + ", ".join(
                f"{item['count']} topicref{'s' if item['count'] != 1 else ''} with @{item['attribute_name']}={item['attribute_value']}"
                for item in topicref_attribute_distributions
            )
            + "."
        )
    required_metadata = _contract_metadata_values(contract)
    if required_metadata:
        lines.append(
            "Required prolog metadata: "
            + ", ".join(f"{name}={value}" for name, value in required_metadata.items())
            + "."
        )
    domain_subtopics = _contract_domain_subtopics(contract)
    if domain_subtopics:
        lines.append("Cover these domain subtopics distinctly: " + ", ".join(domain_subtopics) + ".")
    keyed_links = _contract_keyed_link_requirements(contract)
    filename_requirements = _contract_filename_requirements(contract)
    if keyed_links:
        lines.append(
            "Use map-defined external keydefs and topic xref keyrefs: "
            + "; ".join(
                f"{item.get('key_name') or 'external-docs'} -> {item.get('href') or 'https://example.com/docs'}"
                for item in keyed_links
            )
            + "."
        )
    if filename_requirements:
        lines.append(
            "Use these safe physical filenames: "
            + ", ".join(
                f"{item.get('requested_name')} -> {item.get('safe_name')}"
                for item in filename_requirements
                if item.get("safe_name")
            )
            + "."
        )
    glossary_usage_mode = str(contract.get("glossary_usage_mode") or "standalone").strip().lower()
    if glossary_usage_mode != "standalone":
        lines.append("Keep the glossary usage linkage from the reviewed contract intact.")
    content_mode = str(contract.get("content_mode") or "").strip()
    if content_mode:
        lines.append(f"Content mode: {content_mode}.")
    warnings = [str(item).strip() for item in (contract.get("warnings") or []) if str(item).strip()]
    if warnings:
        lines.append("Do not ignore these generation constraints/warnings: " + " ".join(warnings[:3]))
    return "\n".join(lines).strip()


def _build_generator_plan_from_bundle_contract(
    contract: dict[str, Any] | None,
    *,
    evidence_pack: dict[str, Any] | None = None,
    clean_instructions: str | None = None,
    trace_id: str | None = None,
    jira_id: str | None = None,
) -> GeneratorInvocationPlan | None:
    if not isinstance(contract, dict):
        return None

    bundle_type = str(contract.get("bundle_type") or "").strip().lower()
    topic_family = str(contract.get("topic_family") or "").strip().lower()
    include_map = bool(contract.get("include_map"))
    subject = str(contract.get("subject") or "").strip()
    example_request = bool(contract.get("example_request"))
    example_construct = str(contract.get("example_construct") or "").strip().lower()
    example_shape = str(contract.get("example_shape") or "unspecified").strip().lower()
    metadata_values = _contract_metadata_values(contract)
    topicref_attribute_distributions = _contract_topicref_attribute_distributions(contract)
    domain_subtopics = _contract_domain_subtopics(contract)
    keyed_link_requirements = _contract_keyed_link_requirements(contract)
    filename_requirements = _contract_filename_requirements(contract)
    construct_semantics = [
        item
        for item in (contract.get("construct_semantics") or [])
        if isinstance(item, dict)
    ]
    required_element_names = {
        str(item.get("name") or "").strip().lower()
        for item in (contract.get("required_elements") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }

    selected: SelectedRecipe | None = None
    rationale: list[str] = []

    if example_request and example_construct == "keyscope" and example_shape in {"minimal_demo", "full_demo"}:
        selected = SelectedRecipe(
            recipe_id="keyscope_demo",
            params={
                "demo_shape": example_shape,
                "include_qualified_keyrefs": example_shape == "full_demo",
            },
            evidence_used=[],
        )
        rationale.append(
            f"Applied the reviewed `{example_construct}` example contract using the deterministic {example_shape.replace('_', ' ')} bundle."
        )
        return GeneratorInvocationPlan(recipes=[selected], selection_rationale=rationale)

    if _contract_is_xref_variety_request(contract):
        selected = SelectedRecipe(
            recipe_id="xref_variety_bundle",
            params={
                "subject": subject or "DITA cross references",
                "topic_title": "Cross-reference patterns",
                "target_title": "Cross-reference targets",
                "map_title": "Cross-reference pattern map",
            },
            evidence_used=[],
        )
        rationale.append("Applied deterministic xref variety bundle planning from the reviewed construct contract.")
        return GeneratorInvocationPlan(recipes=[selected], selection_rationale=rationale)

    if keyed_link_requirements:
        requirement = keyed_link_requirements[0]
        selected = SelectedRecipe(
            recipe_id="external_keydef_xref_bundle",
            params={
                "key_name": str(requirement.get("key_name") or "external-docs").strip() or "external-docs",
                "href": str(requirement.get("href") or "https://example.com/docs").strip() or "https://example.com/docs",
                "format": str(requirement.get("format") or "html").strip() or "html",
                "scope": str(requirement.get("scope") or "external").strip() or "external",
                "link_text": str(requirement.get("link_text") or "External documentation").strip() or "External documentation",
                "topic_title": "Using external keyed references",
                "map_title": "External keyed references map",
            },
            evidence_used=[],
        )
        rationale.append("Applied deterministic external keydef/xref bundle planning from the reviewed contract.")
        return GeneratorInvocationPlan(recipes=[selected], selection_rationale=rationale)

    map_construct_recipe = _contract_single_map_construct_recipe(contract)
    if map_construct_recipe:
        construct_name, recipe_id = map_construct_recipe
        topic_count = _contract_count(contract, "topic", 2)
        selected = SelectedRecipe(
            recipe_id=recipe_id,
            params={
                "topic_count": topic_count,
                "id_prefix": "t",
            },
            evidence_used=[],
        )
        rationale.append(
            f"Applied deterministic map-construct bundle planning for `{construct_name}` with {topic_count} companion topic file{'s' if topic_count != 1 else ''}."
        )
        return GeneratorInvocationPlan(recipes=[selected], selection_rationale=rationale)

    if _contract_requires_llm_path(contract):
        representative_xml = pre_extract_representative_xml((evidence_pack or {}).get("primary") or {})
        contract_instructions = _contract_instruction_text(contract)
        instruction_parts = [part for part in [contract_instructions, clean_instructions] if part]
        selected = SelectedRecipe(
            recipe_id="llm_generated_dita",
            params={
                "evidence_pack": evidence_pack or {},
                "representative_xml": representative_xml or [],
                "trace_id": trace_id,
                "jira_id": jira_id,
                "additional_instructions": "\n\n".join(instruction_parts) if instruction_parts else None,
                "recipe_execution_contract": {
                    "recipe_id": "dita_generation_contract",
                    "required_constructs": _contract_required_constructs(contract),
                    "required_attributes": contract.get("required_attributes") or [],
                    "required_elements": contract.get("required_elements") or [],
                    "required_metadata": contract.get("required_metadata") or [],
                    "topicref_attribute_distributions": topicref_attribute_distributions,
                    "preferred_structures": contract.get("preferred_structures") or [],
                    "structure_requirements": contract.get("structure_requirements") or [],
                    "keyed_link_requirements": keyed_link_requirements,
                    "filename_requirements": filename_requirements,
                    "construct_semantics": construct_semantics,
                    "construct_validation_rules": [
                        str(rule).strip()
                        for item in construct_semantics
                        for rule in (item.get("validation_rules") or [])
                        if str(rule).strip()
                    ],
                    "required_companion_artifacts": [
                        str(companion).strip()
                        for item in construct_semantics
                        for companion in (item.get("required_companion_artifacts") or [])
                        if str(companion).strip()
                    ],
                    "domain_decomposition": contract.get("domain_decomposition") or None,
                    "bundle_type": bundle_type or "single_topic",
                    "topic_family": topic_family or "topic",
                    "glossary_usage_mode": contract.get("glossary_usage_mode") or "standalone",
                    "content_mode": contract.get("content_mode") or "auto_hybrid",
                    "subject": subject,
                    "repair_hints": [
                        "Honor every required DITA element and attribute from the reviewed generation contract.",
                        "Do not replace required DITA structures with prose-only approximations.",
                        "Honor structure_requirements exactly when present, including codeblock language and table row/column counts.",
                    ],
                },
            },
            evidence_used=[],
        )
        rationale.append("Applied the reviewed DITA generation contract through the LLM fallback path because the prompt carries explicit structural constraints.")
        return GeneratorInvocationPlan(recipes=[selected], selection_rationale=rationale)

    if topic_family == "task":
        count = _contract_count(contract, "task")
        params: dict[str, Any] = {
            "topic_count": count,
            "include_map": include_map,
            "include_choicetable": "choicetable" in required_element_names,
        }
        if filename_requirements:
            params["content_filenames"] = [str(item.get("safe_name") or "").strip() for item in filename_requirements if str(item.get("safe_name") or "").strip()]
        params["content_include_stepxmp"] = "stepxmp" in required_element_names
        if metadata_values:
            params["content_prolog_metadata"] = metadata_values
        if topicref_attribute_distributions:
            params["map_topicref_attribute_distributions"] = topicref_attribute_distributions
        if subject:
            params["content_titles"] = _subject_guided_titles(subject, "task", count, domain_subtopics)
            params["content_shortdescs"] = _subject_guided_shortdescs(subject, "task", count, domain_subtopics)
            params["content_steps_by_topic"] = _subject_guided_task_steps(subject, count, domain_subtopics)
        selected = SelectedRecipe(recipe_id="task_topics", params=params, evidence_used=[])
        rationale.append(f"Applied reviewed task bundle contract for {count} task topic{'s' if count != 1 else ''}.")
    elif topic_family == "concept":
        count = _contract_count(contract, "concept")
        params = {
            "topic_count": count,
            "include_map": include_map,
        }
        if filename_requirements:
            params["content_filenames"] = [str(item.get("safe_name") or "").strip() for item in filename_requirements if str(item.get("safe_name") or "").strip()]
        if metadata_values:
            params["content_prolog_metadata"] = metadata_values
        if topicref_attribute_distributions:
            params["map_topicref_attribute_distributions"] = topicref_attribute_distributions
        if subject:
            params["content_titles"] = _subject_guided_titles(subject, "concept", count, domain_subtopics)
            params["content_shortdescs"] = _subject_guided_shortdescs(subject, "concept", count, domain_subtopics)
            params["content_body_snippets"] = _subject_guided_concept_body_snippets(subject, count, domain_subtopics)
        selected = SelectedRecipe(recipe_id="concept_topics", params=params, evidence_used=[])
        rationale.append(f"Applied reviewed concept bundle contract for {count} concept topic{'s' if count != 1 else ''}.")
    elif topic_family == "reference":
        count = _contract_count(contract, "reference")
        params = {
            "topic_count": count,
            "include_map": include_map,
            "include_choicetable": "simpletable" in required_element_names,
        }
        if filename_requirements:
            params["content_filenames"] = [str(item.get("safe_name") or "").strip() for item in filename_requirements if str(item.get("safe_name") or "").strip()]
        if contract.get("structure_requirements"):
            params["structure_requirements"] = contract.get("structure_requirements") or []
        if metadata_values:
            params["content_prolog_metadata"] = metadata_values
        if topicref_attribute_distributions:
            params["map_topicref_attribute_distributions"] = topicref_attribute_distributions
        if subject:
            params["content_titles"] = _subject_guided_titles(subject, "reference", count, domain_subtopics)
            params["content_shortdescs"] = _subject_guided_shortdescs(subject, "reference", count, domain_subtopics)
            params["content_property_seeds"] = _subject_guided_reference_property_seeds(subject, count, domain_subtopics)
            params["content_detail_snippets"] = _subject_guided_reference_detail_snippets(subject, count, domain_subtopics)
        selected = SelectedRecipe(recipe_id="reference_topics", params=params, evidence_used=[])
        rationale.append(f"Applied reviewed reference bundle contract for {count} reference topic{'s' if count != 1 else ''}.")
    elif topic_family == "topic":
        count = _contract_count(contract, "topic")
        params = {
            "topic_count": count,
            "include_map": include_map,
        }
        if filename_requirements:
            params["content_filenames"] = [str(item.get("safe_name") or "").strip() for item in filename_requirements if str(item.get("safe_name") or "").strip()]
        if metadata_values:
            params["content_prolog_metadata"] = metadata_values
        if topicref_attribute_distributions:
            params["map_topicref_attribute_distributions"] = topicref_attribute_distributions
        if subject:
            params["content_titles"] = _subject_guided_titles(subject, "topic", count, domain_subtopics)
            params["content_shortdescs"] = _subject_guided_shortdescs(subject, "topic", count, domain_subtopics)
            params["content_body_snippets"] = _subject_guided_topic_body_snippets(subject, count, domain_subtopics)
        selected = SelectedRecipe(recipe_id="topic_topics", params=params, evidence_used=[])
        rationale.append(f"Applied reviewed generic topic bundle contract for {count} topic file{'s' if count != 1 else ''}.")
    elif topic_family == "glossentry":
        count = _contract_count(contract, "glossentry")
        params = {"entry_count": count}
        if subject:
            params["content_terms"] = _subject_guided_glossary_terms(subject, count)
            params["content_definitions"] = _subject_guided_glossary_definitions(subject, count)
            params["content_acronyms"] = _subject_guided_glossary_acronyms(subject, count)
        selected = SelectedRecipe(recipe_id="glossary", params=params, evidence_used=[])
        rationale.append(f"Applied reviewed glossary bundle contract for {count} glossary entr{'y' if count == 1 else 'ies'}.")
        if include_map or bundle_type == "mixed_bundle":
            rationale.append("Glossary generation uses the glossary recipe, which includes a supporting map.")

    if selected is None:
        return None

    if include_map and topic_family in {"task", "concept", "reference"}:
        rationale.append("Map generation was preserved from the reviewed bundle contract.")
    if subject:
        rationale.append(f"Subject focus: {subject}.")
    if domain_subtopics:
        rationale.append(
            "Domain decomposition supplied distinct subtopics: "
            + ", ".join(domain_subtopics[:5])
            + ("..." if len(domain_subtopics) > 5 else "")
        )
    if construct_semantics:
        rationale.append(
            "Construct-aware planning applied for: "
            + ", ".join(str(item.get("name") or "").strip() for item in construct_semantics if str(item.get("name") or "").strip())
            + "."
        )
    if metadata_values:
        rationale.append("Prolog metadata from the reviewed contract was preserved in the deterministic generator path.")
    if topicref_attribute_distributions:
        rationale.append("Map topicref attribute distribution from the reviewed contract was preserved in the deterministic generator path.")

    return GeneratorInvocationPlan(recipes=[selected], selection_rationale=rationale)


def _run_build_validation(*, scenario_dir: Path) -> dict[str, Any]:
    if not DITA_GENERATION_ENABLE_BUILD_VALIDATION:
        return {
            "enabled": False,
            "status": "not_run",
            "validator": DITA_GENERATION_BUILD_VALIDATOR,
            "message": "DITA build validation is disabled for this environment.",
            "issues": [],
        }
    return {
        "enabled": True,
        "status": "failed",
        "validator": DITA_GENERATION_BUILD_VALIDATOR,
        "message": (
            f"{DITA_GENERATION_BUILD_VALIDATOR} build validation is enabled, but no runtime validator is configured "
            "for generate_dita yet."
        ),
        "issues": [
            "Build validation was requested but no DITA-OT/build runner is configured in this environment."
        ],
    }


async def run_generate_from_text(
    *,
    text: str,
    instructions: str | None,
    bundle_contract: dict[str, Any] | None = None,
    run_id: str,
    request: Request | None,
    user_id: str,
    tenant_id: str,
    freeform_mode: bool = False,
    skip_rag_check: bool = False,
    progress_run_id: str | None = None,
) -> dict[str, Any]:
    """Shared generate-from-text execution used by the API route and chat tools."""
    from app.services.dita_pipeline_orchestrator import run_intent_pipeline_with_execution

    pid = progress_run_id or run_id
    resolved_text, real_jira_id, resolution_warning = resolve_text_for_generate_from_text(text)
    jira_id = real_jira_id or f"TEXT-{run_id[:8]}"
    update_generate_progress(
        pid,
        status="running",
        stage="planning",
        jira_id=jira_id,
        scenarios_total=1,
        scenarios_done=0,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    trace_id = str(uuid4())
    start_llm_trace(trace_id)
    start_time = time.perf_counter()
    obs_log.info(
        "dita_generation_started",
        run_id=run_id,
        session_id=pid,
        trace_id=trace_id,
        topic_count=1,
        scenarios_total=1,
    )

    evidence_pack = build_evidence_pack_from_text(resolved_text, run_id, forced_issue_key=real_jira_id)
    clean_instructions = (instructions or "").strip() or None
    if clean_instructions:
        primary = evidence_pack.get("primary") or {}
        description = (primary.get("description") or "").strip()
        merged_description = (
            f"{description}\n\nAdditional instructions / refinements:\n{clean_instructions}"
            if description
            else clean_instructions
        )
        evidence_pack = {**evidence_pack, "primary": {**primary, "description": merged_description}}

    rag_status = check_rag_readiness()
    if not skip_rag_check and not rag_status["any_ready"]:
        raise HTTPException(status_code=503, detail=rag_status["message"])
    if skip_rag_check and not rag_status["any_ready"]:
        rag_status["rag_warning"] = (
            "RAG sources not indexed. For better DITA accuracy, run POST /api/v1/ai/crawl-aem-guides "
            "and POST /api/v1/ai/index-dita-pdf, then retry."
        )

    storage = get_storage()
    temp_base = storage.base_path / "ai_runs" / jira_id / run_id
    temp_base.mkdir(parents=True, exist_ok=True)
    scenario_dir = temp_base / "S1_MIN_REPRO"
    scenario_dir.mkdir(parents=True, exist_ok=True)

    exec_result: dict[str, Any] | None = None
    plan: GeneratorInvocationPlan | None = None
    pipeline_out: dict[str, Any] | None = None
    generation_llm_stage: dict[str, Any] = {
        "llm_draft_used": False,
        "path": "deterministic_only",
        "fields": [],
    }

    try:
        if freeform_mode:
            from app.services.freeform_dita_generation_service import run_freeform_generation
            update_generate_progress(pid, stage="freeform_generation", message="LLM is reasoning about the domain and generating DITA...")
            exec_result = await run_freeform_generation(
                prompt=text,
                jira_id=jira_id,
                run_id=run_id,
                scenario_dir=scenario_dir,
                trace_id=trace_id,
            )
            if exec_result.get("error"):
                raise ValueError(f"FREEFORM_GENERATION_FAILED: {exec_result['error']}")
            generation_llm_stage = {
                "llm_draft_used": True,
                "path": "freeform_llm_generation",
                "fields": ["topic_outline", "dita_xml"],
            }

        contract_plan = _build_generator_plan_from_bundle_contract(
            bundle_contract,
            evidence_pack=evidence_pack,
            clean_instructions=clean_instructions,
            trace_id=trace_id,
            jira_id=jira_id,
        ) if not freeform_mode else None
        if contract_plan is not None:
            plan = contract_plan
            update_generate_progress(
                pid,
                stage="contract_planning",
                message="Applying the reviewed DITA bundle contract...",
            )
        elif GENERATE_FROM_TEXT_USE_INTENT_PIPELINE:
            update_generate_progress(pid, stage="intent_pipeline", message="Analyzing intent and selecting recipe...")
            pipeline_out = await run_intent_pipeline_with_execution(
                evidence_pack,
                jira_id,
                scenario_dir,
                seed=run_id,
                trace_id=trace_id,
                user_instructions=clean_instructions,
            )
            invocation = pipeline_out.get("invocation_plan")
            if invocation is not None:
                plan = invocation
            exec_result = pipeline_out["exec_result"]
            semantic_report = pipeline_out.get("semantic_report")
            if semantic_report and not semantic_report.ok and exec_result:
                for violation in semantic_report.violations:
                    exec_result.setdefault("warnings", []).append(
                        f"semantic:{violation.rule_id}: {violation.message}"
                    )
        elif GENERATE_FROM_TEXT_USE_PIPELINE:
            pipeline_result = await run_recipe_pipeline(evidence_pack, jira_id, trace_id=trace_id)
            per_scenario = pipeline_result.get("per_scenario") or {}
            plan_dict = (per_scenario.get("S1_MIN_REPRO") or {}).get("plan") or {}
            plan = GeneratorInvocationPlan.model_validate(plan_dict)
        else:
            representative_xml = pre_extract_representative_xml(evidence_pack.get("primary") or {})
            plan = GeneratorInvocationPlan(
                recipes=[
                    SelectedRecipe(
                        recipe_id="llm_generated_dita",
                        params={
                            "evidence_pack": evidence_pack,
                            "representative_xml": representative_xml or [],
                            "trace_id": trace_id,
                            "jira_id": jira_id,
                            "additional_instructions": None,
                        },
                        evidence_used=[],
                    )
                ],
                selection_rationale=["generate-from-text: natural language chat"],
            )

        if plan is not None and len(plan.recipes) == 1:
            recipe = plan.recipes[0]
            if str(recipe.recipe_id or "").strip() == "llm_generated_dita":
                generation_llm_stage = {
                    "llm_draft_used": True,
                    "path": "llm_fallback_generation",
                    "fields": ["xml_bundle"],
                }
            else:
                updated_recipe, stage_meta = await _maybe_apply_llm_deterministic_drafts(
                    selected=recipe,
                    contract=bundle_contract,
                    trace_id=trace_id,
                    jira_id=jira_id,
                )
                if updated_recipe is not recipe:
                    plan = GeneratorInvocationPlan(
                        recipes=[updated_recipe],
                        selection_rationale=list(plan.selection_rationale or []),
                    )
                generation_llm_stage = stage_meta

        if exec_result is None:
            assert plan is not None
            update_generate_progress(pid, stage="generating", message="Generating DITA...")
            exec_result = await asyncio.to_thread(
                execute_plan,
                plan,
                str(scenario_dir),
                seed=run_id[:8],
                skip_experience_league_companion=True,
            )

        update_generate_progress(pid, stage="enriching", message="Enriching DITA...")
        await asyncio.to_thread(enrich_dita_folder, scenario_dir)
        await asyncio.to_thread(auto_fix_dita_folder, scenario_dir)

        update_generate_progress(pid, stage="validating", message="Validating...")
        validation_result = await asyncio.to_thread(validate_dita_folder, scenario_dir)
        generated_xml_files: dict[str, str] = {}
        for path in scenario_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".dita", ".ditamap", ".xml"}:
                continue
            generated_xml_files[path.name] = path.read_text(encoding="utf-8", errors="ignore")
        if not generated_xml_files:
            executor_warnings = [
                str(item).strip()
                for item in ((exec_result or {}).get("warnings") or [])
                if str(item).strip()
            ]
            if executor_warnings:
                raise ValueError(
                    "GENERATION_EXECUTION_FAILED: No generated DITA files were produced. "
                    "Executor warnings: " + " | ".join(executor_warnings[:8])
                )
        build_validation = _run_build_validation(scenario_dir=scenario_dir)
        if build_validation.get("enabled") and str(build_validation.get("status") or "").strip().lower() == "failed":
            raise ValueError("GENERATION_BUILD_VALIDATION_FAILED: " + str(build_validation.get("message") or "").strip())
        contract_validation_issues = validate_generated_bundle_against_contract(
            contract=bundle_contract,
            generated_files=generated_xml_files,
            enforce_headers=True,
        )
        if contract_validation_issues:
            raise ValueError("GENERATION_CONTRACT_VIOLATION: " + " | ".join(contract_validation_issues))
    except ValueError as exc:
        logger.warning_structured(
            "Generate-from-text rejected weak or invalid DITA output",
            extra_fields={"run_id": run_id, "jira_id": jira_id, "error": str(exc)},
        )
        set_generate_progress(
            pid,
            {
                "status": "failed",
                "error": str(exc),
                "user_id": user_id,
                "tenant_id": tenant_id,
            },
        )
        clear_llm_trace(trace_id)
        if request is not None:
            raise HTTPException(status_code=422, detail=str(exc))
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger.error_structured(
            "Generate-from-text execution failed",
            extra_fields={"run_id": run_id, "jira_id": jira_id, "error": str(exc)},
            exc_info=True,
        )
        set_generate_progress(
            pid,
            {
                "status": "failed",
                "error": sanitize_error_for_client(exc),
                "user_id": user_id,
                "tenant_id": tenant_id,
            },
        )
        clear_llm_trace(trace_id)
        if request is not None:
            raise HTTPException(status_code=500, detail=sanitize_error_for_client(exc))
        raise

    plans = {
        "S1_MIN_REPRO": {
            "recipes_executed": exec_result.get("recipes_executed", ["llm_generated_dita"]),
            "warnings": exec_result.get("warnings", []),
        }
    }
    validation_results = {"S1_MIN_REPRO": validation_result or {"errors": [], "warnings": []}}
    scenario_outputs = {"S1_MIN_REPRO": scenario_dir}

    write_scenario_metadata(
        scenario_dir,
        jira_id=jira_id,
        scenario_type="MIN_REPRO",
        generator_recipes=plans["S1_MIN_REPRO"].get("recipes_executed", []),
        evidence=[],
    )

    update_generate_progress(pid, stage="bundling", message="Building bundle...")
    bundle_path = await asyncio.to_thread(
        build_bundle,
        jira_id,
        run_id,
        scenario_outputs,
        evidence_pack,
        plans,
        validation_results,
    )
    zip_path = await asyncio.to_thread(package_bundle, bundle_path, jira_id, run_id)

    bundle_summary = _summarize_generated_bundle(scenario_outputs)
    llm_summary = summarize_llm_trace(
        trace_id,
        default_path=str(generation_llm_stage.get("path") or "deterministic_only"),
        llm_used_path=str(generation_llm_stage.get("path") or "llm_assisted"),
    )
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    obs_log.info(
        "dita_generation_completed",
        run_id=run_id,
        session_id=pid,
        trace_id=trace_id,
        topic_count=bundle_summary["artifact_counts"]["topic_files"],
        duration_ms=duration_ms,
        jira_id=jira_id,
    )

    required_metadata = [
        str(item.get("field_name") or "").strip()
        for item in (bundle_contract.get("required_metadata") or [])
        if isinstance(item, dict) and str(item.get("field_name") or "").strip()
    ] if isinstance(bundle_contract, dict) else []
    result: dict[str, Any] = {
        "jira_id": jira_id,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "generation_contract": bundle_contract,
        "contract_summary": (
            {
                "bundle_type": str(bundle_contract.get("bundle_type") or "").strip(),
                "topic_family": str(bundle_contract.get("topic_family") or "").strip(),
                "subject": str(bundle_contract.get("subject") or "").strip() or None,
                "include_map": bool(bundle_contract.get("include_map")),
                "content_mode": str(bundle_contract.get("content_mode") or "").strip() or None,
                "glossary_usage_mode": str(bundle_contract.get("glossary_usage_mode") or "").strip() or None,
                "example_request": bool(bundle_contract.get("example_request")),
                "example_construct": str(bundle_contract.get("example_construct") or "").strip() or None,
                "example_shape": str(bundle_contract.get("example_shape") or "").strip() or None,
            }
            if isinstance(bundle_contract, dict)
            else None
        ),
        "contract_compliance": (
            {
                "status": "satisfied",
                "required_elements": [
                    str(item.get("name") or "").strip()
                    for item in (bundle_contract.get("required_elements") or [])
                    if isinstance(item, dict) and str(item.get("name") or "").strip()
                ],
                "required_attributes": [
                    str(item.get("attribute_name") or "").strip()
                    for item in (bundle_contract.get("required_attributes") or [])
                    if isinstance(item, dict) and str(item.get("attribute_name") or "").strip()
                ],
                "required_metadata": required_metadata,
                "glossary_usage_mode": str(bundle_contract.get("glossary_usage_mode") or "").strip() or None,
                "issues": [],
            }
            if isinstance(bundle_contract, dict)
            else None
        ),
        "build_validation": build_validation,
        "llm_usage": {
            **llm_summary,
            "draft_stage": generation_llm_stage,
        },
        "resolved_source_text": resolved_text,
        "trace_id": trace_id,
        "scenarios": list(scenario_outputs.keys()),
        "bundle": {
            "zip_path": str(zip_path),
            "bundle_dir": str(bundle_path),
        },
        "manifest": {
            "jira_id": jira_id,
            "run_id": run_id,
            "scenarios": ["S1_MIN_REPRO"],
        },
        "download_url": f"/api/v1/ai/bundle/{jira_id}/{run_id}/download",
        **bundle_summary,
    }
    if pipeline_out is not None:
        result["generation_debug"] = {
            "trace_path": pipeline_out.get("generation_trace_path"),
            "outcome": pipeline_out.get("generation_outcome"),
        }
    if rag_status.get("rag_warning"):
        result["rag_warning"] = rag_status["rag_warning"]
    if resolution_warning:
        result["resolution_warning"] = resolution_warning

    db = SessionLocal()
    try:
        existing = db.query(DatasetRun).filter(DatasetRun.id == run_id).first()
        if existing is None:
            db.add(
                DatasetRun(
                    id=run_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    jira_id=jira_id,
                    scenario_type="MIN_REPRO",
                    recipes_used=json.dumps(plans["S1_MIN_REPRO"].get("recipes_executed", [])),
                    bundle_zip=str(zip_path),
                )
            )
            db.commit()
    finally:
        db.close()

    set_generate_progress(
        pid,
        {
            "status": "completed",
            "result": result,
            "user_id": user_id,
            "tenant_id": tenant_id,
        },
    )
    clear_llm_trace(trace_id)
    return result
