"""Mine the variant matrix: which product variants human QEs list in a UAC for each product area.

Blind comparisons (blind50, 2026-10-05) showed that most human UAC points our drafts miss name a variant the
ticket never mentions: the other editor views, the other upload channels, the other translation workflows,
the other output presets. A QE adds them from product knowledge. This script measures, on a corpus of
NON-blind tickets, how often a human UAC names each variant family when the ticket touches an area, so the
skill can add the families humans usually check (data/variant_matrix.json) instead of guessing.

The area is detected from what the skill can see before a UAC exists (summary, description, components);
the variant families are detected in the human Acceptance Criteria. Blind tickets must be excluded
(--exclude), or the benchmark stops being blind. The output holds only family names and counts, no ticket
text.

    python scripts/uac_eval/mine_variant_matrix.py --csv <jira_export.csv> --exclude <blind_keys.txt> \
        --out .codex/skills/test-plan-generation/data/variant_matrix.json
    python scripts/uac_eval/mine_variant_matrix.py --self-test
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Product area -> regex over summary + description + components (what the skill sees before the UAC).
AREAS: dict[str, re.Pattern] = {
    "editor": re.compile(r"\b(editor|author(ing)? view|source view|web editor|topic editor|authoring)\b", re.I),
    "upload": re.compile(r"\b(upload|uploading|uploaded|ingest\w*|import(ed|ing)?|webdav|drag and drop)\b", re.I),
    "translation": re.compile(r"\b(translat\w*|locali[sz]\w*|xliff|language cop(y|ies))\b", re.I),
    "publishing": re.compile(r"\b(publish\w*|output preset|native pdf|dita-?ot|aem sites?|html5|generate output)\b", re.I),
    "review": re.compile(r"\b(review(er|s|ing)?|comment(s)?)\b", re.I),
    "baseline_version": re.compile(r"\b(baseline|version(s|ing)?|version label)\b", re.I),
}

# Variant family -> {variant name: regex over the human UAC}.
FAMILIES: dict[str, dict[str, re.Pattern]] = {
    "editor_views": {
        "Author view": re.compile(r"\bauthor(ing)? (view|mode)\b", re.I),
        "Source view": re.compile(r"\bsource (view|mode)\b", re.I),
        "Side-by-side view": re.compile(r"\b(side[- ]by[- ]side|sbs)\b", re.I),
        "Tags view": re.compile(r"\btags? view\b", re.I),
        "Preview": re.compile(r"\bpreview\b", re.I),
    },
    "editors": {
        "old and new Editor": re.compile(r"\b(old|new|both|legacy) editors?\b", re.I),
        "Assets UI": re.compile(r"\bassets? ui\b", re.I),
        "Repository panel": re.compile(r"\brepository (panel|view)\b", re.I),
        "Map console / Map view": re.compile(r"\bmap (console|view|dashboard)\b", re.I),
    },
    "upload_channels": {
        "Assets UI upload": re.compile(r"\b(assets? ui|browser) upload\b|\bupload\w* (from|via|through) (the )?assets? ui\b", re.I),
        "WebDAV": re.compile(r"\bwebdav\b", re.I),
        "AEM Desktop app": re.compile(r"\b(aem )?desktop (app|tool)\b", re.I),
        "API upload": re.compile(r"\b(api|rest|curl|postman) (upload|call)\b|\bupload\w* (via|using|through) (the )?api\b", re.I),
        "Oxygen connector": re.compile(r"\boxygen\b", re.I),
        "Zip / package": re.compile(r"\bzip\b|\bpackage (install|upload)\b", re.I),
    },
    "translation_workflows": {
        "Human translation": re.compile(r"\bhuman translation\b", re.I),
        "Machine translation": re.compile(r"\bmachine translation\b", re.I),
        "XLIFF": re.compile(r"\bxliff\b", re.I),
        "Multilingual / multiple languages": re.compile(r"\b(multi-?lingual|multiple (target )?languages)\b", re.I),
        "Translation with baseline": re.compile(r"\btranslat\w* .{0,30}baseline|baseline .{0,30}translat", re.I),
    },
    "output_presets": {
        "Native PDF": re.compile(r"\bnative pdf\b", re.I),
        "DITA-OT PDF": re.compile(r"\bdita-?ot\b", re.I),
        "AEM Sites": re.compile(r"\baem sites?\b", re.I),
        "HTML5": re.compile(r"\bhtml5\b", re.I),
        "JSON / Content Fragment": re.compile(r"\b(json|content fragment)\b", re.I),
        "Other output presets unaffected": re.compile(r"\b(other|all|every) (output )?presets?\b|\bother outputs?\b", re.I),
    },
    "review_surfaces": {
        "Review app / review panel": re.compile(r"\breview (app|panel|ui|task)\b", re.I),
        "Version history": re.compile(r"\bversion history\b", re.I),
        "Inbox / notifications": re.compile(r"\b(inbox|notification|email)\b", re.I),
    },
    "roles": {
        "Author": re.compile(r"\bauthors?\b", re.I),
        "Reviewer": re.compile(r"\breviewers?\b", re.I),
        "Admin / folder-profile admin": re.compile(r"\badmin(istrator)?s?\b", re.I),
        "Permissions": re.compile(r"\b(permission|access rights?|read-?only)\b", re.I),
    },
}

MIN_TICKETS = 4  # an area needs at least this many corpus tickets before its rates are kept


def read_csv(path: Path) -> list[dict]:
    """Rows with key, context (summary + description + components) and human UAC, from a Jira CSV export."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]

    def cols(name: str) -> list[int]:
        return [i for i, h in enumerate(header) if h == name]

    key, summary, desc = cols("Issue key")[0], cols("Summary")[0], cols("Description")[0]
    comps, uac = cols("Component/s"), cols("Custom field (Acceptance Criteria)")[0]
    out = []
    for r in rows[1:]:
        if len(r) <= uac or not r[uac].strip():
            continue
        context = " ".join([r[summary], r[desc]] + [r[i] for i in comps if i < len(r)])
        out.append({"key": r[key], "context": context, "human_ac": r[uac]})
    return out


def mine(rows: list[dict]) -> dict:
    area_tickets: Counter = Counter()
    hits: dict[str, Counter] = {a: Counter() for a in AREAS}
    for row in rows:
        families_seen = {(fam, name) for fam, variants in FAMILIES.items()
                         for name, rx in variants.items() if rx.search(row["human_ac"])}
        for area, rx in AREAS.items():
            if not rx.search(row["context"]):
                continue
            area_tickets[area] += 1
            hits[area].update(f"{fam}::{name}" for fam, name in families_seen)
            hits[area].update(f"{fam}::*" for fam in {f for f, _ in families_seen})
    matrix = {}
    for area, n in area_tickets.items():
        if n < MIN_TICKETS:
            continue
        fams = {}
        for fam, variants in FAMILIES.items():
            any_rate = hits[area][f"{fam}::*"] / n
            fams[fam] = {"tickets_naming_family": hits[area][f"{fam}::*"], "rate": round(any_rate, 2),
                         "variants": {name: hits[area][f"{fam}::{name}"] for name in variants}}
        matrix[area] = {"tickets": n, "families": fams}
    return {"schema": "aem-guides-variant-matrix-v1", "corpus_tickets": len(rows), "areas": matrix}


def self_test() -> int:
    rows = [
        {"key": "A-1", "context": "Editor crash in source view", "human_ac": "Works in Author view and Source view"},
        {"key": "A-2", "context": "Editor toolbar", "human_ac": "Side by side view keeps the selection"},
        {"key": "A-3", "context": "Upload of images via WebDAV", "human_ac": "Upload works with WebDAV and Oxygen"},
        {"key": "A-4", "context": "Editor paste", "human_ac": "Paste works"},
        {"key": "A-5", "context": "Editor save", "human_ac": "Save works in the old and new editor"},
    ]
    m = mine(rows)
    editor = m["areas"]["editor"]
    assert editor["tickets"] == 4, editor
    assert editor["families"]["editor_views"]["tickets_naming_family"] == 2, editor["families"]["editor_views"]
    assert editor["families"]["editor_views"]["variants"]["Source view"] == 1
    assert editor["families"]["editors"]["variants"]["old and new Editor"] == 1
    assert "upload" not in m["areas"], "areas below MIN_TICKETS are dropped"
    print("mine_variant_matrix self-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, help="Jira CSV export with the Acceptance Criteria field")
    parser.add_argument("--exclude", type=Path, help="file with blind ticket keys (one per line) to leave out")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.csv:
        parser.error("--csv is required")
    excluded = set(args.exclude.read_text(encoding="utf-8").split()) if args.exclude else set()
    rows = [r for r in read_csv(args.csv) if r["key"] not in excluded]
    result = mine(rows)
    result["excluded_blind_tickets"] = len(excluded)
    text = json.dumps(result, indent=1, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
