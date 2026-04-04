"""Enterprise-safe DITA 1.3 recipes for Builder dropdown scenarios."""
from __future__ import annotations

import json
import posixpath
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple
from xml.sax.saxutils import escape

from app.jobs.schemas import DatasetConfig


def _topic_document(
    config: DatasetConfig,
    topic_id: str,
    title: str,
    shortdesc: str,
    body_xml: str,
) -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f"{config.doctype_topic}\n"
        f'<topic id="{topic_id}" xml:lang="en">\n'
        f"  <title>{escape(title)}</title>\n"
        f"  <shortdesc>{escape(shortdesc)}</shortdesc>\n"
        f"  <body>\n{body_xml}\n"
        f"  </body>\n"
        f"</topic>\n"
    ).encode("utf-8")


def _map_document(
    config: DatasetConfig,
    map_id: str,
    title: str,
    content_xml: str,
) -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f"{config.doctype_map}\n"
        f'<map id="{map_id}">\n'
        f"  <title>{escape(title)}</title>\n{content_xml}\n"
        f"</map>\n"
    ).encode("utf-8")


def _parse_xml_document(content: bytes) -> ET.Element:
    lines = []
    for line in content.decode("utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("<?xml") or stripped.startswith("<!DOCTYPE"):
            continue
        lines.append(line)
    return ET.fromstring("\n".join(lines))


def _resolve_relative(current_file: str, raw_ref: str) -> Tuple[str, str]:
    if "#" in raw_ref:
        ref_path, fragment = raw_ref.split("#", 1)
    else:
        ref_path, fragment = raw_ref, ""
    if not ref_path:
        return current_file, fragment
    current_dir = posixpath.dirname(current_file)
    resolved = posixpath.normpath(posixpath.join(current_dir, ref_path))
    return resolved, fragment


def _fragment_ids_exist(ids: set[str], fragment: str) -> bool:
    if not fragment:
        return True
    return all(part in ids for part in fragment.split("/") if part)


def _validate_dataset_references(files: Dict[str, bytes]) -> List[str]:
    parsed: Dict[str, ET.Element] = {}
    ids_by_file: Dict[str, set[str]] = {}
    key_targets: Dict[str, Tuple[str, str]] = {}
    errors: List[str] = []

    for path, content in files.items():
        if not path.endswith((".dita", ".ditamap")):
            continue
        try:
            root = _parse_xml_document(content)
        except ET.ParseError as exc:
            errors.append(f"{path}: XML parse error: {exc}")
            continue
        parsed[path] = root
        ids_by_file[path] = {
            elem.get("id")
            for elem in root.iter()
            if elem.get("id")
        }

    for path, root in parsed.items():
        for keydef in root.findall(".//keydef"):
            keys_attr = (keydef.get("keys") or "").strip()
            href = (keydef.get("href") or "").strip()
            if not keys_attr or not href:
                continue
            resolved_file, fragment = _resolve_relative(path, href)
            for key in keys_attr.split():
                key_targets[key] = (resolved_file, fragment)

    for path, root in parsed.items():
        for elem in root.iter():
            href = (elem.get("href") or "").strip()
            if href and not href.startswith(("http://", "https://", "mailto:")):
                target_file, fragment = _resolve_relative(path, href)
                if target_file not in parsed:
                    errors.append(f"{path}: missing href target {href}")
                elif fragment and not _fragment_ids_exist(ids_by_file[target_file], fragment):
                    errors.append(f"{path}: missing href fragment {href}")

            conref = (elem.get("conref") or "").strip()
            if conref:
                target_file, fragment = _resolve_relative(path, conref)
                if target_file not in parsed:
                    errors.append(f"{path}: missing conref target {conref}")
                elif fragment and not _fragment_ids_exist(ids_by_file[target_file], fragment):
                    errors.append(f"{path}: missing conref fragment {conref}")

            keyref = (elem.get("keyref") or "").strip()
            if keyref and keyref not in key_targets:
                errors.append(f"{path}: missing key target {keyref}")

            conkeyref = (elem.get("conkeyref") or "").strip()
            if conkeyref:
                if "/" not in conkeyref:
                    errors.append(f"{path}: invalid conkeyref {conkeyref}")
                else:
                    key, fragment = conkeyref.split("/", 1)
                    target = key_targets.get(key)
                    if not target:
                        errors.append(f"{path}: missing conkeyref key {key}")
                    else:
                        target_file, base_fragment = target
                        combined_fragment = (
                            f"{base_fragment}/{fragment}"
                            if base_fragment
                            else fragment
                        )
                        if target_file not in parsed:
                            errors.append(f"{path}: missing conkeyref target file {conkeyref}")
                        elif not _fragment_ids_exist(ids_by_file[target_file], combined_fragment):
                            errors.append(f"{path}: missing conkeyref fragment {conkeyref}")

    return errors


def _summary_file(root: str, summary: dict) -> Dict[str, bytes]:
    return {
        f"{root}/meta/validation-summary.json": json.dumps(summary, indent=2).encode("utf-8"),
    }


def generate_parent_child_maps_keys_conref_conkeyref_selfrefs(
    config: DatasetConfig,
    base_path: str,
    pretty_print: bool = True,
    **kwargs,
) -> Dict[str, bytes]:
    del pretty_print, kwargs
    root = f"{base_path}/parent_child_maps_keys_conref_conkeyref_selfrefs"
    files: Dict[str, bytes] = {}

    files[f"{root}/maps/parent-root.ditamap"] = _map_document(
        config,
        "parent-root-map",
        "Parent Root Map",
        """  <keydef keys="parent-common" href="../topics/common-intro.dita" format="dita"/>
  <keydef keys="parent-shared-content" href="../topics/shared-content.dita" format="dita"/>
  <topicref keyref="parent-common"/>
  <topicref keyref="parent-shared-content"/>
  <mapref href="child-a.ditamap" format="ditamap"/>
  <mapref href="child-b.ditamap" format="ditamap"/>
  <mapref href="child-c.ditamap" format="ditamap"/>""",
    )

    files[f"{root}/maps/child-a.ditamap"] = _map_document(
        config,
        "child-a-map",
        "Child A Map",
        """  <keydef keys="child-a-overview" href="../topics/child-a-topic-01.dita" format="dita"/>
  <keydef keys="child-a-details" href="../topics/child-a-topic-02.dita" format="dita"/>
  <topicref keyref="child-a-overview"/>
  <topicref keyref="child-a-details"/>""",
    )
    files[f"{root}/maps/child-b.ditamap"] = _map_document(
        config,
        "child-b-map",
        "Child B Map",
        """  <keydef keys="child-b-overview" href="../topics/child-b-topic-01.dita" format="dita"/>
  <keydef keys="child-b-details" href="../topics/child-b-topic-02.dita" format="dita"/>
  <topicref keyref="child-b-overview"/>
  <topicref keyref="child-b-details"/>""",
    )
    files[f"{root}/maps/child-c.ditamap"] = _map_document(
        config,
        "child-c-map",
        "Child C Map",
        """  <keydef keys="child-c-overview" href="../topics/child-c-topic-01.dita" format="dita"/>
  <keydef keys="child-c-faq" href="../topics/child-c-topic-02.dita" format="dita"/>
  <topicref keyref="child-c-overview"/>
  <topicref keyref="child-c-faq"/>""",
    )

    files[f"{root}/topics/common-intro.dita"] = _topic_document(
        config,
        "parent-common",
        "Common Introduction",
        "Shared introductory context for all branches in the parent-child map dataset.",
        """    <p id="common-intro-summary">This common introduction is referenced through parent-level keys so every branch can resolve the same baseline context.</p>
    <section id="common-intro-key-behavior">
      <title>Key resolution behavior</title>
      <p>Parent-level keys provide stable targets for branch topics that need a common landing topic or shared reusable guidance.</p>
    </section>""",
    )

    files[f"{root}/topics/shared-content.dita"] = _topic_document(
        config,
        "shared-content",
        "Shared Content Library",
        "Reusable paragraphs and list items that are safe conref and conkeyref targets.",
        """    <p id="shared-intro-copy">Use this shared introduction paragraph when a topic needs a conservative reusable opening statement.</p>
    <p id="shared-warning">Review key resolution in the active root map before validating links, conrefs, and conkeyrefs.</p>
    <section id="shared-checklist">
      <title>Shared Checklist</title>
      <ul>
        <li id="shared-checklist-item-1">Confirm that the root map includes the expected parent-level keydefs.</li>
        <li id="shared-checklist-item-2">Confirm that every child map exposes its branch keys through keydefs and topicrefs.</li>
      </ul>
    </section>
    <p id="shared-result">When all reusable targets exist, both authoring and publishing tools can resolve the dataset without broken references.</p>""",
    )

    files[f"{root}/topics/child-a-topic-01.dita"] = _topic_document(
        config,
        "child-a-overview",
        "Child A Overview",
        "Overview topic for branch A with parent-level key references and safe self links.",
        """    <p id="child-a-overview-summary">Child A uses the parent-level common topic to anchor shared context before linking to branch-specific details.</p>
    <p>See <xref keyref="parent-common"/> for shared context and <xref keyref="child-a-details"/> for the detail topic in this branch.</p>
    <section id="child-a-overview-checklist">
      <title>Checklist</title>
      <p>This checklist section is the local target for same-topic self references.</p>
    </section>
    <p>Jump to the <xref href="#child-a-overview/child-a-overview-checklist">checklist section</xref> to verify the local branch steps.</p>
    <p conkeyref="parent-shared-content/shared-warning">Shared warning placeholder.</p>
    <p>Direct topic linking also works through <xref href="child-a-topic-02.dita#child-a-details">the Child A details topic</xref>.</p>""",
    )

    files[f"{root}/topics/child-a-topic-02.dita"] = _topic_document(
        config,
        "child-a-details",
        "Child A Details",
        "Detail topic for branch A with direct conref and child-level conkeyref reuse.",
        """    <p>This topic reuses conservative shared content and links back to the overview through branch keys.</p>
    <p conref="shared-content.dita#shared-content/shared-intro-copy">Shared introduction placeholder.</p>
    <p conkeyref="child-a-overview/child-a-overview-summary">Overview summary placeholder.</p>
    <p>Return to <xref keyref="child-a-overview"/> or open <xref keyref="parent-shared-content"/> for shared reusable guidance.</p>""",
    )

    files[f"{root}/topics/child-b-topic-01.dita"] = _topic_document(
        config,
        "child-b-overview",
        "Child B Overview",
        "Overview topic for branch B with safe conref list reuse and self references.",
        """    <p id="child-b-overview-summary">Child B demonstrates list-based conref reuse while still resolving parent-level keys from the root map.</p>
    <p>Start with <xref keyref="parent-common"/> and continue to <xref keyref="child-b-details"/> for branch B details.</p>
    <section id="child-b-overview-self-check">
      <title>Self Check</title>
      <ul>
        <li conref="shared-content.dita#shared-content/shared-checklist-item-1">Shared checklist placeholder.</li>
        <li id="child-b-overview-local-step">Confirm that the child map contributes keys for its own branch topics.</li>
      </ul>
    </section>
    <p>Open the <xref href="#child-b-overview/child-b-overview-self-check">self-check section</xref> for a same-topic validation jump.</p>
    <p>Branch-level direct linking also works through <xref href="child-b-topic-02.dita#child-b-details">the Child B details topic</xref>.</p>""",
    )

    files[f"{root}/topics/child-b-topic-02.dita"] = _topic_document(
        config,
        "child-b-details",
        "Child B Details",
        "Detail topic for branch B with child-level and parent-level key-based reuse.",
        """    <p conkeyref="child-b-overview/child-b-overview-summary">Overview summary placeholder.</p>
    <p conkeyref="parent-shared-content/shared-warning">Shared warning placeholder.</p>
    <p>Use <xref keyref="child-b-overview"/> to return to the overview or <xref keyref="parent-common"/> for shared setup guidance.</p>""",
    )

    files[f"{root}/topics/child-c-topic-01.dita"] = _topic_document(
        config,
        "child-c-overview",
        "Child C Overview",
        "Overview topic for branch C with internal section links and parent-level key reuse.",
        """    <p id="child-c-overview-summary">Child C is designed as a lightweight FAQ branch that still participates in conservative parent-child key resolution.</p>
    <p>Open <xref keyref="parent-common"/> for shared context and <xref keyref="child-c-faq"/> for the branch FAQ topic.</p>
    <section id="child-c-overview-highlights">
      <title>Highlights</title>
      <p>This section is the local target for the same-file link in the branch overview.</p>
    </section>
    <p>Review the <xref href="#child-c-overview/child-c-overview-highlights">highlights section</xref> for the branch summary.</p>
    <p>Direct topic linking also works through <xref href="child-c-topic-02.dita#child-c-faq">the Child C FAQ topic</xref>.</p>""",
    )

    files[f"{root}/topics/child-c-topic-02.dita"] = _topic_document(
        config,
        "child-c-faq",
        "Child C FAQ",
        "FAQ topic for branch C with direct conref and child-level conkeyref examples.",
        """    <p conref="shared-content.dita#shared-content/shared-result">Shared result placeholder.</p>
    <p conkeyref="child-c-overview/child-c-overview-summary">Overview summary placeholder.</p>
    <p>Use <xref keyref="child-c-overview"/> to return to the overview and <xref keyref="parent-shared-content"/> for the shared reuse library.</p>""",
    )

    errors = _validate_dataset_references(files)
    summary = {
        "recipe_name": "parent_child_maps_keys_conref_conkeyref_selfrefs",
        "parent_level_keys_created": ["parent-common", "parent-shared-content"],
        "child_level_keys_created": {
            "child-a": ["child-a-overview", "child-a-details"],
            "child-b": ["child-b-overview", "child-b-details"],
            "child-c": ["child-c-overview", "child-c-faq"],
        },
        "conref_targets": [
            "shared-content/shared-intro-copy",
            "shared-content/shared-checklist-item-1",
            "shared-content/shared-result",
        ],
        "conkeyref_targets": [
            "parent-shared-content/shared-warning",
            "child-a-overview/child-a-overview-summary",
            "child-b-overview/child-b-overview-summary",
            "child-c-overview/child-c-overview-summary",
        ],
        "self_reference_targets": [
            "child-a-overview/child-a-overview-checklist",
            "child-b-overview/child-b-overview-self-check",
            "child-c-overview/child-c-overview-highlights",
        ],
        "all_references_resolved": not errors,
        "validation_errors": errors,
    }
    files.update(_summary_file(root, summary))
    return files


def generate_compact_parent_child_key_resolution(
    config: DatasetConfig,
    base_path: str,
    pretty_print: bool = True,
    **kwargs,
) -> Dict[str, bytes]:
    del pretty_print, kwargs
    root = f"{base_path}/compact_parent_child_key_resolution"
    files: Dict[str, bytes] = {}

    files[f"{root}/maps/compact-root.ditamap"] = _map_document(
        config,
        "compact-root-map",
        "Compact Root Map",
        """  <keydef keys="compact-parent-common" href="../topics/compact-common.dita" format="dita"/>
  <keydef keys="compact-parent-landing" href="../topics/compact-child-overview.dita" format="dita"/>
  <topicref keyref="compact-parent-common"/>
  <topicref keyref="compact-parent-landing"/>
  <mapref href="compact-child.ditamap" format="ditamap"/>""",
    )

    files[f"{root}/maps/compact-child.ditamap"] = _map_document(
        config,
        "compact-child-map",
        "Compact Child Map",
        """  <keydef keys="compact-child-overview" href="../topics/compact-child-overview.dita" format="dita"/>
  <keydef keys="compact-child-details" href="../topics/compact-child-details.dita" format="dita"/>
  <topicref keyref="compact-child-overview"/>
  <topicref keyref="compact-child-details"/>""",
    )

    files[f"{root}/topics/compact-common.dita"] = _topic_document(
        config,
        "compact-parent-common",
        "Compact Common Topic",
        "Shared compact topic used to test parent-level key resolution.",
        """    <p id="compact-common-summary">This compact common topic is the parent-level key target for the smaller key-resolution dataset.</p>""",
    )

    files[f"{root}/topics/compact-child-overview.dita"] = _topic_document(
        config,
        "compact-child-overview",
        "Compact Child Overview",
        "Small overview topic that resolves both parent and child keys.",
        """    <p id="compact-overview-summary">This overview confirms that parent-level and child-level keys resolve together in the same branch.</p>
    <p>Use <xref keyref="compact-parent-common"/> for shared context and <xref keyref="compact-child-details"/> for the branch detail topic.</p>
    <section id="compact-overview-self-link">
      <title>Self Link</title>
      <p>This section anchors the same-topic link used in the compact dataset.</p>
    </section>
    <p>Jump to the <xref href="#compact-child-overview/compact-overview-self-link">self-link section</xref> for an internal branch check.</p>""",
    )

    files[f"{root}/topics/compact-child-details.dita"] = _topic_document(
        config,
        "compact-child-details",
        "Compact Child Details",
        "Small detail topic that reuses the overview through a child-level conkeyref.",
        """    <p conkeyref="compact-child-overview/compact-overview-summary">Overview summary placeholder.</p>
    <p>Return to <xref keyref="compact-child-overview"/> or reopen <xref keyref="compact-parent-common"/> for shared context.</p>""",
    )

    errors = _validate_dataset_references(files)
    summary = {
        "recipe_name": "compact_parent_child_key_resolution",
        "parent_level_keys_created": ["compact-parent-common", "compact-parent-landing"],
        "child_level_keys_created": ["compact-child-overview", "compact-child-details"],
        "conkeyref_targets": ["compact-child-overview/compact-overview-summary"],
        "self_reference_targets": ["compact-child-overview/compact-overview-self-link"],
        "all_references_resolved": not errors,
        "validation_errors": errors,
    }
    files.update(_summary_file(root, summary))
    return files


def _large_topic_body(topic_id: str, topic_number: int, target_bytes: int) -> str:
    parts: List[str] = []
    current_bytes = 0
    section_index = 1
    paragraph_index = 1

    while current_bytes < target_bytes:
        section_id = f"{topic_id}-section-{section_index:02d}"
        parts.append(f'    <section id="{section_id}">')
        parts.append(f"      <title>Section {section_index:02d}</title>")
        while current_bytes < target_bytes and paragraph_index % 9 != 0:
            text = (
                f"Topic {topic_number:04d} paragraph {paragraph_index:03d} is conservative filler content for "
                f"enterprise XML scale testing. It keeps the structure DITA 1.3 friendly while exercising large "
                f"topic storage, map loading, and downstream processing with stable, readable prose. "
                f"Each paragraph repeats predictable documentation language so authoring tools can load a topic of "
                f"approximately one hundred kilobytes without introducing risky markup or broken references."
            )
            parts.append(f'      <p id="{topic_id}-p-{paragraph_index:03d}">{escape(text)}</p>')
            current_bytes = len("\n".join(parts).encode("utf-8"))
            paragraph_index += 1
        parts.append("    </section>")
        current_bytes = len("\n".join(parts).encode("utf-8"))
        section_index += 1
        paragraph_index += 1
    return "\n".join(parts)


def generate_large_root_map_1000_topics_100kb(
    config: DatasetConfig,
    base_path: str,
    topic_count: int = 1000,
    approx_topic_size_kb: int = 100,
    pretty_print: bool = False,
    **kwargs,
) -> Dict[str, bytes]:
    del pretty_print, kwargs
    root = f"{base_path}/large_root_map_1000_topics_100kb"
    files: Dict[str, bytes] = {}
    target_bytes = max(8 * 1024, approx_topic_size_kb * 1000)

    topicrefs: List[str] = []
    for topic_number in range(1, topic_count + 1):
        topic_id = f"large-topic-{topic_number:04d}"
        filename = f"topic-{topic_number:04d}.dita"
        title = f"Large Topic {topic_number:04d}"
        shortdesc = (
            f"Large conservative topic {topic_number:04d} used for scale testing with a root map and stable relative references."
        )
        body_xml = _large_topic_body(topic_id, topic_number, target_bytes)
        files[f"{root}/topics/{filename}"] = _topic_document(
            config,
            topic_id,
            title,
            shortdesc,
            body_xml,
        )
        topicrefs.append(f'  <topicref href="../topics/{filename}" navtitle="{title}"/>')

    files[f"{root}/maps/root-map.ditamap"] = _map_document(
        config,
        "large-root-map",
        "Large Root Map",
        "\n".join(topicrefs),
    )

    errors = _validate_dataset_references(files)
    summary = {
        "recipe_name": "large_root_map_1000_topics_100kb",
        "topic_count": topic_count,
        "approx_topic_size_kb": approx_topic_size_kb,
        "root_map": "maps/root-map.ditamap",
        "all_references_resolved": not errors,
        "validation_errors": errors,
    }
    files.update(_summary_file(root, summary))
    return files


RECIPE_SPECS = [
    {
        "id": "parent_child_maps_keys_conref_conkeyref_selfrefs",
        "mechanism_family": "conref",
        "title": "Parent-child maps with keys, conref, conkeyref, and self references",
        "description": "Enterprise-safe parent map plus three child maps using conservative keydefs, keyrefs, conrefs, conkeyrefs, self references, and topic-to-topic links.",
        "tags": ["parent map", "child map", "keydef", "keyref", "conref", "conkeyref", "self xref", "enterprise"],
        "module": "app.generator.enterprise_dita_recipes",
        "function": "generate_parent_child_maps_keys_conref_conkeyref_selfrefs",
        "params_schema": {"pretty_print": "bool"},
        "default_params": {"pretty_print": True},
        "stability": "stable",
        "constructs": ["map", "mapref", "topicref", "keydef", "keyref", "conref", "conkeyref", "xref"],
        "scenario_types": ["MIN_REPRO", "REFERENCE_INTEGRITY"],
        "use_when": [
            "parent child maps with shared keys and reusable content",
            "enterprise XML testing for keyref conref conkeyref and self links",
            "safe multi-file DITA map hierarchy",
        ],
        "avoid_when": ["invalid negative tests", "external links", "specialized topic types only"],
        "positive_negative": "positive",
        "complexity": "medium",
        "output_scale": "medium",
    },
    {
        "id": "compact_parent_child_key_resolution",
        "mechanism_family": "keyref",
        "title": "Compact parent-child key resolution dataset",
        "description": "Smaller parent-child map dataset focused on clean parent-level and child-level key resolution with one conkeyref and one self reference.",
        "tags": ["compact", "key resolution", "parent child", "keyref", "conkeyref"],
        "module": "app.generator.enterprise_dita_recipes",
        "function": "generate_compact_parent_child_key_resolution",
        "params_schema": {"pretty_print": "bool"},
        "default_params": {"pretty_print": True},
        "stability": "stable",
        "constructs": ["map", "mapref", "topicref", "keydef", "keyref", "conkeyref", "xref"],
        "scenario_types": ["MIN_REPRO", "REFERENCE_INTEGRITY"],
        "use_when": [
            "compact parent child key resolution",
            "small QA dataset for keydefs across root and child map",
            "safe branch-level keyref verification",
        ],
        "avoid_when": ["large scale tests", "heavy conref coverage"],
        "positive_negative": "positive",
        "complexity": "minimal",
        "output_scale": "minimal",
    },
    {
        "id": "large_root_map_1000_topics_100kb",
        "mechanism_family": "xref",
        "title": "Large dataset with 1000 topics of about 100 KB and a root map",
        "description": "Scale recipe that emits one root map and one thousand conservative generic topics of roughly one hundred kilobytes each.",
        "tags": ["large scale", "1000 topics", "100kb topics", "root map", "performance"],
        "module": "app.generator.enterprise_dita_recipes",
        "function": "generate_large_root_map_1000_topics_100kb",
        "params_schema": {
            "topic_count": "int",
            "approx_topic_size_kb": "int",
            "pretty_print": "bool",
        },
        "default_params": {
            "topic_count": 1000,
            "approx_topic_size_kb": 100,
            "pretty_print": False,
        },
        "stability": "stable",
        "constructs": ["map", "topicref", "topic"],
        "scenario_types": ["STRESS", "SCALE"],
        "use_when": [
            "large root map with many large topics",
            "enterprise XML scale testing",
            "1000 topics each about 100 KB",
        ],
        "avoid_when": ["small QA repro", "conref heavy reuse scenarios"],
        "positive_negative": "positive",
        "complexity": "stress",
        "output_scale": "stress",
    },
]
