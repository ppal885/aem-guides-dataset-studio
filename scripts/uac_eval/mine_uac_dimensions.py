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
    "batch_failure_path (one item fails, the rest continue)": re.compile(
        r"\b(remaining|rest\s+of\s+the|other)\s+(assets?|files?|topics?|articles?|items?|maps?|jobs?)\b"
        r"|\b(one|a\s+single|each)\s+(asset|file|topic|article|item)\s+that\s+fails?\b"
        r"|\bdoes\s+not\s+(fail|stop|block|halt)\s+the\s+(whole|entire|rest)", re.I),
    "hotfix_build (hotfix / fixed build / backport)": re.compile(
        r"\b(hot\s*-?fix|fixed\s+build|patch\s+build|service\s+pack|backport)", re.I),
}

# Ticket-level signals (from summary + description, not the UAC): a dimension is most useful when
# measured on the tickets it applies to, not on the whole corpus.
TICKET_SIGNALS: dict[str, re.Pattern] = {
    "item-failure batch ticket": re.compile(
        r"\b(?:job|jobs|queue|queued|batch|batches|bulk)\b|\b\d[\d,]*\s+(?:files|assets|topics|items|articles|pages)\b",
        re.I),
    "hotfix or backport ticket": re.compile(r"\bhot\s*-?\s*fix\b|\bbackport(?:ed|ing)?\b|release-hotfix", re.I),
}
ITEM_FAILURE = re.compile(
    r"\b(?:one|a single|some|few|several|remaining|other|rest of the|\d[\d,]*)\s+(?:of the\s+)?"
    r"(?:files?|assets?|topics?|items?|articles?|pages?|maps?)\b[^.\n]{0,80}\b(?:fail\w*|stuck|error\w*|"
    r"not (?:processed|published|translated|generated)|skipped|remain\w*|missing|block\w*|halt\w*)"
    r"|\b(?:fail\w*|error|stuck|halt\w*|abort\w*)\b[^.\n]{0,60}\b(?:remaining|rest of the|other|whole|entire|all)"
    r"\s+(?:files?|assets?|topics?|items?|articles?|pages?|job|batch|queue)", re.I)
SIGNAL_AXIS = {
    "item-failure batch ticket": "batch_failure_path (one item fails, the rest continue)",
    "hotfix or backport ticket": "hotfix_build (hotfix / fixed build / backport)",
}
_STOP = set("the a an and or of to in on for with that this is are be as by it its from at when then should "
            "shall must will can not no verify user users".split())

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
    # uac_completeness_check.py failure_path (item-failure batch tickets)
    "batch_failure_path (one item fails, the rest continue)",
    # hotfix_scope_check.py (hotfix and backport tickets)
    "hotfix_build (hotfix / fixed build / backport)",
}


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z0-9]{2,}", (text or "").lower()) if w not in _STOP}


def ticket_signals(rows: list[dict]) -> dict:
    """Prevalence of an axis among the tickets it applies to, and how much of a human UAC stays with the
    reporter's own words (the reporter-scenario proxy: an AC line sharing >=3 content words with the
    summary and description)."""
    applies: Counter = Counter()
    covered: Counter = Counter()
    shares = []
    for row in rows:
        ac = (row.get("human_ac") or "").strip()
        if len(ac) < 20:
            continue
        text = f"{row.get('summary') or ''}\n{row.get('description') or ''}"
        for signal, rx in TICKET_SIGNALS.items():
            hit = rx.search(text) and (signal != "item-failure batch ticket" or ITEM_FAILURE.search(text))
            if hit:
                applies[signal] += 1
                covered[signal] += bool(AXES[SIGNAL_AXIS[signal]].search(ac))
        reporter = _words(text)
        lines = [l.strip(" *#-\t") for l in ac.splitlines()]
        lines = [l for l in lines if len(l.split()) >= 5 and not re.match(r"(?i)^(source|tbd|evidence)\s*:", l)]
        if lines and reporter:
            shares.append(sum(1 for l in lines if len(_words(l) & reporter) >= 3) / len(lines))
    shares.sort()
    median = shares[len(shares) // 2] if shares else 0.0
    beyond = sum(1 for s in shares if s < 0.5)
    return {"applies": applies, "covered": covered, "median_reporter_share": median,
            "tickets_mostly_beyond_reporter": beyond, "measured": len(shares)}


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
    signal_rows = [
        {"summary": "310 files remain In Progress after the translation job", "description": "",
         "human_ac": "A processing error on one asset does not fail the whole job; the remaining assets are processed."},
        {"summary": "Bulk publish shows the wrong start time", "description": "The job lists 40 topics.",
         "human_ac": "Verify that the bulk publish job shows the start time in the user's time zone."},
        {"summary": "[On-prem] HOTFIX: add PKCE", "description": "",
         "human_ac": "PKCE check should be working on the fixed build and existing profiles keep working."},
    ]
    sig = ticket_signals(signal_rows)
    assert sig["applies"]["item-failure batch ticket"] == 1, sig["applies"]
    assert sig["covered"]["item-failure batch ticket"] == 1
    assert sig["applies"]["hotfix or backport ticket"] == 1
    assert sig["covered"]["hotfix or backport ticket"] == 1
    assert sig["measured"] == 3
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
    sig = ticket_signals(rows)
    print("\nAxis prevalence on the tickets it applies to:")
    for signal, axis in SIGNAL_AXIS.items():
        applies, covered = sig["applies"][signal], sig["covered"][signal]
        pct = 100 * covered / applies if applies else 0
        print(f"  {signal:28s}: {applies:3d} tickets, human UAC covers {axis.split(' ')[0]} in {covered} ({pct:.0f}%)")
    print(f"  reporter scenario (proxy)   : median {100 * sig['median_reporter_share']:.0f}% of a human UAC's "
          f"criteria reuse the reporter's words; {sig['tickets_mostly_beyond_reporter']} of {sig['measured']} tickets "
          "have most criteria beyond them")
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
