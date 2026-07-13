"""Curated corpus generation defaults and artifact-reuse bypass."""

from app.generator.curated_realtime_corpus import CORPUS_SCHEMA_VERSION, generate_curated_realtime_corpus
from app.services.dataset_job_service import (
    apply_dataset_generation_defaults,
    config_skips_artifact_reuse,
)


class _Cfg:
    seed = "fd2b1475"
    windows_safe_filenames = True
    doctype_topic = (
        '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "../../technicalContent/dtd/topic.dtd">'
    )
    doctype_map = '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "../../technicalContent/dtd/map.dtd">'
    xml_lang = "en"


def test_apply_defaults_injects_corpus_schema_version():
    raw = {
        "name": "t",
        "seed": "s",
        "recipes": [{"type": "curated_realtime_corpus", "topic_count": 1000}],
    }
    out = apply_dataset_generation_defaults(raw)
    assert out["recipes"][0]["corpus_schema_version"] == CORPUS_SCHEMA_VERSION


def test_curated_corpus_skips_artifact_reuse():
    raw = {"recipes": [{"type": "curated_realtime_corpus", "topic_count": 1000}]}
    assert config_skips_artifact_reuse(raw) is True
    assert config_skips_artifact_reuse({"recipes": [{"type": "task_topics"}]}) is False


def test_generated_topic_matches_aem_dtd_order_and_rich_markup():
    files, manifest = generate_curated_realtime_corpus(
        _Cfg(),
        "content/dam/dataset-studio",
        topic_count=1,
        data_sources=["blockchain"],
        fetch_live=False,
        map_sample_size=1,
        batch_size=10,
    )
    assert manifest["corpus_schema_version"] == CORPUS_SCHEMA_VERSION
    topic_path = next(p for p in files if p.endswith("curated_00000001.dita"))
    xml = files[topic_path].decode("utf-8")

    assert xml.index("<shortdesc>") < xml.index("<prolog>")
    assert 'conref="../shared/curated_variables.dita#curated-vars/curated-disclaimer"' in xml
    assert 'keyref="product-term"' in xml
    assert 'keyref="curated-logo"' in xml
    assert 'scope="external"' in xml
    assert "<codeblock" in xml
    assert "<related-links>" in xml
    assert "curated-summary" in xml
