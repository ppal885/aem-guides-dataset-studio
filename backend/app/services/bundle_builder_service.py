"""Bundle builder - assemble scenario outputs into single bundle."""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.storage import get_storage
from app.services.llm_service import _get_prompt_versions
from app.core.schemas_bundle import BundleManifest, BundleScenarioResult
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def build_bundle(
    jira_id: str,
    run_id: str,
    scenario_outputs: dict[str, Path],
    evidence_pack: dict,
    plans: dict[str, dict],
    validation_results: Optional[dict[str, dict]] = None,
) -> Path:
    """
    Build bundle: create {jira_id}_bundle/ with scenario subdirs, manifest, logs.
    scenario_outputs: {scenario_id: path_to_scenario_dir}
    """
    storage = get_storage()
    bundle_name = f"{jira_id}_bundle"
    bundle_path = storage.base_path / bundle_name
    if bundle_path.exists():
        shutil.rmtree(bundle_path)
    bundle_path.mkdir(parents=True)

    logs_path = bundle_path / "logs"
    logs_path.mkdir()

    scenario_results = []
    for scenario_id, scenario_dir in scenario_outputs.items():
        if not scenario_dir or not Path(scenario_dir).exists():
            continue
        dest = bundle_path / scenario_id
        shutil.copytree(scenario_dir, dest)
        val = (validation_results or {}).get(scenario_id, {})
        scenario_results.append(BundleScenarioResult(
            scenario_id=scenario_id,
            scenario_dir=scenario_id,
            metadata_path=f"{scenario_id}/metadata.json",
            recipes_executed=plans.get(scenario_id, {}).get("recipes_executed", []),
            validation_passed=len(val.get("errors", [])) == 0,
            warnings=val.get("warnings", []),
        ))

    manifest = BundleManifest(
        jira_id=jira_id,
        run_id=run_id,
        scenarios=scenario_results,
        created_at=datetime.utcnow(),
        stats={"evidence_primary": evidence_pack.get("primary", {}).get("issue_key")},
        prompt_versions=_get_prompt_versions(),
    )
    (bundle_path / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    planning_log = {"plans": plans, "evidence_summary": {"primary_key": evidence_pack.get("primary", {}).get("issue_key")}}
    (logs_path / "planning.json").write_text(json.dumps(planning_log, indent=2), encoding="utf-8")

    validation_log = validation_results or {}
    (logs_path / "validation.json").write_text(json.dumps(validation_log, indent=2), encoding="utf-8")

    return bundle_path


def get_bundle_path_for_jira(jira_id: str) -> Path:
    """Get the bundle directory path for a jira id."""
    storage = get_storage()
    return storage.base_path / f"{jira_id}_bundle"
