#!/usr/bin/env python3
"""Generate draft UACs for every release ticket with GitHub Copilot CLI.

One scheduled run:
  1. health checks: Jira auth, Dataset Studio MCP health URL, Copilot CLI present;
  2. finds tickets with the configured JQL;
  3. runs `copilot -p` once per ticket with the test-plan-generation skill, writing
     UAC.md, test-plan.md, the UAC Doc Researcher result and the source coverage map
     into <output_dir>/<KEY>/;
  4. checks the files (plan validator, AC count 1-10, blocked vocabulary), that the
     UAC Doc Researcher actually ran, and that every sentence of the live Jira
     description and comments, and every attachment, is mapped to the UAC, and that every
     place the feature appears (from documentation and code) is covered;
  5. posts a draft comment with the plan attached and adds the draft label. When the
     UAC has TBDs, the draft also shows the decision request that the poster will send
     to the ticket after QE approval (DECISIONS.md).

Copilot never writes to Jira: its Jira write tools are denied in the config and
all Jira writes happen here, after the checks. The Acceptance Criteria field is
only filled later by uac_approved_poster.py, after QE adds the approval label.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

PROMPT = """Generate the UAC for Jira {key} using the test-plan-generation skill.
Follow the skill fully: live Jira, attachments, product and automation clones, the researcher
agents, and Experience League documentation. Do not write anything to Jira.
When finished, write these files:
1. {uac_path}: only the delivered UAC block - a flat list of "- Acceptance Criteria NN: ..." lines,
   each followed by an indented "**Source:** ..." line and, when a decision is open, a "**TBD:** ...?" line.
2. {plan_path}: the full eleven-section test plan record that passes scripts/validate_test_plan.py.
3. {decisions_path}: ONLY when the UAC has at least one TBD - a short decision request for the
   developer or product owner, in Markdown with exactly these three sections:
   "### What we found" (3-5 bullets of verified facts, each naming its source such as a doc page
   or code file), "### Decision needed" (a numbered list, one question per open TBD), and
   "### Impact on the Acceptance Criteria" (bullets saying which Acceptance Criteria each answer
   changes). No greeting, no names, no mentions. Do not write this file when there is no TBD.
4. {doc_research_path}: the result of the UAC Doc Researcher (uac-doc-researcher agent), written
   unchanged as the strict JSON object the agent returned. Run that agent for every ticket before
   writing the Acceptance Criteria; ask_dita_expert answers never replace it.
5. {source_coverage_path}: a JSON list that maps EVERY sentence and bullet of the Jira description,
   every sentence of every comment (skip comments posted by this automation), and every
   attachment to the UAC, before you write it. One object per item:
   {{"source": "description" | "comment:<id>" | "attachment:<filename>", "text": "<the exact
   sentence, copied>", "disposition": "AC" | "TBD" | "OUT_OF_SCOPE" | "NOT_MATERIAL",
   "ac": <Acceptance Criteria number, or a list when one sentence drives several criteria, for AC
   and TBD>, "reason": "<why, for OUT_OF_SCOPE and NOT_MATERIAL>"}}. A TBD must point at the
   Acceptance Criterion whose TBD line asks it. Every Acceptance Criterion must be driven by a
   ticket sentence, an attachment or a requested screen, or carry a TBD. An
   attachment entry also has "surfaces": ["<every product screen the attachment shows>"].
6. {surface_inventory_path}: a JSON list of every place in the product where the feature appears or
   where its items open, found in the documentation AND by searching the code for every reuse of each
   widget, panel, component, service or API the change touches. One object per place:
   {{"surface": "<on-screen name, e.g. Review UI>", "evidence": ["<documentation URL>" or
   "<repo file>:<line>", ...], "authority": "TICKET" | "ATTACHMENT" | "PRODUCT_DECISION" |
   "DOCUMENTATION" | "CODE_REUSE", "disposition": "AC" | "TBD" | "OUT_OF_SCOPE", "ac": <Acceptance
   Criteria number, for AC and TBD>, "reason": "<why, for OUT_OF_SCOPE>"}}. For AC, the Acceptance
   Criterion text must name the surface. A DOCUMENTATION or CODE_REUSE surface may only get an AC
   that checks it still works as before, or a TBD.
7. {hotfix_scope_path}: ONLY when the ticket is a hotfix, a backport or a private patch - the scope of
   every Acceptance Criterion, as the skill's scripts/hotfix_scope_check.py describes:
   {{"ticket_lines": [<the hotfix ticket's own requirement lines>], "diffs": [{{"repo": "<clone path>",
   "base": "<base ref>", "head": "<hotfix ref>"}}], "acs": [{{"ac": <number>, "basis": "TICKET_LINE" |
   "CHANGED_CODE" | "PARENT_TICKET" | "UNCHANGED_BEHAVIOUR", "ticket_line": "...", "files": [{{"path": "...",
   "lines": "78-89"}}]}}]}}. A parent ticket's criteria and behaviour the hotfix does not change are not
   hotfix scope, and a generic "no regression" line scopes nothing by itself.
8. {evidence_path}: the evidence record the skill's scripts/uac_completeness_check.py checks - "preflight"
   (product_rag, jira_history, live_jira, clones: available | unavailable with a reason and every route
   tried | not_applicable with a reason), at least three "rag_probes" and two "history_attempts" (use
   scripts/vm_evidence_call.py when the tools are not in your tool list), and "doc_findings": one entry per
   documentation finding of the UAC Doc Researcher, {{"finding": <1-based index>, "disposition": "AC",
   "ac": [<numbers>]}} or {{"finding": <index>, "disposition": "SET_ASIDE", "reason": "..."}}.
   Also "scenario": {{"customer_steps": [<the reporter's own steps or requested outcome, copied>], "acs":
   [{{"ac": <number>, "scenario": "CUSTOMER" | "REGRESSION", "step": "<one of customer_steps>"}} or
   {{"ac": <number>, "scenario": "ADJACENT"}} (only with a TBD)]}}, and, when the ticket says items inside
   a job, queue or batch fail or get stuck,
   "failure_path": {{"failing_item_outcome" | "remaining_items" | "user_notice": {{"disposition": "AC" |
   "TBD" | "NOT_APPLICABLE", "ac": <number>, "reason": "..."}}}}.
Write in simple English with AEM Guides names a QE sees on screen."""
SURFACE_DISPOSITIONS = ("AC", "TBD", "OUT_OF_SCOPE")
SURFACE_AUTHORITIES = ("TICKET", "ATTACHMENT", "PRODUCT_DECISION", "DOCUMENTATION", "CODE_REUSE")
DISCOVERED_AUTHORITIES = ("DOCUMENTATION", "CODE_REUSE")
REGRESSION_MARKERS = ("still", "as before", "as they do today", "as it does today", "unchanged", "not changed",
                      "does not change", "keeps", "keep working")
_CODE_REF = re.compile(r"^\S+\.[A-Za-z0-9]+:\d+(?:-\d+)?$")
SOURCE_DISPOSITIONS = ("AC", "TBD", "OUT_OF_SCOPE", "NOT_MATERIAL")
EMPTY_REASONS = {"", "n/a", "na", "none", "tbd", "-", "not material", "out of scope"}
MIN_CLAUSE_WORDS = 4
_SKIPPED_BLOCK = re.compile(r"\{(code|noformat)[^}]*\}.*?\{\1\}", re.S | re.I)
_WIKI_LINK = re.compile(r"\[([^|\]]*)\|[^\]]*\]")
_MENTION = re.compile(r"\[~[^\]]*\]")
_EMBED = re.compile(r"![^!\s][^!]*!")
_HEADING = re.compile(r"^h[1-6]\.\s*")
_BULLET = re.compile(r"^\s*(?:[*#-]+)\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
DOC_RESEARCHER = "uac-doc-researcher"
DOC_RESEARCH_STATUSES = ("ANSWER_FOUND", "PARTIAL", "NOT_FOUND", "SOURCE_UNAVAILABLE", "CONFLICTED")
DECISION_SECTIONS = ("### What we found", "### Decision needed", "### Impact on the Acceptance Criteria")


def decision_problems(ticket_dir: Path) -> list[str]:
    """Warnings (never failures) about the optional decision request."""
    uac_text = (ticket_dir / common.UAC_FILE).read_text(encoding="utf-8")
    decisions = ticket_dir / common.DECISIONS_FILE
    has_tbd = bool(re.search(r"\*\*TBD:\*\*|^\s+TBD:", uac_text, re.MULTILINE))
    if not has_tbd:
        return []
    if not decisions.is_file():
        return ["the UAC has TBDs but DECISIONS.md was not written; no decision request will be sent"]
    text = decisions.read_text(encoding="utf-8")
    missing = [s for s in DECISION_SECTIONS if s not in text]
    return [f"DECISIONS.md is missing section(s): {', '.join(missing)}; no decision request will be sent"] if missing else []


def copilot_command(config: dict, prompt: str, transcript: Path) -> list[str]:
    cop = config.get("copilot", {})
    cmd = [cop.get("command", "copilot"), "-p", prompt, "-s", "--no-ask-user", f"--share={transcript}"]
    if cop.get("model"):
        cmd.append(f"--model={cop['model']}")
    if cop.get("agent"):
        cmd.append(f"--agent={cop['agent']}")
    for directory in cop.get("add_dirs", []):
        cmd.append(f"--add-dir={directory}")
    if cop.get("allow_all_tools"):
        cmd.append("--allow-all-tools")
    for tool in cop.get("allow_tools", []):
        cmd.append(f"--allow-tool={tool}")
    for tool in cop.get("deny_tools", []):
        cmd.append(f"--deny-tool={tool}")
    return cmd


def doc_research_problems(ticket_dir: Path, prompt: str) -> list[str]:
    """Return problems unless the UAC Doc Researcher ran and returned a usable result."""
    path = ticket_dir / common.DOC_RESEARCH_FILE
    if not path.is_file():
        return [f"{common.DOC_RESEARCH_FILE} was not written: the UAC Doc Researcher did not run"]
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        return [f"{common.DOC_RESEARCH_FILE} is not valid JSON: {exc}"]
    if not isinstance(result, dict):
        return [f"{common.DOC_RESEARCH_FILE} is not a JSON object"]
    problems = []
    status = result.get("status")
    findings = result.get("findings") or []
    if status not in DOC_RESEARCH_STATUSES:
        problems.append(f"UAC Doc Researcher status is {status!r}, expected one of {', '.join(DOC_RESEARCH_STATUSES)}")
    elif status in ("ANSWER_FOUND", "PARTIAL") and not findings:
        problems.append(f"UAC Doc Researcher returned {status} with no findings")
    elif status in ("NOT_FOUND", "SOURCE_UNAVAILABLE") and not result.get("limitations"):
        problems.append(f"UAC Doc Researcher returned {status} without limitations naming what was searched")
    for number, finding in enumerate(findings, 1):
        refs = finding.get("source_refs") or []
        cites_doc = any(str(ref).startswith("doc:") for ref in refs)
        if cites_doc and not (finding.get("provenance") or {}).get("locator"):
            problems.append(f"UAC Doc Researcher finding {number} cites a doc: source without a provenance locator")
    transcript = ticket_dir / "copilot-transcript.md"
    text = transcript.read_text(encoding="utf-8", errors="replace") if transcript.is_file() else ""
    echoed = prompt.count(DOC_RESEARCHER)
    if prompt and prompt in text:
        text, echoed = text.replace(prompt, ""), 0
    if text.count(DOC_RESEARCHER) <= echoed:
        problems.append(f"the Copilot transcript shows no {DOC_RESEARCHER} run")
    return problems


def _normalize(text: str) -> str:
    text = re.sub(r"[*_{}|+^~`\"'\u2018\u2019\u201c\u201d]", " ", text.lower())
    return " ".join(text.split()).strip(" .,:;!?-")


def source_clauses(source: dict, own_name: str = "") -> list[tuple[str, str]]:
    """Split the live Jira description and human comments into sentences a UAC must cover."""
    parts = [("description", source.get("description") or "")]
    parts += [(f"comment:{c['id']}", c.get("body") or "") for c in source.get("comments") or []
              if not own_name or c.get("author") != own_name]
    clauses = []
    for label, text in parts:
        text = _EMBED.sub(" ", _MENTION.sub(" ", _WIKI_LINK.sub(r"\1", _SKIPPED_BLOCK.sub(" ", text))))
        for line in text.splitlines():
            line = _BULLET.sub("", _HEADING.sub("", line.strip()))
            for sentence in _SENTENCE_END.split(line):
                clause = _normalize(sentence)
                if len(clause.split()) >= MIN_CLAUSE_WORDS:
                    clauses.append((label, clause))
    return clauses


def source_coverage_problems(ticket_dir: Path, source: dict, own_name: str = "") -> list[str]:
    """Return problems unless every Jira sentence and attachment is mapped to the UAC."""
    path = ticket_dir / common.SOURCE_COVERAGE_FILE
    if not path.is_file():
        return [f"{common.SOURCE_COVERAGE_FILE} was not written: the ticket was not mapped to the UAC"]
    try:
        entries = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        return [f"{common.SOURCE_COVERAGE_FILE} is not valid JSON: {exc}"]
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        return [f"{common.SOURCE_COVERAGE_FILE} must be a JSON list of objects"]
    uac = (ticket_dir / common.UAC_FILE).read_text(encoding="utf-8") if (ticket_dir / common.UAC_FILE).is_file() else ""
    blocks = {int(n): body for n, body in re.findall(
        r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|\Z)", uac, re.M | re.S)}
    problems = []
    for number, entry in enumerate(entries, 1):
        disposition = entry.get("disposition")
        if disposition not in SOURCE_DISPOSITIONS:
            problems.append(f"source coverage item {number}: disposition {disposition!r} is not one of "
                            f"{', '.join(SOURCE_DISPOSITIONS)}")
        elif disposition in ("AC", "TBD"):
            acs = _ac_numbers(entry.get("ac"))
            missing_acs = [ac for ac in acs if ac not in blocks]
            if not acs or missing_acs:
                problems.append(f"source coverage item {number}: Acceptance Criteria {entry.get('ac')!r} does not exist in UAC.md")
            elif disposition == "TBD" and not any("TBD:" in blocks[ac] for ac in acs):
                problems.append(f"source coverage item {number}: Acceptance Criteria {entry.get('ac')} has no TBD line")
        elif str(entry.get("reason") or "").strip().lower() in EMPTY_REASONS:
            problems.append(f"source coverage item {number}: {disposition} needs a concrete reason")
    covered = [_normalize(str(e.get("text") or "")) for e in entries]
    missing = [(label, clause) for label, clause in source_clauses(source, own_name)
               if not any(clause in text for text in covered)]
    if missing:
        shown = "; ".join(f"{label}: \"{clause[:80]}\"" for label, clause in missing[:5])
        problems.append(f"{len(missing)} Jira sentence(s) are not mapped to the UAC, e.g. {shown}")
    mapped_files = {str(e.get("source") or "")[len("attachment:"):] for e in entries
                    if str(e.get("source") or "").startswith("attachment:")}
    for attachment in source.get("attachments") or []:
        name = attachment.get("filename")
        if name and name not in mapped_files and (not own_name or attachment.get("author") != own_name):
            problems.append(f"attachment {name} is not mapped to the UAC")
    return problems


def attachment_surface_problems(ticket_dir: Path, source: dict, own_name: str = "") -> list[str]:
    """Return problems unless every screen shown in an attachment is named and in the surface inventory."""
    try:
        coverage = json.loads((ticket_dir / common.SOURCE_COVERAGE_FILE).read_text(encoding="utf-8-sig"))
        inventory = json.loads((ticket_dir / common.SURFACE_INVENTORY_FILE).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if not isinstance(coverage, list) or not isinstance(inventory, list):
        return []
    known = {_normalize(str(e.get("surface") or "")) for e in inventory if isinstance(e, dict)}
    own_files = {a.get("filename") for a in source.get("attachments") or [] if own_name and a.get("author") == own_name}
    problems = []
    for entry in coverage:
        if not isinstance(entry, dict) or not str(entry.get("source") or "").startswith("attachment:"):
            continue
        name = str(entry["source"])[len("attachment:"):]
        if name in own_files:
            continue
        surfaces = [str(s).strip() for s in entry.get("surfaces") or [] if str(s).strip()]
        if not surfaces:
            problems.append(f"attachment {name}: list the product screens it shows in \"surfaces\"")
        for surface in surfaces:
            if _normalize(surface) not in known:
                problems.append(f"attachment {name} shows {surface}, which is not in the surface inventory")
    return problems


def _load_list(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []


def _ac_numbers(value) -> list[int]:
    """An entry's "ac" may be one Acceptance Criteria number or a list of them."""
    values = value if isinstance(value, list) else [value]
    return [v for v in values if isinstance(v, int) and not isinstance(v, bool)]


def _is_regression(text: str) -> bool:
    return any(f" {m} " in f" {_normalize(text)} " for m in REGRESSION_MARKERS)


def orphan_ac_problems(ticket_dir: Path) -> list[str]:
    """Return problems for Acceptance Criteria that no ticket line, attachment or in-scope surface asks for."""
    uac = (ticket_dir / common.UAC_FILE).read_text(encoding="utf-8") if (ticket_dir / common.UAC_FILE).is_file() else ""
    lines = {int(n): text for n, text in re.findall(r"^- Acceptance Criteria (\d+):\s*(.+)$", uac, re.M)}
    blocks = {int(n): body for n, body in re.findall(
        r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|\Z)", uac, re.M | re.S)}
    coverage = _load_list(ticket_dir / common.SOURCE_COVERAGE_FILE)
    inventory = _load_list(ticket_dir / common.SURFACE_INVENTORY_FILE)
    from_ticket = {ac for e in coverage if e.get("disposition") in ("AC", "TBD") for ac in _ac_numbers(e.get("ac"))}
    in_scope = [e for e in inventory if e.get("disposition") in ("AC", "TBD")]
    requested = [e for e in in_scope if e.get("authority") not in DISCOVERED_AUTHORITIES]

    def names(entries, number, text):
        return any(number in _ac_numbers(e.get("ac")) or _normalize(str(e.get("surface") or "")) in _normalize(text)
                   for e in entries if str(e.get("surface") or "").strip())

    problems = []
    for number, text in sorted(lines.items()):
        if number in from_ticket or names(requested, number, text) or "TBD:" in blocks.get(number, ""):
            continue
        if names(in_scope, number, text) and _is_regression(text):
            continue
        problems.append(f"Acceptance Criteria {number} is not tied to any ticket sentence, attachment or requested "
                        "surface; remove it, tie it to the ticket, or add a TBD for the product owner")
    for number, body in sorted(blocks.items()):
        source = re.search(r"Source:\**\s*(.+)", body)
        if source and _normalize(source.group(1)).startswith("qe reasoning") and "TBD:" not in body:
            problems.append(f"Acceptance Criteria {number} rests only on QE reasoning; add a TBD that asks the "
                            "product owner, or remove it")
    return problems


def ticket_problems(ticket_dir: Path, prompt: str, source: dict | None, own_name: str = "") -> list[str]:
    """Every check the runner applies to a generated UAC folder."""
    problems = (check_outputs(ticket_dir) + doc_research_problems(ticket_dir, prompt)
                + surface_inventory_problems(ticket_dir)
                + common.import_skill_module("uac_completeness_check").evidence_problems(ticket_dir))
    if source is not None:
        problems += source_coverage_problems(ticket_dir, source, own_name)
        problems += attachment_surface_problems(ticket_dir, source, own_name)
        problems += hotfix_scope_problems(ticket_dir, source)
    return problems


def hotfix_scope_problems(ticket_dir: Path, source: dict) -> list[str]:
    """For a hotfix or backport ticket, every Acceptance Criterion must rest on a hotfix ticket line or on code
    the hotfix diff changes (skill script hotfix_scope_check.py); other tickets are not checked."""
    scope_check = common.import_skill_module("hotfix_scope_check")
    if not scope_check.is_hotfix(source.get("summary") or "", source.get("description") or ""):
        return []
    path = ticket_dir / common.HOTFIX_SCOPE_FILE
    if not path.is_file():
        return [f"{common.HOTFIX_SCOPE_FILE} was not written: this is a hotfix ticket, so every Acceptance Criterion "
                "must be tied to a hotfix ticket line or to code the hotfix changes"]
    try:
        scope = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        return [f"{common.HOTFIX_SCOPE_FILE} is not valid JSON: {exc}"]
    uac = (ticket_dir / common.UAC_FILE).read_text(encoding="utf-8") if (ticket_dir / common.UAC_FILE).is_file() else ""
    return [f"hotfix scope: {p}" for p in scope_check.check(scope, uac)]


def surface_inventory_problems(ticket_dir: Path) -> list[str]:
    """Return problems unless every place the feature appears is found in docs and code and covered."""
    path = ticket_dir / common.SURFACE_INVENTORY_FILE
    if not path.is_file():
        return [f"{common.SURFACE_INVENTORY_FILE} was not written: the places the feature appears were not listed"]
    try:
        entries = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        return [f"{common.SURFACE_INVENTORY_FILE} is not valid JSON: {exc}"]
    if not isinstance(entries, list) or not entries or not all(isinstance(e, dict) for e in entries):
        return [f"{common.SURFACE_INVENTORY_FILE} must be a non-empty JSON list of objects"]
    uac = (ticket_dir / common.UAC_FILE).read_text(encoding="utf-8") if (ticket_dir / common.UAC_FILE).is_file() else ""
    lines = {int(n): text for n, text in re.findall(r"^- Acceptance Criteria (\d+):\s*(.+)$", uac, re.M)}
    blocks = {int(n): body for n, body in re.findall(
        r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|\Z)", uac, re.M | re.S)}
    problems, has_doc, has_code = [], False, False
    for number, entry in enumerate(entries, 1):
        surface = str(entry.get("surface") or "").strip()
        label = f"surface {number} ({surface or 'unnamed'})"
        if not surface:
            problems.append(f"{label}: no surface name")
        evidence = [str(e).strip() for e in entry.get("evidence") or [] if str(e).strip()]
        docs = [e for e in evidence if e.startswith(("https://", "http://"))]
        code = [e for e in evidence if _CODE_REF.match(e)]
        has_doc, has_code = has_doc or bool(docs), has_code or bool(code)
        if not evidence:
            problems.append(f"{label}: no evidence")
        elif len(docs) + len(code) < len(evidence):
            problems.append(f"{label}: evidence must be a documentation URL or a <file>:<line> code reference")
        authority = entry.get("authority")
        if authority not in SURFACE_AUTHORITIES:
            problems.append(f"{label}: authority {authority!r} is not one of {', '.join(SURFACE_AUTHORITIES)}")
        disposition = entry.get("disposition")
        if disposition not in SURFACE_DISPOSITIONS:
            problems.append(f"{label}: disposition {disposition!r} is not one of {', '.join(SURFACE_DISPOSITIONS)}")
        elif disposition in ("AC", "TBD"):
            ac = entry.get("ac")
            if not isinstance(ac, int) or ac not in lines:
                problems.append(f"{label}: Acceptance Criteria {ac!r} does not exist in UAC.md")
            elif disposition == "AC" and _normalize(surface) not in _normalize(lines[ac]):
                problems.append(f"{label}: Acceptance Criteria {ac} does not name this surface")
            elif (disposition == "AC" and authority in DISCOVERED_AUTHORITIES
                  and not any(f" {m} " in f" {_normalize(lines[ac])} " for m in REGRESSION_MARKERS)):
                problems.append(f"{label}: found only by {authority}, so Acceptance Criteria {ac} may only check that it "
                                "still works as before; ask about new behaviour there in a TBD")
            elif disposition == "TBD" and "TBD:" not in blocks[ac]:
                problems.append(f"{label}: Acceptance Criteria {ac} has no TBD line")
        elif str(entry.get("reason") or "").strip().lower() in EMPTY_REASONS:
            problems.append(f"{label}: OUT_OF_SCOPE needs a concrete reason")
    if not has_doc:
        problems.append("the surface inventory cites no documentation page")
    if not has_code:
        problems.append("the surface inventory cites no code reference: search the code for every reuse")
    return problems


def check_outputs(ticket_dir: Path) -> list[str]:
    """Return problems with the generated files; an empty list means ready to draft."""
    problems = []
    uac, plan = ticket_dir / common.UAC_FILE, ticket_dir / common.PLAN_FILE
    for path in (uac, plan):
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            problems.append(f"{path.name} was not written")
    if problems:
        return problems
    result = subprocess.run(
        [sys.executable, str(common.SKILL_SCRIPTS / "validate_test_plan.py"), str(plan)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        problems.append("test plan failed validate_test_plan.py: " + (result.stdout + result.stderr).strip()[-600:])
    text = uac.read_text(encoding="utf-8")
    count = len(re.findall(r"^- Acceptance Criteria \d+:", text, re.MULTILINE))
    if not 1 <= count <= 10:
        problems.append(f"UAC.md has {count} Acceptance Criteria (expected 1-10)")
    vocabulary = common.import_skill_module("guides_vocabulary")
    lines = "\n".join(f"- AC-{i:02d}: {m}" for i, m in enumerate(
        re.findall(r"^- Acceptance Criteria \d+:\s*(.+)$", text, re.MULTILINE), 1))
    blocked, _ = vocabulary.check(lines)
    problems.extend(f"vocabulary: {b}" for b in blocked)
    return problems


def draft_comment(field_body: str, plan_name: str, decision_body: str = "", mention_note: str = "",
                  review_notes: list[str] | None = None) -> str:
    text = (
        "*Draft UAC ready for QE review* (generated automatically, not yet in the Acceptance Criteria field)\n"
        "* To approve, add the label *UAC_Approved*. The criteria below are then copied into the "
        "Acceptance Criteria field unchanged.\n"
        "* To change the criteria, approve and then edit the Acceptance Criteria field; your edits are "
        "learned automatically.\n"
        f"* Full test plan: [^{plan_name}]\n\n" + field_body
    )
    if review_notes:
        text += ("\n\n----\n*Please check before approving* (automatic review notes)\n"
                 + "".join(f"* {note}\n" for note in review_notes))
    if decision_body:
        text += (
            "\n\n----\n*Decision request* (posted as its own comment after approval"
            + (f", tagging {mention_note}" if mention_note else "")
            + ")\n\n" + decision_body
        )
    return text


def decision_mention_note(config: dict) -> str:
    settings = config.get("decision_comment") or {}
    if not settings.get("enabled"):
        return ""
    who = [f"the {role}" for role in settings.get("mention", [])] + [f"[~{u}]" for u in settings.get("cc", [])]
    return ", ".join(who)


def process_ticket(key: str, config: dict, jira, logger, dry_run: bool) -> str:
    out_root = Path(config["output_dir"])
    ticket_dir = out_root / key
    status = common.read_status(ticket_dir)
    if status.get("state") in {"DRAFT_POSTED", "POSTED"} and not config.get("regenerate_existing"):
        logger.info("%s: already %s, skipping", key, status["state"])
        return "SKIPPED"
    ticket_dir.mkdir(parents=True, exist_ok=True)
    common.archive_attempt(ticket_dir, int(config.get("keep_attempts", 5)))
    for name in (common.UAC_FILE, common.PLAN_FILE, common.DECISIONS_FILE, common.DECISION_BODY_FILE,
                 common.DOC_RESEARCH_FILE, common.SOURCE_COVERAGE_FILE, common.JIRA_SOURCE_FILE,
                 common.SURFACE_INVENTORY_FILE, common.HOTFIX_SCOPE_FILE, common.EVIDENCE_FILE):
        (ticket_dir / name).unlink(missing_ok=True)
    prompt = PROMPT.format(key=key, uac_path=ticket_dir / common.UAC_FILE, plan_path=ticket_dir / common.PLAN_FILE,
                           decisions_path=ticket_dir / common.DECISIONS_FILE,
                           doc_research_path=ticket_dir / common.DOC_RESEARCH_FILE,
                           source_coverage_path=ticket_dir / common.SOURCE_COVERAGE_FILE,
                           surface_inventory_path=ticket_dir / common.SURFACE_INVENTORY_FILE,
                           hotfix_scope_path=ticket_dir / common.HOTFIX_SCOPE_FILE,
                           evidence_path=ticket_dir / common.EVIDENCE_FILE)
    cmd = copilot_command(config, prompt, ticket_dir / "copilot-transcript.md")
    timeout = int(config.get("copilot", {}).get("timeout_minutes", 45)) * 60
    started = time.time()
    logger.info("%s: running Copilot CLI", key)
    try:
        run = subprocess.run(cmd, cwd=common.REPO_ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout)
        (ticket_dir / "copilot-output.txt").write_text(run.stdout + "\n" + run.stderr, encoding="utf-8")
        exit_code = run.returncode
    except subprocess.TimeoutExpired:
        exit_code = "timeout"
    status.update({"key": key, "copilot_exit": exit_code, "copilot_seconds": round(time.time() - started)})
    if exit_code != 0:
        problems = [f"Copilot CLI exit {exit_code}"]
    else:
        source, own_name, fetch_problem = None, "", []
        try:
            source = jira.get_source(key)
            own_name = str((jira.myself() or {}).get("name") or "")
        except Exception as exc:  # noqa: BLE001 - without the live ticket text the UAC cannot be checked
            fetch_problem = [f"could not read the Jira ticket to check source coverage: {exc}"]
        else:
            (ticket_dir / common.JIRA_SOURCE_FILE).write_text(
                json.dumps(source, indent=2, ensure_ascii=False), encoding="utf-8")
        problems = ticket_problems(ticket_dir, prompt, source, own_name) + fetch_problem
    if problems:
        status.update(state="FAILED", problems=problems)
        common.write_status(ticket_dir, status)
        logger.error("%s: not drafted - %s", key, "; ".join(problems))
        return "FAILED"
    jira_text = common.import_skill_module("jira_safe_text")
    field_body = jira_text.jira_field_body((ticket_dir / common.UAC_FILE).read_text(encoding="utf-8"))
    (ticket_dir / "field-body.txt").write_text(field_body, encoding="utf-8")
    status.update(state="READY", problems=[], uac_sha256=common.sha256_file(ticket_dir / common.UAC_FILE))
    warnings = decision_problems(ticket_dir)
    decision_body = ""
    if not warnings and (ticket_dir / common.DECISIONS_FILE).is_file():
        decision_body = jira_text.jira_wiki_from_markdown(
            (ticket_dir / common.DECISIONS_FILE).read_text(encoding="utf-8"))
        (ticket_dir / common.DECISION_BODY_FILE).write_text(decision_body, encoding="utf-8")
        status["decisions_sha256"] = common.sha256_file(ticket_dir / common.DECISIONS_FILE)
    status["warnings"] = warnings
    review_notes = orphan_ac_problems(ticket_dir)
    status["review_notes"] = review_notes
    for warning in warnings + review_notes:
        logger.warning("%s: %s", key, warning)
    if dry_run:
        common.write_status(ticket_dir, status)
        logger.info("%s: ready (dry run, nothing posted)", key)
        return "READY"
    labels = config["labels"]
    plan_copy = ticket_dir / f"{key}-test-plan.md"
    shutil.copyfile(ticket_dir / common.PLAN_FILE, plan_copy)
    attachment_id = jira.attach_file(key, plan_copy)
    comment_id = jira.add_comment(key, draft_comment(field_body, plan_copy.name, decision_body,
                                                     decision_mention_note(config), review_notes))
    jira.update_labels(key, add=[labels["draft"]])
    status.update(state="DRAFT_POSTED", comment_id=comment_id, attachment_id=attachment_id)
    common.write_status(ticket_dir, status)
    logger.info("%s: draft posted (comment %s)", key, comment_id)
    return "DRAFT_POSTED"


def health(config: dict, jira, logger) -> list[str]:
    problems = []
    try:
        me = jira.myself()
        logger.info("Jira auth OK as %s", me.get("name") or me.get("displayName"))
    except Exception as exc:  # noqa: BLE001 - report any auth/network failure the same way
        problems.append(f"Jira: {exc}")
    url = config.get("mcp_health_url")
    if url:
        ok, detail = common.check_url(url)
        (logger.info if ok else logger.error)("Dataset Studio MCP %s: %s", url, detail)
        if not ok:
            problems.append(f"Dataset Studio MCP unreachable ({detail}); documentation research would be skipped")
    if not shutil.which(config.get("copilot", {}).get("command", "copilot")):
        problems.append("Copilot CLI not found on PATH")
    return problems


def check_dir(ticket_dir: Path, own_name: str = "") -> int:
    """Run every runner check on an existing UAC folder, e.g. one edited by hand before posting."""
    source_file = ticket_dir / common.JIRA_SOURCE_FILE
    source = json.loads(source_file.read_text(encoding="utf-8")) if source_file.is_file() else None
    problems = ticket_problems(ticket_dir, "", source, own_name)
    if source is None:
        problems.append(f"{common.JIRA_SOURCE_FILE} is missing, so ticket coverage was not checked")
    for note in orphan_ac_problems(ticket_dir):
        print(f"WARN: {note}")
    for problem in problems:
        print(f"FAIL: {problem}")
    print("PASS: every runner check passed" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check-dir", type=Path,
                        help="only run every check on an existing UAC folder and exit (no Copilot, no Jira writes)")
    parser.add_argument("--own-name", default="", help="with --check-dir: the automation's Jira user, to skip its comments")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--env-file", type=Path, default=common.REPO_ROOT / "backend" / ".env")
    parser.add_argument("--ticket", action="append", help="process only these keys (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="generate and check, but write nothing to Jira")
    args = parser.parse_args(argv)
    if args.check_dir:
        return check_dir(args.check_dir, args.own_name)
    if not args.config:
        parser.error("--config is required unless --check-dir is used")

    common.load_env_file(args.env_file)
    config = common.load_config(args.config)
    out = Path(config["output_dir"])
    logger = common.setup_logging(out / "logs", "uac-runner")
    run_id, started = common.new_run_id(), time.time()
    logger.info("run %s started%s", run_id, " (dry run)" if args.dry_run else "")
    common.prune_logs(out / "logs", int(config.get("log_retention_days", 30)), logger)
    results: dict[str, str] = {}
    errors: dict[str, str] = {}
    health_problems: list[str] = []
    alerts: list[str] = []
    jira = None
    try:
        jira = common.JiraClient.from_env()
        with common.RunLock(out / "runner.lock", int(config.get("lock_max_age_minutes", 720)) * 60):
            health_problems = health(config, jira, logger)
            for p in health_problems:
                logger.error("health: %s", p)
            if not health_problems:
                keys = args.ticket or config.get("tickets") or jira.search_keys(
                    config["jql"], int(config.get("max_tickets", 100)))
                logger.info("tickets: %s", ", ".join(keys) or "none")
                results, errors = common.run_each(
                    keys, lambda key: process_ticket(key, config, jira, logger, args.dry_run), logger, out)
        exit_code = 2 if health_problems else 1 if any(v in ("FAILED", "ERROR") for v in results.values()) else 0
    except Exception as exc:  # noqa: BLE001 - record and alert on anything that stops the run
        logger.exception("run %s stopped", run_id)
        alerts.append(f"The run stopped before finishing: {type(exc).__name__}: {exc}")
        exit_code = 3
    alerts = [f"Health check failed, no tickets processed: {p}" for p in health_problems] + alerts
    for key, result in results.items():
        if result == "ERROR":
            alerts.append(f"{key}: unexpected error - {errors.get(key, 'see the log')}")
        elif result == "FAILED":
            problems = common.read_status(out / key).get("problems") or ["see status.json"]
            more = f" (and {len(problems) - 1} more)" if len(problems) > 1 else ""
            alerts.append(f"{key}: draft not posted - {problems[0]}{more}")
    logger.info("summary: %s", results)
    common.append_run_record(out, {
        "run_id": run_id, "tool": "uac-runner", "dry_run": args.dry_run,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
        "seconds": round(time.time() - started), "exit_code": exit_code, "tickets": results,
        "errors": errors, "health_problems": health_problems, "alerts": alerts})
    if args.dry_run:
        for line in alerts:
            logger.warning("alert (dry run, not sent): %s", line)
    elif jira is not None:
        common.send_alert(config, jira, logger, "uac-runner", run_id, alerts)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
