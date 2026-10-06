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
  automation's own Jira user, nothing is recorded. The posted version compared is the automation
  account's last write before the human edit (from the changelog; field-body.txt when Jira has no
  text), so a later same-account rewrite is never counted as a QE change. When the field is unchanged, the UAC is recorded
  as accepted only once the ticket has moved on (status in "learning_accepted_statuses", default
  UAT, Closed, Resolved, Done); before that, an untouched field means nothing yet.
  One record per ticket version goes to <output_dir>/learning/records.jsonl, with the old text, the
  new text, who changed the field and when. The same version is never recorded twice.

Monthly (--report YYYY-MM):
  <output_dir>/learning/report-YYYY-MM.md: per component, how many criteria were accepted, removed,
  added and changed, the criteria QE removed (what we over-wrote) and the ones QE added (what we
  missed). "Removed by kind" says, for each reason a criterion was written (reporter step, regression
  check, entry point, switch state, item type, reverse action, item history, value forms, items made
  before the change, failure path - read from the run's UAC_EVIDENCE.json), how often QE removed it,
  and how many criteria per ticket we posted against how many QE left.

Backfill (--backfill KEY ...):
  For UACs posted by hand rather than by this automation, the posted text is not on disk. The
  backfill reads it from the ticket's Jira history instead: the last Acceptance Criteria change made
  by a generator user (the automation's Jira user plus "learning_generator_users" in the config or
  --generator-user) is the posted version, and the changes after it by anyone else are QE's edits.
  The comparison and the record are the same as the nightly harvest; the record says "backfill".

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
# What the Acceptance Criteria field holds now, written on every harvest so the release page can show a
# field changed after posting without calling Jira. Written for any change, whoever made it.
FIELD_NOW_FILE = "field-now.json"
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
# An Open Questions heading or an OQ-NN line (optionally bulleted, struck or tagged like "[To Confirm]").
_QUESTION = re.compile(r"^(?:[-*#]\s*)*(?:\[[^\]]*\]\s*)?\*?\s*(?:OQ[\s-]*\d+\b|Open Questions?\b|Suggested checks?\b|Out\s+of\s+scope\b)",
                       re.IGNORECASE)
# A screen named in a criterion: a word followed by panel, console, dashboard, ... ("right panel", "Review app").
_SCREEN = re.compile(r"\b([a-z][\w-]*)\s+(panel|console|dashboard|dialog|app|view|tab|page|editor|toolbar|menu|"
                     r"preview|widget|screen|inbox)\b", re.IGNORECASE)
_NOT_A_SCREEN_NAME = {"the", "a", "an", "this", "that", "each", "every", "same", "in", "on", "of", "to", "and", "or"}


def missed_screens(added_text: str, posted_text: str) -> list[str]:
    """Screens a QE-added criterion names that our posted UAC never mentioned."""
    posted = (posted_text or "").lower()
    found: list[str] = []
    for word, kind in _SCREEN.findall(added_text or ""):
        phrase = f"{word} {kind}".lower()
        if word.lower() not in _NOT_A_SCREEN_NAME and phrase not in posted and phrase not in found:
            found.append(phrase)
    return found


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
    is required") is not part of the criterion above it. An "Open Questions" heading or an "OQ-NN" line
    starts a questions section: nothing in it is a criterion or part of one, until the next
    "Acceptance Criteria NN:" / "AC-NN:" label.

    Strikethrough is how QE rejects a criterion in Jira: a criterion whose statement is fully struck is
    marked struck, and any text QE left unstruck in its lines (usually a note in brackets) is its reason.
    A partly struck criterion keeps only its unstruck text and records what was struck."""
    criteria: list[dict] = []
    after_blank = False
    in_questions = False
    for raw in (field_text or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            after_blank = True
            continue
        was_blank, after_blank = after_blank, False
        plain = _unstrike(line)
        label, meta, nested, bullet = _LABEL.match(plain), _META.match(plain), _NESTED.match(plain), _BULLET.match(plain)
        if label:
            in_questions = False
        elif _QUESTION.match(plain):
            in_questions = True  # an Open Questions heading or an OQ-NN line: not a criterion
            continue
        if in_questions:
            continue
        if label:
            kept_label = _LABEL.match(_kept(line).strip()) if _kept(line).strip() else None
            kept_text = _clean(kept_label.group(2)) if kept_label else ""
            full = _clean(label.group(2))
            criteria.append({"text": kept_text, "full": full, "source": "", "tbd": "", "number": int(label.group(1)),
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
            criteria.append({"text": kept_text, "full": text, "source": "", "tbd": "", "number": None,
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


def mark_promoted(entries: list[dict], suggested: list[str]) -> list[dict]:
    """An added criterion that matches one of our suggested checks was promoted by QE, not missed by us.

    Only records of UACs posted while suggested checks existed carry a "suggested" list; the delivered UAC
    has none any more, so new records have an empty list and promoted stays 0."""
    left = list(suggested or [])
    for entry in entries:
        if entry["kind"] != "added" or not left:
            continue
        best = max(left, key=lambda s: similarity(s, entry["new"]))
        if similarity(best, entry["new"]) >= MATCH_THRESHOLD:
            entry.update(kind="promoted", old=best, similarity=round(similarity(best, entry["new"]), 2))
            left.remove(best)
    return entries


def compare(posted: list[dict], current: list[dict]) -> list[dict]:
    """One entry per criterion: accepted, changed, removed (posted only, or struck through by QE with its
    reason) or added (current only). A criterion QE struck through counts as removed, not changed."""
    entries: list[dict] = []
    left = list(range(len(posted)))
    struck = [j for j, c in enumerate(current) if c.get("struck")]
    right = [j for j in range(len(current)) if j not in struck]

    def number(i: int) -> int:
        """The posted criterion's own number, or its position when the field has no numbers."""
        return posted[i].get("number") or i + 1

    for j in struck:
        best = max(left, key=lambda i: similarity(posted[i]["text"], current[j]["full"]), default=None)
        if best is not None and similarity(posted[best]["text"], current[j]["full"]) >= MATCH_THRESHOLD:
            left.remove(best)
            entries.append({"kind": "removed", "old": posted[best]["text"], "new": "", "similarity": 0.0,
                            "struck": True, "reason": current[j].get("reason", ""), "number": number(best)})
    for i in list(left):
        for j in list(right):
            if _norm(posted[i]["text"]) == _norm(current[j]["text"]):
                entries.append({"kind": "accepted", "old": posted[i]["text"], "new": current[j]["text"],
                                "similarity": 1.0, "number": number(i)})
                left.remove(i)
                right.remove(j)
                break
    pairs = sorted(((similarity(posted[i]["text"], current[j]["full"]), i, j) for i in left for j in right),
                   reverse=True)
    for score, i, j in pairs:
        if score < MATCH_THRESHOLD or i not in left or j not in right:
            continue
        entry = {"kind": "changed", "old": posted[i]["text"], "new": current[j]["text"],
                 "similarity": round(score, 2), "number": number(i)}
        if current[j].get("struck_parts"):
            entry["struck_parts"] = current[j]["struck_parts"]
            entry["reason"] = current[j].get("reason", "")
        entries.append(entry)
        left.remove(i)
        right.remove(j)
    entries += [{"kind": "removed", "old": posted[i]["text"], "new": "", "similarity": 0.0, "number": number(i)}
                for i in left]
    entries += [{"kind": "added", "old": "", "new": current[j]["text"], "similarity": 0.0} for j in right]
    return entries


# Why each posted criterion was written, read from the run's UAC_EVIDENCE.json. The monthly report counts
# how often QE removes each kind, so rules on size and variants follow QE's edits instead of guesses.
_SCENARIO_KINDS = {"CUSTOMER": "reporter step", "REGRESSION": "regression check", "VARIANT": "variant"}
_VARIANT_KINDS = (("entry_points", "entry point"), ("config_switches", "switch state"),
                  ("input_sources", "input source"))
_MECHANISM_KINDS = (("reverse_action", "reverse action"), ("item_origin", "item history"),
                    ("value_shapes", "value forms"))
KIND_ORDER = ("reporter step", "regression check", "variant", "entry point", "switch state", "input source",
              "item type", "reverse action", "item history", "value forms", "items made before the change",
              "failure path")


def _ac_numbers(entry) -> list[int]:
    if not isinstance(entry, dict) or entry.get("disposition") not in ("AC", "TBD"):
        return []
    value = entry.get("acs", entry.get("ac"))
    values = value if isinstance(value, list) else [value]
    return [v for v in values if isinstance(v, int) and not isinstance(v, bool)]


def criterion_kinds(evidence: dict) -> dict[int, list[str]]:
    """Criterion number -> the kinds of reason it was written for (a criterion can have several)."""
    kinds: dict[int, set[str]] = defaultdict(set)
    if not isinstance(evidence, dict):
        return {}
    scenario = evidence.get("scenario") if isinstance(evidence.get("scenario"), dict) else {}
    for entry in scenario.get("acs") or []:
        if isinstance(entry, dict) and isinstance(entry.get("ac"), int) and entry.get("scenario") in _SCENARIO_KINDS:
            kinds[entry["ac"]].add(_SCENARIO_KINDS[entry["scenario"]])
    variants = evidence.get("action_variants") if isinstance(evidence.get("action_variants"), dict) else {}
    for field, kind in _VARIANT_KINDS:
        for entry in variants.get(field) or []:
            for ac in _ac_numbers(entry):
                kinds[ac].add(kind)
    mechanism = variants.get("mechanism") if isinstance(variants.get("mechanism"), dict) else {}
    for entry in mechanism.get("variants") or []:
        for ac in _ac_numbers(entry):
            kinds[ac].add("item type")
    for field, kind in _MECHANISM_KINDS:
        for ac in _ac_numbers(mechanism.get(field)):
            kinds[ac].add(kind)
    for ac in _ac_numbers(evidence.get("pre_existing_items")):
        kinds[ac].add("items made before the change")
    failure = evidence.get("failure_path") if isinstance(evidence.get("failure_path"), dict) else {}
    for entry in failure.values():
        for ac in _ac_numbers(entry):
            kinds[ac].add("failure path")
    return {ac: sorted(found, key=KIND_ORDER.index) for ac, found in kinds.items()}


def ac_field_changes(issue: dict, field_id: str) -> list[dict]:
    """Every change to the Acceptance Criteria field, oldest first, with who, when and the new text."""
    changes = []
    for history in (issue.get("changelog") or {}).get("histories") or []:
        for item in history.get("items") or []:
            if item.get("fieldId") == field_id or item.get("field") == AC_FIELD_NAME:
                changes.append({"at": str(history.get("created") or ""),
                                "by": str((history.get("author") or {}).get("name") or ""),
                                "to": item.get("toString") or ""})
    return sorted(changes, key=lambda c: c["at"])


def generator_users(config: dict, own_name: str, extra: list[str] | None = None) -> set[str]:
    """Jira users whose writes to the field are the generated UAC, not a QE edit."""
    names = {own_name, *(config.get("learning_generator_users") or []), *(extra or [])}
    return {str(n).strip() for n in names if str(n or "").strip()}


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()


def _issue(jira, key: str, field_id: str) -> dict:
    return jira._json("GET", f"/rest/api/2/issue/{key}?expand=changelog&fields={field_id},status,components,summary")


def _record(key: str, fields: dict, config: dict, posted_text: str, current_text: str, human: list[dict],
            state: dict, extra: dict | None = None, suggested: list[str] | None = None,
            kinds: dict[int, list[str]] | None = None) -> dict | None:
    """Build the learning record, or None when nothing new can be learned yet."""
    ticket_status = str((fields.get("status") or {}).get("name") or "")
    components = [str(c.get("name")) for c in fields.get("components") or [] if c.get("name")] or ["(none)"]
    posted_sha, current_sha = _sha(posted_text), _sha(current_text)
    accepted_statuses = {s.lower() for s in config.get("learning_accepted_statuses") or DEFAULT_ACCEPTED_STATUSES}
    if posted_sha == current_sha:
        if ticket_status.lower() not in accepted_statuses:
            return None
        outcome, editor, edited_at = "ACCEPTED_AS_IS", "", ""
    else:
        if not human:
            return None
        outcome, editor, edited_at = "CHANGED", human[-1]["by"], human[-1]["at"]
    version = f"{outcome}:{current_sha}"
    if state.get(key) == version:
        return None
    state[key] = version
    posted_criteria, current_criteria = parse_criteria(posted_text), parse_criteria(current_text)
    entries = mark_promoted(compare(posted_criteria, current_criteria), suggested or [])
    for entry in entries:
        if kinds and entry.get("number") in kinds:
            entry["kinds"] = kinds[entry["number"]]
    record = {
        "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "key": key, "summary": str(fields.get("summary") or ""), "components": components,
        "ticket_status": ticket_status, "outcome": outcome, "editor": editor, "edited_at": edited_at,
        "posted_sha256": posted_sha, "current_sha256": current_sha,
        "posted_text": posted_text, "current_text": current_text,
        "counts": {k: sum(1 for e in entries if e["kind"] == k)
                   for k in ("accepted", "changed", "removed", "added", "promoted")},
        "posted_count": len(posted_criteria),
        "kept_count": sum(1 for c in current_criteria if not c.get("struck")),
        "criteria": entries,
    }
    record.update(extra or {})
    return record


def backfill_ticket(key: str, config: dict, jira, generators: set[str], state: dict) -> dict | None:
    """Learn from a hand-posted UAC: the last generator write in the Jira history is the posted version."""
    field_id = config["acceptance_criteria_field"]
    issue = _issue(jira, key, field_id)
    fields = issue.get("fields") or {}
    changes = ac_field_changes(issue, field_id)
    posted = [i for i, c in enumerate(changes) if c["by"] in generators]
    if not posted:
        return None
    last = changes[posted[-1]]
    human = [c for c in changes[posted[-1] + 1:] if c["by"] and c["by"] not in generators]
    return _record(key, fields, config, last["to"], fields.get(field_id) or "", human, state,
                   {"source": "backfill", "posted_by": last["by"], "posted_at": last["at"]})


def backfill(config: dict, jira, logger, generators: set[str], keys: list[str], dry_run: bool = False) -> list[dict]:
    learning = Path(config["output_dir"]) / LEARNING_DIR
    state_path = learning / STATE_FILE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except ValueError:
        state = {}
    records = []
    for key in keys:
        try:
            record = backfill_ticket(key, config, jira, generators, state)
        except Exception:  # noqa: BLE001 - one ticket never stops the backfill
            logger.exception("%s: could not backfill", key)
            continue
        if record:
            records.append(record)
            logger.info("%s: %s %s", key, record["outcome"], record["counts"])
        else:
            logger.info("%s: nothing to learn yet (no generated version, or no QE edit and not yet accepted)", key)
    if not dry_run:
        learning.mkdir(parents=True, exist_ok=True)
        with (learning / RECORDS_FILE).open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return records


def write_field_now(ticket_dir: Path, posted_text: str, current_text: str, changes: list[dict]) -> None:
    """Record the field's current criteria count and its last change, for the release page."""
    last = changes[-1] if changes else {}
    now = {
        "criteria": sum(1 for c in parse_criteria(current_text) if not c.get("struck")),
        "changed": _sha(current_text) != _sha(posted_text),
        "last_change_at": last.get("at", ""), "last_change_by": last.get("by", ""),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    (ticket_dir / FIELD_NOW_FILE).write_text(json.dumps(now, indent=2), encoding="utf-8")


def generated_baseline(changes: list[dict], generated, human: list[dict]) -> str:
    """The generated version a QE edit is compared with: the automation's last write before the last human
    edit (or its last write when no human edited). A session that re-wrote the posted UAC with the same
    account must not have its changes counted as QE changes. Empty when Jira has no such text.
    `generated` is a set of generator users or a predicate on a change."""
    is_generated = generated if callable(generated) else (lambda c: c["by"] in generated)
    end = changes.index(human[-1]) if human else len(changes)
    written = [c["to"] for c in changes[:end] if is_generated(c) and c["to"]]
    return written[-1] if written else ""


def generated_predicate(config: dict, own_name: str, ticket_dir: Path):
    """Which field changes the automation wrote.

    By default every write by the automation's Jira user or a configured generator user is generated. With
    "learning_shared_account": true (the automation and QE use the same Jira account), a write by the
    automation's own user counts as generated only when its text is one the runner posted (posted-bodies.txt
    or field-body.txt); any other write by that account is a QE edit. Configured
    "learning_generator_users" stay generated by author.
    """
    others = generator_users(config, "")
    if not config.get("learning_shared_account") or not own_name:
        users = generator_users(config, own_name)
        return lambda c: c["by"] in users
    posted = common.posted_body_keys(ticket_dir)
    return lambda c: c["by"] in others or (c["by"] == own_name and common.text_key(c["to"]) in posted)


def harvest_ticket(key: str, ticket_dir: Path, config: dict, jira, own_name, state: dict) -> dict | None:
    """Return a learning record for this ticket, or None when there is nothing new to learn."""
    status = common.read_status(ticket_dir)
    body_file = ticket_dir / FIELD_BODY_FILE
    if status.get("state") != "POSTED" or not body_file.is_file():
        return None
    posted_text = body_file.read_text(encoding="utf-8")
    field_id = config["acceptance_criteria_field"]
    issue = _issue(jira, key, field_id)
    fields = issue.get("fields") or {}
    if isinstance(own_name, set):
        is_generated = (lambda users: lambda c: c["by"] in users)(own_name)
    else:
        is_generated = generated_predicate(config, own_name, ticket_dir)
    changes = ac_field_changes(issue, field_id)
    human = [c for c in changes if c["by"] and not is_generated(c)]
    current_text = fields.get(field_id) or ""
    write_field_now(ticket_dir, posted_text, current_text, changes)
    if human and is_generated(changes[-1]) and human[-1]["to"]:
        # A later write by the automation is not a QE edit: learn from the last human version.
        current_text = human[-1]["to"]
    posted_text = generated_baseline(changes, is_generated, human) or posted_text
    evidence_path = ticket_dir / common.EVIDENCE_FILE
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig")) if evidence_path.is_file() else {}
    except ValueError:
        evidence = {}
    fallback = status.get("runtime_fallback")
    origin = {"uac_origin": "RUNTIME_FALLBACK" if fallback is not None else "CANONICAL",
              "runtime_fallback_gates": list(fallback or [])}
    return _record(key, fields, config, posted_text, current_text, human, state, origin,
                   suggested=status.get("suggested") or [], kinds=criterion_kinds(evidence))


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


ORIGIN_LABELS = {
    "CANONICAL": "Skill runtime (all gates passed)",
    "RUNTIME_FALLBACK": "Runtime fallback (gates not passed)",
    "HAND_POSTED": "Hand-posted (backfill)",
}


def _origin(record: dict) -> str:
    if record.get("uac_origin"):
        return str(record["uac_origin"])
    return "HAND_POSTED" if record.get("source") == "backfill" else "CANONICAL"


def origin_report_lines(records: list[dict]) -> list[str]:
    """QE's edits split by how the UAC was written, so a runtime-fallback UAC that QE fixes more
    often than a canonical one shows up in the data."""
    groups: dict[str, dict] = {}
    gates: dict[str, int] = defaultdict(int)
    for record in records:
        origin = _origin(record)
        group = groups.setdefault(origin, {"tickets": set(), "accepted": 0, "changed": 0, "removed": 0, "added": 0})
        group["tickets"].add(record.get("key"))
        for entry in record.get("criteria") or []:
            if entry.get("kind") in group:
                group[entry["kind"]] += 1
        if origin == "RUNTIME_FALLBACK":
            for gate in record.get("runtime_fallback_gates") or []:
                gates[str(gate).split(":", 1)[0].strip()] += 1
    lines = ["## By how the UAC was written", ""]
    if not groups:
        return lines + ["No ticket versions were harvested this month.", ""]
    lines += ["| UAC written by | Tickets | Posted criteria | Kept unchanged | Changed | Removed | QE added | Kept % |",
              "|---|---|---|---|---|---|---|---|"]
    for origin in [o for o in ORIGIN_LABELS if o in groups] + sorted(o for o in groups if o not in ORIGIN_LABELS):
        g = groups[origin]
        posted = g["accepted"] + g["changed"] + g["removed"]
        kept = f"{round(100 * g['accepted'] / posted)}%" if posted else "-"
        lines.append(f"| {ORIGIN_LABELS.get(origin, origin)} | {len(g['tickets'])} | {posted} | {g['accepted']} | "
                     f"{g['changed']} | {g['removed']} | {g['added']} | {kept} |")
    lines.append("")
    if gates:
        lines += ["Runtime gates that did not pass on fallback UACs (tickets):", ""] + \
            [f"- {gate}: {count}" for gate, count in sorted(gates.items(), key=lambda kv: (-kv[1], kv[0]))] + [""]
    lines += ["A lower Kept % or more QE-added criteria for fallback UACs than for runtime UACs is the signal to "
              "fix the runtime gate that keeps failing; a similar share means the fallback is safe.", ""]
    return lines


def kind_report_lines(records: list[dict]) -> list[str]:
    """How often QE removed each kind of posted criterion, and how many criteria QE kept per ticket."""
    posted: dict[str, int] = defaultdict(int)
    removed: dict[str, int] = defaultdict(int)
    for record in records:
        for entry in record.get("criteria") or []:
            if entry.get("kind") not in ("accepted", "changed", "removed"):
                continue
            for kind in entry.get("kinds") or ["(no evidence record)"]:
                posted[kind] += 1
                removed[kind] += entry["kind"] == "removed"
    lines = ["## Removed by kind", "",
             "Why each posted criterion was written (from the run's evidence record) and how often QE removed it. "
             "A kind QE removes often is one we over-write; change the rule for it from this table.", ""]
    if not posted:
        return lines + ["No posted criteria with a kind this month.", ""]
    lines += ["| Kind | Posted | Removed by QE | Removed % |", "|---|---|---|---|"]
    for kind in [k for k in KIND_ORDER if k in posted] + sorted(k for k in posted if k not in KIND_ORDER):
        lines.append(f"| {kind} | {posted[kind]} | {removed[kind]} | {round(100 * removed[kind] / posted[kind])}% |")
    sized = [r for r in records if r.get("outcome") == "CHANGED" and isinstance(r.get("posted_count"), int)]
    if sized:
        posted_counts = sorted(r["posted_count"] for r in sized)
        kept_counts = sorted(r.get("kept_count", 0) for r in sized)
        mid = len(sized) // 2
        lines += ["", f"Criteria per ticket QE edited ({len(sized)}): we posted a median of {posted_counts[mid]}, "
                      f"QE left a median of {kept_counts[mid]}."]
    return lines + [""]


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
                                                          "removed": [], "added": [], "promoted": [], "screens": []})
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
                    if entry["kind"] == "added":
                        for screen in missed_screens(entry["new"], record.get("posted_text") or ""):
                            if not any(k == record["key"] and s == screen for k, s, _ in bucket["screens"]):
                                bucket["screens"].append((record["key"], screen, entry["new"]))
    lines = [f"# UAC learning report {month}", "",
             f"{len(records)} ticket version(s) harvested. Accepted = kept unchanged; changed = wording or "
             "expected result edited; removed = QE deleted it (we wrote too much); added = QE wrote it (we missed it); promoted = QE moved one "
             "of our suggested checks into the criteria (older UACs only; the UAC no longer has suggested checks). "
             "Missed screens = screens (panel, console, dashboard, app, ...) that a QE-added criterion names and our "
             "posted UAC never mentioned, counted so a recurring screen miss shows up in the data before any rule changes.",
             ""]
    totals = {k: 0 for k in ("accepted", "changed", "removed", "added", "promoted", "missed_screens")}
    for component in sorted(by_component):
        b = by_component[component]
        screens = b["screens"]
        for kind in ("accepted", "changed"):
            totals[kind] += b[kind]
        totals["removed"] += len(b["removed"])
        totals["added"] += len(b["added"])
        totals["promoted"] += len(b["promoted"])
        totals["missed_screens"] += len(screens)
        lines += [f"## {component}", "",
                  f"- Tickets: {len(b['tickets'])}",
                  f"- Criteria accepted {b['accepted']}, changed {b['changed']}, removed {len(b['removed'])}, "
                  f"added {len(b['added'])}, promoted {len(b['promoted'])}, missed screens {len(screens)}", ""]
        if b["removed"]:
            lines += ["What we wrote that QE removed:", ""] + [f"- {k}: {t}" for k, t in b["removed"]] + [""]
        if b["added"]:
            lines += ["What QE added that we missed:", ""] + [f"- {k}: {t}" for k, t in b["added"]] + [""]
        if b["promoted"]:
            lines += ["Suggested checks QE moved into the criteria:", ""] + [f"- {k}: {t}" for k, t in b["promoted"]] + [""]
        if screens:
            lines += ["Missed screens (named by a QE-added criterion, never named in our UAC):", ""] + \
                [f"- {k}: {s} - {t}" for k, s, t in screens] + [""]
    if records:
        posted = totals["accepted"] + totals["changed"] + totals["removed"]
        lines[3:3] = [f"Overall: {posted} posted criteria - accepted {totals['accepted']}, changed {totals['changed']}, "
                      f"removed {totals['removed']}; QE added {totals['added']}"
                      + (f", promoted {totals['promoted']} suggested" if totals["promoted"] else "")
                      + f" (missed screens "
                      f"{totals['missed_screens']}).", ""]
    if not records:
        lines.append("No ticket versions were harvested this month.")
    lines += [""] + origin_report_lines(records)
    lines += [""] + kind_report_lines(records)
    firing = common.import_skill_module("gate_firing_log")
    runs = [r for r in firing.load([Path(config["output_dir"]) / "logs" / "gate-firing.jsonl"], tool="uac-runner")
            if str(r.get("at") or "").startswith(month)]
    lines += [""] + firing.report_lines(runs, "Runner checks this month")
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
    parser.add_argument("--backfill", nargs="+", metavar="KEY",
                        help="learn from these hand-posted tickets, reading the posted version from Jira history")
    parser.add_argument("--generator-user", action="append", default=[],
                        help="with --backfill: a Jira user whose field writes are the generated UAC (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="with --backfill: print the records, write nothing")
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
    if args.backfill:
        generators = generator_users(config, own_name, args.generator_user)
        records = backfill(config, jira, logger, generators, args.backfill, dry_run=args.dry_run)
        for record in records:
            print(f"{record['key']}: {record['outcome']} by {record['editor'] or '-'} {record['counts']}")
        return 0
    records = harvest(config, jira, logger, own_name)
    logger.info("harvested %d record(s)", len(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
