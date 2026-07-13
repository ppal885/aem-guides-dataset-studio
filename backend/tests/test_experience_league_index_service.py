"""Tests for Experience League RAG indexer."""

from app.services.experience_league_index_service import (
    filter_allowed_urls,
    is_allowed_experience_league_url,
    merge_chunk_records,
    stable_chunk_id,
)

EL_PRESETS = (
    "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
    "using/user-guide/map-management-publishing/output-gen/output-presets-aemg/"
    "generate-output-understand-presets"
)


def test_is_allowed_experience_league_url_accepts_aem_guides():
    assert is_allowed_experience_league_url(EL_PRESETS)


def test_is_allowed_experience_league_url_rejects_external():
    assert not is_allowed_experience_league_url("https://www.dita-ot.org/dev/topics/pdf-themes")
    assert not is_allowed_experience_league_url("https://evil.example.com/en/docs/experience-manager-guides/x")


def test_filter_allowed_urls_dedupes():
    urls = filter_allowed_urls([EL_PRESETS, EL_PRESETS, "https://www.dita-ot.org/"])
    assert len(urls) == 1
    assert urls[0].startswith("https://experienceleague.adobe.com/")


def test_stable_chunk_id_is_deterministic():
    assert stable_chunk_id(EL_PRESETS, 0) == stable_chunk_id(EL_PRESETS, 0)
    assert stable_chunk_id(EL_PRESETS, 0) != stable_chunk_id(EL_PRESETS, 1)


def test_merge_chunk_records_replaces_same_url_only():
    existing = [
        {"url": EL_PRESETS, "chunk_index": 0, "content": "old"},
        {"url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/overview", "chunk_index": 0, "content": "keep"},
    ]
    new_records = [{"url": EL_PRESETS, "chunk_index": 0, "content": "new"}]
    merged = merge_chunk_records(existing, new_records, crawled_urls={EL_PRESETS})
    contents = {row["url"]: row["content"] for row in merged}
    assert contents[EL_PRESETS] == "new"
    assert "keep" in contents.values()
