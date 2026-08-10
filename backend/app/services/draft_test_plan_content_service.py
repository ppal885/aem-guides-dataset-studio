"""Rich, workflow-aware content for pipeline draft test plans."""

from __future__ import annotations

import re
from typing import Any

from app.core.schemas_test_plan_pipeline import PreUacProductBrief, TicketBrief
from app.services.ticket_workflow_profile_service import DefaultScenarioRow, TicketWorkflowProfile

_GENERIC_BUG_SEED_IDS = frozenset(
    {"TA-REPRODUCTION", "TA-CONTROL", "TA-NEGATIVE", "TA-RECOVERY"}
)
_VAGUE_AC_RE = re.compile(
    r"\b(unspecified_output|after clarification|agreed in ticket after|when the fix is applied)\b",
    re.I,
)
_PUBLISHING_API_RE = re.compile(
    r"(publishing api|urls\.primaryname=publishing)(?!.*baseline)",
    re.I,
)


def _topic_ids(pre_uac: PreUacProductBrief | None) -> set[str]:
    return set(pre_uac.topic_ids if pre_uac else [])


def _brief_blob(brief: TicketBrief | None, pre_uac: PreUacProductBrief | None = None) -> str:
    if brief is None:
        return ""
    parts = [
        brief.summary,
        brief.component,
        brief.scope_hint,
        brief.current_behavior,
        brief.expected_behavior,
    ]
    if pre_uac:
        parts.extend(
            [
                pre_uac.primary_product_area,
                pre_uac.summary_plain_english,
                pre_uac.ticket_specific_context,
                " ".join(pre_uac.topic_ids),
                " ".join(pre_uac.how_it_works),
                " ".join(pre_uac.known_product_behavior),
                " ".join(pre_uac.documented_behavior),
            ]
        )
    return " ".join(part for part in parts if part)


def _is_schematron_text_context(brief: TicketBrief | None) -> bool:
    if brief is None:
        return False
    text = _brief_blob(brief).lower()
    return "schematron" in text and ("//text()" in text or "text-node" in text or "text node" in text)


def _is_translation_moved_content_context(
    brief: TicketBrief | None,
    pre_uac: PreUacProductBrief | None = None,
) -> bool:
    text = _brief_blob(brief, pre_uac).lower()
    has_translation = any(
        marker in text
        for marker in ("translation", "translate", "language copy", "translation project")
    )
    has_move = any(
        marker in text
        for marker in ("assets move", "moved", "move content", "content moved")
    )
    has_language_mismatch = any(
        marker in text
        for marker in (
            "en_us",
            "en-us",
            "language root",
            "language code",
            "language uuid",
            "uuid/path",
            "uuid path",
            "language_uuid_path_mismatch",
            "content around language codes",
        )
    )
    return has_translation and has_move and has_language_mismatch


def build_setup_lines(
    key: str,
    brief: TicketBrief,
    pre_uac: PreUacProductBrief | None,
    workflow: TicketWorkflowProfile | None,
) -> list[str]:
    topics = _topic_ids(pre_uac)
    lines = [
        f"Confirm Jira context: [{key}](https://jira.corp.adobe.com/browse/{key}).",
        "Confirm the customer repro data, Author environment, and expected behavior from Jira.",
    ]
    if _is_translation_moved_content_context(brief, pre_uac):
        lines.extend(
            [
                f"Create DAM language folders under `docs/qa/test-data/{key}/`: source `en`, moved source `en_us`, and at least one target language folder such as `fr` or `de`.",
                "Author a small DITA map in `en` with two topics and one referenced asset, then move the map/topics/assets to `en_us` using AEM Assets move so UUID metadata is preserved.",
                "Keep one unchanged control map directly authored under the expected language root for R0 comparison.",
                "Open Map Console / Translation panel for the moved `en_us` map and capture UI state plus network/API response for translation project creation.",
                "If the product exposes `disableCode` or disabled-row reasons, capture the exact code/message for moved content that cannot be translated.",
            ]
        )
    elif _is_schematron_text_context(brief):
        lines.extend(
            [
                "Create a folder profile / Workspace Settings configuration with Schematron validation enabled on save.",
                "Attach two Schematron controls: one rule with `context=\"//text()\"` and one explicit control rule with `context=\"//p\"`.",
                "Prepare a DITA topic containing straight quotes in `title`, `p`, `li`, `note`, and table entry text nodes.",
                "Keep one clean DITA topic with typographic quotes only for negative/no-report validation.",
            ]
        )
    elif "baseline" in topics:
        lines.extend(
            [
                "On Author: open a DITA map with baselines; ensure topics have **Version comment** set in metadata.",
                "Create or open an existing baseline (Web Editor baseline panel + legacy dashboard if both in scope).",
                "Note current baseline table columns before testing (title, version, labels, etc.).",
            ]
        )
    elif "asset_status" in topics or "/assets/status" in f"{brief.summary} {brief.scope_hint}".lower():
        lines.extend(
            [
                f"Upload / confirm DAM test data under `docs/qa/test-data/{key}/` on Author.",
                "Wait for post-processing — CRX `guides:assetStatus=SUCCESS` on test assets.",
                "Obtain AEM Author URL + Bearer token for REST calls.",
            ]
        )
    else:
        lines.append("Upload / confirm DAM test assets for this ticket on Author.")
        if workflow and workflow.ticket_category == "feature_request":
            lines.append("Align with PM on expected behavior before executing P0 scenarios.")
        else:
            lines.append("Obtain AEM Author URL and credentials for API/UI verification.")
    return lines[:8]


def _baseline_feature_scenarios() -> list[DefaultScenarioRow]:
    return [
        DefaultScenarioRow(
            scenario_id="S-01",
            priority="P0",
            title="Version comment column visible in Baseline table",
            links_to="EB-1, AC-1",
            verify_hint="Each topic row shows Version comment without opening the topic editor.",
        ),
        DefaultScenarioRow(
            scenario_id="S-02",
            priority="P0",
            title="CSV export includes Version comment",
            links_to="EB-2, AC-2",
            verify_hint="Exported CSV has a Version comment column with expected values.",
        ),
        DefaultScenarioRow(
            scenario_id="S-03",
            priority="P1",
            title="Filter / sort on Version comment column",
            links_to="EB-3, AC-3",
            verify_hint="Filter and sort behave like other baseline columns (if in scope).",
        ),
        DefaultScenarioRow(
            scenario_id="S-04",
            priority="P0 R0",
            title="Regression — existing baseline columns unchanged",
            links_to="EB-4, AC-4",
            verify_hint="Title, version, labels columns still correct; export still works.",
        ),
        DefaultScenarioRow(
            scenario_id="S-05",
            priority="P1",
            title="Topic without Version comment",
            links_to="EB-5",
            verify_hint="Empty/missing comment shows blank or documented placeholder — no UI error.",
        ),
    ]


def _asset_status_bug_scenarios(brief: TicketBrief) -> list[DefaultScenarioRow]:
    return [
        DefaultScenarioRow(
            scenario_id="S-01",
            priority="P0",
            title="Comma-path customer repro",
            links_to="EB-1, AC-1",
            verify_hint="POST accepts path; poll SUCCESS; no path-split log error.",
        ),
        DefaultScenarioRow(
            scenario_id="S-02",
            priority="P0",
            title="Full path preserved in response",
            links_to="EB-2, AC-2",
            verify_hint="`assets[].path` matches POST path including comma segment.",
        ),
        DefaultScenarioRow(
            scenario_id="S-03",
            priority="P0",
            title="API status matches CRX property",
            links_to="EB-3, AC-3",
            verify_hint="API `status` equals CRX `guides:assetStatus`.",
        ),
        DefaultScenarioRow(
            scenario_id="S-04",
            priority="P0 R0",
            title="Normal path regression (no comma)",
            links_to="EB-4, AC-4",
            verify_hint="Control path without comma still SUCCESS.",
        ),
        DefaultScenarioRow(
            scenario_id="S-05",
            priority="P1",
            title="Batch comma + normal paths",
            links_to="EB-5",
            verify_hint="Mixed batch succeeds; no whole-job FAILED.",
        ),
        DefaultScenarioRow(
            scenario_id="S-06",
            priority="P0 R0",
            title="No auth token",
            links_to="EB-6, AC-5",
            verify_hint="POST without Authorization returns HTTP 401.",
        ),
    ]


def _schematron_text_context_scenarios() -> list[DefaultScenarioRow]:
    return [
        DefaultScenarioRow(
            scenario_id="S-01",
            priority="P0",
            title='Customer repro: Schematron context="//text()" fires',
            links_to="EB-1, AC-1",
            verify_hint='Save validation reports straight-quote hits from a rule using context="//text()".',
        ),
        DefaultScenarioRow(
            scenario_id="S-02",
            priority="P0 R0",
            title='Control: explicit context="//p" still fires',
            links_to="EB-2, AC-2",
            verify_hint='The known-good context="//p" rule continues to report the paragraph quote issue.',
        ),
        DefaultScenarioRow(
            scenario_id="S-03",
            priority="P0",
            title="Broad text-node coverage across DITA elements",
            links_to="EB-3, AC-3",
            verify_hint="The same text-node rule catches title, paragraph, list, note, and table-entry text without enumerating elements.",
        ),
        DefaultScenarioRow(
            scenario_id="S-04",
            priority="P1",
            title="Negative clean-content oracle",
            links_to="EB-4, AC-4",
            verify_hint="A topic without straight quotes produces no false Schematron report.",
        ),
        DefaultScenarioRow(
            scenario_id="S-05",
            priority="P1",
            title="Workspace save validation and panel oracle",
            links_to="EB-5, AC-5",
            verify_hint="Save flow completes; Schematron panel/network response shows rule reports, not a generic fatal/NPE error.",
        ),
        DefaultScenarioRow(
            scenario_id="S-06",
            priority="P1 R0",
            title="Multiple Schematron files regression",
            links_to="EB-6, RR-SCH-MULTI",
            verify_hint="Adding a sibling valid Schematron file does not suppress the text-node rule or hide reports.",
        ),
    ]


def _translation_moved_content_scenarios() -> list[DefaultScenarioRow]:
    return [
        DefaultScenarioRow(
            scenario_id="S-01",
            priority="P0",
            title="Customer repro: `en` content moved to `en_us` translates",
            links_to="EB-1, AC-01",
            verify_hint="Translation panel/project creation resolves moved map/topics/assets and no language UUID/path mismatch blocks the job.",
        ),
        DefaultScenarioRow(
            scenario_id="S-02",
            priority="P0 R0",
            title="Control: normal language-root translation still works",
            links_to="EB-2, AC-02",
            verify_hint="A map authored directly under the expected language root still creates a translation job successfully.",
        ),
        DefaultScenarioRow(
            scenario_id="S-03",
            priority="P0",
            title="Assets-move metadata preserved for map, topics, and referenced assets",
            links_to="EB-3, AC-03",
            verify_hint="Moved map retains UUID-backed references; referenced topics/assets appear in translation scope instead of disappearing.",
        ),
        DefaultScenarioRow(
            scenario_id="S-04",
            priority="P1",
            title="Mixed moved and unmoved topics in one map",
            links_to="EB-4, AC-04",
            verify_hint="Valid sibling topics remain translatable even if one moved item needs a disabled/actionable state.",
        ),
        DefaultScenarioRow(
            scenario_id="S-05",
            priority="P1",
            title="Moved-out-of-language-root handling is clear",
            links_to="EB-5, AC-06",
            verify_hint="If content is intentionally unsupported, UI/API shows a clear disabled reason such as `disableCode`, not an empty/wrong translation list.",
        ),
        DefaultScenarioRow(
            scenario_id="S-06",
            priority="P1 R0",
            title="Translation status and out-of-sync checks remain accurate",
            links_to="EB-6",
            verify_hint="Existing translation status/out-of-sync behavior remains correct for moved and control maps after job creation.",
        ),
    ]


def _filter_seed_areas(
    test_areas: list[dict[str, Any]],
    workflow: TicketWorkflowProfile | None,
) -> list[dict[str, Any]]:
    if not test_areas or not workflow:
        return test_areas
    if workflow.ticket_category != "feature_request":
        return test_areas
    filtered = [
        area
        for area in test_areas
        if str(area.get("id") or "") not in _GENERIC_BUG_SEED_IDS
        and str(area.get("category") or "").lower() not in {"reproduction", "r0 control", "recovery"}
    ]
    return filtered or []


def build_scenario_rows(
    test_areas: list[dict[str, Any]],
    workflow: TicketWorkflowProfile | None,
    pre_uac: PreUacProductBrief | None,
    brief: TicketBrief,
) -> list[DefaultScenarioRow]:
    topics = _topic_ids(pre_uac)
    category = workflow.ticket_category if workflow else "other"

    if _is_translation_moved_content_context(brief, pre_uac) and category == "bug":
        return _translation_moved_content_scenarios()
    if "baseline" in topics and category == "feature_request":
        return _baseline_feature_scenarios()
    if "asset_status" in topics and category == "bug":
        return _asset_status_bug_scenarios(brief)
    if _is_schematron_text_context(brief) and category == "bug":
        return _schematron_text_context_scenarios()
    if category == "bug" and workflow:
        rows = list(workflow.default_scenarios)
        filtered = _filter_seed_areas(test_areas, workflow)
        for idx, area in enumerate(filtered[:3], start=len(rows) + 1):
            rows.append(
                DefaultScenarioRow(
                    scenario_id=f"S-{idx:02d}",
                    priority=str(area.get("priority") or "P1"),
                    title=str(area.get("category") or area.get("id") or "Test area"),
                    links_to=f"EB-{idx}",
                    verify_hint=str(area.get("rationale") or "")[:120],
                )
            )
        return rows[:8]
    if category == "feature_request" and workflow:
        return list(workflow.default_scenarios)[:6]

    rows: list[DefaultScenarioRow] = []
    filtered_areas = _filter_seed_areas(test_areas, workflow)
    for idx, area in enumerate(filtered_areas[:6], start=1):
        rows.append(
            DefaultScenarioRow(
                scenario_id=f"S-{idx:02d}",
                priority=str(area.get("priority") or "P1"),
                title=str(area.get("category") or area.get("id") or "Test area"),
                links_to=f"EB-{idx}",
                verify_hint=str(area.get("rationale") or "")[:120],
            )
        )
    if not rows and workflow:
        return list(workflow.default_scenarios)
    if not rows:
        return [
            DefaultScenarioRow(
                scenario_id="S-01",
                priority="P0",
                title="Primary scenario",
                links_to="EB-1",
                verify_hint="Matches Jira expected behavior.",
            )
        ]
    return rows


def _scenario_table_lines(scenarios: list[DefaultScenarioRow]) -> list[str]:
    return [
        f"| {row.scenario_id} | {row.priority} | {row.title} | {row.links_to} | {row.verify_hint} |"
        for row in scenarios
    ]


def build_must_run_rows(scenarios: list[DefaultScenarioRow]) -> list[str]:
    rows: list[str] = []
    run_order = 1
    for scenario in scenarios:
        if not scenario.priority.startswith("P0"):
            continue
        rows.append(
            f"| **{run_order}** | **{scenario.scenario_id}** {scenario.title} | {scenario.verify_hint} |"
        )
        run_order += 1
        if run_order > 6:
            break
    return rows


def build_step_lines(scenarios: list[DefaultScenarioRow], brief: TicketBrief) -> list[str]:
    lines: list[str] = []
    topics = set()
    for scenario in scenarios:
        sid = scenario.scenario_id
        title = scenario.title
        hint = scenario.verify_hint
        if "version comment column visible" in title.lower():
            lines.append(
                f"- **{sid}** Open baseline for a map where topics have Version comment set. "
                "**How to check:** column appears; values match topic metadata without opening each topic."
            )
        elif "csv export" in title.lower():
            lines.append(
                f"- **{sid}** Export baseline to CSV. "
                "**How to check:** file contains Version comment column with correct values."
            )
        elif "filter / sort" in title.lower():
            lines.append(
                f"- **{sid}** Apply filter/sort using Version comment column (if in scope). "
                "**How to check:** results order/filter correctly; no UI error."
            )
        elif "regression" in title.lower() and "baseline" in title.lower():
            lines.append(
                f"- **{sid}** Verify title/version/labels columns and legacy export on same baseline. "
                "**How to check:** unchanged from pre-feature behavior."
            )
        elif "comma-path" in title.lower() or "comma" in title.lower():
            lines.append(
                f"- **{sid}** POST customer comma-folder path from Jira; poll to terminal status. "
                f"**How to check:** {hint}"
            )
        elif "no auth" in title.lower():
            lines.append(
                f"- **{sid}** POST without Authorization header. **How to check:** HTTP 401."
            )
        elif "context=\"//text()\"" in title.lower():
            lines.append(
                f"- **{sid}** Configure a Schematron rule with `context=\"//text()\"`, save a DITA topic containing straight quotes in multiple text nodes, then open the validation result. "
                "**How to check:** each straight quote is reported with the configured `sch:report` message; no generic fatal error is shown."
            )
        elif "context=\"//p\"" in title.lower():
            lines.append(
                f"- **{sid}** Run the existing explicit paragraph control rule on the same topic. "
                "**How to check:** paragraph straight quotes are reported exactly as before; this proves the validation harness itself still works."
            )
        elif "broad text-node" in title.lower():
            lines.append(
                f"- **{sid}** Place straight quotes in `title`, `p`, `li`, `note`, and table `entry` text. "
                "**How to check:** the `//text()` rule reports all text-node locations without adding element-specific rules."
            )
        elif "clean-content" in title.lower():
            lines.append(
                f"- **{sid}** Save a clean topic with typographic quotes only. "
                "**How to check:** no straight-quote report appears and save remains successful."
            )
        elif "workspace save validation" in title.lower():
            lines.append(
                f"- **{sid}** Trigger validation through Workspace Settings save-on-save flow and inspect UI panel plus network response. "
                "**How to check:** response contains deterministic Schematron report entries; UI does not show misleading fatal-content/NPE text."
            )
        elif "multiple schematron" in title.lower():
            lines.append(
                f"- **{sid}** Attach the `//text()` Schematron file together with another valid Schematron file. "
                "**How to check:** both files are evaluated independently; no sibling file suppresses or masks reports."
            )
        elif "en` content moved to `en_us`" in title.lower():
            lines.append(
                f"- **{sid}** Author a DITA map under `en`, move the map/topics/assets to `en_us` using Assets move, then create a translation project from Map Console / Translation panel. "
                "**How to check:** moved map, child topics, and referenced assets are listed for target language translation; no language UUID/path mismatch error blocks the job."
            )
        elif "normal language-root translation" in title.lower():
            lines.append(
                f"- **{sid}** Run the same translation-project flow on a control map authored directly under the expected source language root. "
                "**How to check:** job creation succeeds as before; this proves the fix did not break the standard path."
            )
        elif "assets-move metadata" in title.lower():
            lines.append(
                f"- **{sid}** Inspect moved map/topic references before opening Translation panel, then start translation. "
                "**How to check:** UUID-backed references still resolve to the moved `en_us` paths and referenced assets are not dropped from the translation scope."
            )
        elif "mixed moved and unmoved" in title.lower():
            lines.append(
                f"- **{sid}** Build one map with one moved topic, one normal topic, and one referenced asset. "
                "**How to check:** valid siblings stay selectable/translatable; a problematic item does not poison the whole map."
            )
        elif "moved-out-of-language-root" in title.lower():
            lines.append(
                f"- **{sid}** Move a topic/map outside the configured language tree and open Translation panel/API. "
                "**How to check:** product gives an actionable disabled reason/code, not a blank panel, wrong language, or silent failure."
            )
        elif "translation status" in title.lower() and "out-of-sync" in title.lower():
            lines.append(
                f"- **{sid}** After project creation, modify one source topic and refresh translation status/out-of-sync view. "
                "**How to check:** moved and control maps show accurate status without stale language-root/cache results."
            )
        elif scenario.priority.startswith("P0"):
            lines.append(
                f"- **{sid}** Execute {title.lower()} on Author. **How to check:** {hint}"
            )
    if not lines and brief.summary:
        lines.append(
            "- **S-01** Execute primary scenario from Jira on Author. "
            "**How to check:** actual matches PM-agreed or Jira expected behavior."
        )
    return lines[:10]


def _is_usable_ac(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 12:
        return False
    if _VAGUE_AC_RE.search(cleaned):
        return False
    if cleaned.lower().startswith("regression guard: actual failure mode"):
        return False
    return True


def build_ac_lines(
    acceptance: list[Any],
    brief: TicketBrief,
    workflow: TicketWorkflowProfile | None,
    scenarios: list[DefaultScenarioRow],
) -> list[str]:
    lines: list[str] = []
    category = workflow.ticket_category if workflow else "other"
    if _is_translation_moved_content_context(brief) and category == "bug":
        return [
            "| AC ID | Acceptance Criteria |",
            "| --- | --- |",
            "| AC-01 | In AEM Guides 2605+, a DITA map and its topics moved by Assets Move between `en` and `en_us` remain eligible for translation when the content is otherwise valid. |",
            "| AC-02 | The translation eligibility API must not return `disableCode: LANGUAGE_UUID_PATH_MISMATCH` for valid moved content that previously translated in 2604. |",
            "| AC-03 | The Map Console Translation panel must allow selecting both the moved map and moved topics for translation. |",
            "| AC-04 | Translation job/project creation must proceed after selection and must preserve the expected source language / target language mapping. |",
            "| AC-05 | Both movement directions are supported or explicitly documented: `en_us -> en` from repro and `en -> en_us` from business impact. |",
            "| AC-06 | If content is truly corrupted or unrecoverably mismatched, the UI must show an actionable message instead of silently disabling selection. |",
            "| AC-07 | Existing production-style content with legacy GUID/language metadata can be translated or repaired without requiring manual per-topic recreation. |",
            "",
            "- **Blocking sign-off today:** AC-01 through AC-04 plus the P0 scenarios S-01, S-02, and S-03 must pass on Author.",
        ]
    if _is_schematron_text_context(brief) and category == "bug":
        return [
            '- **AC-1 (S-01):** A Schematron rule using `context="//text()"` reports straight quotes during AEM Guides validation on save.',
            '- **AC-2 (S-02):** Existing explicit element rules such as `context="//p"` continue to work unchanged.',
            "- **AC-3 (S-03):** The `//text()` rule covers text nodes across common DITA elements without requiring authors to enumerate every element.",
            "- **AC-4 (S-04):** Clean content without straight quotes produces no false positive report.",
            "- **AC-5 (S-05):** Validation failures and reports are surfaced in the Schematron panel/network response with actionable messages, not generic fatal/NPE errors.",
            "- **Blocking sign-off today:** P0 repro (S-01), explicit-context R0 control (S-02), and broad text-node coverage (S-03) must pass on Author.",
        ]
    for idx, ac in enumerate(acceptance[:10], start=1):
        text = ac if isinstance(ac, str) else str(ac.get("text") or ac.get("criterion") or ac)
        if _is_usable_ac(text):
            lines.append(f"- **AC-{idx}:** {text.strip()[:400]}")

    topics = {s.title.lower() for s in scenarios}

    if not lines and category == "feature_request" and any("version comment" in t for t in topics):
        lines = [
            "- **AC-1 (S-01):** Version comment is visible as a column (or agreed UI surface) in the Baseline table.",
            "- **AC-2 (S-02):** CSV export includes Version comment values.",
            "- **AC-3 (S-03):** Filter/sort on Version comment works like other columns (if PM confirms in scope).",
            "- **AC-4 (S-04):** Existing baseline columns and export behavior are unchanged (regression).",
            "- **AC-5:** _PM to confirm legacy dashboard vs Web Editor baseline v2 parity before sign-off._",
        ]
    elif not lines and category == "feature_request":
        for idx, scenario in enumerate(scenarios[:5], start=1):
            lines.append(
                f"- **AC-{idx} ({scenario.scenario_id}):** _PM define pass criteria for: {scenario.title}._"
            )
    elif not lines and category == "bug" and brief.expected_behavior:
        parts = re.split(r"[;\n]+", brief.expected_behavior)
        for idx, part in enumerate(parts[:7], start=1):
            text = part.strip(" -•")
            if text:
                lines.append(f"- **AC-{idx}:** {text[:240]}")
    elif not lines and brief.expected_behavior:
        lines.append(f"- **AC-1:** {brief.expected_behavior[:400]}")
    elif not lines:
        lines.append("- **AC-1:** _Define from Jira Expected Result after PM review._")

    if category == "feature_request" and not brief.expected_behavior.strip():
        lines.append(
            "- **Blocking sign-off today:** Expected Result not agreed in Jira — execute TW/PU clarifications with PM first."
        )
    elif category == "bug" and brief.current_behavior and brief.expected_behavior:
        lines.append(
            "- **Blocking sign-off today:** P0 repro (S-01) and R0 regression must pass on Author before release."
        )
    return lines[:12]


def build_eb_lines(
    brief: TicketBrief,
    uac: dict[str, Any],
    workflow: TicketWorkflowProfile | None,
    pre_uac: PreUacProductBrief | None,
) -> list[str]:
    lines: list[str] = []
    category = workflow.ticket_category if workflow else "other"
    topics = _topic_ids(pre_uac)

    if _is_translation_moved_content_context(brief, pre_uac) and category == "bug":
        return [
            "- **EB-1:** AEM Guides translation must work for existing production maps that were created in `en` and later moved to `en_us` with Assets move.",
            "- **EB-2:** The normal source-language-root translation workflow remains the known-good control.",
            "- **EB-3:** Map/topic/asset resolution must use preserved UUID/reference metadata strongly enough that moved paths do not disappear from translation scope.",
            "- **EB-4:** A map containing both moved and unmoved topics should isolate the problematic item; valid siblings must remain selectable/translatable.",
            "- **EB-5:** If a moved path is unsupported because it is outside a configured language root, UI/API must expose a clear disabled reason/code instead of silent empty results.",
            "- **EB-6:** Translation status and out-of-sync checks must not use stale language-root/cache state after Assets move.",
        ]

    if category == "feature_request" and "baseline" in topics:
        lines.extend(
            [
                "- **EB-1:** Baseline table shows Version comment per topic row (when PM confirms column UI).",
                "- **EB-2:** CSV export includes Version comment values matching topic metadata.",
                "- **EB-3:** Filter/sort on Version comment behaves consistently with other baseline columns (if in scope).",
                "- **EB-4:** Existing columns (title, version, labels) and export still work — no regression.",
                "- **EB-5:** Topic with empty Version comment shows blank/placeholder — no error.",
            ]
        )
        if pre_uac and pre_uac.known_product_behavior:
            kb4 = next((k for k in pre_uac.known_product_behavior if "not a Baseline table column today" in k), "")
            if kb4:
                lines.append(f"- **EB-0 (today):** {kb4}")
        return lines[:8]

    if _is_schematron_text_context(brief) and category == "bug":
        return [
            '- **EB-1:** `context="//text()"` is a valid customer-authored Schematron XPath context and must be evaluated by the save-validation pipeline.',
            '- **EB-2:** `context="//p"` is the known-good control and must remain green after the fix.',
            "- **EB-3:** A single text-node rule must detect text in common DITA elements such as title, p, li, note, and table entry.",
            "- **EB-4:** Topics without straight quotes must not produce false reports.",
            "- **EB-5:** UI panel, network/API response, and backend logs must expose the rule report or clear transform error.",
            "- **EB-6:** Multiple configured Schematron files must not suppress each other.",
        ]

    if category == "bug" and brief.expected_behavior:
        lines.append(f"- **EB-1:** Fix repro — {brief.expected_behavior[:220]}")
        if brief.current_behavior:
            lines.append(f"- **EB-2:** Current failure — {brief.current_behavior[:220]}")
    elif category == "feature_request" and not brief.expected_behavior:
        lines.append("- **EB-1:** _PM must define agreed expected behavior before UAC sign-off._")

    if brief.expected_behavior and not (category == "bug" and lines):
        parts = re.split(r"[;\n]+", brief.expected_behavior)
        start = len(lines) + 1
        for idx, part in enumerate(parts[:6], start=start):
            text = part.strip(" -•")
            if text:
                lines.append(f"- **EB-{idx}:** {text[:240]}")

    out_exp = uac.get("output_expectations") or {}
    if isinstance(out_exp, dict):
        for idx, bullet in enumerate(list(out_exp.get("expectations") or [])[:2], start=len(lines) + 1):
            lines.append(f"- **EB-{idx}:** {str(bullet)[:240]}")

    while len(lines) < 3:
        n = len(lines) + 1
        if category == "feature_request":
            lines.append(f"- **EB-{n}:** _Derived from PM Expected Result — not yet in Jira._")
        else:
            lines.append(f"- **EB-{n}:** _Refine from Jira Expected/Actual Result._")
    return lines[:10]


_GENERIC_RISK_IDS = frozenset(
    {
        "RR-R0-CONTROL",
        "RR-DIRECT-FIX",
        "RR-RECOVERY",
        "RR-PUBLISHING-OUTPUTS",
        "RR-CONSTRUCT-MATRIX",
    }
)
_OFF_TOPIC_BLAST_RE = re.compile(
    r"\b(asset-versioning|asset-status-api|rest-api(?!.*baseline)|publishing outputs)\b",
    re.I,
)


def _scenario_id_for(title_keyword: str, scenarios: list[DefaultScenarioRow], default: str = "S-01") -> str:
    for scenario in scenarios:
        if title_keyword.lower() in scenario.title.lower():
            return scenario.scenario_id
    return default


def build_blast_rows(
    blast: list[dict[str, Any]],
    scenarios: list[DefaultScenarioRow],
    workflow: TicketWorkflowProfile | None,
    pre_uac: PreUacProductBrief | None,
    brief: TicketBrief,
) -> list[str]:
    topics = _topic_ids(pre_uac)
    category = workflow.ticket_category if workflow else "other"

    if _is_translation_moved_content_context(brief, pre_uac) and category == "bug":
        return [
            "| Translation panel / Map Console | Direct | Customer repro is opening translation for map content moved from `en` to `en_us` | S-01 |",
            "| Translation project creation API | Direct | Job creation must resolve moved map/topic paths and target language folders | S-01 |",
            "| Assets move metadata | Shared-path | Preserved UUID/reference metadata is the difference between moved content working or disappearing | S-03 |",
            "| Language-root resolver | Shared-path | `en`, `en_us`, and BCP-style `en-US` handling can disagree if code trusts only folder names | S-01 |",
            "| Translation status cache | Downstream | Status/out-of-sync views can stay stale after a path move | S-06 |",
        ]

    if "baseline" in topics and category == "feature_request":
        return [
            f"| Baseline table UI | High | Version comment column visible per topic row | {_scenario_id_for('column visible', scenarios)} |",
            f"| CSV export | High | Export includes Version comment values | {_scenario_id_for('csv export', scenarios, 'S-02')} |",
            f"| Filter / sort | Medium | Column filter/sort behaves like other columns (if in scope) | {_scenario_id_for('filter', scenarios, 'S-03')} |",
            f"| Legacy dashboard | Medium | Web Editor v2 vs legacy parity if PM confirms both surfaces | {_scenario_id_for('regression', scenarios, 'S-04')} |",
            f"| Topic metadata | Low | Displayed value matches topic Version comment metadata | S-01 |",
        ]
    if "asset_status" in topics and category == "bug":
        return [
            f"| POST /assets/status | High | Comma-containing DAM paths must not split or fail | S-01 |",
            f"| Async poll job | High | Terminal SUCCESS returns full path intact | S-01 |",
            f"| Normal paths | Medium | Control paths without comma still succeed | {_scenario_id_for('normal', scenarios, 'S-04')} |",
            f"| Batch API | Medium | Mixed comma + normal paths in one request | S-05 |",
            f"| Auth contract | High | Missing token returns HTTP 401 | {_scenario_id_for('auth', scenarios, 'S-06')} |",
        ]
    if _is_schematron_text_context(brief) and category == "bug":
        return [
            "| Schematron XPath context evaluation | Direct | Regression is specifically in `context=\"//text()\"` node-kind handling | S-01 |",
            "| Workspace Settings validation on save | Direct | Customer runs validation from Workspace Settings while saving DITA files | S-05 |",
            "| Explicit element contexts | Shared-path | Existing `context=\"//p\"` rules must not regress while fixing text nodes | S-02 |",
            "| Validation result panel / network contract | Downstream | Report visibility and actionable error mapping are the user-facing oracle | S-05 |",
            "| Multiple Schematron file configuration | Compatibility | Customers often attach multiple Schematron files in one workspace | S-06 |",
        ]

    filtered: list[dict[str, Any]] = []
    for item in blast:
        blob = f"{item.get('category', '')} {item.get('rationale', '')}"
        if category == "feature_request" and _OFF_TOPIC_BLAST_RE.search(blob):
            continue
        filtered.append(item)

    rows: list[str] = []
    for idx, item in enumerate(filtered[:5], start=1):
        sid = scenarios[min(idx - 1, len(scenarios) - 1)].scenario_id if scenarios else "S-01"
        rows.append(
            f"| {item.get('category', 'Area')} | {item.get('priority', 'Direct')} | "
            f"{str(item.get('rationale') or '')[:100]} | {sid} |"
        )
    if not rows:
        scope = brief.scope_hint or brief.component or "Primary surface"
        rows.append(f"| {scope} | Direct | Primary change surface from Jira | S-01 |")
    return rows


def build_risk_rows(
    risks: list[dict[str, Any]],
    scenarios: list[DefaultScenarioRow],
    workflow: TicketWorkflowProfile | None,
    pre_uac: PreUacProductBrief | None,
    brief: TicketBrief | None = None,
) -> list[str]:
    topics = _topic_ids(pre_uac)
    category = workflow.ticket_category if workflow else "other"

    if _is_translation_moved_content_context(brief, pre_uac) and category == "bug":
        return [
            "| RR-LANG-ROOT-MISMATCH | P0 | Resolver treats moved `en_us` path as different language than preserved UUID/source metadata | S-01 |",
            "| RR-ASSETS-MOVE-REFS | P0 | Assets move preserves UUID but translation scope still drops child topics or referenced assets | S-03 |",
            "| RR-STANDARD-TRANSLATION | P0 | Fix for moved content breaks normal language-root translation | S-02 |",
            "| RR-MIXED-MAP-POISON | P1 | One moved/invalid item disables the whole map instead of isolating the bad row | S-04 |",
            "| RR-DISABLE-REASON | P1 | Unsupported moved content shows blank panel/wrong list instead of actionable disabled reason/code | S-05 |",
            "| RR-STATUS-CACHE | P1 | Translation status/out-of-sync view uses stale path after Assets move | S-06 |",
        ]

    if "baseline" in topics and category == "feature_request":
        return [
            f"| RR-COLUMN-REGRESSION | P0 | Existing baseline columns (title, version, labels) break | {_scenario_id_for('regression', scenarios, 'S-04')} |",
            f"| RR-EXPORT-FORMAT | P0 | CSV export missing or corrupts Version comment column | {_scenario_id_for('csv export', scenarios, 'S-02')} |",
            f"| RR-FILTER-SORT | P1 | Filter/sort on new column fails or sorts wrong | {_scenario_id_for('filter', scenarios, 'S-03')} |",
            f"| RR-UI-PARITY | P1 | Legacy dashboard vs Web Editor baseline v2 differ | S-04 |",
            f"| RR-EMPTY-META | P1 | Empty Version comment causes UI error | {_scenario_id_for('without', scenarios, 'S-05')} |",
        ]
    if "asset_status" in topics and category == "bug":
        return [
            "| RR-COMMA-SPLIT | P0 | Path split on comma causes FAILED job | S-01 |",
            "| RR-NORMAL-REGRESSION | P0 | Valid non-comma paths regress | S-04 |",
            "| RR-BATCH-PARTIAL | P1 | One bad path fails entire batch | S-05 |",
            "| RR-AUTH-REGRESSION | P0 | Auth contract changes unexpectedly | S-06 |",
        ]
    if _is_schematron_text_context(brief) and category == "bug":
        return [
            "| RR-SCH-TEXTNODE | P0 | `//text()` rule still silently skipped after fix | S-01 |",
            "| RR-SCH-ELEMENT | P0 | Existing element-context rules regress while fixing text-node handling | S-02 |",
            "| RR-SCH-COVERAGE | P1 | Fix only handles paragraphs and misses title/list/note/table text nodes | S-03 |",
            "| RR-SCH-FALSEPOS | P1 | Clean content generates false Schematron reports | S-04 |",
            "| RR-SCH-MULTI | P1 | One Schematron file masks reports from another configured file | S-06 |",
        ]

    filtered = [
        item
        for item in risks
        if category != "feature_request" or str(item.get("id") or "") not in _GENERIC_RISK_IDS
    ]
    rows: list[str] = []
    for idx, item in enumerate(filtered[:5], start=1):
        rid = str(item.get("id") or f"R-{idx:02d}")
        sid = scenarios[min(idx - 1, len(scenarios) - 1)].scenario_id if scenarios else "S-01"
        rows.append(
            f"| {rid} | {item.get('priority', 'P1')} | {str(item.get('rationale') or '')[:100]} | {sid} |"
        )
    if not rows:
        rows.append("| R-DIRECT-01 | P0 | Primary failure mode from Jira | S-01 |")
    return rows


def build_hypothesis_rows(
    hypotheses: list[dict[str, Any]],
    scenarios: list[DefaultScenarioRow],
    workflow: TicketWorkflowProfile | None,
    pre_uac: PreUacProductBrief | None,
    brief: TicketBrief | None = None,
) -> list[str]:
    topics = _topic_ids(pre_uac)
    category = workflow.ticket_category if workflow else "other"

    if _is_translation_moved_content_context(brief, pre_uac) and category == "bug":
        return [
            "| BH-01 | Code derives source language from DAM folder name after move instead of original language/UUID metadata | `en_us` moved map missing from translation scope | S-01 |",
            "| BH-02 | Assets move updates paths but translation mapping/cache still points to old `en` location | stale path or empty Translation panel | S-01 |",
            "| BH-03 | Translation project API validates map paths differently from UI and hides disabled-row reason | UI/API mismatch or missing `disableCode`/message | S-03, S-05 |",
        ]

    if "baseline" in topics and category == "feature_request":
        return [
            f"| BH-01 | Empty Version comment shows error instead of blank/placeholder | UI error toast | {_scenario_id_for('without', scenarios, 'S-05')} |",
            f"| BH-02 | Large baseline pagination drops Version comment values | Missing values on page 2+ | S-01 |",
            f"| BH-03 | Legacy vs v2 baseline panels show different columns | Column mismatch between UIs | S-04 |",
        ]
    if "asset_status" in topics and category == "bug":
        return [
            "| BH-01 | Comma in path split into separate job property segments | Not an absolute path error | S-01 |",
            "| BH-02 | URL encoding vs raw comma handled inconsistently | Intermittent SUCCESS/FAILED | S-01 |",
            "| BH-03 | Poll response truncates path at comma | Partial path in status JSON | S-01 |",
        ]
    if _is_schematron_text_context(brief) and category == "bug":
        return [
            "| BH-01 | XSLT/Schematron wrapper filters out text node contexts before transform | `//p` works but `//text()` produces no report | S-01 |",
            "| BH-02 | Fix only whitelists element nodes, leaving mixed-content text unvisited | title/list/note/table text not reported | S-03 |",
            "| BH-03 | Error/report mapping collapses transform failures into generic fatal-content UI | Network has failed transform but panel lacks actionable report | S-05 |",
        ]

    if category == "feature_request":
        return [
            f"| BH-01 | New capability hidden behind wrong role/permission | Feature invisible to author | S-01 |",
            f"| BH-02 | Enhancement breaks adjacent workflow not in scope | Regression in related UI | S-02 |",
            f"| BH-03 | Empty/null property values cause UI error | Error instead of blank display | S-03 |",
        ]

    rows: list[str] = []
    for idx, item in enumerate(hypotheses[:3], start=1):
        sid = scenarios[0].scenario_id if scenarios else "S-01"
        rows.append(
            f"| BH-{idx:02d} | {str(item.get('rationale') or '')[:80]} | Log/error signal | {sid} |"
        )
    if not rows:
        rows.append("| BH-01 | Root-cause hypothesis from Jira | Customer repro fails | S-01 |")
    return rows


def build_regression_bullets(
    workflow: TicketWorkflowProfile | None,
    pre_uac: PreUacProductBrief | None,
    brief: TicketBrief,
) -> list[str]:
    topics = _topic_ids(pre_uac)
    category = workflow.ticket_category if workflow else "other"
    if _is_translation_moved_content_context(brief, pre_uac) and category == "bug":
        return [
            "Normal language-root translation project creation still works for an unmoved control map (S-02).",
            "Assets move does not drop map child topics, topicrefs, or referenced assets from translation scope (S-03).",
            "Mixed moved/unmoved maps do not disable valid sibling topics (S-04).",
            "Translation status and out-of-sync indicators remain accurate after source topic edits (S-06).",
        ]
    if "baseline" in topics and category == "feature_request":
        return [
            "Existing baseline columns (title, version, labels) and CSV export unchanged (S-04).",
            "Baseline create/edit/delete and label filtering still work on same map.",
            "Topics without Version comment metadata do not error (S-05).",
        ]
    if "asset_status" in topics and category == "bug":
        return [
            "Normal (non-comma) DAM paths still reach SUCCESS (S-04).",
            "401 returned for unauthenticated POST (S-06).",
            "Batch with mixed valid paths completes without whole-job FAILED (S-05).",
        ]
    if _is_schematron_text_context(brief) and category == "bug":
        return [
            "`context=\"//p\"` and other explicit element-context Schematron rules still report as before (S-02).",
            "Validation-on-save remains successful for clean topics and does not show false positives (S-04).",
            "Multiple Schematron files configured in Workspace Settings continue to evaluate independently (S-06).",
        ]
    if category == "feature_request":
        return [
            "Existing product behavior without the new capability still works (S-02 regression scenario).",
            "Adjacent flows called out in similar Jiras and repo evidence.",
        ]
    return ["Adjacent flows called out in similar Jiras and repo evidence."]


def build_historical_rows(
    similar: list[dict[str, Any]],
    key: str,
    brief: TicketBrief | None = None,
    pre_uac: PreUacProductBrief | None = None,
) -> list[str]:
    rows: list[str] = []
    for item in similar[:5]:
        jira_key = str(item.get("jira_key") or "").strip()
        if not jira_key or jira_key.upper() == key.upper():
            continue
        what_happened = str(item.get("title") or item.get("summary") or item.get("why_similar") or "Similar history")[:80]
        why = str(item.get("risk_signal") or item.get("why_similar") or "Same product area")[:100]
        rows.append(
            f"| {jira_key} | {what_happened} | {why} | S-01 |"
        )
    if not rows:
        if _is_translation_moved_content_context(brief, pre_uac):
            return [
                "| — | Historical search: no related Jiras returned by current packet | Run Jira MCP JQL for Translation + Assets move + `en_us` + `disableCode`; treat missing history as a blocker before final QE sign-off | S-01 |"
            ]
        return [
            "| — | Historical search: no related Jiras returned by current packet | Treat as evidence gap; run Jira MCP query for this component and failure mode before final sign-off | S-01 |"
        ]
    return rows


def dedupe_clarifications(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = re.sub(r"\s+", " ", item.strip().lower())[:100]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out[:8]
