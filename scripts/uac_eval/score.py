"""Blind-draft-vs-gold scoring.

For a sample of corpus tickets: generate a BLIND baseline UAC from the description
only (a plain LLM, no skill), detect coverage dimensions in the draft and in the
human gold, and score dimension recall + the per-dimension miss histogram. This is
the baseline the skill must improve on: it shows which dimensions a description-only
draft systematically drops versus the human QA.

Uses Azure OpenAI from backend/.env. Sampling is stratified across components.

Usage:
  python scripts/uac_eval/score.py --n 12 --out scripts/uac_eval/score_report.md
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from analyze import DIMENSIONS, _norm_component  # noqa: E402


def _dims(text: str) -> set[str]:
    low = (text or "").lower()
    return {k for k, rx in DIMENSIONS.items() if rx.search(low)}


def _client():
    from dotenv import load_dotenv

    load_dotenv(str(REPO / "backend" / ".env"))
    from openai import AzureOpenAI

    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    )
    return client, os.getenv("AZURE_OPENAI_MODEL")


PROMPT = (
    "You are a QA engineer for Adobe Experience Manager Guides. Write acceptance "
    "criteria (a UAC) for this Jira ticket, using only the description below. "
    "Output short one-line acceptance criteria bullets. Do not ask questions.\n\n"
    "Summary: {summary}\nComponent: {component}\n\nDescription:\n{description}\n"
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(HERE / "corpus.jsonl"))
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--out", default=str(HERE / "score_report.md"))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.corpus).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if len((r.get("description") or "").strip()) > 120 and len((r.get("human_ac") or "").strip()) > 60]
    # stratify by component
    by_comp = defaultdict(list)
    for r in rows:
        by_comp[_norm_component(r.get("component", []))].append(r)
    random.seed(args.seed)
    sample: list[dict] = []
    comps = sorted(by_comp, key=lambda c: -len(by_comp[c]))
    while len(sample) < args.n and any(by_comp.values()):
        for c in comps:
            if by_comp[c] and len(sample) < args.n:
                sample.append(by_comp[c].pop(random.randrange(len(by_comp[c]))))

    client, model = _client()
    per = []
    miss_hist = Counter()
    gold_hist = Counter()
    recalls = []
    for r in sample:
        draft = ""
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": PROMPT.format(
                    summary=r.get("summary", ""), component=", ".join(r.get("component", []) or []),
                    description=(r.get("description") or "")[:6000])}],
                max_completion_tokens=1200,
            )
            draft = resp.choices[0].message.content or ""
        except Exception as exc:
            sys.stderr.write(f"LLM fail {r.get('key')}: {exc}\n")
            continue
        gold_d = _dims(r.get("human_ac", ""))
        draft_d = _dims(draft)
        missed = gold_d - draft_d
        for d in gold_d:
            gold_hist[d] += 1
        for d in missed:
            miss_hist[d] += 1
        recall = round(100 * len(gold_d & draft_d) / len(gold_d), 0) if gold_d else 100.0
        recalls.append(recall)
        per.append({"key": r.get("key"), "component": _norm_component(r.get("component", [])),
                    "gold_dims": sorted(gold_d), "draft_dims": sorted(draft_d),
                    "missed": sorted(missed), "recall_pct": recall})

    lines = ["# Blind-draft-vs-gold scoring (baseline LLM, no skill)", ""]
    lines.append(f"Sample: {len(per)} tickets | model: {model}")
    if recalls:
        lines.append(f"Mean dimension recall (draft vs human gold): **{round(sum(recalls)/len(recalls),1)}%**")
    lines.append("")
    lines.append("## Most-missed dimensions (gold had it, blind draft dropped it)")
    for d, c in miss_hist.most_common():
        g = gold_hist[d]
        lines.append(f"- {d}: missed {c}/{g} times ({round(100*c/g)}% of the tickets where the human included it)")
    lines.append("")
    lines.append("## Per ticket")
    for p in per:
        lines.append(f"### {p['key']} ({p['component']}) - recall {p['recall_pct']}%")
        lines.append(f"- missed: {', '.join(p['missed']) or 'none'}")
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    Path(args.out).with_suffix(".json").write_text(json.dumps({"per": per, "miss_hist": dict(miss_hist), "gold_hist": dict(gold_hist)}, indent=2), encoding="utf-8")
    print(json.dumps({"scored": len(per), "mean_recall": round(sum(recalls)/len(recalls),1) if recalls else None, "out": args.out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
