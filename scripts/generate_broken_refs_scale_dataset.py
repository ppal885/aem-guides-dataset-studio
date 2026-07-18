#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate an AEM Guides broken references scale dataset.

The archive contains one DITA map and exactly 1,000 DITA topics. Each topic
contains intentional broken local hrefs, keyrefs, conrefs, and conkeyrefs plus
two valid external HTML links.
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET


DATASET_NAME = "aem-guides-1000-topics-broken-links"
TOPIC_COUNT = 1000
BROKEN_PER_TYPE_PER_TOPIC = 10
EXTERNAL_LINKS = (
    {
        "href": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/overview",
        "scope": "external",
        "format": "html",
        "text": "Adobe Experience Manager Guides documentation",
    },
    {
        "href": "https://docs.oasis-open.org/dita/dita/v1.3/dita-v1.3-part1-base.html",
        "scope": "external",
        "format": "html",
        "text": "OASIS DITA 1.3 specification",
    },
)


@dataclass(frozen=True)
class DatasetPaths:
    root: Path
    dataset_dir: Path
    topics_dir: Path
    map_path: Path
    manifest_path: Path
    readme_path: Path
    zip_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--keep-folder", action="store_true", help="keep generated folder after ZIP creation")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = build_paths(args.output_dir)
    recreate_dataset_dir(paths)
    write_map(paths.map_path)
    write_topics(paths.topics_dir)
    manifest = build_manifest()
    write_text(paths.manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    write_text(paths.readme_path, build_readme())
    validate_dataset(paths)
    create_zip(paths)
    validate_zip(paths.zip_path)
    if not args.keep_folder:
        shutil.rmtree(paths.dataset_dir)
    print(
        json.dumps(
            {
                "dataset": DATASET_NAME,
                "zip": str(paths.zip_path.resolve()),
                "topics": TOPIC_COUNT,
                "intentional_broken_references": TOPIC_COUNT * BROKEN_PER_TYPE_PER_TOPIC * 4,
                "valid_external_links": TOPIC_COUNT * len(EXTERNAL_LINKS),
                "status": "validated",
            },
            indent=2,
        )
    )
    return 0


def build_paths(output_dir: Path) -> DatasetPaths:
    root = output_dir.resolve()
    dataset_dir = root / DATASET_NAME
    return DatasetPaths(
        root=root,
        dataset_dir=dataset_dir,
        topics_dir=dataset_dir / "topics",
        map_path=dataset_dir / f"{DATASET_NAME}.ditamap",
        manifest_path=dataset_dir / "dataset-manifest.json",
        readme_path=dataset_dir / "README.txt",
        zip_path=root / f"{DATASET_NAME}.zip",
    )


def recreate_dataset_dir(paths: DatasetPaths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    if paths.dataset_dir.exists():
        shutil.rmtree(paths.dataset_dir)
    if paths.zip_path.exists():
        paths.zip_path.unlink()
    paths.topics_dir.mkdir(parents=True)


def write_map(path: Path) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">',
        '<map id="aem_guides_1000_topics_broken_links_map" xml:lang="en-US">',
        "  <title>AEM Guides 1,000 Topics Broken References Scale Dataset</title>",
    ]
    for index in range(1, TOPIC_COUNT + 1):
        topic_id = format_topic_id(index)
        lines.append(
            f'  <topicref href="topics/topic-{index:04d}.dita" type="topic" navtitle="Broken Reference Topic {index:04d}"/>'
        )
    lines.append("</map>")
    write_text(path, "\n".join(lines) + "\n")


def write_topics(topics_dir: Path) -> None:
    for index in range(1, TOPIC_COUNT + 1):
        write_text(topics_dir / f"topic-{index:04d}.dita", build_topic_xml(index))


def build_topic_xml(index: int) -> str:
    topic_id = format_topic_id(index)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">',
        f'<topic id="{topic_id}" xml:lang="en-US">',
        f"  <title>Broken Reference Topic {index:04d}</title>",
        "  <shortdesc>Scale dataset topic for validating AEM Guides Broken Links Report behavior.</shortdesc>",
        "  <body>",
        '    <section id="broken_href_links">',
        "      <title>Intentional broken local href links</title>",
        "      <ul>",
    ]
    for number in range(1, BROKEN_PER_TYPE_PER_TOPIC + 1):
        missing_id = f"missing_topic_{index:04d}_{number:02d}"
        lines.extend(
            [
                "        <li>",
                f'          <xref href="../missing/missing-topic-{index:04d}-{number:02d}.dita#{missing_id}">Intentionally broken local DITA href {number:02d}</xref>',
                "        </li>",
            ]
        )
    lines.extend(
        [
            "      </ul>",
            "    </section>",
            '    <section id="unresolved_keyrefs">',
            "      <title>Intentional unresolved keyrefs</title>",
            "      <ul>",
        ]
    )
    for number in range(1, BROKEN_PER_TYPE_PER_TOPIC + 1):
        lines.extend(
            [
                "        <li>",
                f'          <xref keyref="undefined-key-{index:04d}-{number:02d}">Intentionally unresolved keyref {number:02d}</xref>',
                "        </li>",
            ]
        )
    lines.extend(
        [
            "      </ul>",
            "    </section>",
            '    <section id="broken_conrefs">',
            "      <title>Intentional broken conrefs</title>",
        ]
    )
    for number in range(1, BROKEN_PER_TYPE_PER_TOPIC + 1):
        missing_id = f"missing_conref_topic_{index:04d}_{number:02d}"
        lines.append(
            f'      <p conref="../missing/missing-conref-topic-{index:04d}-{number:02d}.dita#{missing_id}/missing_p">Fallback content for intentionally broken conref {number:02d}</p>'
        )
    lines.extend(
        [
            "    </section>",
            '    <section id="unresolved_conkeyrefs">',
            "      <title>Intentional unresolved conkeyrefs</title>",
        ]
    )
    for number in range(1, BROKEN_PER_TYPE_PER_TOPIC + 1):
        lines.append(
            f'      <p conkeyref="undefined-conkey-{index:04d}-{number:02d}/missing_p">Fallback content for intentionally unresolved conkeyref {number:02d}</p>'
        )
    lines.extend(
        [
            "    </section>",
            '    <section id="valid_external_html_links">',
            "      <title>Valid external HTML links</title>",
            "      <ul>",
        ]
    )
    for link in EXTERNAL_LINKS:
        lines.extend(
            [
                "        <li>",
                f'          <xref href="{link["href"]}" scope="{link["scope"]}" format="{link["format"]}">{link["text"]}</xref>',
                "        </li>",
            ]
        )
    lines.extend(["      </ul>", "    </section>", "  </body>", "</topic>"])
    return "\n".join(lines) + "\n"


def build_manifest() -> dict[str, object]:
    total_per_type = TOPIC_COUNT * BROKEN_PER_TYPE_PER_TOPIC
    return {
        "dataset_name": DATASET_NAME,
        "entry_map_filename": f"{DATASET_NAME}.ditamap",
        "topic_count": TOPIC_COUNT,
        "map_topicref_count": TOPIC_COUNT,
        "broken_reference_count_per_type_per_topic": {
            "href": BROKEN_PER_TYPE_PER_TOPIC,
            "keyref": BROKEN_PER_TYPE_PER_TOPIC,
            "conref": BROKEN_PER_TYPE_PER_TOPIC,
            "conkeyref": BROKEN_PER_TYPE_PER_TOPIC,
        },
        "total_broken_reference_count_per_topic": BROKEN_PER_TYPE_PER_TOPIC * 4,
        "total_broken_reference_count_by_type": {
            "href": total_per_type,
            "keyref": total_per_type,
            "conref": total_per_type,
            "conkeyref": total_per_type,
        },
        "overall_broken_reference_count": total_per_type * 4,
        "external_link_count_per_topic": len(EXTERNAL_LINKS),
        "total_external_link_count": TOPIC_COUNT * len(EXTERNAL_LINKS),
        "external_urls": EXTERNAL_LINKS,
        "missing_directory_intentionally_absent": True,
    }


def build_readme() -> str:
    return f"""AEM Guides 1,000 Topics Broken References Scale Dataset

Upload:
1. Extract {DATASET_NAME}.zip.
2. Upload the extracted {DATASET_NAME} folder into AEM Assets.
3. Open {DATASET_NAME}.ditamap in Adobe Experience Manager Guides.

Broken Links Report:
1. Open the DITA map in AEM Guides.
2. Run the Broken Links Report from the map/reporting workflow.
3. Verify that the report scales across exactly {TOPIC_COUNT} referenced topics.

Intentional broken references:
- 10 local DITA href xrefs per topic point to ../missing/*.dita files that do not exist.
- 10 keyrefs per topic use undefined-key-* keys that are not declared anywhere.
- 10 conrefs per topic point to ../missing/*.dita source files and missing target IDs.
- 10 conkeyrefs per topic use undefined-conkey-* keys that are not declared anywhere.

Expected counts:
- Broken href references: 10,000
- Unresolved keyrefs: 10,000
- Broken conrefs: 10,000
- Unresolved conkeyrefs: 10,000
- Total intentional broken references: 40,000

Valid external links:
- Each topic contains exactly two valid external HTML links.
- Each external xref has scope="external" and format="html".
- Expected valid external links: 2,000

Important:
- The missing directory is intentionally absent.
- No key named undefined-key-* or undefined-conkey-* is declared in the map.
"""


def validate_dataset(paths: DatasetPaths) -> None:
    topic_paths = sorted(paths.topics_dir.glob("*.dita"))
    require(len(topic_paths) == TOPIC_COUNT, f"expected {TOPIC_COUNT} topics, found {len(topic_paths)}")
    require(not (paths.dataset_dir / "missing").exists(), "missing directory must be absent")

    map_root = parse_xml_without_doctype(paths.map_path)
    topicrefs = map_root.findall(".//topicref")
    require(len(topicrefs) == TOPIC_COUNT, f"expected {TOPIC_COUNT} topicrefs, found {len(topicrefs)}")
    declared_keys = [
        value
        for topicref in topicrefs
        for attr in ("keys", "keyref", "conkeyref")
        if (value := topicref.attrib.get(attr))
    ]
    require(not any(value.startswith(("undefined-key-", "undefined-conkey-")) for value in declared_keys), "undefined test keys declared in map")

    for topic_path in topic_paths:
        root = parse_xml_without_doctype(topic_path)
        require(root.tag == "topic", f"{topic_path.name} root is not topic")
        xrefs = root.findall(".//xref")
        broken_hrefs = [node for node in xrefs if (node.attrib.get("href") or "").startswith("../missing/")]
        keyrefs = [node for node in xrefs if (node.attrib.get("keyref") or "").startswith("undefined-key-")]
        conrefs = [node for node in root.findall(".//p") if (node.attrib.get("conref") or "").startswith("../missing/")]
        conkeyrefs = [node for node in root.findall(".//p") if (node.attrib.get("conkeyref") or "").startswith("undefined-conkey-")]
        external_xrefs = [node for node in xrefs if (node.attrib.get("href") or "").startswith("https://")]

        require(len(broken_hrefs) == BROKEN_PER_TYPE_PER_TOPIC, f"{topic_path.name} broken href count mismatch")
        require(len(keyrefs) == BROKEN_PER_TYPE_PER_TOPIC, f"{topic_path.name} keyref count mismatch")
        require(len(conrefs) == BROKEN_PER_TYPE_PER_TOPIC, f"{topic_path.name} conref count mismatch")
        require(len(conkeyrefs) == BROKEN_PER_TYPE_PER_TOPIC, f"{topic_path.name} conkeyref count mismatch")
        require(len(external_xrefs) == len(EXTERNAL_LINKS), f"{topic_path.name} external xref count mismatch")
        require(all(node.attrib.get("scope") == "external" for node in external_xrefs), f"{topic_path.name} external scope mismatch")
        require(all(node.attrib.get("format") == "html" for node in external_xrefs), f"{topic_path.name} external format mismatch")
        require_missing_targets_absent(paths.dataset_dir, broken_hrefs, conrefs, topic_path)


def require_missing_targets_absent(
    dataset_dir: Path,
    broken_hrefs: list[ET.Element],
    conrefs: list[ET.Element],
    topic_path: Path,
) -> None:
    for node in [*broken_hrefs, *conrefs]:
        value = node.attrib.get("href") or node.attrib.get("conref") or ""
        target = value.split("#", 1)[0]
        resolved = (topic_path.parent / target).resolve()
        require(dataset_dir.resolve() in resolved.parents, f"target resolved outside dataset: {value}")
        require(not resolved.exists(), f"intentional missing target exists: {resolved}")


def parse_xml_without_doctype(path: Path) -> ET.Element:
    text = path.read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("<!DOCTYPE"))
    return ET.fromstring(text)


def create_zip(paths: DatasetPaths) -> None:
    with zipfile.ZipFile(paths.zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file_path in sorted(paths.dataset_dir.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(paths.root).as_posix())


def validate_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        bad_file = archive.testzip()
        require(bad_file is None, f"ZIP integrity failed at {bad_file}")
        topic_entries = [name for name in archive.namelist() if name.endswith(".dita")]
        require(len(topic_entries) == TOPIC_COUNT, f"ZIP expected {TOPIC_COUNT} topics, found {len(topic_entries)}")
        require(f"{DATASET_NAME}/{DATASET_NAME}.ditamap" in archive.namelist(), "entry map missing from ZIP")
        require(f"{DATASET_NAME}/dataset-manifest.json" in archive.namelist(), "manifest missing from ZIP")
        require(f"{DATASET_NAME}/README.txt" in archive.namelist(), "README missing from ZIP")
        require(not any(f"{DATASET_NAME}/missing/" in name for name in archive.namelist()), "missing directory present in ZIP")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def format_topic_id(index: int) -> str:
    return f"topic_{index:04d}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    raise SystemExit(main())
