"""Dynamic recipe catalog metadata for the Builder UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.generator.recipe_manifest import RecipeSpec, discover_recipe_specs
from app.services.recipe_sample_preview_service import get_recipe_sample_preview

_FEATURED_TRACKS = {
    "dita_authoring": "DITA authoring",
    "reuse_maps": "Reuse / maps",
    "publishing_native_pdf": "Publishing / Native PDF",
    "troubleshooting": "Troubleshooting",
    "qa_dataset_creation": "QA dataset creation",
}

_CATEGORY_LABELS = {
    "dita_authoring": "DITA authoring",
    "reuse_maps": "Reuse / maps",
    "publishing_native_pdf": "Publishing / Native PDF",
    "troubleshooting": "Troubleshooting",
    "qa_dataset_creation": "QA dataset creation",
}

_CURATED_EXAMPLES: dict[str, dict[str, str]] = {
    "task_topics": {
        "full_example_xml": """<task id="configure-output">
  <title>Configure PDF output</title>
  <taskbody>
    <steps>
      <step>
        <cmd>Open the output preset.</cmd>
      </step>
      <step>
        <cmd>Choose the PDF template.</cmd>
        <info>Use a preset that matches the publication target.</info>
      </step>
    </steps>
  </taskbody>
</task>""",
        "expected_result": "Generates task topics with procedural steps and, when enabled, a map that references them.",
    },
    "conref_pack": {
        "full_example_xml": """<topic id="reusable-notes">
  <title>Reusable notes</title>
  <body>
    <note id="safety-note">Disconnect power before service.</note>
  </body>
</topic>

<task id="service-unit">
  <title>Service the unit</title>
  <taskbody>
    <prereq>
      <note conref="reusable-notes.dita#reusable-notes/safety-note"/>
    </prereq>
  </taskbody>
</task>""",
        "expected_result": "Produces reusable source topics plus downstream topics that pull shared content through `conref`.",
    },
    "keydef_heavy": {
        "full_example_xml": """<map>
  <topicref keys="install-guide" href="install.dita"/>
  <topicref keys="admin-guide" href="admin.dita"/>
</map>

<p>See <xref keyref="install-guide"/> before continuing.</p>""",
        "expected_result": "Creates map-level key definitions and topics that resolve repeated `keyref` usage through shared keys.",
    },
    "relationship_table": {
        "full_example_xml": """<map>
  <reltable>
    <relrow>
      <relcell><topicref href="install.dita"/></relcell>
      <relcell><topicref href="configure.dita"/></relcell>
      <relcell><topicref href="troubleshoot.dita"/></relcell>
    </relrow>
  </reltable>
</map>""",
        "expected_result": "Builds map relationships that connect related topics for navigation and related-links testing.",
    },
    "curated_realtime_corpus": {
        "expected_result": (
            "Writes topics/curated/curated_NNNNNNNN.dita files (100k-200k) with DITA-valid element order "
            "(title, shortdesc, prolog, body, related-links), conref to topics/shared/curated_variables.dita, "
            "keyref keywords/images, external xrefs, domain codeblocks, shared PNG keydefs, and "
            "maps/curated_root_sample.ditamap plus curated_corpus_manifest.json (corpus_schema_version=2)."
        ),
    },
    "conditionals.audience_filter": {
        "full_example_xml": """<task id="install-app">
  <title>Install the application</title>
  <taskbody>
    <steps>
      <step audience="admin">
        <cmd>Deploy the package from the admin console.</cmd>
      </step>
      <step audience="user">
        <cmd>Install the desktop client from the portal.</cmd>
      </step>
    </steps>
  </taskbody>
</task>""",
        "expected_result": "Creates audience-specific content that can be included or excluded through conditional publishing rules.",
    },
    "output_optimized": {
        "full_example_xml": """<topic id="draft-only-example">
  <title>Draft-only review note</title>
  <body>
    <draft-comment author="writer1">Remove this before publish.</draft-comment>
    <p audience="customer">Visible in approved deliverables.</p>
  </body>
</topic>

<val>
  <prop action="exclude" att="audience" val="internal"/>
  <prop action="exclude" elem="draft-comment"/>
</val>""",
        "expected_result": "Produces output-oriented samples for publishing validation, including draft filtering and output profile behavior.",
    },
    "map_parse_stress": {
        "full_example_xml": """<map id="stress-map">
  <topicref href="topic-001.dita"/>
  <topicref href="topic-002.dita"/>
  <topicref href="topic-003.dita"/>
</map>""",
        "expected_result": "Creates large maps and topicref distributions to test parser performance and scale behavior.",
    },
    "bookmap": {
        "full_example_xml": """<bookmap>
  <booktitle>
    <mainbooktitle>Product Guide</mainbooktitle>
  </booktitle>
  <chapter href="intro.dita"/>
  <chapter href="install.dita"/>
</bookmap>""",
        "expected_result": "Generates a bookmap structure with front matter, chapters, and supporting topics for book output testing.",
    },
}


def _normalize_text_list(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _infer_schema_type_from_default(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "str"


def _normalize_schema_type(raw_type: Any, default_value: Any = None) -> str:
    text = str(raw_type or "").strip().lower()
    if text:
        if "dict" in text or "mapping" in text or "json" in text or "object" in text:
            return "dict"
        if "list" in text or "tuple" in text or "sequence" in text or text.startswith("["):
            return "list"
        if "bool" in text:
            return "bool"
        if "float" in text or "decimal" in text or "number" in text:
            return "float"
        if "int" in text or "integer" in text:
            return "int"
        if "str" in text or "string" in text or "literal" in text:
            return "str"
    return _infer_schema_type_from_default(default_value)


def _normalized_params_schema(spec: RecipeSpec) -> dict[str, str]:
    defaults = spec.default_params or {}
    normalized: dict[str, str] = {}
    for key, raw_type in (spec.params_schema or {}).items():
        normalized[key] = _normalize_schema_type(raw_type, defaults.get(key))
    for key, default_value in defaults.items():
        normalized.setdefault(key, _infer_schema_type_from_default(default_value))
    return normalized


def _spec_dedupe_key(spec: RecipeSpec) -> tuple[str, str, str]:
    return (
        str(spec.module or "").strip().lower(),
        str(spec.function or "").strip().lower(),
        str(spec.title or "").strip().lower(),
    )


def _spec_preference_key(spec: RecipeSpec) -> tuple[int, int, str]:
    recipe_id = str(spec.id or "").strip()
    return (0 if "." in recipe_id else 1, len(recipe_id), recipe_id.lower())


def _merge_spec_alias(target: RecipeSpec, alias_spec: RecipeSpec) -> None:
    merged_tags = _normalize_text_list(list(target.tags or []) + list(alias_spec.tags or []) + [alias_spec.id])
    target.tags = merged_tags
    merged_keywords = _normalize_text_list(
        list(target.retrieval_keywords or []) + list(alias_spec.retrieval_keywords or []) + [alias_spec.id]
    )
    target.retrieval_keywords = merged_keywords


def _dedupe_specs(specs: list[RecipeSpec]) -> list[RecipeSpec]:
    deduped: dict[tuple[str, str, str], RecipeSpec] = {}
    for spec in specs:
        key = _spec_dedupe_key(spec)
        current = deduped.get(key)
        if current is None:
            deduped[key] = spec
            continue
        preferred = min((current, spec), key=_spec_preference_key)
        other = spec if preferred is current else current
        _merge_spec_alias(preferred, other)
        deduped[key] = preferred
    return list(deduped.values())


def _infer_category(spec: RecipeSpec) -> str:
    corpus = " ".join(
        [
            spec.id,
            spec.title,
            spec.description,
            " ".join(spec.tags or []),
            " ".join(spec.constructs or []),
            " ".join(spec.intent_tags or []),
            " ".join(spec.trigger_phrases or []),
            spec.mechanism_family or "",
        ]
    ).lower()
    if any(token in corpus for token in ("jira", "qa", "issue", "repro", "dataset")):
        return "qa_dataset_creation"
    if any(token in corpus for token in ("output", "publish", "native pdf", "ditaval", "conditional", "flag")):
        return "publishing_native_pdf"
    if any(token in corpus for token in ("stress", "troubleshoot", "parse", "scale", "validation", "negative")):
        return "troubleshooting"
    if any(token in corpus for token in ("conref", "keyref", "keydef", "map", "relationship", "reuse", "hub", "spoke")):
        return "reuse_maps"
    return "dita_authoring"


def _infer_tracks(spec: RecipeSpec, category: str) -> list[str]:
    tracks = [category]
    corpus = f"{spec.id} {spec.title} {spec.description} {' '.join(spec.tags or [])}".lower()
    if category != "reuse_maps" and any(token in corpus for token in ("conref", "keyref", "map", "relationship", "reuse")):
        tracks.append("reuse_maps")
    if category != "publishing_native_pdf" and any(token in corpus for token in ("output", "publish", "conditional", "ditaval")):
        tracks.append("publishing_native_pdf")
    if category != "troubleshooting" and any(token in corpus for token in ("stress", "scale", "parse")):
        tracks.append("troubleshooting")
    return list(dict.fromkeys(track for track in tracks if track in _FEATURED_TRACKS))


def _infer_editor_type(spec: RecipeSpec) -> str:
    if spec.id in _CURATED_EXAMPLES:
        return "curated_form"
    if spec.params_schema:
        return "schema_form"
    return "defaults_only"


def _legacy_fallback_example_xml(spec: RecipeSpec) -> str:
    if spec.id.startswith("conditionals."):
        return """<topic id="conditional-sample">
  <title>Conditional sample</title>
  <body>
    <p audience="admin">Admin-only content.</p>
    <p platform="windows">Windows-specific content.</p>
  </body>
</topic>"""
    if "bookmap" in spec.id:
        return """<bookmap>
  <booktitle>
    <mainbooktitle>Sample publication</mainbooktitle>
  </booktitle>
  <chapter href="intro.dita"/>
</bookmap>"""
    if "map" in spec.id or "relationship" in spec.id:
        return """<map id="sample-map">
  <topicref href="topic-a.dita"/>
  <topicref href="topic-b.dita"/>
</map>"""
    if "glossary" in spec.id:
        return """<glossentry id="term-api">
  <glossterm>API</glossterm>
  <glossdef>Application Programming Interface.</glossdef>
</glossentry>"""
    if "reference" in spec.id:
        return """<reference id="sample-reference">
  <title>Sample reference</title>
  <refbody>
    <properties>
      <property>
        <proptype>Option</proptype>
        <propvalue>Enabled</propvalue>
      </property>
        </properties>
  </refbody>
</reference>"""
    if "concept" in spec.id:
        return """<concept id="sample-concept">
  <title>Sample concept</title>
  <conbody>
    <p>Conceptual background for the generated dataset.</p>
  </conbody>
</concept>"""
    return """<topic id="sample-topic">
  <title>Sample topic</title>
  <body>
    <p>Representative output for this recipe.</p>
  </body>
</topic>"""


def _resolve_catalog_sample(spec: RecipeSpec) -> tuple[str, str]:
    curated = _CURATED_EXAMPLES.get(spec.id) or {}
    if curated.get("full_example_xml"):
        return (
            str(curated["full_example_xml"]).strip(),
            curated.get("expected_result") or _expected_result(spec, _infer_category(spec)),
        )

    generated = get_recipe_sample_preview(spec.id)
    if generated:
        return generated

    category = _infer_category(spec)
    return _legacy_fallback_example_xml(spec), _expected_result(spec, category)


def _expected_result(spec: RecipeSpec, category: str) -> str:
    if spec.id in _CURATED_EXAMPLES:
        return _CURATED_EXAMPLES[spec.id]["expected_result"]
    scale_hint = spec.output_scale or spec.complexity or "standard"
    return (
        f"Creates a {scale_hint} dataset for { _CATEGORY_LABELS.get(category, category).lower() } "
        f"based on `{spec.id}` defaults and schema-driven configuration."
    )


def _entry_from_spec(spec: RecipeSpec) -> dict[str, Any]:
    category = _infer_category(spec)
    tracks = _infer_tracks(spec, category)
    sample_xml, sample_summary = _resolve_catalog_sample(spec)
    normalized_params_schema = _normalized_params_schema(spec)
    tags = _normalize_text_list(
        list(spec.tags or [])
        + list(spec.intent_tags or [])
        + list(spec.constructs or [])
        + list(spec.retrieval_keywords or [])
    )
    return {
        "id": spec.id,
        "title": spec.title,
        "description": spec.description,
        "category": category,
        "category_label": _CATEGORY_LABELS.get(category, category),
        "tags": tags[:20],
        "featured_tracks": tracks,
        "featured_track_labels": [_FEATURED_TRACKS[track] for track in tracks],
        "params_schema": normalized_params_schema,
        "default_params": spec.default_params or {},
        "editor_type": "schema_form" if normalized_params_schema else _infer_editor_type(spec),
        "full_example_xml": sample_xml,
        "expected_result": sample_summary,
        "stability": spec.stability,
        "topic_type": spec.topic_type,
        "mechanism_family": spec.mechanism_family,
        "output_scale": spec.output_scale,
    }


def get_recipe_catalog() -> dict[str, Any]:
    specs = sorted(_dedupe_specs(discover_recipe_specs()), key=lambda spec: (spec.title.lower(), spec.id.lower()))
    entries = [_entry_from_spec(spec) for spec in specs]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(entries),
        "entries": entries,
        "categories": [
            {"id": key, "label": label}
            for key, label in _CATEGORY_LABELS.items()
        ],
        "featured_tracks": [
            {"id": key, "label": label}
            for key, label in _FEATURED_TRACKS.items()
        ],
        "quick_workflows": [
            {
                "id": "curated_100k",
                "title": "1 Lakh curated",
                "description": "100,000 AEM Guides topics from Stack Overflow, blockchain, and cloud seeds.",
                "category": "qa_dataset_creation",
                "featured_track": "qa_dataset_creation",
                "search_terms": ["curated_realtime_corpus", "curated", "100k", "stackoverflow"],
                "recipe_id": "curated_realtime_corpus",
                "preset_params": {"topic_count": 100_000},
            },
            {
                "id": "curated_200k",
                "title": "2 Lakh curated",
                "description": "200,000 richly tagged topics with DITA prolog metadata and sample root map.",
                "category": "qa_dataset_creation",
                "featured_track": "qa_dataset_creation",
                "search_terms": ["curated_realtime_corpus", "200k", "blockchain", "cloud"],
                "recipe_id": "curated_realtime_corpus",
                "preset_params": {"topic_count": 200_000},
            },
        ],
    }
