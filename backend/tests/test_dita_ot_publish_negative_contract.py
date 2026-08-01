import asyncio
import zipfile
from pathlib import Path

from app.services import dita_ot_publish_service


def test_publish_packages_executed_negative_fixtures_and_logs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(dita_ot_publish_service, "OUTPUT_ROOT", tmp_path / "runs")

    def fake_run(input_map: Path, fmt: str, output_dir: Path, timeout_seconds: int):
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "index.html").write_text("<html>fixture output</html>", encoding="utf-8")
        is_positive = "negative-cases" not in input_map.parts
        return {
            "ok": is_positive,
            "format": fmt,
            "exit_code": 0 if is_positive else 1,
            "command": f"dita -i {input_map} -f {fmt}",
            "stdout": "positive" if is_positive else "fixture stdout",
            "stderr": "" if is_positive else "fixture diagnostic",
            "output_dir": str(output_dir),
        }

    monkeypatch.setattr(dita_ot_publish_service, "_run_dita", fake_run)
    result = asyncio.run(
        dita_ot_publish_service.publish_with_dita_ot(
            prompt=(
                'Generate HTML5 evidence for copy-to and chunk="to-content". Include nested maps, '
                "duplicate references, conflicting copy-to, broken keyrefs, conrefs, relative links, "
                "images, and invalid combinations."
            ),
            output_format="html5",
            package_name="negative-contract",
        )
    )

    assert result["status"] == "success"
    assert result["negative_fixture_count"] == 8
    assert len(result["negative_fixture_results"]) == 8
    assert Path(result["observation_summary"]).exists()
    assert any("isolated negative/control fixtures" in item for item in result["what_was_generated"])

    with zipfile.ZipFile(result["artifact_zip"]) as archive:
        names = set(archive.namelist())
    assert "observation-summary.json" in names
    assert "logs/positive-control.html5.stdout.log" in names
    assert "logs/negative-cases/invalid-chunk-token.html5.stderr.log" in names
    assert "source/negative-cases/conflicting-copy-to/root.ditamap" in names
