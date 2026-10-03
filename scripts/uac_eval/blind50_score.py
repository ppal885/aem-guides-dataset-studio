"""Score the blind50 benchmark and compare a skill rule change with the unchanged skill.

The blind50 set (scripts/uac_eval/blind50/, gitignored: it holds Jira text and human UACs) has one folder per
ticket with input.json, human_uac.md, the drafts and the labels written by the B4 labeling step
(BLIND50_LABELING.md). This script only reads saved labels; it never generates or labels anything.

    python scripts/uac_eval/blind50_score.py                    # per ticket and totals from blind50/labels.csv
    python scripts/uac_eval/blind50_score.py --tag b6b          # totals for labels_b6b.json
    python scripts/uac_eval/blind50_score.py --compare b6b      # rule change vs the unchanged skill
    python scripts/uac_eval/blind50_score.py --self-test

recall    = (FOUND + 0.5 * PARTIAL) / human criteria
precision = (MATCH + EXTRA_OK) / draft criteria
WRONG     = draft criteria labelled WRONG, per ticket

--compare scores labels_<tag>.json against the unchanged skill on the same tickets: labels.json (run 1) plus
labels_r2.json (run 2) where it exists, averaged per ticket. Two runs of the same skill differ by about
2 recall and 3 precision points on 13 tickets, so a change is KEEP only when recall rises by more than
NOISE_RECALL, precision does not fall by more than NOISE_PRECISION and WRONG per ticket does not rise.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parent / "blind50"
NOISE_RECALL, NOISE_PRECISION = 2.0, 3.0
HUMAN_LABELS = ("FOUND", "PARTIAL", "MISSED")
DRAFT_LABELS = ("MATCH", "EXTRA_OK", "EXTRA_NOISE", "WRONG")


def score(counts: Counter, tickets: int) -> dict:
    human = sum(counts[k] for k in HUMAN_LABELS)
    draft = sum(counts[k] for k in DRAFT_LABELS)
    return {
        "tickets": tickets,
        "recall": round(100 * (counts["FOUND"] + 0.5 * counts["PARTIAL"]) / human, 1) if human else 0.0,
        "precision": round(100 * (counts["MATCH"] + counts["EXTRA_OK"]) / draft, 1) if draft else 0.0,
        "wrong_per_ticket": round(counts["WRONG"] / tickets, 2) if tickets else 0.0,
        "human": round(human, 1), "draft": round(draft, 1),
    }


def counts_from_csv(path: Path) -> dict[str, Counter]:
    """Per-ticket label counts from labels.csv (key, side, criterion, label, matched, reason)."""
    per_ticket: dict[str, Counter] = defaultdict(Counter)
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["side"] == "human" or row["side"] in ("skill", "draft"):
                per_ticket[row["key"]][row["label"]] += 1
    return dict(per_ticket)


def counts_from_json(path: Path) -> Counter:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    found = Counter(p["label"] for p in data["human"])
    found.update(p["label"] for p in data["draft"])
    return found


def per_ticket_lines(per_ticket: dict[str, Counter]) -> list[str]:
    lines = ["| Ticket | Recall | Precision | WRONG |", "|---|---|---|---|"]
    for key in sorted(per_ticket):
        s = score(per_ticket[key], 1)
        lines.append(f"| {key} | {s['recall']}% | {s['precision']}% | {per_ticket[key]['WRONG']} |")
    total = Counter()
    for c in per_ticket.values():
        total.update(c)
    s = score(total, len(per_ticket))
    lines += ["", f"Total: {s['tickets']} tickets, recall {s['recall']}%, precision {s['precision']}%, "
              f"WRONG per ticket {s['wrong_per_ticket']}"]
    return lines


def baseline(folder: Path) -> Counter | None:
    runs = [counts_from_json(p) for p in (folder / "labels.json", folder / "labels_r2.json") if p.is_file()]
    if not runs:
        return None
    avg = Counter()
    for run in runs:
        avg.update(run)
    return Counter({k: v / len(runs) for k, v in avg.items()})


def compare(root: Path, tag: str, controls: set[str]) -> tuple[list[str], bool]:
    keys = sorted(p.parent.name for p in root.glob(f"GUIDES-*/labels_{tag}.json") if (p.parent / "labels.json").is_file())
    groups = {"all": keys, "affected": [k for k in keys if k not in controls], "controls": [k for k in keys if k in controls]}
    lines = [f"# {tag} vs the unchanged skill (average of the available baseline runs)", "",
             "| Set | Tickets | Recall base -> new | Precision base -> new | WRONG/ticket base -> new |",
             "|---|---|---|---|---|"]
    keep = False
    for name, ks in groups.items():
        if not ks:
            continue
        base, new = Counter(), Counter()
        for k in ks:
            base.update(baseline(root / k))
            new.update(counts_from_json(root / k / f"labels_{tag}.json"))
        b, n = score(base, len(ks)), score(new, len(ks))
        lines.append(f"| {name} | {len(ks)} | {b['recall']} -> {n['recall']} | {b['precision']} -> {n['precision']} | "
                     f"{b['wrong_per_ticket']} -> {n['wrong_per_ticket']} |")
        if name == "all":
            keep = (n["recall"] - b["recall"] > NOISE_RECALL and b["precision"] - n["precision"] <= NOISE_PRECISION
                    and n["wrong_per_ticket"] <= b["wrong_per_ticket"])
    lines += ["", f"Verdict: {'KEEP' if keep else 'REVERT'} (recall must rise by more than {NOISE_RECALL} points, "
              f"precision may fall by at most {NOISE_PRECISION}, WRONG per ticket must not rise)."]
    return lines, keep


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def labels(path: Path, human: list[str], draft: list[str]) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"human": [{"label": x} for x in human], "draft": [{"label": x} for x in draft]}),
                            encoding="utf-8")

        labels(root / "GUIDES-1" / "labels.json", ["FOUND", "MISSED"], ["MATCH", "EXTRA_NOISE"])
        labels(root / "GUIDES-1" / "labels_r2.json", ["FOUND", "PARTIAL"], ["MATCH", "EXTRA_OK"])
        labels(root / "GUIDES-1" / "labels_good.json", ["FOUND", "FOUND"], ["MATCH", "EXTRA_OK"])
        labels(root / "GUIDES-1" / "labels_bad.json", ["FOUND", "FOUND"], ["MATCH", "WRONG"])
        s = score(counts_from_json(root / "GUIDES-1" / "labels.json"), 1)
        assert (s["recall"], s["precision"], s["wrong_per_ticket"]) == (50.0, 50.0, 0.0), s
        base = score(baseline(root / "GUIDES-1"), 1)
        assert (base["recall"], base["precision"]) == (62.5, 75.0), base
        assert compare(root, "good", set())[1] is True, "recall up, precision up, no WRONG -> KEEP"
        assert compare(root, "bad", set())[1] is False, "WRONG rose -> REVERT"
        csv_path = root / "labels.csv"
        csv_path.write_text("key,side,criterion,label,matched,reason\nGUIDES-1,human,1,FOUND,1,\n"
                            "GUIDES-1,human,2,PARTIAL,1,\nGUIDES-1,skill,1,MATCH,1,\nGUIDES-1,skill,2,WRONG,,x\n",
                            encoding="utf-8")
        per = counts_from_csv(csv_path)
        s = score(per["GUIDES-1"], 1)
        assert (s["recall"], s["precision"], s["wrong_per_ticket"]) == (75.0, 50.0, 1.0), s
    print("blind50_score self-test passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--tag", help="score labels_<tag>.json instead of labels.csv")
    parser.add_argument("--compare", metavar="TAG", help="compare labels_<TAG>.json with the unchanged skill")
    parser.add_argument("--controls", default="", help="comma-separated control tickets for --compare")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.compare:
        lines, _ = compare(args.dir, args.compare, {k for k in args.controls.split(",") if k})
    elif args.tag:
        per = {p.parent.name: counts_from_json(p) for p in args.dir.glob(f"GUIDES-*/labels_{args.tag}.json")}
        lines = per_ticket_lines(per)
    else:
        lines = per_ticket_lines(counts_from_csv(args.dir / "labels.csv"))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
