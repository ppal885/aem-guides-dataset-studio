#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable Dataset Studio recipe for AEM Guides broken-reference scale data."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


RECIPE_NAME = "AEM Guides — 1,000 Topics Broken References with Internal DAM External-Scope Links"
DEFAULT_DATASET_NAME = "aem-guides-1000-topics-broken-links-internal-external-scope"
DEFAULT_INTERNAL_DAM_BASE_PATH = "/content/dam/aem-guides-broken-links-scope-test/nonexistent"
VALID_EXTERNAL_LINKS = (
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
class RecipeConfig:
    topic_count: int = 1000
    broken_href_count_per_topic: int = 10
    broken_keyref_count_per_topic: int = 10
    broken_conref_count_per_topic: int = 10
    broken_conkeyref_count_per_topic: int = 10
    internal_dam_external_scope_link_count: int = 100
    valid_external_links_per_topic: int = 2
    dataset_name: str = DEFAULT_DATASET_NAME
    internal_dam_base_path: str = DEFAULT_INTERNAL_DAM_BASE_PATH


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
    parser.add_argument("--topic-count", type=int, default=1000)
    parser.add_argument("--broken-href-count-per-topic", type=int, default=10)
    parser.add_argument("--broken-keyref-count-per-topic", type=int, default=10)
    parser.add_argument("--broken-conref-count-per-topic", type=int, default=10)
    parser.add_argument("--broken-conkeyref-count-per-topic", type=int, default=10)
    parser.add_argument("--internal-dam-external-scope-link-count", type=int, default=100)
    parser.add_argument("--valid-external-links-per-topic", type=int, default=2)
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--internal-dam-base-path", default=DEFAULT_INTERNAL_DAM_BASE_PATH)
    parser.add_argument("--keep-folder", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = RecipeConfig(
        topic_count=args.topic_count,
        broken_href_count_per_topic=args.broken_href_count_per_topic,
        broken_keyref_count_per_topic=args.broken_keyref_count_per_topic,
        broken_conref_count_per_topic=args.broken_conref_count_per_topic,
        broken_conkeyref_count_per_topic=args.broken_conkeyref_count_per_topic,
        internal_dam_external_scope_link_count=args.internal_dam_external_scope_link_count,
        valid_external_links_per_topic=args.valid_external_links_per_topic,
        dataset_name=args.dataset_name,
        internal_dam_base_path=args.internal_dam_base_path.rstrip("/"),
    )
    validate_config(config)
    paths = build_paths(args.output_dir, config.dataset_name)
    recreate_dataset_dir(paths)
    write_map(paths.map_path, config)
    write_topics(paths.topics_dir, config)
    validate_dataset(paths, config)
    manifest = build_manifest(config, paths, sha256_checksum=dataset_tree_sha256(paths.dataset_dir))
    write_text(paths.manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    write_text(paths.readme_path, build_readme(config))
    validate_dataset(paths, config)
    create_zip(paths)
    zip_checksum = file_sha256(paths.zip_path)
    zip_size = paths.zip_path.stat().st_size
    validate_zip(paths, config)
    if not args.keep_folder:
        shutil.rmtree(paths.dataset_dir)
    print(
        json.dumps(
            {
                "recipe_name": RECIPE_NAME,
                "dataset_name": config.dataset_name,
                "topic_count": config.topic_count,
                "broken_reference_counts_by_type": {
                    "href": config.topic_count * config.broken_href_count_per_topic,
                    "keyref": config.topic_count * config.broken_keyref_count_per_topic,
                    "conref": config.topic_count * config.broken_conref_count_per_topic,
                    "conkeyref": config.topic_count * config.broken_conkeyref_count_per_topic,
                },
                "internal_dam_external_scope_link_count": config.internal_dam_external_scope_link_count,
                "valid_external_link_count": config.topic_count * config.valid_external_links_per_topic,
                "zip": str(paths.zip_path.resolve()),
                "zip_size": zip_size,
                "zip_integrity_status": "passed",
                "sha256_checksum": zip_checksum,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def validate_config(config: RecipeConfig) -> None:
    require(config.topic_count >= 1, "topic_count must be at least 1")
    require(config.valid_external_links_per_topic == len(VALID_EXTERNAL_LINKS), "valid_external_links_per_topic must be 2 for this recipe")
    require(config.internal_dam_external_scope_link_count <= config.topic_count, "internal DAM link count cannot exceed topic_count")
    for name, value in asdict(config).items():
        if name.endswith("_per_topic") or name == "internal_dam_external_scope_link_count":
            require(isinstance(value, int) and value >= 0, f"{name} must be a non-negative integer")
    require(config.dataset_name.strip(), "dataset_name cannot be empty")
    require(config.internal_dam_base_path.startswith("/content/dam/"), "internal_dam_base_path must start with /content/dam/")


def build_paths(output_dir: Path, dataset_name: str) -> DatasetPaths:
    root = output_dir.resolve()
    dataset_dir = root / dataset_name
    return DatasetPaths(
        root=root,
        dataset_dir=dataset_dir,
        topics_dir=dataset_dir / "topics",
        map_path=dataset_dir / f"{dataset_name}.ditamap",
        manifest_path=dataset_dir / "dataset-manifest.json",
        readme_path=dataset_dir / "README.txt",
        zip_path=root / f"{dataset_name}.zip",
    )


def recreate_dataset_dir(paths: DatasetPaths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    if paths.dataset_dir.exists():
        shutil.rmtree(paths.dataset_dir)
    if paths.zip_path.exists():
        paths.zip_path.unlink()
    paths.topics_dir.mkdir(parents=True)


def write_map(path: Path, config: RecipeConfig) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">',
        f'<map id="{safe_xml_id(config.dataset_name)}_map" xml:lang="en-US">',
        f"  <title>{xml_escape(config.dataset_name)} scale dataset</title>",
    ]
    for index in range(1, config.topic_count + 1):
        lines.append(f'  <topicref href="topics/topic-{index:04d}.dita" type="topic"/>')
    lines.append("</map>")
    write_text(path, "\n".join(lines) + "\n")


def write_topics(topics_dir: Path, config: RecipeConfig) -> None:
    for index in range(1, config.topic_count + 1):
        write_text(topics_dir / f"topic-{index:04d}.dita", build_topic_xml(index, config))


def build_topic_xml(index: int, config: RecipeConfig) -> str:
    topic_id = f"scale_topic_{index:04d}"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">',
        f'<topic id="{topic_id}" xml:lang="en-US">',
        f"  <title>Broken Reference Scale Topic {index:04d}</title>",
        "  <shortdesc>Scale dataset topic for validating AEM Guides Broken Links Report reference classification.</shortdesc>",
        "  <body>",
        '    <section id="broken_local_href_references">',
        "      <title>Broken local href references</title>",
        "      <ul>",
    ]
    for number in range(1, config.broken_href_count_per_topic + 1):
        target_id = f"missing_topic_{index:04d}_{number:02d}"
        lines.extend(
            [
                "        <li>",
                f'          <xref href="../missing/missing-topic-{index:04d}-{number:02d}.dita#{target_id}">Intentionally broken local DITA href {number:02d}</xref>',
                "        </li>",
            ]
        )
    lines.extend(["      </ul>", "    </section>", '    <section id="unresolved_keyrefs">', "      <title>Unresolved keyrefs</title>", "      <ul>"])
    for number in range(1, config.broken_keyref_count_per_topic + 1):
        lines.extend(
            [
                "        <li>",
                f'          <xref keyref="undefined-key-{index:04d}-{number:02d}">Intentionally unresolved keyref {number:02d}</xref>',
                "        </li>",
            ]
        )
    lines.extend(["      </ul>", "    </section>", '    <section id="broken_conrefs">', "      <title>Broken conrefs</title>"])
    for number in range(1, config.broken_conref_count_per_topic + 1):
        target_id = f"missing_conref_topic_{index:04d}_{number:02d}"
        lines.append(
            f'      <p conref="../missing/missing-conref-topic-{index:04d}-{number:02d}.dita#{target_id}/missing_p">Fallback content for intentionally broken conref {number:02d}</p>'
        )
    lines.extend(["    </section>", '    <section id="unresolved_conkeyrefs">', "      <title>Unresolved conkeyrefs</title>"])
    for number in range(1, config.broken_conkeyref_count_per_topic + 1):
        lines.append(
            f'      <p conkeyref="undefined-conkey-{index:04d}-{number:02d}/missing_p">Fallback content for intentionally unresolved conkeyref {number:02d}</p>'
        )
    if index <= config.internal_dam_external_scope_link_count:
        lines.extend(
            [
                "    </section>",
                '    <section id="internal_dam_reference_marked_external">',
                "      <title>Internal DAM reference marked as external</title>",
                "      <ul>",
                "        <li>",
                f'          <xref href="{config.internal_dam_base_path}/internal-target-{index:04d}.dita#internal_target_{index:04d}" scope="external" format="dita">Intentionally broken internal DAM reference {index:04d} marked as external</xref>',
                "        </li>",
                "      </ul>",
            ]
        )
    lines.extend(
        [
            "    </section>",
            '    <section id="valid_external_html_links">',
            "      <title>Valid external HTML links</title>",
            "      <ul>",
        ]
    )
    for link in VALID_EXTERNAL_LINKS[: config.valid_external_links_per_topic]:
        lines.extend(
            [
                "        <li>",
                f'          <xref href="{link["href"]}" scope="{link["scope"]}" format="{link["format"]}">{link["text"]}</xref>',
                "        </li>",
            ]
        )
    lines.extend(["      </ul>", "    </section>", "  </body>", "</topic>"])
    return "\n".join(lines) + "\n"


def build_manifest(config: RecipeConfig, paths: DatasetPaths, *, sha256_checksum: str) -> dict[str, object]:
    href_total = config.topic_count * config.broken_href_count_per_topic
    keyref_total = config.topic_count * config.broken_keyref_count_per_topic
    conref_total = config.topic_count * config.broken_conref_count_per_topic
    conkeyref_total = config.topic_count * config.broken_conkeyref_count_per_topic
    standard_total = href_total + keyref_total + conref_total + conkeyref_total
    zip_entry_count = config.topic_count + 3
    return {
        "recipe_name": RECIPE_NAME,
        "recipe_parameters": asdict(config),
        "dataset_name": config.dataset_name,
        "entry_map_filename": f"{config.dataset_name}.ditamap",
        "topic_count": config.topic_count,
        "map_topicref_count": config.topic_count,
        "broken_href_count_per_topic": config.broken_href_count_per_topic,
        "broken_keyref_count_per_topic": config.broken_keyref_count_per_topic,
        "broken_conref_count_per_topic": config.broken_conref_count_per_topic,
        "broken_conkeyref_count_per_topic": config.broken_conkeyref_count_per_topic,
        "total_broken_href_count": href_total,
        "total_broken_keyref_count": keyref_total,
        "total_broken_conref_count": conref_total,
        "total_broken_conkeyref_count": conkeyref_total,
        "standard_broken_reference_total": standard_total,
        "internal_dam_external_scope_reference_count": config.internal_dam_external_scope_link_count,
        "internal_dam_base_path": config.internal_dam_base_path,
        "internal_dam_scope_value": "external",
        "internal_dam_format_value": "dita",
        "internal_dam_reference_distribution": f"topic-0001.dita through topic-{config.internal_dam_external_scope_link_count:04d}.dita",
        "overall_intentional_broken_reference_total": standard_total + config.internal_dam_external_scope_link_count,
        "valid_external_link_count_per_topic": config.valid_external_links_per_topic,
        "total_valid_external_link_count": config.topic_count * config.valid_external_links_per_topic,
        "valid_external_urls": VALID_EXTERNAL_LINKS[: config.valid_external_links_per_topic],
        "intentionally_missing_targets_generated": False,
        "missing_directory_intentionally_absent": True,
        "zip_filename": paths.zip_path.name,
        "zip_entry_count": zip_entry_count,
        "generated_timestamp": datetime.now(timezone.utc).isoformat(),
        "sha256_checksum": sha256_checksum,
        "sha256_checksum_scope": "generated dataset tree before archive creation",
    }


def build_readme(config: RecipeConfig) -> str:
    standard_total = config.topic_count * (
        config.broken_href_count_per_topic
        + config.broken_keyref_count_per_topic
        + config.broken_conref_count_per_topic
        + config.broken_conkeyref_count_per_topic
    )
    return f"""AEM Guides Broken References Dataset

Recipe:
{RECIPE_NAME}

Upload:
1. Extract {config.dataset_name}.zip.
2. Upload the extracted {config.dataset_name} folder into AEM Assets.
3. Open {config.dataset_name}.ditamap as the entry map in AEM Guides.

Run the Broken Links Report:
1. Open the entry map in AEM Guides.
2. Run the Broken Links Report from the map/reporting workflow.
3. Capture counts, classification, memory behavior, runtime, and any skipped references.

Intentional broken references:
- Broken local href xrefs point to ../missing/*.dita files that are not packaged.
- Unresolved keyrefs use undefined-key-* values that are never declared.
- Broken conrefs point to ../missing/*.dita files and missing element IDs.
- Unresolved conkeyrefs use undefined-conkey-* values that are never declared.
- The missing directory is absent by design so these references remain broken.

Internal DAM external-scope edge case:
- The first {config.internal_dam_external_scope_link_count} topics each contain one /content/dam reference.
- These links deliberately use scope="external" and format="dita".
- Record whether AEM Guides reports, ignores, or misclassifies these internal repository paths.

Valid external HTML links:
- Every topic contains {config.valid_external_links_per_topic} valid external HTML links.
- These links use scope="external" and format="html".
- They must not be treated as local DITA targets.

Expected counts:
- Topic files: {config.topic_count}
- Map topicrefs: {config.topic_count}
- Broken href references: {config.topic_count * config.broken_href_count_per_topic}
- Unresolved keyrefs: {config.topic_count * config.broken_keyref_count_per_topic}
- Broken conrefs: {config.topic_count * config.broken_conref_count_per_topic}
- Unresolved conkeyrefs: {config.topic_count * config.broken_conkeyref_count_per_topic}
- Standard broken references: {standard_total}
- Broken internal DAM links with external scope: {config.internal_dam_external_scope_link_count}
- Total intentional broken references: {standard_total + config.internal_dam_external_scope_link_count}
- Valid external HTML links: {config.topic_count * config.valid_external_links_per_topic}

Purpose:
This dataset is intended for AEM Guides Broken Links Report scale, classification, correctness, and reliability testing.
"""


def validate_dataset(paths: DatasetPaths, config: RecipeConfig) -> None:
    require(not (paths.dataset_dir / "missing").exists(), "missing directory must be absent")
    topic_paths = sorted(paths.topics_dir.glob("*.dita"))
    require(len(topic_paths) == config.topic_count, f"expected {config.topic_count} topics, found {len(topic_paths)}")
    map_root = parse_xml_without_doctype(paths.map_path)
    topicrefs = map_root.findall(".//topicref")
    require(len(topicrefs) == config.topic_count, f"expected {config.topic_count} topicrefs, found {len(topicrefs)}")
    require([node.attrib.get("href") for node in topicrefs] == [f"topics/topic-{i:04d}.dita" for i in range(1, config.topic_count + 1)], "topicrefs are not ascending zero-padded topics")
    require_no_undefined_keys_declared(map_root)

    internal_dam_links: list[tuple[int, ET.Element]] = []
    for topic_path in topic_paths:
        topic_index = int(topic_path.stem.split("-")[-1])
        root = parse_xml_without_doctype(topic_path)
        require(root.tag == "topic", f"{topic_path.name} root must be topic")
        require(root.attrib.get("id") == f"scale_topic_{topic_index:04d}", f"{topic_path.name} has unexpected topic id")
        require(root.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") == "en-US", f"{topic_path.name} must set xml:lang=en-US")
        require_no_undefined_keys_declared(root)

        xrefs = root.findall(".//xref")
        p_nodes = root.findall(".//p")
        broken_hrefs = [node for node in xrefs if (node.attrib.get("href") or "").startswith("../missing/")]
        keyrefs = [node for node in xrefs if (node.attrib.get("keyref") or "").startswith("undefined-key-")]
        conrefs = [node for node in p_nodes if (node.attrib.get("conref") or "").startswith("../missing/")]
        conkeyrefs = [node for node in p_nodes if (node.attrib.get("conkeyref") or "").startswith("undefined-conkey-")]
        dam_links = [node for node in xrefs if (node.attrib.get("href") or "").startswith("/content/dam/")]
        external_html = [node for node in xrefs if (node.attrib.get("href") or "").startswith("https://")]

        require(len(broken_hrefs) == config.broken_href_count_per_topic, f"{topic_path.name} broken href count mismatch")
        require(len(keyrefs) == config.broken_keyref_count_per_topic, f"{topic_path.name} keyref count mismatch")
        require(len(conrefs) == config.broken_conref_count_per_topic, f"{topic_path.name} conref count mismatch")
        require(len(conkeyrefs) == config.broken_conkeyref_count_per_topic, f"{topic_path.name} conkeyref count mismatch")
        require(len(external_html) == config.valid_external_links_per_topic, f"{topic_path.name} valid external HTML count mismatch")
        require(all(node.attrib.get("scope") == "external" and node.attrib.get("format") == "html" for node in external_html), f"{topic_path.name} external HTML attributes mismatch")
        require_missing_targets_absent(paths.dataset_dir, topic_path, broken_hrefs, conrefs)

        if topic_index <= config.internal_dam_external_scope_link_count:
            require(len(dam_links) == 1, f"{topic_path.name} must contain one internal DAM external-scope link")
            require(dam_links[0].attrib.get("scope") == "external", f"{topic_path.name} DAM scope mismatch")
            require(dam_links[0].attrib.get("format") == "dita", f"{topic_path.name} DAM format mismatch")
            require(not packaged_dam_target_exists(paths.dataset_dir, dam_links[0].attrib["href"]), f"{topic_path.name} DAM target was packaged")
            internal_dam_links.append((topic_index, dam_links[0]))
        else:
            require(not dam_links, f"{topic_path.name} must not contain an internal DAM external-scope link")

    require(len(internal_dam_links) == config.internal_dam_external_scope_link_count, "internal DAM link total mismatch")
    if config.internal_dam_external_scope_link_count >= 100:
        topic_0100 = paths.topics_dir / "topic-0100.dita"
        topic_0101 = paths.topics_dir / "topic-0101.dita"
        require('/content/dam/' in topic_0100.read_text(encoding="utf-8"), "topic-0100 must contain special DAM link")
        if topic_0101.exists():
            require('/content/dam/' not in topic_0101.read_text(encoding="utf-8"), "topic-0101 must not contain special DAM link")


def require_no_undefined_keys_declared(root: ET.Element) -> None:
    for element in root.iter():
        keys = element.attrib.get("keys", "")
        require(not any(key.startswith(("undefined-key-", "undefined-conkey-")) for key in keys.split()), "undefined test key accidentally declared")


def require_missing_targets_absent(dataset_dir: Path, topic_path: Path, broken_hrefs: list[ET.Element], conrefs: list[ET.Element]) -> None:
    for node in [*broken_hrefs, *conrefs]:
        value = node.attrib.get("href") or node.attrib.get("conref") or ""
        target = value.split("#", 1)[0]
        resolved = (topic_path.parent / target).resolve()
        require(dataset_dir.resolve() in resolved.parents, f"target resolved outside dataset: {value}")
        require(not resolved.exists(), f"intentionally missing target was generated: {resolved}")


def packaged_dam_target_exists(dataset_dir: Path, href: str) -> bool:
    relative = href.split("#", 1)[0].lstrip("/")
    return (dataset_dir / relative).exists()


def create_zip(paths: DatasetPaths) -> None:
    with zipfile.ZipFile(paths.zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for file_path in sorted(paths.dataset_dir.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(paths.root).as_posix())


def validate_zip(paths: DatasetPaths, config: RecipeConfig) -> None:
    with zipfile.ZipFile(paths.zip_path, "r") as archive:
        bad_file = archive.testzip()
        require(bad_file is None, f"ZIP integrity failed at {bad_file}")
        names = archive.namelist()
        require(len([name for name in names if name.endswith(".dita")]) == config.topic_count, "ZIP topic count mismatch")
        require(f"{config.dataset_name}/{config.dataset_name}.ditamap" in names, "entry map missing from ZIP")
        require(f"{config.dataset_name}/dataset-manifest.json" in names, "manifest missing from ZIP")
        require(f"{config.dataset_name}/README.txt" in names, "README missing from ZIP")
        require(not any(f"{config.dataset_name}/missing/" in name for name in names), "missing directory must not be packaged")
        manifest = json.loads(archive.read(f"{config.dataset_name}/dataset-manifest.json").decode("utf-8"))
        expected_total = (
            config.topic_count
            * (
                config.broken_href_count_per_topic
                + config.broken_keyref_count_per_topic
                + config.broken_conref_count_per_topic
                + config.broken_conkeyref_count_per_topic
            )
            + config.internal_dam_external_scope_link_count
        )
        require(manifest["overall_intentional_broken_reference_total"] == expected_total, "manifest grand total mismatch")
        if config.topic_count == 1000 and config.internal_dam_external_scope_link_count == 100:
            require(manifest["overall_intentional_broken_reference_total"] == 40100, "manifest must report 40,100 broken references")


def parse_xml_without_doctype(path: Path) -> ET.Element:
    text = path.read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("<!DOCTYPE"))
    return ET.fromstring(text)


def dataset_tree_sha256(dataset_dir: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(path for path in dataset_dir.rglob("*") if path.is_file()):
        digest.update(file_path.relative_to(dataset_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def safe_xml_id(value: str) -> str:
    out = "".join(char if char.isalnum() else "_" for char in value)
    return out if out and (out[0].isalpha() or out[0] == "_") else f"dataset_{out}"


def xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    raise SystemExit(main())
