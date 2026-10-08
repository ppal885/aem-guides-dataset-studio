#!/usr/bin/env python3
"""Generate the UAC for every release ticket with GitHub Copilot CLI and write it to Jira.

One scheduled run:
  1. health checks: Jira auth, Dataset Studio MCP health URL, Copilot CLI present;
  2. finds tickets with the configured JQL;
  3. downloads the wiki pages the ticket links to (design documents; WIKI_PAT) and
     runs `copilot -p` once per ticket with the test-plan-generation skill, writing
     UAC.md, test-plan.md, the UAC Doc Researcher result and the source coverage map
     into <output_dir>/<KEY>/;
  4. checks the files (plan validator, AC count 1-10, blocked vocabulary), that the
     UAC Doc Researcher actually ran, and that every sentence of the live Jira
     description and comments, and every attachment, is mapped to the UAC, and that every
     place the feature appears (from documentation and code) is covered;
  5. writes the UAC into an empty Acceptance Criteria field, checks the field rendered,
     attaches the plan, comments (review notes), adds the posted label
     (the UAC was written by the skill) and, when the UAC has TBDs, sends the decision
     request (DECISIONS.md) as its own comment. A field that already holds text is never
     overwritten.

Copilot never writes to Jira: its Jira write tools are denied in the config and
all Jira writes happen here, after the checks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import linked_docs  # noqa: E402

PROMPT = """Generate the UAC for Jira {key} using the test-plan-generation skill.
Follow the skill fully: live Jira, attachments, product and automation clones, the researcher
agents, and Experience League documentation. Do not write anything to Jira.
Linked documents: {linked_docs_path} lists every wiki page (design document, specification) and every pull
request linked from the ticket. The runner already downloaded each page with status READ into the file named in "file"; read every
one in full before writing the Acceptance Criteria, and do not try to open the wiki yourself. A design
document is the developer's or product owner's decision for what it specifies (endpoint, inputs, responses,
status values, errors, permissions, limits, configuration): a behaviour it states is an Acceptance Criterion
whose Source line names the document title, not a TBD. Ask a TBD only for what the document leaves open or
marks as still under review. For a page with status UNREADABLE, the TBD for what it would decide names the
document title or link.
When finished, write these files:
1. {uac_path}: only the delivered UAC block - a flat list of "- Acceptance Criteria NN: ..." lines,
   each followed by an indented "**Source:** ..." line and, when a decision is open, a "**TBD:** ...?" line.
   Acceptance Criteria are what the ticket, an attachment, a product decision or the confirmed fix asks
   for, and QE regression checks around the reporter's scenario. A check your own research found
   (documentation, code, a similar or parent ticket's UAC, an investigator's other scenario, parity) that
   matters is also an Acceptance Criterion - usually a "still works as before" check, or a sub-point of the
   criterion with the same outcome - and its Source line names the documentation page, code or ticket.
   Research checks that do not matter enough go to the full test plan (file 2), not to the UAC. There is no
   "Suggested checks" section. Keep at most ten criteria; an open product decision stays a TBD.
   Keep the criteria (with sub-points, Scope and Out of scope) within 350 words and each Source line within
   30 words: name the ticket, comment, attachment, design document or documentation page title, or the fix
   pull request. Never a clone revision or commit hash, a file path, or a class, method or test name: those
   go in the test plan (the runner removes them from Source lines).
   State each criterion as the expected outcome in plain words (no "Verify that" prefix is needed): one thing
   a QE can check, in at most two clauses, using only names shown on screen. Exact technical values - API
   paths and fields, setting values, status codes, file names - go in a sub-point, never in the statement
   (statement "An invalid request is rejected and returns no results", sub-point "returns 400").
   Use the everyday AEM Guides words QE use: topic reference, map reference, direct reference, indirect
   reference, DITA map, bookmap, topic, DITA files, non-DITA files, images, asset update, Map console, Map
   dashboard, publishing, review, postprocessing, DAM Update Asset workflow, Cloud (AEMaaCS), doc state,
   Global Profile, XML Editor Configuration, ui config, Repository View, Layout View, Preview, Side By Side
   View, Content Fragment, Download, Download Map, forward reference, backward reference, output presets,
   PDF preset (say Native PDF or DITA-OT), Workfront, conref, conkeyref, keyref, fmditaTitle, dc:title,
   asset state, Tags View and non-tag view, new baseline (V2) and old baseline (V1) - say which baseline,
   new AEM Sites (the same as Native AEM Sites) and old AEM Site (DITA-OT based) - say which AEM Sites output,
   output, the output preset tabs (General, Metadata, Layout, Security, Print, Advanced) - name the tab -,
   Using DITAVAL and Using condition preset (Conditional filtering), Author view, Source view, Side-by-side,
   Preview, left panel, right panel (File properties), breadcrumb, editor search bar - name the Editor area -,
   Outline Panel, Glossary panel, Templates panel, Snippets Panel, Subject Scheme Panel, Find and Replace, Map
   Panel, Collections, PDF templates, variables, language variables, Workspace Settings, Publish profile,
   Assets View, element, tag, attribute, friendly names (use the friendly name the Editor shows), toggle on
   and toggle off for a switch on screen ("with Enable DITA-OT preprocessing toggled off"). For a Workspace
   settings option name the tab, section and toggle as shown (General tab, Condition, "Highlight conditional
   text in the Author view"); a panel shown or hidden from the Panels tab keeps its name there (Reusable
   content, Output templates, Data sources, Citations). Name a metadata property by its Label (Title, Document
   State, Tags); its Metadata Path (metadata/cq:tags) goes in a sub-point. Validation tab: "Run validation check
   before saving the file", "Allow all users to add schematron files in validation panel", Schematron Files.
   Translation tab: Language groups, "Propagate source version labels to the target version", "Translation
   project cleanup after completion" (None, Disable, Delete). Context menu, Copy UUID, Copy path, Locate in,
   schematron file(s), Single Topic Publishing (STP). In the References section use "Used in" (backward
   references) and "Outgoing links" (forward references). Top toolbar (Menu, Insert image, Multimedia), ellipses
   menu (Cross-reference, Reusable content, Symbol, Snippets, Keyword), Save as new version dialog (Last
   Version, Comments for new version, Version labels), Menu dropdown (Cut, Copy, Delete, Version label, Merge),
   check out, check in, Repository Search, the Explorer folder options menu and file options menu (Upload assets,
   Find files in folder, Reprocess asset(s), View in Assets UI, Edit in Oxygen, Unlock, Duplicate, Move to,
   Rename, Generate) - name the menu and the option. Right panel Content properties (Type, Attributes); options
   menu at the top right (Assets, Editor settings, Workspace settings). Element context menu in Author view
   (Rename element, Surround with element, Unwrap element, Insert before, Insert after, Create snippet, Generate
   IDs); Map Panel selection bar (Save as new version and unlock); Collections panel (Lightbox); app switcher
   (Home, Editor, Map console); Map console left panel (Output presets, Reports, Baseline, Condition presets,
   Translation); Map console map dropdown (Open in editor, Select another map); New output preset Type (AEM Sites, PDF, Knowledge Base, HTML5, JSON, Custom, SCORM).
   A DITA element name (topicref, mapref, reltable), a file extension or an
   XML word goes in a sub-point, never in the statement.
   Shortening never merges, drops or renames a named product item (a map template and a topic template are
   different); shorten by moving detail to sub-points. Before rewriting a criterion, re-read the ticket's
   description, comments and attachments: a comment that names the screen decides which screen it is about.
   A documentation answer marked not verified, or one citing unrelated pages, can only be a TBD.
   Every criterion is a product check a QE can run on a test instance. Engineering, support and operations
   deliverables are not criteria: an incident record or root-cause write-up, a post-mortem, a timing or
   performance report, a rollback or mitigation of a customer environment, a folder or access an Adobe team
   sets up for the customer, monitoring. Put them in the test plan; when the ticket asks for one, its
   product outcome (the output generates, the move completes) is the criterion instead. Documentation is a
   criterion only when the ticket itself asks for documentation.
   Under a criterion, list up to five short cases of the same outcome as indented "  - ..." lines when it
   has a construct or case matrix. A case is the condition that varies, in plain words (about twelve words
   or fewer); test data - customer topic and file names, preset and DITAVAL names, sample titles - goes in
   the test plan's "Test data to prepare", never in a case line. A fact the ticket or a developer comment already decided (a feature
   flag, a preset argument, a default, a parity target such as "same as AEM Sites") is written as a
   criterion, not a TBD. When the ticket or a product decision sets the scope, add a "Scope: ..." line
   before the first criterion and an "Out of scope:" line with "- ..." items right after the criteria.
   When fix_basis (below) is UNCONFIRMED, the first line is exactly:
   "Note: The root cause and the fix are not confirmed yet. These criteria cover what the customer
   reported and will be checked again when the fix is known."
   When it is PROPOSED, the first line is exactly: "Note: A fix is proposed in a linked pull request but is
   not reviewed yet. These criteria cover what the customer reported and the proposed fix, and will be
   checked again when the fix is final." CONFIRMED and NOT_A_DEFECT have no Note line.
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
   {{"source": "description" | "comment:<id>" | "attachment:<filename>" | "linked:<url from {linked_docs_path}>",
   "text": "<the exact
   sentence, copied; for a linked page, the requirement copied from it>", "disposition": "AC" | "TBD" | "OUT_OF_SCOPE" | "NOT_MATERIAL",
   "ac": <Acceptance Criteria number, or a list when one sentence drives several criteria, for AC
   and TBD>, "reason": "<why, for OUT_OF_SCOPE and NOT_MATERIAL>"}}. A TBD must point at the
   Acceptance Criterion whose TBD line asks it. Every Acceptance Criterion must be driven by a
   ticket sentence, an attachment, a linked page or a requested screen, or carry a TBD. An
   image, video or document attachment entry also has "surfaces": ["<every product screen the attachment
   shows>"]; a log, data or code attachment does not. Every attachment entry from a person (not this
   automation) also has "facts": [{{"fact": "<what it shows, in plain words>", "disposition": "AC" | "TBD" |
   "NOT_MATERIAL", "ac": <number, for AC and TBD>, "reason": "<for NOT_MATERIAL>"}}] - every configuration
   value it shows (every preset, profile or setting visible on the item, not only the one the reporter
   used, e.g. another preset of the same map that uses a baseline), every status it shows (status icon or
   colour, a "queued" or "success" message) and every log line that states a count or a starting state
   (e.g. "Found 0 existing published pages", "Starting regeneration for 5 topic(s)", "BUILD SUCCESSFUL"
   followed by no output). For a video, look at a frame at least every two seconds and at every screen
   change, not a handful of samples. Also add each fact to the evidence catalog. A fact about the
   reported item's starting state is a precondition of the criterion (or a TBD when the ticket does not
   say which state is expected); a configuration on the same item that differs from the reporter's is a
   case of the criterion. Status pings (ETA or update requests), bot notices,
   credential lines and access links are not requirements: leave them out and never copy credentials.
6. {surface_inventory_path}: a JSON list of every place in the product where the feature appears or
   where its items open, found in the documentation AND by searching the code for every reuse of each
   widget, panel, component, service or API the change touches. One object per place:
   {{"surface": "<on-screen name, e.g. Review UI>", "evidence": ["<documentation URL>" or
   "<repo file>:<line>", ...], "authority": "TICKET" | "ATTACHMENT" | "PRODUCT_DECISION" |
   "DOCUMENTATION" | "CODE_REUSE", "disposition": "AC" | "TBD" | "OUT_OF_SCOPE" | "TEST_PLAN", "ac":
   <Acceptance Criteria number, for AC and TBD>, "reason": "<why, for OUT_OF_SCOPE>"}}. For AC, the
   Acceptance Criterion text must name the surface. A DOCUMENTATION or CODE_REUSE surface may only get an
   AC that checks it still works as before, or a TBD; when it does not matter enough for the UAC it is
   TEST_PLAN (the full test plan, file 2, names it). One criterion names at most {max_discovered} such
   surfaces.
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
   "ac": [<numbers>]}}, {{"finding": <index>, "disposition": "TEST_PLAN"}} (the test plan names it) or
   {{"finding": <index>, "disposition": "SET_ASIDE", "reason": "..."}}.
   Also "scenario": {{"customer_steps": [<the reporter's own steps or requested outcome, copied>], "acs":
   [{{"ac": <number>, "scenario": "CUSTOMER" | "REGRESSION" | "VARIANT", "step": "<one of customer_steps>"}} or
   {{"ac": <number>, "scenario": "ADJACENT"}} for a research check on a scenario the reporter did not hit; at
   least one criterion follows the reporter's own scenario]}}.
   Also "scope_boundaries": [{{"boundary": "<a limit the ticket, a developer or product decided, e.g. V2
   baseline is out of scope>", "basis": "TICKET" | "ATTACHMENT" | "PRODUCT_DECISION" | "DEVELOPER_COMMENT",
   "disposition": "OUT_OF_SCOPE" (named in the UAC's Out of scope list) | "AC", "ac": <number>}}] (or [] with
   "scope_boundaries_reason").
   Also "action_variants": {{"entry_points": [{{"name": "<route, e.g. toolbar insert>", "basis": "TICKET" |
   "ATTACHMENT" | "PRODUCT_DECISION" | "DEVELOPER_COMMENT" | "DOCUMENTATION" | "CODE", "disposition": "AC" |
   "TBD" | "NOT_APPLICABLE" | "TEST_PLAN" (DOCUMENTATION or CODE basis, same outcome as an AC; the test plan
   names it and the UAC stays short), "ac": <number>, "reason":
   "..."}}], "config_switches": [{{"name": "...", "basis": "...", "states": ["enabled", "disabled"],
   "disposition": "AC", "acs": [<numbers>]}}] (or [] with "config_switches_reason"), "mechanism":
   {{"general_ask": true | false, "variants": [<same shape as entry_points>], "reason": "...",
   "reverse_action": {{"name": "<e.g. move the item back>", "disposition": "TEST_PLAN" | "AC" | "TBD" |
   "NOT_APPLICABLE", "basis": "<for AC only: TICKET | ATTACHMENT | PRODUCT_DECISION | DEVELOPER_COMMENT>",
   "ac": <number>, "reason": "..."}}, "item_origin": {{<same shape, e.g. an item created in the target
   folder>}}, "value_shapes": {{<same shape, plus "shapes": ["empty", "missing", "special characters", ...]
   - the forms of the value the change reads or shows; an AC names each shape>}}}}, "input_sources": [<same shape
   as entry_points: where pasted, imported or uploaded content can come from, at least two, e.g. Word, Google
   Docs, Excel, a web page>]}} - every route to the ticket's action (for an output ticket: the output preset from the map,
   Map Collection, a baseline, for PDF Download as PDF, and for a changed preset setting a profile preset
   template applied with Apply Preset Changes), the result in each state of every switch that changes
   it, the other item or reference types when the ticket asks for general behaviour, the action done the
   other way round, and an item with a different history. These are criteria (scenario VARIANT) that name
   the route, state or type. One known only from the code (basis CODE) is a TBD, TEST_PLAN, or an AC that
   checks it still works as before.
   Also "pre_existing_items": {{"disposition": "AC" | "TBD" | "NOT_APPLICABLE", "ac": <number>, "outcome":
   "UNCHANGED" | "CHANGED", "basis": "<TICKET | ATTACHMENT | PRODUCT_DECISION | DEVELOPER_COMMENT, needed for
   CHANGED>", "quote": "<for CHANGED: the ticket sentence that decided it, copied>", "reason": "..."}} - what
   happens to content, presets, output or settings created before the
   change. Do not guess new behaviour for them: existing items usually stay as they are.
   When the ticket changes generated output, also "output_setting": {{"disposition": "AC" | "TBD" |
   "NOT_APPLICABLE", "ac": <number>, "basis": "PRODUCT_DECISION" | "DEVELOPER_COMMENT", "reason": "..."}} -
   whether the new behaviour is behind a setting and off by default (ask in a TBD when nobody decided it).
   Also "shared_consumers": {{"mechanism": "<what the change touches that other screens read>", "consumers":
   [{{"name": "<screen, e.g. outline panel>", "disposition": "AC" | "TEST_PLAN" | "NOT_APPLICABLE", "ac":
   <number>, "reason": "..."}}]}} (or "consumers": [] with "reason") - list the AC consumers as sub-points of one
   "still works as before" criterion.
   Also "fix_basis": {{"status": "CONFIRMED", "signal": "<the ticket text, copied, that reports the root
   cause, fix or merged pull request>"}}, {{"status": "PROPOSED", "signal": "<the ticket text, copied, that
   links a fix pull request nobody has reviewed or merged>"}}, {{"status": "NOT_A_DEFECT", "reason": "<the new
   capability or change the ticket asks for, e.g. a new API or template field, an access or permission change,
   an enhancement or documentation>"}} or {{"status": "UNCONFIRMED",
   "reason": "<why, when the ticket has a root-cause or fix comment that is not the fix>"}}. Every pull
   request listed in {linked_docs_path} (kind "pull_request") is a fix someone proposed: fetch it in the
   matching clone (git fetch origin pull/<number>/head, or the branch named in the comment) and read the
   diff. Its Acceptance Criteria check what the fix changes and the risks it introduces (for example a
   lookup that now returns an empty list must not look like "no results", and a skipped check must not
   remove a protection such as a delete warning). Many tickets never get a root cause: UNCONFIRMED is fine,
   but then no Acceptance Criterion except a REGRESSION check may rest only on code. And, when the
   ticket says that some of several
   items in one job, queue or batch fail or get stuck while others go through (one item in a job is not a
   batch; do not ask about partial failure the ticket never raised),
   "failure_path": {{"failing_item_outcome" | "remaining_items" | "user_notice": {{"disposition": "AC" |
   "TBD" | "NOT_APPLICABLE", "ac": <number>, "reason": "..."}}}}.
   Also "similar_uacs": run the skill's scripts/similar_uac_compare.py (--ticket-source the ticket's
   jira-source.json, --key, --component, --evidence this file; for a hotfix or backport add --also with its
   parent ticket) and answer every listed dimension of the
   similar human UACs with "disposition": "AC" | "TBD" | "TEST_PLAN" | "NOT_APPLICABLE", "ac" and "reason".
Canonical runtime research: your environment already sets AGENT_RESEARCH_MODE=copilot_host and
AGENT_RESEARCH_STORE={research_store}. Run the canonical runtime locally with the backend's Python -
{runtime_python} scripts/run_test_plan_pipeline.py {key} - and never with --http, which writes the research requests to the backend's own store where nobody
answers them. When it returns waiting_for_agent_research, answer EVERY request before anything else:
list them with {runtime_python} scripts/agent_research_bridge.py pending --store {research_store}, delegate each to the
registered agent named by its worker_role (task tool, background mode, the whole batch at once), and submit
each agent's strict JSON result with {runtime_python} scripts/agent_research_bridge.py fulfill-agent --store
{research_store} --execution-id <id> --result <file> --model <model>. Then run the same runtime command
again. Repeat for up to three passes; questions a later pass adds are answered the same way. A
uac-doc-researcher result delegated this way also counts for file 4 (write one of them unchanged). Do
not research a request yourself and do not use the runtime fallback while requests are still waiting.
Runtime fallback: this invocation asks for runtime-fallback authoring. When the canonical runtime ends
blocked, waiting, or with no deliverable Acceptance Criteria after its bounded attempts, do not stop: write
files 1, 2 and 3 yourself from the evidence you already verified, following every rule above and the skill,
and make them pass scripts/validate_test_plan.py and scripts/uac_completeness_check.py. Then write
{fallback_path}: {{"canonical_status": "<the runtime's final status>", "failed_gates": [{{"gate": "<gate
name>", "reason": "<why it did not pass, one sentence>"}}]}}. Never invent evidence or report a failed gate
as passed. Do not write this file when the canonical runtime delivered the UAC.
Write in simple English with AEM Guides names a QE sees on screen. A criterion that checks a fix says what QE
sees when it works: the changed content in the output itself and the final status shown. A "queued" or
"success" message, or a successful preprocessing step, is not proof that the output changed."""
SURFACE_DISPOSITIONS = ("AC", "TBD", "OUT_OF_SCOPE", "TEST_PLAN")
SURFACE_AUTHORITIES = ("TICKET", "ATTACHMENT", "PRODUCT_DECISION", "DOCUMENTATION", "CODE_REUSE")
DISCOVERED_AUTHORITIES = ("DOCUMENTATION", "CODE_REUSE")
# A criterion listing six or more screens found only by research is the long route list QE review flags as
# noise; up to five is a normal "still works as before" check.
MAX_DISCOVERED_SURFACES_PER_AC = 5
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
# Jira lines that never hold a requirement: status pings, bot notices, credential and access-link lines.
# The model rightly leaves these out of source coverage (and must never copy credentials). A ping is only
# skipped when short, so a long sentence that also asks for an ETA still has to be mapped.
_STATUS_PING = re.compile(r"\b(?:eta|an update|any update|update on this|been picked up|picked this up"
                          r"|please update|update here|prioriti[sz]e this|pending from)\b")
_STATUS_PING_MAX_WORDS = 16
_NOT_A_REQUIREMENT = re.compile(
    r"\bcrm is watching this ticket\b|\bprogressing without uac\b|\bjira closed without automating\b"
    r"|\bcredentials? shared\b"
    r"|\bshared (?:the )?credentials\b|\b(?:username|password)\s*[:=]|\buse this link\b|\baccess the link\b")
# Support-template metadata lines (org ids, environments, Slack and investigation links, user/load-time log
# lines) and release-scheduling questions never state product behaviour, so the UAC does not have to map them.
_TICKET_METADATA = re.compile(
    r"^[\u2022\u00b7\s]*(?:ims org(?:anization)? id|program\s*/\s*env(?:ironment)?(?:\s*id)?|environment id"
    r"|author url|internal (?:sme )?discussion(?: thread)?|slack (?:thread|link)|posted on (?:the )?guides channel"
    r"|full investigation (?:is )?available here|user\s*:\s*\S+@\S+)"
    r"|\bwhich release (?:would|will) (?:this|the) (?:bug|issue|ticket|fix) be (?:fixed|delivered|released)\b")
# "label: value" reference lines, e.g. "customer case: e-002460814", "related jira (...): aemagt-2195",
# "internal kb ...: e-000874107", "sample affected url (stage): publish-p1-e2...". The label names a reference
# and the value is a short identifier, so the line records where to look, not how the product must behave.
# A line such as "max limit: 1000 assets" is kept: its label is not a reference word.
_LABEL_VALUE = re.compile(r"^[•·\s]*(?P<label>[^:]{1,80}):\s*(?P<value>.+)$")
_REFERENCE_LABEL = re.compile(r"\b(?:case|kb|jira|url|link|id|account|ticket|tenant|env|environment|instance|org"
                              r"|customer|program|contact|email|e-mail|slack|investigation|dynamics|crm|reference)\b")
_IDENTIFIER = re.compile(r"\d|@|\b[a-z]+-[a-z0-9-]+\b")
_REFERENCE_LABEL_MAX_WORDS = 6  # a longer "label" is a sentence with a colon in it, e.g. a path like jcr:content
_REFERENCE_VALUE_MAX_WORDS = 6
_REFERENCE_TITLED_MAX_WORDS = 15
# A line that only records which account was used to reproduce ("authentication performed with adobe id x@y").
_ACCOUNT_LINE = re.compile(r"\S+@\S+\.\S+")
_ACCOUNT_WORDS = re.compile(r"\b(?:authenticat\w*|logged in|log in|login|signed in|sign in|performed with|account"
                            r"|adobe id|user)\b")
_URL = re.compile(r"\[?\b(?:https?://|www\.)\S+")
_LEADING_CHATTER = re.compile(r"^(?:(?:hi|hey|hello|cc|fyi|thanks|thank you)\b[\s,:;!-]*)+")
_INVISIBLE = re.compile("[​-‍⁠﻿]")
# Attachments that cannot show a product screen do not need "surfaces". Report and data documents (test
# summaries, performance reports, permission spreadsheets) are read for facts; screens they do show may
# still be listed, and those are checked against the surface inventory like any other.
NON_VISUAL_ATTACHMENTS = (".txt", ".log", ".json", ".xml", ".dita", ".ditamap", ".har", ".csv", ".zip", ".gz",
                          ".md", ".yaml", ".yml", ".properties", ".java", ".js", ".ts", ".py", ".sql",
                          ".pdf", ".doc", ".docx", ".xls", ".xlsx")
DOC_RESEARCHER = "uac-doc-researcher"
RESEARCH_STORE_DIR = "agent-research"
CODE_RESEARCHER = "uac-code-researcher"
ATTACHMENT_RESEARCHER = "uac-attachment-researcher"
GATE_LOG_FILE = "gate-firing.jsonl"
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


def interpreter_dir(python: str) -> str:
    """The folder of the real interpreter behind a Python path. A virtual environment's bin/python is a
    symlink to the system interpreter (/usr/bin/python3.11), and Copilot CLI checks the resolved path: outside
    every --add-dir folder, running it needs an approval that a non-interactive session cannot give."""
    if not python:
        return ""
    found = shutil.which(python) or python
    try:
        return str(Path(found).resolve().parent)
    except OSError:
        return ""


def copilot_command(config: dict, prompt: str, transcript: Path, python: str = "") -> list[str]:
    cop = config.get("copilot", {})
    cmd = [cop.get("command", "copilot"), "-p", prompt, "-s", "--no-ask-user", f"--share={transcript}"]
    if cop.get("model"):
        cmd.append(f"--model={cop['model']}")
    if cop.get("agent"):
        cmd.append(f"--agent={cop['agent']}")
    directories = list(cop.get("add_dirs", []))
    real = interpreter_dir(python)
    if real and not any(Path(real) == Path(d) or Path(d) in Path(real).parents for d in directories):
        directories.append(real)
    for directory in directories:
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
    if not isinstance(findings, list):
        problems.append("UAC Doc Researcher findings must be a list")
        findings = []
    if status not in DOC_RESEARCH_STATUSES:
        problems.append(f"UAC Doc Researcher status is {status!r}, expected one of {', '.join(DOC_RESEARCH_STATUSES)}")
    elif status in ("ANSWER_FOUND", "PARTIAL") and not findings:
        problems.append(f"UAC Doc Researcher returned {status} with no findings")
    elif status in ("NOT_FOUND", "SOURCE_UNAVAILABLE") and not result.get("limitations"):
        problems.append(f"UAC Doc Researcher returned {status} without limitations naming what was searched")
    for number, finding in enumerate(findings, 1):
        if not isinstance(finding, dict):
            problems.append(f"UAC Doc Researcher finding {number} is not an object")
            continue
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


def _strip_markup(text: str) -> str:
    text = _SKIPPED_BLOCK.sub(" ", _INVISIBLE.sub("", text))
    return _EMBED.sub(" ", _MENTION.sub(" ", _WIKI_LINK.sub(r"\1", text)))


def _words(text: str) -> str:
    """Letters and digits only, without URLs, so bullets, dashes, quotes, link markup and a shortened or
    rewritten link never break a copied sentence."""
    return " ".join(re.findall(r"[^\W_]+", _URL.sub(" ", _strip_markup(text)).lower()))


def _is_reference_line(clause: str) -> bool:
    """A "label: value" reference (case, KB, related Jira, sample URL) or a line naming the account used."""
    match = _LABEL_VALUE.match(clause)
    if match and len(match.group("label").split()) <= _REFERENCE_LABEL_MAX_WORDS \
            and _REFERENCE_LABEL.search(match.group("label")):
        words = match.group("value").split()
        if len(words) <= _REFERENCE_VALUE_MAX_WORDS and _IDENTIFIER.search(" ".join(words)):
            return True
        if words and len(words) <= _REFERENCE_TITLED_MAX_WORDS and _IDENTIFIER.search(words[0]):
            return True  # an identifier followed by its title, e.g. "e-000874107 - guides add-on limitation"
    return bool(_ACCOUNT_LINE.search(clause) and _ACCOUNT_WORDS.search(clause))


def _is_requirement(clause: str) -> bool:
    if _NOT_A_REQUIREMENT.search(clause) or _TICKET_METADATA.search(clause) or _is_reference_line(clause):
        return False
    return not (_STATUS_PING.search(clause) and len(clause.split()) <= _STATUS_PING_MAX_WORDS)


def source_clauses(source: dict, own_name: str = "") -> list[tuple[str, str]]:
    """Split the live Jira description and human comments into sentences a UAC must cover."""
    parts = [("description", source.get("description") or "")]
    parts += [(f"comment:{c['id']}", c.get("body") or "") for c in source.get("comments") or []
              if not own_name or c.get("author") != own_name]
    clauses = []
    for label, text in parts:
        text = _strip_markup(text)
        for line in text.splitlines():
            line = _BULLET.sub("", _HEADING.sub("", line.strip()))
            for sentence in _SENTENCE_END.split(line):
                clause = _LEADING_CHATTER.sub("", _normalize(_URL.sub(" ", sentence)))
                if len(clause.split()) >= MIN_CLAUSE_WORDS and _is_requirement(clause):
                    clauses.append((label, clause))
    return clauses


def unmapped_clauses(entries: list, source: dict, own_name: str = "") -> list[tuple[str, str]]:
    """Jira sentences (label, clause) that no SOURCE_COVERAGE.json entry copies."""
    covered = [f" {_words(str(e.get('text') or ''))} " for e in entries if isinstance(e, dict)]
    return [(label, clause) for label, clause in source_clauses(source, own_name)
            if not any(f" {_words(clause)} " in text for text in covered)]


def unmapped_comment_notes(ticket_dir: Path, source: dict | None, own_name: str = "") -> list[str]:
    """Review notes (never failures) for comment sentences the UAC does not map.

    Requirements live in the description; comments are mostly coordination (recordings, links, server
    URLs, fix-version questions). An unmapped comment sentence is shown to QE instead of stopping the UAC."""
    if not source:
        return []
    try:
        entries = json.loads((ticket_dir / common.SOURCE_COVERAGE_FILE).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if not isinstance(entries, list):
        return []
    return [f"Comment {label[len('comment:'):]} is not covered by the UAC; check it is not a requirement: "
            f"\"{clause[:120]}\""
            for label, clause in unmapped_clauses(entries, source, own_name) if label.startswith("comment:")]


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
        r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|^Suggested checks\b|^Out of scope\b|\Z)", uac, re.M | re.S)}
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
    missing = [(label, clause) for label, clause in unmapped_clauses(entries, source, own_name)
               if label == "description"]
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


_ROTATION_SUFFIX = re.compile(r"(?:\.(?:\d+|\d{4}-\d{2}-\d{2}(?:[-_T]\d[\d-]*)?|old|bak))+$")


def is_non_visual_attachment(name: str) -> bool:
    """True for files that cannot show a product screen, rotated logs included (request.log.2026-07-07,
    error.log.1, server.log.gz)."""
    name = name.lower()
    return name.endswith(NON_VISUAL_ATTACHMENTS) or _ROTATION_SUFFIX.sub("", name).endswith(NON_VISUAL_ATTACHMENTS)


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
        if is_non_visual_attachment(name) and not entry.get("surfaces"):
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


def runtime_python(config: dict) -> str:
    """The Python that can import the backend (the backend's virtual environment): config "runtime_python",
    else backend/venv. The system python3 may be too old for the backend (StrEnum needs 3.11)."""
    configured = str(config.get("runtime_python") or "").strip()
    if configured:
        return configured
    for candidate in (common.REPO_ROOT / "backend" / "venv" / "bin" / "python",
                      common.REPO_ROOT / "backend" / "venv" / "Scripts" / "python.exe"):
        if candidate.is_file():
            return str(candidate)
    return ""


def copilot_env(ticket_dir: Path, python: str = "") -> dict[str, str]:
    """The Copilot session's environment: the canonical runtime hands research to the session's agents and
    writes the requests to this ticket's own store, so they can be answered and counted. The backend's
    Python comes first on PATH, so a plain "python" also imports the backend."""
    env = dict(os.environ)
    env["AGENT_RESEARCH_MODE"] = "copilot_host"
    env["AGENT_RESEARCH_STORE"] = str(ticket_dir / RESEARCH_STORE_DIR)
    env["TEST_PLAN_RESULT_PATH"] = str(ticket_dir / common.RUNTIME_RESULT_FILE)
    if python:
        env["PATH"] = str(Path(python).parent) + os.pathsep + env.get("PATH", "")
    return env


def research_store_summary(ticket_dir: Path) -> dict:
    """How many canonical research requests this ticket's run emitted and how many were answered."""
    store = ticket_dir / RESEARCH_STORE_DIR
    requests = sorted((store / "pending").glob("*.json")) if (store / "pending").is_dir() else []
    answered = {p.name for p in (store / "fulfilled").glob("*.json")} if (store / "fulfilled").is_dir() else set()
    roles: dict[str, int] = {}
    for path in requests:
        if path.name in answered:
            continue
        try:
            role = str(json.loads(path.read_text(encoding="utf-8-sig")).get("worker_role") or "unknown")
        except ValueError:
            role = "unknown"
        roles[role] = roles.get(role, 0) + 1
    return {"requests": len(requests), "answered": sum(1 for p in requests if p.name in answered),
            "unanswered_by_role": roles}


def research_store_notes(summary: dict) -> list[str]:
    """Review notes (never failures) for canonical research requests nobody answered."""
    unanswered = summary["requests"] - summary["answered"]
    if not unanswered:
        return []
    roles = ", ".join(f"{n} {role}" for role, n in sorted(summary["unanswered_by_role"].items()))
    return [f"canonical runtime research requests not answered: {unanswered} of {summary['requests']} ({roles}); "
            "the runtime could not use them"]


def _researcher_ran(ticket_dir: Path, prompt: str, agent: str) -> bool:
    """True when the Copilot transcript shows the agent running, beyond the prompt's own mentions of it."""
    transcript = ticket_dir / "copilot-transcript.md"
    text = transcript.read_text(encoding="utf-8", errors="replace") if transcript.is_file() else ""
    echoed = prompt.count(agent)
    if prompt and prompt in text:
        text, echoed = text.replace(prompt, ""), 0
    return text.count(agent) > echoed


def researcher_run_notes(ticket_dir: Path, prompt: str, source: dict | None, own_name: str = "") -> list[str]:
    """Review notes (never failures) when the code or attachment researcher did not run although it could.

    The doc researcher is a posting check (doc_research_problems); these two are only reported, so a skipped
    run is visible on the release page without blocking the UAC."""
    notes = []
    evidence_file = ticket_dir / common.EVIDENCE_FILE
    try:
        evidence = json.loads(evidence_file.read_text(encoding="utf-8-sig")) if evidence_file.is_file() else {}
    except ValueError:
        evidence = {}
    clones = (((evidence or {}).get("preflight") or {}).get("clones") or {}).get("status")
    if clones != "unavailable" and not _researcher_ran(ticket_dir, prompt, CODE_RESEARCHER):
        notes.append(f"the Copilot transcript shows no {CODE_RESEARCHER} run although the product clones were "
                     "available; code evidence comes only from the main session")
    people = [a.get("filename") for a in (source or {}).get("attachments") or []
              if a.get("filename") and (not own_name or a.get("author") != own_name)]
    if people and not _researcher_ran(ticket_dir, prompt, ATTACHMENT_RESEARCHER):
        notes.append(f"the Copilot transcript shows no {ATTACHMENT_RESEARCHER} run although the ticket has "
                     f"{len(people)} attachment(s) from people")
    return notes


def attachment_fact_notes(ticket_dir: Path, source: dict | None, own_name: str = "") -> list[str]:
    """Review notes (never failures) for attachments from people that list no "facts"."""
    path = ticket_dir / common.SOURCE_COVERAGE_FILE
    if source is None or not path.is_file():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        return []
    with_facts = {str(e.get("source") or "")[len("attachment:"):] for e in entries
                  if isinstance(e, dict) and str(e.get("source") or "").startswith("attachment:")
                  and isinstance(e.get("facts"), list) and e.get("facts")}
    return [f"attachment {a.get('filename')} lists no facts (configuration, status or log lines it shows)"
            for a in source.get("attachments") or []
            if a.get("filename") and a.get("filename") not in with_facts
            and (not own_name or a.get("author") != own_name)]


def orphan_ac_problems(ticket_dir: Path) -> list[str]:
    """Return problems for Acceptance Criteria that no ticket line, attachment or in-scope surface asks for."""
    uac = (ticket_dir / common.UAC_FILE).read_text(encoding="utf-8") if (ticket_dir / common.UAC_FILE).is_file() else ""
    lines = {int(n): text for n, text in re.findall(r"^- Acceptance Criteria (\d+):\s*(.+)$", uac, re.M)}
    blocks = {int(n): body for n, body in re.findall(
        r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|^Suggested checks\b|^Out of scope\b|\Z)", uac, re.M | re.S)}
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


def ticket_problem_groups(ticket_dir: Path, prompt: str, source: dict | None, own_name: str = "") -> dict[str, list[str]]:
    """Every check the runner applies to a generated UAC folder, by check name (for the gate firing log)."""
    groups = {"outputs": check_outputs(ticket_dir), "doc_research": doc_research_problems(ticket_dir, prompt),
              "surface_inventory": surface_inventory_problems(ticket_dir)}
    for name, found in common.import_skill_module("uac_completeness_check").evidence_problems_by_check(ticket_dir).items():
        groups[f"evidence.{name}"] = found
    if source is not None:
        groups["source_coverage"] = source_coverage_problems(ticket_dir, source, own_name)
        groups["attachment_surfaces"] = attachment_surface_problems(ticket_dir, source, own_name)
        groups["hotfix_scope"] = hotfix_scope_problems(ticket_dir, source)
    return groups


def ticket_problems(ticket_dir: Path, prompt: str, source: dict | None, own_name: str = "") -> list[str]:
    """Every check the runner applies to a generated UAC folder."""
    problems: list[str] = []
    for found in ticket_problem_groups(ticket_dir, prompt, source, own_name).values():
        problems += found
    return problems


def log_check_firing(config: dict, key: str, groups: dict[str, list[str]], advisories: dict[str, list[str]]) -> None:
    """Record which runner checks fired on this ticket (<output_dir>/logs/gate-firing.jsonl). Never raises."""
    firing = common.import_skill_module("gate_firing_log")
    checks = {name: len(found) for name, found in groups.items()}
    checks.update({f"advisory.{name}": len(found) for name, found in advisories.items()})
    firing.record(Path(config["output_dir"]) / "logs" / GATE_LOG_FILE, tool="uac-runner", key=key, checks=checks,
                  passed=not any(groups.values()))


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


def _criterion_text(first_line: str, block: str) -> str:
    """The criterion and its indented "  - " case sub-points, without its Source and TBD lines."""
    cases = [line.strip()[2:] for line in block.splitlines()[1:] if re.match(r"^\s+- ", line)]
    return " ".join([first_line, *cases])


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
    plan_file = ticket_dir / common.PLAN_FILE
    plan = _normalize(plan_file.read_text(encoding="utf-8", errors="replace")) if plan_file.is_file() else ""
    lines = {int(n): text for n, text in re.findall(r"^- Acceptance Criteria (\d+):\s*(.+)$", uac, re.M)}
    blocks = {int(n): body for n, body in re.findall(
        r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|^Suggested checks\b|^Out of scope\b|\Z)", uac, re.M | re.S)}
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
            elif disposition == "AC" and _normalize(surface) not in _normalize(_criterion_text(lines[ac], blocks[ac])):
                problems.append(f"{label}: Acceptance Criteria {ac} does not name this surface")
            elif (disposition == "AC" and authority in DISCOVERED_AUTHORITIES
                  and not any(f" {m} " in f" {_normalize(lines[ac])} " for m in REGRESSION_MARKERS)):
                problems.append(f"{label}: found only by {authority}, so Acceptance Criteria {ac} may only check that it "
                                "still works as before; ask about new behaviour there in a TBD, or move it to TEST_PLAN")
            elif disposition == "TBD" and "TBD:" not in blocks[ac]:
                problems.append(f"{label}: Acceptance Criteria {ac} has no TBD line")
        elif disposition == "TEST_PLAN":
            if authority not in DISCOVERED_AUTHORITIES:
                problems.append(f"{label}: the ticket, an attachment or a decision asks for it, so it needs an "
                                "Acceptance Criterion or a TBD, not TEST_PLAN")
            elif surface and _normalize(surface) not in plan:
                problems.append(f"{label}: TEST_PLAN, but the full test plan does not name this surface")
        elif str(entry.get("reason") or "").strip().lower() in EMPTY_REASONS:
            problems.append(f"{label}: OUT_OF_SCOPE needs a concrete reason")
    discovered_per_ac: dict[int, int] = {}
    for entry in entries:
        if entry.get("disposition") == "AC" and entry.get("authority") in DISCOVERED_AUTHORITIES \
                and isinstance(entry.get("ac"), int):
            discovered_per_ac[entry["ac"]] = discovered_per_ac.get(entry["ac"], 0) + 1
    for ac, count in sorted(discovered_per_ac.items()):
        if count > MAX_DISCOVERED_SURFACES_PER_AC:
            problems.append(f"Acceptance Criteria {ac} lists {count} screens found only by research; keep at most "
                            f"{MAX_DISCOVERED_SURFACES_PER_AC} and move the rest to TEST_PLAN")
    if not has_doc:
        problems.append("the surface inventory cites no documentation page")
    if not has_code:
        problems.append("the surface inventory cites no code reference: search the code for every reuse")
    return problems


_PLAN_SECTION_AFTER_REGRESSION = "**Automation Coverage & Gaps**"


def add_test_plan_surfaces(ticket_dir: Path) -> list[str]:
    """Name every research-found TEST_PLAN surface in the full test plan's Regression Areas.

    TEST_PLAN means "the full test plan checks it still works", but sessions often set the disposition and
    forget the plan line, which then blocked the UAC. Only DOCUMENTATION or CODE_REUSE surfaces are added; a
    surface the ticket, an attachment or a decision asks for still needs an Acceptance Criterion or a TBD.
    Returns the surfaces added."""
    plan_file = ticket_dir / common.PLAN_FILE
    entries = _load_list(ticket_dir / common.SURFACE_INVENTORY_FILE)
    if not plan_file.is_file() or not entries:
        return []
    text = plan_file.read_text(encoding="utf-8")
    plan, added = _normalize(text), []
    for entry in entries:
        surface = " ".join(str(entry.get("surface") or "").split())
        if (entry.get("disposition") == "TEST_PLAN" and entry.get("authority") in DISCOVERED_AUTHORITIES
                and surface and _normalize(surface) not in plan and surface not in added):
            added.append(surface)
    lines = text.splitlines()
    if not added or _PLAN_SECTION_AFTER_REGRESSION not in lines:
        return []
    at = lines.index(_PLAN_SECTION_AFTER_REGRESSION)
    while at > 0 and not lines[at - 1].strip():
        at -= 1
    bullets = [f"- Re-run {surface} and assert it still works as before, because research found it on the "
               "path this change touches; it is checked here rather than in the UAC." for surface in added]
    lines[at:at] = bullets
    plan_file.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return added


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


# Engineering, support and operations deliverables a QE cannot check on a test instance (seen in posted UACs:
# "The incident record identifies the missing-ZIP cause", "Creation and upload have separate timings",
# "The approved urgent rollback to AEM release 2608 ..."). They belong in the test plan.
_PROCESS_AC = re.compile(
    r"\bincident record\b|\broot[- ]cause (?:analysis|write-?up|report)\b|\bpost-?mortem\b"
    r"|\broll ?back (?:to|of) (?:the )?(?:aem )?release\b|\b(?:timing|performance) (?:report|breakdown)\b"
    r"|\bseparate timings\b", re.IGNORECASE)


def process_ac_problems(uac_text: str) -> list[str]:
    """Criteria whose statement is a process deliverable, not a product check."""
    return [f"Acceptance Criteria {number} is a process deliverable, not a product check a QE can run "
            f"(move it to the test plan): \"{statement.strip()[:100]}\""
            for number, statement in re.findall(r"^- Acceptance Criteria (\d+):\s*(.+)$", uac_text, re.MULTILINE)
            if _PROCESS_AC.search(statement)]


_AC_BLOCK = re.compile(r"^- Acceptance Criteria (\d+):(.*?)(?=^- Acceptance Criteria \d+:|^Out of scope\b|\Z)",
                       re.MULTILINE | re.DOTALL)


def move_process_acs(uac_text: str) -> tuple[str, list[str]]:
    """Take process-deliverable criteria out of the delivered UAC and renumber the rest.

    Returns (UAC text to deliver, moved criteria as written). The UAC is still delivered: a criterion that is
    an engineering, support or operations deliverable goes to the full test plan instead of blocking the
    UAC. When every criterion would move, nothing moves (the UAC is never emptied)."""
    blocks = list(_AC_BLOCK.finditer(uac_text))
    moving = [m for m in blocks if _PROCESS_AC.search(m.group(2).splitlines()[0] if m.group(2) else "")]
    if not moving or len(moving) == len(blocks):
        return uac_text, []
    width = len(blocks[0].group(1))
    kept, number, out, last = [], 0, [], 0
    for m in blocks:
        out.append(uac_text[last:m.start()])
        last = m.end()
        if m in moving:
            continue
        number += 1
        out.append(f"- Acceptance Criteria {number:0{width}d}:{m.group(2)}")
    out.append(uac_text[last:])
    moved = [f"Acceptance Criteria {m.group(1)}:{m.group(2).rstrip()}" for m in moving]
    return "".join(out), moved


def record_moved_acs(ticket_dir: Path, moved: list[str]) -> None:
    """Append moved process criteria to the full test plan so they are kept, not lost."""
    plan = ticket_dir / common.PLAN_FILE
    if not moved or not plan.is_file():
        return
    section = ("\n\n**Moved from the UAC (engineering, support or operations work, not a product check)**\n"
               + "\n".join(f"- {text.splitlines()[0].strip()}" for text in moved) + "\n")
    plan.write_text(plan.read_text(encoding="utf-8").rstrip() + section, encoding="utf-8")


def runtime_fallback_gates(ticket_dir: Path) -> list[str] | None:
    """The runtime gates that did not pass when Copilot wrote the UAC through the runtime
    fallback, as "gate: reason" lines; None when the canonical runtime delivered the UAC."""
    path = ticket_dir / common.RUNTIME_FALLBACK_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        return ["the runtime fallback record is not valid JSON"]
    gates = data.get("failed_gates") if isinstance(data, dict) else None
    lines = []
    for gate in gates if isinstance(gates, list) else []:
        if isinstance(gate, dict) and gate.get("gate"):
            reason = str(gate.get("reason") or "").strip()
            lines.append(f"{gate['gate']}: {reason}" if reason else str(gate["gate"]))
    if not lines and isinstance(data, dict) and data.get("canonical_status"):
        lines.append(f"canonical runtime status: {data['canonical_status']}")
    return lines


def runtime_result_summary(ticket_dir: Path) -> dict:
    """The canonical runtime's last saved result: its status and every gate failure in the runtime's own
    words. Unlike the fallback record, nothing here is restated by Copilot."""
    path = ticket_dir / common.RUNTIME_RESULT_FILE
    if not path.is_file():
        return {"saved": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        return {"saved": True, "error": "the saved runtime result is not valid JSON"}
    package = data.get("qe_review_package") if isinstance(data, dict) else None
    canonical = (package or {}).get("canonical_result") if isinstance(package, dict) else None
    if not isinstance(canonical, dict):
        return {"saved": True, "error": "the saved runtime result has no canonical result"}
    failures = []
    for gate in canonical.get("gate_decisions") or []:
        if isinstance(gate, dict) and str(gate.get("status") or "").upper() != "PASSED":
            for failure in gate.get("failures") or [str(gate.get("status") or "not passed")]:
                failures.append(f"{gate.get('gate')}: {failure}")
    delivery = canonical.get("uac_delivery") if isinstance(canonical.get("uac_delivery"), dict) else {}
    return {"saved": True, "canonical_status": str(canonical.get("status") or ""),
            "postable": bool(canonical.get("postable")), "gate_failures": failures,
            "delivery_failures": [str(row) for row in delivery.get("failures") or []]}


def written_comment(plan_name: str) -> str:
    """The posted comment holds only the full test plan link. Review notes and runtime gates that did not
    pass stay in status.json and on the release page, never in the ticket."""
    return f"*Full test plan:* [^{plan_name}]"


def post_decision_request(key: str, config: dict, jira, logger, ticket_dir: Path, status: dict,
                          decision_body: str) -> str:
    """Post the decision request for the UAC's TBDs once, as its own comment; never blocks the UAC."""
    settings = config.get("decision_comment") or {}
    if not settings.get("enabled") or not decision_body:
        return "NONE"
    if status.get("decision_comment_id"):
        return "ALREADY_POSTED"
    try:
        people = jira.get_people(key) if settings.get("mention") else {}
        names = [people.get(role, "") for role in settings.get("mention", [])] + list(settings.get("cc", []))
        names = list(dict.fromkeys(n for n in names if n))
        lead = " ".join(f"[~{name}]" for name in names)
        intro = "The UAC is in the Acceptance Criteria field. These product decisions are still open:"
        body = (f"{lead} {intro}" if lead else intro) + "\n\n" + decision_body
        status["decision_comment_id"] = jira.add_comment(key, body)
    except Exception as exc:  # noqa: BLE001 - the UAC is already posted; the request must not undo that
        logger.exception("%s: decision request could not be posted", key)
        status["decision_request_error"] = f"{type(exc).__name__}: {exc}"
        common.write_status(ticket_dir, status)
        return "FAILED"
    status.pop("decision_request_error", None)
    common.write_status(ticket_dir, status)
    logger.info("%s: decision request posted (comment %s)", key, status["decision_comment_id"])
    return "POSTED"


def field_rendered(field_body: str, rendered: str) -> bool:
    """True when Jira rendered the first criterion label in bold, whatever its number ("1" or "01")."""
    first = re.search(r"\*(Acceptance Criteria \d+):\*", field_body)
    label = first.group(1) if first else "Acceptance Criteria 01"
    return f"<b>{label}:</b>" in rendered


def write_field(key: str, config: dict, jira, logger, ticket_dir: Path, status: dict, field_body: str,
                plan_copy: Path, review_notes: list[str], decision_body: str = "") -> str:
    """Write the checked UAC into an empty Acceptance Criteria field and mark it written by the skill."""
    field = config["acceptance_criteria_field"]
    current = (jira.get_field(key, field) or "").strip()
    # Text this runner wrote before (a run that stopped after writing the field) is ours to replace; only
    # text a person wrote is kept. Compare without whitespace, as Jira may return CRLF line endings.
    ours = common.text_key(current) in common.posted_body_keys(ticket_dir) | {common.text_key(field_body)}
    if current and not ours:
        status.update(state="FIELD_KEPT")
        common.write_status(ticket_dir, status)
        logger.info("%s: the Acceptance Criteria field already has text; not overwriting it", key)
        return "FIELD_KEPT"
    attachment_id = jira.attach_file(key, plan_copy)
    jira.set_field(key, field, field_body)
    common.remember_posted_body(ticket_dir, field_body)
    rendered = jira.get_field(key, field, rendered=True) or ""
    if not field_rendered(field_body, rendered):
        # The UAC is in the field now: record it as written, so it is not reported as "not posted"
        # and the next run does not generate it again.
        status.update(state=common.WRITTEN_UNRENDERED, attachment_id=attachment_id,
                      posted_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                      posted_sha256=common.sha256_file(ticket_dir / "field-body.txt"),
                      problems=["the UAC was written into the Acceptance Criteria field but did not render as "
                                "expected, so no comment or done label was added; check the field in Jira"])
        common.write_status(ticket_dir, status)
        logger.error("%s: UAC written into the field but it did not render as expected; check it in Jira", key)
        return common.WRITTEN_UNRENDERED
    comment_id = jira.add_comment(key, written_comment(plan_copy.name))
    jira.update_labels(key, add=[config["labels"]["posted"]])
    status.update(state="POSTED", comment_id=comment_id, attachment_id=attachment_id,
                  posted_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                  posted_sha256=common.sha256_file(ticket_dir / "field-body.txt"))
    common.write_status(ticket_dir, status)
    logger.info("%s: written to the Acceptance Criteria field (comment %s)", key, comment_id)
    post_decision_request(key, config, jira, logger, ticket_dir, status, decision_body)
    return "POSTED"


def fetch_linked_docs(key: str, config: dict, jira, logger, ticket_dir: Path) -> list[dict]:
    """Download the wiki pages the ticket links to (LINKED_DOCS.json). Never raises."""
    try:
        source = jira.get_source(key)
        own_name = str((jira.myself() or {}).get("name") or "")
    except Exception as exc:  # noqa: BLE001 - the Copilot session still reads the ticket itself
        logger.warning("%s: could not read the ticket to find linked pages: %s", key, exc)
        source, own_name = {}, ""
    hosts = tuple(config.get("linked_doc_hosts") or linked_docs.DEFAULT_HOSTS)
    entries = linked_docs.collect(source, ticket_dir, own_name, linked_docs.WikiClient.from_env(), hosts)
    for entry in entries:
        if entry["status"] == "READ":
            logger.info("%s: linked page read: %s", key, entry.get("title") or entry["url"])
        else:
            logger.warning("%s: linked page not read: %s (%s)", key, entry["url"], entry.get("reason"))
    return entries


# A "Note:" paragraph, including lines it wraps onto, up to a blank line, a criterion or the Scope line.
_NOTE_PARAGRAPH = re.compile(r"^Note:[^\n]*(?:\n(?!- |Scope:|\s*$)[^\n]*)*\n*", re.M | re.I)


def _strip_fix_note(uac_text: str) -> str:
    def drop(match: re.Match) -> str:
        text = " ".join(match.group(0).split())
        return "" if re.search(r"not confirmed|fix is proposed", text, re.I) else match.group(0)
    return _NOTE_PARAGRAPH.sub(drop, uac_text)
_SOURCE_LINE = re.compile(r"^(\s*\*\*Source:\*\*\s*)(.+)$", re.M)
_CODE_TOKEN = re.compile(
    r"\b(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"  # a commit or clone revision
    r"|\b(?:[A-Z][a-z0-9]+){2,}(?:IT|Test|Tests)?\b"          # a class name such as TranslationStateService
    r"|\b[a-z]+[A-Z]\w*\("                                   # a method call
    r"|[\w.-]*/[\w.-]+/[\w./-]+"                              # a repository path
    r"|\b[\w-]+\.(?:java|ts|tsx|js|jsx|py|xsl|scss|css|jsp|html)\b")
_CAMEL_ALLOWED = {"JavaScript", "PowerPoint", "SharePoint", "OneDrive", "GitHub", "YouTube", "FrameMaker",
                  "RoboHelp", "WordPress", "DocBook", "MathML", "PostgreSQL", "ExperienceLeague"}


_SOURCE_URL = re.compile(r"\bhttps?://\S+", re.I)
_DATE = re.compile(r"^\d{1,4}/\d{1,2}/\d{1,4}$")


def _code_piece(piece: str, keep: set[str]) -> bool:
    # A documentation or wiki URL is an openable source; scan only the rest of the piece for code names.
    for match in _CODE_TOKEN.finditer(_SOURCE_URL.sub(" ", piece)):
        token = match.group(0)
        if token in _CAMEL_ALLOWED or any(token in name for name in keep) or _DATE.match(token):
            continue
        if "/" in token and token.lower().startswith(("experienceleague", "wiki.")):
            continue
        return True
    return False


def clean_source_lines(uac_text: str, attachments: list[str] = ()) -> tuple[str, list[str]]:
    """Drop clone revisions, file paths and code names from Source lines; a QE reader cannot open them."""
    keep = {name for name in attachments if name}
    removed: list[str] = []

    def clean(match: re.Match) -> str:
        pieces = [p.strip() for p in re.split(r";", match.group(2)) if p.strip()]
        kept = []
        for piece in pieces:
            parts = [part.strip() for part in piece.split(",") if part.strip()]
            good = [part for part in parts if not _code_piece(part, keep)]
            removed.extend(part for part in parts if _code_piece(part, keep))
            if good:
                kept.append(", ".join(good))
        text = "; ".join(kept) or "QE regression around the reported scenario (code references are in the test plan)"
        return match.group(1) + text.rstrip(".") + "."
    return _SOURCE_LINE.sub(clean, uac_text), removed


def normalize_note(uac_text: str, fix_status: str) -> str:
    """The Note line says what is known about the fix, decided from fix_basis, never left to wording."""
    check = common.import_skill_module("uac_completeness_check")
    body = _strip_fix_note(uac_text).lstrip("\n")
    note = {"UNCONFIRMED": check.UNCONFIRMED_NOTE, "PROPOSED": check.PROPOSED_NOTE}.get(fix_status, "")
    return f"{note}\n\n{body}" if note else body


# Jira labels that mark a ticket as a feature request: it has no defect, so no root-cause Note line.
FEATURE_REQUEST_LABELS = {"customer-features"}


def is_feature_request(source: dict | None) -> bool:
    return any(str(label).lower() in FEATURE_REQUEST_LABELS for label in (source or {}).get("labels") or [])


def deliverable_uac(ticket_dir: Path, source: dict | None) -> tuple[str, list[str]]:
    """UAC.md as it goes to the field: the Note line set from fix_basis and clean Source lines."""
    text = (ticket_dir / common.UAC_FILE).read_text(encoding="utf-8")
    evidence_file = ticket_dir / common.EVIDENCE_FILE
    try:
        evidence = json.loads(evidence_file.read_text(encoding="utf-8-sig")) if evidence_file.is_file() else {}
    except ValueError:
        evidence = {}
    status = str(((evidence or {}).get("fix_basis") or {}).get("status") or "")
    if status == "UNCONFIRMED" and is_feature_request(source):
        status = "NOT_A_DEFECT"
    if status:
        text = normalize_note(text, status)
    names = [str(a.get("filename") or "") for a in (source or {}).get("attachments") or []]
    return clean_source_lines(text, names)


def process_ticket(key: str, config: dict, jira, logger, dry_run: bool) -> str:
    out_root = Path(config["output_dir"])
    ticket_dir = out_root / key
    status = common.read_status(ticket_dir)
    if status.get("state") in common.FINAL_STATES and not config.get("regenerate_existing"):
        logger.info("%s: already %s, skipping", key, status["state"])
        return "SKIPPED"
    ticket_dir.mkdir(parents=True, exist_ok=True)
    # An error from an earlier run belongs to that run; this run records its own result.
    status.pop("last_error", None)
    common.archive_attempt(ticket_dir, int(config.get("keep_attempts", 5)))
    for name in (common.UAC_FILE, common.PLAN_FILE, common.DECISIONS_FILE, common.DECISION_BODY_FILE,
                 common.DOC_RESEARCH_FILE, common.SOURCE_COVERAGE_FILE, common.JIRA_SOURCE_FILE,
                 common.SURFACE_INVENTORY_FILE, common.HOTFIX_SCOPE_FILE, common.EVIDENCE_FILE,
                 common.RUNTIME_FALLBACK_FILE, common.RUNTIME_RESULT_FILE, linked_docs.LINKED_DOCS_FILE):
        (ticket_dir / name).unlink(missing_ok=True)
    shutil.rmtree(ticket_dir / linked_docs.LINKED_DOCS_DIR, ignore_errors=True)
    shutil.rmtree(ticket_dir / RESEARCH_STORE_DIR, ignore_errors=True)  # each attempt answers its own requests
    links = fetch_linked_docs(key, config, jira, logger, ticket_dir)
    prompt = PROMPT.format(key=key, uac_path=ticket_dir / common.UAC_FILE, plan_path=ticket_dir / common.PLAN_FILE,
                           decisions_path=ticket_dir / common.DECISIONS_FILE,
                           doc_research_path=ticket_dir / common.DOC_RESEARCH_FILE,
                           source_coverage_path=ticket_dir / common.SOURCE_COVERAGE_FILE,
                           surface_inventory_path=ticket_dir / common.SURFACE_INVENTORY_FILE,
                           hotfix_scope_path=ticket_dir / common.HOTFIX_SCOPE_FILE,
                           evidence_path=ticket_dir / common.EVIDENCE_FILE,
                           fallback_path=ticket_dir / common.RUNTIME_FALLBACK_FILE,
                           linked_docs_path=ticket_dir / linked_docs.LINKED_DOCS_FILE,
                           research_store=ticket_dir / RESEARCH_STORE_DIR,
                           runtime_python=runtime_python(config) or "python3",
                           max_discovered=MAX_DISCOVERED_SURFACES_PER_AC)
    cmd = copilot_command(config, prompt, ticket_dir / "copilot-transcript.md", runtime_python(config))
    timeout = int(config.get("copilot", {}).get("timeout_minutes", 100)) * 60
    started = time.time()
    logger.info("%s: running Copilot CLI", key)
    try:
        run = subprocess.run(cmd, cwd=common.REPO_ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout,
                             env=copilot_env(ticket_dir, runtime_python(config)))
        (ticket_dir / "copilot-output.txt").write_text(run.stdout + "\n" + run.stderr, encoding="utf-8")
        exit_code = run.returncode
    except subprocess.TimeoutExpired:
        exit_code = "timeout"
    status.update({"key": key, "copilot_exit": exit_code, "copilot_seconds": round(time.time() - started),
                   "linked_docs_unread": linked_docs.unread(links)})
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
        plan_surfaces = add_test_plan_surfaces(ticket_dir)
        if plan_surfaces:
            status["test_plan_surfaces_added"] = plan_surfaces
            logger.info("%s: named research-found TEST_PLAN surfaces in the test plan: %s",
                        key, "; ".join(plan_surfaces))
        groups = ticket_problem_groups(ticket_dir, prompt, source, own_name)
        if fetch_problem:
            groups["jira_source"] = fetch_problem
        problems = [p for found in groups.values() for p in found]
    if problems:
        if exit_code == 0:
            log_check_firing(config, key, groups, {})
        status.update(state="FAILED", problems=problems)
        common.write_status(ticket_dir, status)
        logger.error("%s: UAC not written - %s", key, "; ".join(problems))
        return "FAILED"
    jira_text = common.import_skill_module("jira_safe_text")
    uac_text, removed_sources = deliverable_uac(ticket_dir, source)
    uac_text, moved_acs = move_process_acs(uac_text)
    if moved_acs:
        record_moved_acs(ticket_dir, moved_acs)
        status["moved_process_acs"] = moved_acs
        logger.info("%s: moved %d process criteria to the test plan", key, len(moved_acs))
    if removed_sources:
        status["source_code_refs_removed"] = removed_sources
        logger.info("%s: removed code references from Source lines: %s", key, "; ".join(removed_sources))
    # Every check is an Acceptance Criterion in the field; there are no suggested checks.
    field_body = jira_text.jira_field_body(uac_text)
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
    comment_notes = unmapped_comment_notes(ticket_dir, source, own_name)
    research = research_store_summary(ticket_dir)
    status["runtime_research"] = research
    status["runtime_result"] = runtime_result_summary(ticket_dir)
    review_notes = (orphan_ac_problems(ticket_dir) + comment_notes + attachment_fact_notes(ticket_dir, source, own_name)
                    + researcher_run_notes(ticket_dir, prompt, source, own_name) + research_store_notes(research)
                    + [f"moved to the test plan, not a product check: {text.splitlines()[0][:110]}" for text in moved_acs])
    status["review_notes"] = review_notes
    fallback = runtime_fallback_gates(ticket_dir)
    if fallback is not None:
        status["runtime_fallback"] = fallback
        logger.warning("%s: written by the runtime fallback; gates not passed: %s",
                       key, "; ".join(fallback) or "not recorded")
    log_check_firing(config, key, groups, {"orphan_acs": review_notes[:len(review_notes) - len(comment_notes)],
                                           "unmapped_comments": comment_notes, "decisions": warnings})
    for warning in warnings + review_notes:
        logger.warning("%s: %s", key, warning)
    if dry_run:
        common.write_status(ticket_dir, status)
        logger.info("%s: ready (dry run, nothing posted)", key)
        return "READY"
    plan_copy = ticket_dir / f"{key}-test-plan.md"
    shutil.copyfile(ticket_dir / common.PLAN_FILE, plan_copy)
    return write_field(key, config, jira, logger, ticket_dir, status, field_body, plan_copy,
                       review_notes, decision_body)


def health(config: dict, jira, logger) -> list[str]:
    problems = []
    python = runtime_python(config)
    if python:
        logger.info("canonical runtime Python: %s", python)
    else:
        logger.warning("no backend Python found (set runtime_python in the config); the Copilot session cannot run "
                       "the canonical runtime locally and its research requests will not be answered")
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
        problems.append("Copilot CLI not found on PATH; under cron set PATH in the crontab to the folders that hold "
                        "copilot and node (see uac-release.cron)")
    return problems


def check_dir(ticket_dir: Path, own_name: str = "") -> int:
    """Run every runner check on an existing UAC folder, e.g. one edited by hand before posting."""
    source_file = ticket_dir / common.JIRA_SOURCE_FILE
    source = json.loads(source_file.read_text(encoding="utf-8")) if source_file.is_file() else None
    problems = ticket_problems(ticket_dir, "", source, own_name)
    if source is None:
        problems.append(f"{common.JIRA_SOURCE_FILE} is missing, so ticket coverage was not checked")
    for note in orphan_ac_problems(ticket_dir) + unmapped_comment_notes(ticket_dir, source, own_name):
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
        exit_code = 2 if health_problems else 1 if any(
            v in ("FAILED", "ERROR", common.WRITTEN_UNRENDERED) for v in results.values()) else 0
    except Exception as exc:  # noqa: BLE001 - record and alert on anything that stops the run
        logger.exception("run %s stopped", run_id)
        alerts.append(f"The run stopped before finishing: {type(exc).__name__}: {exc}")
        exit_code = 3
    alerts = [f"Health check failed, no tickets processed: {p}" for p in health_problems] + alerts
    for key, result in results.items():
        if result == "ERROR":
            alerts.append(f"{key}: unexpected error - {errors.get(key, 'see the log')}")
        elif result == common.WRITTEN_UNRENDERED:
            alerts.append(f"{key}: UAC written into the Acceptance Criteria field but it did not render as "
                          "expected; no comment or done label was added - check the field in Jira")
        elif result == "FAILED":
            problems = common.read_status(out / key).get("problems") or ["see status.json"]
            more = f" (and {len(problems) - 1} more)" if len(problems) > 1 else ""
            alerts.append(f"{key}: UAC not posted - {problems[0]}{more}")
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
