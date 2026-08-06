from pathlib import Path

from app.services.dita_ot_negative_fixture_service import (
    wants_negative_fixtures,
    write_negative_fixtures,
)


def test_negative_fixture_request_writes_every_requested_behavior(tmp_path: Path):
    prompt = (
        'Generate HTML5 evidence for copy-to with chunk="to-content" and chunk="by-topic". '
        "Include nested maps, duplicate references, conflicting copy-to values, keyrefs, conrefs, "
        "relative links, images, and invalid combinations."
    )

    fixtures = write_negative_fixtures(tmp_path, prompt)
    fixture_ids = {fixture.fixture_id for fixture in fixtures}

    assert fixture_ids == {
        "duplicate-reference",
        "conflicting-copy-to",
        "unresolved-keyref",
        "dangling-conref",
        "broken-relative-xref",
        "missing-image",
        "invalid-chunk-token",
        "nested-map-image-control",
    }
    assert all(fixture.map_path.exists() for fixture in fixtures)
    assert (tmp_path / "negative-cases" / "nested-map-image-control" / "images" / "pixel.png").exists()
    assert 'chunk="split to-navigation"' in (
        tmp_path / "negative-cases" / "invalid-chunk-token" / "root.ditamap"
    ).read_text(encoding="utf-8")
    assert 'copy-to="collision.dita"' in (
        tmp_path / "negative-cases" / "conflicting-copy-to" / "root.ditamap"
    ).read_text(encoding="utf-8")


def test_positive_prompt_does_not_create_negative_fixtures(tmp_path: Path):
    assert wants_negative_fixtures("Generate a valid HTML5 smoke corpus") is False
    assert write_negative_fixtures(tmp_path, "Generate a valid HTML5 smoke corpus") == []
