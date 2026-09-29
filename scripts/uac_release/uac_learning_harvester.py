#!/usr/bin/env python3
"""Learn from what QE does to the UACs this automation posted. Read-only on Jira.

Nightly (harvest):
  For every ticket whose UAC this automation posted to the Acceptance Criteria field (status.json
  state POSTED, with the exact posted text in field-body.txt), read the current field, the ticket
  status and the changelog. Compare the posted criteria with the current ones, one criterion at a
  time:
    accepted  - the criterion is still there, unchanged
    removed   - QE deleted it (we wrote something that was not wanted)
    added     - QE wrote a criterion we did not have (we missed it)
    changed   - QE kept the idea but changed its wording or expected result
  Only a human's edit counts: when every change to the field after the post was made by the
  automation's own Jira user, nothing is recorded. When the field is unchanged, the UAC is recorded
  as accepted only once the ticket has moved on (status in "learning_accepted_statuses", default
  UAT, Closed, Resolved, Done); before that, an untouched field means nothing yet.
  One record per ticket version goes to <output_dir>/learning/records.jsonl, with the old text, the
  new text, who changed the field and when. The same version is never recorded twice.

Monthly (--report YYYY-MM):
  <output_dir>/learning/report-YYYY-MM.md: per component, how many criteria were accepted, removed,
  added and changed, the criteria QE removed (what we over-wrote) and the ones QE added (what we
  missed).

It never writes to Jira. QE only updates the Acceptance Criteria field; no label is needed.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

LEARNING_DIR = "learning"
RECORDS_FILE = "records.jsonl"
STATE_FILE = "state.json"
FIELD_BODY_FILE = "field-body.txt"
AC_FIELD_NAME = "Acceptance Criteria"
DEFAULT_ACCEPTED_STATUSES = ("UAT", "Closed", "Resolved", "Done")
MATCH_THRESHOLD = 0.5

_LABEL = re.compile(r"^(?:[-*#]\s+)?\*?\s*(?:Acceptance Criteri(?:a|on)|AC)[\s-]*(\d+)\s*:?\s*\*?\s*:?\s*(.*)$",
                    re.IGNORECASE)
_META = re.compile(r"^(?:[*#-]+\s*)?\*?(Source|TBD)\*?\s*:\s*(.*)$", re.IGNORECASE)
_NESTED = re.compile(r"^(?:\*\*+|##+|--+)\s+(.*)$")
_BULLET = re.compile(r"^(?:[*#-]|\d+[.)])\s+(.*)$")
# Jira wiki strikethrough: {-}text{-} or -text- (a dash touching text on the inside, not inside a word).
_STRIKE = re.compile(r"\{-\}(.*?)(?:\{-\}|$)|(?<![\w-])-(?=\S)(.+?)(?<=\S)-(?![\w-])")


def _clean(text: str) -> str:
    text = re.sub(r"\{\{(.*?)\}\}", r"\1", text or "")
    text = re.sub(r"(?<!\w)[*_](\S(?:.*?\S)?)[*_](?!\w)", r"\1", text)
    text = text.replace("\\[", "[").replace("\\]", "]")
    return " ".join(text.split())


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", _clean(text).lower()).split())


def _unstrike(line: str) -> str:
    """The line with its strikethrough markers removed (the text a reader sees, struck or not)."""
    return _STRIKE.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(2), line)


def _kept(line: str) -> str:
    """The part of the line that is not struck through."""
    return _STRIKE.sub(" ", line)


def _reason(text: str) -> str:
    return " ".join(text.replace("(", " ").replace(")", " ").split()).strip(" .;:-")


def parse_criteria(field_text: str) -> list[dict]:
    """Split an Acceptance Criteria field into criteria.

    A criterion starts at an 'Acceptance Criteria NN:' or 'AC-NN:' label (optionally after a bullet) or
    at a top-level bullet/numbered line. Source and TBD lines and nested bullets belong to the criterion
    above them. Text before the first criterion (for example a summary paragraph) is ignored.

    A plain line that follows a blank line (for example a closing note such as "Automation UI or API
    is required") is not part of the criterion above it.

    Strikethrough is how QE rejects a criterion in Jira: a criterion whose statement is fully struck is
    marked struck, and any text QE left unstruck in its lines (usually a note in brackets) is its reason.
    A partly struck criterion keeps only its unstruck text and records what was struck."""
    criteria: list[dict] = []
    after_blank = False
    for raw in (field_text or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            after_blank = True
            continue
        was_blank, after_blank = after_blank, False
        plain = _unstrike(line)
        label, meta, nested, bullet = _LABEL.match(plain), _META.match(plain), _NESTED.match(plain), _BULLET.match(plain)
        if label:
            kept_label = _LABEL.match(_kept(line).strip()) if _kept(line).strip() else None
            kept_text = _clean(kept_label.group(2)) if kept_label else ""
            full = _clean(label.group(2))
            criteria.append({"text": kept_text, "full": full, "source": "", "tbd": "",
                             "struck_parts": [] if kept_text == full else [full], "notes": []})
            continue
        if not criteria and not bullet:
            continue
        if meta and criteria:
            key = meta.group(1).lower()
            kept = _kept(line)
            if _clean(kept) != _clean(line):
                criteria[-1]["struck_parts"].append(_clean(plain))
                note = _reason(_clean(_META.sub(r"\2", kept.strip())) if _META.match(kept.strip()) else _clean(kept))
                if note:
                    criteria[-1]["notes"].append(note)
                continue
            criteria[-1][key] = (criteria[-1][key] + " " + _clean(meta.group(2))).strip()
        elif not nested and not bullet and was_blank:
            continue  # a free-standing note after a blank line belongs to no criterion
        elif (nested or not bullet) and criteria:
            body = nested.group(1) if nested else plain
            kept = _clean(_kept(line))
            criteria[-1]["full"] = (criteria[-1]["full"] + " " + _clean(body)).strip()
            if kept != _clean(line):
                criteria[-1]["struck_parts"].append(_clean(body))
                if kept and not _BULLET.match(kept):
                    criteria[-1]["notes"].append(_reason(kept))
            else:
                criteria[-1]["text"] = (criteria[-1]["text"] + " " + _clean(body)).strip()
        elif bullet:
            text = _clean(_BULLET.match(plain).group(1))
            kept = _clean(_kept(line))
            kept_text = _clean(_BULLET.match(kept).group(1)) if _BULLET.match(kept) else ""
            criteria.append({"text": kept_text, "full": text, "source": "", "tbd": "",
                             "struck_parts": [] if kept_text == text else [text], "notes": []})
    result = []
    for c in criteria:
        if not c["full"]:
            continue
        c["struck"] = not _norm(c["text"])
        c["reason"] = "; ".join(n for n in c.pop("notes") if n)
        result.append(c)
    return result


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _norm(a).split(), _norm(b).split()).ratio()


def compare(posted: list[dict], current: list[dict]) -> list[dict]:
    """One entry per criterion: accepted, changed, removed (posted only, or struck through by QE with its
    reason) or added (current only). A criterion QE struck through counts as removed, not changed."""
    entries: list[dict] = []
    left = list(range(len(posted)))
    struck = [j for j, c in enumerate(current) if c.get("struck")]
    right = [j for j in range(len(current)) if j not in struck]

    for j in struck:
        best = max(left, key=lambda i: similarity(posted[i]["text"], current[j]["full"]), default=None)
        if best is not None and similarity(posted[best]["text"], current[j]["full"]) >= MATCH_THRESHOLD:
            left.remove(best)
            entries.append({"kind": "removed", "old": posted[best]["text"], "new": "", "similarity": 0.0,
                            "struck": True, "reason": current[j].get("reason", "")})
    for i in list(left):
        for j in list(right):
            if _norm(posted[i]["text"]) == _norm(current[j]["text"]):
                entries.append({"kind": "accepted", "old": posted[i]["text"], "new": current[j]["text"],
                                "similarity": 1.0})
                left.remove(i)
                right.remove(j)
                break
    pairs = sorted(((similarity(posted[i]["text"], current[j]["full"]), i, j) for i in left for j in right),
                   reverse=True)
    for score, i, j in pairs:
        if score < MATCH_THRESHOLD or i not in left or j not in right:
            continue
        entry = {"kind": "changed", "old": posted[i]["text"], "new": current[j]["text"],
                 "similarity": round(score, 2)}
        if current[j].get("struck_parts"):
            entry["struck_parts"] = current[j]["struck_parts"]
            entry["reason"] = current[j].get("reason", "")
        entries.append(entry)
        left.remove(i)
        right.remove(j)
    entries += [{"kind": "removed", "old": posted[i]["text"], "new": "", "similarity": 0.0} for i in left]
    entries += [{"kind": "added", "old": "", "new": current[j]["text"], "similarity": 0.0} for j in right]
    return entries


def ac_field_changes(issue: dict, field_id: str) -> list[dict]:
    changes = []
    for history in (issue.get("changelog") or {}).get("histories") or []:
        for item in history.get("items") or []:
            if item.get("fieldId") == field_id or item.get("field") == AC_FIELD_NAME:
                changes.append({"at": str(history.get("created") or ""),
                                "by": str((history.get("author") or {}).get("name") or "")})
    return sorted(changes, key=lambda c: c["at"])


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()


def harvest_ticket(key: str, ticket_dir: Path, config: dict, jira, own_name: str, state: dict) -> dict | None:
    """Return a learning record for this ticket, or None when there is nothing new to learn."""
    status = common.read_status(ticket_dir)
    body_file = ticket_dir / FIELD_BODY_FILE
    if status.get("state") != "POSTED" or not body_file.is_file():
        return None
    posted_text = body_file.read_text(encoding="utf-8")
    field_id = config["acceptance_criteria_field"]
    issue = jira._json("GET", f"/rest/api/2/issue/{key}?expand=changelog&fields={field_id},status,components,summary")
    fields = issue.get("fields") or {}
    current_text = fields.get(field_id) or ""
    ticket_status = str((fields.get("status") or {}).get("name") or "")
    components = [str(c.get("name")) for c in fields.get("components") or [] if c.get("name")] or ["(none)"]
    posted_sha, current_sha = _sha(posted_text), _sha(current_text)
    accepted_statuses = {s.lower() for s in config.get("learning_accepted_statuses") or DEFAULT_ACCEPTED_STATUSES}

    if posted_sha == current_sha:
        if ticket_status.lower() not in accepted_statuses:
            return None
        outcome, editor, edited_at = "ACCEPTED_AS_IS", "", ""
    else:
        human = [c for c in ac_field_changes(issue, field_id) if c["by"] and c["by"] != own_name]
        if not human:
            return None
        outcome, editor, edited_at = "CHANGED", human[-1]["by"], human[-1]["at"]

    version = f"{outcome}:{current_sha}"
    if state.get(key) == version:
        return None
    state[key] = version
    entries = compare(parse_criteria(posted_text), parse_criteria(current_text))
    return {
        "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "key": key, "summary": str(fields.get("summary") or ""), "components": components,
        "ticket_status": ticket_status, "outcome": outcome, "editor": editor, "edited_at": edited_at,
        "posted_sha256": posted_sha, "current_sha256": current_sha,
        "posted_text": posted_text, "current_text": current_text,
        "counts": {k: sum(1 for e in entries if e["kind"] == k) for k in ("accepted", "changed", "removed", "added")},
        "criteria": entries,
    }


def harvest(config: dict, jira, logger, own_name: str) -> list[dict]:
    out = Path(config["output_dir"])
    learning = out / LEARNING_DIR
    learning.mkdir(parents=True, exist_ok=True)
    state_path = learning / STATE_FILE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except ValueError:
        state = {}
    records = []
    for ticket_dir in sorted(p for p in out.iterdir() if p.is_dir() and (p / common.STATUS_FILE).is_file()):
        key = ticket_dir.name
        try:
            record = harvest_ticket(key, ticket_dir, config, jira, own_name, state)
        except Exception:  # noqa: BLE001 - one ticket never stops the harvest
            logger.exception("%s: could not harvest", key)
            continue
        if record:
            records.append(record)
            logger.info("%s: %s %s", key, record["outcome"], record["counts"])
    with (learning / RECORDS_FILE).open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return records


def monthly_report(config: dict, month: str) -> Path:
    """Write learning/report-<month>.md from the records harvested in that month (YYYY-MM)."""
    learning = Path(config["output_dir"]) / LEARNING_DIR
    path = learning / RECORDS_FILE
    records = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if str(record.get("harvested_at") or "").startswith(month):
                records.append(record)
    by_component: dict[str, dict] = defaultdict(lambda: {"tickets": set(), "accepted": 0, "changed": 0,
                                                          "removed": [], "added": []})
    for record in records:
        for component in record.get("components") or ["(none)"]:
            bucket = by_component[component]
            bucket["tickets"].add(record["key"])
            for entry in record.get("criteria") or []:
                if entry["kind"] in ("accepted", "changed"):
                    bucket[entry["kind"]] += 1
                else:
                    text = entry["old"] or entry["new"]
                    if entry.get("reason"):
                        text += f" (QE: {entry['reason']})"
                    bucket[entry["kind"]].append((record["key"], text))
    lines = [f"# UAC learning report {month}", "",
             f"{len(records)} ticket version(s) harvested. Accepted = kept unchanged; changed = wording or "
             "expected result edited; removed = QE deleted it (we wrote too much); added = QE wrote it (we missed it).",
             ""]
    for component in sorted(by_component):
        b = by_component[component]
        lines += [f"## {component}", "",
                  f"- Tickets: {len(b['tickets'])}",
                  f"- Criteria accepted {b['accepted']}, changed {b['changed']}, removed {len(b['removed'])}, "
                  f"added {len(b['added'])}", ""]
        if b["removed"]:
            lines += ["What we wrote that QE removed:", ""] + [f"- {k}: {t}" for k, t in b["removed"]] + [""]
        if b["added"]:
            lines += ["What QE added that we missed:", ""] + [f"- {k}: {t}" for k, t in b["added"]] + [""]
    if not records:
        lines.append("No ticket versions were harvested this month.")
    learning.mkdir(parents=True, exist_ok=True)
    report = learning / f"report-{month}.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=common.REPO_ROOT / "backend" / ".env")
    parser.add_argument("--report", metavar="YYYY-MM",
                        help="write the monthly report for this month (use 'last' for the previous month)")
    args = parser.parse_args(argv)
    common.load_env_file(args.env_file)
    config = common.load_config(args.config)
    if args.report:
        month = args.report
        if month == "last":
            now = time.localtime()
            year, mon = (now.tm_year, now.tm_mon - 1) if now.tm_mon > 1 else (now.tm_year - 1, 12)
            month = f"{year:04d}-{mon:02d}"
        print(monthly_report(config, month))
        return 0
    out = Path(config["output_dir"])
    logger = common.setup_logging(out / "logs", "uac-learning")
    jira = common.JiraClient.from_env()
    own_name = str((jira.myself() or {}).get("name") or "")
    records = harvest(config, jira, logger, own_name)
    logger.info("harvested %d record(s)", len(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
