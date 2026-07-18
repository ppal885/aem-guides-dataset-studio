"""Local DITA-OT publishing helpers for chat tools."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = PROJECT_ROOT / "output" / "dita-ot-chat"


def _safe_slug(value: str, fallback: str = "dita-ot-publish") -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip()).strip("-")
    return (slug or fallback)[:80]


def _dita_ot_cli_path() -> Path | None:
    configured = (os.getenv("DITA_OT_CLI") or "").strip()
    if configured:
        path = Path(configured)
        if path.exists():
            return path
    for candidate in (
        PROJECT_ROOT / "tools" / "dita-ot-4.4-runtime" / "dita-ot-4.4" / "bin" / "dita.bat",
        PROJECT_ROOT / "tools" / "dita-ot-4.4" / "bin" / "dita.bat",
        PROJECT_ROOT / "tools" / "dita-ot" / "bin" / "dita.bat",
        PROJECT_ROOT / "tools" / "dita-ot" / "bin" / "dita",
    ):
        if candidate.exists():
            return candidate
    return None


def _resolve_workspace_path(value: str | None) -> Path | None:
    raw = (value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("input_map must be inside the project workspace")
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(f"input_map does not exist: {resolved}")
    if resolved.suffix.lower() != ".ditamap":
        raise ValueError("input_map must point to a .ditamap file")
    return resolved


def _write_sample_dataset(work_dir: Path, title: str) -> Path:
    slug = _safe_slug(title)
    map_path = work_dir / f"{slug}.ditamap"
    topic_path = work_dir / f"{slug}-topic.dita"
    map_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map id="{slug}" xml:lang="en-US">
  <title>{title}</title>
  <topicref href="{topic_path.name}"/>
</map>
""",
        encoding="utf-8",
    )
    topic_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="{slug}-topic" xml:lang="en-US">
  <title>{title}</title>
  <shortdesc>DITA-OT publish smoke test generated from the chatbot.</shortdesc>
  <body>
    <p>This topic verifies that the local DITA-OT CLI can publish a DITA map to PDF.</p>
    <section id="oracle"><title>Expected oracle</title>
      <p>The PDF build passes when DITA-OT exits with code 0 and produces a non-empty PDF file.</p>
    </section>
  </body>
</topic>
""",
        encoding="utf-8",
    )
    return map_path


def _run_dita(input_map: Path, fmt: str, output_dir: Path, timeout_seconds: int) -> dict[str, Any]:
    cli = _dita_ot_cli_path()
    if cli is None:
        return {
            "ok": False,
            "format": fmt,
            "exit_code": None,
            "stdout": "",
            "stderr": "DITA-OT CLI not found. Set DITA_OT_CLI or install tools/dita-ot-4.4-runtime.",
            "output_dir": str(output_dir),
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(cli), "--input", str(input_map), "--format", fmt, "--output", str(output_dir)]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    return {
        "ok": proc.returncode == 0,
        "format": fmt,
        "exit_code": proc.returncode,
        "command": " ".join(cmd),
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "output_dir": str(output_dir),
    }


async def publish_with_dita_ot(
    *,
    input_map: str | None = None,
    prompt: str = "DITA-OT PDF smoke test",
    output_format: str = "pdf",
    package_name: str = "",
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Generate or publish DITA content with local DITA-OT and return artifact paths."""
    requested = (output_format or "pdf").strip().lower()
    if requested == "pdf2":
        requested = "pdf"
    if requested not in {"pdf", "html5", "both"}:
        raise ValueError("output_format must be one of: pdf, html5, both")

    run_id = str(uuid4())
    slug = _safe_slug(package_name or prompt)
    work_dir = OUTPUT_ROOT / run_id / "source"
    publish_dir = OUTPUT_ROOT / run_id / "publish"
    work_dir.mkdir(parents=True, exist_ok=True)
    publish_dir.mkdir(parents=True, exist_ok=True)

    resolved_map = _resolve_workspace_path(input_map)
    if resolved_map:
        source_map = work_dir / resolved_map.name
        if resolved_map.parent != work_dir:
            for item in resolved_map.parent.iterdir():
                target = work_dir / item.name
                if item.is_file():
                    shutil.copy2(item, target)
                elif item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
        input_for_build = source_map if source_map.exists() else resolved_map
    else:
        input_for_build = _write_sample_dataset(work_dir, prompt or slug)

    formats = ["pdf", "html5"] if requested == "both" else [requested]
    publish: dict[str, Any] = {}
    for fmt in formats:
        publish[fmt] = _run_dita(input_for_build, fmt, publish_dir / fmt, timeout_seconds)

    pdf_files = sorted((publish_dir / "pdf").glob("*.pdf")) if (publish_dir / "pdf").exists() else []
    html_files = sorted((publish_dir / "html5").glob("*.html")) if (publish_dir / "html5").exists() else []
    zip_path = OUTPUT_ROOT / run_id / f"{slug}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for base in (work_dir, publish_dir):
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(OUTPUT_ROOT / run_id).as_posix())
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "run_id": run_id,
                    "prompt": prompt,
                    "input_map": str(input_for_build),
                    "output_format": requested,
                    "created_at": datetime.now().isoformat(),
                    "pdf_files": [str(path) for path in pdf_files],
                    "html_files": [str(path) for path in html_files],
                },
                indent=2,
            ),
        )

    ok = all(bool(item.get("ok")) for item in publish.values()) if publish else False
    return {
        "status": "success" if ok else "error",
        "summary": "DITA-OT publish completed." if ok else "DITA-OT publish failed; inspect stderr.",
        "run_id": run_id,
        "input_map": str(input_for_build),
        "output_format": requested,
        "publish": publish,
        "pdf_files": [str(path) for path in pdf_files],
        "html_files": [str(path) for path in html_files],
        "artifact_zip": str(zip_path),
        "artifact_counts": {
            "pdf_files": len(pdf_files),
            "html_files": len(html_files),
        },
        "oracle": {
            "dita_ot_exit_zero": ok,
            "pdf_created": bool(pdf_files and pdf_files[0].stat().st_size > 0) if "pdf" in formats else None,
            "html_created": bool(html_files) if "html5" in formats else None,
        },
    }
