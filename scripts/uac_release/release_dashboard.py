#!/usr/bin/env python3
"""Build a read-only HTML page that shows what the UAC release automation did.

Reads <output_dir>/<KEY>/status.json (one per ticket the runner picked) and
<output_dir>/learning/records.jsonl (the harvester's records) and writes one static page:
  1. tickets picked for a UAC: posted, and not posted with the reason;
  2. tickets where a person edited our posted UAC, which the harvester picked up to learn from.

It never calls Jira and never changes a ticket. Run it from cron after the runner and harvester:
  python3 scripts/uac_release/release_dashboard.py --config /opt/uac-release/config.json \
      --env-file /opt/uac-release/uac.env --out /var/www/uac-release/index.html
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

AC_PATTERN = re.compile(r"Acceptance Criteria \d+:")
FIELD_NOW_FILE = "field-now.json"  # written by uac_learning_harvester.py on its nightly read of Jira

WHERE = {
    "POSTED": "Acceptance Criteria field",
}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def not_posted_reason(status: dict) -> tuple[str, list[str]]:
    """A one-line reason a person can read, and the full list behind it."""
    state = str(status.get("state") or "")
    problems = [str(p) for p in status.get("problems") or []]
    if status.get("last_error"):
        return f"Unexpected error: {status['last_error']}", problems
    if state == "FIELD_KEPT":
        return "The Acceptance Criteria field already had text, so the UAC was not written over it.", []
    if state == common.WRITTEN_UNRENDERED:
        return ("Written into the Acceptance Criteria field, but Jira did not render it as expected; "
                "no comment or done label was added. Check the field in Jira.", problems)
    if state == common.NOT_REQUIRED:
        label = status.get("not_required_label") or "UAC_Not_Required"
        return f"Label {label} is on the ticket, so no UAC is written.", []
    if state == "READY":
        return "Dry run only: the UAC passed the checks, but nothing was posted.", []
    if state == "FAILED" and problems:
        more = f" (and {len(problems) - 1} more)" if len(problems) > 1 else ""
        return problems[0] + more, problems
    if state == "FAILED":
        return "The UAC failed the checks; see status.json.", []
    return f"Not finished (state {state or 'unknown'}).", problems


def collect_tickets(out: Path) -> tuple[list[dict], list[dict]]:
    """Tickets the runner picked, split into posted and not posted."""
    posted, not_posted = [], []
    for ticket_dir in sorted(p for p in out.iterdir() if p.is_dir() and (p / common.STATUS_FILE).is_file()):
        status = common.read_status(ticket_dir)
        source = _read_json(ticket_dir / common.JIRA_SOURCE_FILE) or {}
        body = ticket_dir / "field-body.txt"
        row = {
            "key": ticket_dir.name,
            "summary": str(source.get("summary") or ""),
            "state": str(status.get("state") or ""),
            "updated": str(status.get("posted_at") or status.get("updated_at") or ""),
            "criteria": len(AC_PATTERN.findall(body.read_text(encoding="utf-8"))) if body.is_file() else 0,
            "field_now": _read_json(ticket_dir / FIELD_NOW_FILE) or {},
        }
        if row["state"] in WHERE and not status.get("last_error"):
            row["where"] = WHERE[row["state"]]
            if status.get("runtime_fallback") is not None:
                row["where"] += " (runtime gates not passed)"
            if status.get("linked_docs_unread"):
                row["where"] += " (linked design document not read)"
            row["notes"] = [str(n) for n in status.get("review_notes") or []]
            posted.append(row)
        else:
            row["reason"], row["problems"] = not_posted_reason(status)
            not_posted.append(row)
    return posted, not_posted


def collect_human_edits(out: Path) -> tuple[list[dict], int]:
    """The newest harvester record per ticket that a person changed, and how many were accepted as is."""
    path = out / "learning" / "records.jsonl"
    latest: dict[str, dict] = {}
    accepted: set[str] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            key = str(record.get("key") or "")
            if not key:
                continue
            if record.get("outcome") == "CHANGED":
                latest[key] = record
                accepted.discard(key)
            elif record.get("outcome") == "ACCEPTED_AS_IS" and key not in latest:
                accepted.add(key)
    rows = sorted(latest.values(), key=lambda r: str(r.get("edited_at") or ""), reverse=True)
    return rows, len(accepted)


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _ticket(key: str, jira_url: str) -> str:
    if jira_url:
        return f'<a href="{_e(jira_url.rstrip("/"))}/browse/{_e(key)}">{_e(key)}</a>'
    return _e(key)


def _when(value: str) -> str:
    return _e(value[:16].replace("T", " ")) if value else "-"


def _table(headers: list[str], rows: list[str], empty: str) -> str:
    if not rows:
        return f'<p class="empty">{_e(empty)}</p>'
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    return f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def _criteria_cell(row: dict) -> str:
    """Posted count; when the field changed after posting, also its count now and who changed it last."""
    posted = str(row["criteria"] or "-")
    now = row.get("field_now") or {}
    if not now.get("changed"):
        return posted
    at = str(now.get("last_change_at") or "")[:16].replace("T", " ") or "unknown time"
    title = _e(f"Changed in Jira after posting, last by {now.get('last_change_by') or 'unknown'} at {at}")
    return f"<span title=\"{title}\">{posted} &rarr; {_e(now.get('criteria', '?'))} (edited)</span>"


def _notes(notes: list[str] | None) -> str:
    """Review notes (for example a comment the UAC does not cover) behind a click; QE decides on them."""
    if not notes:
        return ""
    items = "".join(f"<li>{_e(n)}</li>" for n in notes)
    return f"<details><summary>{len(notes)} review note(s)</summary><ul>{items}</ul></details>"


def render(posted: list[dict], not_posted: list[dict], edits: list[dict], accepted: int,
           jira_url: str, generated: str, shared_account: bool = False) -> str:
    posted_rows = [
        f"<tr><td>{_ticket(r['key'], jira_url)}</td><td>{_e(r['summary'] or '-')}</td>"
        f"<td>{_e(r['where'])}{_notes(r.get('notes'))}</td><td class=\"num\">{_criteria_cell(r)}</td>"
        f"<td>{_when(r['updated'])}</td></tr>"
        for r in posted
    ]
    not_posted_rows = []
    for r in not_posted:
        reason = _e(r["reason"])
        if len(r["problems"]) > 1:
            items = "".join(f"<li>{_e(p)}</li>" for p in r["problems"])
            reason = f"<details><summary>{reason}</summary><ul>{items}</ul></details>"
        not_posted_rows.append(
            f"<tr><td>{_ticket(r['key'], jira_url)}</td><td>{_e(r['summary'] or '-')}</td>"
            f"<td>{reason}</td><td>{_when(r['updated'])}</td></tr>")
    edit_rows = []
    for r in edits:
        counts = r.get("counts") or {}
        edit_rows.append(
            f"<tr><td>{_ticket(str(r.get('key')), jira_url)}</td><td>{_e(r.get('summary') or '-')}</td>"
            f"<td>{_e(r.get('editor') or '-')}{' (Claude rewrite)' if r.get('edit_origin') == 'CLAUDE_REWRITE' else ''}</td><td>{_when(str(r.get('edited_at') or ''))}</td>"
            f"<td class=\"num\">{_e(counts.get('accepted', 0))}</td><td class=\"num\">{_e(counts.get('changed', 0))}</td>"
            f"<td class=\"num\">{_e(counts.get('removed', 0))}</td><td class=\"num\">{_e(counts.get('added', 0))}</td></tr>")
    picked = len(posted) + len(not_posted)
    cards = "".join(
        f'<div class="card"><div class="value">{n}</div><div class="label">{_e(label)}</div></div>'
        for n, label in ((picked, "Tickets picked"), (len(posted), "UAC posted"),
                         (len(not_posted), "Not posted"), (len(edits), "Edited by a person")))
    account_note = (
        "The automation and QE share one Jira account, so any change to the field that is not a text the "
        "runner posted counts here, including a rewrite by a Claude or Codex session with that account."
        if shared_account else
        "Edits made with the automation's own Jira account are not counted here, even when a person made "
        "them; they still show as \"edited\" in the posted table.")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UAC Release Tracker</title>
<style>
:root {{ --bg:#f7f7f5; --panel:#ffffff; --text:#1d1d1b; --muted:#6b6b66; --line:#e3e2dd; --accent:#2f5d8a; --bad:#a3392f; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#161615; --panel:#20201e; --text:#ecebe6; --muted:#a09f99; --line:#34332f; --accent:#8db4dc; --bad:#e08a80; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ font-size:22px; margin:0 0 4px; }}
h2 {{ font-size:17px; margin:32px 0 4px; }}
.sub, .hint {{ color:var(--muted); margin:0 0 12px; font-size:14px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-top:20px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }}
.value {{ font-size:26px; font-weight:600; }}
.label {{ color:var(--muted); font-size:13px; }}
.wrap {{ overflow-x:auto; background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ text-align:left; padding:9px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-size:13px; color:var(--muted); font-weight:600; white-space:nowrap; }}
tr:last-child td {{ border-bottom:none; }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
a {{ color:var(--accent); white-space:nowrap; }}
details summary {{ cursor:pointer; }}
details ul {{ margin:6px 0 0; padding-left:18px; color:var(--muted); }}
.reasons td:nth-child(3) {{ color:var(--bad); }}
.empty {{ color:var(--muted); background:var(--panel); border:1px dashed var(--line); border-radius:8px; padding:14px 16px; }}
</style>
</head>
<body>
<main>
<h1>UAC release automation</h1>
<p class="sub">Updated {_e(generated)} (VM time). Read-only: built from the run files on the VM, never from Jira.</p>
<div class="cards">{cards}</div>

<h2>UAC posted</h2>
<p class="hint">Tickets where the UAC passed every check and was posted. Criteria is the number posted; "9 &rarr; 7 (edited)"
means the field was changed in Jira afterwards (read on the harvester's nightly run; hover for who and when).</p>
{_table(["Ticket", "Summary", "Posted to", "Criteria", "When"], posted_rows, "No UAC posted yet.")}

<h2>UAC not posted</h2>
<p class="hint">Tickets the automation picked but did not post, with the reason. Click a reason to see every problem.</p>
<div class="reasons">{_table(["Ticket", "Summary", "Reason", "Last run"], not_posted_rows, "Every picked ticket was posted.")}</div>

<h2>Edited by a person</h2>
<p class="hint">Posted UACs a person changed afterwards; the harvester learns from these edits. {account_note}
Counts are per criterion. {accepted} more ticket(s) were accepted without edits.</p>
{_table(["Ticket", "Summary", "Edited by", "When", "Kept", "Changed", "Removed", "Added"], edit_rows, "No human edits harvested yet.")}
</main>
</body>
</html>
"""


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The web server reads this as another user; a strict umask (root 077) would hide the folder.
    os.chmod(path.parent, 0o755)
    handle, tmp = tempfile.mkstemp(prefix=".uac-release-", dir=path.parent)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=common.REPO_ROOT / "backend" / ".env",
                        help="read JIRA_BASE_URL from it for ticket links (no Jira call is made)")
    parser.add_argument("--out", type=Path, required=True, help="HTML file to write")
    args = parser.parse_args(argv)
    if args.env_file.is_file():
        common.load_env_file(args.env_file)
    config = common.load_config(args.config)
    out = Path(config["output_dir"])
    posted, not_posted = collect_tickets(out) if out.is_dir() else ([], [])
    edits, accepted = collect_human_edits(out) if out.is_dir() else ([], 0)
    page = render(posted, not_posted, edits, accepted, os.environ.get("JIRA_BASE_URL", ""),
                  time.strftime("%Y-%m-%d %H:%M %Z"), bool(config.get("learning_shared_account")))
    write_atomic(args.out, page)
    print(f"wrote {args.out}: {len(posted)} posted, {len(not_posted)} not posted, {len(edits)} edited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
