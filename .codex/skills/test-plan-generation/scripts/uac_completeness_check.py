"""Refuse a UAC whose evidence steps were skipped, even when every structural check passes.

WHY THIS EXISTS
---------------
Structural checks (AC format, source coverage, surfaces) pass on a UAC that never ran product RAG,
never searched Jira history, copied a parent ticket's criterion into a hotfix, or dropped a
documentation finding while rewriting. Those gaps are process gaps: each one is a step the author
skipped. This check makes every such step leave a record, and fails when the record is missing.

WHAT IT CHECKS in a UAC folder
------------------------------
1. DOC_RESEARCH.json exists: the UAC Doc Researcher ran.
2. UAC_EVIDENCE.json "preflight": product_rag, jira_history, live_jira and clones, each available,
   unavailable or not_applicable. "unavailable" needs a reason AND at least two attempted routes -
   a tool missing from the session is not an unavailable source while the backend JSON-RPC route
   (vm_evidence_call.py) was not tried. not_applicable needs a reason.
3. "rag_probes": when product_rag is available, at least three probes, each with the exact
   question and a result (ok, empty or error).
4. "history_attempts": when jira_history or live_jira is available, at least two attempts, each
   with source, exact query, result (ok, empty or unavailable) and count.
5. "doc_findings": every Doc Researcher finding that cites a documentation source (doc: ref) is
   dispositioned exactly once - AC (the listed Acceptance Criteria exist and their Source line
   names the documentation) or SET_ASIDE (with a concrete reason of at least five words). A rewrite
   that drops the documentation from a Source line fails here.
6. "scenario": the reporter's own steps or requested outcome (text copied from the ticket) and, for
   every Acceptance Criterion, the step it follows (CUSTOMER) - or ADJACENT with a TBD when it follows
   a scenario the reporter did not hit (for example one an investigator found). At least one criterion
   follows the reporter's scenario.
7. "failure_path": when the ticket describes a job, queue or batch, what happens to the item that
   fails, to the remaining items, and how the user learns which items failed - each an AC, a TBD or
   not applicable with a reason.
8. Hotfix or backport tickets (from jira-source.json): HOTFIX_SCOPE.json passes
   hotfix_scope_check.py.

Run it before a UAC is shown, posted or re-posted, and again after every rewrite.

Usage:
    python uac_completeness_check.py UAC_FOLDER

Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EVIDENCE_FILE = "UAC_EVIDENCE.json"
DOC_RESEARCH_FILE = "DOC_RESEARCH.json"
UAC_FILE = "UAC.md"
JIRA_SOURCE_FILE = "jira-source.json"
HOTFIX_SCOPE_FILE = "HOTFIX_SCOPE.json"
PREFLIGHT_SOURCES = ("product_rag", "jira_history", "live_jira", "clones")
PREFLIGHT_STATES = ("available", "unavailable", "not_applicable")
RAG_RESULTS = ("ok", "empty", "error")
HISTORY_RESULTS = ("ok", "empty", "unavailable")
MIN_RAG_PROBES = 3
MIN_HISTORY_ATTEMPTS = 2
DOC_MARKERS = ("experience league", "experienceleague", "helpx.adobe.com", "doc:")
EMPTY_REASONS = {"", "n/a", "na", "none", "tbd", "-", "not relevant", "not needed", "out of scope"}
_AC_BLOCK = re.compile(r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|\Z)", re.M | re.S)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _reason_ok(value) -> bool:
    text = str(value or "").strip()
    return text.lower() not in EMPTY_REASONS and len(text.split()) >= 3


def _ac_list(value) -> list[int]:
    values = value if isinstance(value, list) else [value]
    return [v for v in values if isinstance(v, int) and not isinstance(v, bool)]


def preflight_problems(preflight) -> list[str]:
    if not isinstance(preflight, dict):
        return ["preflight is missing: record product_rag, jira_history, live_jira and clones"]
    problems = []
    for source in PREFLIGHT_SOURCES:
        entry = preflight.get(source)
        if not isinstance(entry, dict) or entry.get("status") not in PREFLIGHT_STATES:
            problems.append(f"preflight.{source} needs status {', '.join(PREFLIGHT_STATES)}")
            continue
        if entry["status"] == "unavailable":
            routes = [r for r in entry.get("attempted_routes") or [] if str(r).strip()]
            if not _reason_ok(entry.get("reason")):
                problems.append(f"preflight.{source} is unavailable without a concrete reason")
            if len(routes) < 2:
                problems.append(f"preflight.{source} is unavailable after {len(routes)} route(s); a tool missing from "
                                "the session is not unavailable until the backend route (vm_evidence_call.py) is tried")
        elif entry["status"] == "not_applicable" and not _reason_ok(entry.get("reason")):
            problems.append(f"preflight.{source} is not_applicable without a concrete reason")
    return problems


def rag_problems(evidence: dict) -> list[str]:
    if (evidence.get("preflight") or {}).get("product_rag", {}).get("status") != "available":
        return []
    probes = [p for p in evidence.get("rag_probes") or [] if isinstance(p, dict)]
    problems = []
    if len(probes) < MIN_RAG_PROBES:
        problems.append(f"product RAG is available but {len(probes)} probe(s) were recorded; run at least "
                        f"{MIN_RAG_PROBES} focused ask_dita_expert probes")
    for number, probe in enumerate(probes, 1):
        if not str(probe.get("question") or "").strip() or probe.get("result") not in RAG_RESULTS:
            problems.append(f"rag_probes {number} needs the exact question and a result ({', '.join(RAG_RESULTS)})")
    return problems


def history_problems(evidence: dict) -> list[str]:
    preflight = evidence.get("preflight") or {}
    if all((preflight.get(s) or {}).get("status") != "available" for s in ("jira_history", "live_jira")):
        return []
    attempts = [a for a in evidence.get("history_attempts") or [] if isinstance(a, dict)]
    problems = []
    if len(attempts) < MIN_HISTORY_ATTEMPTS:
        problems.append(f"Jira history is reachable but {len(attempts)} attempt(s) were recorded; record at least "
                        f"{MIN_HISTORY_ATTEMPTS} narrow searches (exact error text, workflow, component)")
    for number, attempt in enumerate(attempts, 1):
        count = attempt.get("count")
        if (not str(attempt.get("source") or "").strip() or not str(attempt.get("query") or "").strip()
                or attempt.get("result") not in HISTORY_RESULTS
                or not isinstance(count, int) or isinstance(count, bool) or count < 0):
            problems.append(f"history_attempts {number} needs source, query, result "
                            f"({', '.join(HISTORY_RESULTS)}) and a non-negative count")
    return problems


def doc_finding_problems(evidence: dict, doc_research: dict, uac_text: str) -> list[str]:
    findings = [f for f in (doc_research or {}).get("findings") or [] if isinstance(f, dict)]
    documented = [i for i, f in enumerate(findings, 1)
                  if any(str(r).startswith("doc:") for r in f.get("source_refs") or [])]
    blocks = {int(n): body for n, body in _AC_BLOCK.findall(uac_text)}
    entries: dict[int, list[dict]] = {}
    for entry in evidence.get("doc_findings") or []:
        if isinstance(entry, dict) and isinstance(entry.get("finding"), int):
            entries.setdefault(entry["finding"], []).append(entry)
    problems = []
    for index in documented:
        found = entries.get(index) or []
        claim = str(findings[index - 1].get("claim") or "")[:70]
        if len(found) != 1:
            problems.append(f"documentation finding {index} (\"{claim}\") is dispositioned {len(found)} times; "
                            "use it in an Acceptance Criterion or set it aside with a reason, exactly once")
            continue
        entry = found[0]
        if entry.get("disposition") == "AC":
            acs = _ac_list(entry.get("ac"))
            if not acs:
                problems.append(f"documentation finding {index}: AC disposition needs the Acceptance Criteria numbers")
            for ac in acs:
                body = blocks.get(ac)
                if body is None:
                    problems.append(f"documentation finding {index}: Acceptance Criteria {ac:02d} does not exist")
                    continue
                source = re.search(r"Source:\**\s*(.+)", body)
                if not source or not any(m in source.group(1).lower() for m in DOC_MARKERS):
                    problems.append(f"documentation finding {index} is used by Acceptance Criteria {ac:02d}, but its "
                                    "Source line does not name the documentation")
        elif entry.get("disposition") == "SET_ASIDE":
            if len(str(entry.get("reason") or "").split()) < 5:
                problems.append(f"documentation finding {index} is set aside without a concrete reason")
        else:
            problems.append(f"documentation finding {index}: disposition must be AC or SET_ASIDE")
    for index in sorted(set(entries) - set(documented)):
        problems.append(f"doc_findings names finding {index}, which is not a documentation finding in "
                        f"{DOC_RESEARCH_FILE}")
    return problems


def evidence_problems(folder: Path) -> list[str]:
    """Checks 2-7: the evidence record the runner also enforces."""
    path = folder / EVIDENCE_FILE
    if not path.is_file():
        return [f"{EVIDENCE_FILE} was not written: record the evidence preflight, RAG probes, Jira history "
                "attempts and the disposition of every documentation finding"]
    try:
        evidence = _load(path)
    except ValueError as exc:
        return [f"{EVIDENCE_FILE} is not valid JSON: {exc}"]
    if not isinstance(evidence, dict):
        return [f"{EVIDENCE_FILE} must be a JSON object"]
    doc_path = folder / DOC_RESEARCH_FILE
    try:
        doc_research = _load(doc_path) if doc_path.is_file() else {}
    except ValueError:
        doc_research = {}
    uac = (folder / UAC_FILE).read_text(encoding="utf-8") if (folder / UAC_FILE).is_file() else ""
    source_path = folder / JIRA_SOURCE_FILE
    try:
        source = _load(source_path) if source_path.is_file() else None
    except ValueError:
        source = None
    return (preflight_problems(evidence.get("preflight")) + rag_problems(evidence) + history_problems(evidence)
            + doc_finding_problems(evidence, doc_research, uac) + scenario_problems(evidence, uac, source)
            + failure_path_problems(evidence, uac, source))


def check(folder: Path) -> list[str]:
    problems = []
    if not (folder / UAC_FILE).is_file():
        problems.append(f"{UAC_FILE} is missing")
    if not (folder / DOC_RESEARCH_FILE).is_file():
        problems.append(f"{DOC_RESEARCH_FILE} is missing: the UAC Doc Researcher did not run")
    problems += evidence_problems(folder)
    source_path = folder / JIRA_SOURCE_FILE
    if source_path.is_file():
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import hotfix_scope_check  # noqa: E402

        source = _load(source_path)
        if hotfix_scope_check.is_hotfix(source.get("summary") or "", source.get("description") or ""):
            scope_path = folder / HOTFIX_SCOPE_FILE
            if not scope_path.is_file():
                problems.append(f"{HOTFIX_SCOPE_FILE} is missing for a hotfix ticket")
            else:
                uac = (folder / UAC_FILE).read_text(encoding="utf-8") if (folder / UAC_FILE).is_file() else ""
                problems += [f"hotfix scope: {p}" for p in hotfix_scope_check.check(_load(scope_path), uac)]
    else:
        problems.append(f"{JIRA_SOURCE_FILE} is missing: save the live ticket text so hotfix scope can be checked")
    return problems


# --- customer scenario ---------------------------------------------------------------------------------
SCENARIO_KINDS = ("CUSTOMER", "ADJACENT")
_NORMALIZE = re.compile(r"[*_{}|`\"'‘’“”]")


def _normalize(text) -> str:
    return " ".join(_NORMALIZE.sub(" ", str(text or "").lower()).split()).strip(" .,:;!?-")


def _ticket_text(source: dict) -> str:
    parts = [source.get("summary") or "", source.get("description") or ""]
    parts += [c.get("body") or "" for c in source.get("comments") or [] if isinstance(c, dict)]
    return _normalize("\n".join(parts))


def scenario_problems(evidence: dict, uac_text: str, source: dict | None) -> list[str]:
    """Every Acceptance Criterion follows the reporter's own scenario, or is marked ADJACENT and asks a TBD.

    An investigator's comment often finds a different scenario from the one the reporter hit (for example
    a deleted project when the reporter's job completed). Criteria built on that other scenario must not
    become the core contract silently."""
    scenario = evidence.get("scenario")
    if not isinstance(scenario, dict):
        return ["scenario is missing: copy the reporter's own steps or requested outcome into "
                "scenario.customer_steps and say for every Acceptance Criterion which step it follows"]
    steps = [_normalize(s) for s in scenario.get("customer_steps") or [] if str(s).strip()]
    problems = []
    if not steps:
        problems.append("scenario.customer_steps is empty: copy the reporter's own steps or requested outcome")
    if source:
        ticket = _ticket_text(source)
        for step in steps:
            if step not in ticket:
                problems.append(f"scenario step \"{step[:60]}\" is not text from the ticket")
    blocks = {int(n): body for n, body in _AC_BLOCK.findall(uac_text)}
    entries = {e["ac"]: e for e in scenario.get("acs") or [] if isinstance(e, dict) and isinstance(e.get("ac"), int)}
    customer_acs = 0
    for ac in sorted(blocks):
        entry = entries.get(ac)
        if entry is None:
            problems.append(f"Acceptance Criteria {ac:02d}: say in scenario.acs which customer step it follows")
            continue
        kind = entry.get("scenario")
        if kind == "CUSTOMER":
            customer_acs += 1
            if _normalize(entry.get("step")) not in steps:
                problems.append(f"Acceptance Criteria {ac:02d}: its step is not one of scenario.customer_steps")
        elif kind == "ADJACENT":
            if "TBD:" not in blocks[ac]:
                problems.append(f"Acceptance Criteria {ac:02d} follows a scenario the reporter did not hit; add a TBD "
                                "asking whether it belongs in this ticket, or move it to its own ticket")
        else:
            problems.append(f"Acceptance Criteria {ac:02d}: scenario must be {' or '.join(SCENARIO_KINDS)}")
    if blocks and customer_acs == 0:
        problems.append("no Acceptance Criterion follows the reporter's own scenario")
    return problems


# --- batch and queue failure path ----------------------------------------------------------------------
BATCH_SIGNAL = re.compile(
    r"\b(?:job|jobs|queue|queued|batch|batches|bulk)\b|\b\d[\d,]*\s+(?:files|assets|topics|items|articles|pages)\b",
    re.IGNORECASE)
FAILURE_DIMENSIONS = ("failing_item_outcome", "remaining_items", "user_notice")
FAILURE_DISPOSITIONS = ("AC", "TBD", "NOT_APPLICABLE")


def is_batch(source: dict | None) -> bool:
    return bool(source) and bool(BATCH_SIGNAL.search(_ticket_text(source)))


def failure_path_problems(evidence: dict, uac_text: str, source: dict | None) -> list[str]:
    """A job that processes many items must say what happens when one item fails.

    Dimensions: the failing item's own outcome (status it ends in), the remaining items (the job continues
    or stops), and how the user learns which items failed. Each is covered by an Acceptance Criterion,
    asked in a TBD, or not applicable with a reason."""
    if not is_batch(source):
        return []
    block = evidence.get("failure_path")
    if not isinstance(block, dict):
        return ["the ticket describes a job, queue or batch, so failure_path must say what happens to the item that "
                "fails, to the remaining items, and how the user learns which items failed"]
    blocks = {int(n): body for n, body in _AC_BLOCK.findall(uac_text)}
    problems = []
    for dimension in FAILURE_DIMENSIONS:
        entry = block.get(dimension)
        if not isinstance(entry, dict) or entry.get("disposition") not in FAILURE_DISPOSITIONS:
            problems.append(f"failure_path.{dimension} needs disposition {', '.join(FAILURE_DISPOSITIONS)}")
            continue
        disposition = entry["disposition"]
        if disposition == "NOT_APPLICABLE":
            if len(str(entry.get("reason") or "").split()) < 5:
                problems.append(f"failure_path.{dimension} is not applicable without a concrete reason")
            continue
        ac = entry.get("ac")
        if not isinstance(ac, int) or ac not in blocks:
            problems.append(f"failure_path.{dimension}: Acceptance Criteria {ac!r} does not exist")
        elif disposition == "TBD" and "TBD:" not in blocks[ac]:
            problems.append(f"failure_path.{dimension}: Acceptance Criteria {ac:02d} has no TBD line")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__)
        return 2
    problems = check(Path(args[0]))
    for problem in problems:
        print(f"FAIL: {problem}")
    print("PASS: every evidence step left a record" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
