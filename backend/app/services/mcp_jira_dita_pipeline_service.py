"""Post-generation helpers for MCP Jira → DITA → output/dita workflows."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DITA_DIR = PROJECT_ROOT / "output" / "dita"
GENERATION_LOG = PROJECT_ROOT / "output" / "generation_log.json"
DITA_ARTIFACT_EXTENSIONS = {".dita", ".ditamap", ".xml", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf"}


def build_jira_generation_request(issue_key: str, *, dita_type: str = "auto") -> str:
    type_hint = dita_type if dita_type != "auto" else "auto-detected topic/map bundle"
    return (
        f"Generate a DITA QA dataset for Jira {issue_key}. "
        f"Use dita_type={type_hint}. "
        "When the issue involves maps, dependents, reprocessing, Editor workflows, or reports, "
        "include a ditamap plus supporting topics that reproduce the scenario structure."
    )


def sync_bundle_to_output_dita(jira_id: str, *, output_dir: Path | None = None) -> list[str]:
    """Copy generated bundle artifacts into output/dita/ for MCP upload tools."""
    from app.services.bundle_builder_service import get_bundle_path_for_jira

    bundle_path = get_bundle_path_for_jira(jira_id)
    target_dir = output_dir or OUTPUT_DITA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    if not bundle_path.exists():
        return []

    saved: list[str] = []
    for path in bundle_path.rglob("*"):
        if not path.is_file():
            continue
        if path.name in {"manifest.json", "metadata.json"}:
            continue
        if "logs" in path.parts:
            continue
        suffix = path.suffix.lower()
        if suffix not in DITA_ARTIFACT_EXTENSIONS and not path.name.startswith("README"):
            continue
        dest = target_dir / path.name
        shutil.copy2(path, dest)
        saved.append(dest.name)
    return sorted(set(saved))


def finalize_mcp_dita_output(saved_files: list[str], *, output_dir: Path | None = None) -> dict[str, Any]:
    """Enrich and lightly validate files already written to output/dita/."""
    from app.services.dita_enrichment_service import enrich_dita_folder

    target_dir = output_dir or OUTPUT_DITA_DIR
    enrich_stats = enrich_dita_folder(target_dir) if target_dir.exists() else {
        "topics_processed": 0,
        "shortdesc_added": 0,
        "prolog_added": 0,
        "errors": ["output/dita missing"],
    }

    validation: dict[str, str] = {}
    for name in saved_files:
        if not name.lower().endswith((".dita", ".ditamap", ".xml")):
            continue
        path = target_dir / name
        if not path.is_file():
            validation[name] = "missing after sync"
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "<?xml" not in text:
            validation[name] = "missing XML declaration"
        elif "<title" not in text:
            validation[name] = "missing title"
        else:
            validation[name] = "ok"

    return {"enrich": enrich_stats, "validation": validation}


def mark_issue_generated_local(issue_key: str, dita_files: list[str], notes: str = "") -> None:
    log: dict[str, Any] = {}
    if GENERATION_LOG.exists():
        log = json.loads(GENERATION_LOG.read_text(encoding="utf-8"))
    log[issue_key] = {
        "generated_at": datetime.utcnow().isoformat(),
        "dita_files": dita_files,
        "notes": notes,
    }
    GENERATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    GENERATION_LOG.write_text(json.dumps(log, indent=2), encoding="utf-8")
