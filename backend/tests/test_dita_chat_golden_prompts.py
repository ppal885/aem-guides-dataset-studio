from types import SimpleNamespace

import pytest

from app.services import chat_service
from app.services.grounding_service import build_evidence_pack


def _candidate(*, source: str, title: str, text: str):
    return SimpleNamespace(
        source=source,
        label=title,
        text=text,
        url="",
        metadata={"title": title},
        score=0.0,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("prompt", "tool_results", "candidates", "must_have"),
    [
        (
            "What did morerows attribute do in table?",
            {
                "lookup_dita_attribute": {
                    "attribute_name": "morerows",
                    "attribute_syntax": "non-negative integer row-span count",
                    "text_content": "@morerows attribute makes a CALS table <entry> span additional rows downward.",
                    "supported_elements": ["entry"],
                    "usage_contexts": [
                        "Use @morerows on a CALS table <entry> to make that cell span additional rows downward.",
                        "It applies to CALS table <entry> cells, not <simpletable> cells.",
                    ],
                    "default_scenarios": ["morerows=\"1\" means the cell spans the current row plus one more row."],
                    "correct_examples": [
                        "<row><entry morerows=\"1\">Spans 2 rows</entry><entry>Row 1, Col 2</entry></row><row><entry>Row 2, Col 2</entry></row>"
                    ],
                    "common_mistakes": ["Using @morerows without checking that the resulting table grid remains valid."],
                    "status": "success",
                    "status_tone": "success",
                }
            },
            [
                _candidate(
                    source="dita_spec",
                    title="morerows",
                    text="Use @morerows on a CALS table entry to make that cell span additional rows downward.",
                )
            ],
            ["## Short answer", "not <simpletable>", 'morerows="1"', "<table>", "<tgroup cols=\"2\">"],
        ),
        (
            "How do I exclude draft-only content at publish time?",
            {},
            [
                _candidate(
                    source="dita_spec",
                    title="DITAVAL",
                    text="DITAVAL Conditional Processing filters content based on profiling attributes such as audience, props, and otherprops.",
                )
            ],
            ["conditional processing", ".ditaval", "<draft-comment>"],
        ),
        (
            "What is the difference between simpletable and table in DITA?",
            {
                "lookup_dita_spec": {
                    "query_type": "element_comparison",
                    "summary": "<table> is for CALS complexity; <simpletable> is for lightweight regular grids.",
                    "comparisons": [
                        {
                            "element_name": "table",
                            "text_content": "<table> is a formal CALS table with spanning and richer structure.",
                            "parent_elements": ["body", "section"],
                            "supported_attributes": ["frame", "colsep", "morerows"],
                            "usage_contexts": ["Use it when you need spanning, headers, or precise column control."],
                            "common_mistakes": ["Using it for tiny key-value grids that only need simpletable."],
                        },
                        {
                            "element_name": "simpletable",
                            "text_content": "<simpletable> is a lightweight table for regular grids without CALS complexity.",
                            "parent_elements": ["body", "refbody"],
                            "supported_attributes": ["relcolwidth", "keycol"],
                            "usage_contexts": ["Use it for simple rows and columns without spanning."],
                            "common_mistakes": ["Expecting CALS-style row or column spanning."],
                        },
                    ],
                    "status": "success",
                }
            },
            [
                _candidate(source="dita_spec", title="table", text="<table> is a formal CALS table."),
                _candidate(source="dita_spec", title="simpletable", text="<simpletable> is a lightweight grid."),
            ],
            ["## Comparison", "`<simpletable>`", "`<table>`"],
        ),
        (
            "When should I use topicgroup instead of topichead?",
            {
                "lookup_dita_spec": {
                    "query_type": "element_comparison",
                    "summary": "<topicgroup> silently groups topics; <topichead> adds a visible navigation heading.",
                    "comparisons": [
                        {
                            "element_name": "topicgroup",
                            "text_content": "<topicgroup> is a silent grouping element in a map.",
                            "parent_elements": ["map", "topicgroup"],
                            "supported_attributes": ["collection-type", "processing-role"],
                            "usage_contexts": ["Use it to group related topics without creating a heading in output."],
                            "common_mistakes": ["Expecting it to render a visible section title."],
                        },
                        {
                            "element_name": "topichead",
                            "text_content": "<topichead> creates a visible section heading in navigation without pointing to a topic file.",
                            "parent_elements": ["map", "topicgroup"],
                            "supported_attributes": ["navtitle", "locktitle"],
                            "usage_contexts": ["Use it when you need a visible section label in the map or TOC."],
                            "common_mistakes": ["Using it as if it directly referenced topic content."],
                        },
                    ],
                    "status": "success",
                }
            },
            [
                _candidate(source="dita_spec", title="topicgroup", text="<topicgroup> silently groups topics."),
                _candidate(source="dita_spec", title="topichead", text="<topichead> creates a visible section heading."),
            ],
            ["`<topicgroup>`", "`<topichead>`", "visible"],
        ),
        (
            "What is the difference between keyref and conref?",
            {
                "lookup_dita_spec": {
                    "query_type": "attribute_comparison",
                    "summary": "@keyref resolves through keys; @conref reuses addressed XML content directly.",
                    "comparisons": [
                        {
                            "attribute_name": "keyref",
                            "text_content": "@keyref resolves a key defined in a map.",
                            "attribute_syntax": "key name token",
                            "supported_elements": ["xref", "link", "keyword"],
                            "usage_contexts": ["Use @keyref for indirect links, variables, and map-managed references."],
                            "common_mistakes": ["Expecting @keyref to copy block content like conref."],
                        },
                        {
                            "attribute_name": "conref",
                            "text_content": "@conref pulls reusable XML content from another element by ID.",
                            "attribute_syntax": "URI#topicid/elementid",
                            "supported_elements": ["p", "note", "step"],
                            "usage_contexts": ["Use @conref for direct content reuse when the target element is stable."],
                            "common_mistakes": ["Using @conref when indirection through keys is required."],
                        },
                    ],
                    "status": "success",
                }
            },
            [
                _candidate(source="dita_spec", title="keyref", text="@keyref resolves map-defined keys."),
                _candidate(source="dita_spec", title="conref", text="@conref reuses addressed XML content."),
            ],
            ["## Comparison", "`@keyref`", "`@conref`"],
        ),
        (
            "What is keyscope in DITA? Show an example.",
            {
                "lookup_dita_attribute": {
                    "attribute_name": "keyscope",
                    "attribute_syntax": "One or more space-separated scope names (same naming rules as keys)",
                    "attribute_semantic_class": "map_scoped",
                    "text_content": "@keyscope attribute creates a named scope for key definitions.",
                    "supported_elements": ["topicref", "map"],
                    "combination_attributes": ["scope", "keys", "format"],
                    "default_scenarios": ["The root map defines an implicit unnamed scope."],
                    "usage_contexts": [
                        "Use @keyscope on a topicref branch to create a named scope for keys below that branch.",
                        "Use scope-qualified key references such as scope-name.key-name when referring across scopes.",
                    ],
                    "correct_examples": [
                        "<map><topicref href=\"../book-b/book-b.ditamap\" scope=\"peer\" keyscope=\"book-b\" format=\"ditamap\"/><xref keyref=\"book-b.install\">See Book B installation</xref></map>"
                    ],
                    "common_mistakes": [
                        "Forgetting to qualify key names when resolving keys from outside the local scope."
                    ],
                    "status": "success",
                    "status_tone": "success",
                }
            },
            [
                _candidate(source="dita_spec", title="keyscope", text="@keyscope creates a named scope for key definitions."),
            ],
            ["## Verified example", "<map>", 'keyscope="book-b"', 'keyref="book-b.install"'],
        ),
        (
            'What does processing-role="resource-only" do?',
            {
                "lookup_dita_attribute": {
                    "attribute_name": "processing-role",
                    "attribute_syntax": "normal, resource-only, or -dita-use-conref-target",
                    "text_content": "@processing-role controls whether referenced content behaves like normal publishable content or a supporting resource only.",
                    "all_valid_values": ["normal", "resource-only", "-dita-use-conref-target"],
                    "supported_elements": ["topicref", "keydef", "mapref", "topichead", "topicgroup"],
                    "usage_contexts": [
                        "Use @processing-role on map references to decide whether the target is normal publishable content or resource-only content for keys/reuse."
                    ],
                    "correct_examples": ['<topicref href="shared/reuse.dita" processing-role="resource-only"/>'],
                    "common_mistakes": ["Forgetting resource-only on key or reuse maps that should not publish as normal content."],
                    "status": "success",
                    "status_tone": "success",
                }
            },
            [
                _candidate(source="dita_spec", title="processing-role", text="@processing-role controls normal vs resource-only publish behavior."),
            ],
            ["resource-only", "<map>", "processing-role=\"resource-only\""],
        ),
        (
            "Show me a full map example for processing-role=\"resource-only\".",
            {
                "lookup_dita_attribute": {
                    "attribute_name": "processing-role",
                    "attribute_syntax": "normal, resource-only, or -dita-use-conref-target",
                    "attribute_semantic_class": "map_scoped",
                    "text_content": "@processing-role controls whether referenced content behaves like normal publishable content or a supporting resource only.",
                    "all_valid_values": ["normal", "resource-only", "-dita-use-conref-target"],
                    "supported_elements": ["topicref", "keydef", "mapref", "topichead", "topicgroup"],
                    "combination_attributes": ["href", "keys", "toc", "linking"],
                    "usage_contexts": [
                        "Use @processing-role on map references to decide whether the target is normal publishable content or resource-only content for keys/reuse."
                    ],
                    "default_scenarios": ["Omitted value defaults to normal.", "A keydef is implicitly resource-only."],
                    "correct_examples": [
                        "<map><topicref href=\"visible.dita\" processing-role=\"normal\"/><topicref href=\"reusable.dita\" processing-role=\"resource-only\"/><topicref href=\"default.dita\"/><keydef keys=\"product\" href=\"vars.dita\"/></map>"
                    ],
                    "common_mistakes": ["Forgetting processing-role=\"resource-only\" on key or reuse resources that should not publish normally."],
                    "status": "success",
                    "status_tone": "success",
                }
            },
            [
                _candidate(source="dita_spec", title="processing-role", text="@processing-role controls normal vs resource-only publish behavior."),
            ],
            ["## Verified example", "<map>", 'processing-role="resource-only"', 'processing-role="normal"', "<keydef"],
        ),
        (
            "What can go inside ditavalref? Show a full example.",
            {
                "lookup_dita_spec": {
                    "query_type": "content_model",
                    "element_name": "ditavalref",
                    "content_model_summary": "Inside <ditavalref>, DITA allows ditavalmeta.",
                    "summary": "Inside <ditavalref>, DITA allows ditavalmeta.",
                    "parent_elements": ["topicref"],
                    "allowed_children": ["ditavalmeta"],
                    "supported_attributes": ["href"],
                    "usage_contexts": [
                        "Use <ditavalref> inside a map branch when different branches need different conditional filtering.",
                        "Branch filtering is a DITA 1.3 map feature rather than a topic-body structure.",
                    ],
                    "correct_examples": [
                        "<topicref href=\"installation.dita\"><ditavalref href=\"ditaval/windows.ditaval\"><ditavalmeta><dvrResourceSuffix>-win</dvrResourceSuffix></ditavalmeta></ditavalref></topicref>"
                    ],
                    "common_mistakes": [
                        "Applying <ditavalref> at the map root instead of a specific branch."
                    ],
                    "status": "success",
                }
            },
            [
                _candidate(source="dita_spec", title="ditavalref", text="Inside <ditavalref>, DITA allows ditavalmeta."),
            ],
            ["## Allowed children", "ditavalmeta", "## Verified example", "<map>", "<ditavalref", "dvrResourceSuffix"],
        ),
        (
            "Show me a full XML example for morerows in a table.",
            {
                "lookup_dita_attribute": {
                    "attribute_name": "morerows",
                    "attribute_syntax": "non-negative integer row-span count",
                    "text_content": "@morerows attribute makes a CALS table <entry> span additional rows downward.",
                    "supported_elements": ["entry"],
                    "usage_contexts": [
                        "Use @morerows on a CALS table <entry> to make that cell span additional rows downward."
                    ],
                    "correct_examples": [
                        "<row><entry morerows=\"1\">Spans 2 rows</entry><entry>Row 1, Col 2</entry></row><row><entry>Row 2, Col 2</entry></row>"
                    ],
                    "common_mistakes": ["Using @morerows without checking that the resulting table grid remains valid."],
                    "status": "success",
                    "status_tone": "success",
                }
            },
            [
                _candidate(source="dita_spec", title="morerows", text="Use @morerows on a CALS table entry to make that cell span additional rows downward."),
            ],
            ["<table>", "<tgroup cols=\"2\">", "<tbody>", 'morerows="1"'],
        ),
        (
            "What DITA-OT argument enables draft-comment in PDF?",
            {
                "lookup_aem_guides": {
                    "query": "What DITA-OT argument enables draft-comment in PDF?",
                    "summary": "args.draft specifies whether draft-comment and required-cleanup elements are included in output.",
                    "results": [
                        {
                            "url": "https://www.dita-ot.org/dev/parameters/parameters-base",
                            "title": "DITA-OT base parameters: args.draft",
                            "snippet": "args.draft specifies whether draft-comment and required-cleanup elements are included in output. Use --args.draft=yes for DITA-OT PDF/PDF2.",
                        }
                    ],
                    "count": 1,
                    "retrieval_mode": "lexical",
                    "semantic_required": False,
                    "allowed_host_suffixes": ["experienceleague.adobe.com", "dita-ot.org"],
                    "source_domain": "dita_ot",
                    "embedding": {"available": False},
                    "warnings": [],
                }
            },
            [
                _candidate(
                    source="aem_guides",
                    title="DITA-OT base parameters: args.draft",
                    text="args.draft specifies whether draft-comment and required-cleanup elements are included in output. Use --args.draft=yes for DITA-OT PDF/PDF2.",
                ),
            ],
            ["args.draft", "--args.draft=yes", "<draft-comment>", "<required-cleanup>"],
        ),
    ],
)
async def test_local_fallback_golden_dita_prompts(monkeypatch, prompt, tool_results, candidates, must_have):
    pack = build_evidence_pack(
        query=prompt,
        tenant_id="kone",
        candidates=candidates,
    )

    async def fake_grounded_pack(**_kwargs):
        return pack, {"strength": pack.decision.status, "reason": pack.decision.reason}, tool_results

    monkeypatch.setattr(chat_service, "_build_grounded_tool_evidence_pack", fake_grounded_pack)
    monkeypatch.setattr(chat_service, "_build_rag_context", lambda *_args, **_kwargs: "")

    text = await chat_service._build_local_fallback_response(
        prompt,
        "kone",
        answer_mode="grounded_dita_answer",
    )

    lowered = text.lower()
    assert "local indexed knowledge while live providers recover" not in lowered
    for token in must_have:
        assert token.lower() in lowered
