"""Measure the miss-rate reduction from running the gates INSIDE UAC generation.

This is the "gates in one go" flow the skill should use, and the before/after proof:

  GATES OFF: generate a blind draft from the ticket description only. Score which of the
             human UAC's dimension axes it misses.
  GATES ON:  generate the same blind draft, then run coverage_forcing.validate on it; feed
             the gate failures back to the model to produce a corrected draft; re-gate;
             loop until the gates pass or a round cap is hit. Score its missed axes.

Dimension oracle = mine_uac_dimensions.AXES applied to the human UAC (the axes a human
actually covered) vs the draft. Miss-rate = human axes the draft does not cover / human
axes. Reports the mean miss-rate OFF vs ON and the mean gate-failures fixed per ticket.

Usage:
  python scripts/uac_eval/measure_gate_effect.py --n 15 --seed 5
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / ".codex" / "skills" / "test-plan-generation" / "scripts"))

import score as sc  # noqa: E402
import mine_uac_dimensions as mud  # noqa: E402
import coverage_forcing as cf  # noqa: E402

MAX_CORRECTION_ROUNDS = 2


def _axes(text: str) -> set[str]:
    return {name for name, rx in mud.AXES.items() if rx.search(text or "")}


def _gen(client, model, content: str, max_tokens: int = 1300) -> str:
    try:
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": content}],
            max_completion_tokens=max_tokens)
        return resp.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"gen fail: {exc}\n")
        return ""


def _draft(client, model, row) -> str:
    return _gen(client, model, sc.PROMPT.format(
        summary=row.get("summary", ""), component=", ".join(row.get("component", []) or []),
        description=(row.get("description") or "")[:6000]))


def _manifest(row) -> dict:
    return {"issue": {"summary": row.get("summary", ""), "description": row.get("description", "")}}


def _gate_correct(client, model, row, draft: str) -> tuple[str, int, int]:
    """Run gates; while they fail, re-prompt with the failures. Return (final_draft,
    initial_failures, rounds_used)."""
    manifest = _manifest(row)
    initial = cf.validate(manifest, draft)
    current = draft
    rounds = 0
    failures = initial
    while failures and rounds < MAX_CORRECTION_ROUNDS:
        rounds += 1
        fix_prompt = (
            "Here is a draft UAC:\n\n" + current + "\n\n"
            "A QA coverage gate found these missing dimensions. Revise the UAC to address "
            "EACH one - add the missing dimension as a concise acceptance criterion or an "
            "Open Question. Keep the existing criteria. Return the full revised UAC only.\n\n"
            + "\n".join(f"- {f}" for f in failures)
        )
        revised = _gen(client, model, fix_prompt, max_tokens=1600)
        if not revised:
            break
        current = revised
        failures = cf.validate(manifest, current)
    return current, len(initial), rounds


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(HERE / "corpus.jsonl"))
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--out", default=str(HERE / "gate_effect_report.md"))
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.corpus).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows
            if len((r.get("description") or "").strip()) > 120
            and len((r.get("human_ac") or "").strip()) > 40]
    random.seed(args.seed)
    random.shuffle(rows)
    rows = rows[: args.n]

    client, model = sc._client()
    off_miss, on_miss, fixed, rounds_used, per = [], [], [], [], []
    for row in rows:
        human = _axes(row.get("human_ac", ""))
        if not human:
            continue
        d_off = _draft(client, model, row)
        if not d_off:
            continue
        off_axes = _axes(d_off)
        off_m = len(human - off_axes) / len(human)
        d_on, init_fail, rnd = _gate_correct(client, model, row, d_off)
        on_axes = _axes(d_on)
        on_m = len(human - on_axes) / len(human)
        off_miss.append(off_m)
        on_miss.append(on_m)
        fixed.append(init_fail)
        rounds_used.append(rnd)
        per.append({"key": row.get("key"), "human_axes": len(human),
                    "off_miss": round(off_m, 2), "on_miss": round(on_m, 2),
                    "gate_failures": init_fail, "rounds": rnd})
        sys.stderr.write(f"{row.get('key')}: off_miss={off_m:.2f} on_miss={on_m:.2f} "
                         f"gate_fail={init_fail} rounds={rnd}\n")

    def m(v):
        return round(statistics.mean(v), 3) if v else None

    lines = ["# Gate effect: blind-draft miss-rate, gates OFF vs ON (gate-correction loop)", "",
             f"Tickets: {len(per)} | seed {args.seed} | model {model}",
             "Miss-rate = human-UAC dimension axes the draft does NOT cover / human axes "
             "(oracle: mine_uac_dimensions.AXES).", "",
             "| metric | value |", "|---|---|",
             f"| mean miss-rate GATES OFF | {m(off_miss)} |",
             f"| mean miss-rate GATES ON | {m(on_miss)} |",
             f"| mean gate-failures fixed / ticket | {m(fixed)} |",
             f"| mean correction rounds / ticket | {m(rounds_used)} |", "",
             "## Per ticket", ]
    for p in per:
        lines.append(f"- {p['key']}: off_miss {p['off_miss']} -> on_miss {p['on_miss']} "
                     f"(human_axes={p['human_axes']}, gate_failures={p['gate_failures']}, rounds={p['rounds']})")
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    Path(args.out).with_suffix(".json").write_text(
        json.dumps({"off_miss": m(off_miss), "on_miss": m(on_miss), "fixed": m(fixed), "per": per}, indent=2),
        encoding="utf-8")
    print(json.dumps({"n": len(per), "off_miss": m(off_miss), "on_miss": m(on_miss),
                      "reduction": (round(m(off_miss) - m(on_miss), 3) if off_miss else None),
                      "out": args.out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
