from types import SimpleNamespace

import pytest

from app.services.grounding_service import (
    build_evidence_pack,
    build_section_evidence_map,
    grounding_metadata_from_pack,
    verify_grounded_answer,
)


def _candidate(
    *,
    source: str,
    text: str,
    title: str = "",
    url: str = "",
    metadata: dict | None = None,
    score: float = 0.0,
):
    return SimpleNamespace(
        source=source,
        label=title or source,
        text=text,
        url=url,
        metadata=metadata or {},
        score=score,
    )


def test_build_evidence_pack_prefers_tenant_authority():
    pack = build_evidence_pack(
        query="configure elevator door operator terminology",
        tenant_id="kone",
        candidates=[
            _candidate(
                source="aem_guides",
                title="Experience League setup",
                text="Configure the door operator in AEM Guides using the generic setup workflow.",
                metadata={"title": "Experience League setup"},
            ),
            _candidate(
                source="tenant_context",
                title="KONE terminology",
                text="Use the term door operator for field documentation and avoid generic actuator wording.",
                metadata={"label": "KONE terminology", "doc_type": "terminology", "credibility": "0.95"},
            ),
        ],
    )

    assert pack.chunks[0].source_kind == "tenant_context"
    assert pack.chunks[0].authority == "tenant_approved"
    assert pack.decision.status in {"grounded", "partial"}


def test_build_evidence_pack_abstains_on_thin_evidence():
    pack = build_evidence_pack(
        query="does swift support undocumented export mode",
        tenant_id="swift",
        candidates=[
            _candidate(
                source="tavily",
                title="Web result",
                text="A loosely related blog post mentions export options in passing.",
                metadata={"title": "Web result"},
            )
        ],
    )

    assert pack.decision.status == "abstain"
    assert pack.decision.thin_evidence is True


def test_build_evidence_pack_detects_conflicts():
    pack = build_evidence_pack(
        query="AEM Guides 4.2 support for nested keyscope",
        tenant_id="kone",
        candidates=[
            _candidate(
                source="tenant_context",
                title="Tenant release note",
                text="Nested keyscope is supported in version 4.2 for tenant deployments.",
                metadata={"title": "Tenant release note", "doc_type": "release_notes"},
            ),
            _candidate(
                source="aem_guides",
                title="Platform limitation",
                text="Nested keyscope is not supported in version 4.2 and remains disabled.",
                metadata={"title": "Platform limitation", "doc_type": "product_doc"},
            ),
        ],
    )

    assert pack.decision.status == "conflict"
    assert pack.decision.has_conflict is True


def test_build_section_evidence_map_prefers_examples_for_steps():
    pack = build_evidence_pack(
        query="write steps for glossary review",
        tenant_id="kone",
        candidates=[
            _candidate(
                source="tenant_examples",
                title="approved-task.dita",
                text="Step 1: Open the glossary. Step 2: Review the term status.",
                metadata={"filename": "approved-task.dita"},
            ),
            _candidate(
                source="tenant_context",
                title="Writer guide",
                text="Document glossary review with concise steps and approved terminology.",
                metadata={"label": "Writer guide", "doc_type": "style_guide"},
            ),
        ],
    )

    evidence_map = build_section_evidence_map(pack)

    assert evidence_map["steps"]["citation_ids"]
    assert evidence_map["steps"]["citation_ids"][0].startswith("E")


@pytest.mark.anyio
async def test_verify_grounded_answer_abstains_on_conflict():
    pack = build_evidence_pack(
        query="Is feature X supported?",
        tenant_id="ibm",
        candidates=[
            _candidate(source="tenant_context", title="IBM doc", text="Feature X is supported for managed tenants."),
            _candidate(source="aem_guides", title="Adobe doc", text="Feature X is not supported for managed tenants."),
        ],
    )

    grounded = await verify_grounded_answer(
        question="Is feature X supported?",
        draft_answer="Yes, feature X is supported everywhere.",
        evidence_pack=pack,
    )

    assert grounded.grounding_status == "partial"
    assert grounded.answer.startswith("I couldn't verify")
    assert "what it usually means" in grounded.answer.lower()
    assert "## Sources" in grounded.answer
    assert "plain-language summary" in grounded.reason.lower()


@pytest.mark.anyio
async def test_verify_grounded_answer_rewrites_retrieval_style_thin_answer():
    pack = build_evidence_pack(
        query="What is call out attribute in dita?",
        tenant_id="kone",
        candidates=[
            _candidate(
                source="dita_spec",
                title="dita_spec",
                text="The following attributes are available on this element: Universal attribute group, outputclass, and the attributes defined below.",
                metadata={"title": "dita_spec"},
            ),
            _candidate(
                source="dita_spec",
                title="ditaval",
                text="DITAVAL files define include/exclude/flag rules.",
                metadata={"title": "ditaval"},
            ),
        ],
    )

    draft = """## At a glance
Retrieved DITA specification guidance for `What is call out attribute in dita?`.

## Details
- Retrieved DITA specification guidance for `What is call out attribute in dita?`
"""

    grounded = await verify_grounded_answer(
        question="What is call out attribute in dita?",
        draft_answer=draft,
        evidence_pack=pack,
    )

    assert grounded.grounding_status == "partial"
    assert grounded.answer.startswith("I couldn't verify a standard DITA attribute")
    assert "What it usually means:" in grounded.answer
    assert "Retrieved DITA specification guidance" not in grounded.answer


@pytest.mark.anyio
async def test_verify_grounded_answer_marks_unknown_term_as_not_verified():
    pack = build_evidence_pack(
        query="Do we require href in Hasinstance and how does it resolve in Author view?",
        tenant_id="kone",
        candidates=[
            _candidate(
                source="aem_guides",
                title="Experience League",
                text="The Map Editor Author view renders map content in a WYSIWYG view. Topicref href and key-based references are resolved through the map context.",
                metadata={"title": "Experience League", "doc_type": "product_doc"},
            ),
            _candidate(
                source="dita_spec",
                title="DITA Spec",
                text="The href attribute points to the represented resource for a topic reference.",
                metadata={"title": "DITA Spec"},
            ),
        ],
    )

    grounded = await verify_grounded_answer(
        question="Do we require href in Hasinstance and how does it resolve in Author view?",
        draft_answer="href points to the represented resource and Author view resolves references through the map context.",
        evidence_pack=pack,
    )

    assert grounded.grounding_status == "partial"
    assert grounded.answer.startswith("href points to the represented resource")
    assert "not verified" in grounded.answer.lower()
    assert "hasinstance" in grounded.answer.lower()


@pytest.mark.anyio
async def test_verify_grounded_answer_preserves_supported_draft_with_light_caveat():
    pack = build_evidence_pack(
        query="How does keyref work in DITA?",
        tenant_id="kone",
        candidates=[
            _candidate(
                source="tenant_context",
                title="DITA keyref",
                text="The keyref attribute references a key defined in a map and lets topics reuse that target without hardcoding the destination.",
                metadata={"title": "DITA keyref", "doc_type": "terminology", "credibility": "0.95"},
            ),
            _candidate(
                source="tenant_examples",
                title="DITA keydef",
                text="The keydef element defines a key name and the resource it points to.",
                metadata={"title": "DITA keydef"},
            ),
        ],
    )

    grounded = await verify_grounded_answer(
        question="How does keyref work in DITA?",
        draft_answer=(
            "The keyref attribute references a key defined in a map and helps topics reuse the same target "
            "without hardcoding the destination. It can also simplify translation workflows."
        ),
        evidence_pack=pack,
    )

    assert grounded.grounding_status == "partial"
    assert grounded.answer.startswith("The keyref attribute references a key defined in a map")
    assert "translation workflows" in grounded.answer.lower()
    assert "verification notes" in grounded.answer.lower()
    assert "## Sources" in grounded.answer


@pytest.mark.anyio
async def test_verify_grounded_answer_replaces_unsafe_dita_example_with_safe_example():
    pack = build_evidence_pack(
        query="Show me a task topic skeleton in DITA 1.3",
        tenant_id="kone",
        candidates=[
            _candidate(
                source="dita_spec",
                title="DITA task",
                text="A task topic uses the root task element with title, shortdesc, and taskbody.",
                metadata={"title": "DITA task"},
            ),
            _candidate(
                source="dita_spec",
                title="DITA steps",
                text="Task steps are expressed with steps, step, and cmd elements.",
                metadata={"title": "DITA steps"},
            ),
        ],
    )

    unsafe_draft = """```xml
<task id="bad-task">
  <title>Introduction</title>
  <body>
    <shortcut>P</shortcut>
  </body>
</task>
```"""

    grounded = await verify_grounded_answer(
        question="Show me a task topic skeleton in DITA 1.3",
        draft_answer=unsafe_draft,
        evidence_pack=pack,
    )

    assert grounded.grounding_status == "partial"
    assert "safe dita 1.3 example" in grounded.answer.lower()
    assert "<!DOCTYPE task PUBLIC" in grounded.answer
    assert "<shortcut>" not in grounded.answer


@pytest.mark.anyio
async def test_verify_grounded_answer_prefers_structured_fallback_over_thin_evidence_summary():
    pack = build_evidence_pack(
        query="Different types of tables in dita",
        tenant_id="kone",
        candidates=[
            _candidate(
                source="dita_spec",
                title="table",
                text="<table> is a formal CALS table with thead, tbody, rows, and entries.",
                metadata={"title": "table"},
            ),
            _candidate(
                source="dita_spec",
                title="simpletable",
                text="<simpletable> is a lightweight table for simple grids.",
                metadata={"title": "simpletable"},
            ),
            _candidate(
                source="dita_spec",
                title="choicetable",
                text="<choicetable> is a two-column options table inside a task step.",
                metadata={"title": "choicetable"},
            ),
        ],
    )

    structured_answer = """## At a glance
The main DITA table types are `<table>`, `<simpletable>`, and `<choicetable>`.

## Types
- `<table>`: Use it for CALS-style tables with richer structure.
- `<simpletable>`: Use it for lightweight grids without spanning.
- `<choicetable>`: Use it inside a task `<step>` for option/description pairs.
"""

    grounded = await verify_grounded_answer(
        question="Different types of tables in dita",
        draft_answer="DITA has several table families for structured authoring and advanced presentation patterns.",
        evidence_pack=pack,
        verified_examples=[{"label": "table", "snippet": "<table/>"}],
        structured_fallback_answer=structured_answer,
    )

    metadata = grounding_metadata_from_pack(pack, grounded)

    assert grounded.grounding_status == "grounded"
    assert "## Types" in grounded.answer
    assert "not verified" not in grounded.answer.lower()
    assert metadata["status"] == "grounded"
    assert metadata["confidence"] >= 0.74
    assert metadata["thin_evidence"] is False
