"""Build the UAC eval corpus from a Jira CSV export.

Reads a Jira CSV (multi-column Component/s and Labels, custom-field columns) and
writes one JSONL row per ticket that has a non-empty human Acceptance Criteria:
{key, summary, status, component[], labels[], description, human_ac}.

Usage:
  python scripts/uac_eval/build_corpus.py --csv "<export.csv>" --out scripts/uac_eval/corpus.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def _cols(header: list[str], name: str) -> list[int]:
    return [i for i, h in enumerate(header) if h.strip().lstrip("﻿") == name]


def _first(header: list[str], name: str) -> int:
    c = _cols(header, name)
    return c[0] if c else -1


def _join(row: list[str], idxs: list[int]) -> list[str]:
    return [row[i].strip() for i in idxs if i < len(row) and row[i].strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", default=str(Path(__file__).with_name("corpus.jsonl")))
    args = ap.parse_args()

    csv.field_size_limit(10_000_000)
    with open(args.csv, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)

    i_key = _first(header, "Issue key")
    i_sum = _first(header, "Summary")
    i_status = _first(header, "Status")
    i_desc = _first(header, "Description")
    i_ac = _first(header, "Custom field (Acceptance Criteria)")
    comp_cols = _cols(header, "Component/s")
    label_cols = _cols(header, "Labels")
    comment_cols = _cols(header, "Comment")

    import re as _re

    def _uac_from_comments(row: list[str]) -> str:
        """Fallback: recover a UAC posted as a comment. A Jira comment cell is
        'date;author;body'; pick the longest body that reads like a UAC (mentions
        acceptance/scope/criteria and has multiple bullet lines)."""
        best = ""
        for i in comment_cols:
            if i >= len(row) or not row[i].strip():
                continue
            body = row[i].split(";", 2)[-1]
            if not _re.search(r"accept|scope\s*:|criteria|\bAC\b", body, _re.I):
                continue
            if len(_re.findall(r"(^|\n)\s*(?:[*#\-•]|\d+[.)])\s+\S", body)) < 2:
                continue
            if len(body) > len(best):
                best = body.strip()
        return best

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out_path.open("w", encoding="utf-8") as out:
        from_field = 0
        from_comment = 0
        for row in rows:
            ac = row[i_ac].strip() if i_ac >= 0 and i_ac < len(row) else ""
            source = "ac_field"
            if not ac:
                ac = _uac_from_comments(row)
                source = "comment" if ac else ""
            if not ac:
                continue
            rec = {
                "key": row[i_key] if i_key >= 0 else "",
                "summary": row[i_sum] if i_sum >= 0 else "",
                "status": row[i_status] if i_status >= 0 else "",
                "component": _join(row, comp_cols),
                "labels": _join(row, label_cols),
                "description": row[i_desc] if i_desc >= 0 else "",
                "human_ac": ac,
                "uac_source": source,
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
            from_field += source == "ac_field"
            from_comment += source == "comment"
    sys.stderr.write(f"corpus: {written}/{len(rows)} had a human UAC ({from_field} ac_field, {from_comment} comment) -> {out_path}\n")
    print(json.dumps({"rows": len(rows), "with_uac": written, "from_field": from_field, "from_comment": from_comment, "out": str(out_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
