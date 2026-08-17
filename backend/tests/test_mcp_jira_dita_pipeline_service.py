from pathlib import Path

from app.services import mcp_jira_dita_pipeline_service as pipeline


def test_sync_bundle_to_output_dita_flattens_artifacts(tmp_path: Path, monkeypatch):
    bundle_dir = tmp_path / "GUIDES-99999_bundle" / "S1_MIN_REPRO"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "GUIDES-99999-root.ditamap").write_text("<map/>", encoding="utf-8")
    (bundle_dir / "GUIDES-99999-topic.dita").write_text("<topic/>", encoding="utf-8")
    (bundle_dir / "manifest.json").write_text("{}", encoding="utf-8")

    from app.services import bundle_builder_service

    monkeypatch.setattr(
        bundle_builder_service,
        "get_bundle_path_for_jira",
        lambda jira_id: tmp_path / f"{jira_id}_bundle",
    )

    output_dir = tmp_path / "output" / "dita"
    saved = pipeline.sync_bundle_to_output_dita("GUIDES-99999", output_dir=output_dir)

    assert saved == ["GUIDES-99999-root.ditamap", "GUIDES-99999-topic.dita"]
    assert (output_dir / "GUIDES-99999-root.ditamap").exists()


def test_finalize_mcp_dita_output_enriches_and_validates(tmp_path: Path, monkeypatch):
    output_dir = tmp_path / "dita"
    output_dir.mkdir(parents=True)
    (output_dir / "sample.dita").write_text(
        '<?xml version="1.0"?><topic id="x"><title>Title</title><body><p>ok</p></body></topic>',
        encoding="utf-8",
    )

    from app.services import dita_enrichment_service

    monkeypatch.setattr(dita_enrichment_service, "enrich_dita_folder", lambda folder: {
        "topics_processed": 1,
        "shortdesc_added": 0,
        "prolog_added": 0,
        "errors": [],
    })

    result = pipeline.finalize_mcp_dita_output(["sample.dita"], output_dir=output_dir)

    assert result["validation"]["sample.dita"] == "ok"
    assert result["enrich"]["topics_processed"] == 1
