"""Smoke tests for bulk_dita_map_topics recipe generator."""
from types import SimpleNamespace

from app.generator.bulk_dita_map_topics import generate_bulk_dita_map_topics_dataset


def test_generate_bulk_dita_map_topics_small_count_stubs_and_doctypes():
    cfg = SimpleNamespace(
        doctype_topic=(
            '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">'
        ),
        doctype_map='<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
    )
    files = generate_bulk_dita_map_topics_dataset(cfg, "dataset", 3, include_readme=True, pretty_print=True)
    assert "dataset/dita_dataset_3/topics/topic_00001.dita" in files
    assert "dataset/dita_dataset_3/topics/topic_00003.dita" in files
    assert "dataset/dita_dataset_3/rootmap_3.ditamap" in files
    assert "dataset/dita_dataset_3/README.txt" in files
    assert "dataset/dita_dataset_3/technicalContent/dtd/topic.dtd" in files
    assert "dataset/dita_dataset_3/technicalContent/dtd/map.dtd" in files

    topic_xml = files["dataset/dita_dataset_3/topics/topic_00001.dita"].decode("utf-8")
    assert "../technicalContent/dtd/topic.dtd" in topic_xml

    map_xml = files["dataset/dita_dataset_3/rootmap_3.ditamap"].decode("utf-8")
    assert "topicref" in map_xml
    assert "topics/topic_00001.dita" in map_xml
    assert 'navtitle="Generated Topic 00001"' in map_xml
    assert 'technicalContent/dtd/map.dtd' in map_xml

    stub_topic = files["dataset/dita_dataset_3/technicalContent/dtd/topic.dtd"].decode("utf-8")
    assert "<!ELEMENT topic" in stub_topic


def test_generate_bulk_dita_map_topics_without_technical_content_stubs():
    cfg = SimpleNamespace(
        doctype_topic='<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">',
        doctype_map='<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">',
    )
    files = generate_bulk_dita_map_topics_dataset(
        cfg,
        "dataset",
        2,
        include_readme=False,
        pretty_print=True,
        include_local_dtd_stubs=False,
    )
    assert "dataset/dita_dataset_2/topic.dtd" in files
    assert "dataset/dita_dataset_2/map.dtd" in files
    assert "dataset/dita_dataset_2/technicalContent/dtd/topic.dtd" not in files

    topic_xml = files["dataset/dita_dataset_2/topics/topic_00001.dita"].decode("utf-8")
    assert "../topic.dtd" in topic_xml
    map_xml = files["dataset/dita_dataset_2/rootmap_2.ditamap"].decode("utf-8")
    assert "map.dtd" in map_xml
    assert "technicalContent" not in map_xml
