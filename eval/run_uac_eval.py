"""Offline UAC quality evaluation for Jira Intelligence outputs.

Usage:
    python eval/run_uac_eval.py --cases eval/uac_cases.json --json-out eval/uac_report.json

The cases file is optional. If omitted or missing, the runner executes a small
smoke suite that requires no network, Jira, Chroma, or LLM provider.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.answer_quality_service import score_answer_specificity  # noqa: E402
from services.uac_generation_service import generate_uac_recommendations  # noqa: E402


def _default_cases() -> list[dict[str, Any]]:
    return [
        {
            "id": "native_pdf_glossary_smoke",
            "enriched_jira": {
                "jira_key": "GUIDES-EVAL-1",
                "summary": "Native PDF drops glossStatus in glossary bookmap",
                "description": "Expected: glossStatus appears in PDF. Actual: glossary output drops the status.",
                "issue_type": "Bug",
                "domain": "native_pdf",
                "customer_names": ["EvalCustomer"],
                "affected_outputs": ["native_pdf"],
                "dita_entities": ["glossStatus", "bookmap"],
                "components": ["PDF Publishing"],
                "missing_info": ["Exact Native PDF preset"],
            },
            "similar_jiras": [
                {
                    "jira_key": "GUIDES-EVAL-0",
                    "title": "Glossary Native PDF regression",
                    "document": "Native PDF drops glossStatus for glossary maps.",
                    "matching_entities": ["glossStatus"],
                    "matching_outputs": ["native_pdf"],
                    "score": 0.92,
                }
            ],
            "min_quality_score": 70,
        }
    ]


def _load_cases(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return _default_cases()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("cases"), list):
        return [dict(x) for x in raw["cases"] if isinstance(x, dict)]
    if isinstance(raw, list):
        return [dict(x) for x in raw if isinstance(x, dict)]
    raise ValueError("UAC eval cases must be a list or an object with a 'cases' list.")


def _render_compact_answer(payload: dict[str, Any]) -> str:
    cls = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    scenarios = payload.get("must_test_scenarios") if isinstance(payload.get("must_test_scenarios"), list) else []
    similar = payload.get("similar_jiras") if isinstance(payload.get("similar_jiras"), list) else []
    lines = [
        "### 1. Jira Classification",
        f"Current Jira {cls.get('jira_key')} domain {cls.get('domain')} outputs {cls.get('affected_outputs')} entities {cls.get('dita_entities')}.",
        "### 3. Similar Historical Tickets",
    ]
    lines.extend([f"**{row.get('jira_key')}** {row.get('why_relevant')}" for row in similar[:5]])
    lines.append("### 4. Must-Test Scenarios")
    for sc in scenarios[:7]:
        lines.extend(
            [
                "```",
                f"Scenario: {sc.get('scenario')}",
                f"Why: {sc.get('why')}",
                f"Evidence: {sc.get('evidence')}",
                f"Test Layer: {sc.get('test_layer')}",
                "```",
            ]
        )
    return "\n".join(lines)


def run_eval(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    passed = 0
    for case in cases:
        enriched = case.get("enriched_jira") if isinstance(case.get("enriched_jira"), dict) else {}
        similar = case.get("similar_jiras") if isinstance(case.get("similar_jiras"), list) else []
        retrieval_debug = case.get("retrieval_debug") if isinstance(case.get("retrieval_debug"), dict) else {}
        payload = generate_uac_recommendations(enriched, similar, retrieval_debug)
        answer = _render_compact_answer(payload)
        quality = score_answer_specificity(answer, enriched, payload.get("similar_jiras") or [])
        min_score = int(case.get("min_quality_score") or 70)
        ok = int(quality.get("score") or 0) >= min_score
        passed += 1 if ok else 0
        rows.append(
            {
                "id": case.get("id") or f"case_{len(rows) + 1}",
                "passed": ok,
                "quality_score": quality.get("score"),
                "min_quality_score": min_score,
                "confidence": payload.get("confidence"),
                "scenario_count": len(payload.get("must_test_scenarios") or []),
                "similar_count": len(payload.get("similar_jiras") or []),
                "missing_specificity": quality.get("missing_specificity") or [],
            }
        )
    return {
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "pass_rate": round((passed / len(rows)) if rows else 0.0, 4),
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline UAC quality evals.")
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    report = run_eval(_load_cases(args.cases))
    text = json.dumps(report, indent=2, ensure_ascii=True)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
