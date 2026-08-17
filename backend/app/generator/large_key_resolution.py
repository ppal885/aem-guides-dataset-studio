"""Large map key-resolution scale recipe.

Generates one DITA map with many map-defined keys and one large topic that
references every key exactly once.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import PurePosixPath
from typing import Dict
import xml.etree.ElementTree as ET

from app.generator.recipe_manifest import RecipeSpec
from app.jobs.schemas import DatasetConfig


RECIPE_ID = "large_map_key_resolution"
RECIPE_TITLE = "Large Map Key Resolution"
KEY_PREFIX_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
KEY_VALUE_TEMPLATE = "Enterprise configuration value {index:03d} for AEM Guides key-resolution validation"


class LargeKeyResolutionValidationError(ValueError):
    """User-facing validation failure for large key-resolution recipe inputs."""


def _validate_inputs(key_count: int, keys_per_section: int, key_prefix: str) -> tuple[int, int, str]:
    try:
        key_count = int(key_count)
        keys_per_section = int(keys_per_section)
    except Exception as exc:
        raise LargeKeyResolutionValidationError("key_count and keys_per_section must be integers") from exc

    key_prefix = (key_prefix or "product-key").strip()
    if key_count < 1:
        raise LargeKeyResolutionValidationError("key_count must be at least 1")
    if key_count > 10000:
        raise LargeKeyResolutionValidationError("key_count cannot exceed 10000")
    if keys_per_section < 1:
        raise LargeKeyResolutionValidationError("keys_per_section must be at least 1")
    if not KEY_PREFIX_PATTERN.fullmatch(key_prefix):
        raise LargeKeyResolutionValidationError(
            "key_prefix must start with a letter or underscore and contain only letters, numbers, '.', '_' or '-'"
        )
    return key_count, keys_per_section, key_prefix


def _key_name(prefix: str, index: int) -> str:
    return f"{prefix}-{index:03d}"


def _xml_text(value: str) -> str:
    from xml.sax.saxutils import escape

    return escape(value or "", entities={'"': "&quot;"})


def _map_xml(config: DatasetConfig, *, key_count: int, key_prefix: str, map_title: str, topic_href: str) -> bytes:
    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write(f"{config.doctype_map}\n")
    out.write('<map id="large-key-resolution-map" xml:lang="en-US">\n')
    out.write(f"  <title>{_xml_text(map_title)}</title>\n")
    for index in range(1, key_count + 1):
        key = _key_name(key_prefix, index)
        value = KEY_VALUE_TEMPLATE.format(index=index)
        out.write(f'  <keydef keys="{key}">\n')
        out.write("    <topicmeta>\n")
        out.write("      <keywords>\n")
        out.write(f"        <keyword>{_xml_text(value)}</keyword>\n")
        out.write("      </keywords>\n")
        out.write("    </topicmeta>\n")
        out.write("  </keydef>\n")
    out.write(f'  <topicref href="{topic_href}"/>\n')
    out.write("</map>\n")
    return out.getvalue().encode("utf-8")


def _topic_xml(
    config: DatasetConfig,
    *,
    key_count: int,
    keys_per_section: int,
    key_prefix: str,
    topic_title: str,
) -> bytes:
    out = io.StringIO()
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    out.write(f"{config.doctype_topic}\n")
    out.write('<topic id="large-keyref-topic" xml:lang="en-US">\n')
    out.write(f"  <title>{_xml_text(topic_title)}</title>\n")
    out.write("  <shortdesc>One large topic that consumes every map-defined key exactly once.</shortdesc>\n")
    out.write("  <body>\n")
    for start in range(1, key_count + 1, keys_per_section):
        end = min(start + keys_per_section - 1, key_count)
        out.write(f'    <section id="keys-{start:03d}-{end:03d}">\n')
        out.write(f"      <title>Resolved keys {start:03d} through {end:03d}</title>\n")
        out.write("      <dl>\n")
        for index in range(start, end + 1):
            key = _key_name(key_prefix, index)
            out.write(f'        <dlentry id="keyref-{index:03d}">\n')
            out.write(f"          <dt>{key}</dt>\n")
            out.write(f'          <dd><keyword keyref="{key}"/></dd>\n')
            out.write("        </dlentry>\n")
        out.write("      </dl>\n")
        out.write("    </section>\n")
    out.write("  </body>\n")
    out.write("</topic>\n")
    return out.getvalue().encode("utf-8")


def _expected_csv(*, key_count: int, key_prefix: str) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["key", "resolved-value"])
    for index in range(1, key_count + 1):
        writer.writerow([_key_name(key_prefix, index), KEY_VALUE_TEMPLATE.format(index=index)])
    return out.getvalue().encode("utf-8")


def _readme(
    *,
    key_count: int,
    keys_per_section: int,
    map_name: str,
    topic_name: str,
    csv_name: str,
    include_expected_values: bool,
) -> bytes:
    del include_expected_values
    csv_line = f"- `{csv_name}`: expected key-to-value oracle CSV."
    return f"""# Large Map Key Resolution

Generated key count: {key_count}
Keys per section: {keys_per_section}

## Files
- `{map_name}`: root DITA map containing exactly {key_count} map-defined keys and one topicref.
- `{topic_name}`: one large topic containing exactly {key_count} key references.
{csv_line}
- `README.md`: this guide.

## AEM Guides Upload Steps
1. Upload all generated files into the same DAM folder.
2. Keep the map and topic side by side exactly as generated.
3. Open `{map_name}` in AEM Guides.
4. Open `{topic_name}` from the map context, not as a standalone topic.

## Expected Result
- All `{key_count}` keys resolve.
- Zero unresolved keys.
- The set of map `keydef/@keys` values matches the set of topic `keyword/@keyref` values exactly.

## Suggested Performance Measurements
- Map opening time
- Topic opening time
- Author-mode rendering time
- Source-to-Author switching time
- Preview time
- Save time
- Publishing duration
- Browser peak memory
- Server errors and timeouts
""".encode("utf-8")


def _validate_generated_files(files: Dict[str, bytes], *, key_count: int, create_zip: bool, dataset_root: str) -> None:
    map_paths = [path for path in files if path.endswith(".ditamap")]
    topic_paths = [path for path in files if path.endswith(".dita")]
    csv_paths = [path for path in files if path.endswith("expected-key-values.csv")]
    readme_paths = [path for path in files if path.endswith("README.md")]
    if len(map_paths) != 1 or len(topic_paths) != 1 or len(readme_paths) != 1:
        raise LargeKeyResolutionValidationError("generated dataset must contain one map, one topic, and one README")
    if not csv_paths:
        raise LargeKeyResolutionValidationError("generated dataset must contain expected-key-values.csv")

    map_root = ET.fromstring(files[map_paths[0]])
    topic_root = ET.fromstring(files[topic_paths[0]])
    keydefs = [elem.attrib.get("keys", "") for elem in map_root.findall("keydef")]
    keyrefs = [elem.attrib.get("keyref", "") for elem in topic_root.iter("keyword") if elem.attrib.get("keyref")]
    if len(keydefs) != key_count:
        raise LargeKeyResolutionValidationError("number of key definitions does not match key_count")
    if len(set(keydefs)) != key_count:
        raise LargeKeyResolutionValidationError("generated key definitions contain duplicates")
    if len(keyrefs) != key_count:
        raise LargeKeyResolutionValidationError("number of key references does not match key_count")
    if set(keydefs) != set(keyrefs):
        raise LargeKeyResolutionValidationError("key definition and key reference sets do not match exactly")

    ids = [elem.attrib["id"] for elem in topic_root.iter() if "id" in elem.attrib]
    if len(ids) != len(set(ids)):
        raise LargeKeyResolutionValidationError("generated topic contains duplicate XML IDs")

    csv_rows = files[csv_paths[0]].decode("utf-8").splitlines()
    if len(csv_rows) != key_count + 1:
        raise LargeKeyResolutionValidationError("CSV row count does not match key_count")

    if create_zip:
        zip_path = f"{dataset_root}.zip"
        if zip_path not in files:
            raise LargeKeyResolutionValidationError("ZIP generation enabled but ZIP file is missing")
        with zipfile.ZipFile(io.BytesIO(files[zip_path]), "r") as archive:
            bad_file = archive.testzip()
            if bad_file:
                raise LargeKeyResolutionValidationError(f"ZIP integrity check failed at {bad_file}")
            names = set(archive.namelist())
            expected = {PurePosixPath(path).name for path in map_paths + topic_paths + csv_paths + readme_paths}
            zip_leaf_names = {PurePosixPath(name).name for name in names}
            if not expected.issubset(zip_leaf_names):
                raise LargeKeyResolutionValidationError("ZIP does not contain the complete generated dataset")


def _zip_dataset(files: Dict[str, bytes], dataset_root: str) -> bytes:
    prefix = f"{dataset_root}/"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            if path.startswith(prefix):
                archive.writestr(path[len(prefix):], files[path])
    return out.getvalue()


def generate_large_map_key_resolution_dataset(
    config: DatasetConfig,
    base_path: str,
    *,
    key_count: int = 500,
    keys_per_section: int = 25,
    key_prefix: str = "product-key",
    map_title: str = "Large Key Resolution Performance Map",
    topic_title: str = "Large Topic Resolving Map-Defined Keys",
    include_expected_values: bool = True,
    create_zip: bool = True,
    **kwargs,
) -> Dict[str, bytes]:
    del kwargs
    key_count, keys_per_section, key_prefix = _validate_inputs(key_count, keys_per_section, key_prefix)
    dataset_root = f"{base_path.rstrip('/')}/large-key-resolution-{key_count}"
    map_name = f"key-resolution-{key_count}-map.ditamap"
    topic_name = f"large-keyref-topic-{key_count}.dita"
    csv_name = "expected-key-values.csv"
    files: Dict[str, bytes] = {}
    files[f"{dataset_root}/{map_name}"] = _map_xml(
        config,
        key_count=key_count,
        key_prefix=key_prefix,
        map_title=map_title,
        topic_href=topic_name,
    )
    files[f"{dataset_root}/{topic_name}"] = _topic_xml(
        config,
        key_count=key_count,
        keys_per_section=keys_per_section,
        key_prefix=key_prefix,
        topic_title=topic_title,
    )
    files[f"{dataset_root}/{csv_name}"] = _expected_csv(key_count=key_count, key_prefix=key_prefix)
    files[f"{dataset_root}/README.md"] = _readme(
        key_count=key_count,
        keys_per_section=keys_per_section,
        map_name=map_name,
        topic_name=topic_name,
        csv_name=csv_name,
        include_expected_values=include_expected_values,
    )
    if create_zip:
        files[f"{dataset_root}.zip"] = _zip_dataset(files, dataset_root)
    _validate_generated_files(files, key_count=key_count, create_zip=create_zip, dataset_root=dataset_root)
    return files


RECIPE_SPECS = [
    RecipeSpec(
        id=RECIPE_ID,
        title=RECIPE_TITLE,
        description=(
            "Generate a DITA map and one large topic for validating hundreds or thousands of "
            "map-defined key references."
        ),
        tags=["KEYDEF", "KEYREF", "SCALE", "PERFORMANCE", "AEM_GUIDES"],
        module="app.generator.large_key_resolution",
        function="generate_large_map_key_resolution_dataset",
        params_schema={
            "key_count": "int",
            "keys_per_section": "int",
            "key_prefix": "str",
            "map_title": "str",
            "topic_title": "str",
            "include_expected_values": "bool",
            "create_zip": "bool",
        },
        default_params={
            "key_count": 500,
            "keys_per_section": 25,
            "key_prefix": "product-key",
            "map_title": "Large Key Resolution Performance Map",
            "topic_title": "Large Topic Resolving Map-Defined Keys",
            "include_expected_values": True,
            "create_zip": True,
        },
        stability="stable",
        constructs=["keydef", "keyref", "keyword", "topicmeta", "keywords", "map", "topicref"],
        scenario_types=["SCALE", "PERFORMANCE", "PUBLISHING", "EDITOR"],
        use_when=[
            "large map key resolution",
            "hundreds or thousands of map-defined keys",
            "AEM Guides keyref scale testing",
            "Editor Preview publishing key resolution performance",
        ],
        avoid_when=["keyscope shadowing", "duplicate key negative testing", "small minimal keyref repro"],
        positive_negative="positive",
        complexity="stress",
        aem_guides_features=["Editor", "Preview", "Publishing", "Map context", "Key resolution"],
        output_scale="stress",
        mechanism_family="keyref",
        topic_type="mixed",
        intent_tags=["large-key-resolution", "keyref-scale", "map-defined-keys"],
        trigger_phrases=[
            "large map key resolution",
            "thousands of keyrefs",
            "many map-defined keys",
            "key resolution performance",
        ],
        required_constructs=[
            {"name": "keydef", "min_count": 1},
            {"name": "keyword keyref", "min_count": 1},
        ],
        validation_rules=[
            {"id": "keydefs_match_keyrefs", "description": "Every generated keydef is referenced exactly once."},
        ],
        retrieval_keywords=["keydef", "keyref", "keyword", "large map", "performance", "AEM Guides"],
        retrieval_element_hints=["keydef", "keyword", "topicmeta", "topicref"],
        examples=[
            {"prompt": "Generate 2000 map-defined keys and one large topic that resolves every key."},
            {"prompt": "Create a key resolution performance dataset for AEM Guides Preview and publishing."},
        ],
        example_input="key_count=500, keys_per_section=25",
        example_output="large-key-resolution-500/key-resolution-500-map.ditamap plus one large keyref topic.",
    )
]
