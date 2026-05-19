from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.schemas_chat_authoring import (
    ChatDitaType,
    ChatDitaGenerationOptions,
    ChatImageContext,
    ReferenceAdoptionDecision,
    ChatSemanticPlan,
    ChatSemanticPlanSection,
    ReferenceStyleProfile,
    ScreenshotContentModel,
    ScreenshotProceduralModel,
    ScreenshotSettingsReferenceModel,
)


@dataclass
class DraftNote:
    kind: str
    text: str


@dataclass
class DraftTable:
    caption: str
    rows: list[list[str]]


@dataclass
class DraftProceduralSubstep:
    command: str
    info_lines: list[str] = field(default_factory=list)


@dataclass
class DraftProceduralStep:
    command: str
    info_lines: list[str] = field(default_factory=list)
    substeps: list[DraftProceduralSubstep] = field(default_factory=list)
    ui_controls: list[str] = field(default_factory=list)


@dataclass
class TopicDraft:
    dita_type: ChatDitaType
    title: str
    shortdesc: str
    sections: list[ChatSemanticPlanSection] = field(default_factory=list)
    notes: list[DraftNote] = field(default_factory=list)
    tables: list[DraftTable] = field(default_factory=list)
    code_snippets: list[str] = field(default_factory=list)
    procedural_model: ScreenshotProceduralModel | None = None
    procedural_steps: list[DraftProceduralStep] = field(default_factory=list)
    #: Structured settings / form / properties panel (reference topics).
    settings_reference_model: ScreenshotSettingsReferenceModel | None = None
    reference_adoption: ReferenceAdoptionDecision | None = None


def infer_topic_type(
    *,
    options: ChatDitaGenerationOptions,
    user_prompt: str,
    image_context: ChatImageContext,
    profile: ReferenceStyleProfile | None,
) -> ChatDitaType:
    if options.dita_type:
        if options.dita_type == "map":
            return "task"
        return options.dita_type
    prompt = (user_prompt or "").lower()
    for candidate in ("task", "concept", "reference", "topic"):
        if re.search(rf"\b{candidate}\b", prompt):
            return candidate  # type: ignore[return-value]
    sc = image_context.structured
    route = sc.screenshot_intent_route_decision.chosen_route if sc.screenshot_intent_route_decision else ""
    if route == "structure_reconstruction_mode":
        return "concept"
    if route == "procedural_authoring_mode":
        return "task"
    if route == "reference_extraction_mode":
        return "reference"
    if route == "conceptual_diagram_mode":
        return "concept"
    wf = (image_context.inferred_workflow or "").lower()
    if len(sc.numbered_steps) >= 2 or (wf and "step" in wf):
        return "task"
    if sc.settings_reference_model and (
        sc.settings_reference_model.sections
        or sc.settings_reference_model.tabs
        or sc.settings_reference_model.parameter_tables
    ):
        return "reference"
    if sc.field_value_pairs and len(sc.numbered_steps) == 0:
        return "reference"
    if len(sc.ui_labels) >= 6 or (len(sc.tables) >= 1 and len(sc.numbered_steps) == 0):
        return "reference"
    root = (profile.root_local_name if profile else "") or ""
    if root in ("task", "concept", "reference", "topic"):
        return root  # type: ignore[return-value]
    summ = (image_context.summary or "").strip()
    # When there are visible headings / sections but zero steps, prefer concept over task.
    # A UI screenshot with navigation labels and no numbered procedure is almost never a task.
    has_heading_structure = bool(sc.headings or sc.sections or sc.semantic_hierarchy)
    if len(sc.numbered_steps) == 0 and not sc.bullet_lists and has_heading_structure:
        return "concept"
    if summ and len(sc.numbered_steps) == 0 and not sc.bullet_lists:
        return "concept"
    return "task"


def merge_structured_into_plan(
    plan: ChatSemanticPlan,
    structured: ScreenshotContentModel,
) -> ChatSemanticPlan:
    """Enrich semantic plan with screenshot IR when LLM plan is thin."""
    sections = list(plan.sections)
    titles = {s.name.lower() for s in sections}
    procedural = structured.procedural_model
    policy = plan.reference_adoption.serializer_policy if plan.reference_adoption else None
    name_map = {str(key).strip().lower(): str(value).strip() for key, value in ((policy.preferred_section_name_map if policy else {}) or {}).items() if str(key).strip() and str(value).strip()}
    prefer_properties_layout = bool(policy and policy.prefer_properties_layout)
    field_details_name = name_map.get("field details", "properties" if prefer_properties_layout else "field details")
    parameter_tables_name = name_map.get("parameter tables", "properties tables" if prefer_properties_layout else "parameter tables")
    dialog_layout_name = name_map.get("dialog layout", "Dialog layout")
    steps_name = name_map.get("steps", "steps")
    acceptance_criteria_name = name_map.get("acceptance criteria", "acceptance criteria")
    details_name = name_map.get("details", "details")

    def _has_section(*names: str) -> bool:
        normalized = {str(name or "").strip().lower() for name in names if str(name or "").strip()}
        return any(name in titles for name in normalized)

    def _register_section_name(name: str) -> None:
        clean = str(name or "").strip().lower()
        if clean:
            titles.add(clean)

    if structured.numbered_steps and not _has_section("steps", steps_name):
        sections.append(
            ChatSemanticPlanSection(
                name=steps_name,
                purpose="Procedure from the screenshot.",
                details=list(structured.numbered_steps)[:12],
                list_kind="numbered",
            )
        )
        _register_section_name(steps_name)
    if structured.acceptance_criteria and not _has_section("acceptance criteria", acceptance_criteria_name):
        sections.append(
            ChatSemanticPlanSection(
                name=acceptance_criteria_name,
                purpose="Acceptance criteria visible in the screenshot.",
                details=list(structured.acceptance_criteria)[:15],
            )
        )
        _register_section_name(acceptance_criteria_name)

    if procedural:
        prereq_name = name_map.get("prereq", name_map.get("prerequisites", "prereq"))
        context_name = name_map.get("context", "context")
        result_name = name_map.get("result", "result")
        examples_name = name_map.get("examples", name_map.get("example", "examples"))
        if procedural.prerequisites and not _has_section("prereq", "prerequisites", prereq_name):
            sections.append(
                ChatSemanticPlanSection(
                    name=prereq_name,
                    purpose="Prerequisites recovered from the screenshot procedure.",
                    details=[item.text for item in procedural.prerequisites[:10]],
                )
            )
            _register_section_name(prereq_name)
        if procedural.context and not _has_section("context", context_name):
            sections.append(
                ChatSemanticPlanSection(
                    name=context_name,
                    purpose="Context recovered from the screenshot procedure.",
                    details=[item.text for item in procedural.context[:10]],
                )
            )
            _register_section_name(context_name)
        if procedural.steps and not _has_section("steps", steps_name):
            step_details: list[str] = []
            for step in procedural.steps[:20]:
                info = " ".join(step.info_lines[:2]).strip()
                detail = f"{step.command} || {info}" if info else step.command
                step_details.append(detail)
            sections.append(
                ChatSemanticPlanSection(
                    name=steps_name,
                    purpose="Ordered task steps recovered from the screenshot procedure.",
                    details=step_details,
                )
            )
            _register_section_name(steps_name)
        if procedural.result and not _has_section("result", result_name):
            sections.append(
                ChatSemanticPlanSection(
                    name=result_name,
                    purpose="Result text recovered from the screenshot procedure.",
                    details=[item.text for item in procedural.result[:10]],
                )
            )
            _register_section_name(result_name)
        if procedural.examples and not _has_section("examples", "example", examples_name):
            sections.append(
                ChatSemanticPlanSection(
                    name=examples_name,
                    purpose="Examples or command blocks recovered from the screenshot procedure.",
                    details=[item.text for item in procedural.examples[:8]],
                )
            )
            _register_section_name(examples_name)

    for node in structured.semantic_hierarchy[:10]:
        if not node.title:
            continue
        lower = node.title.lower()
        if lower in titles or node.level <= 1:
            continue
        sections.append(
            ChatSemanticPlanSection(
                name=node.title[:120],
                purpose=node.purpose or f"Recovered heading from screenshot layout (level {node.level}).",
                details=[],
            )
        )
        titles.add(lower)

    for sec in structured.sections[:8]:
        if sec.name and sec.name.lower() not in titles:
            titles.add(sec.name.lower())
            sections.append(
                ChatSemanticPlanSection(
                    name=sec.name[:120],
                    purpose=sec.purpose or f"Section: {sec.name[:120]}",
                    details=list(sec.details)[:10],
                )
            )
    for h in structured.headings[:8]:
        hn = h.text[:120]
        if hn and hn.lower() not in titles:
            titles.add(hn.lower())
            sections.append(
                ChatSemanticPlanSection(
                    name=hn,
                    purpose=f"Heading (level {h.level}) from screenshot",
                    details=[],
                )
            )
    if structured.bullet_lists and not any(s.name.lower() == "details" for s in sections):
        flat: list[str] = []
        for bl in structured.bullet_lists[:3]:
            flat.extend(bl[:12])
        if flat:
            sections.append(
                ChatSemanticPlanSection(
                    name="details",
                    purpose="Bulleted details from the screenshot.",
                    details=flat[:15],
                    list_kind="bullet",
                )
            )

    has_settings_ir = bool(
        structured.settings_reference_model
        and (
            structured.settings_reference_model.sections
            or structured.settings_reference_model.tabs
            or structured.settings_reference_model.parameter_tables
        )
    )
    settings_has_field_details = bool(
        structured.settings_reference_model
        and any(section.fields for section in structured.settings_reference_model.sections)
    )
    if has_settings_ir:
        sm = structured.settings_reference_model
        assert sm is not None
        for sec in sm.sections[:15]:
            stitle = (sec.title or "Settings").strip()[:120] or "Settings"
            if stitle.lower() in titles:
                continue
            details: list[str] = []
            tab_note = f"(Tab: {sec.tab}) " if sec.tab else ""
            for line in sec.description[:4]:
                if line.strip():
                    details.append(line.strip())
            for fld in sec.fields[:30]:
                ctl = fld.control_type if fld.control_type != "unknown" else "control"
                row = f"{tab_note}{fld.label}: {fld.value}".strip()
                if fld.helper_text:
                    row += " — " + " ".join(fld.helper_text[:3])
                if fld.options:
                    opts = ", ".join(
                        f"{o.label}{' (selected)' if o.selected else ''}" for o in fld.options[:12]
                    )
                    row += f" [{opts}]"
                details.append(row)
            for tbl in sec.parameter_tables[:2]:
                cap = (tbl.caption or "Parameters").strip()
                hdr = " | ".join(tbl.headers) if tbl.headers else ""
                body = "; ".join(" / ".join(r) for r in tbl.rows[:5])
                piece = f"Table {cap}: {hdr} {body}".strip()
                if piece:
                    details.append(piece)
            if details:
                titles.add(stitle.lower())
                sections.append(
                    ChatSemanticPlanSection(
                        name=stitle,
                        purpose="Settings or form fields grouped as in the screenshot.",
                        details=details[:40],
                    )
                )
        if sm.tabs and not _has_section("dialog layout", dialog_layout_name):
            tab_line = "Visible tabs: " + ", ".join(sm.tabs[:12])
            if sm.active_tab:
                tab_line += f". Active tab: {sm.active_tab}"
            sections.append(
                ChatSemanticPlanSection(
                    name=dialog_layout_name,
                    purpose="Tab strip or view switcher on the settings or properties UI.",
                    details=[tab_line],
                )
            )
            _register_section_name(dialog_layout_name)
    if (
        structured.field_value_pairs
        and not _has_section(field_details_name, "field details", "configuration values", "properties")
        and (not has_settings_ir or not settings_has_field_details)
    ):
        field_details = [f"{pair.field}: {pair.value}".strip(": ") for pair in structured.field_value_pairs[:15] if pair.field or pair.value]
        if field_details:
            sections.append(
                ChatSemanticPlanSection(
                    name=field_details_name,
                    purpose="Recovered field and value pairs from the screenshot.",
                    details=field_details,
                )
            )
            _register_section_name(field_details_name)

    if structured.tables and not _has_section(parameter_tables_name, "parameter tables"):
        lines = []
        for table in structured.tables[:4]:
            header = " | ".join(cell for cell in table.headers[:8] if cell)
            rows = "; ".join(" / ".join(cell for cell in row[:8] if cell) for row in table.rows[:4] if any(cell for cell in row))
            summary = " ".join(part for part in [table.caption, header, rows] if part).strip()
            if summary:
                lines.append(summary)
        if lines:
            sections.append(
                ChatSemanticPlanSection(
                    name=parameter_tables_name,
                    purpose="Tabular reference details recovered from the screenshot.",
                    details=lines[:8],
                )
            )
            _register_section_name(parameter_tables_name)

    preferred_order = [str(item).strip().lower() for item in ((policy.preferred_top_level_order if policy else []) or []) if str(item).strip()]
    if preferred_order:
        ordered_sections: list[ChatSemanticPlanSection] = []
        remaining = list(sections)
        for preferred in preferred_order:
            display_match = name_map.get(preferred, "")
            matched = [section for section in remaining if section.name.strip().lower() in {preferred, display_match.lower() if display_match else ""}]
            if matched:
                ordered_sections.extend(matched)
                matched_ids = {id(section) for section in matched}
                remaining = [section for section in remaining if id(section) not in matched_ids]
        sections = ordered_sections + remaining

    title = plan.title.strip() or structured.title.strip() or plan.title
    shortdesc = plan.shortdesc.strip()
    if not shortdesc and structured.title.strip():
        shortdesc = structured.title.strip()[:500]
    elif not shortdesc and structured.headings:
        shortdesc = structured.headings[0].text[:500]

    return ChatSemanticPlan(
        title=title or "Generated topic",
        dita_type=plan.dita_type,
        shortdesc=shortdesc or "Content derived from the attached screenshot.",
        audience=plan.audience,
        purpose=plan.purpose,
        sections=sections or plan.sections,
        style_notes=plan.style_notes,
        source_notes=plan.source_notes,
        reference_adoption=plan.reference_adoption,
    )


def build_topic_draft(
    *,
    plan: ChatSemanticPlan,
    image_context: ChatImageContext,
) -> TopicDraft:
    sc = image_context.structured
    notes = [DraftNote(kind=n.kind or "note", text=n.text) for n in sc.notes[:8]]
    tables = [DraftTable(caption=t.caption, rows=[list(r) for r in t.rows[:25]]) for t in sc.tables[:4]]
    sm = sc.settings_reference_model
    has_settings_ir = bool(
        sm and (sm.sections or sm.tabs or sm.parameter_tables or sm.helper_text)
    )
    if not tables and sc.field_value_pairs and not has_settings_ir:
        rows = [["Field", "Value"]]
        for pair in sc.field_value_pairs[:20]:
            if pair.field or pair.value:
                rows.append([pair.field or "", pair.value or ""])
        if len(rows) > 1:
            tables.append(DraftTable(caption="Field details", rows=rows))
    code = list(sc.code_snippets[:8])
    procedural_steps: list[DraftProceduralStep] = []
    if sc.procedural_model:
        notes = [DraftNote(kind=n.kind or "note", text=n.text) for n in sc.procedural_model.notes[:8]] or notes
        for step in sc.procedural_model.steps[:20]:
            procedural_steps.append(
                DraftProceduralStep(
                    command=step.command,
                    info_lines=list(step.info_lines),
                    substeps=[
                        DraftProceduralSubstep(command=sub.command, info_lines=list(sub.info_lines))
                        for sub in step.substeps[:12]
                    ],
                    ui_controls=list(step.ui_controls),
                )
            )
        for item in sc.procedural_model.examples[:8]:
            if item.kind in {"code", "command"} and item.text:
                code.append(item.text)
    return TopicDraft(
        dita_type=plan.dita_type,
        title=plan.title,
        shortdesc=plan.shortdesc,
        sections=list(plan.sections),
        notes=notes,
        tables=tables,
        code_snippets=code,
        procedural_model=sc.procedural_model,
        procedural_steps=procedural_steps,
        settings_reference_model=sc.settings_reference_model,
        reference_adoption=plan.reference_adoption,
    )
