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
import uac_learning_harvester as harvester  # noqa: E402

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


PATTERN_FIXES_FILE = Path(__file__).resolve().parent / "pattern_fixes.json"


def load_pattern_fixes(path: Path = PATTERN_FIXES_FILE) -> dict[str, dict]:
    """pattern -> {"fix", "deployed_at"}: the skill fix for a correction pattern and when it reached the VM."""
    data = _read_json(path) or {}
    return {str(k): v for k, v in (data.get("fixes") or {}).items() if isinstance(v, dict)}


def _parse_time(value: str) -> datetime.datetime | None:
    value = str(value or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


def annotate_patterns(patterns: list[dict], fixes: dict[str, dict], posted_at: dict[str, str]) -> list[dict]:
    """Split each fixed pattern's tickets by whether the UAC was posted after the fix reached the VM. A fixed
    pattern is repeated only when two or more tickets posted after the fix were corrected for it, so the page
    shows whether the fix worked; a ticket with no posted time (a hand-posted UAC) counts as before the fix."""
    out = []
    for p in patterns:
        fix = fixes.get(str(p.get("pattern")))
        deployed = _parse_time(fix.get("deployed_at")) if fix else None
        if not fix or deployed is None:
            out.append(p)
            continue
        after = [k for k in p.get("tickets") or []
                 if (_parse_time(posted_at.get(k, "")) or deployed) > deployed]
        before = [k for k in p.get("tickets") or [] if k not in after]
        out.append({**p, "fix": str(fix.get("fix") or ""), "deployed_at": deployed.strftime("%Y-%m-%d %H:%M UTC"),
                    "tickets_after": after, "tickets_before": before, "repeated": len(after) >= 2})
    return sorted(out, key=lambda r: (not r.get("repeated"), "fix" in r, -len(r.get("tickets") or []), r.get("pattern", "")))


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
    totals = {k: 0 for k in ("accepted", "changed", "rewritten", "removed", "added")}
    for record in latest.values():
        for kind, n in _criterion_counts(record).items():
            totals[kind] += n
    judged_posted = totals["accepted"] + totals["changed"] + totals["rewritten"] + totals["removed"]
    # Time saved counts only criteria QE kept as written or edited; a reworded check QE rewrote is not counted.
    kept = totals["accepted"] + totals["changed"]
    kept_checks = kept + totals["rewritten"]
    kept_rate = kept_checks / judged_posted if judged_posted else 0.0
    saved_rate = kept / judged_posted if judged_posted else 0.0
    waiting = [r for r in posted if r["key"] not in latest]
    waiting_criteria = sum(int(r.get("criteria") or 0) for r in waiting)
    weeks: dict[str, int] = {}
    for r in posted:
        when = _week_start(str(r.get("updated") or ""))
        if when:
            weeks[when] = weeks.get(when, 0) + 1
    areas: dict[str, dict] = {}
    sizes_posted, sizes_final = [], []
    for record in latest.values():
        counts = _criterion_counts(record)
        judged = counts["accepted"] + counts["changed"] + counts["rewritten"] + counts["removed"]
        kept_here = counts["accepted"] + counts["changed"] + counts["rewritten"]
        for area in record.get("components") or ["(no component)"]:
            row = areas.setdefault(str(area), {"area": str(area), "tickets": 0, "judged": 0, "kept": 0})
            row["tickets"] += 1
            row["judged"] += judged
            row["kept"] += kept_here
        if judged:
            sizes_posted.append(judged)
            sizes_final.append(kept_here + int(counts.get("added") or 0))
    return {
        "by_area": sorted(areas.values(), key=lambda a: (-(a["kept"] / a["judged"] if a["judged"] else 0), a["area"])),
        "median_posted": _median(sizes_posted), "median_final": _median(sizes_final),
        "posted_tickets": len(posted), "posted_criteria": sum(int(r.get("criteria") or 0) for r in posted),
        "judged_tickets": len(latest), "waiting_tickets": len(waiting), "waiting_criteria": waiting_criteria,
        **totals, "kept": kept, "kept_checks": kept_checks, "judged_criteria": judged_posted, "kept_rate": kept_rate,
        "minutes": minutes, "hours_saved": kept * minutes / 60,
        "hours_potential": waiting_criteria * saved_rate * minutes / 60,
        "weeks": sorted(weeks.items()),
    }


def _criterion_counts(record: dict) -> dict[str, int]:
    """Per-criterion outcome counts of one harvested record. Records written before the harvester knew reworded
    criteria are re-paired from their entries, so the page and new records count the same way."""
    entries = record.get("criteria")
    if isinstance(entries, list) and entries:
        entries = harvester.pair_rewrites([e for e in entries if isinstance(e, dict)])
        return {k: sum(1 for e in entries if e.get("kind") == k)
                for k in ("accepted", "changed", "rewritten", "removed", "added")}
    counts = record.get("counts") or {}
    return {k: int(counts.get(k) or 0) for k in ("accepted", "changed", "rewritten", "removed", "added")}


def collect_verdicts(out: Path) -> dict[str, dict]:
    """key -> the newest harvested verdict: outcome CHANGED (a person edited it) or ACCEPTED_AS_IS, with counts."""
    verdicts: dict[str, dict] = {}
    path = out / "learning" / "records.jsonl"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("key") and record.get("outcome") in ("CHANGED", "ACCEPTED_AS_IS"):
                verdicts[str(record["key"])] = {"outcome": record["outcome"], "counts": _criterion_counts(record),
                                                "edit_origin": record.get("edit_origin") or ""}
    return verdicts


def _days_since(value: str, now: datetime.datetime) -> int | None:
    when = _parse_time(value)
    return max(0, (now - when).days) if when else None


def _verdict(row: dict, verdicts: dict[str, dict], now: datetime.datetime) -> tuple[str, str]:
    """(filter group, cell text) for one posted ticket."""
    v = verdicts.get(row["key"])
    if not v:
        days = _days_since(str(row.get("updated") or ""), now)
        return "waiting", f"Waiting for QE{f' - {days} day(s)' if days is not None else ''}"
    c = v["counts"]
    if v["outcome"] == "ACCEPTED_AS_IS":
        return "accepted", f"Accepted untouched ({c['accepted']} kept)"
    parts = [f"{c[k]} {label}" for k, label in (("accepted", "kept"), ("changed", "edited"),
                                                 ("rewritten", "reworded"), ("removed", "removed"),
                                                 ("added", "added")) if c[k]]
    who = "corrected via Claude" if v["edit_origin"] == "CLAUDE_REWRITE" else "edited by QE"
    return "edited", f"{who.capitalize()}: {', '.join(parts) or 'no criteria matched'}"


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered, mid = sorted(values), len(values) // 2
    return float(ordered[mid]) if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


NOT_POSTED_GROUPS = (  # (prefix of the reason, group shown on the page)
    ("Label ", "Skipped: no UAC needed (label)"),
    ("Skipped: the last comment", "Skipped: ticket being closed"),
    ("Copilot CLI", "Generation did not finish (Copilot)"),
    ("Dry run", "Dry run only"),
    ("Unexpected error", "Unexpected error"),
    ("The Acceptance Criteria field already had text", "Field already filled by a person"),
)


def not_posted_groups(not_posted: list[dict]) -> list[tuple[str, int]]:
    """Not-posted tickets grouped by the kind of reason, most first; anything else failed a UAC check."""
    counts: dict[str, int] = {}
    for row in not_posted:
        reason = str(row.get("reason") or "")
        group = next((g for prefix, g in NOT_POSTED_GROUPS if reason.startswith(prefix)), "Failed a UAC check")
        counts[group] = counts.get(group, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


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
             ("Same check, reworded", impact["rewritten"], "s4"), ("Removed", impact["removed"], "s3")]
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
        marks.append(f'{shape} class="{slot} mark" tabindex="0" data-tip="{_e(title)}"></{"path" if i == len(shown) - 1 else "rect"}>')
        x += w + gap
    legend = "".join(
        f'<li><span class="key {slot}"></span>{_e(label)} <b>{n}</b> <span class="hint">({round(100 * n / total)}%)'
        f"</span></li>" for label, n, slot in parts)
    return (f'<svg class="bar100" viewBox="0 0 {width:.0f} {height:.0f}" preserveAspectRatio="none" role="img" '
            f'aria-label="Outcome of {total} judged criteria">{"".join(marks)}</svg>'
            f'<ul class="legend">{legend}</ul>'
            f'<p class="hint">QE also added {impact["added"]} new criteria we missed. "Same check, reworded" means '
            f'the check stayed but was reworded or merged into another criterion.</p>')


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
        bars.append(f'<path d="{_top_rounded(x, y, bar_w, h)}" class="s1 mark" tabindex="0" '
                    f'data-tip="Week of {_e(label)}: {n} UAC(s) posted"></path><text x="{x + bar_w / 2:.1f}" y="{y - 5:.1f}" class="val" text-anchor="middle">{n}</text>'
                    f'<text x="{x + bar_w / 2:.1f}" y="{16 + plot_h + 16:.1f}" class="tick" text-anchor="middle">{_e(label)}</text>')
    return (f'<svg class="cols" viewBox="0 0 {width:.0f} {height:.0f}" preserveAspectRatio="xMinYMid meet" '
            f'role="img" aria-label="UACs posted per week">'
            f'{grid}{"".join(bars)}</svg>')


def _hbars(rows: list[dict], label: str, empty: str) -> str:
    """Horizontal bars in HTML: one row per item with its label, a bar and its value. Each row is a hover and
    keyboard target that shows its tooltip; "muted" rows are drawn in the de-emphasis gray."""
    if not rows:
        return f'<p class="empty">{_e(empty)}</p>'
    top = max(float(r["value"]) for r in rows) or 1.0
    items = []
    for r in rows:
        width = max(1.5, 100 * float(r["value"]) / top) if r["value"] else 0
        muted = " muted" if r.get("muted") else ""
        items.append(f'<div class="hb-row" tabindex="0" data-tip="{_e(r["tip"])}"><span class="hb-label">{_e(r["label"])}</span>'
                     f'<span class="hb-track"><span class="hb-fill{muted}" style="width:{width:.1f}%"></span></span>'
                     f'<span class="hb-val">{_e(r["display"])}</span></div>')
    return f'<div class="hb" role="list" aria-label="{_e(label)}">{"".join(items)}</div>'


def collect_trend(posted: list[dict], verdicts: dict[str, dict]) -> list[dict]:
    """Per week a UAC was posted: how many were posted and judged, and of the judged criteria the share QE kept
    (as is, edited or reworded) and the share kept as written or edited (what time saved counts)."""
    weeks: dict[str, dict] = {}
    for row in posted:
        week = _week_start(str(row.get("updated") or ""))
        if not week:
            continue
        w = weeks.setdefault(week, {"week": week, "posted": 0, "judged": 0, "criteria": 0, "checks": 0, "saved": 0})
        w["posted"] += 1
        v = verdicts.get(row["key"])
        if not v:
            continue
        c = v["counts"]
        w["judged"] += 1
        w["criteria"] += c["accepted"] + c["changed"] + c["rewritten"] + c["removed"]
        w["checks"] += c["accepted"] + c["changed"] + c["rewritten"]
        w["saved"] += c["accepted"] + c["changed"]
    for w in weeks.values():
        w["checks_rate"] = w["checks"] / w["criteria"] if w["criteria"] else None
        w["saved_rate"] = w["saved"] / w["criteria"] if w["criteria"] else None
    return [weeks[k] for k in sorted(weeks)]


def _trend_chart(trend: list[dict], fixes: dict[str, dict], today: datetime.date | None = None) -> str:
    """Two lines on one 0-100% axis by week posted, on a day scale from the first week to today so every fix
    marker sits on its deploy day; a per-week hit area whose tooltip lists both values and the judged count."""
    points = [w for w in trend if w["checks_rate"] is not None]
    if not points:
        return '<p class="empty">No posted UAC has been judged yet.</p>'
    first = datetime.date.fromisoformat(trend[0]["week"])
    last_week = datetime.date.fromisoformat(trend[-1]["week"])
    end = max(last_week + datetime.timedelta(days=6), today or last_week)
    span = max(7, (end - first).days)
    width, left, right, top, plot_h, bottom = 640.0, 44.0, 16.0, 12.0, 160.0, 74.0
    plot_w = width - left - right
    height = top + plot_h + bottom

    def x(day: datetime.date) -> float:
        return left + plot_w * (day - first).days / span

    def y(rate: float) -> float:
        return top + plot_h * (1 - rate)

    grid = "".join(f'<line x1="{left}" x2="{width - right:.0f}" y1="{y(t / 100):.1f}" y2="{y(t / 100):.1f}" '
                   f'class="{"axis" if t == 0 else "grid"}"/><text x="{left - 6}" y="{y(t / 100) + 4:.1f}" '
                   f'class="tick" text-anchor="end">{t}%</text>' for t in (0, 25, 50, 75, 100))
    by_day: dict[datetime.date, list[str]] = {}
    for fix in fixes.values():
        when = _parse_time(fix.get("deployed_at"))
        if when and first <= when.date() <= end:
            ref = re.search(r"#\d+|\b[0-9a-f]{7,9}\b", str(fix.get("fix") or ""))
            by_day.setdefault(when.date(), []).append(ref.group(0) if ref else "fix")
    markers = []
    for n, (day, refs) in enumerate(sorted(by_day.items())):
        fx = x(day)
        flip = fx > left + plot_w * 0.75  # a label near the right edge sits left of its marker
        markers.append(f'<line x1="{fx:.1f}" x2="{fx:.1f}" y1="{top}" y2="{top + plot_h + 44 + 12 * (n % 2):.1f}" '
                       f'class="fixline"/><text x="{fx + (-3 if flip else 3):.1f}" y="{top + plot_h + 52 + 12 * (n % 2):.1f}" '
                       f'class="fixlabel" text-anchor="{"end" if flip else "start"}">{_e(" ".join(sorted(refs)))}</text>')
    lines, dots = [], []
    for key, slot in (("checks_rate", "s1"), ("saved_rate", "s2")):
        pts = [(x(datetime.date.fromisoformat(w["week"])), y(w[key])) for w in points]
        if len(pts) > 1:
            lines.append(f'<polyline points="{" ".join(f"{px:.1f},{py:.1f}" for px, py in pts)}" class="line {slot}"/>')
        dots += [f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" class="dot {slot}"/>' for px, py in pts]
    hits, ticks = [], []
    for w in trend:
        start_day = datetime.date.fromisoformat(w["week"])
        wx = x(start_day)
        label = start_day.strftime("%d %b")
        tip = (f"Week of {label}: {w['posted']} posted, {w['judged']} judged" +
               (f"; checks kept {round(100 * w['checks_rate'])}%, kept as written or edited "
                f"{round(100 * w['saved_rate'])}% of {w['criteria']} criteria" if w["checks_rate"] is not None else ""))
        hits.append(f'<rect x="{wx:.1f}" y="{top}" width="{plot_w * 7 / span:.1f}" height="{plot_h}" class="hit" '
                    f'tabindex="0" data-tip="{_e(tip)}"/>')
        ticks.append(f'<text x="{wx:.1f}" y="{top + plot_h + 16:.1f}" class="tick" text-anchor="middle">{_e(label)}</text>'
                     f'<text x="{wx:.1f}" y="{top + plot_h + 30:.1f}" class="tick" text-anchor="middle">'
                     f'n={w["judged"]}/{w["posted"]}</text>')
    legend = ('<ul class="legend"><li><span class="key line s1"></span>Checks QE kept (as is, edited or reworded)</li>'
              '<li><span class="key line s2"></span>Kept as written or edited (counted as time saved)</li>'
              '<li><span class="key fixkey"></span>Fix reached the VM (PR or commit)</li></ul>')
    rows = "".join(f'<tr><td>{_e(w["week"])}</td><td class="num">{w["posted"]}</td><td class="num">{w["judged"]}</td>'
                   f'<td class="num">{"-" if w["checks_rate"] is None else str(round(100 * w["checks_rate"])) + "%"}</td>'
                   f'<td class="num">{"-" if w["saved_rate"] is None else str(round(100 * w["saved_rate"])) + "%"}</td></tr>'
                   for w in trend)
    return (f'<svg class="trend" viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-label="Share of criteria QE kept '
            f'by week posted">{grid}{"".join(markers)}{"".join(hits)}{"".join(lines)}{"".join(dots)}{"".join(ticks)}</svg>'
            f'{legend}<details><summary class="hint">Table view</summary><table><thead><tr><th>Week of</th><th>Posted</th>'
            f'<th>Judged</th><th>Checks kept</th><th>Kept as written or edited</th></tr></thead><tbody>{rows}</tbody>'
            f'</table></details>')


def _impact_section(impact: dict, picked: int, not_posted: list[dict], patterns: list[dict],
                    trend_html: str = "") -> str:
    rate = round(100 * impact["kept_rate"])
    tiles = [
        (f"{impact['posted_tickets']}", "UACs written for QE", f"{impact['posted_criteria']} criteria in total"),
        (f"{rate}%", "Checks QE kept", f"{impact['kept_checks']} of {impact['judged_criteria']} judged: as is, edited or reworded"),
        (f"{impact['judged_tickets']}", "UACs judged by QE", "edited, or accepted untouched"),
        (f"{impact['waiting_tickets']}", "Waiting for QE", f"{impact['waiting_criteria']} criteria not judged yet"),
    ]
    tile_html = "".join(f'<div class="card tile"><div class="label">{_e(label)}</div><div class="value">{_e(value)}</div>'
                        f'<div class="hint">{_e(note)}</div></div>' for value, label, note in tiles)
    funnel = _hbars([
        {"label": "Tickets picked", "value": picked, "display": str(picked), "tip": f"{picked} tickets picked for a UAC"},
        {"label": "UAC posted", "value": impact["posted_tickets"], "display": str(impact["posted_tickets"]),
         "tip": f"{impact['posted_tickets']} of {picked} picked tickets got a UAC"},
        {"label": "Judged by QE", "value": impact["judged_tickets"], "display": str(impact["judged_tickets"]),
         "tip": f"{impact['judged_tickets']} posted UACs were edited or accepted untouched"},
    ], "Ticket pipeline", "No ticket picked yet.")
    areas = _hbars([
        {"label": a["area"], "value": a["kept"] / a["judged"] if a["judged"] else 0,
         "display": f"{round(100 * a['kept'] / a['judged']) if a['judged'] else 0}%",
         "tip": f"{a['area']}: QE kept {a['kept']} of {a['judged']} criteria on {a['tickets']} ticket(s)",
         "muted": a["judged"] < 5}
        for a in impact["by_area"]], "Criteria kept by product area", "No UAC has been judged yet.")
    if impact["judged_tickets"]:
        size = _hbars([
            {"label": "Our UAC", "value": impact["median_posted"], "display": f"{impact['median_posted']:g}",
             "tip": f"Median criteria we posted on a judged UAC: {impact['median_posted']:g}"},
            {"label": "QE's final UAC", "value": impact["median_final"], "display": f"{impact['median_final']:g}",
             "tip": f"Median criteria in the UAC after QE's edits (kept plus added): {impact['median_final']:g}"},
        ], "Criteria per UAC", "No UAC has been judged yet.")
    else:
        size = '<p class="empty">No UAC has been judged yet.</p>'
    groups = not_posted_groups(not_posted)
    reasons = _hbars([{"label": g, "value": n, "display": str(n), "tip": f"{g}: {n} ticket(s)",
                       "muted": g.startswith("Skipped")} for g, n in groups],
                     "Why UACs were not posted", "Every picked ticket was posted.")
    pattern_bars = _hbars([
        {"label": p["pattern"], "value": len(p.get("tickets") or []), "display": str(len(p.get("tickets") or [])),
         "tip": (f"{p['pattern']}: {', '.join(p.get('tickets') or [])}"
                + (f" - fixed by {p['fix']} on {p['deployed_at']}; {len(p.get('tickets_after') or [])} ticket(s) after"
                   if "fix" in p else "")),
         "muted": not p.get("repeated")}
        for p in patterns], "Correction patterns", "No correction patterns recorded yet.")
    weekly_rows = "".join(f'<tr><td>{_e(w)}</td><td class="num">{n}</td></tr>' for w, n in impact["weeks"])
    area_rows = "".join(f'<tr><td>{_e(a["area"])}</td><td class="num">{a["tickets"]}</td><td class="num">{a["kept"]}'
                        f'</td><td class="num">{a["judged"]}</td></tr>' for a in impact["by_area"])
    minutes = _hours(impact["minutes"])
    return f"""
<section id="impact" class="impact">
<div class="eyebrow">Impact</div>
<div class="hero-row">
  <div class="card hero">
    <div class="label">QE time saved so far (estimate)</div>
    <div class="hero-value">{_hours(impact['hours_saved'])}<span class="unit"> h</span></div>
    <div class="hint">{impact['kept']} criteria QE kept as written or edited instead of writing them, at about {minutes} minutes each. Reworded checks are not counted.</div>
    <div class="potential">+ up to {_hours(impact['hours_potential'])} h more from the {impact['waiting_tickets']} UACs still waiting for QE, at today's keep rate</div>
  </div>
  <div class="tiles">{tile_html}</div>
</div>
<div class="charts">
  <div class="card chart wide"><h3>What QE did with our criteria</h3><p class="hint">{impact['judged_criteria']} criteria on {impact['judged_tickets']} judged UACs</p>{_outcome_chart(impact)}</div>
  <div class="card chart wide"><h3>Is it getting better?</h3><p class="hint">Share of judged criteria QE kept, by the week the UAC was posted. n = UACs judged / posted that week; recent weeks fill in as QE reviews them.</p>{trend_html}</div>
  <div class="card chart"><h3>Ticket pipeline</h3><p class="hint">From picked to judged by QE</p>{funnel}</div>
  <div class="card chart"><h3>Criteria per UAC (median)</h3><p class="hint">What we posted against what QE ended with</p>{size}</div>
  <div class="card chart"><h3>Kept by product area</h3><p class="hint">Share of judged criteria QE kept; gray = fewer than 5 criteria</p>{areas}
    <details><summary class="hint">Table view</summary><table><thead><tr><th>Area</th><th>Tickets</th><th>Kept</th><th>Judged</th></tr></thead>
    <tbody>{area_rows}</tbody></table></details></div>
  <div class="card chart"><h3>UACs posted per week</h3><p class="hint">By the week the UAC was posted</p>{_weekly_chart(impact['weeks'])}
    <details><summary class="hint">Table view</summary><table><thead><tr><th>Week of</th><th>UACs</th></tr></thead>
    <tbody>{weekly_rows}</tbody></table></details></div>
  <div class="card chart"><h3>Why UACs were not posted</h3><p class="hint">Gray = skipped on purpose</p>{reasons}</div>
  <div class="card chart"><h3>Where QE corrects us</h3><p class="hint">Tickets per correction pattern; gray = seen once, or fixed and not seen again after the fix</p>{pattern_bars}</div>
</div>
<p class="hint footnote">Judged = a person edited the UAC (directly or through a Claude chat) or the ticket reached an accepted
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
        if "fix" in p:
            after = len(p.get("tickets_after") or [])
            flag = (f'<span class="flag">Repeated after the fix: {after} ticket(s)</span>' if p.get("repeated") else
                    f'<span class="ok">Fixed</span>: {_e(p["fix"])}, on the VM {_e(p["deployed_at"])}. '
                    f'{len(p.get("tickets_before") or [])} ticket(s) before the fix, {after} after.')
        else:
            flag = '<span class="flag">Repeated: pick for a skill fix</span>' if p.get("repeated") else "Seen once"
        rows.append(f"<tr><td><b>{_e(p.get('pattern'))}</b><br><span class=\"hint\">{_e(p.get('description') or '')}"
                    f"</span></td><td>{tickets}</td><td>{flag}</td><td>{lessons}</td></tr>")
    return rows


def render(posted: list[dict], not_posted: list[dict], edits: list[dict], accepted: int,
           jira_url: str, generated: str, shared_account: bool = False, patterns: list[dict] | None = None,
           report: tuple[str, str] = ("", ""), impact: dict | None = None,
           verdicts: dict[str, dict] | None = None, now: datetime.datetime | None = None,
           fixes: dict[str, dict] | None = None) -> str:
    patterns = patterns or []
    verdicts = verdicts or {}
    now = now or datetime.datetime.now(datetime.timezone.utc)
    verdict_of = {r["key"]: _verdict(r, verdicts, now) for r in posted}
    groups = {g: sum(1 for k in verdict_of if verdict_of[k][0] == g) for g in ("waiting", "edited", "accepted")}
    chips = "".join(f'<button type="button" class="chip-btn{" on" if g == "all" else ""}" data-group="{g}">{label} '
                    f'<span>{n}</span></button>'
                    for g, label, n in (("all", "All", len(posted)), ("waiting", "Waiting for QE", groups["waiting"]),
                                        ("edited", "Edited", groups["edited"]), ("accepted", "Accepted", groups["accepted"])))
    waiting = sorted((r for r in posted if verdict_of[r["key"]][0] == "waiting"),
                     key=lambda r: str(r.get("updated") or ""))
    waiting_rows = [
        f"<tr><td>{_ticket(r['key'], jira_url)}</td><td>{_e(r['summary'] or '-')}</td>"
        f"<td class=\"num\">{_e(_days_since(str(r.get('updated') or ''), now) if _days_since(str(r.get('updated') or ''), now) is not None else '-')}</td>"
        f"<td class=\"num\">{_e(r['criteria'] or '-')}</td><td>{_when(r['updated'])}</td></tr>"
        for r in waiting]
    posted_rows = [
        f"<tr data-group=\"{verdict_of[r['key']][0]}\"><td>{_ticket(r['key'], jira_url)}</td><td>{_e(r['summary'] or '-')}</td>"
        f"<td>{_e(r['where'])}{_notes(r.get('notes'))}</td><td class=\"num\">{_criteria_cell(r)}</td>"
        f"<td class=\"verdict {verdict_of[r['key']][0]}\">{_e(verdict_of[r['key']][1])}</td>"
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
    trend_html = _trend_chart(collect_trend(posted, verdicts), fixes or {}, now.date())
    impact_html = _impact_section(impact, picked, not_posted, patterns, trend_html) if impact else ""
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
:root {{ --bg:#f6f7f9; --panel:#ffffff; --text:#14161a; --muted:#646a73; --line:#e4e7ec; --accent:#2a63c7; --bad:#b4372c;
  --s1:#2a78d6; --s2:#1baf7a; --s3:#eb6834; --s4:#4a3aa7; --gray:#c9ccd1; --grid:#e1e0d9; --axis:#c3c2b7; --track:#eef0f3; --good:#006300;
  --shadow:0 1px 2px rgba(16,24,40,.05), 0 1px 3px rgba(16,24,40,.06); --nav:rgba(246,247,249,.85); }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0f1012; --panel:#17191c; --text:#eceef1; --muted:#9aa1ab; --line:#2a2d32; --accent:#7fb0ff; --bad:#f08a7e;
    --s1:#3987e5; --s2:#199e70; --s3:#d95926; --s4:#9085e9; --gray:#4a4e55; --grid:#2c2c2a; --axis:#383835; --track:#22252a; --good:#0ca30c;
    --shadow:none; --nav:rgba(15,16,18,.85); }}
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; scroll-padding-top:64px; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
nav.top {{ position:sticky; top:0; z-index:5; background:var(--nav); backdrop-filter:saturate(1.4) blur(8px);
  border-bottom:1px solid var(--line); }}
nav.top div {{ max-width:1160px; margin:0 auto; padding:10px 16px; display:flex; gap:4px; align-items:center; overflow-x:auto; scrollbar-width:none; }}
nav.top div::-webkit-scrollbar {{ display:none; }}
nav.top b {{ margin-right:12px; white-space:nowrap; }}
nav.top a {{ color:var(--muted); text-decoration:none; padding:5px 10px; border-radius:6px; font-size:14px; white-space:nowrap; }}
nav.top a:hover, nav.top a:focus-visible {{ background:var(--track); color:var(--text); }}
main {{ max-width:1160px; margin:0 auto; padding:24px 16px 64px; }}
h1 {{ font-size:26px; letter-spacing:-.01em; margin:0 0 4px; }}
h2 {{ font-size:18px; margin:40px 0 4px; }}
h3 {{ font-size:15px; margin:0 0 2px; }}
.eyebrow {{ text-transform:uppercase; letter-spacing:.08em; font-size:12px; font-weight:600; color:var(--muted); margin:28px 0 10px; }}
.sub, .hint {{ color:var(--muted); margin:0 0 12px; font-size:13.5px; }}
.chip {{ display:inline-block; background:var(--track); border-radius:999px; padding:2px 10px; font-size:12.5px; color:var(--muted); }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-top:18px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px 18px; box-shadow:var(--shadow); }}
.value {{ font-size:28px; font-weight:600; letter-spacing:-.01em; }}
.label {{ color:var(--muted); font-size:13px; }}
.wrap {{ overflow-x:auto; background:var(--panel); border:1px solid var(--line); border-radius:12px; box-shadow:var(--shadow); }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ text-align:left; padding:10px 14px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-size:12.5px; color:var(--muted); font-weight:600; white-space:nowrap; background:var(--panel); }}
tbody tr:hover td {{ background:var(--track); }}
tr:last-child td {{ border-bottom:none; }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
a {{ color:var(--accent); white-space:nowrap; }}
details summary {{ cursor:pointer; }}
details ul {{ margin:6px 0 0; padding-left:18px; color:var(--muted); }}
.reasons td:nth-child(3) {{ color:var(--bad); }}
.flag {{ color:var(--bad); font-weight:600; }}
.ok {{ color:var(--good); font-weight:600; }}
.hero-row {{ display:grid; grid-template-columns:minmax(260px,1.1fr) 2fr; gap:12px; }}
@media (max-width:820px) {{ .hero-row {{ grid-template-columns:1fr; }} }}
.hero {{ display:flex; flex-direction:column; justify-content:center; }}
.hero-value {{ font-size:60px; font-weight:650; line-height:1.05; letter-spacing:-.02em; margin:6px 0 8px; }}
.hero-value .unit {{ font-size:28px; color:var(--muted); font-weight:500; }}
.potential {{ margin-top:4px; font-size:13.5px; color:var(--text); background:var(--track); border-radius:8px; padding:8px 10px; }}
.tiles {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
@media (max-width:520px) {{ .tiles {{ grid-template-columns:1fr; }} }}
.tile .value {{ margin:2px 0; }}
.tile .hint {{ margin:0; }}
.charts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); gap:12px; margin-top:12px; }}
.chart.wide {{ grid-column:1 / -1; }}
.chart .hint {{ margin-bottom:14px; }}
.footnote {{ margin-top:12px; }}
svg.bar100 {{ width:100%; height:32px; display:block; }}
svg.cols {{ width:100%; height:200px; display:block; }}
.s1 {{ fill:var(--s1); }} .s2 {{ fill:var(--s2); }} .s3 {{ fill:var(--s3); }} .s4 {{ fill:var(--s4); }}
.mark {{ outline:none; transition:opacity .12s; }}
svg.trend {{ width:100%; max-width:760px; height:auto; display:block; }}
polyline.line {{ fill:none; stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }}
polyline.line.s1 {{ stroke:var(--s1); }} polyline.line.s2 {{ stroke:var(--s2); }}
circle.dot {{ stroke:var(--panel); stroke-width:2; }}
text.endlabel {{ fill:var(--text); font-size:12px; }}
line.fixline {{ stroke:var(--muted); stroke-width:1; opacity:.6; }}
text.fixlabel {{ fill:var(--muted); font-size:10.5px; }}
rect.hit {{ fill:transparent; outline:none; }}
rect.hit:hover, rect.hit:focus {{ fill:var(--track); fill-opacity:.5; }}
.key.line {{ height:3px; border-radius:2px; vertical-align:3px; width:14px; }}
.key.line.s1 {{ background:var(--s1); }} .key.line.s2 {{ background:var(--s2); }}
.key.fixkey {{ width:1px; height:12px; background:var(--muted); border-radius:0; }}
.mark:hover, .mark:focus {{ opacity:.8; }}
line.grid {{ stroke:var(--grid); stroke-width:1; }} line.axis {{ stroke:var(--axis); stroke-width:1; }}
text.tick {{ fill:var(--muted); font-size:11px; }} text.val {{ fill:var(--text); font-size:12px; font-weight:600; }}
ul.legend {{ list-style:none; padding:0; margin:14px 0 4px; display:flex; flex-wrap:wrap; gap:6px 22px; }}
.key {{ display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; vertical-align:-1px; }}
.key.s1 {{ background:var(--s1); }} .key.s2 {{ background:var(--s2); }} .key.s3 {{ background:var(--s3); }} .key.s4 {{ background:var(--s4); }}
.hb {{ display:grid; gap:8px; }}
.hb-row {{ display:grid; grid-template-columns:minmax(110px,40%) 1fr 44px; align-items:center; gap:10px; border-radius:6px; padding:2px 4px; outline:none; }}
.hb-row:hover, .hb-row:focus-visible {{ background:var(--track); }}
.hb-label {{ font-size:13.5px; line-height:1.3; overflow-wrap:anywhere; }}
.hb-track {{ height:14px; }}
.hb-fill {{ display:block; height:14px; background:var(--s1); border-radius:0 4px 4px 0; }}
.hb-fill.muted {{ background:var(--gray); }}
.hb-val {{ text-align:right; font-weight:600; font-size:13.5px; font-variant-numeric:tabular-nums; }}
.filter {{ display:flex; gap:8px; align-items:center; margin:0 0 10px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
.chip-btn {{ font:inherit; font-size:13px; border:1px solid var(--line); background:var(--panel); color:var(--text); border-radius:999px; padding:5px 12px; cursor:pointer; }}
.chip-btn span {{ color:var(--muted); margin-left:4px; }}
.chip-btn.on {{ background:var(--text); color:var(--bg); border-color:var(--text); }}
.chip-btn.on span {{ color:var(--bg); opacity:.75; }}
td.verdict.waiting {{ color:var(--muted); }} td.verdict.accepted {{ color:var(--good); }}
.filter {{ flex-wrap:wrap; }}
.filter input {{ width:min(360px,100%); padding:7px 10px; border:1px solid var(--line); border-radius:8px; background:var(--panel); color:var(--text); font:inherit; font-size:14px; }}
ul.lessons {{ margin:0; padding-left:18px; }}
pre.report {{ white-space:pre-wrap; background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:14px; font-size:13px; }}
.empty {{ color:var(--muted); background:var(--panel); border:1px dashed var(--line); border-radius:12px; padding:14px 16px; margin:0; }}
#tip {{ position:fixed; z-index:10; pointer-events:none; max-width:320px; background:var(--text); color:var(--bg); font-size:13px;
  padding:7px 10px; border-radius:8px; box-shadow:0 4px 12px rgba(0,0,0,.18); opacity:0; transition:opacity .08s; }}
</style>
</head>
<body>
<nav class="top" aria-label="Sections"><div><b>UAC release</b>
<a href="#impact">Impact</a><a href="#posted">Posted</a><a href="#waiting">Waiting for QE</a><a href="#not-posted">Not posted</a>
<a href="#patterns">Patterns</a><a href="#edits">QE edits</a><a href="#corrections">Corrections</a><a href="#report">Report</a></div></nav>
<main>
<h1>UAC release automation</h1>
<p class="sub"><span class="chip">Updated {_e(generated)} (VM time)</span> Read-only: built from the run files on the VM, never from Jira.</p>
<div class="cards">{cards}</div>
{impact_html}

<h2 id="posted">UAC posted</h2>
<p class="hint">Tickets where the UAC passed every check and was posted. Criteria is the number posted; "9 &rarr; 7 (edited)"
means the field was changed in Jira afterwards (read on the harvester's nightly run; hover for who and when).</p>
<div class="filter"><input type="search" placeholder="Filter by ticket or summary" data-filter="posted-table" aria-label="Filter posted tickets">
<div class="chips" role="group" aria-label="Filter by QE verdict">{chips}</div></div>
<div id="posted-table">{_table(["Ticket", "Summary", "Posted to", "Criteria", "QE verdict", "When"], posted_rows, "No UAC posted yet.")}</div>

<h2 id="waiting">Waiting for QE</h2>
<p class="hint">Posted UACs nobody has edited and whose ticket has not reached an accepted status, oldest first. These
hold the time still to be saved; ask QE to review the oldest.</p>
{_table(["Ticket", "Summary", "Days waiting", "Criteria", "Posted"], waiting_rows, "Every posted UAC has a QE verdict.")}

<h2 id="not-posted">UAC not posted</h2>
<p class="hint">Tickets the automation picked but did not post, with the reason. Click a reason to see every problem.</p>
<div class="reasons">{_table(["Ticket", "Summary", "Reason", "Last run"], not_posted_rows, "Every picked ticket was posted.")}</div>

<h2 id="patterns">Repeated correction patterns</h2>
<p class="hint">The kind of mistake each QE correction fixed (recorded with record_manual_rewrite.py --pattern), with the
tickets it was seen on. A pattern on two or more tickets is repeated: pick the next skill fix from the top rows.</p>
{_table(["Pattern", "Tickets", "Status", "Lessons"], pattern_rows, "No correction patterns recorded yet.")}

<h2 id="edits">Edited by a QE</h2>
<p class="hint">Posted UACs a QE changed directly in Jira; the harvester learns from these edits. {account_note}
Counts are per criterion. {accepted} more ticket(s) were accepted without edits.</p>
{_table(["Ticket", "Summary", "Edited by", "When", "Kept", "Changed", "Removed", "Added"], qe_rows, "No QE edits harvested yet.")}

<h2 id="corrections">QE corrections made through Claude</h2>
<p class="hint">Rewrites a QE asked for in a Claude or Codex chat and that session wrote with the shared account.
These are QE feedback too; their patterns are counted in the table above.</p>
{_table(["Ticket", "Summary", "Written by", "When", "Kept", "Changed", "Removed", "Added"], correction_rows, "No corrections recorded yet.")}

<h2 id="report">Monthly learning report</h2>
{report_html}
</main>
<div id="tip" role="tooltip"></div>
<script>
(() => {{
  const tip = document.getElementById("tip");
  const show = (el, x, y) => {{
    tip.textContent = el.getAttribute("data-tip");
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(x + 12, innerWidth - w - 8)) + "px";
    tip.style.top = Math.max(8, y - h - 12) + "px";
    tip.style.opacity = "1";
  }};
  const hide = () => {{ tip.style.opacity = "0"; }};
  document.addEventListener("pointermove", e => {{
    const el = e.target.closest && e.target.closest("[data-tip]");
    el ? show(el, e.clientX, e.clientY) : hide();
  }});
  document.addEventListener("focusin", e => {{
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el) {{ const r = el.getBoundingClientRect(); show(el, r.left, r.top); }}
  }});
  document.addEventListener("focusout", hide);
  const rows = document.querySelectorAll("#posted-table tbody tr");
  const search = document.querySelector("input[data-filter]");
  let group = "all";
  const apply = () => {{
    const q = search ? search.value.trim().toLowerCase() : "";
    rows.forEach(r => {{
      r.hidden = (q && !r.textContent.toLowerCase().includes(q)) || (group !== "all" && r.dataset.group !== group);
    }});
  }};
  if (search) search.addEventListener("input", apply);
  document.querySelectorAll(".chip-btn").forEach(b => b.addEventListener("click", () => {{
    group = b.dataset.group;
    document.querySelectorAll(".chip-btn").forEach(x => x.classList.toggle("on", x === b));
    apply();
  }}));
}})();
</script>
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
    posted_at = {r["key"]: str(r.get("updated") or "") for r in posted}
    patterns = annotate_patterns(collect_patterns(out), load_pattern_fixes(), posted_at) if out.is_dir() else []
    report = latest_report(out) if out.is_dir() else ("", "")
    minutes = float(config.get("impact_minutes_per_criterion") or DEFAULT_MINUTES_PER_CRITERION)
    impact = collect_impact(out, posted, minutes) if out.is_dir() else None
    verdicts = collect_verdicts(out) if out.is_dir() else {}
    page = render(posted, not_posted, edits, accepted, os.environ.get("JIRA_BASE_URL", ""),
                  time.strftime("%Y-%m-%d %H:%M %Z"), bool(config.get("learning_shared_account")),
                  patterns, report, impact, verdicts, fixes=load_pattern_fixes())
    write_atomic(args.out, page)
    print(f"wrote {args.out}: {len(posted)} posted, {len(not_posted)} not posted, {len(edits)} edited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
