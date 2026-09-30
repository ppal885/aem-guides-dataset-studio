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
   names the documentation), SUGGESTED (the listed suggested check exists) or SET_ASIDE (with a
   concrete reason of at least five words). A rewrite
   that drops the documentation from a Source line fails here.
6. "scenario": the reporter's own steps or requested outcome (text copied from the ticket) and, for
   every Acceptance Criterion, the step it follows (CUSTOMER), the step it guards as a QE regression or
   edge-case check (REGRESSION, no TBD needed). A check that follows a scenario the reporter did not
   hit (ADJACENT, for example one an investigator found) is a suggested check, never a criterion. At
   least one criterion follows the reporter's scenario.
7. "failure_path": when the ticket says that items inside a job, queue or batch fail, get stuck or
   are left unprocessed, what happens to the item that fails, to the remaining items, and how the user
   learns which items failed - each an AC, a TBD or not applicable with a reason. A batch ticket that
   reports no item failure needs no failure_path (in the human UAC corpus, 43% of item-failure batch
   tickets covered it, against 9% of other batch tickets).
8. "similar_uacs" (written by similar_uac_compare.py): the human UACs of the most similar resolved
   tickets and the dimensions each covers. "compared" needs every dimension answered - AC (an existing
   Acceptance Criterion covers it), TBD (that criterion asks it) or NOT_APPLICABLE with a reason;
   "none_found" needs the queries tried; "unavailable" needs the reason.
9. Hotfix or backport tickets (from jira-source.json): HOTFIX_SCOPE.json passes
   hotfix_scope_check.py.
10. "fix_basis": whether the root cause or fix is known. CONFIRMED needs the ticket text that says it.
   UNCONFIRMED is fine - many tickets never get a root-cause comment or a linked pull request - but
   then UAC.md starts with a "Note:" line saying the root cause is not confirmed yet, and no Acceptance
   Criterion other than a REGRESSION check rests only on code. When the ticket does report a root cause
   or fix, UNCONFIRMED needs a reason why that text is not the fix.
11. "Suggested checks (QE decide):": checks found only by our own research (documentation, code, a
   similar or parent ticket, an investigator's other scenario) go below the Acceptance Criteria as
   "- Suggested check NN:" lines, each with a Source line and a "Why suggested:" line, at most three.
   They are not posted as Acceptance Criteria: QE moves the ones they want into the criteria. A
   criterion that follows a scenario the reporter did not hit (ADJACENT) must be a suggested check.
12. Size: the delivered criteria (with their sub-points, the Scope line and the Out of scope list, but not
   the Source, TBD or Note lines) stay within MAX_BODY_WORDS, and each Source line within MAX_SOURCE_WORDS.
   In the 386 human UACs of the corpus the median is 122 words and 90% are under 337; blind comparisons
   showed ours 4 to 15 times longer, mostly from long Source lines and extra sub-points. File paths and line
   numbers belong in the full test plan record.
13. "pre_existing_items": what happens to items made before the change - content, maps, presets,
   output, settings or projects created or generated earlier - an AC, a TBD or NOT_APPLICABLE with a reason.
   15% of human UACs cover it ("older files need re-processing", "old preset and newly created preset"),
   and blind comparisons missed it on tickets that never say "upgrade" or "migration".

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
_AC_BLOCK = re.compile(r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|^Suggested checks\b|^Out of scope\b|\Z)",
                       re.M | re.S)
SUGGESTED_HEADER = "Suggested checks (QE decide):"
_SUGGESTED_HEADER = re.compile(r"^Suggested checks\b.*$", re.M)
_SUGGESTED_BLOCK = re.compile(r"^- Suggested check (\d+):(.*?)(?=^- Suggested check \d+:|\Z)", re.M | re.S)
MAX_SUGGESTED = 3
MAX_BODY_WORDS = 350
MAX_SOURCE_WORDS = 30
PRE_EXISTING_DISPOSITIONS = ("AC", "TBD", "NOT_APPLICABLE")


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
        elif entry.get("disposition") == "SUGGESTED":
            problems += _suggested_ref_problems(f"documentation finding {index}", entry, uac_text)
        else:
            problems.append(f"documentation finding {index}: disposition must be AC, SUGGESTED or SET_ASIDE")
    for index in sorted(set(entries) - set(documented)):
        problems.append(f"doc_findings names finding {index}, which is not a documentation finding in "
                        f"{DOC_RESEARCH_FILE}")
    return problems


def evidence_problems_by_check(folder: Path) -> dict[str, list[str]]:
    """The evidence-record problems by check name (for the gate firing log); "record" when it is missing."""
    path = folder / EVIDENCE_FILE
    if not path.is_file():
        return {"record": [f"{EVIDENCE_FILE} was not written: record the evidence preflight, RAG probes, Jira history "
                           "attempts and the disposition of every documentation finding"]}
    try:
        evidence = _load(path)
    except ValueError as exc:
        return {"record": [f"{EVIDENCE_FILE} is not valid JSON: {exc}"]}
    if not isinstance(evidence, dict):
        return {"record": [f"{EVIDENCE_FILE} must be a JSON object"]}
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
    return {
        "preflight": preflight_problems(evidence.get("preflight")), "rag_probes": rag_problems(evidence),
        "history_attempts": history_problems(evidence),
        "doc_findings": doc_finding_problems(evidence, doc_research, uac),
        "scenario": scenario_problems(evidence, uac, source), "failure_path": failure_path_problems(evidence, uac, source),
        "similar_uacs": similar_uac_problems(evidence, uac), "suggested_checks": suggested_problems(uac),
        "fix_basis": fix_basis_problems(evidence, uac, source),
        "size": size_problems(uac), "pre_existing_items": pre_existing_problems(evidence, uac),
    }


def evidence_problems(folder: Path) -> list[str]:
    """Checks 2-8 and 10-13: the evidence record the runner also enforces."""
    problems: list[str] = []
    for found in evidence_problems_by_check(folder).values():
        problems += found
    return problems


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
SCENARIO_KINDS = ("CUSTOMER", "REGRESSION", "ADJACENT")
_NORMALIZE = re.compile(r"[*_{}|`\"'‘’“”]")


def _normalize(text) -> str:
    return " ".join(_NORMALIZE.sub(" ", str(text or "").lower()).split()).strip(" .,:;!?-")


def _ticket_text(source: dict) -> str:
    parts = [source.get("summary") or "", source.get("description") or ""]
    parts += [c.get("body") or "" for c in source.get("comments") or [] if isinstance(c, dict)]
    return _normalize("\n".join(parts))


def scenario_problems(evidence: dict, uac_text: str, source: dict | None) -> list[str]:
    """Every Acceptance Criterion follows the reporter's own scenario (CUSTOMER) or guards it (REGRESSION).

    An investigator's comment often finds a different scenario from the one the reporter hit (for example
    a deleted project when the reporter's job completed). A criterion built on that other scenario is
    ADJACENT: it must not become the core contract, so it goes to the suggested checks for QE to decide."""
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
        if kind in ("CUSTOMER", "REGRESSION"):
            customer_acs += kind == "CUSTOMER"
            if _normalize(entry.get("step")) not in steps:
                problems.append(f"Acceptance Criteria {ac:02d}: its step is not one of scenario.customer_steps")
        elif kind == "ADJACENT":
            problems.append(f"Acceptance Criteria {ac:02d} follows a scenario the reporter did not hit; move it to "
                            f"\"{SUGGESTED_HEADER}\" so QE decides whether it belongs in this ticket")
        else:
            problems.append(f"Acceptance Criteria {ac:02d}: scenario must be {', '.join(SCENARIO_KINDS)}")
    if blocks and customer_acs == 0:
        problems.append("no Acceptance Criterion follows the reporter's own scenario")
    return problems


# --- batch and queue failure path ----------------------------------------------------------------------
BATCH_SIGNAL = re.compile(
    r"\b(?:job|jobs|queue|queued|batch|batches|bulk)\b|\b\d[\d,]*\s+(?:files|assets|topics|items|articles|pages)\b",
    re.IGNORECASE)
# The ticket's own text reports items failing, stuck or left unprocessed inside the job.
ITEM_FAILURE_SIGNAL = re.compile(
    r"\b(?:one|a single|some|few|several|remaining|other|rest of the|\d[\d,]*)\s+(?:of the\s+)?"
    r"(?:files?|assets?|topics?|items?|articles?|pages?|maps?)\b[^.\n]{0,80}\b(?:fail\w*|stuck|error\w*|"
    r"not (?:processed|published|translated|generated)|skipped|remain\w*|missing|block\w*|halt\w*)"
    r"|\b(?:fail\w*|error|stuck|halt\w*|abort\w*)\b[^.\n]{0,60}\b(?:remaining|rest of the|other|whole|entire|all)"
    r"\s+(?:files?|assets?|topics?|items?|articles?|pages?|job|batch|queue)", re.IGNORECASE)
FAILURE_DIMENSIONS = ("failing_item_outcome", "remaining_items", "user_notice")
FAILURE_DISPOSITIONS = ("AC", "TBD", "NOT_APPLICABLE")


def is_batch(source: dict | None) -> bool:
    return bool(source) and bool(BATCH_SIGNAL.search(_ticket_text(source)))


def is_item_failure_batch(source: dict | None) -> bool:
    """A batch ticket whose own text says items fail, get stuck or are left unprocessed."""
    return is_batch(source) and bool(ITEM_FAILURE_SIGNAL.search(_ticket_text(source)))


def failure_path_problems(evidence: dict, uac_text: str, source: dict | None) -> list[str]:
    """A job whose items fail must say what happens to the failing item and to the rest.

    Dimensions: the failing item's own outcome (status it ends in), the remaining items (the job continues
    or stops), and how the user learns which items failed. Each is covered by an Acceptance Criterion,
    asked in a TBD, or not applicable with a reason."""
    if not is_item_failure_batch(source):
        return []
    block = evidence.get("failure_path")
    if not isinstance(block, dict):
        return ["the ticket says items inside a job, queue or batch fail or get stuck, so failure_path must say what "
                "happens to the item that fails, to the remaining items, and how the user learns which items failed"]
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


# --- similar human UACs ---------------------------------------------------------------------------------
SIMILAR_STATES = ("compared", "none_found", "unavailable")
SIMILAR_DISPOSITIONS = ("AC", "TBD", "SUGGESTED", "NOT_APPLICABLE")


def similar_uac_problems(evidence: dict, uac_text: str) -> list[str]:
    """Every dimension of the most similar human UACs is covered, asked or set aside with a reason."""
    block = evidence.get("similar_uacs")
    if not isinstance(block, dict):
        return ["similar_uacs is missing: run similar_uac_compare.py and answer every dimension of the similar "
                "human UACs (AC, TBD or NOT_APPLICABLE with a reason)"]
    status = block.get("status")
    if status not in SIMILAR_STATES:
        return [f"similar_uacs.status must be {', '.join(SIMILAR_STATES)}"]
    if status == "none_found":
        return [] if block.get("queries") else ["similar_uacs is none_found without the queries tried"]
    if status == "unavailable":
        return [] if _reason_ok(block.get("reason")) else ["similar_uacs is unavailable without a concrete reason"]
    blocks = {int(n): body for n, body in _AC_BLOCK.findall(uac_text)}
    uacs = [u for u in block.get("uacs") or [] if isinstance(u, dict)]
    problems = [] if uacs else ["similar_uacs is compared but lists no similar UAC"]
    for uac in uacs:
        for entry in uac.get("dimensions") or []:
            name = f"similar UAC {uac.get('key')}: \"{entry.get('dimension')}\""
            disposition = entry.get("disposition")
            if disposition not in SIMILAR_DISPOSITIONS:
                problems.append(f"{name} has no answer; say AC, TBD, SUGGESTED or NOT_APPLICABLE")
            elif disposition == "NOT_APPLICABLE":
                if len(str(entry.get("reason") or "").split()) < 5:
                    problems.append(f"{name} is not applicable without a concrete reason")
            elif disposition == "SUGGESTED":
                problems += _suggested_ref_problems(name, entry, uac_text)
            else:
                ac = entry.get("ac")
                if not isinstance(ac, int) or ac not in blocks:
                    problems.append(f"{name}: Acceptance Criteria {ac!r} does not exist")
                elif disposition == "TBD" and "TBD:" not in blocks[ac]:
                    problems.append(f"{name}: Acceptance Criteria {ac:02d} has no TBD line")
    return problems


# --- suggested checks ----------------------------------------------------------------------------------
def suggested_blocks(uac_text: str) -> dict[int, str]:
    """The "- Suggested check NN:" blocks below the "Suggested checks" heading."""
    header = _SUGGESTED_HEADER.search(uac_text or "")
    if not header:
        return {}
    return {int(n): body for n, body in _SUGGESTED_BLOCK.findall(uac_text[header.end():])}


def _suggested_ref_problems(name: str, entry: dict, uac_text: str) -> list[str]:
    number = entry.get("suggested")
    if not isinstance(number, int) or isinstance(number, bool) or number not in suggested_blocks(uac_text):
        return [f"{name}: Suggested check {number!r} does not exist"]
    return []


def suggested_problems(uac_text: str) -> list[str]:
    """Suggested checks sit below every Acceptance Criterion, each with its source and why it is suggested."""
    text = uac_text or ""
    header = _SUGGESTED_HEADER.search(text)
    if not header:
        if re.search(r"^- Suggested check \d+:", text, re.M):
            return [f"suggested checks need the heading \"{SUGGESTED_HEADER}\" above them"]
        return []
    problems = []
    if re.search(r"^- Acceptance Criteria \d+:", text[header.end():], re.M):
        problems.append(f"every Acceptance Criterion must come before \"{SUGGESTED_HEADER}\"")
    if re.search(r"^Out of scope\b", text[header.end():], re.M | re.I):
        problems.append(f"the Out of scope list belongs above \"{SUGGESTED_HEADER}\", right after the criteria")
    blocks = suggested_blocks(text)
    if not blocks:
        problems.append(f"\"{SUGGESTED_HEADER}\" has no \"- Suggested check NN:\" line; remove the heading")
    if len(blocks) > MAX_SUGGESTED:
        problems.append(f"{len(blocks)} suggested checks; keep the {MAX_SUGGESTED} that matter most - QE reads "
                        "every one")
    for number, body in sorted(blocks.items()):
        if not re.search(r"Source:\**\s*\S", body):
            problems.append(f"Suggested check {number:02d} has no Source line")
        why = re.search(r"Why suggested:\**\s*(.+)", body)
        if not why or len(why.group(1).split()) < 5:
            problems.append(f"Suggested check {number:02d} needs a \"Why suggested:\" line saying what it guards "
                            "and why it is not an Acceptance Criterion")
    return problems


# --- root cause or fix known ---------------------------------------------------------------------------
# Ticket text that reports a root cause, a fix or a pull request. The VM staleness watcher uses it too.
FIX_SIGNAL = re.compile(
    r"\broot[\s-]*cause\b|\bRCA\b|\bcaused by\b|\bfix(?:ed)? in\b|\bthe fix\b|/pull/\d+|\bpull request\b"
    r"|\bPR\s*#?\d+|\bmerged\b|\bcherry[\s-]*pick", re.IGNORECASE)
FIX_STATES = ("CONFIRMED", "UNCONFIRMED")
UNCONFIRMED_NOTE = ("Note: The root cause and the fix are not confirmed yet. These criteria cover what the customer "
                    "reported and will be checked again when the fix is known.")
_CODE_SOURCE = re.compile(
    r"\b[\w./-]+\.(?:java|jsx?|tsx?|py|xslt?|scss|css|html?|groovy|kt|jsp)\b|\bcommit\s+[0-9a-f]{7,}\b|/pull/\d+",
    re.IGNORECASE)
_NON_CODE_SOURCE = ("jira", "ticket", "description", "comment", "attachment", "screenshot", "customer", "reporter",
                    "experience league", "experienceleague", "doc:", "product decision")


def fix_signals(source: dict | None) -> list[str]:
    """Sentences of the ticket description and comments that report a root cause, a fix or a pull request."""
    if not source:
        return []
    texts = [source.get("description") or ""] + [c.get("body") or "" for c in source.get("comments") or []
                                                 if isinstance(c, dict)]
    found: list[str] = []
    for text in texts:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            if FIX_SIGNAL.search(sentence) and sentence.strip() not in found:
                found.append(sentence.strip())
    return found


def _code_only(body: str) -> bool:
    source = re.search(r"Source:\**\s*(.+)", body)
    text = (source.group(1) if source else "").lower()
    return bool(_CODE_SOURCE.search(text)) and not any(marker in text for marker in _NON_CODE_SOURCE)


def fix_basis_problems(evidence: dict, uac_text: str, source: dict | None) -> list[str]:
    """Say whether the root cause or fix is known and, when it is not, keep guesses out of the criteria.

    Posting is never blocked for want of a root cause: many tickets never get one. A UAC written without
    it says so at the top, and a criterion that rests only on code (a guess at the mechanism) becomes a
    suggested check. A REGRESSION check around the reporter's scenario may still cite code."""
    block = evidence.get("fix_basis")
    if not isinstance(block, dict) or block.get("status") not in FIX_STATES:
        return [f"fix_basis is missing: say whether the root cause or fix is known ({', '.join(FIX_STATES)})"]
    problems = []
    if block["status"] == "CONFIRMED":
        signal = _normalize(block.get("signal"))
        if not signal:
            problems.append("fix_basis is CONFIRMED without the ticket text that reports the root cause or fix")
        elif source and signal not in _ticket_text(source):
            problems.append("fix_basis.signal is not text from the ticket; copy the comment that reports the root "
                            "cause or fix")
        return problems
    signals = fix_signals(source)
    if signals and not _reason_ok(block.get("reason")):
        problems.append(f"the ticket reports a root cause or fix (\"{signals[0][:80]}\"); record fix_basis "
                        "CONFIRMED with that text, or give a reason why it is not the fix")
    text = uac_text or ""
    first_ac = re.search(r"^- Acceptance Criteria \d+:", text, re.M)
    if not re.search(r"^Note:.*not confirmed", text[:first_ac.start()] if first_ac else text, re.M | re.I):
        problems.append(f"the root cause is not confirmed, so UAC.md must start with: {UNCONFIRMED_NOTE}")
    kinds = {e.get("ac"): e.get("scenario") for e in (evidence.get("scenario") or {}).get("acs") or []
             if isinstance(e, dict)}
    for number, body in sorted((int(n), b) for n, b in _AC_BLOCK.findall(text)):
        if kinds.get(number) != "REGRESSION" and _code_only(body):
            problems.append(f"Acceptance Criteria {number:02d} rests only on code while the root cause is not "
                            f"confirmed; tie it to what the customer reported, or move it to \"{SUGGESTED_HEADER}\"")
    return problems


# --- size ------------------------------------------------------------------------------------------
_LABEL_LINE = re.compile(r"^\s*(?:\*\*)?(?:Source|TBD|Why suggested):", re.I)


def size_problems(uac_text: str) -> list[str]:
    """Keep the delivered UAC near the size of a human UAC, and every Source line short."""
    text = uac_text or ""
    header = _SUGGESTED_HEADER.search(text)
    body = text[:header.start()] if header else text
    problems = []
    words, current = 0, "a criterion"
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("note:"):
            continue
        label = re.match(r"^- (Acceptance Criteria \d+):", stripped)
        if label:
            current = label.group(1)
        source = re.match(r"^(?:\*\*)?Source:(?:\*\*)?\s*(.*)$", stripped)
        if source:
            count = len(source.group(1).split())
            if count > MAX_SOURCE_WORDS:
                problems.append(f"the Source line of {current} has {count} words; keep it to {MAX_SOURCE_WORDS} - name "
                                "the ticket, comment, documentation page or commit, and keep file paths and line numbers "
                                "in the full test plan")
            continue
        if _LABEL_LINE.match(stripped):
            continue
        words += len(stripped.split())
    if words > MAX_BODY_WORDS:
        problems.append(f"the delivered criteria have {words} words; keep them within {MAX_BODY_WORDS} (human UACs: "
                        "median 122, 90% under 337) by merging cases, cutting sub-points and moving detail to the "
                        "full test plan")
    return problems


# --- items made before the change ------------------------------------------------------------------
def pre_existing_problems(evidence: dict, uac_text: str) -> list[str]:
    """Say what happens to content, presets, output or settings created before the change."""
    entry = evidence.get("pre_existing_items")
    if not isinstance(entry, dict) or entry.get("disposition") not in PRE_EXISTING_DISPOSITIONS:
        return ["pre_existing_items is missing: say what happens to items made before the change (content, "
                "presets, output, settings created earlier) - AC, TBD or NOT_APPLICABLE with a reason"]
    disposition = entry["disposition"]
    if disposition == "NOT_APPLICABLE":
        return [] if len(str(entry.get("reason") or "").split()) >= 5 else [
            "pre_existing_items is not applicable without a concrete reason"]
    blocks = {int(n): body for n, body in _AC_BLOCK.findall(uac_text or "")}
    ac = entry.get("ac")
    if not isinstance(ac, int) or ac not in blocks:
        return [f"pre_existing_items: Acceptance Criteria {ac!r} does not exist"]
    if disposition == "TBD" and "TBD:" not in blocks[ac]:
        return [f"pre_existing_items: Acceptance Criteria {ac:02d} has no TBD line"]
    return []


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
