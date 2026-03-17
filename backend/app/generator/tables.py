"""
Table recipe family - basic structure, colspec, colwidth, entry spans.

Deterministic generators for DITA table scenarios.
"""
import xml.etree.ElementTree as ET
from typing import Dict

from app.generator.dita_utils import stable_id
from app.jobs.schemas import DatasetConfig


def _topic_xml(config: DatasetConfig, topic_id: str, title: str, body_elem: ET.Element, pretty: bool = True) -> bytes:
    topic = ET.Element("topic", {"id": topic_id, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = title
    body = ET.SubElement(topic, "body")
    body.append(body_elem)
    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    if pretty:
        try:
            from xml.dom import minidom
            dom = minidom.parseString(xml_body)
            xml_body = dom.toprettyxml(indent="  ", encoding="utf-8")
            xml_body = xml_body.split(b"\n", 1)[1] if b"\n" in xml_body else xml_body
        except Exception:
            pass
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'.encode("utf-8") + xml_body


def _simple_table(cols: int = 2, rows: int = 2, table_id: str = "tbl1") -> ET.Element:
    tbl = ET.Element("table", {"id": table_id})
    ET.SubElement(tbl, "title").text = "Table"
    tg = ET.SubElement(tbl, "tgroup", {"cols": str(cols)})
    thead = ET.SubElement(tg, "thead")
    tr = ET.SubElement(thead, "row")
    for c in range(cols):
        ET.SubElement(tr, "entry").text = f"H{c+1}"
    tbody = ET.SubElement(tg, "tbody")
    for r in range(rows):
        tr = ET.SubElement(tbody, "row")
        for c in range(cols):
            ET.SubElement(tr, "entry").text = f"R{r+1}C{c+1}"
    return tbl


def generate_tables_basic_structure(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topic with basic table structure (table, tgroup, thead, tbody, row, entry)."""
    used = set()
    tid = stable_id("tbl_basic", id_prefix, "topic", used)
    tbl_id = stable_id("tbl_basic", id_prefix, "tbl", used)
    body = ET.Element("body")
    p = ET.SubElement(body, "p")
    p.text = "See table below."
    tbl = _simple_table(2, 2, tbl_id)
    body.append(tbl)
    root = f"{base_path}/tables_basic_structure"
    return {f"{root}/topics/main.dita": _topic_xml(config, tid, "Tables Basic", body)}


def generate_tables_colspec_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Table with colspec elements."""
    used = set()
    tid = stable_id("tbl_col", id_prefix, "topic", used)
    tbl_id = stable_id("tbl_col", id_prefix, "tbl", used)
    tbl = ET.Element("table", {"id": tbl_id})
    ET.SubElement(tbl, "title").text = "Colspec Basic"
    tg = ET.SubElement(tbl, "tgroup", {"cols": "3"})
    ET.SubElement(tg, "colspec", {"colname": "c1"})
    ET.SubElement(tg, "colspec", {"colname": "c2"})
    ET.SubElement(tg, "colspec", {"colname": "c3"})
    thead = ET.SubElement(tg, "thead")
    tr = ET.SubElement(thead, "row")
    ET.SubElement(tr, "entry").text = "A"
    ET.SubElement(tr, "entry").text = "B"
    ET.SubElement(tr, "entry").text = "C"
    tbody = ET.SubElement(tg, "tbody")
    tr = ET.SubElement(tbody, "row")
    ET.SubElement(tr, "entry").text = "1"
    ET.SubElement(tr, "entry").text = "2"
    ET.SubElement(tr, "entry").text = "3"
    body = ET.Element("body")
    body.append(tbl)
    root = f"{base_path}/tables_colspec_basic"
    return {f"{root}/topics/main.dita": _topic_xml(config, tid, "Colspec Basic", body)}


def generate_tables_colwidth_percent(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Colspec with colwidth in percent."""
    used = set()
    tid = stable_id("tbl_cw", id_prefix, "topic", used)
    tbl_id = stable_id("tbl_cw", id_prefix, "tbl", used)
    tbl = ET.Element("table", {"id": tbl_id})
    ET.SubElement(tbl, "title").text = "Colwidth Percent"
    tg = ET.SubElement(tbl, "tgroup", {"cols": "3"})
    ET.SubElement(tg, "colspec", {"colname": "c1", "colwidth": "33*"})
    ET.SubElement(tg, "colspec", {"colname": "c2", "colwidth": "33*"})
    ET.SubElement(tg, "colspec", {"colname": "c3", "colwidth": "34*"})
    thead = ET.SubElement(tg, "thead")
    tr = ET.SubElement(thead, "row")
    for _ in range(3):
        ET.SubElement(tr, "entry").text = "H"
    tbody = ET.SubElement(tg, "tbody")
    tr = ET.SubElement(tbody, "row")
    for _ in range(3):
        ET.SubElement(tr, "entry").text = "X"
    body = ET.Element("body")
    body.append(tbl)
    root = f"{base_path}/tables_colwidth_percent"
    return {f"{root}/topics/main.dita": _topic_xml(config, tid, "Colwidth Percent", body)}


def generate_tables_colwidth_boundary(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Colspec with boundary colwidth values (1*, 100*)."""
    used = set()
    tid = stable_id("tbl_cwb", id_prefix, "topic", used)
    tbl_id = stable_id("tbl_cwb", id_prefix, "tbl", used)
    tbl = ET.Element("table", {"id": tbl_id})
    ET.SubElement(tbl, "title").text = "Colwidth Boundary"
    tg = ET.SubElement(tbl, "tgroup", {"cols": "2"})
    ET.SubElement(tg, "colspec", {"colname": "c1", "colwidth": "1*"})
    ET.SubElement(tg, "colspec", {"colname": "c2", "colwidth": "99*"})
    thead = ET.SubElement(tg, "thead")
    tr = ET.SubElement(thead, "row")
    ET.SubElement(tr, "entry").text = "Narrow"
    ET.SubElement(tr, "entry").text = "Wide"
    tbody = ET.SubElement(tg, "tbody")
    tr = ET.SubElement(tbody, "row")
    ET.SubElement(tr, "entry").text = "A"
    ET.SubElement(tr, "entry").text = "B"
    body = ET.Element("body")
    body.append(tbl)
    root = f"{base_path}/tables_colwidth_boundary"
    return {f"{root}/topics/main.dita": _topic_xml(config, tid, "Colwidth Boundary", body)}


def generate_tables_entry_spans(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Table with namest/nameend entry spans."""
    used = set()
    tid = stable_id("tbl_span", id_prefix, "topic", used)
    tbl_id = stable_id("tbl_span", id_prefix, "tbl", used)
    tbl = ET.Element("table", {"id": tbl_id})
    ET.SubElement(tbl, "title").text = "Entry Spans"
    tg = ET.SubElement(tbl, "tgroup", {"cols": "3"})
    ET.SubElement(tg, "colspec", {"colname": "c1"})
    ET.SubElement(tg, "colspec", {"colname": "c2"})
    ET.SubElement(tg, "colspec", {"colname": "c3"})
    thead = ET.SubElement(tg, "thead")
    tr = ET.SubElement(thead, "row")
    e = ET.SubElement(tr, "entry", {"namest": "c1", "nameend": "c3"})
    e.text = "Spanned Header"
    tbody = ET.SubElement(tg, "tbody")
    tr = ET.SubElement(tbody, "row")
    ET.SubElement(tr, "entry").text = "A"
    ET.SubElement(tr, "entry").text = "B"
    ET.SubElement(tr, "entry").text = "C"
    body = ET.Element("body")
    body.append(tbl)
    root = f"{base_path}/tables_entry_spans"
    return {f"{root}/topics/main.dita": _topic_xml(config, tid, "Entry Spans", body)}


def generate_tables_missing_tgroup_negative(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: table without tgroup (invalid)."""
    used = set()
    tid = stable_id("tbl_neg", id_prefix, "topic", used)
    tbl = ET.Element("table", {"id": stable_id("tbl_neg", id_prefix, "tbl", used)})
    ET.SubElement(tbl, "title").text = "Invalid"
    # Missing tgroup - invalid structure
    body = ET.Element("body")
    body.append(tbl)
    root = f"{base_path}/tables_missing_tgroup_negative"
    return {f"{root}/topics/main.dita": _topic_xml(config, tid, "Missing Tgroup Negative", body)}


def generate_tables_invalid_colspec_negative(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Negative: colspec with invalid cols mismatch."""
    used = set()
    tid = stable_id("tbl_inv", id_prefix, "topic", used)
    tbl_id = stable_id("tbl_inv", id_prefix, "tbl", used)
    tbl = ET.Element("table", {"id": tbl_id})
    ET.SubElement(tbl, "title").text = "Invalid Colspec"
    tg = ET.SubElement(tbl, "tgroup", {"cols": "2"})
    ET.SubElement(tg, "colspec", {"colname": "c1"})
    # Only 1 colspec for cols=2 - boundary/negative
    thead = ET.SubElement(tg, "thead")
    tr = ET.SubElement(thead, "row")
    ET.SubElement(tr, "entry").text = "A"
    ET.SubElement(tr, "entry").text = "B"
    tbody = ET.SubElement(tg, "tbody")
    tr = ET.SubElement(tbody, "row")
    ET.SubElement(tr, "entry").text = "1"
    ET.SubElement(tr, "entry").text = "2"
    body = ET.Element("body")
    body.append(tbl)
    root = f"{base_path}/tables_invalid_colspec_negative"
    return {f"{root}/topics/main.dita": _topic_xml(config, tid, "Invalid Colspec Negative", body)}


def _spec(id_: str, title: str, desc: str, fn: str, tags: list, use_when: list, avoid_when: list,
          positive: str = "positive", scenario_types: list = None, complexity: str = "minimal") -> dict:
    return {
        "id": id_,
        "title": title,
        "description": desc,
        "tags": tags,
        "constructs": ["table", "tgroup", "thead", "tbody", "row", "entry", "colspec"],
        "scenario_types": scenario_types or ["MIN_REPRO"],
        "use_when": use_when,
        "avoid_when": avoid_when,
        "positive_negative": positive,
        "complexity": complexity,
        "output_scale": "minimal",
        "module": "app.generator.tables",
        "function": fn,
        "params_schema": {"id_prefix": "str"},
        "default_params": {"id_prefix": "t"},
        "stability": "stable",
        "examples": [{"prompt": desc[:80]}],
    }


RECIPE_SPECS = [
    _spec("tables.basic_structure", "Tables Basic Structure", "Topic with basic table structure.", "generate_tables_basic_structure",
          ["TABLE", "TGROUP", "THEAD", "TBODY"], ["table", "DITA table"], ["list", "figure"], "positive"),
    _spec("tables.colspec_basic", "Colspec Basic", "Table with colspec elements.", "generate_tables_colspec_basic",
          ["TABLE", "COLSPEC"], ["colspec", "column spec"], ["simple table"], "positive"),
    _spec("tables.colwidth_percent", "Colwidth Percent", "Colspec with colwidth in percent.", "generate_tables_colwidth_percent",
          ["TABLE", "COLSPEC", "COLWIDTH"], ["colwidth", "column width", "percent"], ["default width"], "positive"),
    _spec("tables.colwidth_boundary", "Colwidth Boundary", "Colspec with boundary colwidth values.", "generate_tables_colwidth_boundary",
          ["TABLE", "COLWIDTH", "BOUNDARY"], ["boundary colwidth", "1*", "99*"], ["standard width"], "positive", ["BOUNDARY"]),
    _spec("tables.entry_spans", "Entry Spans", "Table with namest/nameend entry spans.", "generate_tables_entry_spans",
          ["TABLE", "ENTRY", "NAMEST", "NAMEEND"], ["entry span", "colspan", "namest nameend"], ["simple cells"], "positive"),
    _spec("tables.missing_tgroup_negative", "Missing Tgroup Negative", "Negative: table without tgroup.", "generate_tables_missing_tgroup_negative",
          ["TABLE", "NEGATIVE"], ["validation", "invalid table"], ["valid table"], "negative", ["NEGATIVE"]),
    _spec("tables.invalid_colspec_negative", "Invalid Colspec Negative", "Negative: colspec mismatch.", "generate_tables_invalid_colspec_negative",
          ["TABLE", "COLSPEC", "NEGATIVE"], ["validation", "invalid colspec"], ["valid table"], "negative", ["NEGATIVE"]),
]
