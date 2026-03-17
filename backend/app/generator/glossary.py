"""
Glossary recipe family - glossentry, term reference.

Thin wrappers over specialized glossary generator.
"""
from typing import Dict

from app.generator.specialized import generate_glossary_dataset
from app.generator.dita_utils import stable_id
from app.generator.generate import safe_join, sanitize_filename, _map_xml
import xml.etree.ElementTree as ET
from app.jobs.schemas import DatasetConfig


def generate_glossary_glossentry_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Minimal glossary with one glossentry."""
    return generate_glossary_dataset(config, base_path, entry_count=1, **kwargs)


def generate_glossary_term_reference_basic(config: DatasetConfig, base_path: str, id_prefix: str = "t", **kwargs) -> Dict[str, bytes]:
    """Topic with term reference to glossary. Returns glossary + consumer topic with xref to first entry."""
    files = generate_glossary_dataset(config, base_path, entry_count=2, **kwargs)
    used = set()
    tid = stable_id("gloss_term", id_prefix, "topic", used)
    root = f"{base_path}/glossary_term_ref"
    topic = ET.Element("topic", {"id": tid, "xml:lang": "en"})
    ET.SubElement(topic, "title").text = "Term Reference"
    body = ET.SubElement(topic, "body")
    p = ET.SubElement(body, "p")
    p.text = "See "
    xref = ET.SubElement(p, "xref", {"href": "../../glossary/glossentry_00001.dita", "type": "glossentry"})
    xref.text = "Term 1"
    xref.tail = " for definition."
    xml_body = ET.tostring(topic, encoding="utf-8", xml_declaration=False)
    doc = f'<?xml version="1.0" encoding="UTF-8"?>\n{config.doctype_topic}\n'
    files[f"{root}/topics/consumer.dita"] = doc.encode("utf-8") + xml_body
    return files


def _spec(id_: str, title: str, desc: str, fn: str, tags: list, use_when: list, avoid_when: list) -> dict:
    return {
        "id": id_,
        "title": title,
        "description": desc,
        "tags": tags,
        "constructs": ["glossentry", "glossterm", "glossdef", "term"],
        "scenario_types": ["MIN_REPRO"],
        "use_when": use_when,
        "avoid_when": avoid_when,
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
        "module": "app.generator.glossary",
        "function": fn,
        "params_schema": {},
        "default_params": {},
        "stability": "stable",
        "examples": [{"prompt": desc[:80]}],
    }


RECIPE_SPECS = [
    _spec("glossary.glossentry_basic", "Glossentry Basic", "Minimal glossary with glossentry.", "generate_glossary_glossentry_basic",
          ["GLOSSARY", "GLOSSENTRY"], ["glossary", "glossentry", "term definition"], ["concept only"]),
    _spec("glossary.term_reference_basic", "Term Reference Basic", "Topic with term reference to glossary.", "generate_glossary_term_reference_basic",
          ["GLOSSARY", "TERM", "KEYREF"], ["term reference", "glossary link"], ["plain text"]),
]
