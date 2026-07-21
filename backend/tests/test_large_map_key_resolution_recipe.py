import csv
import io
import zipfile
import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError

from app.generator.large_key_resolution import generate_large_map_key_resolution_dataset
from app.generator.recipe_manifest import discover_recipe_specs
from app.jobs.schemas import DatasetConfig
from app.services.recipe_catalog_service import get_recipe_catalog
from app.tasks.generate_dataset import run_generate_dataset


def _config(recipe: dict) -> dict:
    return {
        "name": "large-key-resolution-test",
        "seed": "large-key-seed",
        "root_folder": "/content/dam/key-resolution-test",
        "windows_safe_filenames": True,
        "doctype_topic": '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
        "doctype_map": '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
        "recipes": [recipe],
    }


def _generated(recipe: dict) -> dict[str, bytes]:
    return run_generate_dataset(_config(recipe), "job-large-key-resolution")


def _main_files(files: dict[str, bytes], key_count: int) -> tuple[str, str, str, str]:
    root = f"content/dam/key-resolution-test/large-key-resolution-{key_count}"
    return (
        f"{root}/key-resolution-{key_count}-map.ditamap",
        f"{root}/large-keyref-topic-{key_count}.dita",
        f"{root}/expected-key-values.csv",
        f"{root}.zip",
    )


def _defs_and_refs(files: dict[str, bytes], key_count: int) -> tuple[list[str], list[str]]:
    map_path, topic_path, _, _ = _main_files(files, key_count)
    map_root = ET.fromstring(files[map_path])
    topic_root = ET.fromstring(files[topic_path])
    defs = [elem.attrib["keys"] for elem in map_root.findall("keydef")]
    refs = [elem.attrib["keyref"] for elem in topic_root.iter("keyword") if "keyref" in elem.attrib]
    return defs, refs


def test_large_key_resolution_default_500_generation():
    files = _generated({"type": "large_map_key_resolution"})
    map_path, topic_path, csv_path, zip_path = _main_files(files, 500)

    assert map_path in files
    assert topic_path in files
    assert csv_path in files
    assert zip_path in files
    defs, refs = _defs_and_refs(files, 500)
    assert len(defs) == 500
    assert len(refs) == 500
    assert defs[0] == "product-key-001"
    assert defs[-1] == "product-key-500"
    assert set(defs) == set(refs)


def test_large_key_resolution_2000_generation():
    files = _generated({"type": "large_map_key_resolution", "key_count": 2000, "keys_per_section": 100})
    defs, refs = _defs_and_refs(files, 2000)

    assert len(defs) == 2000
    assert defs[0] == "product-key-001"
    assert defs[-1] == "product-key-2000"
    assert set(defs) == set(refs)


def test_large_key_resolution_minimum_count():
    files = _generated({"type": "large_map_key_resolution", "key_count": 1})
    defs, refs = _defs_and_refs(files, 1)

    assert defs == ["product-key-001"]
    assert refs == ["product-key-001"]


def test_large_key_resolution_maximum_count_direct_generator():
    cfg = DatasetConfig.model_validate(_config({"type": "large_map_key_resolution", "key_count": 10000}))
    files = generate_large_map_key_resolution_dataset(
        cfg,
        "content/dam/key-resolution-test",
        key_count=10000,
        keys_per_section=250,
        create_zip=False,
    )
    defs, refs = _defs_and_refs(files, 10000)

    assert len(defs) == 10000
    assert defs[-1] == "product-key-10000"
    assert set(defs) == set(refs)


@pytest.mark.parametrize("key_count", [0, -1, 10001])
def test_large_key_resolution_invalid_key_count_rejected(key_count: int):
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(_config({"type": "large_map_key_resolution", "key_count": key_count}))


@pytest.mark.parametrize("key_prefix", ["", "1bad", "bad prefix", "bad/key"])
def test_large_key_resolution_invalid_key_prefix_rejected(key_prefix: str):
    with pytest.raises(ValidationError):
        DatasetConfig.model_validate(_config({"type": "large_map_key_resolution", "key_prefix": key_prefix}))


def test_large_key_resolution_non_divisible_sections_unique_ids_and_csv_rows():
    files = _generated({"type": "large_map_key_resolution", "key_count": 103, "keys_per_section": 25})
    _, topic_path, csv_path, _ = _main_files(files, 103)
    topic_root = ET.fromstring(files[topic_path])
    section_ids = [elem.attrib["id"] for elem in topic_root.findall(".//section")]
    all_ids = [elem.attrib["id"] for elem in topic_root.iter() if "id" in elem.attrib]
    rows = list(csv.DictReader(io.StringIO(files[csv_path].decode("utf-8"))))

    assert section_ids[-1] == "keys-101-103"
    assert len(all_ids) == len(set(all_ids))
    assert len(rows) == 103
    assert rows[-1]["key"] == "product-key-103"


def test_large_key_resolution_zip_contents():
    files = _generated({"type": "large_map_key_resolution", "key_count": 10})
    _, _, _, zip_path = _main_files(files, 10)

    with zipfile.ZipFile(io.BytesIO(files[zip_path])) as archive:
        names = set(archive.namelist())
        assert archive.testzip() is None
    assert {
        "key-resolution-10-map.ditamap",
        "large-keyref-topic-10.dita",
        "expected-key-values.csv",
        "README.md",
    }.issubset(names)


def test_large_key_resolution_recipe_registration_and_catalog_availability():
    specs = {spec.id: spec for spec in discover_recipe_specs()}
    catalog_ids = {entry["id"] for entry in get_recipe_catalog()["entries"]}

    assert "large_map_key_resolution" in specs
    assert specs["large_map_key_resolution"].title == "Large Map Key Resolution"
    assert "large_map_key_resolution" in catalog_ids


def test_existing_keydef_heavy_recipe_still_generates():
    files = _generated({"type": "keydef_heavy", "topic_count": 10, "keydef_count": 5})

    assert files
    assert any(path.endswith(".ditamap") for path in files)
