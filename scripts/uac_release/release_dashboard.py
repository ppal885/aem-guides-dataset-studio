#!/usr/bin/env python3
"""Build a read-only HTML page that shows what the UAC release automation did.

Reads <output_dir>/<KEY>/status.json (one per ticket the runner picked) and the harvester's
<output_dir>/learning/ files (records.jsonl, corrections.json, report-YYYY-MM.md) and writes one static page:
  1. tickets picked for a UAC: posted, and not posted with the reason;
  2. QE correction patterns, with the ones seen on two or more tickets marked for a skill fix;
  3. tickets where a QE edited our posted UAC, and corrections a QE made through a Claude session;
  4. the newest monthly learning report.

It never calls Jira and never changes a ticket. Run it from cron after the runner and harvester:
  python3 scripts/uac_release/release_dashboard.py --config /opt/uac-release/config.json \
      --env-file /opt/uac-release/uac.env --out /var/www/uac-release/index.html
"""
from __future__ import annotations

import argparse
import datetime
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
    if state == common.CLOSURE_ASKED:
        comment = status.get("closure_comment") or {}
        return (f"Skipped: the last comment ({comment.get('author') or 'unknown'}, comment {comment.get('id') or '?'}) "
                f"is about closing the ticket: \"{comment.get('quote') or ''}\". "
                "A later comment in Jira releases it.", [])
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


def collect_patterns(out: Path) -> list[dict]:
    """Correction patterns with their tickets and lessons, from the harvester's learning/corrections.json."""
    data = _read_json(out / "learning" / common.CORRECTIONS_FILE) or {}
    return [p for p in data.get("patterns") or [] if isinstance(p, dict)]


def latest_report(out: Path) -> tuple[str, str]:
    """(month, text) of the newest monthly learning report, or ("", "") when there is none."""
    reports = sorted((out / "learning").glob("report-*.md")) if (out / "learning").is_dir() else []
    if not reports:
        return "", ""
    try:
        return reports[-1].stem[len("report-"):], reports[-1].read_text(encoding="utf-8")
    except OSError:
        return "", ""


DEFAULT_MINUTES_PER_CRITERION = 10  # config "impact_minutes_per_criterion": time a QE needs to write one by hand


def collect_impact(out: Path, posted: list[dict], minutes: float = DEFAULT_MINUTES_PER_CRITERION) -> dict:
    """What the posted UACs saved QE, from the harvester's newest record per ticket and the posted rows.

    A ticket is judged when a person edited its UAC or it reached an accepted status untouched. Each judged
    criterion QE kept (as is or edited) is one QE did not write by hand; that time is the estimate. Nothing
    here is invented: the counts come from records.jsonl and field-body.txt, and the minutes are config."""
    latest: dict[str, dict] = {}
    path = out / "learning" / "records.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("key") and record.get("outcome") in ("CHANGED", "ACCEPTED_AS_IS"):
                latest[str(record["key"])] = record
    totals = {k: 0 for k in ("accepted", "changed", "removed", "added")}
    for record in latest.values():
        for kind in totals:
            totals[kind] += int((record.get("counts") or {}).get(kind) or 0)
    judged_posted = totals["accepted"] + totals["changed"] + totals["removed"]
    kept = totals["accepted"] + totals["changed"]
    kept_rate = kept / judged_posted if judged_posted else 0.0
    waiting = [r for r in posted if r["key"] not in latest]
    waiting_criteria = sum(int(r.get("criteria") or 0) for r in waiting)
    weeks: dict[str, int] = {}
    for r in posted:
        when = _week_start(str(r.get("updated") or ""))
        if when:
            weeks[when] = weeks.get(when, 0) + 1
    return {
        "posted_tickets": len(posted), "posted_criteria": sum(int(r.get("criteria") or 0) for r in posted),
        "judged_tickets": len(latest), "waiting_tickets": len(waiting), "waiting_criteria": waiting_criteria,
        **totals, "kept": kept, "judged_criteria": judged_posted, "kept_rate": kept_rate,
        "minutes": minutes, "hours_saved": kept * minutes / 60,
        "hours_potential": waiting_criteria * kept_rate * minutes / 60,
        "weeks": sorted(weeks.items()),
    }


def _week_start(value: str) -> str:
    """The Monday (YYYY-MM-DD) of a timestamp's week, or "" when it cannot be read."""
    try:
        day = datetime.date.fromisoformat(value[:10])
    except ValueError:
        return ""
    return (day - datetime.timedelta(days=day.weekday())).isoformat()


def _hours(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".") if value < 10 else f"{round(value):,}"


def _right_rounded(x: float, y: float, w: float, h: float, r: float = 4) -> str:
    """A bar segment whose right end (the data end) is rounded and whose left end is square."""
    r = min(r, w / 2, h / 2)
    return (f"M{x:.1f},{y:.1f}h{w - r:.1f}a{r},{r} 0 0 1 {r},{r}v{h - 2 * r:.1f}a{r},{r} 0 0 1 -{r},{r}"
            f"h-{w - r:.1f}z")


def _top_rounded(x: float, y: float, w: float, h: float, r: float = 4) -> str:
    """A column whose top (the data end) is rounded and whose baseline is square."""
    r = min(r, w / 2, h)
    return (f"M{x:.1f},{y + h:.1f}v-{h - r:.1f}a{r},{r} 0 0 1 {r},-{r}h{w - 2 * r:.1f}a{r},{r} 0 0 1 {r},{r}"
            f"v{h - r:.1f}z")


def _outcome_chart(impact: dict) -> str:
    """One 100% bar: judged criteria QE kept as is, kept with edits, or removed; legend carries the numbers."""
    parts = [("Kept as is", impact["accepted"], "s1"), ("Kept with edits", impact["changed"], "s2"),
             ("Removed", impact["removed"], "s3")]
    total = sum(n for _, n, _ in parts)
    if not total:
        return '<p class="empty">No UAC has been judged yet.</p>'
    width, height, gap = 600.0, 28.0, 2.0
    shown = [(label, n, slot) for label, n, slot in parts if n]
    usable = width - gap * (len(shown) - 1)
    x, marks = 0.0, []
    for i, (label, n, slot) in enumerate(shown):
        w = usable * n / total
        title = f"{label}: {n} of {total} criteria ({round(100 * n / total)}%)"
        shape = (f'<path d="{_right_rounded(x, 0, w, height)}"' if i == len(shown) - 1
                 else f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{height}"')
        marks.append(f'{shape} class="{slot}"><title>{_e(title)}</title></{"path" if i == len(shown) - 1 else "rect"}>')
        x += w + gap
    legend = "".join(
        f'<li><span class="key {slot}"></span>{_e(label)} <b>{n}</b> <span class="hint">({round(100 * n / total)}%)'
        f"</span></li>" for label, n, slot in parts)
    return (f'<svg class="bar100" viewBox="0 0 {width:.0f} {height:.0f}" preserveAspectRatio="none" role="img" '
            f'aria-label="Outcome of {total} judged criteria">{"".join(marks)}</svg>'
            f'<ul class="legend">{legend}</ul>'
            f'<p class="hint">QE also added {impact["added"]} criteria we missed.</p>')


def _weekly_chart(weeks: list[tuple[str, int]]) -> str:
    """Columns: UACs posted per week (single series, value on each cap)."""
    if not weeks:
        return '<p class="empty">No UAC posted yet.</p>'
    top = max(n for _, n in weeks)
    step = max(1, -(-top // 4))
    ticks = list(range(0, step * 4 + 1, step))
    left, bottom, plot_h, slot = 28.0, 22.0, 140.0, 64.0
    width, height = left + slot * len(weeks), plot_h + bottom + 16
    scale = plot_h / ticks[-1]
    grid = "".join(
        f'<line x1="{left}" x2="{width:.0f}" y1="{16 + plot_h - t * scale:.1f}" y2="{16 + plot_h - t * scale:.1f}" '
        f'class="{"axis" if t == 0 else "grid"}"/><text x="{left - 6}" y="{16 + plot_h - t * scale + 4:.1f}" '
        f'class="tick" text-anchor="end">{t}</text>' for t in ticks)
    bars = []
    for i, (week, n) in enumerate(weeks):
        bar_w = 24.0
        x = left + slot * i + (slot - bar_w) / 2
        h = n * scale
        y = 16 + plot_h - h
        label = datetime.date.fromisoformat(week).strftime("%d %b")
        bars.append(f'<path d="{_top_rounded(x, y, bar_w, h)}" class="s1"><title>Week of {_e(label)}: {n} UAC(s) posted'
                    f'</title></path><text x="{x + bar_w / 2:.1f}" y="{y - 5:.1f}" class="val" text-anchor="middle">{n}</text>'
                    f'<text x="{x + bar_w / 2:.1f}" y="{16 + plot_h + 16:.1f}" class="tick" text-anchor="middle">{_e(label)}</text>')
    return (f'<svg class="cols" viewBox="0 0 {width:.0f} {height:.0f}" preserveAspectRatio="xMinYMid meet" '
            f'role="img" aria-label="UACs posted per week">'
            f'{grid}{"".join(bars)}</svg>')


def _impact_section(impact: dict) -> str:
    tiles = [
        (f"{impact['posted_tickets']}", "UACs written for QE", f"{impact['posted_criteria']} criteria in total"),
        (f"{round(100 * impact['kept_rate'])}%", "Criteria QE kept",
         f"{impact['kept']} of {impact['judged_criteria']} judged, as is or edited"),
        (f"{impact['judged_tickets']}", "UACs judged by QE", "edited, or accepted untouched"),
        (f"{impact['waiting_tickets']}", "Waiting for QE", f"{impact['waiting_criteria']} criteria not judged yet"),
    ]
    tile_html = "".join(f'<div class="card"><div class="label">{_e(label)}</div><div class="value">{_e(value)}</div>'
                        f'<div class="hint">{_e(note)}</div></div>' for value, label, note in tiles)
    weekly_rows = "".join(f"<tr><td>{_e(w)}</td><td class=\"num\">{n}</td></tr>" for w, n in impact["weeks"])
    minutes = _hours(impact["minutes"])
    return f"""
<section class="impact">
<div class="hero card">
  <div class="label">QE time saved so far (estimate)</div>
  <div class="hero-value">{_hours(impact['hours_saved'])} h</div>
  <div class="hint">{impact['kept']} criteria QE kept instead of writing them, at about {minutes} minutes each.
  Up to {_hours(impact['hours_potential'])} h more when the {impact['waiting_tickets']} waiting UACs are kept at the same rate.</div>
</div>
<div class="tiles">{tile_html}</div>
<div class="charts">
  <div class="card chart"><h3>What QE did with our criteria</h3>{_outcome_chart(impact)}</div>
  <div class="card chart"><h3>UACs posted per week</h3>{_weekly_chart(impact['weeks'])}
    <details><summary class="hint">Table view</summary><table><thead><tr><th>Week of</th><th>UACs</th></tr></thead>
    <tbody>{weekly_rows}</tbody></table></details></div>
</div>
<p class="hint">Judged = a person edited the UAC (directly or through a Claude chat) or the ticket reached an accepted
status untouched. Minutes per criterion is the config value impact_minutes_per_criterion; it is an estimate, not a
measurement.</p>
</section>"""


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


def _edit_row(r: dict, jira_url: str) -> str:
    counts = r.get("counts") or {}
    reason = f"<br><span class=\"hint\">{_e(r['rewrite_reason'])}</span>" if r.get("rewrite_reason") else ""
    return (f"<tr><td>{_ticket(str(r.get('key')), jira_url)}</td><td>{_e(r.get('summary') or '-')}</td>"
            f"<td>{_e(r.get('editor') or '-')}{reason}</td><td>{_when(str(r.get('edited_at') or ''))}</td>"
            f"<td class=\"num\">{_e(counts.get('accepted', 0))}</td><td class=\"num\">{_e(counts.get('changed', 0))}</td>"
            f"<td class=\"num\">{_e(counts.get('removed', 0))}</td><td class=\"num\">{_e(counts.get('added', 0))}</td></tr>")


def _pattern_rows(patterns: list[dict], jira_url: str) -> list[str]:
    rows = []
    for p in patterns:
        tickets = ", ".join(_ticket(str(k), jira_url) for k in p.get("tickets") or [])
        lessons = "".join(f"<li>{_e(k)}: {_e(t)}</li>" for k, t in p.get("lessons") or [])
        lessons = f"<ul class=\"lessons\">{lessons}</ul>" if lessons else "-"
        flag = '<span class="flag">Repeated: pick for a skill fix</span>' if p.get("repeated") else "Seen once"
        rows.append(f"<tr><td><b>{_e(p.get('pattern'))}</b><br><span class=\"hint\">{_e(p.get('description') or '')}"
                    f"</span></td><td>{tickets}</td><td>{flag}</td><td>{lessons}</td></tr>")
    return rows


def render(posted: list[dict], not_posted: list[dict], edits: list[dict], accepted: int,
           jira_url: str, generated: str, shared_account: bool = False, patterns: list[dict] | None = None,
           report: tuple[str, str] = ("", ""), impact: dict | None = None) -> str:
    patterns = patterns or []
    impact_html = _impact_section(impact) if impact else ""
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
    qe_rows = [_edit_row(r, jira_url) for r in edits if r.get("edit_origin") != "CLAUDE_REWRITE"]
    correction_rows = [_edit_row(r, jira_url) for r in edits if r.get("edit_origin") == "CLAUDE_REWRITE"]
    pattern_rows = _pattern_rows(patterns, jira_url)
    repeated = sum(1 for p in patterns if p.get("repeated"))
    month, report_text = report
    report_html = (f"<details><summary>Learning report {_e(month)}</summary><pre class=\"report\">{_e(report_text)}"
                   f"</pre></details>" if report_text else
                   '<p class="empty">No monthly report yet; the harvester writes one on the 1st of each month.</p>')
    picked = len(posted) + len(not_posted)
    cards = "".join(
        f'<div class="card"><div class="value">{n}</div><div class="label">{_e(label)}</div></div>'
        for n, label in ((picked, "Tickets picked"), (len(posted), "UAC posted"),
                         (len(not_posted), "Not posted"), (len(qe_rows), "Edited by a QE"),
                         (len(correction_rows), "QE corrections via Claude"), (repeated, "Repeated patterns")))
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
:root {{ --bg:#f7f7f5; --panel:#ffffff; --text:#1d1d1b; --muted:#6b6b66; --line:#e3e2dd; --accent:#2f5d8a; --bad:#a3392f;
  --s1:#2a78d6; --s2:#1baf7a; --s3:#eb6834; --grid:#e1e0d9; --axis:#c3c2b7; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --s1:#3987e5; --s2:#199e70; --s3:#d95926; --grid:#2c2c2a; --axis:#383835; }}
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
.flag {{ color:var(--bad); font-weight:600; }}
.impact {{ margin-top:16px; }}
.hero {{ margin-bottom:12px; }}
.hero-value {{ font-size:52px; font-weight:600; line-height:1.1; margin:4px 0; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; }}
.charts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:12px; margin-top:12px; }}
.chart h3 {{ font-size:15px; margin:0 0 12px; }}
svg.bar100 {{ width:100%; height:28px; display:block; }}
svg.cols {{ width:100%; height:200px; display:block; }}
.s1 {{ fill:var(--s1); }} .s2 {{ fill:var(--s2); }} .s3 {{ fill:var(--s3); }}
line.grid {{ stroke:var(--grid); stroke-width:1; }} line.axis {{ stroke:var(--axis); stroke-width:1; }}
text.tick {{ fill:var(--muted); font-size:11px; }} text.val {{ fill:var(--text); font-size:12px; font-weight:600; }}
ul.legend {{ list-style:none; padding:0; margin:12px 0 4px; display:flex; flex-wrap:wrap; gap:6px 18px; }}
.key {{ display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; vertical-align:-1px; }}
.key.s1 {{ background:var(--s1); }} .key.s2 {{ background:var(--s2); }} .key.s3 {{ background:var(--s3); }}
ul.lessons {{ margin:0; padding-left:18px; }}
pre.report {{ white-space:pre-wrap; background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px; font-size:13px; }}
.empty {{ color:var(--muted); background:var(--panel); border:1px dashed var(--line); border-radius:8px; padding:14px 16px; }}
</style>
</head>
<body>
<main>
<h1>UAC release automation</h1>
<p class="sub">Updated {_e(generated)} (VM time). Read-only: built from the run files on the VM, never from Jira.</p>
<div class="cards">{cards}</div>
{impact_html}

<h2>UAC posted</h2>
<p class="hint">Tickets where the UAC passed every check and was posted. Criteria is the number posted; "9 &rarr; 7 (edited)"
means the field was changed in Jira afterwards (read on the harvester's nightly run; hover for who and when).</p>
{_table(["Ticket", "Summary", "Posted to", "Criteria", "When"], posted_rows, "No UAC posted yet.")}

<h2>UAC not posted</h2>
<p class="hint">Tickets the automation picked but did not post, with the reason. Click a reason to see every problem.</p>
<div class="reasons">{_table(["Ticket", "Summary", "Reason", "Last run"], not_posted_rows, "Every picked ticket was posted.")}</div>

<h2>Repeated correction patterns</h2>
<p class="hint">The kind of mistake each QE correction fixed (recorded with record_manual_rewrite.py --pattern), with the
tickets it was seen on. A pattern on two or more tickets is repeated: pick the next skill fix from the top rows.</p>
{_table(["Pattern", "Tickets", "Status", "Lessons"], pattern_rows, "No correction patterns recorded yet.")}

<h2>Edited by a QE</h2>
<p class="hint">Posted UACs a QE changed directly in Jira; the harvester learns from these edits. {account_note}
Counts are per criterion. {accepted} more ticket(s) were accepted without edits.</p>
{_table(["Ticket", "Summary", "Edited by", "When", "Kept", "Changed", "Removed", "Added"], qe_rows, "No QE edits harvested yet.")}

<h2>QE corrections made through Claude</h2>
<p class="hint">Rewrites a QE asked for in a Claude or Codex chat and that session wrote with the shared account.
These are QE feedback too; their patterns are counted in the table above.</p>
{_table(["Ticket", "Summary", "Written by", "When", "Kept", "Changed", "Removed", "Added"], correction_rows, "No corrections recorded yet.")}

<h2>Monthly learning report</h2>
{report_html}
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
    patterns = collect_patterns(out) if out.is_dir() else []
    report = latest_report(out) if out.is_dir() else ("", "")
    minutes = float(config.get("impact_minutes_per_criterion") or DEFAULT_MINUTES_PER_CRITERION)
    impact = collect_impact(out, posted, minutes) if out.is_dir() else None
    page = render(posted, not_posted, edits, accepted, os.environ.get("JIRA_BASE_URL", ""),
                  time.strftime("%Y-%m-%d %H:%M %Z"), bool(config.get("learning_shared_account")),
                  patterns, report, impact)
    write_atomic(args.out, page)
    print(f"wrote {args.out}: {len(posted)} posted, {len(not_posted)} not posted, {len(edits)} edited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
