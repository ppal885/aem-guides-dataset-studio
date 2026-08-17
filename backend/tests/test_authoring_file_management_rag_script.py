from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "upsert_authoring_file_management_vm.sh"
)
SOURCE_URL = (
    "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
    "user-guide/appendix/manage-content/authoring-file-management"
)


def test_authoring_file_management_script_targets_exact_official_page():
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'SLUG="authoring-file-management"' in script
    assert 'SOURCE_URL="$SCOPE/$SLUG"' in script
    assert SOURCE_URL == (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
        "user-guide/appendix/manage-content/authoring-file-management"
    )
    assert '--seed-url "$SOURCE_URL"' in script
    assert "--limit 1" in script


def test_authoring_file_management_script_builds_raw_and_enriched_chunks():
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "scripts/index_dita_behavior_corpus.py" in script
    assert "scripts/enrich_experienceleague_behavior_chunks.py" in script
    assert script.count("scripts/upsert_vm_rag_backend.sh") == 2
    assert '--input "$RAW_OUTPUT"' in script
    assert '--input "$ENRICHED_OUTPUT"' in script
    assert "--no-restart" in script
