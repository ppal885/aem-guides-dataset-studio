"""Analyze the human-UAC corpus for the recurring dimensions a senior QA includes.

For each ticket's human Acceptance Criteria, detect which coverage dimensions the
human addressed, then aggregate per component. The output is the data-backed
checklist of what the skill should consider (and currently tends to miss):
consumer surfaces, performance, attachments/big-content, cross-tool oracle, state
partitions, provenance channels, negative paths, regression, presets, localization
- plus style stats (AC count, length, Scope block, decide-vs-ask).

Usage:
  python scripts/uac_eval/analyze.py --corpus scripts/uac_eval/corpus.jsonl \
      --report-json scripts/uac_eval/report.json --report-md scripts/uac_eval/report.md
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

# Each dimension: name -> compiled regex over the lowercased human AC text.
DIMENSIONS = {
    "multi_surface": re.compile(r"\b(panel|dropdown|dialog|preview|right panel|left panel|toolbar|menu|tab|view)\b"),
    "performance": re.compile(r"\b(performance|large|loading|scale|big content|memory|timeout|slow|latency|throughput)\b"),
    "attachment_or_bigcontent": re.compile(r"\b(attach|attached|attachment|big content|sample|\.rar|\.zip|provided content|large map|large file)\b"),
    "cross_tool_oracle": re.compile(r"\b(oxygen|framemaker|xmetal|xml ?spy|word|how .*(is|are) .*(handled|addressed) in)\b"),
    "state_partition": re.compile(r"\b(both|with and without|bound by|not in|enabled and disabled|on and off|enumdef|profile|global and folder|baseline)\b"),
    "provenance_channels": re.compile(r"\b(crx|jcr:content|metadata\.xml|temporary files|temp files|rendition|renditionmapping|/import|api|migration|source file)\b"),
    "negative_error": re.compile(r"\b(invalid|error|fail|failure|missing|empty|fallback|not present|no tag loss|corrupt|broken)\b"),
    "regression_parity": re.compile(r"\b(regression|unaffected|other preset|backward|existing|no impact|still work|parity|unchanged)\b"),
    "output_preset": re.compile(r"\b(native pdf|dita-?ot|html5|aem site|aem ?sites|preset|epub|json output|kb output)\b"),
    "localization": re.compile(r"\b(translation|xliff|locale|language|multilingual|localization)\b"),
    "permissions_role": re.compile(r"\b(permission|role|admin|access|privilege|group)\b"),
    "css_styles": re.compile(r"\b(css|style|styling|placement|width|height|rendition)\b"),
}

SCOPE_RE = re.compile(r"(^|\n)\s*[*#-]?\s*scope\s*[:\-]", re.I)
ASK_RE = re.compile(r"(\?|\bwhich\b|\bTBD\b|\bto be (decided|confirmed)\b)", re.I)
BULLET_RE = re.compile(r"(^|\n)\s*(?:[*#\-•]|\d+[.)])\s+\S")


def _norm_component(components: list[str]) -> str:
    if not components:
        return "(none)"
    # canonicalize to the first, collapse known variants
    c = components[0].strip()
    m = {"Native_PDF": "Native PDF", "NativePDF": "Native PDF"}
    return m.get(c, c)


def analyze_row(row: dict) -> dict:
    ac = row.get("human_ac", "") or ""
    low = ac.lower()
    bullets = BULLET_RE.findall(ac)
    bullet_count = len(bullets)
    # crude AC-line word lengths
    lines = [l.strip() for l in ac.splitlines() if l.strip()]
    word_lens = [len(l.split()) for l in lines] or [0]
    dims = {name: bool(rx.search(low)) for name, rx in DIMENSIONS.items()}
    # count distinct surface words as a proxy for "multiple surfaces"
    surfaces = set(re.findall(r"\b(panel|dropdown|dialog|preview|toolbar|menu|view)\b", low))
    return {
        "key": row.get("key"),
        "component": _norm_component(row.get("component", [])),
        "ac_chars": len(ac),
        "bullet_count": bullet_count,
        "avg_line_words": round(statistics.mean(word_lens), 1),
        "has_scope_block": bool(SCOPE_RE.search(ac)),
        "asks_question": bool(ASK_RE.search(ac)),
        "distinct_surface_words": len(surfaces),
        "multi_surface_named": len(surfaces) >= 2,
        **{f"dim_{k}": v for k, v in dims.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(Path(__file__).with_name("corpus.jsonl")))
    ap.add_argument("--report-json", default=str(Path(__file__).with_name("report.json")))
    ap.add_argument("--report-md", default=str(Path(__file__).with_name("report.md")))
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.corpus).read_text(encoding="utf-8").splitlines() if l.strip()]
    feats = [analyze_row(r) for r in rows]
    n = len(feats)

    dim_keys = [f"dim_{k}" for k in DIMENSIONS] + ["multi_surface_named", "has_scope_block", "asks_question"]
    overall = {k: round(100 * sum(f[k] for f in feats) / n, 1) for k in dim_keys}
    style = {
        "tickets": n,
        "avg_bullets": round(statistics.mean([f["bullet_count"] for f in feats]), 1),
        "median_bullets": statistics.median([f["bullet_count"] for f in feats]),
        "avg_line_words": round(statistics.mean([f["avg_line_words"] for f in feats]), 1),
        "pct_scope_block": overall["has_scope_block"],
        "pct_asks_question": overall["asks_question"],
        "pct_multi_surface": overall["multi_surface_named"],
    }

    by_comp = defaultdict(list)
    for f in feats:
        by_comp[f["component"]].append(f)
    comp_report = {}
    for comp, fs in sorted(by_comp.items(), key=lambda kv: -len(kv[1])):
        if len(fs) < 5:
            continue
        comp_report[comp] = {
            "tickets": len(fs),
            **{k: round(100 * sum(f[k] for f in fs) / len(fs), 1) for k in dim_keys},
        }

    report = {"style": style, "overall_dimension_pct": overall, "by_component": comp_report}
    Path(args.report_json).write_text(json.dumps(report, indent=2), encoding="utf-8")

    # markdown
    lines = ["# UAC corpus analysis (human UAC_Done)", ""]
    lines.append(f"Tickets with a human UAC: **{n}**")
    lines.append("")
    lines.append("## Style")
    for k, v in style.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Overall — % of human UACs that include each dimension")
    for k, v in sorted(overall.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {k}: {v}%")
    lines.append("")
    lines.append("## By component (>=5 tickets) — dimension inclusion %")
    for comp, r in comp_report.items():
        lines.append(f"### {comp} ({r['tickets']})")
        top = sorted(((k, r[k]) for k in dim_keys), key=lambda kv: -kv[1])
        for k, v in top:
            if v >= 10:
                lines.append(f"- {k}: {v}%")
        lines.append("")
    Path(args.report_md).write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"tickets": n, "report_md": args.report_md, "report_json": args.report_json}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
