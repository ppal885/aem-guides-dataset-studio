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
   names the documentation), TEST_PLAN (checked in the full test plan, test-plan.md names it) or
   SET_ASIDE (with a concrete reason of at least five words). A rewrite that drops the documentation
   from a Source line fails here. SUGGESTED is no longer an answer.
6. "scenario": the reporter's own steps or requested outcome (text copied from the ticket) and, for
   every Acceptance Criterion, the step it follows (CUSTOMER), the step it guards as a QE regression or
   edge-case check (REGRESSION, no TBD needed). A criterion on a scenario the reporter did not hit
   (ADJACENT, for example one an investigator found or a similar ticket's UAC) may be an Acceptance
   Criterion when it matters - usually a "still works as before" check - and its Source line names
   where it comes from. The reporter's step done another way - another entry point, configuration state or item type listed in
   "action_variants" - is VARIANT and stays a criterion. At least one criterion follows the reporter's
   scenario.
7. "failure_path": when the ticket says that items inside a job, queue or batch fail, get stuck or
   are left unprocessed, what happens to the item that fails, to the remaining items, and how the user
   learns which items failed - each an AC, a TBD or not applicable with a reason. A batch ticket that
   reports no item failure needs no failure_path (in the human UAC corpus, 43% of item-failure batch
   tickets covered it, against 9% of other batch tickets).
8. "similar_uacs" (written by similar_uac_compare.py): the human UACs of the most similar resolved
   tickets and the dimensions each covers. "compared" needs every dimension answered - AC (an existing
   Acceptance Criterion covers it), TBD (that criterion asks it), TEST_PLAN (test-plan.md names it) or
   NOT_APPLICABLE with a reason;
   "none_found" needs the queries tried; "unavailable" needs the reason.
9. Hotfix or backport tickets (from jira-source.json): HOTFIX_SCOPE.json passes
   hotfix_scope_check.py.
10. "fix_basis": whether the root cause or fix is known. CONFIRMED needs the ticket text that says it.
   PROPOSED: a fix pull request is linked but not reviewed or merged; it needs the ticket text that links
   it, and UAC.md starts with the proposed-fix "Note:" line. CONFIRMED also covers a developer comment that
   says the problem is fixed or already handled, and a QE comment that verified it on a build. CAUSE_KNOWN:
   a comment or the investigation explains the root cause but no fix is decided; it needs that ticket text,
   and UAC.md starts with the cause-known "Note:" line. NOT_A_DEFECT: the ticket asks for a new
   capability (an API, an option, a template field), so there is no root cause and no Note line; it needs
   a reason. UNCONFIRMED is fine - many tickets never get a root-cause comment or a linked pull request -
   but then UAC.md starts with a "Note:" line saying the root cause is not confirmed yet. Unless the fix is
   CONFIRMED or PROPOSED, no Acceptance Criterion other than a REGRESSION check rests only on code. When
   the ticket does report a root cause or fix, UNCONFIRMED needs a reason why that text is not the fix.
11. No "Suggested checks" section: a check our own research found (documentation, code, a similar or
   parent ticket, an investigator's other scenario, parity) that matters is an Acceptance Criterion -
   usually a "still works as before" check, or a sub-point of the criterion with the same outcome - and
   one that does not matter enough goes to the full test plan or is set aside with a reason. A UAC.md
   with a "Suggested checks" heading or "- Suggested check NN:" line is refused.
12. Size: the delivered criteria (with their sub-points, the Scope line and the Out of scope list, but not
   the Source, TBD or Note lines) stay within MAX_BODY_WORDS, and each Source line within MAX_SOURCE_WORDS.
   In the 386 human UACs of the corpus the median is 122 words and 90% are under 337; blind comparisons
   showed ours 4 to 15 times longer, mostly from long Source lines and extra sub-points. File paths and line
   numbers belong in the full test plan record.
13. "pre_existing_items": what happens to items made before the change - content, maps, presets,
   output, settings or projects created or generated earlier - an AC, a TBD or NOT_APPLICABLE with a reason.
   15% of human UACs cover it ("older files need re-processing", "old preset and newly created preset"),
   and blind comparisons missed it on tickets that never say "upgrade" or "migration". An AC says the
   outcome: UNCHANGED (they stay as they are - the usual human answer), or CHANGED with the basis that
   decided it; a guessed new behaviour for old items is refused.
14. "action_variants": the ticket's own action through every route the user has (entry_points: drag and
   drop, toolbar, dialog, context menu, API), every configuration switch that changes the result
   (config_switches, each state it can take), and - when the ticket asks for general behaviour - the other
   item or reference types it applies to (mechanism), plus the action done the other way round
   (mechanism.reverse_action), an item with a different history (mechanism.item_origin), and the forms of
   the value the change reads or shows - empty, missing, special characters (mechanism.value_shapes, an AC
   lists at least two in "shapes" and names each). Each is an AC
   that names it, a TBD, or not applicable with a reason. A route, switch or item type known only from the
   code (basis CODE) is a TBD, TEST_PLAN, or an AC that checks it still works as before - never new
   behaviour read from the code. A research-found variant (DOCUMENTATION or CODE basis, or a reverse action, item history or value
   form) with the same outcome as an AC may be TEST_PLAN: named in test-plan.md, left out of the delivered
   UAC. A criterion that covers one of them is scenario VARIANT. When the ticket generates output (any
   output type), entry_points also names each documented generation route - the output preset from the map,
   Map Collection, a baseline, and for PDF the Download as PDF / single-topic path - so none is dropped
   silently (miss probe MP-004); when it changes an output preset setting, also a Global or Folder Profile
   preset template applied with Apply Preset Changes. When the ticket brings content in (paste, import, upload, drag and drop),
   input_sources lists at least two places it can come from (another application, view, topic or file
   format), each dispositioned. A NOT_APPLICABLE reason says why the route, switch or item cannot do the
   action; "nobody named it" is why it is a variant, not a reason, and is refused.
15. "scope_boundaries": each limit the ticket, a developer or product decided - a version, type or path the
   change does not cover, a loss that is expected - is an Out of scope item or a criterion that states it
   (human UACs: "V2 baseline is out of scope", "external paste: fix not applicable"). An empty list needs
   scope_boundaries_reason.
16. "output_setting": when the ticket changes generated output, whether the new behaviour sits behind a
   setting and its default - an AC with a product or development basis, a TBD, or NOT_APPLICABLE with a
   reason. Existing output changing (pre_existing_items CHANGED) needs a product or development basis too.
17. "shared_consumers": what the change touches that other screens read ("mechanism") and those screens
   ("consumers"), each an AC sub-point of a "still works as before" criterion, TEST_PLAN, or NOT_APPLICABLE
   with a reason; an empty list needs a reason, and is refused when the ticket says the change reaches other
   areas.

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
PLAN_FILE = "test-plan.md"
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
# The delivered UAC no longer has a "Suggested checks (QE decide):" section: research checks that matter are
# Acceptance Criteria, the rest go to the full test plan. The patterns stay only to refuse an old-style section.
_SUGGESTED_HEADER = re.compile(r"^Suggested checks\b.*$", re.M)
_SUGGESTED_LINE = re.compile(r"^- Suggested check \d+:", re.M)
_SUGGESTED_GONE = ("SUGGESTED is no longer an answer: a research check that matters is an Acceptance Criterion "
                   "(usually a \"still works as before\" check or a sub-point); otherwise TEST_PLAN or set it aside")
MAX_BODY_WORDS = 350
MAX_SOURCE_WORDS = 30
PRE_EXISTING_DISPOSITIONS = ("AC", "TBD", "NOT_APPLICABLE")
# What an AC says about items made before the change. Human UACs usually say they stay as they are ("existing
# presets remain unaffected"); two blind comparisons asserted new behaviour for them instead (a guessed upgrade
# criterion QE struck, and "existing content shows draft comments" where the new option was off by default).
# A held-out run guessed it a third time with a loose "basis TICKET", so CHANGED now also needs the ticket text
# that decided it, copied.
PRE_EXISTING_OUTCOMES = ("UNCHANGED", "CHANGED")
PRE_EXISTING_DECIDED_BASES = ("TICKET", "ATTACHMENT", "PRODUCT_DECISION", "DEVELOPER_COMMENT")
# A reverse action, item history or value form becomes a criterion only when the ticket, an attachment or a
# decision names it; otherwise it goes to the full test plan (TEST_PLAN). A held-out run of ten tickets still
# averaged 5.2 criteria against human UACs of 37-46 words on small fixes, mostly from these dimensions.
DECIDED_BASES = PRE_EXISTING_DECIDED_BASES
# When a ticket changes what generated output looks like, the team shipped the new behaviour behind a setting that
# is off by default, so existing output stays the same (Include Draft Comments toggle, Show all glossary entries
# option, an OSGi flag for map appendices). Ours assumed the new behaviour for everyone on all three.
OUTPUT_CHANGE_DECIDERS = ("PRODUCT_DECISION", "DEVELOPER_COMMENT")
OUTPUT_SETTING_DISPOSITIONS = ("AC", "TBD", "NOT_APPLICABLE")


def is_output_ticket(source: dict | None) -> bool:
    if not source:
        return False
    return bool(OUTPUT_SIGNAL.search("\n".join([source.get("summary") or "", source.get("description") or ""])))


# When a change touches something many screens read - element position and selection, the topic's CSS, how a
# reference is stored - human UACs list every screen that reads it as a "still works" check: breadcrumb, right
# panel, outline, source cursor and AI Assistant selection for a position-mapping fix; review panel, version
# history and merge for a CSS-order fix; baseline, reports and translation for a reference change. Blind
# comparisons missed them on all three. They are regression checks, so a screen found in code or documentation
# may be one - as a sub-point of a single "still works as before" criterion, or in the full test plan.
SHARED_SIGNAL = re.compile(
    r"\b(?:touch(?:es|ed)?\s+(?:upon\s+)?(?:a\s+lot\s+of|many|several|multiple|other)\s+areas|impact(?:ed)?\s+areas?|"
    r"areas?\s+(?:of\s+)?impact|shared\s+(?:code|logic|component|service|path)|common\s+(?:code|logic|component|"
    r"service|path)|used\s+(?:in|by)\s+(?:many|multiple|several|other))\b", re.IGNORECASE)
SHARED_DISPOSITIONS = ("AC", "TEST_PLAN", "NOT_APPLICABLE")
MIN_SHARED_CONSUMERS = 2


def shared_consumer_problems(evidence: dict, uac_text: str, source: dict | None, plan_text: str = "") -> list[str]:
    """Name the other screens that read what the change touches, each checked in the UAC or the test plan."""
    block = evidence.get("shared_consumers")
    signal = bool(source) and bool(SHARED_SIGNAL.search(_ticket_text(source)))
    if not isinstance(block, dict):
        return ["shared_consumers is missing: name what the change touches (\"mechanism\") and the other screens that "
                "read it (\"consumers\"), or \"consumers\": [] with a reason when nothing else reads it"]
    consumers = block.get("consumers")
    if not isinstance(consumers, list):
        return ["shared_consumers.consumers must be a list"]
    if not consumers:
        if signal:
            return ["the ticket says the change reaches other areas: shared_consumers needs at least "
                    f"{MIN_SHARED_CONSUMERS} screens that read what it touches, each an AC sub-point, TEST_PLAN or "
                    "NOT_APPLICABLE with a reason"]
        return [] if len(str(block.get("reason") or "").split()) >= 5 else [
            "shared_consumers is empty without a concrete reason"]
    if not str(block.get("mechanism") or "").strip():
        return ["shared_consumers needs \"mechanism\": what the change touches that other screens read"]
    if signal and len(consumers) < MIN_SHARED_CONSUMERS:
        return [f"the ticket says the change reaches other areas: list at least {MIN_SHARED_CONSUMERS} consumers"]
    blocks = {int(n): body for n, body in _AC_BLOCK.findall(uac_text or "")}
    plan = _normalize(plan_text)
    problems = []
    for index, entry in enumerate(consumers, 1):
        label = f"shared_consumers {index}"
        if not isinstance(entry, dict) or not str(entry.get("name") or "").strip():
            problems.append(f"{label} needs a name")
            continue
        name, disposition = str(entry["name"]).strip(), entry.get("disposition")
        words = _name_words(name)
        if disposition == "NOT_APPLICABLE":
            if len(str(entry.get("reason") or "").split()) < 5:
                problems.append(f"{label} \"{name}\" is not applicable without a concrete reason")
        elif disposition == "AC":
            acs = _ac_list(entry.get("acs", entry.get("ac")))
            if not acs or any(ac not in blocks for ac in acs):
                problems.append(f"{label} \"{name}\": Acceptance Criteria {acs!r} does not exist")
                continue
            text = _normalize(" ".join(blocks[ac] for ac in acs))
            if words and not any(re.search(rf"\b{re.escape(w)}", text) for w in words):
                problems.append(f"{label} \"{name}\": Acceptance Criteria {', '.join(f'{a:02d}' for a in acs)} does not "
                                "name it")
        elif disposition == "TEST_PLAN":
            if not plan:
                problems.append(f"{label} \"{name}\": TEST_PLAN needs the full test plan ({PLAN_FILE}) that checks it")
            elif words and not any(re.search(rf"\b{re.escape(w)}", plan) for w in words):
                problems.append(f"{label} \"{name}\": the full test plan does not name it")
        else:
            problems.append(f"{label} \"{name}\": disposition must be {', '.join(SHARED_DISPOSITIONS)}")
    return problems


def output_setting_problems(evidence: dict, uac_text: str, source: dict | None) -> list[str]:
    """An output-changing ticket says whether the new behaviour sits behind a setting, and its default."""
    if not is_output_ticket(source):
        return []
    entry = evidence.get("output_setting")
    if not isinstance(entry, dict) or entry.get("disposition") not in OUTPUT_SETTING_DISPOSITIONS:
        return ["output_setting is missing: the ticket changes generated output - say whether the new behaviour is "
                "behind a setting (preset option, template option, configuration) and whether it is off by default "
                "- an AC with the deciding basis, a TBD, or NOT_APPLICABLE with a reason (for example a fix that "
                "restores documented output)"]
    disposition = entry["disposition"]
    if disposition == "NOT_APPLICABLE":
        return [] if len(str(entry.get("reason") or "").split()) >= 5 else [
            "output_setting is not applicable without a concrete reason"]
    blocks = {int(n): body for n, body in _AC_BLOCK.findall(uac_text or "")}
    ac = entry.get("ac")
    if not isinstance(ac, int) or ac not in blocks:
        return [f"output_setting: Acceptance Criteria {ac!r} does not exist"]
    if disposition == "TBD":
        return [] if "TBD:" in blocks[ac] else [f"output_setting: Acceptance Criteria {ac:02d} has no TBD line"]
    if entry.get("basis") not in OUTPUT_CHANGE_DECIDERS:
        return ["output_setting: a setting and its default are decided by product or development "
                f"({', '.join(OUTPUT_CHANGE_DECIDERS)}); without that, ask in a TBD"]
    return []


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


def doc_finding_problems(evidence: dict, doc_research: dict, uac_text: str, plan_text: str = "") -> list[str]:
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
        elif entry.get("disposition") == "TEST_PLAN":
            problems += _test_plan_problems(f"documentation finding {index}", claim or f"finding {index}",
                                            None, plan_text)
        elif entry.get("disposition") == "SUGGESTED":
            problems.append(f"documentation finding {index}: {_SUGGESTED_GONE}")
        else:
            problems.append(f"documentation finding {index}: disposition must be AC, TEST_PLAN or SET_ASIDE")
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
    plan = (folder / PLAN_FILE).read_text(encoding="utf-8") if (folder / PLAN_FILE).is_file() else ""
    source_path = folder / JIRA_SOURCE_FILE
    try:
        source = _load(source_path) if source_path.is_file() else None
    except ValueError:
        source = None
    return {
        "preflight": preflight_problems(evidence.get("preflight")), "rag_probes": rag_problems(evidence),
        "history_attempts": history_problems(evidence),
        "doc_findings": doc_finding_problems(evidence, doc_research, uac, plan),
        "scenario": scenario_problems(evidence, uac, source), "failure_path": failure_path_problems(evidence, uac, source),
        "similar_uacs": similar_uac_problems(evidence, uac, plan), "suggested_checks": suggested_problems(uac),
        "fix_basis": fix_basis_problems(evidence, uac, source),
        "size": size_problems(uac), "pre_existing_items": pre_existing_problems(evidence, uac, source),
        "action_variants": action_variant_problems(evidence, uac, source, plan),
        "output_setting": output_setting_problems(evidence, uac, source),
        "shared_consumers": shared_consumer_problems(evidence, uac, source, plan),
        "scope_boundaries": scope_boundary_problems(evidence, uac),
        "internal_settings": internal_setting_problems(uac),
    }


def evidence_problems(folder: Path) -> list[str]:
    """Checks 2-8 and 10-15: the evidence record the runner also enforces."""
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
SCENARIO_KINDS = ("CUSTOMER", "REGRESSION", "VARIANT", "ADJACENT")
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
    a deleted project when the reporter's job completed). A criterion built on that other scenario, or on a
    similar ticket's UAC, is ADJACENT: it may be an Acceptance Criterion when it matters (usually a "still works
    as before" check, its Source line naming where it comes from), but it never replaces the reporter's own
    scenario - at least one criterion still follows it.
    The reporter's step done through another entry point, configuration state or item type is VARIANT: it
    stays a criterion when "action_variants" lists it for that criterion."""
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
        if kind == "VARIANT":
            if _normalize(entry.get("step")) not in steps:
                problems.append(f"Acceptance Criteria {ac:02d}: its step is not one of scenario.customer_steps")
            if ac not in _variant_acs(evidence):
                problems.append(f"Acceptance Criteria {ac:02d} is a VARIANT, but action_variants lists no entry point, "
                                "configuration switch or mechanism variant for it")
        elif kind in ("CUSTOMER", "REGRESSION"):
            customer_acs += kind == "CUSTOMER"
            if _normalize(entry.get("step")) not in steps:
                problems.append(f"Acceptance Criteria {ac:02d}: its step is not one of scenario.customer_steps")
        elif kind == "ADJACENT":
            if not re.search(r"Source:\**\s*\S", blocks[ac]):
                problems.append(f"Acceptance Criteria {ac:02d} follows a scenario the reporter did not hit; its Source "
                                "line must name the documentation page, code or ticket it comes from")
        else:
            problems.append(f"Acceptance Criteria {ac:02d}: scenario must be {', '.join(SCENARIO_KINDS)}")
    if blocks and customer_acs == 0:
        problems.append("no Acceptance Criterion follows the reporter's own scenario")
    return problems


def _variant_acs(evidence: dict) -> set[int]:
    block = evidence.get("action_variants") if isinstance(evidence.get("action_variants"), dict) else {}
    mechanism = block.get("mechanism") if isinstance(block.get("mechanism"), dict) else {}
    found: set[int] = set()
    for entry in (block.get("entry_points") or []) + (block.get("config_switches") or []) + (
            block.get("input_sources") or []) + (mechanism.get("variants") or []) + [
            mechanism.get(d) for d in MECHANISM_DIMENSIONS]:
        if isinstance(entry, dict) and entry.get("disposition") in ("AC", "TBD"):
            found.update(_ac_list(entry.get("acs", entry.get("ac"))))
    return found


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
SIMILAR_DISPOSITIONS = ("AC", "TBD", "TEST_PLAN", "NOT_APPLICABLE")


def similar_uac_problems(evidence: dict, uac_text: str, plan_text: str = "") -> list[str]:
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
            if disposition == "SUGGESTED":
                problems.append(f"{name}: {_SUGGESTED_GONE}")
            elif disposition not in SIMILAR_DISPOSITIONS:
                problems.append(f"{name} has no answer; say AC, TBD, TEST_PLAN or NOT_APPLICABLE")
            elif disposition == "NOT_APPLICABLE":
                if len(str(entry.get("reason") or "").split()) < 5:
                    problems.append(f"{name} is not applicable without a concrete reason")
            elif disposition == "TEST_PLAN":
                problems += _test_plan_problems(f"similar UAC {uac.get('key')}", str(entry.get("dimension") or ""), None,
                                                plan_text)
            else:
                ac = entry.get("ac")
                if not isinstance(ac, int) or ac not in blocks:
                    problems.append(f"{name}: Acceptance Criteria {ac!r} does not exist")
                elif disposition == "TBD" and "TBD:" not in blocks[ac]:
                    problems.append(f"{name}: Acceptance Criteria {ac:02d} has no TBD line")
    return problems


# --- no suggested checks ------------------------------------------------------------------------------
def suggested_problems(uac_text: str) -> list[str]:
    """The delivered UAC has no "Suggested checks" section any more.

    A check our own research found that matters is an Acceptance Criterion (usually a "still works as before"
    check, or a sub-point of the criterion with the same outcome); one that does not matter enough goes to the
    full test plan or is set aside with a reason in the record."""
    text = uac_text or ""
    if _SUGGESTED_HEADER.search(text) or _SUGGESTED_LINE.search(text):
        return ["UAC.md has a \"Suggested checks\" section; there are no suggested checks any more - write each check "
                "that matters as an Acceptance Criterion (a \"still works as before\" check or a sub-point, within the "
                "ten-criteria cap) whose Source line names the documentation page, code or ticket, and move the rest "
                f"to the full test plan ({PLAN_FILE})"]
    return []


# --- internal settings ------------------------------------------------------------------------------
# Setting names QE cannot find on a screen: dotted configuration keys (dxml.use.split), ALL_CAPS flags
# (PDF_ENGINE), camelCase keys (enablePublishApiMigration), snake_case keys (guides_publish_config) and
# configuration files (all_lngvar.json).
_INTERNAL_NAME = re.compile(
    r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}\b"
    r"|\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b"
    r"|\b[\w-]+\.(?:json|properties|cfg|config|yaml|yml)\b")
# A camelCase or snake_case name is an API field QE send on an API ticket (asOnDate, jobId); it is an
# internal setting only when the line switches it.
_KEY_NAME = re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b|\b[a-z][a-z0-9]*_[a-z0-9_]+\b")
_SWITCHED = re.compile(r"\btoggl\w*|\bturn(?:ed|s)? (?:on|off)\b|\b(?:on|off),? (?:then|and)\b|\benabled?\b"
                       r"|\bdisabled?\b|\bfeature flag\b|\bsetting\b|\bv1\b.*\bv2\b", re.I)
# Names QE do use: DITA attribute and metadata names and the conref href forms.
_INTERNAL_ALLOWED = {"fmditaTitle", "topicID", "elementID", "topicId", "elementId", "conkeyref", "keyref", "iPhone",
                     "iPad", "eBook"}
_QUOTED = re.compile(r'"[^"]*"|`[^`]*`')
# A web address (my.salesforce.com, experienceleague.adobe.com) is something QE type, not a setting.
_WEB_ADDRESS = re.compile(r"\.(?:com|net|org|io|edu|gov|co|uk|in|de|fr|jp|cn|site|cloud)$", re.I)


def internal_setting_problems(uac_text: str) -> list[str]:
    """Criteria and case sub-points name settings by their on-screen label; internal names go to the test plan."""
    problems = []
    ac = 0
    for line in (uac_text or "").splitlines():
        head = re.match(r"^- Acceptance Criteria (\d+):", line)
        if head:
            ac = int(head.group(1))
        elif not re.match(r"^\s+- ", line):
            continue
        text = _QUOTED.sub(" ", line)
        found = list(_INTERNAL_NAME.finditer(text))
        if _SWITCHED.search(text):
            found += list(_KEY_NAME.finditer(text))
        names = [m.group(0) for m in found
                 if m.group(0) not in _INTERNAL_ALLOWED and not _WEB_ADDRESS.search(m.group(0))]
        if names:
            problems.append(f"Acceptance Criteria {ac:02d} names internal settings or code ({', '.join(names[:4])}): "
                            "use the setting's on-screen label (for example Enable DITA-OT preprocessing on the "
                            f"General tab), or move the internal flag or configuration key to the test plan ({PLAN_FILE})")
    return problems


# --- root cause or fix known ---------------------------------------------------------------------------
# Ticket text that reports a root cause, a fix or a pull request. The VM staleness watcher uses it too.
FIX_SIGNAL = re.compile(
    r"\broot[\s-]*cause\b|\bRCA\b|\bcaused by\b|\bfix(?:ed)? in\b|\bthe fix\b|/pull/\d+|\bpull request\b"
    r"|\bPR\s*#?\d+|\bmerged\b|\bcherry[\s-]*pick"
    r"|\balready (?:handled|fixed|taken care of)\b|\bverified (?:on|in) (?:build )?\d", re.IGNORECASE)
FIX_STATES = ("CONFIRMED", "PROPOSED", "CAUSE_KNOWN", "UNCONFIRMED", "NOT_A_DEFECT")
CAUSE_KNOWN_NOTE = ("Note: The root cause is explained in the ticket, but the fix is not decided yet. These criteria "
                    "cover what the customer reported and will be checked again when the fix is known.")
UNCONFIRMED_NOTE = ("Note: The root cause and the fix are not confirmed yet. These criteria cover what the customer "
                    "reported and will be checked again when the fix is known.")
PROPOSED_NOTE = ("Note: A fix is proposed in a linked pull request but is not reviewed yet. These criteria cover what "
                 "the customer reported and the proposed fix, and will be checked again when the fix is final.")
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
    it says so at the top, and a criterion that rests only on code (a guess at the mechanism) is refused unless
    it is a REGRESSION check that the reporter's scenario still works as before; otherwise it goes to the full
    test plan."""
    block = evidence.get("fix_basis")
    if not isinstance(block, dict) or block.get("status") not in FIX_STATES:
        return [f"fix_basis is missing: say whether the root cause or fix is known ({', '.join(FIX_STATES)})"]
    problems = []
    status = block["status"]
    text = uac_text or ""
    first_ac = re.search(r"^- Acceptance Criteria \d+:", text, re.M)
    head = text[:first_ac.start()] if first_ac else text
    if status in ("CONFIRMED", "PROPOSED", "CAUSE_KNOWN"):
        signal = _normalize(block.get("signal"))
        if not signal:
            problems.append(f"fix_basis is {status} without the ticket text that reports the root cause or fix")
        elif source and signal not in _ticket_text(source):
            problems.append("fix_basis.signal is not text from the ticket; copy the comment that reports the root "
                            "cause or fix")
        if status == "PROPOSED" and not re.search(r"^Note:.*fix is proposed", head, re.M | re.I):
            problems.append(f"a fix is proposed but not reviewed, so UAC.md must start with: {PROPOSED_NOTE}")
        if status == "CAUSE_KNOWN":
            if not re.search(r"^Note:.*fix is not decided", head, re.M | re.I):
                problems.append(f"the root cause is known but the fix is not, so UAC.md must start with: "
                                f"{CAUSE_KNOWN_NOTE}")
            return problems + _code_only_problems(evidence, text)
        return problems
    if status == "NOT_A_DEFECT":
        if not _reason_ok(block.get("reason")):
            problems.append("fix_basis NOT_A_DEFECT needs a reason: what new capability the ticket asks for")
        if re.search(r"^Note:.*not confirmed", head, re.M | re.I):
            problems.append("the ticket asks for a new capability, so UAC.md has no root-cause Note line")
        return problems + _code_only_problems(evidence, text)
    signals = fix_signals(source)
    if signals and not _reason_ok(block.get("reason")):
        problems.append(f"the ticket reports a root cause or fix (\"{signals[0][:80]}\"); record fix_basis "
                        "CONFIRMED with that text, or give a reason why it is not the fix")
    if not re.search(r"^Note:.*not confirmed", head, re.M | re.I):
        problems.append(f"the root cause is not confirmed, so UAC.md must start with: {UNCONFIRMED_NOTE}")
    return problems + _code_only_problems(evidence, text)


def _code_only_problems(evidence: dict, text: str) -> list[str]:
    kinds = {e.get("ac"): e.get("scenario") for e in (evidence.get("scenario") or {}).get("acs") or []
             if isinstance(e, dict)}
    problems = []
    for number, body in sorted((int(n), b) for n, b in _AC_BLOCK.findall(text)):
        if kinds.get(number) != "REGRESSION" and _code_only(body):
            problems.append(f"Acceptance Criteria {number:02d} rests only on code while the root cause is not "
                            "confirmed; tie it to what the customer reported, make it a REGRESSION check that it "
                            f"still works as before, or move it to the full test plan ({PLAN_FILE})")
    return problems


# --- size ------------------------------------------------------------------------------------------
_LABEL_LINE = re.compile(r"^\s*(?:\*\*)?(?:Source|TBD):", re.I)


def size_problems(uac_text: str) -> list[str]:
    """Keep the delivered UAC near the size of a human UAC, and every Source line short."""
    text = uac_text or ""
    problems = []
    words, current = 0, "a criterion"
    for line in text.splitlines():
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
def pre_existing_problems(evidence: dict, uac_text: str, source: dict | None = None) -> list[str]:
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
    if disposition == "AC":
        outcome = entry.get("outcome")
        if outcome not in PRE_EXISTING_OUTCOMES:
            return ["pre_existing_items: say whether items made before the change stay as they are (outcome "
                    "UNCHANGED) or behave the new way (outcome CHANGED, with the basis that decided it)"]
        if outcome == "CHANGED" and entry.get("basis") not in PRE_EXISTING_DECIDED_BASES:
            return ["pre_existing_items: new behaviour for items made before the change needs a basis that decided it ("
                    f"{', '.join(PRE_EXISTING_DECIDED_BASES)}); without one, expect them unchanged or ask in a TBD - "
                    "a new option is usually off for existing items"]
        if outcome == "CHANGED" and is_output_ticket(source) and entry.get("basis") not in OUTPUT_CHANGE_DECIDERS:
            return ["pre_existing_items: the ticket changes generated output, and existing output changing is decided "
                    f"by product or development ({', '.join(OUTPUT_CHANGE_DECIDERS)}), not by the customer's ask; "
                    "human UACs kept existing output unchanged behind a setting that is off by default - expect "
                    "UNCHANGED or ask in a TBD"]
        if outcome == "CHANGED":
            quote = _normalize(entry.get("quote"))
            if len(quote.split()) < 5:
                return ["pre_existing_items: outcome CHANGED needs \"quote\": the ticket or decision text, copied, that "
                        "says items made before the change behave the new way"]
            if source and quote not in _ticket_text(source):
                return ["pre_existing_items: the CHANGED quote is not text from the ticket; copy the sentence that "
                        "decided it, or expect existing items unchanged, or ask in a TBD"]
    return []


# --- entry points, configuration switches and mechanism variants ---------------------------------------
VARIANT_DISPOSITIONS = ("AC", "TBD", "NOT_APPLICABLE")
# A criterion that checks existing behaviour is kept: the only kind of AC a code-only variant may have.
_AS_BEFORE = re.compile(r"\b(?:as before|still works?|still \w+s\b|unchanged|not change|no change|stays? the same|"
                        r"remains?|continues? to|same as before)", re.I)
# Where a route, switch or item type comes from. CODE alone never makes new behaviour a criterion: in blind
# comparisons, routes and modes read only from the code were criteria the human UAC did not have.
VARIANT_BASES = ("TICKET", "ATTACHMENT", "PRODUCT_DECISION", "DEVELOPER_COMMENT", "DOCUMENTATION", "CODE")
# Always answered, each with what it asks for. value_shapes: the human UACs test the forms of the value the
# change reads or shows - an empty value and a missing one (href="" and no href), and special characters,
# fragments, query strings, encoded characters and very long values (a URL used as a TOC title). Blind
# comparisons missed them on two tickets while covering the reporter's one value.
MECHANISM_DIMENSIONS = {
    "reverse_action": "the action done the other way round (move back, re-enable, undo)",
    "item_origin": "an item with a different history (created in the target location, never translated, from an "
                   "older release)",
    "value_shapes": "the forms of the value the change reads or shows (empty, missing, special characters, "
                    "encoded, very long)",
}
_STOP_WORDS = {"from", "with", "into", "that", "this", "when", "then", "panel", "dialog", "using", "through",
               "button", "option", "menu", "file", "files", "view", "editor", "page", "item", "items"}


# "Nobody named it" is the reason a variant exists, never a reason it does not apply. Blind comparisons
# marked Map Collection not applicable with "no one names it" on two tickets whose human UAC made it a
# criterion. A reason must say why the route, switch or item cannot do the action.
_NOT_NAMED_REASON = re.compile(
    r"\b(?:not|never|neither|nor|no\s+one|nobody|nothing|none)\b[^.;]{0,40}\b(?:named?|names|mention\w*|ask\w*|request\w*|"
    r"report\w*|list\w*|cited?|referenc\w*)\b"
    r"|\b(?:reporter|ticket|customer|description|comments?)\s+(?:did\s+not|didn't|does\s+not|doesn't|never)\s+"
    r"(?:name|mention|ask|use|hit|cover|include)\b"
    r"|\bnot\s+in\s+the\s+(?:ticket|description|comments?)\b", re.IGNORECASE)
_CANNOT_REASON = re.compile(
    r"\b(?:cannot|can't|can\s+not|does\s+not\s+(?:use|open|read|store|show|call|reach|support|offer|have|run)|"
    r"doesn't\s+(?:use|open|read|store|show|call|reach|support|offer|have|run)|has\s+no|no\s+such|not\s+available|"
    r"not\s+supported|only\s+(?:for|in|on))\b", re.IGNORECASE)


def _value_shape_problems(entry: dict, blocks: dict[int, str]) -> list[str]:
    """An AC answer lists at least two value forms, and its criteria name each of them."""
    shapes = [str(s).strip() for s in entry.get("shapes") or [] if str(s).strip()]
    if len(shapes) < 2:
        return ["action_variants.mechanism.value_shapes: list at least two value forms in shapes (for example empty "
                "and missing, or special characters and a very long value)"]
    text = _normalize(" ".join(blocks.get(ac, "") for ac in _ac_list(entry.get("acs", entry.get("ac")))))
    return [f"action_variants.mechanism.value_shapes: no Acceptance Criterion names the {shape} value"
            for shape in shapes
            if not any(re.search(rf"\b{re.escape(w)}", text) for w in re.findall(r"[a-z0-9]+", shape.lower())
                       if len(w) >= 4) and _normalize(shape) not in text]


# Research-found variants may live in the full test plan instead of the delivered UAC. Blind comparisons showed
# human UACs of one to three lines where ours listed every route, switch and value form as criteria; the checks
# stay, in the test plan. A ticket-named or decided variant is never TEST_PLAN: the human UAC keeps those.
TEST_PLAN_BASES = ("DOCUMENTATION", "CODE", None)


def _test_plan_problems(label: str, name: str, basis, plan_text: str) -> list[str]:
    if basis not in TEST_PLAN_BASES:
        return [f"{label} \"{name}\": a variant from the ticket, an attachment or a decision (basis {basis}) stays in "
                "the delivered UAC as an AC or a TBD; TEST_PLAN is for variants found by our own research"]
    if not plan_text.strip():
        return [f"{label} \"{name}\": TEST_PLAN needs the full test plan ({PLAN_FILE}) that checks it"]
    words = _name_words(name)
    text = _normalize(plan_text)
    if words and not any(re.search(rf"\b{re.escape(w)}", text) for w in words):
        return [f"{label} \"{name}\": the full test plan does not name it"]
    return []


def _name_words(name) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", str(name or "").lower()) if len(w) >= 4 and w not in _STOP_WORDS]


def _variant_entry_problems(label: str, entry, blocks: dict[int, str], uac_text: str = "",
                            needs_basis: bool = True, plan_text: str = "") -> list[str]:
    """One variant: an AC that names it, a TBD on the AC it governs, or not applicable with a reason.

    A variant known only from the code (basis CODE) is a TBD, TEST_PLAN, or an AC that checks it still works as
    before - never new behaviour read from the code. A variant found by
    our own research (DOCUMENTATION or CODE, or a reverse action, item history or value form) whose expected outcome
    is the same as a criterion may be TEST_PLAN: checked in the full test plan, not listed in the delivered UAC."""
    if not isinstance(entry, dict) or not str(entry.get("name") or "").strip():
        return [f"{label} needs a name"]
    name = str(entry["name"]).strip()
    disposition = entry.get("disposition")
    basis = entry.get("basis")
    if needs_basis and disposition != "NOT_APPLICABLE" and basis not in VARIANT_BASES:
        return [f"{label} \"{name}\": basis must be {', '.join(VARIANT_BASES)} - where this route, switch or item "
                "type comes from"]
    if disposition == "SUGGESTED":
        return [f"{label} \"{name}\": {_SUGGESTED_GONE}"]
    if needs_basis and basis == "CODE" and disposition == "AC":
        acs = _ac_list(entry.get("acs", entry.get("ac")))
        if not acs or not all(ac in blocks and _AS_BEFORE.search(blocks[ac]) for ac in acs):
            return [f"{label} \"{name}\" is known only from the code: an Acceptance Criterion may only check that it "
                    "still works as before; otherwise make it a TBD or TEST_PLAN"]
    if disposition == "TEST_PLAN":
        return _test_plan_problems(label, name, basis if needs_basis else None, plan_text)
    if disposition not in VARIANT_DISPOSITIONS:
        return [f"{label} \"{name}\": disposition must be {', '.join(VARIANT_DISPOSITIONS)} or TEST_PLAN"]
    if disposition == "NOT_APPLICABLE":
        reason = str(entry.get("reason") or "")
        if len(reason.split()) < 5:
            return [f"{label} \"{name}\" is not applicable without a concrete reason"]
        if _NOT_NAMED_REASON.search(reason) and not _CANNOT_REASON.search(reason):
            return [f"{label} \"{name}\": \"{reason[:80]}\" is why it is a variant, not why it does not apply - say "
                    "why this route, switch or item cannot do the action, or make it an AC or a TBD"]
        return []
    acs = _ac_list(entry.get("acs", entry.get("ac")))
    missing = [ac for ac in acs if ac not in blocks]
    if not acs or missing:
        return [f"{label} \"{name}\": Acceptance Criteria {missing or acs!r} does not exist"]
    text = _normalize(" ".join(blocks[ac] for ac in acs))
    if disposition == "TBD":
        return [] if "tbd:" in text else [f"{label} \"{name}\": Acceptance Criteria {acs[0]:02d} has no TBD line"]
    words = _name_words(name)
    if words and not any(re.search(rf"\b{re.escape(w)}", text) for w in words):
        return [f"{label} \"{name}\": Acceptance Criteria {', '.join(f'{a:02d}' for a in acs)} does not name it"]
    return []


# Output generation has several routes that share one engine; the reporter uses one of them (miss probe
# MP-004). Blind comparisons missed Map Collection publishing on a New AEM Sites ticket and Download as PDF on
# Native PDF tickets.
OUTPUT_SIGNAL = re.compile(
    r"\b(?:native\s+pdf|pdf\s+output|aem\s+sites?|html5|output\s+presets?|generate\s+output|output\s+generation|"
    r"generated\s+output|download\s+as\s+pdf|map\s+collection|dita[\s-]?ot\s+(?:output|publish\w*)|"
    r"publish(?:es|ed|ing)?\s+(?:the\s+)?(?:map|output|site)s?)\b", re.IGNORECASE)
PDF_SIGNAL = re.compile(r"\b(?:native\s+pdf|pdf\s+output|download\s+as\s+pdf|pdf\s+preset)\b", re.IGNORECASE)
OUTPUT_ROUTES = {
    "the output preset from the map (Map console or Map Dashboard Generate)": (
        "output preset", "map console", "map dashboard", "output tab", "output panel", "generate"),
    "Map Collection": ("map collection",),
    "a baseline": ("baseline",),
}
PDF_ROUTES = {"Download as PDF or a single topic": ("download as pdf", "download pdf", "single topic",
                                                    "single-topic")}
# A setting in an output preset also reaches maps through a profile preset template pushed with Apply Preset
# Changes. Human UACs checked that the setting survives that path on two tickets (an AEM Sites publish context
# pushed from a Folder Profile preset, and a new Native PDF preset toggle); ours did not.
PRESET_SETTING_SIGNAL = re.compile(
    r"\bpresets?\b[^.\n]{0,60}\b(?:options?|toggles?|settings?|checkbox(?:es)?|fields?|flags?|parameters?|"
    r"properties|property|context)\b"
    r"|\b(?:options?|toggles?|settings?|checkbox(?:es)?|fields?|flags?|parameters?|properties|property)\b[^.\n]{0,60}"
    r"\bpresets?\b", re.IGNORECASE)
PRESET_ROUTES = {"a Global or Folder Profile preset template applied to maps with Apply Preset Changes": (
    "apply preset changes", "preset template", "profile preset", "folder profile", "global profile")}


def output_route_problems(entry_points, source: dict | None) -> list[str]:
    """An output-generation ticket names every documented generation route in entry_points."""
    if not source or not isinstance(entry_points, list):
        return []
    text = "\n".join([source.get("summary") or "", source.get("description") or ""])
    if not OUTPUT_SIGNAL.search(text):
        return []
    names = " | ".join(str(e.get("name") or "").lower() for e in entry_points if isinstance(e, dict))
    routes = dict(OUTPUT_ROUTES, **(PDF_ROUTES if PDF_SIGNAL.search(text) else {}),
                  **(PRESET_ROUTES if PRESET_SETTING_SIGNAL.search(text) else {}))
    return [f"the ticket generates output: action_variants.entry_points must name {label} - an AC, a TBD or "
            "NOT_APPLICABLE with a reason (the generation routes share one engine; MP-004)"
            for label, terms in routes.items() if not any(term in names for term in terms)]


# Content brought in from outside - pasted, imported, uploaded, dragged in - arrives from several places that the
# same conversion handles. The reporter uses one. Human UACs name the others: a Word table paste ticket covered
# Google Docs, an HTML page and Excel (ours made them suggested checks, "the ticket only reports Word"), and a
# table copy ticket said external paste from Word or Excel is not covered by the fix.
INPUT_SIGNAL = re.compile(
    r"\b(?:paste[sd]?|pasting|clipboard|import(?:s|ed|ing)?|upload(?:s|ed|ing)?|drag(?:ged|ging)?\s+(?:and|&)\s+drop"
    r"(?:ped|ping)?)\b", re.IGNORECASE)
MIN_INPUT_SOURCES = 2


def input_source_problems(block: dict, blocks: dict[int, str], uac_text: str, source: dict | None,
                          plan_text: str = "") -> list[str]:
    """A ticket about content brought in names where that content can come from, each dispositioned."""
    if not source:
        return []
    text = "\n".join([source.get("summary") or "", source.get("description") or ""])
    if not INPUT_SIGNAL.search(text):
        return []
    sources = block.get("input_sources")
    if not isinstance(sources, list) or len(sources) < MIN_INPUT_SOURCES:
        return ["the ticket brings content in (paste, import, upload or drag and drop): action_variants.input_sources "
                f"must list at least {MIN_INPUT_SOURCES} places it can come from - the reporter's one and the others "
                "the same conversion handles (another application, another view or topic, another file format) - "
                "each an AC, a TBD or NOT_APPLICABLE with a reason"]
    problems = []
    for index, entry in enumerate(sources, 1):
        problems += _variant_entry_problems(f"action_variants.input_sources {index}", entry, blocks, uac_text,
                                        plan_text=plan_text)
    return problems


def action_variant_problems(evidence: dict, uac_text: str, source: dict | None = None,
                            plan_text: str = "") -> list[str]:
    """The ticket's own action through every route, configuration state and item type it applies to.

    Blind comparisons with human UACs missed these while the reporter's single path was covered: the toolbar
    insert when the reporter dragged and dropped, both states of the configuration that decides what is
    stored, and the topic reference when the reporter used a map reference while the ticket asked for the
    general behaviour ("users can move content while others refer to it"). On a move ticket the human UAC
    also moved the item back and moved an item with a different origin (created in the target folder). They
    are ACs or TBDs: they are the ticket's own action, not a scenario found only by research. A route, switch
    or item type known only from the code would assert behaviour nobody asked for, so it is a TBD, TEST_PLAN,
    or an AC that checks it still works as before."""
    block = evidence.get("action_variants")
    if not isinstance(block, dict):
        return ["action_variants is missing: list every way the user performs the ticket's action (entry_points), "
                "every configuration switch that changes the result (config_switches), and whether the ticket asks "
                "for general behaviour that covers other item or reference types (mechanism)"]
    blocks = {int(n): body for n, body in _AC_BLOCK.findall(uac_text or "")}
    problems = []
    entry_points = block.get("entry_points")
    if not isinstance(entry_points, list) or not entry_points:
        problems.append("action_variants.entry_points is empty: name every route to the ticket's action (for "
                        "example drag and drop, the toolbar, a dialog, the context menu, an API)")
    else:
        for index, entry in enumerate(entry_points, 1):
            problems += _variant_entry_problems(f"action_variants.entry_points {index}", entry, blocks, uac_text,
                                        plan_text=plan_text)
        problems += output_route_problems(entry_points, source)
    problems += input_source_problems(block, blocks, uac_text, source, plan_text)
    switches = block.get("config_switches")
    if not isinstance(switches, list):
        problems.append("action_variants.config_switches is missing: list each configuration, feature flag or "
                        "setting that changes the result, or give an empty list with config_switches_reason")
    elif not switches:
        if len(str(block.get("config_switches_reason") or "").split()) < 5:
            problems.append("action_variants.config_switches is empty without a concrete config_switches_reason")
    else:
        for index, entry in enumerate(switches, 1):
            label = f"action_variants.config_switches {index}"
            found = _variant_entry_problems(label, entry, blocks, uac_text,
                                        plan_text=plan_text)
            problems += found
            if found or not isinstance(entry, dict) or entry.get("disposition") != "AC":
                continue
            states = [str(s).strip().lower() for s in entry.get("states") or [] if str(s).strip()]
            if len(states) < 2:
                problems.append(f"{label} \"{entry['name']}\": list at least two states (for example enabled and "
                                "disabled) - the human UACs cover each state the switch can take")
                continue
            text = _normalize(" ".join(blocks[ac] for ac in _ac_list(entry.get("acs", entry.get("ac")))))
            for state in states:
                if not re.search(rf"\b{re.escape(_normalize(state))}\b", text):
                    problems.append(f"{label} \"{entry['name']}\": no Acceptance Criterion states the result when it "
                                    f"is {state}")
    mechanism = block.get("mechanism")
    if not isinstance(mechanism, dict) or not isinstance(mechanism.get("general_ask"), bool):
        problems.append("action_variants.mechanism needs general_ask true or false: does the ticket ask for a general "
                        "behaviour, beyond the one item or reference type the reporter used?")
    elif mechanism["general_ask"]:
        variants = mechanism.get("variants")
        if not isinstance(variants, list) or not variants:
            problems.append("action_variants.mechanism asks for general behaviour but lists no variants (the other "
                            "item or reference types the same action applies to)")
        else:
            for index, entry in enumerate(variants, 1):
                problems += _variant_entry_problems(f"action_variants.mechanism variant {index}", entry, blocks,
                                                    uac_text, plan_text=plan_text)
    elif len(str(mechanism.get("reason") or "").split()) < 5:
        problems.append("action_variants.mechanism is limited to the reporter's case without a concrete reason")
    if isinstance(mechanism, dict):
        for dimension in MECHANISM_DIMENSIONS:
            entry = mechanism.get(dimension)
            if not isinstance(entry, dict):
                problems.append(f"action_variants.mechanism.{dimension} is missing: {MECHANISM_DIMENSIONS[dimension]}"
                                " - an AC, a TBD or NOT_APPLICABLE with a reason")
                continue
            found = _variant_entry_problems(f"action_variants.mechanism.{dimension}", entry, blocks, uac_text,
                                            needs_basis=False, plan_text=plan_text)
            problems += found
            if not found and entry.get("disposition") == "AC" and entry.get("basis") not in DECIDED_BASES:
                problems.append(f"action_variants.mechanism.{dimension} \"{entry.get('name')}\": the {dimension.replace('_', ' ')} "
                                "is an Acceptance Criterion only when the ticket, an attachment or a decision names it "
                                f"(basis {', '.join(DECIDED_BASES)}); otherwise answer TEST_PLAN (checked in the full "
                                "test plan), TBD or NOT_APPLICABLE")
                continue
            if dimension == "value_shapes" and not found and entry.get("disposition") == "AC":
                problems += _value_shape_problems(entry, blocks)
    return problems


# --- decided boundaries ------------------------------------------------------------------------------
BOUNDARY_BASES = ("TICKET", "ATTACHMENT", "PRODUCT_DECISION", "DEVELOPER_COMMENT")
BOUNDARY_DISPOSITIONS = ("OUT_OF_SCOPE", "AC")
_OUT_OF_SCOPE_LIST = re.compile(r"^Out of scope:?[ \t]*$(.*?)(?=^(?![-\s])\S|\Z)", re.M | re.S | re.I)


def out_of_scope_items(uac_text: str) -> list[str]:
    """The "- item" lines of the UAC's Out of scope list."""
    match = _OUT_OF_SCOPE_LIST.search(uac_text or "")
    return [line.strip()[2:].strip() for line in (match.group(1) if match else "").splitlines()
            if line.strip().startswith("- ")]


def scope_boundary_problems(evidence: dict, uac_text: str) -> list[str]:
    """Boundaries the ticket, a developer or product already decided are written in the UAC.

    Human UACs state them as points: "V2 baseline is out of scope", "applicable for the old baseline (v1)",
    "external paste from Word or Excel: fix not applicable", "partial table copy: data loss is expected".
    Blind comparisons dropped or turned them into TBDs on two tickets. A decided boundary is an Out of scope
    item or a criterion that states the limit; an undecided one is a TBD and does not belong here."""
    block = evidence.get("scope_boundaries")
    if not isinstance(block, list):
        return ["scope_boundaries is missing: list each limit the ticket, a developer or product decided (a version, "
                "type or path the change does not cover, a loss that is expected) - or give an empty list with "
                "scope_boundaries_reason"]
    if not block:
        return [] if len(str(evidence.get("scope_boundaries_reason") or "").split()) >= 5 else [
            "scope_boundaries is empty without a concrete scope_boundaries_reason"]
    blocks = {int(n): body for n, body in _AC_BLOCK.findall(uac_text or "")}
    listed = _normalize(" ".join(out_of_scope_items(uac_text)))
    problems = []
    for index, entry in enumerate(block, 1):
        label = f"scope_boundaries {index}"
        if not isinstance(entry, dict) or not str(entry.get("boundary") or "").strip():
            problems.append(f"{label} needs the boundary text")
            continue
        boundary = str(entry["boundary"]).strip()
        if entry.get("basis") not in BOUNDARY_BASES:
            problems.append(f"{label} \"{boundary[:60]}\": basis must be {', '.join(BOUNDARY_BASES)} - a limit found "
                            "only in the code or by our own research is a TBD, not a decided boundary")
            continue
        words = _name_words(boundary)
        disposition = entry.get("disposition")
        if disposition == "OUT_OF_SCOPE":
            if not listed:
                problems.append(f"{label} \"{boundary[:60]}\": the UAC has no Out of scope list")
            elif words and not any(re.search(rf"\b{re.escape(w)}", listed) for w in words):
                problems.append(f"{label} \"{boundary[:60]}\": no Out of scope item names it")
        elif disposition == "AC":
            acs = _ac_list(entry.get("acs", entry.get("ac")))
            if not acs or any(ac not in blocks for ac in acs):
                problems.append(f"{label} \"{boundary[:60]}\": Acceptance Criteria {acs!r} does not exist")
                continue
            text = _normalize(" ".join(blocks[ac] for ac in acs))
            if words and not any(re.search(rf"\b{re.escape(w)}", text) for w in words):
                problems.append(f"{label} \"{boundary[:60]}\": Acceptance Criteria "
                                f"{', '.join(f'{a:02d}' for a in acs)} does not state it")
        else:
            problems.append(f"{label} \"{boundary[:60]}\": disposition must be {', '.join(BOUNDARY_DISPOSITIONS)}")
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
