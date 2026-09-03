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

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out_path.open("w", encoding="utf-8") as out:
        for row in rows:
            ac = row[i_ac].strip() if i_ac >= 0 and i_ac < len(row) else ""
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
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
    sys.stderr.write(f"corpus: {written}/{len(rows)} rows had a human UAC -> {out_path}\n")
    print(json.dumps({"rows": len(rows), "with_uac": written, "out": str(out_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
