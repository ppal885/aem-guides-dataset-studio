"""Mine the recurring dimension axes from a corpus of human UACs.

Root-cause fix for reactive one-gate-per-miss: instead of hand-coding a discovery gate
each time a single ticket burns us, learn the axis catalog ONCE from the corpus of human
acceptance criteria. For every human UAC in the corpus, detect which known variant axes it
disposition (source apps, link schemes, table structure, output presets, translation
project types, concurrency, topic types, editor scope, states, locale, migration,
security, ...), then aggregate by frequency and by component.

The output is an empirical axis catalog: the dimensions humans repeatedly include. Axes
that recur often but are NOT yet forced by a skill gate are the learning targets - they
tell us which discovery gates to add next, grounded in the corpus rather than in whichever
ticket happened to fail today.

Input: a JSONL corpus where each row has at least `human_ac` (and optionally `component`,
`key`, `summary`). Works on scripts/uac_eval/corpus.jsonl and on a jira_qa dump in the same
shape. Standard library only.

Usage:
  python scripts/uac_eval/mine_uac_dimensions.py --corpus scripts/uac_eval/corpus.jsonl
  python scripts/uac_eval/mine_uac_dimensions.py --corpus <jira_qa_dump.jsonl> --by-component
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

# The variant-axis taxonomy. Each axis -> a regex over the human UAC text. Kept broad on
# purpose; this measures which axes humans mention, not whether they mention them well.
AXES: dict[str, re.Pattern] = {
    "source_apps (Word/Excel/Google/HTML)": re.compile(
        r"\b(word|excel|google\s*doc|powerpoint|office|html\s*(page|content)|clipboard)\b", re.I),
    "link_schemes (http/ftp/mailto)": re.compile(
        r"\b(https?\b|ftps?\b|mailto|tel:|protocol|scheme|web\s*link|hyperlink)\b", re.I),
    "table_structure (nested/merged/header/simple)": re.compile(
        r"\b(nested\s+table|merged|span(ned)?|colspan|morerows|multiple\s+header|repeat\s+header|"
        r"simple\s*table|simpletable|normal\s+table|header\s+row)\b", re.I),
    "output_presets (PDF/HTML5/AEM Sites/DITA-OT)": re.compile(
        r"\b(native\s+pdf|dita-?ot|html5|aem\s+sites?|output\s+preset|preset)\b", re.I),
    "publishing_status (failed/queued/reconcile)": re.compile(
        r"\b(failed\s+status|status\s+(shown|reflect)|reconcile|queued|in\s+progress|"
        r"generation\s+status|output\s+status)\b", re.I),
    "concurrency_overlap": re.compile(
        r"\b(overlap|concurren|already\s+running|still\s+running|parallel|simultaneous|"
        r"same\s+map\s+and\s+preset)\b", re.I),
    "translation_project_types": re.compile(
        r"\b(translation|xliff|multilingual|localization|source\s+language|target\s+language|"
        r"scoping\s+project|newtranslationproject)\b", re.I),
    "topic_types (concept/reference/task)": re.compile(
        r"\b(concept|reference|task|glossary|bookmap|topic\s+type)\b", re.I),
    "editor_scope (new/old)": re.compile(
        r"\b(new\s+editor|old\s+editor|legacy\s+editor|both\s+editors|web\s+editor|map\s+editor)\b", re.I),
    "state_config_partition": re.compile(
        r"\b(enabled\s+or\s+disabled|on\s+and\s+off|profile|baseline|feature\s+flag|"
        r"setting\s+(is|when)|toggle)\b", re.I),
    "locale_translation_regional": re.compile(
        r"\b(locale|language\s+code|en_us|regional|country\s+code|xml:lang)\b", re.I),
    "upgrade_migration": re.compile(
        r"\b(upgrade|migrat|non-?uuid|backward\s+compat|on-?prem(ise)?\s+to\s+cloud|"
        r"version\s+boundary)\b", re.I),
    "permissions_role": re.compile(
        r"\b(permission|role|acl|access\s+control|unauthorized|privilege)\b", re.I),
    "negative_error_boundary": re.compile(
        r"\b(invalid|error|should\s+not|must\s+not|empty|missing|fallback|boundary|"
        r"broken|fail\s+gracefully)\b", re.I),
    "performance_scale": re.compile(
        r"\b(performance|large\s+(map|file|dataset)|\d{3,}\s*(topics?|maps?|files?)|timeout|"
        r"slow|latency|concurrent\s+load|bulk)\b", re.I),
    "persistence_roundtrip": re.compile(
        r"\b(save\s+and\s+reopen|reopen|persist|round[-\s]?trip|after\s+reload|survive)\b", re.I),
    "regression_unchanged": re.compile(
        r"\b(regression|unchanged|still\s+works?|not\s+affected|existing\s+behaviou?r|"
        r"backward)\b", re.I),
}

# Axes already forced by a fail-closed skill gate (across ALL gate scripts, not just
# coverage_forcing) so the report flags only GENUINELY ungated axes as learning targets.
# Keep in sync with the skill's gates.
GATED_AXES = {
    # coverage_forcing.py
    "source_apps (Word/Excel/Google/HTML)",
    "link_schemes (http/ftp/mailto)",
    "table_structure (nested/merged/header/simple)",
    "output_presets (PDF/HTML5/AEM Sites/DITA-OT)",
    "publishing_status (failed/queued/reconcile)",
    "concurrency_overlap",
    "performance_scale",
    "negative_error_boundary",           # _validate_negative_boundary_present
    "topic_types (concept/reference/task)",  # _validate_topic_type_coverage
    # dedicated gate scripts
    "state_config_partition",            # state_partition_coverage.py
    "translation_project_types",         # localization_regression_coverage.py
    "locale_translation_regional",       # localization_regression_coverage.py
    "upgrade_migration",                 # upgrade_migration_coverage.py
    "permissions_role",                  # security_coverage.py (AUTHZ)
    # structurally required by the 11-section plan (validate_test_plan Regression Areas)
    "regression_unchanged",
}


def _component(row: dict) -> str:
    comp = row.get("component")
    if isinstance(comp, list):
        return comp[0] if comp else "unknown"
    return str(comp or row.get("component_primary") or "unknown")


def mine(rows: list[dict]) -> dict:
    axis_freq: Counter = Counter()
    by_component: dict[str, Counter] = defaultdict(Counter)
    scored = 0
    for row in rows:
        ac = (row.get("human_ac") or row.get("acceptance_criteria") or "").strip()
        if len(ac) < 20:
            continue
        scored += 1
        comp = _component(row)
        hit_any = False
        for axis, rx in AXES.items():
            if rx.search(ac):
                axis_freq[axis] += 1
                by_component[comp][axis] += 1
                hit_any = True
        if hit_any:
            by_component[comp]["_tickets"] += 0  # keep key set stable
        by_component[comp]["_tickets_total"] += 1
    return {"scored": scored, "axis_freq": axis_freq, "by_component": by_component}


def run_self_tests() -> None:
    rows = [
        {"human_ac": "Copy paste from word and excel; validate nested tables and merged header cells; "
                     "multiple header rows; concept, reference, task topics; both old and new editor."},
        {"human_ac": "Any link inserted via weblink should be scope external; http, https, ftp supported."},
        {"human_ac": "short"},  # skipped
    ]
    out = mine(rows)
    assert out["scored"] == 2, out["scored"]
    assert out["axis_freq"]["source_apps (Word/Excel/Google/HTML)"] == 1
    assert out["axis_freq"]["link_schemes (http/ftp/mailto)"] >= 1
    assert out["axis_freq"]["table_structure (nested/merged/header/simple)"] == 1
    assert out["axis_freq"]["topic_types (concept/reference/task)"] == 1
    print("mine_uac_dimensions self-tests: PASS")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(Path(__file__).with_name("corpus.jsonl")))
    ap.add_argument("--by-component", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        run_self_tests()
        return 0
    rows = [json.loads(l) for l in Path(args.corpus).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = mine(rows)
    freq = out["axis_freq"]
    n = out["scored"]
    print(f"corpus: {len(rows)} rows | scored (human_ac >= 20 chars): {n}\n")
    print(f"{'AXIS':52s} {'tickets':>8s} {'%':>6s}  gated?")
    for axis, count in freq.most_common():
        pct = 100 * count / n if n else 0
        flag = "GATED" if axis in GATED_AXES else "** UNGATED (learn) **"
        print(f"{axis:52s} {count:8d} {pct:5.1f}%  {flag}")
    ungated = [(a, c) for a, c in freq.most_common() if a not in GATED_AXES]
    print("\nTop UNGATED recurring axes (next learning targets):")
    for axis, count in ungated[:8]:
        print(f"  - {axis}: {count} tickets ({100*count/n:.1f}%)")
    if args.by_component:
        print("\nBy component (top axis per component):")
        for comp, ctr in sorted(out["by_component"].items(), key=lambda kv: -kv[1].get("_tickets_total", 0)):
            total = ctr.get("_tickets_total", 0)
            top = [(a, c) for a, c in ctr.most_common() if not a.startswith("_")][:3]
            if total >= 5 and top:
                pretty = ", ".join(f"{a.split(' ')[0]}={c}" for a, c in top)
                print(f"  {comp:22s} (n={total:3d}): {pretty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
