"""Judge the REAL evidence-grounded pipeline (not prompt-injection) vs the human gold.

This is the honest measurement of the shipped skill. For each held-out ticket it:
  1. calls the VM canonical runtime (/api/v1/mcp/guides-test-plan-generator) with the
     jira_key to get the real, evidence-grounded, gated plan_markdown, and
  2. generates a baseline description-only draft (the plain LLM),
then asks the same reference-based LLM judge to score both against the human gold on
coverage and correctness (hallucinations). Because the real pipeline's gates require
each AC to cite evidence, this should show LOWER hallucination than the prompt-
injection "skill" proxy in judge.py.

Usage:
  python scripts/uac_eval/judge_pipeline.py --n 8 --seed 5 \
      --vm http://10.42.46.78:4502 --out scripts/uac_eval/judge_pipeline_report.md
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze import _norm_component  # noqa: E402
import score as sc  # noqa: E402
from judge import _judge  # noqa: E402


def _pipeline_plan(vm: str, token: str, jira_key: str) -> tuple[str, str]:
    """Return (plan_markdown, status) from the real canonical runtime."""
    try:
        r = requests.post(
            vm.rstrip("/") + "/api/v1/mcp/guides-test-plan-generator",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"jira_key": jira_key, "skip_uac_label_gate": True, "full_rag": True},
            timeout=300, verify=False,
        )
        if r.status_code != 200:
            return "", f"http_{r.status_code}"
        d = r.json()
        plan = d.get("plan_markdown") or ""
        if not plan:
            op = d.get("output_payload") or {}
            plan = op.get("plan_markdown") or op.get("rendered_output") or ""
        return plan, d.get("status", "")
    except Exception as exc:
        sys.stderr.write(f"pipeline fail {jira_key}: {exc}\n")
        return "", "error"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(HERE / "corpus.jsonl"))
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--holdout-frac", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--vm", default="http://10.42.46.78:4502")
    ap.add_argument("--token", default="dev-bypass")
    ap.add_argument("--out", default=str(HERE / "judge_pipeline_report.md"))
    args = ap.parse_args()

    from gold_quality import is_scorable  # noqa: E402

    rows = [json.loads(l) for l in Path(args.corpus).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if len((r.get("description") or "").strip()) > 120 and len((r.get("human_ac") or "").strip()) > 60]
    _before = len(rows)
    rows = [r for r in rows if is_scorable(r)]
    _excluded = _before - len(rows)
    if _excluded:
        print(f"excluded {_excluded} rows with non-AC gold (pointer/resolution/conversational)")
    random.seed(args.seed)
    random.shuffle(rows)
    cut = int(len(rows) * (1 - args.holdout_frac))
    test = rows[cut:][: args.n]

    client, model = sc._client()
    agg = {"baseline": defaultdict(list), "pipeline": defaultdict(list)}
    per = []
    for row in test:
        key = row.get("key")
        rec = {"key": key, "component": _norm_component(row.get("component", []))}
        # real pipeline
        plan, status = _pipeline_plan(args.vm, args.token, key)
        rec["pipeline_status"] = status
        rec["pipeline_chars"] = len(plan)
        cands = {"pipeline": plan}
        # baseline
        cands["baseline"] = sc.PROMPT and _gen_baseline(client, model, row)
        for mode, cand in cands.items():
            if not cand:
                rec[mode] = {"coverage_pct": None, "note": "empty"}
                continue
            j = _judge(client, model, row, cand)
            if j:
                agg[mode]["coverage"].append(float(j.get("coverage_pct", 0)))
                agg[mode]["halluc"].append(float(j.get("hallucinations", 0)))
                agg[mode]["holistic"].append(float(j.get("holistic", 0)))
            rec[mode] = {"coverage_pct": j.get("coverage_pct"), "hallucinations": j.get("hallucinations"), "holistic": j.get("holistic")}
        per.append(rec)

    def _m(mode, k):
        v = agg[mode][k]
        return round(statistics.mean(v), 1) if v else None

    lines = ["# Real-pipeline (evidence-grounded) vs baseline, LLM-judged, held-out", "",
             f"Test tickets: {len(test)} | seed {args.seed} | judge model: {model} | pipeline: canonical runtime on {args.vm}",
             "", "| metric | baseline | real pipeline |", "|---|---|---|",
             f"| mean coverage vs gold | {_m('baseline','coverage')}% | {_m('pipeline','coverage')}% |",
             f"| mean hallucinations | {_m('baseline','halluc')} | {_m('pipeline','halluc')} |",
             f"| mean holistic (1-5) | {_m('baseline','holistic')} | {_m('pipeline','holistic')} |", "",
             "## Per ticket", ]
    for p in per:
        b, pl = p.get("baseline", {}), p.get("pipeline", {})
        lines.append(f"- {p['key']} ({p['component']}) [pipeline {p.get('pipeline_status')}, {p.get('pipeline_chars')} chars]: baseline {b.get('coverage_pct')}%/{b.get('holistic')} -> pipeline {pl.get('coverage_pct')}%/{pl.get('holistic')}")
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    Path(args.out).with_suffix(".json").write_text(json.dumps({"per": per, "agg": {m: {k: _m(m, k) for k in ("coverage", "halluc", "holistic")} for m in agg}}, indent=2), encoding="utf-8")
    print(json.dumps({"test": len(test), "baseline_cov": _m("baseline", "coverage"), "pipeline_cov": _m("pipeline", "coverage"), "pipeline_halluc": _m("pipeline", "halluc"), "out": args.out}))
    return 0


def _gen_baseline(client, model, row):
    content = sc.PROMPT.format(summary=row.get("summary", ""), component=", ".join(row.get("component", []) or []), description=(row.get("description") or "")[:6000])
    try:
        resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": content}], max_completion_tokens=1200)
        return resp.choices[0].message.content or ""
    except Exception:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
