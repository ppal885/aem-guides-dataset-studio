"""Harvest human UAC_Done tickets into a local eval corpus.

Pulls GUIDES tickets that carry a human-written acceptance-criteria field
(customfield_13400) and a UAC_Done label, and writes one JSONL row per ticket:
{key, summary, component, labels, status, description, attachments, human_ac}.

Input for a blind skill run = description + attachments; gold = human_ac.
Reads Jira creds from backend/.env via the studio JiraClient.

Usage:
  python scripts/uac_eval/harvest.py --max 40 --out scripts/uac_eval/corpus.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=40, help="max tickets to harvest")
    ap.add_argument(
        "--jql",
        default='project = GUIDES AND labels = UAC_Done AND "Acceptance Criteria" is not EMPTY ORDER BY updated DESC',
    )
    ap.add_argument("--out", default=str(Path(__file__).with_name("corpus.jsonl")))
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(str(REPO / "backend" / ".env"))
    except Exception:
        pass
    from app.services.jira_client import JiraClient  # noqa: E402

    client = JiraClient()
    keys: list[str] = []
    try:
        results = client.search_issues(args.jql, max_results=max(args.max, 50))
        for item in results:
            key = item.get("key") if isinstance(item, dict) else None
            if key:
                keys.append(key)
    except Exception as exc:  # fall back to a label-only JQL if the field JQL is rejected
        sys.stderr.write(f"primary JQL failed ({exc}); retrying label-only\n")
        results = client.search_issues(
            "project = GUIDES AND labels = UAC_Done ORDER BY updated DESC",
            max_results=max(args.max, 50),
        )
        keys = [i.get("key") for i in results if isinstance(i, dict) and i.get("key")]

    keys = keys[: args.max]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for key in keys:
            try:
                issue = client.get_issue(
                    key,
                    fields="summary,status,components,labels,description,attachment,customfield_13400",
                )
            except Exception as exc:
                sys.stderr.write(f"skip {key}: {exc}\n")
                continue
            f = issue.get("fields", {})
            human_ac = f.get("customfield_13400")
            if not human_ac or not str(human_ac).strip():
                continue  # no human UAC to compare against
            row = {
                "key": key,
                "summary": f.get("summary") or "",
                "status": (f.get("status") or {}).get("name") or "",
                "component": [c["name"] for c in f.get("components", [])],
                "labels": f.get("labels") or [],
                "description": f.get("description") or "",
                "attachments": [
                    {"filename": a["filename"], "mimeType": a["mimeType"], "size": a["size"]}
                    for a in f.get("attachment", [])
                ],
                "human_ac": str(human_ac),
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
    sys.stderr.write(f"harvested {written} tickets with a human UAC -> {out_path}\n")
    print(json.dumps({"harvested": written, "out": str(out_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
