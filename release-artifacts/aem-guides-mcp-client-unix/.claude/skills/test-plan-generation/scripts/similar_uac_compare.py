"""Find the human UACs of the most similar resolved tickets and list their dimensions for comparison.

WHY THIS EXISTS
---------------
Hundreds of human-approved UACs sit in the Acceptance Criteria field of resolved tickets, but a new UAC
is written without looking at them. This script brings the closest ones into every generation: it finds
up to three similar resolved tickets (same component first), reads their human UAC, and lists the
dimensions that UAC covers - the screens it names and the kinds of check it makes (negative cases,
configuration states, output presets, permissions, a failing item in a batch, and so on).

The author then says, for every listed dimension, whether the new UAC covers it (AC), asks it (TBD), or
why it does not apply (NOT_APPLICABLE with a reason). uac_completeness_check.py fails a UAC whose
"similar_uacs" record is missing or has a dimension without that answer. A similar human UAC is a
checklist, never acceptance authority: nothing is copied into the new UAC without its own evidence.

A ticket is similar only when it shares at least MIN_SIMILARITY of the current ticket's key terms (taken
from the summary first, without URLs, ids or code blocks). When nothing qualifies the record says
"none_found" with the queries tried - an honest empty result beats comparing against unrelated UACs.

SOURCES
-------
  live Jira (default), read-only: resolved tickets with a non-empty Acceptance Criteria field, same
      component first, whose text matches the key terms; machine-posted UACs (labels in --exclude-label)
      and the ticket itself are skipped.
  --corpus FILE: an offline JSONL corpus with key, summary, description, component, human_ac.

Usage:
    python similar_uac_compare.py --ticket-source jira-source.json --key PROJ-1 --component Publishing \\
        --evidence UAC_EVIDENCE.json [--env-file .env] [--corpus corpus.jsonl] [--top 3]

Jira settings: JIRA_BASE_URL (or JIRA_URL), JIRA_PAT (or JIRA_BEARER_TOKEN), JIRA_SSL_VERIFY. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

DEFAULT_TOP = 3
MIN_SIMILARITY = 0.3
COMPONENT_BONUS = 0.1
MIN_UAC_CHARS = 150
# Acceptance Criteria fields that record a decision instead of a UAC.
NOT_A_UAC = re.compile(r"\b(not\s+reproducible|cannot\s+reproduce|uac\s+not\s+required|not\s+applicable|"
                       r"working\s+as\s+(?:designed|expected)|duplicate\s+of)\b", re.I)


def is_real_uac(text: str) -> bool:
    return len((text or "").strip()) >= MIN_UAC_CHARS and not NOT_A_UAC.search((text or "")[:300])
DEFAULT_EXCLUDE_LABELS = ("Needs_Human_Review", "QEVision_UAC_DONE", "UAC_Draft")
RESOLVED_STATUSES = ("UAT", "Closed", "Resolved", "Done")
STOP = set("""the a an and or of to in on for with that this is are be as by it its from at when then should shall
must will can not no any all into after before while via using used use user users able also only such same
other new old one two where which what who how does did done get gets make makes set sets show shows
verify issue ticket customer guides aem adobe experience manager please need needs want wants like still
see seen unable even just than more most some very break sla hotfix on-prem cloud only private files file
remain remains progress completed complete working work works fails failing failed getting prod stage
environment content issue issues problem able expected actual observed steps reproduce step result
add adds added adding allow allows allowed""".split())
_NOISE = re.compile(r"https?://\S+|\[[^\]|]*\|[^\]]*\]|\{\{[^}]*\}\}|\{code[^}]*\}.*?\{code\}|"
                    r"\{noformat\}.*?\{noformat\}", re.S)

DIMENSIONS: dict[str, re.Pattern] = {
    "negative or error case": re.compile(r"\b(invalid|error|should\s+not|must\s+not|empty|missing|fallback|broken|"
                                         r"not\s+(?:shown|allowed|saved|displayed))\b", re.I),
    "configuration or state on/off": re.compile(r"\b(enabled?|disabled?|on\s+and\s+off|toggle|feature\s+flag|"
                                                r"setting|configuration|config)\b", re.I),
    "output presets": re.compile(r"\b(native\s+pdf|dita-?ot|html5|aem\s+sites?|output\s+preset|knowledge\s+base)\b", re.I),
    "topic types": re.compile(r"\b(concept|reference|task|glossary|bookmap)\b", re.I),
    "existing behaviour unchanged": re.compile(r"\b(regression|unchanged|still\s+works?|not\s+affected|existing\s+"
                                               r"behaviou?r|as\s+(?:before|today))\b", re.I),
    "scale or performance": re.compile(r"\b(performance|large|\d{3,}\s*(?:topics?|maps?|files?|assets?)|timeout|slow|"
                                       r"bulk)\b", re.I),
    "permissions or role": re.compile(r"\b(permissions?|roles?|acl|access\s+(?:control|rights?)|no\s+access|"
                                      r"administrators?|admin\s+users?|reviewer|publisher|unauthori[sz]ed)\b", re.I),
    "upgrade or migration": re.compile(r"\b(upgrade|migrat\w*|backward\s+compat\w*|older\s+version)\b", re.I),
    "translation or language": re.compile(r"\b(translation|translated|language|locale|xliff)\b", re.I),
    "saved and reloaded": re.compile(r"\b(reload\w*|refresh(?:es|ing)?\s+the\s+page|after\s+(?:a\s+)?refresh|"
                                     r"reopen\w*|persist\w*|after\s+sav\w+|survives?)\b", re.I),
    "old and new editor": re.compile(r"\b(new\s+editor|old\s+editor|web\s+editor|both\s+editors|legacy\s+editor)\b", re.I),
    "one item fails in a batch": re.compile(r"\b(remaining|rest\s+of\s+the|other)\s+(assets?|files?|topics?|articles?|"
                                            r"items?|maps?|jobs?)\b|\bdoes\s+not\s+(fail|stop|block|halt)\s+the\s+"
                                            r"(whole|entire|rest)", re.I),
}
SCREEN = re.compile(r"\b([a-z][\w-]*)\s+(panel|console|dashboard|dialog|app|view|tab|page|editor|toolbar|menu|"
                    r"preview|widget|screen|inbox)\b", re.I)
NOT_A_NAME = {"the", "a", "an", "this", "that", "each", "every", "same", "in", "on", "of", "to", "and", "or", "new",
              "old", "both", "with", "when", "from", "for", "by", "as", "is", "are", "into", "its", "their", "your",
              "our", "any", "which", "where", "while", "then", "via"}


def _words(text: str) -> list[str]:
    text = _NOISE.sub(" ", text or "")
    return [w for w in re.findall(r"[a-z][a-z0-9-]{2,}", text.lower())
            if w not in STOP and not any(c.isdigit() for c in w)]


def key_terms(summary: str, description: str, limit: int = 8) -> list[str]:
    """Distinctive words, the summary's first: the summary names the feature, the description adds noise."""
    ordered = [w for w, _ in Counter(_words(summary)).most_common()]
    ordered += [w for w, _ in Counter(_words(description)).most_common() if w not in ordered]
    return ordered[:limit]


def similarity(terms: list[str], other_text: str) -> float:
    other = set(_words(other_text))
    return len(set(terms) & other) / max(1, len(terms))


def dimensions_of(human_ac: str) -> list[str]:
    found = [name for name, rx in DIMENSIONS.items() if rx.search(human_ac or "")]
    screens: list[str] = []
    for word, kind in SCREEN.findall(human_ac or ""):
        phrase = f"screen: {word.lower()} {kind.lower()}"
        if word.lower() not in NOT_A_NAME and phrase not in screens:
            screens.append(phrase)
    return found + screens[:6]


def from_corpus(path: Path, terms: list[str], key: str, component: str, top: int) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    scored = []
    for row in rows:
        if row.get("key") == key or not is_real_uac(row.get("human_ac") or ""):
            continue
        comps = row.get("component") or []
        comps = comps if isinstance(comps, list) else [comps]
        score = similarity(terms, f"{row.get('summary') or ''} {row.get('description') or ''}")
        if score >= MIN_SIMILARITY:
            scored.append((score + (COMPONENT_BONUS if component and component in comps else 0), row))
    scored.sort(key=lambda s: -s[0])
    return [{"key": r.get("key"), "summary": r.get("summary") or "", "score": round(s, 3), "human_ac": r["human_ac"]}
            for s, r in scored[:top]]


class Jira:
    def __init__(self) -> None:
        self.base = (os.getenv("JIRA_BASE_URL") or os.getenv("JIRA_URL") or "").rstrip("/")
        self.token = os.getenv("JIRA_PAT") or os.getenv("JIRA_BEARER_TOKEN") or ""
        if not self.base or not self.token:
            raise RuntimeError("JIRA_BASE_URL and JIRA_PAT must be set")
        self.ctx = None
        if os.getenv("JIRA_SSL_VERIFY", "true").strip().lower() in {"false", "0", "no"}:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def get(self, path: str):
        req = urllib.request.Request(self.base + path, headers={"Authorization": f"Bearer {self.token}",
                                                               "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60, context=self.ctx) as resp:
            return json.loads(resp.read())


def from_jira(jira, terms: list[str], key: str, component: str, top: int,
              exclude_labels: tuple[str, ...]) -> tuple[list[dict], list[str]]:
    ac_field = next((f["id"] for f in jira.get("/rest/api/2/field") if f.get("name") == "Acceptance Criteria"), None)
    if not ac_field:
        raise RuntimeError("no Acceptance Criteria field in this Jira")
    project = key.split("-")[0] if "-" in key else ""
    queries: list[str] = []
    rows: dict[str, dict] = {}
    passes = [(3, True), (2, True)] if component else []
    for n_terms, use_component in passes + [(3, False), (2, False)]:
        if len(terms) < n_terms or (not use_component and component and rows):
            continue  # search outside the component only when the component gave nothing
        if len(rows) >= top:
            break
        clauses = [f'project = "{project}"'] if project else []
        clauses += ['"Acceptance Criteria" is not EMPTY', f'status in ({", ".join(RESOLVED_STATUSES)})',
                    f'key != "{key}"', f'text ~ "{" ".join(terms[:n_terms])}"']
        if use_component:
            clauses.append(f'component = "{component}"')
        if exclude_labels:
            clauses.append(f'(labels is EMPTY OR labels not in ({", ".join(exclude_labels)}))')
        jql = " AND ".join(clauses)
        queries.append(jql)
        result = jira.get("/rest/api/2/search?maxResults=20&fields=summary,description," + ac_field
                          + "&jql=" + urllib.parse.quote(jql))
        for issue in result.get("issues", []):
            fields = issue.get("fields") or {}
            ac = fields.get(ac_field) or ""
            if not is_real_uac(ac) or issue["key"] in rows:
                continue
            score = similarity(terms, f"{fields.get('summary') or ''} {fields.get('description') or ''}")
            if score >= MIN_SIMILARITY:
                rows[issue["key"]] = {"key": issue["key"], "summary": fields.get("summary") or "",
                                      "score": round(score + (COMPONENT_BONUS if use_component else 0), 3),
                                      "human_ac": ac}
    return sorted(rows.values(), key=lambda r: -r["score"])[:top], queries


def build_record(similar: list[dict], queries: list[str], source: str, terms: list[str]) -> dict:
    record = {"source": source, "key_terms": terms, "queries": queries}
    if not similar:
        return {"status": "none_found", **record, "uacs": []}
    return {"status": "compared", **record,
            "uacs": [{"key": s["key"], "summary": s["summary"], "score": s["score"],
                      "dimensions": [{"dimension": d, "disposition": "", "ac": None, "reason": ""}
                                     for d in dimensions_of(s["human_ac"])]} for s in similar]}


def load_env_file(path: Path | None) -> None:
    if not path or not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticket-source", type=Path, required=True, help="jira-source.json of the current ticket")
    parser.add_argument("--key", required=True)
    parser.add_argument("--component", default="")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--corpus", type=Path, help="offline corpus instead of live Jira")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--exclude-label", action="append", default=list(DEFAULT_EXCLUDE_LABELS))
    args = parser.parse_args(argv)
    source = json.loads(args.ticket_source.read_text(encoding="utf-8-sig"))
    terms = key_terms(source.get("summary") or "", source.get("description") or "")
    evidence = json.loads(args.evidence.read_text(encoding="utf-8-sig")) if args.evidence.is_file() else {}
    try:
        if args.corpus:
            similar = from_corpus(args.corpus, terms, args.key, args.component, args.top)
            evidence["similar_uacs"] = build_record(similar, [f"corpus {args.corpus.name}"], "corpus", terms)
        else:
            load_env_file(args.env_file)
            similar, queries = from_jira(Jira(), terms, args.key, args.component, args.top,
                                         tuple(dict.fromkeys(args.exclude_label)))
            evidence["similar_uacs"] = build_record(similar, queries, "jira", terms)
    except Exception as exc:  # noqa: BLE001 - record the failure, never hide it
        evidence["similar_uacs"] = {"status": "unavailable", "key_terms": terms,
                                    "reason": f"{type(exc).__name__}: {str(exc)[:200]}",
                                    "attempted_routes": ["corpus" if args.corpus else "live Jira"], "uacs": []}
    args.evidence.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    record = evidence["similar_uacs"]
    print(f"similar_uacs: {record['status']} (key terms: {', '.join(terms)})")
    for uac in record.get("uacs", []):
        print(f"  {uac['key']} ({uac['score']}) {uac['summary'][:80]}")
        for dimension in uac["dimensions"]:
            print(f"    - {dimension['dimension']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
