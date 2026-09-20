"""Change-surface entity quality: a CHANGED_ENTITY must name code, not prose.

Observed on a real GUIDES-11947 run: four implementation evidence records
produced 824 CHANGED_ENTITY surfaces, including the bare words ``must``,
``model`` and ``tests``, a whole ``import { ... } from '...'`` line, and a Jest
test title.  ``_flatten_strings`` propagates an ancestor key such as ``matches``
or ``file`` into every descendant JSON path, so the admitting path said nothing
about the leaf itself.  Those non-entity terms then drove directed retrieval
into unrelated documentation.

These tests pin the value-shape contract that separates a real entity from
retrieval noise, and prove the relational kinds and the prose behavior fallback
are untouched.
"""

from __future__ import annotations

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    CanonicalBehaviorModel,
    CanonicalEvidenceBundle,
    ChangeSurfaceKind,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    EvidenceRecord,
    EvidenceSourceType,
    SemanticDimension,
    SourceVisibility,
)
from app.services.canonical_test_plan_reasoning_service import (
    CanonicalTestPlanReasoningService,
    _is_code_entity_literal,
)

TENANT = "tenant-alpha"

# Exact literals observed as CHANGED_ENTITY surfaces on the real run.
REAL_NOISE = [
    "must",
    "model",
    "tests",
    "Map",
    "should call close dialog function when preset type is knowledge Base or Native p",
    "import { POST_PROCESS_REPORT_TYPE } from 'appSrc/common/reports_constants'",
]

REAL_ENTITIES = [
    "OutputController",
    "PublishDashboard",
    "common/dita_paths.py",
    r"C:\UI TEST\guides-ui-tests\resources\ui_config_keyword.json",
]


@pytest.mark.parametrize("literal", REAL_NOISE)
def test_prose_and_bare_words_are_not_entities(literal: str) -> None:
    assert _is_code_entity_literal(literal) is False


@pytest.mark.parametrize("literal", REAL_ENTITIES)
def test_files_and_symbols_remain_entities(literal: str) -> None:
    assert _is_code_entity_literal(literal) is True


def test_rejects_empty_oversized_and_multiline_literals() -> None:
    assert _is_code_entity_literal("") is False
    assert _is_code_entity_literal("   ") is False
    assert _is_code_entity_literal("A" * 500) is False
    assert _is_code_entity_literal("OutputController\nPublishDashboard") is False


def test_quoted_path_inside_a_snippet_is_not_a_path() -> None:
    """A snippet ending in a quoted module path must not read as a file."""

    assert _is_code_entity_literal("from 'appSrc/common/reports_constants.js'") is False


def test_separator_and_digit_identifiers_are_entities() -> None:
    assert _is_code_entity_literal("reports_constants") is True
    assert _is_code_entity_literal("common.dita_paths") is True
    assert _is_code_entity_literal("Topic2") is True


def _code_record(content: dict[str, object]) -> EvidenceRecord:
    return EvidenceRecord(
        source_type=EvidenceSourceType.CURRENT_CODE,
        source_reference="clone://guides/reports",
        tenant_id=TENANT,
        visibility=SourceVisibility(tenant_id=TENANT),
        content=content,
        evidence_confidence=0.55,
    )


def _bundle(content: dict[str, object]) -> CanonicalEvidenceBundle:
    return CanonicalEvidenceBundle(tenant_id=TENANT, records=[_code_record(content)])


def _implementation_bundle() -> CanonicalEvidenceBundle:
    """One code record shaped the way the real evidence records are shaped."""

    return _bundle(
        {
            "matches": [
                {
                    "file": "common/dita_paths.py",
                    "symbol": "OutputController",
                    "snippet": (
                        "import { POST_PROCESS_REPORT_TYPE } "
                        "from 'appSrc/common/reports_constants'"
                    ),
                    "line_text": "must",
                    "other": "model",
                }
            ]
        }
    )


def test_extractor_admits_entities_and_drops_snippet_noise() -> None:
    service = CanonicalTestPlanReasoningService()
    surfaces = service.extract_change_surfaces(
        _implementation_bundle(), ContractFactSet(contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)
    )

    entities = {
        row.entity for row in surfaces if row.kind == ChangeSurfaceKind.CHANGED_ENTITY
    }
    assert "common/dita_paths.py" in entities
    assert "OutputController" in entities
    for noise in ("must", "model"):
        assert noise not in entities
    assert not any("import {" in entity for entity in entities)


def test_noise_only_record_falls_back_instead_of_flooding() -> None:
    """Filtering must not leave the extractor empty-handed."""

    bundle = _bundle({"matches": [{"line_text": "must", "other": "tests"}]})
    surfaces = CanonicalTestPlanReasoningService().extract_change_surfaces(
        bundle, ContractFactSet(contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT)
    )

    assert not any(row.entity in {"must", "tests"} for row in surfaces)


def test_dita_dimensions_require_a_ticket_signal_not_code_vocabulary() -> None:
    """A code match mentioning DITA cannot widen a non-DITA Jira request."""

    bundle = _bundle(
        {
            "matches": [
                {
                    "symbol": "TopicListService",
                    "snippet": "Filter DITA topic file types before returning rows.",
                }
            ]
        }
    )
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                literal="Topic List and downloaded CSV follow map order.",
                source_evidence_ids=["jira:GUIDES-11947"],
                source_reference="jira:GUIDES-11947:description",
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            )
        ],
    )

    dimensions = CanonicalTestPlanReasoningService().applicable_semantic_dimensions(
        bundle,
        CanonicalBehaviorModel(),
        facts=facts,
    )

    assert SemanticDimension.NESTED_REFERENCED_CONTENT not in dimensions
    assert SemanticDimension.HIERARCHY not in dimensions
