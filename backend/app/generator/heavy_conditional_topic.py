"""
Heavy Conditional Topic - single extremely large DITA topic for stress/performance/filtering tests.

Generates one 6000+ line topic with:
- Heavy audience/platform/otherprops profiling
- Structural variety: sections, subsections, paragraphs, lists, tables, codeblocks, notes, examples
- Optional DITAVAL
- Manifest JSON with stats

Recipe ID: heavy_conditional_topic_6000_lines
Recipe family: stress_dataset
"""
import json
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from app.generator.dita_utils import make_dita_id
from app.generator.generate import sanitize_filename
from app.jobs.schemas import DatasetConfig


# Default profiling values
DEFAULT_AUDIENCE = ["beginner", "advanced", "admin", "developer", "author", "reviewer"]
DEFAULT_PLATFORM = ["windows", "linux", "mac", "cloud", "web"]
DEFAULT_OTHERPROPS = ["cloud", "onprem", "hybrid", "internal", "external", "beta", "prod", "staging"]


def _pick_attrs(
    idx: int,
    audiences: List[str],
    platforms: List[str],
    otherprops: List[str],
    density: str,
) -> Dict[str, str]:
    """Pick deterministic profiling attributes for element at index."""
    attrs = {}
    if density == "none":
        return attrs
    if audiences and (density == "high" or (density == "medium" and idx % 2 == 0)):
        attrs["audience"] = audiences[idx % len(audiences)]
    if platforms and (density == "high" or (density == "medium" and idx % 3 == 0)):
        attrs["platform"] = platforms[idx % len(platforms)]
    if otherprops and density == "high":
        attrs["otherprops"] = otherprops[idx % len(otherprops)]
    return attrs


def _apply_attrs(elem: ET.Element, attrs: Dict[str, str]) -> None:
    for k, v in attrs.items():
        if v:
            elem.set(k, v)


def _serialize_topic(topic: ET.Element, config: DatasetConfig, pretty_print: bool) -> bytes:
    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    if pretty_print:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    return doc.encode("utf-8") + xml_body


def _add_block(
    parent: ET.Element,
    idx: int,
    audiences: List[str],
    platforms: List[str],
    otherprops: List[str],
    density: str,
    subsections_per_section: int,
    paragraphs_per_subsection: int,
    include_tables: bool,
    include_codeblocks: bool,
    include_notes: bool,
    include_examples: bool,
    include_xrefs: bool,
    include_images: bool,
    tables_per_n: int,
    codeblocks_per_n: int,
    notes_per_n: int,
    examples_per_n: int,
) -> None:
    """Add one structural block (section with subsections). Deterministic."""
    section = ET.SubElement(parent, "section")
    section.set("id", f"sec_{idx:04d}")
    _apply_attrs(section, _pick_attrs(idx, audiences, platforms, otherprops, density))
    title = ET.SubElement(section, "title")
    title.text = f"Section {idx + 1}: Conditional Content Block"

    for sub_idx in range(subsections_per_section):
        # DITA does not allow nested <section>; use sectiondiv + titled <p> for sub-blocks.
        sub = ET.SubElement(section, "sectiondiv")
        sub.set("id", f"sec_{idx:04d}_sub{sub_idx}")
        _apply_attrs(sub, _pick_attrs(idx * 10 + sub_idx, audiences, platforms, otherprops, density))
        st_p = ET.SubElement(sub, "p")
        st_b = ET.SubElement(st_p, "b")
        st_b.text = f"Subsection {sub_idx + 1}"

        for p_idx in range(paragraphs_per_subsection):
            p = ET.SubElement(sub, "p")
            _apply_attrs(p, _pick_attrs(idx * 100 + sub_idx * 10 + p_idx, audiences, platforms, otherprops, density))
            p.text = f"Paragraph content for section {idx + 1}, subsection {sub_idx + 1}, paragraph {p_idx + 1}. "
            p.text += "This block is part of a heavy conditional topic for stress and filtering tests. "
            p.text += "Audience, platform, and otherprops attributes are distributed across elements."
            if include_xrefs and (idx + sub_idx + p_idx) % 5 == 0:
                xref = ET.SubElement(p, "xref")
                xref.set("href", "#sec_0000")
                xref.set("type", "section")
                xref.text = "See Section 1"

        ul = ET.SubElement(sub, "ul")
        _apply_attrs(ul, _pick_attrs(idx * 10 + sub_idx + 1000, audiences, platforms, otherprops, density))
        for li_idx in range(4):
            li = ET.SubElement(ul, "li")
            _apply_attrs(li, _pick_attrs(idx * 100 + li_idx, audiences, platforms, otherprops, density))
            li.text = f"List item {li_idx + 1} in subsection {sub_idx + 1}."

        ol = ET.SubElement(sub, "ol")
        for li_idx in range(3):
            li = ET.SubElement(ol, "li")
            _apply_attrs(li, _pick_attrs(idx * 100 + li_idx + 500, audiences, platforms, otherprops, density))
            li.text = f"Step {li_idx + 1} in ordered list."

        sub_global_idx = idx * subsections_per_section + sub_idx
        if include_tables and tables_per_n > 0 and sub_global_idx % tables_per_n == 0:
            table = ET.SubElement(sub, "table", {"frame": "all", "rowsep": "1", "colsep": "1"})
            _apply_attrs(table, _pick_attrs(idx + 2000, audiences, platforms, otherprops, density))
            tgroup = ET.SubElement(table, "tgroup", {"cols": "4", "colsep": "1", "rowsep": "1"})
            for c in range(4):
                ET.SubElement(tgroup, "colspec", {"colname": f"c{c+1}", "colwidth": "1*"})
            thead = ET.SubElement(tgroup, "thead")
            row = ET.SubElement(thead, "row")
            for c in range(4):
                e = ET.SubElement(row, "entry")
                e.text = f"H{c+1}"
                _apply_attrs(e, _pick_attrs(idx + c, audiences, platforms, otherprops, density))
            tbody = ET.SubElement(tgroup, "tbody")
            for r in range(5):
                row = ET.SubElement(tbody, "row")
                for c in range(4):
                    e = ET.SubElement(row, "entry")
                    e.text = f"R{r+1}C{c+1}"
                    _apply_attrs(e, _pick_attrs(idx * 20 + r * 4 + c, audiences, platforms, otherprops, density))

        if include_codeblocks and codeblocks_per_n > 0 and sub_global_idx % codeblocks_per_n == 0:
            cb = ET.SubElement(sub, "codeblock", {"xml:space": "preserve"})
            _apply_attrs(cb, _pick_attrs(idx + 3000, audiences, platforms, otherprops, density))
            cb.text = "\n".join([f'  line_{i}: config key = "item_{i}"; value = Content {i};' for i in range(15)])

        if include_notes and notes_per_n > 0 and sub_global_idx % notes_per_n == 0:
            note = ET.SubElement(sub, "note")
            _apply_attrs(note, _pick_attrs(idx + 4000, audiences, platforms, otherprops, density))
            p = ET.SubElement(note, "p")
            p.text = f"Note for subsection {sub_idx + 1}. Conditional content for filtering tests."

        if include_examples and examples_per_n > 0 and sub_global_idx % examples_per_n == 0:
            ex = ET.SubElement(sub, "example")
            _apply_attrs(ex, _pick_attrs(idx + 5000, audiences, platforms, otherprops, density))
            p = ET.SubElement(ex, "p")
            p.text = f"Example content for subsection {sub_idx + 1}."

        if include_images and sub_global_idx % 4 == 0:
            img = ET.SubElement(sub, "image", {"href": "images/placeholder.png", "placement": "inline"})
            _apply_attrs(img, _pick_attrs(idx + 6000, audiences, platforms, otherprops, density))


def _count_stats(topic: ET.Element) -> Dict[str, int]:
    """Count elements deterministically from topic tree."""
    def count_cond_attrs(elem: ET.Element) -> int:
        n = 0
        for a in ("audience", "platform", "otherprops"):
            if elem.get(a):
                n += 1
        for child in elem:
            n += count_cond_attrs(child)
        return n

    body = topic.find(".//body") or topic
    section_count = len(body.findall("section"))
    paragraph_count = len(body.findall(".//p"))
    table_count = len(body.findall(".//table"))
    codeblock_count = len(body.findall(".//codeblock"))
    note_count = len(body.findall(".//note"))
    example_count = len(body.findall(".//example"))
    conditional_attribute_count = count_cond_attrs(body)

    return {
        "section_count": section_count,
        "paragraph_count": paragraph_count,
        "table_count": table_count,
        "codeblock_count": codeblock_count,
        "note_count": note_count,
        "example_count": example_count,
        "conditional_attribute_count": conditional_attribute_count,
    }


def _generate_ditaval(
    audiences: List[str],
    platforms: List[str],
    otherprops: List[str],
) -> bytes:
    """Generate a DITAVAL for filtering tests."""
    val = ET.Element("val")

    for a in audiences[:3]:
        prop = ET.SubElement(val, "prop")
        prop.set("att", "audience")
        prop.set("val", a)
        prop.set("action", "include")
    for p in platforms[:2]:
        prop = ET.SubElement(val, "prop")
        prop.set("att", "platform")
        prop.set("val", p)
        prop.set("action", "include")
    for o in otherprops[:2]:
        prop = ET.SubElement(val, "prop")
        prop.set("att", "otherprops")
        prop.set("val", o)
        prop.set("action", "include")

    for a in audiences[3:]:
        prop = ET.SubElement(val, "prop")
        prop.set("att", "audience")
        prop.set("val", a)
        prop.set("action", "exclude")

    xml_body = ET.tostring(val, encoding="utf-8", xml_declaration=False)
    try:
        from xml.dom import minidom
        dom = minidom.parseString(xml_body)
        xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
        xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
    except Exception:
        pass
    doc = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<!DOCTYPE val PUBLIC "-//OASIS//DTD DITA DITAVAL//EN" "ditaval.dtd">\n'
    )
    return doc + xml_body


def generate_heavy_conditional_topic_6000_lines(
    config: DatasetConfig,
    base_path: str,
    topic_id: str = "heavy_conditional_topic_001",
    title: str = "Enterprise Conditional Processing Heavy Topic",
    target_lines: int = 6000,
    section_count: int = 120,
    subsections_per_section: int = 4,
    paragraphs_per_subsection: int = 6,
    include_tables: bool = True,
    include_codeblocks: bool = True,
    include_notes: bool = True,
    include_examples: bool = True,
    include_xrefs: bool = False,
    include_images: bool = False,
    include_ditaval: bool = True,
    condition_density: str = "high",
    audience_values: Optional[List[str]] = None,
    platform_values: Optional[List[str]] = None,
    otherprops_values: Optional[List[str]] = None,
    tables_per_n_sections: int = 2,
    codeblocks_per_n_sections: int = 2,
    notes_per_n_sections: int = 3,
    examples_per_n_sections: int = 3,
    pretty_print: bool = True,
    **kwargs,
) -> Dict[str, bytes]:
    """
    Generate a single extremely large condition-heavy DITA topic (6000+ lines).

    Deterministic, builder-first generation for stress/performance/filtering tests.
    """
    audiences = audience_values or DEFAULT_AUDIENCE
    platforms = platform_values or DEFAULT_PLATFORM
    otherprops = otherprops_values or DEFAULT_OTHERPROPS

    root = f"{base_path}/heavy_conditional_topic_6000_lines"
    topics_dir = f"{root}/topics"
    filters_dir = f"{root}/filters"
    meta_dir = f"{root}/meta"

    used_ids = set()
    tid = make_dita_id(topic_id, "t", used_ids)

    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = title
    shortdesc = ET.SubElement(topic, "shortdesc")
    shortdesc.text = f"Heavy conditional topic for stress and filtering tests. Target: {target_lines}+ lines."
    body = ET.SubElement(topic, "body")

    intro = ET.SubElement(body, "p")
    intro.text = (
        "This topic is generated for performance, scalability, source/author rendering, "
        "save/load latency, and profiling/filtering stress tests. "
        "It contains many sections with audience, platform, and otherprops attributes."
    )

    total_blocks = 0
    block_idx = 0
    while total_blocks < section_count:
        _add_block(
            body,
            block_idx,
            audiences,
            platforms,
            otherprops,
            condition_density,
            subsections_per_section,
            paragraphs_per_subsection,
            include_tables,
            include_codeblocks,
            include_notes,
            include_examples,
            include_xrefs,
            include_images,
            tables_per_n_sections,
            codeblocks_per_n_sections,
            notes_per_n_sections,
            examples_per_n_sections,
        )
        total_blocks += 1
        block_idx += 1
        topic_xml = _serialize_topic(topic, config, pretty_print)
        topic_lines = topic_xml.decode("utf-8").count("\n") + 1
        if topic_lines >= target_lines:
            break

    topic_xml = _serialize_topic(topic, config, pretty_print)
    line_count = topic_xml.decode("utf-8").count("\n") + 1

    topic_filename = sanitize_filename("heavy-conditional-topic-6000-lines.dita", getattr(config, "windows_safe_filenames", True))
    topic_path = f"{topics_dir}/{topic_filename}"

    files: Dict[str, bytes] = {topic_path: topic_xml}

    if include_ditaval:
        ditaval_content = _generate_ditaval(audiences, platforms, otherprops)
        ditaval_path = f"{filters_dir}/heavy-conditional-topic.ditaval"
        files[ditaval_path] = ditaval_content

    elem_stats = _count_stats(topic)
    stats = {
        "line_count": line_count,
        "section_count": elem_stats["section_count"],
        "paragraph_count": elem_stats["paragraph_count"],
        "table_count": elem_stats["table_count"],
        "codeblock_count": elem_stats["codeblock_count"],
        "note_count": elem_stats["note_count"],
        "example_count": elem_stats["example_count"],
        "conditional_attribute_count": elem_stats["conditional_attribute_count"],
        "generated_files": list(files.keys()),
        "target_lines": target_lines,
        "target_met": line_count >= target_lines,
    }

    warnings = []
    if line_count < target_lines:
        warnings.append(f"Line count {line_count} below target {target_lines}")
    if stats["section_count"] < 10:
        warnings.append(f"Section count {stats['section_count']} below threshold 10")
    if stats["conditional_attribute_count"] < 100 and condition_density != "none":
        warnings.append(f"Conditional attribute count {stats['conditional_attribute_count']} may be low")

    try:
        ET.fromstring(topic_xml)
    except ET.ParseError as e:
        warnings.append(f"XML validation failed: {e}")

    manifest = {
        "recipe_name": "heavy_conditional_topic_6000_lines",
        "files": stats["generated_files"],
        "stats": stats,
        "assumptions": [],
        "warnings": warnings,
    }

    manifest_path = f"{meta_dir}/heavy-conditional-topic-manifest.json"
    all_files = list(files.keys()) + [manifest_path]
    stats["generated_files"] = all_files
    manifest["files"] = all_files
    manifest["stats"] = stats
    files[manifest_path] = json.dumps(manifest, indent=2).encode("utf-8")

    return files


RECIPE_SPECS = [
    {
        "id": "heavy_conditional_topic_6000_lines",
        "mechanism_family": "stress_dataset",
        "title": "Heavy Conditional Topic (6000+ lines)",
        "description": "Generates a single extremely large condition-heavy DITA topic with audience/platform/otherprops profiling for performance, filtering, and rendering stress tests.",
        "tags": ["heavy", "conditional", "profiling", "stress", "6000 lines", "audience", "platform", "otherprops", "filtering"],
        "module": "app.generator.heavy_conditional_topic",
        "function": "generate_heavy_conditional_topic_6000_lines",
        "params_schema": {
            "topic_id": "str",
            "title": "str",
            "target_lines": "int",
            "section_count": "int",
            "subsections_per_section": "int",
            "paragraphs_per_subsection": "int",
            "include_tables": "bool",
            "include_codeblocks": "bool",
            "include_notes": "bool",
            "include_examples": "bool",
            "include_xrefs": "bool",
            "include_images": "bool",
            "include_ditaval": "bool",
            "condition_density": "str",
            "audience_values": "list[str]",
            "platform_values": "list[str]",
            "otherprops_values": "list[str]",
            "tables_per_n_sections": "int",
            "codeblocks_per_n_sections": "int",
            "notes_per_n_sections": "int",
            "examples_per_n_sections": "int",
            "pretty_print": "bool",
        },
        "default_params": {
            "topic_id": "heavy_conditional_topic_001",
            "title": "Enterprise Conditional Processing Heavy Topic",
            "target_lines": 6000,
            "section_count": 120,
            "subsections_per_section": 4,
            "paragraphs_per_subsection": 6,
            "include_tables": True,
            "include_codeblocks": True,
            "include_notes": True,
            "include_examples": True,
            "include_xrefs": False,
            "include_images": False,
            "include_ditaval": True,
            "condition_density": "high",
            "audience_values": ["beginner", "advanced", "admin", "developer", "author", "reviewer"],
            "platform_values": ["windows", "linux", "mac", "cloud", "web"],
            "otherprops_values": ["cloud", "onprem", "hybrid", "internal", "external", "beta", "prod", "staging"],
            "tables_per_n_sections": 2,
            "codeblocks_per_n_sections": 2,
            "notes_per_n_sections": 3,
            "examples_per_n_sections": 3,
            "pretty_print": True,
        },
        "stability": "stable",
        "constructs": ["topic", "section", "audience", "platform", "otherprops", "table", "codeblock", "note", "example"],
        "scenario_types": ["STRESS", "MIN_REPRO", "BOUNDARY"],
        "use_when": [
            "very large single DITA topic with heavy conditional profiling audience platform otherprops",
            "stress filtering rendering or performance testing on large topic",
            "need large topic",
            "need very heavy topic",
            "need 6000 line topic",
            "create huge topic for performance",
            "topic for save/load stress",
            "author loading issue with large files",
            "source view slow for heavy topic",
            "profiling conditional rendering issue on large topic",
            "filtering problem with audience platform otherprops",
            "large topic with many conditions",
            "stress test for conditional processing",
            "performance issue on topic with profiling",
            "need massive topic for validation",
            "need bulky topic for editor rendering indexing",
            "generate heavy conditional topic",
        ],
        "avoid_when": [
            "keyref resolution",
            "nested map hierarchy",
            "duplicate keys",
            "conref conrefend",
            "xref linking",
            "small functional repro",
        ],
        "positive_negative": "positive",
        "complexity": "high",
        "output_scale": "stress",
    },
]
