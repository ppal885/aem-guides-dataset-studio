"""
Heavy content generation - topics with tables and codeblocks.

This module generates DITA topics with heavy content including:
- Multiple tables per topic
- Multiple codeblocks per topic
- Large amounts of structured content

When representative_xml is provided (from Jira evidence), writes those topics
instead of synthetic content for MIN_REPRO / table_content scenarios.
"""

from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
from app.generator.dita_utils import stable_id, make_dita_id
from app.generator.generate import safe_join, sanitize_filename, _map_xml, _rel_href
from app.generator.evidence_to_dita import (
    _validate_representative_xml,
    _ensure_root_tag,
    _extract_root_tag,
    _minimal_topic_xml,
)
from app.utils.xml_escape import xml_escape_attr, xml_escape_text


class HeavyContentGenerator:
    """Generate heavy content topics with tables and codeblocks."""

    _SCENARIO_BLUEPRINTS = [
        {
            "focus": "output preset governance",
            "overview": (
                "Use this topic to stress-test large reference content around output preset "
                "configuration, approval checkpoints, and publishing readiness."
            ),
            "objectives": [
                "Capture which preset settings must be reviewed before the publishing team promotes a change.",
                "Document the evidence authors gather when preview output differs from the approved template.",
                "Keep repeatable checkpoints close to the generated examples so validation tools can compare results.",
            ],
            "areas": ["Preset", "Template", "CSS", "Metadata", "Publish", "Fallback"],
            "actions": [
                "Review the preset owner, target format, and environment scope",
                "Confirm the template and brand overrides stay within supported parameters",
                "Record the preview result and compare it with the approved baseline",
                "Capture remediation steps when authors report inconsistent output",
            ],
            "expectations": [
                "Expected behaviour: the preset renders consistently in Author, Preview, and output generation.",
                "Expected behaviour: overrides remain traceable to a named governance decision.",
                "Expected behaviour: publication notes explain why a preset exists and when to retire it.",
            ],
            "evidence": [
                "Evidence: reviewed preset metadata, preview screenshots, and release notes.",
                "Evidence: sample generated output stored with the build artifact for comparison.",
                "Evidence: validation checklist signed off by the authoring lead.",
            ],
            "notes": [
                "Note: keep labels stable so output regression tooling can diff repeated runs.",
                "Note: prefer conservative overrides instead of product-specific workarounds.",
                "Note: record whether the issue reproduces only in editor preview or also in published output.",
            ],
            "code_title_prefix": "Preset example",
            "table_title_prefix": "Preset validation matrix",
        },
        {
            "focus": "key and content reference resolution",
            "overview": (
                "Use this topic to validate how keys, content references, and scoped reuse behave "
                "when the dataset contains many repeated tables and markup examples."
            ),
            "objectives": [
                "Show which references resolve from the root map and which ones depend on local branch context.",
                "Document how authors verify the same XML in Author view, Preview, and downstream output.",
                "Provide a stable large topic for parser, indexing, and rendering benchmarks.",
            ],
            "areas": ["Keydef", "Keyref", "Conref", "Conkeyref", "Scope", "Preview"],
            "actions": [
                "Check the active map context before validating any reference behaviour",
                "Compare local branch resolution with root-map resolution for the same construct",
                "Verify that reused fragments preserve expected wording and identifiers",
                "Capture follow-up actions for references that resolve differently across surfaces",
            ],
            "expectations": [
                "Expected behaviour: all referenced fragments resolve from the intended scope.",
                "Expected behaviour: branch-local overrides do not shadow unrelated keys.",
                "Expected behaviour: reused content stays semantically identical across repeated outputs.",
            ],
            "evidence": [
                "Evidence: root map, child map, and topic-level screenshots or build output.",
                "Evidence: resolved XML snippets copied from preview or generated HTML/PDF.",
                "Evidence: reference targets are present and named consistently for every example.",
            ],
            "notes": [
                "Note: use deterministic ids so repeated runs can compare the same reference chain.",
                "Note: include both positive and fallback cases when recording resolution behaviour.",
                "Note: unresolved references should be captured with the exact context map used for the test.",
            ],
            "code_title_prefix": "Reference example",
            "table_title_prefix": "Resolution checkpoint matrix",
        },
        {
            "focus": "translation and review workflow coverage",
            "overview": (
                "Use this topic to model enterprise translation handoff, reviewer sign-off, and "
                "post-translation validation across a large documentation branch."
            ),
            "objectives": [
                "Track what authors package for translation and what reviewers must verify on return.",
                "Keep language-neutral checkpoints consistent across repeated stress datasets.",
                "Provide realistic examples for status dashboards, QA automation, and localization audits.",
            ],
            "areas": ["Package", "Vendor", "Reviewer", "Status", "Publish", "Audit"],
            "actions": [
                "List the source assets, target locale, and handoff timing for each package",
                "Confirm returned content preserves identifiers, links, and metadata expectations",
                "Record reviewer notes before the branch is republished to downstream channels",
                "Capture audit evidence that the localized branch matches the release baseline",
            ],
            "expectations": [
                "Expected behaviour: translation packages preserve source structure and stable identifiers.",
                "Expected behaviour: reviewer comments are resolved before publication approval.",
                "Expected behaviour: localization status remains traceable from request through release.",
            ],
            "evidence": [
                "Evidence: translation package manifest, locale checklist, and reviewer comments.",
                "Evidence: localized preview output compared with the approved source baseline.",
                "Evidence: audit log showing who approved the branch for release.",
            ],
            "notes": [
                "Note: keep locale names and package identifiers deterministic for automation.",
                "Note: do not rely on screenshot-only validation when link or key resolution is involved.",
                "Note: track whether issues are source defects, translation defects, or output defects.",
            ],
            "code_title_prefix": "Localization example",
            "table_title_prefix": "Translation workflow matrix",
        },
        {
            "focus": "editor configuration and governance checks",
            "overview": (
                "Use this topic to validate editor settings, toolbar behaviour, and governance rules "
                "that authors rely on while working with large content sets."
            ),
            "objectives": [
                "Document which editor settings are safe defaults for large-scale authoring.",
                "Show how teams verify configuration changes before rolling them out broadly.",
                "Provide repeatable content for usability, governance, and regression testing.",
            ],
            "areas": ["Toolbar", "Layout", "Shortcut", "Preference", "Governance", "Rollout"],
            "actions": [
                "Review the editor setting and document the affected authoring surface",
                "Confirm the configuration matches the approved governance profile",
                "Capture rollout notes, fallback steps, and support handoff details",
                "Compare authoring behaviour before and after the configuration change",
            ],
            "expectations": [
                "Expected behaviour: editor changes are traceable and reversible within governance policy.",
                "Expected behaviour: authoring productivity improves without creating unsupported layouts.",
                "Expected behaviour: rollout notes explain which roles are affected by the change.",
            ],
            "evidence": [
                "Evidence: preference export, rollout checklist, and verified screenshots.",
                "Evidence: change ticket reference plus confirmation from the pilot author group.",
                "Evidence: editor behaviour observed in Author, Source, and Preview modes.",
            ],
            "notes": [
                "Note: configuration examples should remain generic enough for AEM Guides and Oxygen.",
                "Note: avoid unsupported UI hacks when documenting recommended settings.",
                "Note: capture rollback instructions alongside the forward change.",
            ],
            "code_title_prefix": "Configuration example",
            "table_title_prefix": "Configuration control matrix",
        },
    ]
    
    def __init__(self, config, rand):
        self.config = config
        self.rand = rand

    def _blueprint_for_topic(self, topic_id: str, title: str) -> Dict[str, object]:
        index_seed = f"{topic_id}:{title}"
        blueprint_index = sum(ord(char) for char in index_seed) % len(self._SCENARIO_BLUEPRINTS)
        return self._SCENARIO_BLUEPRINTS[blueprint_index]

    def _section_id(self, topic_id: str, suffix: str) -> str:
        return xml_escape_attr(f"{suffix}_{topic_id}")

    def _table_headers(self, cols: int) -> List[str]:
        base_headers = ["Checkpoint", "Validation focus", "Expected behaviour", "Evidence", "Notes"]
        if cols <= len(base_headers):
            return base_headers[:cols]
        return base_headers + [f"Extended detail {index}" for index in range(1, cols - len(base_headers) + 1)]

    def _table_row_values(
        self,
        row_index: int,
        cols: int,
        blueprint: Dict[str, object],
        table_number: int,
    ) -> List[str]:
        areas = blueprint["areas"]
        actions = blueprint["actions"]
        expectations = blueprint["expectations"]
        evidence = blueprint["evidence"]
        notes = blueprint["notes"]
        focus = blueprint["focus"]
        area = areas[row_index % len(areas)]
        action = actions[row_index % len(actions)]
        expected = expectations[row_index % len(expectations)]
        evidence_line = evidence[(row_index + table_number - 1) % len(evidence)]
        note = notes[(row_index + table_number) % len(notes)]

        values = [
            f"{area} checkpoint {table_number}.{row_index + 1}",
            f"{action} for {focus}.",
            expected,
            evidence_line,
            note,
        ]
        if cols > len(values):
            for extra_index in range(cols - len(values)):
                values.append(
                    f"Extended detail {extra_index + 1}: record the observed result for {focus} iteration {row_index + 1}."
                )
        return values[:cols]

    def generate_table(
        self,
        cols: int,
        rows: int,
        blueprint: Dict[str, object],
        table_number: int,
    ) -> ET.Element:
        """Generate a DITA table."""
        table = ET.Element("table")
        table.set("frame", "all")
        table.set("rowsep", "1")
        table.set("colsep", "1")
        
        tgroup = ET.SubElement(table, "tgroup")
        tgroup.set("cols", str(cols))
        tgroup.set("colsep", "1")
        tgroup.set("rowsep", "1")
        
        # Column specifications with varied widths (1*, 2*, etc.) for width-related testing
        width_patterns = ["1*", "2*", "1*", "3*", "1*"]
        for i in range(cols):
            colspec = ET.SubElement(tgroup, "colspec")
            colspec.set("colname", f"col{i+1}")
            colspec.set("colnum", str(i+1))
            colspec.set("colwidth", width_patterns[i % len(width_patterns)])
        
        headers = self._table_headers(cols)

        # Header
        thead = ET.SubElement(tgroup, "thead")
        header_row = ET.SubElement(thead, "row")
        for header in headers:
            entry = ET.SubElement(header_row, "entry")
            entry.text = xml_escape_text(header)
        
        # Body rows
        tbody = ET.SubElement(tgroup, "tbody")
        for row_idx in range(rows):
            row = ET.SubElement(tbody, "row")
            row_values = self._table_row_values(row_idx, cols, blueprint, table_number)
            for col_idx in range(cols):
                entry = ET.SubElement(row, "entry")
                entry.text = xml_escape_text(row_values[col_idx])
        
        return table

    def _code_lines(
        self,
        lines: int,
        language: str,
        blueprint: Dict[str, object],
        snippet_number: int,
    ) -> List[str]:
        focus_slug = str(blueprint["focus"]).replace(" ", "-")
        focus_title = str(blueprint["focus"]).title()
        if language == "xml":
            return [
                "<reference id=\"config-reference\">",
                f"  <title>{focus_title} Example {snippet_number}</title>",
                f"  <shortdesc>Reference sample for {blueprint['focus']} validation.</shortdesc>",
                "  <refbody>",
                "    <section id=\"verification-scope\">",
                "      <title>Verification scope</title>",
                "      <p>Capture the exact editor surface, output preset, and validation evidence.</p>",
                "    </section>",
                "    <simpletable id=\"verification-matrix\">",
                "      <sthead><stentry>Item</stentry><stentry>Expected result</stentry></sthead>",
                f"      <strow><stentry>focus</stentry><stentry>{focus_title}</stentry></strow>",
                "    </simpletable>",
                "  </refbody>",
                "</reference>",
            ]
        if language == "json":
            return [
                "{",
                f'  "scenario": "{focus_slug}",',
                f'  "sample": "snippet-{snippet_number}",',
                '  "validation": {',
                '    "strict": true,',
                '    "capture_preview": true,',
                '    "record_output": true',
                "  },",
                '  "ownership": {',
                '    "authoring_team": "enterprise-docs",',
                '    "review_state": "ready-for-check"'
                "  }",
                "}",
            ]
        if language == "python":
            return [
                "def collect_verification_result(sample_id: str) -> dict[str, str]:",
                "    return {",
                f'        "focus": "{focus_slug}",',
                f'        "sample": sample_id or "snippet-{snippet_number}",',
                '        "status": "verified",',
                '        "next_action": "publish evidence and attach preview output",',
                "    }",
                "",
                f'result = collect_verification_result("snippet-{snippet_number}")',
                'print(result["status"])',
            ]
        if language == "yaml":
            return [
                f"scenario: {focus_slug}",
                f"snippet: snippet-{snippet_number}",
                "validation:",
                "  strict: true",
                "  compare_preview: true",
                "  retain_artifacts: true",
                "ownership:",
                "  team: enterprise-docs",
                "  reviewer: qa-lead",
            ]
        return [
            f"scenario={focus_slug}",
            f"snippet=snippet-{snippet_number}",
            "strict_validation=true",
            "capture_preview=true",
            "retain_artifacts=true",
        ]

    def generate_codeblock(
        self,
        lines: int,
        language: str = "xml",
        blueprint: Optional[Dict[str, object]] = None,
        snippet_number: int = 1,
    ) -> ET.Element:
        """Generate a DITA codeblock."""
        codeblock = ET.Element("codeblock")
        codeblock.set("xml:space", "preserve")

        active_blueprint = blueprint or self._SCENARIO_BLUEPRINTS[0]
        seed_lines = self._code_lines(lines, language, active_blueprint, snippet_number)
        code_lines: List[str] = []
        while len(code_lines) < max(lines, len(seed_lines)):
            for source_line in seed_lines:
                if len(code_lines) >= max(lines, len(seed_lines)):
                    break
                code_lines.append(source_line)

        codeblock.text = "\n".join(code_lines[: max(lines, len(seed_lines))])
        return codeblock
    
    def generate_heavy_topic(
        self,
        topic_id: str,
        title: str,
        tables_per_topic: int,
        codeblocks_per_topic: int,
        table_cols: int,
        table_rows: int,
        code_lines_per_codeblock: int,
    ) -> bytes:
        """Generate a topic with heavy content (tables and codeblocks)."""
        topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
        blueprint = self._blueprint_for_topic(topic_id, title)
        
        # Title
        title_elem = ET.SubElement(topic, "title")
        title_elem.text = xml_escape_text(title)
        
        # Short description
        shortdesc = ET.SubElement(topic, "shortdesc")
        shortdesc.text = xml_escape_text(
            f"High-volume reference content for validating {blueprint['focus']} workflows in enterprise DITA environments."
        )
        
        # Body
        body = ET.SubElement(topic, "body")

        overview = ET.SubElement(body, "section")
        overview.set("id", self._section_id(topic_id, "overview"))
        overview_title = ET.SubElement(overview, "title")
        overview_title.text = "Scenario overview"
        overview_p = ET.SubElement(overview, "p")
        overview_p.text = xml_escape_text(str(blueprint["overview"]))
        overview_scope = ET.SubElement(overview, "p")
        overview_scope.text = xml_escape_text(
            f"The topic intentionally includes {tables_per_topic} tables and {codeblocks_per_topic} code samples so indexing, rendering, and diff tooling can validate repeated structured content."
        )
        overview_note = ET.SubElement(overview, "note")
        overview_note.set("type", "tip")
        overview_note_p = ET.SubElement(overview_note, "p")
        overview_note_p.text = xml_escape_text(
            "Use the repeated sections below to compare authoring behaviour, preview output, and published output without changing the test shape."
        )

        checklist = ET.SubElement(body, "section")
        checklist.set("id", self._section_id(topic_id, "validation_checklist"))
        checklist_title = ET.SubElement(checklist, "title")
        checklist_title.text = "Validation checklist"
        checklist_p = ET.SubElement(checklist, "p")
        checklist_p.text = xml_escape_text(
            "Review these checkpoints before treating the generated output as a stable regression baseline."
        )
        checklist_ul = ET.SubElement(checklist, "ul")
        for objective in blueprint["objectives"]:
            li = ET.SubElement(checklist_ul, "li")
            li.text = xml_escape_text(objective)
        
        # Add tables
        for i in range(tables_per_topic):
            section = ET.SubElement(body, "section")
            section.set("id", self._section_id(topic_id, f"table_section_{i+1}"))
            section_title = ET.SubElement(section, "title")
            section_title.text = xml_escape_text(f"{blueprint['table_title_prefix']} {i + 1}")
            
            section_p = ET.SubElement(section, "p")
            section_p.text = xml_escape_text(
                f"This matrix records structured checkpoints for {blueprint['focus']}, using {table_cols} columns and {table_rows} rows to keep repeated validation data consistent."
            )
            section_context = ET.SubElement(section, "p")
            section_context.text = xml_escape_text(
                "Each row should be readable on its own so downstream comparison tools and human reviewers can audit the topic without extra context."
            )
            
            table = self.generate_table(table_cols, table_rows, blueprint, i + 1)
            section.append(table)
        
        # Add codeblocks
        languages = ["xml", "json", "python", "yaml"]
        for i in range(codeblocks_per_topic):
            section = ET.SubElement(body, "section")
            section.set("id", self._section_id(topic_id, f"code_section_{i+1}"))
            section_title = ET.SubElement(section, "title")
            section_title.text = xml_escape_text(f"{blueprint['code_title_prefix']} {i + 1}")
            
            section_p = ET.SubElement(section, "p")
            section_p.text = xml_escape_text(
                f"This sample preserves a realistic markup or automation pattern for {blueprint['focus']} and expands to {code_lines_per_codeblock} lines for stress testing."
            )
            section_outcome = ET.SubElement(section, "p")
            section_outcome.text = xml_escape_text(
                "Keep snippet labels, ids, and field names stable so repeated dataset runs remain comparable."
            )
            
            language = languages[i % len(languages)]
            codeblock = self.generate_codeblock(
                code_lines_per_codeblock,
                language,
                blueprint=blueprint,
                snippet_number=i + 1,
            )
            codeblock.set("outputclass", xml_escape_attr(f"language-{language}"))
            section.append(codeblock)

        summary = ET.SubElement(body, "section")
        summary.set("id", self._section_id(topic_id, "verification_summary"))
        summary_title = ET.SubElement(summary, "title")
        summary_title.text = "Verification summary"
        summary_p = ET.SubElement(summary, "p")
        summary_p.text = xml_escape_text(
            f"Use {title} as a reusable stress topic when you need high-volume but semantically meaningful content for {blueprint['focus']} checks."
        )
        summary_ul = ET.SubElement(summary, "ul")
        for note in blueprint["notes"]:
            li = ET.SubElement(summary_ul, "li")
            li.text = xml_escape_text(note)
        
        # Generate XML
        xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{self.config.doctype_topic}\n'
        return doc.encode("utf-8") + xml_body


def _generate_from_representative_xml(
    config,
    base: str,
    representative_xml: List[str],
    max_items: int = 6,
    max_chars: int = 2000,
) -> tuple[Dict[str, bytes], List[str]]:
    """
    Parse representative_xml and write topics to heavy_topics/.
    Returns (files dict, list of topic paths for map).
    """
    files: Dict[str, bytes] = {}
    topic_paths: List[str] = []
    used_ids: set = set()
    snippets = _validate_representative_xml(representative_xml, max_items=max_items, max_chars=max_chars)

    if not snippets:
        return files, topic_paths

    topics_dir = safe_join(base, "heavy_topics")
    map_path = safe_join(base, "heavy_topics.ditamap")

    for i, snippet in enumerate(snippets):
        if not snippet or not isinstance(snippet, str):
            continue
        snippet = snippet.strip()
        if not snippet:
            continue

        wrapped = _ensure_root_tag(snippet)
        try:
            root_elem = ET.fromstring(wrapped)
        except ET.ParseError:
            pid = make_dita_id(f"parse_fail_{i}", "ev", used_ids)
            topic_path = safe_join(topics_dir, f"evidence_topic_{i}.dita")
            files[topic_path] = _minimal_topic_xml(config, pid, f"Parse fallback {i}")
            topic_paths.append(topic_path)
            continue

        tag = _extract_root_tag(root_elem)
        elem_id = root_elem.get("id") or root_elem.get("{http://www.w3.org/XML/1998/namespace}id")
        if not elem_id:
            elem_id = make_dita_id(f"elem_{i}", "ev", used_ids)
            root_elem.set("id", elem_id)
        used_ids.add(elem_id)

        if tag == "map":
            continue
        fname = f"evidence_topic_{i}.dita"
        topic_path = safe_join(topics_dir, fname)
        topic_paths.append(topic_path)

        xml_bytes = ET.tostring(root_elem, encoding="utf-8", xml_declaration=False)
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_bytes)
            xml_bytes = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_bytes = xml_bytes.split(b"\n", 1)[1] if b"\n" in xml_bytes else xml_bytes
        except Exception:
            pass

        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
        files[topic_path] = doc.encode("utf-8") + xml_bytes

    return files, topic_paths


def generate_heavy_topics_dataset(
    config,
    base: str,
    topic_count: int = 50,
    tables_per_topic: int = 5,
    codeblocks_per_topic: int = 5,
    table_cols: int = 4,
    table_rows: int = 10,
    code_lines_per_codeblock: int = 20,
    include_map: bool = True,
    map_topicref_count: int = 50,
    representative_xml: Optional[List[str]] = None,
    rand=None,
) -> Dict[str, bytes]:
    """Generate heavy content dataset with tables and codeblocks.
    When representative_xml is provided, writes evidence topics instead of synthetic content."""
    if rand is None:
        import random
        rand = random.Random(config.seed)

    files: Dict[str, bytes] = {}
    used_ids: set = set()
    topics_dir = safe_join(base, "heavy_topics")
    topic_paths: List[str] = []

    generator = HeavyContentGenerator(config, rand)
    evidence_has_tables = False

    if representative_xml and isinstance(representative_xml, list) and len(representative_xml) > 0:
        evidence_files, topic_paths = _generate_from_representative_xml(
            config, base, representative_xml, max_items=6, max_chars=8000
        )
        files.update(evidence_files)
        # Check if evidence topics contain tables (table_content recipe should output tables)
        for content in evidence_files.values():
            if content and (b"<table" in content or b"<simpletable" in content):
                evidence_has_tables = True
                break

    if not evidence_has_tables:
        # Ensure tables in output: either full synthetic or augment evidence with table topics
        for i in range(1, topic_count + 1):
            topic_filename = sanitize_filename(f"heavy_topic_{i:05d}.dita", config.windows_safe_filenames)
            topic_path = safe_join(topics_dir, topic_filename)
            topic_id = stable_id(config.seed, "heavy_topic", str(i), used_ids)

            topic_xml = generator.generate_heavy_topic(
                topic_id,
                f"Heavy Topic {i}",
                tables_per_topic,
                codeblocks_per_topic,
                table_cols,
                table_rows,
                code_lines_per_codeblock,
            )

            files[topic_path] = topic_xml
            topic_paths.append(topic_path)
    
    # Generate map if requested
    if include_map:
        map_dir = base
        map_filename = sanitize_filename("heavy_topics.ditamap", config.windows_safe_filenames)
        map_path = safe_join(map_dir, map_filename)
        map_id = stable_id(config.seed, "heavy_map", "", used_ids)
        
        # Select topics for map
        selected_topics = topic_paths[:map_topicref_count]
        
        # Generate map XML
        root = ET.Element("map", {"id": map_id, "xml:lang": "en"})
        title_elem = ET.SubElement(root, "title")
        title_elem.text = "Heavy Topics Map"
        
        for topic_path in selected_topics:
            topicref = ET.SubElement(root, "topicref")
            topicref.set("href", _rel_href(map_path, topic_path))
            topicref.set("type", "topic")
        
        xml_body = ET.tostring(root, encoding="utf-8", xml_declaration=False)
        doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_map}\n'
        files[map_path] = doc.encode("utf-8") + xml_body
    
    return files


RECIPE_SPECS = [
    {
        "id": "heavy_topics_tables_codeblocks",
        "title": "Heavy Topics (Tables + Codeblocks)",
        "description": "Generate topics with tables and codeblocks for content processing tests",
        "tags": ["heavy", "tables", "codeblocks"],
        "module": "app.generator.heavy_content",
        "function": "generate_heavy_topics_dataset",
        "params_schema": {"topic_count": "int", "tables_per_topic": "int", "codeblocks_per_topic": "int", "representative_xml": "list"},
        "default_params": {"topic_count": 50, "tables_per_topic": 5, "codeblocks_per_topic": 5},
        "stability": "stable",
        "output_scale": "medium",
        "constructs": ["table", "codeblock", "topic"],
        "scenario_types": ["STRESS", "SCALE", "BOUNDARY"],
        "use_when": ["stress test", "heavy content", "tables codeblocks", "content processing"],
        "avoid_when": ["minimal repro", "light content"],
        "positive_negative": "positive",
        "complexity": "medium",
    },
]
