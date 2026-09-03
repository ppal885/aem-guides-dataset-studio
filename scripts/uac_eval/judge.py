"""Held-out, LLM-judged baseline-vs-skill scoring (removes both circularities).

Fixes the two weaknesses of the keyword scorer:
  1. Train/test split - the component dimension priors are rebuilt from the TRAIN
     split only, so the priors never saw the evaluated ticket.
  2. LLM judge - a reference-based judge scores each candidate UAC against the
     human gold on coverage and correctness (hallucination), not keyword presence.

For each held-out ticket it generates a baseline draft (description only) and a
skill draft (description + train-only priors + forcing rules), then asks the judge
to score both against the human gold. Reports mean coverage, hallucinations, and a
holistic 1-5, baseline vs skill.

Usage:
  python scripts/uac_eval/judge.py --n 12 --holdout-frac 0.3 --seed 5
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze import DIMENSIONS, _norm_component, analyze_row  # noqa: E402
import score as sc  # noqa: E402


def _build_train_priors(train_rows: list[dict], out_path: Path, thresh: float = 30.0) -> None:
    feats = [analyze_row(r) for r in train_rows]
    by_comp = defaultdict(list)
    for f in feats:
        by_comp[f["component"]].append(f)
    NAME = {f"dim_{k}": k for k in DIMENSIONS}
    friendly = {
        "state_partition": "state partitions (both/with-and-without, profile, baseline, enumdef bound vs unbound)",
        "multi_surface": "all consumer UI surfaces (every panel/view/dropdown that shows this)",
        "regression_parity": "regression / existing behaviour unchanged",
        "negative_error": "negative / error / missing / fallback paths",
        "output_preset": "output preset matrix",
        "provenance_channels": "value provenance / source channels",
        "performance": "performance with large content",
        "localization": "localization / translation impact",
        "css_styles": "CSS / styling / rendition",
        "permissions_role": "permissions / role",
        "cross_tool_oracle": "cross-tool oracle (compare to Oxygen etc.)",
        "attachment_or_bigcontent": "use the attached / big-content sample",
    }
    out = {"schema_version": "aem-guides-component-dimension-priors-v1", "threshold_pct": thresh,
           "source": "train split only (held-out eval)", "components": {}}
    for comp, fs in by_comp.items():
        if len(fs) < 4:
            continue
        dims = []
        for dk in NAME:
            pct = round(100 * sum(f[dk] for f in fs) / len(fs), 1)
            if pct >= thresh:
                dims.append({"dimension": friendly.get(NAME[dk], NAME[dk]), "pct": pct})
        dims.sort(key=lambda x: -x["pct"])
        if dims:
            out["components"][comp] = {"tickets": len(fs), "usually_expected": dims}
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")


JUDGE = (
    "You are an impartial QA reviewer. Both texts below are ACCEPTANCE CRITERIA for "
    "the same Jira ticket: a human REFERENCE and a CANDIDATE. Compare only the "
    "acceptance criteria. Return ONLY JSON:\n"
    '{{"coverage_pct": <0-100, fraction of the reference''s acceptance points the '
    'candidate addresses>, "hallucinations": <int, candidate acceptance criteria '
    'that CONTRADICT the ticket or assert behaviour the ticket does not support; do '
    'NOT count a criterion merely for being additional reasonable coverage the human '
    'omitted, and do NOT count test scenarios, regression notes, or open questions>, '
    '"missing_key_points": [<short strings of important reference points the '
    'candidate omits>], "holistic": <1-5 overall usefulness of the candidate''s '
    'acceptance criteria vs the reference>}}\n\n'
    "TICKET: {summary}\n\nREFERENCE ACCEPTANCE CRITERIA:\n{gold}\n\n"
    "CANDIDATE ACCEPTANCE CRITERIA:\n{cand}\n"
)


def _extract_ac(text: str) -> str:
    """Return just the Acceptance Criteria section of a plan so the judge compares
    AC-to-AC. Falls back to the whole text when no AC heading is present (e.g. a
    baseline draft that is already only acceptance criteria)."""
    if not text:
        return ""
    m = re.search(
        r"(?:^|\n)\s*(?:#{1,4}\s*|\*\*)\s*"
        r"(?:Proposed acceptance contract|Acceptance contract|Acceptance criteria)\b.*?"
        r"(?=\n\s*(?:#{1,4}\s*|\*\*)\s*[A-Z][A-Za-z /]{2,40}\b|\Z)",
        text, re.S | re.I,
    )
    return (m.group(0).strip() if m else text.strip())


def _judge(client, model, row, cand) -> dict:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": JUDGE.format(
                summary=row.get("summary", ""), gold=_extract_ac(row.get("human_ac") or "")[:5000],
                cand=_extract_ac(cand or "")[:5000])}],
            max_completion_tokens=800,
        )
        txt = resp.choices[0].message.content or "{}"
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception as exc:
        sys.stderr.write(f"judge fail {row.get('key')}: {exc}\n")
        return {}


def _generate(client, model, row, mode, priors_path):
    comp = _norm_component(row.get("component", []))
    if mode == "skill":
        content = sc.SKILL_PROMPT.format(
            guidance=sc._skill_guidance(comp, priors_path=priors_path),
            summary=row.get("summary", ""), component=", ".join(row.get("component", []) or []),
            description=(row.get("description") or "")[:6000])
    else:
        content = sc.PROMPT.format(
            summary=row.get("summary", ""), component=", ".join(row.get("component", []) or []),
            description=(row.get("description") or "")[:6000])
    try:
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": content}], max_completion_tokens=1200)
        return resp.choices[0].message.content or ""
    except Exception as exc:
        sys.stderr.write(f"gen fail {row.get('key')} {mode}: {exc}\n")
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(HERE / "corpus.jsonl"))
    ap.add_argument("--n", type=int, default=12, help="held-out test tickets to judge")
    ap.add_argument("--holdout-frac", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--out", default=str(HERE / "judge_report.md"))
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.corpus).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if len((r.get("description") or "").strip()) > 120 and len((r.get("human_ac") or "").strip()) > 60]
    random.seed(args.seed)
    random.shuffle(rows)
    cut = int(len(rows) * (1 - args.holdout_frac))
    train, test = rows[:cut], rows[cut:]
    test = test[: args.n]
    priors_path = HERE / "train_priors.json"
    _build_train_priors(train, priors_path)
    sys.stderr.write(f"train {len(train)} / test {len(test)}; train priors -> {priors_path}\n")

    client, model = sc._client()
    agg = {"baseline": defaultdict(list), "skill": defaultdict(list)}
    per = []
    for row in test:
        rec = {"key": row.get("key"), "component": _norm_component(row.get("component", []))}
        for mode in ("baseline", "skill"):
            cand = _generate(client, model, row, mode, priors_path)
            j = _judge(client, model, row, cand)
            if j:
                agg[mode]["coverage"].append(float(j.get("coverage_pct", 0)))
                agg[mode]["halluc"].append(float(j.get("hallucinations", 0)))
                agg[mode]["holistic"].append(float(j.get("holistic", 0)))
            rec[mode] = {"coverage_pct": j.get("coverage_pct"), "hallucinations": j.get("hallucinations"),
                         "holistic": j.get("holistic"), "missing": j.get("missing_key_points", [])[:4]}
        per.append(rec)

    def _m(mode, k):
        v = agg[mode][k]
        return round(statistics.mean(v), 1) if v else None

    lines = ["# Held-out, LLM-judged baseline vs skill", "",
             f"Test tickets (held out): {len(test)} | train: {len(train)} | model/judge: {model} | seed {args.seed}",
             "Priors rebuilt from TRAIN only; judge scores coverage & correctness vs human gold.", "",
             "| metric | baseline | skill |", "|---|---|---|",
             f"| mean coverage vs gold | {_m('baseline','coverage')}% | {_m('skill','coverage')}% |",
             f"| mean hallucinations | {_m('baseline','halluc')} | {_m('skill','halluc')} |",
             f"| mean holistic (1-5) | {_m('baseline','holistic')} | {_m('skill','holistic')} |", "",
             "## Per ticket (coverage% / holistic)"]
    for p in per:
        b, s = p["baseline"], p["skill"]
        lines.append(f"- {p['key']} ({p['component']}): baseline {b.get('coverage_pct')}%/{b.get('holistic')} -> skill {s.get('coverage_pct')}%/{s.get('holistic')}")
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    Path(args.out).with_suffix(".json").write_text(json.dumps({"per": per, "agg": {m: {k: _m(m, k) for k in ("coverage", "halluc", "holistic")} for m in agg}}, indent=2), encoding="utf-8")
    print(json.dumps({"test": len(test), "baseline_cov": _m("baseline", "coverage"), "skill_cov": _m("skill", "coverage"), "out": args.out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
