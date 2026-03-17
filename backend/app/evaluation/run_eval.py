"""Evaluation script - run eval cases and compute metrics."""
import asyncio
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure app is importable when run as script
if __name__ == "__main__" and str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.services.ai_planner_service import classify_domain, expand_scenarios, plan_for_scenario
from app.services.recipe_retriever import retrieve_recipes
from app.services.feedback_analysis_service import analyze_eval_report
from app.services.ai_executor_service import execute_plan
from app.utils.dita_validator import validate_dita_folder
from app.core.agentic_config import agentic_config


def _extract_failed_recipe_ids(warnings: list[str], recipes_executed: list[str]) -> list[str]:
    """From warnings like 'Unknown recipe_id: X' or 'Recipe Y failed: ...', return [X, Y]."""
    ids = []
    for w in warnings:
        m = re.search(r"Unknown recipe_id:\s*(\S+)", w, re.IGNORECASE)
        if m:
            ids.append(m.group(1).strip())
            continue
        m = re.search(r"Recipe\s+(\S+)\s+failed", w, re.IGNORECASE)
        if m:
            ids.append(m.group(1).strip())
    return list(dict.fromkeys(ids))


def _load_eval_cases() -> list[dict]:
    """Load eval cases from eval_cases.json."""
    path = Path(__file__).resolve().parent / "eval_cases.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _build_evidence_pack(jira_text: str, case_id: str = "EVAL") -> dict:
    """Build synthetic evidence pack from jira_text."""
    return {
        "primary": {
            "issue_key": f"{case_id}-1",
            "summary": jira_text,
            "description": jira_text,
            "description_excerpt": jira_text[:1000],
            "issue_type": "Bug",
            "status": "Open",
            "attachments": [],
        },
        "similar": [],
        "stats": {},
    }


async def _run_case(case: dict, index: int, run_execution: bool = True, trace_id: str | None = None) -> dict:
    """Run a single eval case and return results. Uses same agentic config as API."""
    jira_text = case.get("jira_text", "")
    expected_domain = (case.get("expected_domain") or "").lower().strip()
    expected_recipe = (case.get("expected_recipe") or "").strip()
    expected_scenarios = [str(s).upper().strip() for s in case.get("expected_scenarios", [])]

    case_id = f"EVAL-{index}"
    evidence_pack = _build_evidence_pack(jira_text, case_id)
    trace_id = trace_id or f"eval-{case_id}"

    domain_result = await classify_domain(evidence_pack, trace_id=trace_id, jira_id=case_id)
    predicted_domain = (domain_result.get("domain") or "").lower().strip()
    domain_match = expected_domain in predicted_domain or predicted_domain in expected_domain

    scenario_set = await expand_scenarios(evidence_pack, trace_id=trace_id, jira_id=case_id)
    actual_scenario_types = [s.type.value for s in scenario_set.scenarios]
    expected_set = set(expected_scenarios)
    actual_set = set(actual_scenario_types)
    scenario_overlap = len(expected_set & actual_set) / max(1, len(expected_set))

    recipe_match = False
    validation_passed = False
    plans_used = []

    if scenario_set.scenarios:
        scenario = scenario_set.scenarios[0]
        excluded_recipe_ids = []
        last_validation_errors = None
        last_exec_warnings = None
        plan = None
        exec_result = None
        val_result = None

        if run_execution:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                validation_retries = 0
                execution_retries = 0

                while True:
                    k = agentic_config.recipe_k_for_validation_retry(validation_retries)
                    candidates = await retrieve_recipes(
                        f"{scenario.title} {scenario.description}",
                        k=k,
                        scenario_hint=scenario.type.value,
                        exclude_ids=excluded_recipe_ids,
                        trace_id=trace_id,
                        jira_id=case_id,
                    )
                    if not candidates:
                        break

                    plan = await plan_for_scenario(
                        evidence_pack,
                        scenario,
                        candidates,
                        trace_id=trace_id,
                        jira_id=case_id,
                        validation_errors=last_validation_errors,
                        execution_warnings=last_exec_warnings,
                        excluded_recipe_ids=excluded_recipe_ids,
                    )
                    if not plan.recipes:
                        break

                    if validation_retries > 0 or execution_retries > 0:
                        for p in tmpdir_path.iterdir():
                            if p.is_file():
                                p.unlink()
                            else:
                                shutil.rmtree(p, ignore_errors=True)

                    exec_result = execute_plan(plan, str(tmpdir_path), seed="eval")

                    failed_ids = _extract_failed_recipe_ids(
                        exec_result["warnings"], exec_result.get("recipes_executed", [])
                    )
                    if not failed_ids and exec_result["warnings"]:
                        failed_ids = exec_result.get("recipes_executed", [])
                    excluded_recipe_ids = list(dict.fromkeys(excluded_recipe_ids + failed_ids))

                    if exec_result["warnings"] and execution_retries < agentic_config.max_execution_retries:
                        execution_retries += 1
                        last_exec_warnings = exec_result["warnings"]
                        continue

                    val_result = validate_dita_folder(tmpdir_path)

                    if val_result.get("errors") and validation_retries < agentic_config.max_validation_retries:
                        excluded_recipe_ids = list(
                            dict.fromkeys(excluded_recipe_ids + exec_result.get("recipes_executed", []))
                        )
                        last_validation_errors = val_result["errors"]
                        last_exec_warnings = exec_result["warnings"]
                        validation_retries += 1
                        continue

                    break

                validation_passed = bool(val_result and len(val_result.get("errors", [])) == 0)
        else:
            candidates = await retrieve_recipes(
                f"{scenario.title} {scenario.description}",
                k=agentic_config.recipe_candidates_k,
                scenario_hint=scenario.type.value,
                trace_id=trace_id,
                jira_id=case_id,
            )
            plan = await plan_for_scenario(evidence_pack, scenario, candidates, trace_id=trace_id, jira_id=case_id)

        plans_used = [r.recipe_id for r in plan.recipes] if plan else []
        recipe_match = expected_recipe in plans_used if expected_recipe else True

    return {
        "domain_match": domain_match,
        "recipe_match": recipe_match,
        "scenario_overlap": scenario_overlap,
        "validation_passed": validation_passed,
        "predicted_domain": predicted_domain,
        "actual_scenarios": actual_scenario_types,
        "plans_used": plans_used,
    }


async def run_evaluation(run_execution: bool = True) -> dict:
    """Run all eval cases and compute metrics."""
    cases = _load_eval_cases()
    results = []
    total_scenarios = 0
    validated_scenarios = 0

    for i, case in enumerate(cases):
        try:
            r = await _run_case(case, i, run_execution=run_execution)
            results.append({"case_index": i, "case": case, "result": r})
            total_scenarios += 1
            if r.get("validation_passed"):
                validated_scenarios += 1
        except Exception as e:
            results.append({
                "case_index": i,
                "case": case,
                "result": {"error": str(e)},
            })

    n = len(cases)
    domain_correct = sum(1 for r in results if r.get("result", {}).get("domain_match"))
    recipe_correct = sum(1 for r in results if r.get("result", {}).get("recipe_match"))
    scenario_diversity = (
        sum(r.get("result", {}).get("scenario_overlap", 0) for r in results if "error" not in r.get("result", {}))
        / max(1, n)
    )

    report = {
        "metrics": {
            "domain_accuracy": domain_correct / n if n else 0,
            "recipe_selection_accuracy": recipe_correct / n if n else 0,
            "scenario_diversity": scenario_diversity,
            "dataset_validation_rate": validated_scenarios / total_scenarios if total_scenarios else 0,
        },
        "summary": {
            "total_cases": n,
            "domain_correct": domain_correct,
            "recipe_correct": recipe_correct,
            "validated_scenarios": validated_scenarios,
            "total_scenarios": total_scenarios,
        },
        "case_results": [
            {
                "index": r["case_index"],
                "jira_text_preview": (r["case"].get("jira_text", ""))[:80] + "...",
                "result": r["result"],
            }
            for r in results
        ],
    }
    return report


def main():
    """Entry point for evaluation script."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-execution", action="store_true", help="Skip dataset execution and validation")
    parser.add_argument("--output", "-o", help="Write report to JSON file")
    parser.add_argument("--feedback", "-f", help="Write suggested prompt/recipe updates to file")
    args = parser.parse_args()

    report = asyncio.run(run_evaluation(run_execution=not args.no_execution))

    print(json.dumps(report, indent=2))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport written to {args.output}")

    if args.feedback:
        analysis = analyze_eval_report(report)
        feedback_content = {
            "summary": analysis.get("summary"),
            "weak_areas": analysis.get("weak_areas"),
            "recommendations": analysis.get("recommendations"),
        }
        with open(args.feedback, "w", encoding="utf-8") as f:
            json.dump(feedback_content, f, indent=2)
        print(f"\nFeedback written to {args.feedback}")


if __name__ == "__main__":
    main()
