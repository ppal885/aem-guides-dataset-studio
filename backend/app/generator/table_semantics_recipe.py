"""
Table semantics reference recipe — deterministic map + concept with @align value table.

Used when Jira primarily concerns table text/cell alignment or documenting align allowed values,
without requiring the heavier generic table/codeblock recipe.
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import make_dita_id, stable_id
from app.generator.generate import _map_xml, _rel_href, safe_join, sanitize_filename
from app.jobs.schemas import DatasetConfig

_BASE = "table_semantics_reference"


def _topic_bytes(config: DatasetConfig, topic: ET.Element) -> bytes:
    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    return doc.encode("utf-8") + xml_body


def generate_table_semantics_reference_dataset(
    config: DatasetConfig,
    base_path: str,
    id_prefix: str = "tblalign",
    issue_summary: str = "",
    **kwargs,
) -> Dict[str, bytes]:
    """Minimal map + concept topic with a two-column reference table for align values."""
    used_ids: set = set()
    topic_id = make_dita_id("align_ref", id_prefix, used_ids)

    title_text = (issue_summary or "").strip()[:200] or "Table text alignment reference"

    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = title_text
    sd = ET.SubElement(topic, "shortdesc")
    sd.text = "Reference topic documenting DITA table align attribute values for reproduction datasets."

    body = ET.SubElement(topic, "body")
    sect = ET.SubElement(body, "section")
    ET.SubElement(sect, "title").text = "Allowed align values"
    p = ET.SubElement(sect, "p")
    p.text = "Use align on colspec or entry. Example: align=\"left\" on colspec or entry."

    tbl = ET.SubElement(sect, "table")
    tgroup = ET.SubElement(tbl, "tgroup", {"cols": "2"})
    ET.SubElement(tgroup, "colspec", {"colname": "c1", "colwidth": "1*"})
    ET.SubElement(tgroup, "colspec", {"colname": "c2", "colwidth": "3*"})
    thead = ET.SubElement(tgroup, "thead")
    hrow = ET.SubElement(thead, "row")
    ET.SubElement(hrow, "entry").text = "Value"
    ET.SubElement(hrow, "entry").text = "Description"
    tbody = ET.SubElement(tgroup, "tbody")

    for val, desc in (
        ("left", "Aligns text to the left."),
        ("right", "Aligns text to the right."),
        ("center", "Centers the text."),
        ("justify", "Justifies content."),
        ("char", "Use the character specified on the char attribute."),
        ("-dita-use-conref-target", "Per DITA spec when conref supplies alignment."),
    ):
        row = ET.SubElement(tbody, "row")
        e1 = ET.SubElement(row, "entry")
        ph = ET.SubElement(e1, "codeph")
        ph.text = val
        ET.SubElement(row, "entry").text = desc

    win_safe = getattr(config, "windows_safe_filenames", True)
    topic_fn = sanitize_filename("align_reference.dita", win_safe)
    topic_rel = f"{_BASE}/topics/{topic_fn}"
    topic_path = safe_join(base_path, topic_rel)

    map_id = stable_id(config.seed, "table_semantics_map", "", used_ids)
    map_fn = sanitize_filename("main.ditamap", win_safe)
    map_rel = f"{_BASE}/maps/{map_fn}"
    map_path = safe_join(base_path, map_rel)
    href = _rel_href(map_path, topic_path)
    map_xml = _map_xml(
        config,
        map_id=map_id,
        title="Table semantics reference",
        topicref_hrefs=[href],
        keydef_entries=[],
        scoped_blocks=[],
    )

    return {
        topic_path: _topic_bytes(config, topic),
        map_path: map_xml,
    }


RECIPE_SPECS = [
    {
        "id": "table_semantics_reference",
        "title": "Table semantics (@align) reference",
        "description": (
            "Deterministic concept topic with a two-column reference table documenting "
            "DITA table align values (left, right, center, justify, char, -dita-use-conref-target). "
            "Use when Jira focuses on cell/text alignment, @align, or alignment UI in tables—not only column width."
        ),
        "tags": ["table", "align", "colspec", "entry", "cell alignment", "text alignment", "tgroup"],
        "module": "app.generator.table_semantics_recipe",
        "function": "generate_table_semantics_reference_dataset",
        "params_schema": {"issue_summary": "str"},
        "default_params": {},
        "stability": "stable",
        "constructs": ["map", "topic", "table", "tgroup", "colspec", "thead", "tbody", "row", "entry", "codeph"],
        "scenario_types": ["MIN_REPRO", "BOUNDARY"],
        "use_when": [
            "table alignment",
            "cell alignment",
            "text alignment",
            "@align",
            "align attribute",
            "right-click alignment",
            "justify table cell",
        ],
        "avoid_when": ["keyref", "conref", "xref-only", "no table"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
        "mechanism_family": "table_content",
        "topic_type": "concept",
        "intent_tags": ["table", "alignment", "attribute_reference", "aem_ui"],
        "trigger_phrases": [
            "text alignment",
            "table alignment",
            "right-click",
            "@align",
            "cell alignment",
        ],
        "required_constructs": [
            {"name": "table", "min_count": 1},
            {"name": "tgroup", "min_count": 1},
            {"name": "entry", "min_count": 2},
        ],
        "optional_constructs": ["note", "codeph", "p", "section"],
        "anti_patterns": [
            {
                "id": "prose_listing_align_without_table",
                "description": "Listing align values only in p/ul without a DITA table",
            }
        ],
        "validation_rules": [
            {
                "id": "has_table_or_align_attr",
                "when": "table_alignment",
                "require": {"regex": "(<\\s*table\\b|align\\s*=\\s*['\"]?(?:left|right|center|justify|char))"},
                "severity": "warn",
            }
        ],
        "retrieval_keywords": [
            "DITA table align colspec entry",
            "tgroup thead tbody row entry",
            "AEM Guides table formatting",
        ],
        "retrieval_element_hints": ["table", "tgroup", "colspec", "entry", "align", "thead", "tbody"],
        "forbidden_fallback_patterns": [
            "paragraph_only_body_without_table_when_table_required",
            "ul_only_allowed_values_without_table",
        ],
        "repair_hints": [
            "Keep one <table> with <tgroup>, <thead>/<tbody>, <row>, and <entry> cells; list align values inside the table, not only in <p>/<ul>.",
            "Use <codeph> for each align keyword in the reference column when showing allowed values.",
        ],
        "example_input": "Users need right-click text alignment in tables in AEM.",
        "example_output": "<concept>...<table><tgroup cols=\"2\">...align values...</tgroup></table>...",
    },
]
