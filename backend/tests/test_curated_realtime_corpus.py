"""Tests for curated realtime corpus generator."""

from app.generator.curated_realtime_corpus import (
    _pick_entry,
    _pool_for_source,
    build_recipe_example_xml,
    fetch_stackoverflow_seeds,
    generate_curated_realtime_corpus,
)


class _Cfg:
    seed = "test"
    windows_safe_filenames = True
    doctype_topic = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
    doctype_map = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">'
    xml_lang = "en"


def test_pick_entry_includes_source_tags():
    pools = {
        "stackoverflow": _pool_for_source("stackoverflow", fetch_live=False),
        "blockchain": _pool_for_source("blockchain", fetch_live=False),
    }
    title, shortdesc, tags, source = _pick_entry(0, ["stackoverflow", "blockchain"], pools, __import__("random").Random(1))
    assert title
    assert shortdesc
    assert "aem-guides" in tags
    assert source in ("stackoverflow", "blockchain")


def test_generate_small_curated_corpus():
    files, manifest = generate_curated_realtime_corpus(
        _Cfg(),
        "bundle",
        topic_count=3,
        data_sources=["stackoverflow", "blockchain", "cloud_computing"],
        fetch_live=False,
        map_sample_size=2,
        batch_size=10,
    )
    assert manifest["topic_count"] == 3
    topic_files = [p for p in files if "/topics/curated/curated_" in p.replace("\\", "/")]
    assert len(topic_files) == 3
    sample = next(iter(topic_files))
    xml = files[sample].decode("utf-8")
    assert xml.index("<shortdesc>") < xml.index("<prolog>")
    assert "<prolog>" in xml
    assert 'keyref="product-term"' in xml
    assert 'conref="' in xml
    assert 'scope="external"' in xml
    assert "<codeblock" in xml
    assert 'keyref="curated-logo"' in xml
    assert "<related-links>" in xml
    assert "topic.dtd" in xml
    assert any(p.endswith("curated_variables.dita") for p in files)
    assert any(p.endswith(".png") for p in files)
    map_xml = files[[p for p in files if p.endswith(".ditamap")][0]].decode("utf-8")
    assert "<keydef" in map_xml
    assert any(p.endswith(".ditamap") for p in files)


def test_build_recipe_example_xml_matches_generator_shape():
    xml = build_recipe_example_xml()
    assert "source:stackoverflow" in xml
    assert "source:blockchain" in xml
    assert xml.index("<shortdesc>") < xml.index("<prolog>")
    assert 'keyref="curated-logo"' in xml
    assert 'scope="external"' in xml
    assert "<codeblock" in xml
    assert 'conref="' in xml
    assert "<related-links>" in xml
    assert "<section>" in xml and "<title>Tags</title>" in xml
    assert "curated_root_sample.ditamap" in xml
    assert "<keydef" in xml
    assert "curated_corpus_manifest.json" in xml


def test_stackoverflow_fetch_falls_back_offline():
    seeds = fetch_stackoverflow_seeds(max_items=5)
    assert len(seeds) >= 1
    assert seeds[0][0]
