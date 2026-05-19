from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from app.core.schemas_chat_authoring import (
    ChatDitaGenerationOptions,
    ChatSemanticPlanSection,
    ReferenceStyleProfile,
    ScreenshotSettingField,
)
from app.services.dita_topic_draft import TopicDraft
from app.services.dita_xml_headers import normalize_dita_document, replace_first_doctype_line


def _slug(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip().lower()).strip(".-")
    return cleaned or fallback


def indent_unit_from_profile(profile: ReferenceStyleProfile | None) -> str:
    """One indentation step per nesting level (default: two spaces)."""
    if not profile or not profile.xml_indent_style:
        return "  "
    m = {
        "space_2": "  ",
        "space_4": "    ",
        "tab": "\t",
    }
    return m.get(profile.xml_indent_style, "  ")


def _indent_xml(elem: ET.Element, level: int = 0, *, indent_unit: str = "  ") -> None:
    one = indent_unit
    indent = "\n" + level * one
    child_indent = "\n" + (level + 1) * one
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = child_indent
        for child in elem:
            _indent_xml(child, level + 1, indent_unit=indent_unit)
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = indent
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = indent


def _serializer_policy(draft: TopicDraft):
    if draft.reference_adoption and draft.reference_adoption.serializer_policy:
        return draft.reference_adoption.serializer_policy
    return None


def _taskbody_sequence(draft: TopicDraft, profile: ReferenceStyleProfile | None) -> list[str]:
    policy = _serializer_policy(draft)
    seq = list(policy.preferred_taskbody_sequence or []) if policy else []
    if not seq and profile:
        seq = list(profile.taskbody_top_level_sequence or [])
    return [item.strip().lower() for item in seq if item and item.strip()]


def _preferred_section_title(section_name: str, draft: TopicDraft) -> str:
    policy = _serializer_policy(draft)
    if not policy:
        return section_name.replace("-", " ").title()[:200]
    mapped = policy.preferred_section_name_map.get(section_name.strip().lower(), "") if policy.preferred_section_name_map else ""
    if mapped.strip():
        return mapped.strip()[:200]
    return section_name.replace("-", " ").title()[:200]


def _normalized_section_name(value: str) -> str:
    return " ".join((value or "").replace("-", " ").split()).strip().lower()


def _ordered_sections(draft: TopicDraft, sections: list[ChatSemanticPlanSection]) -> list[ChatSemanticPlanSection]:
    policy = _serializer_policy(draft)
    if not policy or not policy.preferred_section_names:
        return list(sections)

    preferred = [_normalized_section_name(name) for name in policy.preferred_section_names if _normalized_section_name(name)]
    if not preferred:
        return list(sections)

    bucketed: dict[str, list[ChatSemanticPlanSection]] = {}
    remainder: list[ChatSemanticPlanSection] = []
    for section in sections:
        display = _normalized_section_name(_preferred_section_title(section.name, draft))
        original = _normalized_section_name(section.name)
        match_key = next((pref for pref in preferred if pref in {display, original}), None)
        if match_key:
            bucketed.setdefault(match_key, []).append(section)
        else:
            remainder.append(section)

    ordered: list[ChatSemanticPlanSection] = []
    for pref in preferred:
        ordered.extend(bucketed.pop(pref, []))
    ordered.extend(remainder)
    for leftover in bucketed.values():
        ordered.extend(leftover)
    return ordered


def _extract_property_pairs(items: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in items:
        text = " ".join((item or "").split()).strip()
        if not text or ":" not in text:
            continue
        left, right = text.split(":", 1)
        left = left.strip()
        right = right.strip()
        if not left or not right:
            continue
        if len(left) > 120 or "http" in left.lower():
            continue
        pairs.append((left[:500], right[:800]))
    return pairs


def _append_properties(parent: ET.Element, rows: list[tuple[str, str]], *, title: str | None = None) -> None:
    if not rows:
        return
    if title:
        ET.SubElement(parent, "title").text = title[:200]
    props = ET.SubElement(parent, "properties")
    for label, value in rows[:80]:
        prop = ET.SubElement(props, "property")
        ET.SubElement(prop, "proptype").text = label
        ET.SubElement(prop, "propvalue").text = value


_NOTE_TYPE_MAP = {
    "caution": "caution",
    "warning": "warning",
    "important": "important",
    "tip": "tip",
    "note": "note",
    "danger": "danger",
    "attention": "attention",
}


def _propdesc_for_setting_field(field: ScreenshotSettingField) -> str:
    parts: list[str] = []
    parts.extend(h for h in (field.helper_text or [])[:6] if h and str(h).strip())
    if field.control_type and str(field.control_type) != "unknown":
        parts.append(f"Control type: {field.control_type}")
    if field.options:
        parts.append(
            "Options: "
            + "; ".join(
                f"{opt.label}{' (selected)' if opt.selected else ''}" for opt in field.options[:18] if opt.label
            )
        )
    out = " ".join(parts).strip()
    return out if out else " "


def _settings_section_titles_lower(sm) -> set[str]:
    return {sec.title.strip().lower() for sec in sm.sections if (sec.title or "").strip()}


def _serialize_reference_settings_body(
    root: ET.Element,
    draft: TopicDraft,
    options: ChatDitaGenerationOptions,
    use_uicontrol: bool,
    ui_label_hints: set[str],
) -> None:
    sm = draft.settings_reference_model
    if sm is None:
        _serialize_body(root, "refbody", draft, use_uicontrol, ui_label_hints, options)
        return

    body = ET.SubElement(root, "refbody")
    base = _slug(draft.title, "ref")
    policy = _serializer_policy(draft)
    use_cals = getattr(options, "authoring_pattern", "default") == "cisco_reference" or bool(
        policy and policy.prefer_cals_tables
    )

    for note in draft.notes[:6]:
        ntype = _NOTE_TYPE_MAP.get((note.kind or "note").lower(), "note")
        ne = ET.SubElement(body, "note", {"type": ntype})
        ET.SubElement(ne, "p").text = note.text

    refsyn = ET.SubElement(body, "refsyn")
    ET.SubElement(refsyn, "p").text = draft.shortdesc or "User interface parameters recovered from the screenshot."

    if sm.tabs:
        tab_line = "Visible tabs: " + ", ".join(sm.tabs[:24])
        if sm.active_tab:
            tab_line += f". Active tab: {sm.active_tab}."
        ET.SubElement(refsyn, "p").text = tab_line

    for hx in sm.helper_text[:10]:
        if hx.strip():
            ET.SubElement(refsyn, "p").text = hx.strip()

    emitted_titles = _settings_section_titles_lower(sm)

    for idx, sec in enumerate(sm.sections[:25], start=1):
        sid = f"{base}-cfg-{idx}"
        sec_el = ET.SubElement(body, "section", {"id": sid} if options.auto_ids else {})
        stitle = (sec.title or f"Settings {idx}").strip()[:200] or f"Settings {idx}"
        ET.SubElement(sec_el, "title").text = stitle
        if sec.tab:
            ET.SubElement(sec_el, "p").text = f"Tab: {sec.tab}"
        for line in sec.description[:12]:
            if line.strip():
                ET.SubElement(sec_el, "p").text = line.strip()

        if sec.fields:
            props = ET.SubElement(sec_el, "properties")
            for fi, fld in enumerate(sec.fields[:60], start=1):
                pattrs = {"id": f"{sid}-p-{fi}"} if options.auto_ids else {}
                prop = ET.SubElement(props, "property", pattrs)
                ET.SubElement(prop, "proptype").text = (fld.label or "Field")[:500] or "Field"
                ET.SubElement(prop, "propvalue").text = (fld.value or "—")[:800] or "—"
                pd = ET.SubElement(prop, "propdesc")
                ET.SubElement(pd, "p").text = _propdesc_for_setting_field(fld)

        for tbl in sec.parameter_tables[:5]:
            rows = [tbl.headers] + tbl.rows if tbl.headers else tbl.rows
            if rows:
                _emit_tabular(sec_el, tbl.caption or "Parameters", rows, use_cals=use_cals)

    for ti, tbl in enumerate(sm.parameter_tables[:8], start=1):
        sid = f"{base}-tbl-{ti}"
        sec_el = ET.SubElement(body, "section", {"id": sid} if options.auto_ids else {})
        if tbl.caption:
            ET.SubElement(sec_el, "title").text = tbl.caption[:200]
        rows = [tbl.headers] + tbl.rows if tbl.headers else tbl.rows
        if rows:
            _emit_tabular(sec_el, "", rows, use_cals=use_cals)

    for section in draft.sections:
        ln = section.name.strip().lower()
        if ln in emitted_titles or ln in {"dialog layout", "field details", "properties", "properties tables"}:
            continue
        if ln == "details" and (sm.sections or sm.tabs):
            continue
        content_items = _section_content_items(section)
        prop_rows = _extract_property_pairs(content_items) if policy and policy.prefer_properties_layout else []
        idx = len(emitted_titles) + 50
        emitted_titles.add(ln)
        sec_el = ET.SubElement(body, "section", {"id": f"{base}-plan-{idx}"} if options.auto_ids else {})
        ET.SubElement(sec_el, "title").text = _preferred_section_title(section.name, draft)
        if policy and policy.prefer_properties_layout and prop_rows and len(prop_rows) >= max(1, min(2, len(content_items))):
            _append_properties(sec_el, prop_rows)
        else:
            _append_paragraphs(sec_el, section, max_items=14)

    for tbl in draft.tables[:4]:
        _emit_tabular(body, tbl.caption, tbl.rows, use_cals=use_cals)

    for code in draft.code_snippets[:4]:
        ex = ET.SubElement(body, "example")
        cb = ET.SubElement(ex, "codeblock")
        cb.text = code


def _append_paragraphs(parent: ET.Element, section: ChatSemanticPlanSection, *, max_items: int = 12) -> None:
    """Serialize section details as DITA list or paragraphs depending on list_kind.

    - list_kind == "bullet"   → <ul><li><p>…</p></li>…</ul>
    - list_kind == "numbered" → <ol><li><p>…</p></li>…</ol>
    - otherwise               → one <p> per detail item
    """
    content = _section_content_items(section)
    items = content[:max_items]
    if not items:
        return
    kind = (getattr(section, "list_kind", "") or "").strip().lower()
    if kind == "bullet" and len(items) >= 2:
        ul = ET.SubElement(parent, "ul")
        for item in items:
            li = ET.SubElement(ul, "li")
            ET.SubElement(li, "p").text = item
    elif kind == "numbered" and len(items) >= 2:
        ol = ET.SubElement(parent, "ol")
        for item in items:
            li = ET.SubElement(ol, "li")
            ET.SubElement(li, "p").text = item
    else:
        for item in items:
            ET.SubElement(parent, "p").text = item


_GENERIC_PURPOSE_PREFIXES = (
    "explain ",
    "describe ",
    "document ",
    "summarize ",
    "state ",
    "list ",
    "heading ",
    "section:",
)


def _purpose_is_publishable(purpose: str) -> bool:
    text = " ".join((purpose or "").split()).strip()
    if not text:
        return False
    lowered = text.lower()
    if any(lowered.startswith(prefix) for prefix in _GENERIC_PURPOSE_PREFIXES):
        return False
    if "recovered from the screenshot" in lowered:
        return False
    if "visible " in lowered and ("structure" in lowered or "content" in lowered or "summary" in lowered):
        return False
    return True


# Single-token HTML/DOM tag names that should never appear as standalone paragraph text.
# The vision model sometimes emits the raw DOM tree node labels (e.g. "body", "ul", "li")
# as separate "bullet" items — we strip them before rendering.
_DOM_NOISE_TOKENS: frozenset[str] = frozenset({
    "body", "html", "head", "div", "span", "ul", "ol", "li", "p", "a",
    "table", "thead", "tbody", "tr", "th", "td", "form", "input", "button",
    "nav", "header", "footer", "main", "section", "article", "aside",
    "h1", "h2", "h3", "h4", "h5", "h6", "br", "hr", "img", "figure",
    "figcaption", "label", "select", "option", "textarea", "iframe",
})


def _is_dom_noise(text: str) -> bool:
    """Return True if *text* is a bare HTML/DOM tag name with no surrounding context."""
    stripped = text.strip().lower()
    return stripped in _DOM_NOISE_TOKENS


def _section_content_items(
    section: ChatSemanticPlanSection,
    *,
    include_purpose_when_no_details: bool = False,
) -> list[str]:
    details = [detail.strip() for detail in section.details if detail.strip() and not _is_dom_noise(detail)]
    if details:
        return details
    purpose = section.purpose.strip()
    if include_purpose_when_no_details and _purpose_is_publishable(purpose):
        return [purpose]
    return []


def _find_section_by_names(draft: TopicDraft, names: tuple[str, ...]) -> ChatSemanticPlanSection | None:
    want = {n.lower() for n in names}
    for s in draft.sections:
        if s.name.strip().lower() in want:
            return s
    return None


def _split_cmd_and_info(detail: str) -> tuple[str, str]:
    d = (detail or "").strip()
    if " || " in d:
        a, b = d.split(" || ", 1)
        return a.strip(), b.strip()
    if "\n\n" in d:
        a, b = d.split("\n\n", 1)
        return a.strip(), b.strip()
    return d, ""


def _parse_gui_cli_prefix(text: str) -> tuple[str | None, str]:
    """Return (ui-type value ``gui``/``cli`` or None, remainder). Prefix is case-insensitive."""
    t = (text or "").strip()
    ul = t.upper()
    if ul.startswith("GUI:"):
        return "gui", t[4:].strip()
    if ul.startswith("CLI:"):
        return "cli", t[4:].strip()
    return None, t


def _split_step_detail(detail: str) -> tuple[str | None, str, list[str]]:
    """Return ``(ui-type or None, cmd text, info paragraphs)`` for one step line."""
    d = (detail or "").strip()
    if not d:
        return None, "", []
    parts = re.split(r"\s*\|\|\s*", d)
    ui, cmd = _parse_gui_cli_prefix(parts[0].strip())
    infos = [p.strip() for p in parts[1:] if p.strip()]
    return ui, cmd, infos


def _append_cisco_context(ctx: ET.Element, section: ChatSemanticPlanSection, *, profile: ReferenceStyleProfile | None) -> None:
    content = _section_content_items(section)
    use_ui = bool(profile and profile.reference_uses_ui_type_attributes)
    for item in content[:12]:
        ut, body = _parse_gui_cli_prefix(item)
        attrs: dict[str, str] = {}
        if use_ui and ut:
            attrs["ui-type"] = ut
        p_el = ET.SubElement(ctx, "p", attrs)
        p_el.text = body


def _append_prereq_cisco(
    pr: ET.Element,
    section: ChatSemanticPlanSection,
    *,
    options: ChatDitaGenerationOptions,
    base: str,
    use_list: bool,
) -> None:
    content = _section_content_items(section)
    bullets = [c for c in content if c]
    if use_list and len(bullets) >= 2:
        ul = ET.SubElement(pr, "ul")
        for index, item in enumerate(bullets[:12], start=1):
            li_attrs: dict[str, str] = {}
            if options.auto_ids:
                li_attrs["id"] = f"{base}-prereq-li-{index}"
            li = ET.SubElement(ul, "li", li_attrs)
            ET.SubElement(li, "p").text = item
        return
    _append_paragraphs(pr, section)


def _append_info_lines(parent: ET.Element, lines: list[str]) -> None:
    if not lines:
        return
    info_el = ET.SubElement(parent, "info")
    for line in lines[:6]:
        if line.strip():
            ET.SubElement(info_el, "p").text = line.strip()


def _append_procedural_steps(
    *,
    steps_el: ET.Element,
    draft: TopicDraft,
    options: ChatDitaGenerationOptions,
    base: str,
    use_codeph: bool,
    code_tokens: set[str],
    ui_label_hints: set[str],
    use_uicontrol: bool,
) -> bool:
    if not draft.procedural_steps:
        return False
    for index, step_data in enumerate(draft.procedural_steps[:20], start=1):
        step_attrs: dict[str, str] = {}
        if options.auto_ids:
            step_attrs["id"] = f"{base}-step-{index}"
        step_el = ET.SubElement(steps_el, "step", step_attrs)
        cmd_el = ET.SubElement(step_el, "cmd")
        applied = use_codeph and _apply_codeph_in_cmd(cmd_el, step_data.command, code_tokens)
        if not applied:
            _fill_cmd_uicontrol(cmd_el, step_data.command, set(step_data.ui_controls) | ui_label_hints, use_uicontrol)
        _append_info_lines(step_el, step_data.info_lines)
        if step_data.substeps:
            substeps_el = ET.SubElement(step_el, "substeps")
            for sub_index, substep in enumerate(step_data.substeps[:12], start=1):
                sub_attrs: dict[str, str] = {}
                if options.auto_ids:
                    sub_attrs["id"] = f"{base}-step-{index}-substep-{sub_index}"
                sub_el = ET.SubElement(substeps_el, "substep", sub_attrs)
                sub_cmd = ET.SubElement(sub_el, "cmd")
                applied_sub = use_codeph and _apply_codeph_in_cmd(sub_cmd, substep.command, code_tokens)
                if not applied_sub:
                    _fill_cmd_uicontrol(sub_cmd, substep.command, ui_label_hints, use_uicontrol)
                _append_info_lines(sub_el, substep.info_lines)
    return True


def _apply_codeph_in_cmd(cmd: ET.Element, text: str, code_tokens: set[str]) -> bool:
    for tok in sorted(code_tokens, key=len, reverse=True):
        if tok and tok in text:
            i = text.index(tok)
            before, after = text[:i], text[i + len(tok) :]
            if before:
                cmd.text = before
            cp = ET.SubElement(cmd, "codeph")
            cp.text = tok
            if after.strip():
                ph = ET.SubElement(cmd, "ph")
                ph.text = after.strip()
            return True
    return False


def _fill_cmd_uicontrol(cmd: ET.Element, text: str, labels: set[str], use_uicontrol: bool) -> None:
    if not use_uicontrol or not labels:
        cmd.text = text
        return
    for label in sorted(labels, key=len, reverse=True):
        if label and label in text:
            i = text.index(label)
            if i > 0:
                cmd.text = text[:i]
            uc = ET.SubElement(cmd, "uicontrol")
            uc.text = label
            rest = text[i + len(label) :]
            if rest:
                ph = ET.SubElement(cmd, "ph")
                ph.text = rest
            return
    cmd.text = text


def _add_simpletable(parent: ET.Element, caption: str, rows: list[list[str]]) -> None:
    if not rows:
        return
    st = ET.SubElement(parent, "simpletable")
    if caption:
        t = ET.SubElement(st, "title")
        t.text = caption
    ncol = max(len(r) for r in rows) if rows else 1
    strow = ET.SubElement(st, "sthead")
    for i in range(ncol):
        cell = rows[0][i] if i < len(rows[0]) else ""
        stentry = ET.SubElement(strow, "stentry")
        stentry.text = cell
    data_rows = rows[1:] if len(rows) > 1 else []
    for row in data_rows[:40]:
        strow = ET.SubElement(st, "strow")
        for i in range(ncol):
            cell = row[i] if i < len(row) else ""
            stentry = ET.SubElement(strow, "stentry")
            stentry.text = cell


def _add_cals_table(parent: ET.Element, caption: str, rows: list[list[str]]) -> None:
    if not rows:
        return
    ncol = max(len(r) for r in rows) if rows else 1
    tbl = ET.SubElement(parent, "table")
    if caption:
        ET.SubElement(tbl, "title").text = caption
    tgroup = ET.SubElement(tbl, "tgroup", {"cols": str(ncol)})
    for i in range(1, ncol + 1):
        ET.SubElement(tgroup, "colspec", {"colname": f"c{i}", "colnum": str(i), "colwidth": "1*"})

    def _entry(row_el: ET.Element, col_idx: int, row: list[str]) -> None:
        cell = row[col_idx] if col_idx < len(row) else ""
        ET.SubElement(row_el, "entry").text = cell

    if len(rows) == 1:
        tbody = ET.SubElement(tgroup, "tbody")
        er = ET.SubElement(tbody, "row")
        for i in range(ncol):
            _entry(er, i, rows[0])
        return

    thead = ET.SubElement(tgroup, "thead")
    hrow = ET.SubElement(thead, "row")
    hdr = rows[0]
    for i in range(ncol):
        _entry(hrow, i, hdr)
    tbody = ET.SubElement(tgroup, "tbody")
    for row in rows[1:40]:
        er = ET.SubElement(tbody, "row")
        for i in range(ncol):
            _entry(er, i, row)


def _emit_tabular(parent: ET.Element, caption: str, rows: list[list[str]], *, use_cals: bool) -> None:
    if use_cals:
        _add_cals_table(parent, caption, rows)
    else:
        _add_simpletable(parent, caption, rows)


def serialize_topic_draft(
    draft: TopicDraft,
    *,
    profile: ReferenceStyleProfile | None,
    options: ChatDitaGenerationOptions,
    ui_label_hints: set[str],
) -> str:
    dita_type = draft.dita_type
    topic_id = _slug(draft.title, f"generated-{dita_type}")
    root_attrs: dict[str, str] = {}
    if options.auto_ids:
        root_attrs["id"] = topic_id
    lang = "en-US"
    outclass = None
    policy = _serializer_policy(draft)
    if profile and profile.root_attributes_sample:
        lang = profile.root_attributes_sample.get("xml:lang") or profile.root_attributes_sample.get("lang") or lang
        outclass = profile.root_attributes_sample.get("outputclass")
        adoption_mode = draft.reference_adoption.mode if draft.reference_adoption else ""
        if adoption_mode in {"compatible_adoption", "partial_adoption"}:
            for attr_name, attr_value in profile.root_attributes_sample.items():
                key = (attr_name or "").strip()
                if not key or key in {"xml:lang", "lang", "outputclass"}:
                    continue
                value = str(attr_value or "").strip()
                if not value:
                    continue
                root_attrs[key] = value[:300]
    root_attrs["xml:lang"] = lang
    if outclass:
        root_attrs["outputclass"] = outclass

    root = ET.Element(dita_type, root_attrs)
    ET.SubElement(root, "title").text = draft.title
    ET.SubElement(root, "shortdesc").text = draft.shortdesc

    use_uicontrol = bool(profile and (profile.inline_element_usage.get("uicontrol") or 0) > 0)
    use_uicontrol = use_uicontrol or bool(policy and policy.prefer_uicontrol)
    ap = getattr(options, "authoring_pattern", "default")
    use_cisco_task = dita_type == "task" and ap == "cisco_task"
    use_cisco_ref = dita_type == "reference" and ap == "cisco_reference"
    if use_cisco_task or use_cisco_ref:
        use_uicontrol = use_uicontrol or bool(ui_label_hints)

    preserve_prolog = bool(options.preserve_prolog) or bool(policy and policy.prefer_prolog)
    if preserve_prolog and profile and profile.uses_prolog:
        prolog = ET.SubElement(root, "prolog")
        meta = ET.SubElement(prolog, "metadata")
        keys = ET.SubElement(meta, "keywords")
        ET.SubElement(keys, "keyword")
    elif use_cisco_task:
        prolog = ET.SubElement(root, "prolog")
        meta = ET.SubElement(prolog, "metadata")
        keys = ET.SubElement(meta, "keywords")
        kw = ET.SubElement(keys, "keyword")
        kw.text = (_slug(draft.title, "procedure"))[:120] or "procedure"
    elif use_cisco_ref:
        prolog = ET.SubElement(root, "prolog")
        meta = ET.SubElement(prolog, "metadata")
        keys = ET.SubElement(meta, "keywords")
        kw = ET.SubElement(keys, "keyword")
        kw.text = (_slug(draft.title, "reference"))[:120] or "reference"

    if dita_type == "task":
        if use_cisco_task:
            _serialize_cisco_enterprise_task_body(
                root, draft, options, use_uicontrol, ui_label_hints, profile
            )
        else:
            _serialize_task_body(root, draft, options, use_uicontrol, ui_label_hints, profile)
    elif dita_type == "concept":
        _serialize_body(root, "conbody", draft, use_uicontrol, ui_label_hints, options)
    elif dita_type == "reference":
        if draft.settings_reference_model and (
            draft.settings_reference_model.sections
            or draft.settings_reference_model.tabs
            or draft.settings_reference_model.parameter_tables
            or draft.settings_reference_model.helper_text
        ):
            _serialize_reference_settings_body(root, draft, options, use_uicontrol, ui_label_hints)
        else:
            _serialize_reference_body(root, draft, use_uicontrol, ui_label_hints, options)
    else:
        _serialize_body(root, "body", draft, use_uicontrol, ui_label_hints, options)

    _indent_xml(root, indent_unit=indent_unit_from_profile(profile))
    xml_body = ET.tostring(root, encoding="unicode", short_empty_elements=False)
    normalized, _ = normalize_dita_document(xml_body, dita_type)
    preserve_dt = (
        bool(getattr(options, "preserve_reference_doctype", False))
        or ap in ("cisco_task", "cisco_reference")
        or bool(policy and draft.reference_adoption and draft.reference_adoption.mode == "compatible_adoption")
    )
    if profile and profile.declared_doctype_line and preserve_dt:
        dt_line = profile.declared_doctype_line.lower()
        root_ok = (dita_type == "task" and "task" in dt_line) or (dita_type == "reference" and "reference" in dt_line)
        if root_ok:
            normalized = replace_first_doctype_line(normalized, profile.declared_doctype_line.strip())
    return normalized


def _serialize_cisco_enterprise_task_body(
    root: ET.Element,
    draft: TopicDraft,
    options: ChatDitaGenerationOptions,
    use_uicontrol: bool,
    ui_label_hints: set[str],
    profile: ReferenceStyleProfile | None,
) -> None:
    """
    Enterprise task ordering: prereq → context → notes → steps (cmd [+info]) → sections →
    examples (tables/code) → result → postreq. Fresh ids only; no xref/conref emitted here.

    DITA 1.3 note: ``<section>`` is NOT a valid child of ``<taskbody>`` (taskbody allows
    ``(prereq?, context?, (steps|steps-unordered|steps-informal)?, result?, example*, postreq?)``).
    Free-form draft sections that don't map to one of the reserved task slots are therefore
    serialized as ``<example>`` elements, which are repeatable and accept a ``<title>`` plus
    rich block content (paragraphs, lists, simpletable, codeblock, etc.).
    """
    taskbody = ET.SubElement(root, "taskbody")
    base = _slug(draft.title, "generated")
    code_tokens = {c.strip() for c in draft.code_snippets if c and c.strip()}
    use_codeph = bool(code_tokens)

    steps_section = _find_section_by_names(draft, ("steps",))
    details: list[str] = []
    if steps_section:
        details = _section_content_items(steps_section, include_purpose_when_no_details=False)
    if not details:
        details = [draft.shortdesc or "Complete the procedure shown in the user interface."]
    prereq_sec = _find_section_by_names(draft, ("prereq", "prerequisite", "prerequisites"))
    context_section = _find_section_by_names(draft, ("context",))
    result_section = _find_section_by_names(draft, ("result",))
    ac_section = next((s for s in draft.sections if "acceptance" in s.name.lower()), None)
    reserved = {
        "context",
        "steps",
        "result",
        "prereq",
        "prerequisite",
        "prerequisites",
    }

    def emit_prereq() -> None:
        if prereq_sec:
            pr = ET.SubElement(taskbody, "prereq")
            _append_paragraphs(pr, prereq_sec)
        elif draft.procedural_model and draft.procedural_model.prerequisites:
            pr = ET.SubElement(taskbody, "prereq")
            for item in draft.procedural_model.prerequisites[:8]:
                ET.SubElement(pr, "p").text = item.text

    def emit_context() -> None:
        if context_section:
            ctx = ET.SubElement(taskbody, "context")
            _append_paragraphs(ctx, context_section)
        elif draft.procedural_model and draft.procedural_model.context:
            ctx = ET.SubElement(taskbody, "context")
            for item in draft.procedural_model.context[:8]:
                ET.SubElement(ctx, "p").text = item.text

    def emit_notes() -> None:
        for note in draft.notes[:6]:
            ntype = _NOTE_TYPE_MAP.get((note.kind or "note").lower(), "note")
            ne = ET.SubElement(taskbody, "note", {"type": ntype})
            ET.SubElement(ne, "p").text = note.text

    def emit_steps() -> None:
        steps_el = ET.SubElement(taskbody, "steps")
        used_procedural = _append_procedural_steps(
            steps_el=steps_el,
            draft=draft,
            options=options,
            base=base,
            use_codeph=use_codeph,
            code_tokens=code_tokens,
            ui_label_hints=ui_label_hints,
            use_uicontrol=use_uicontrol,
        )
        if not used_procedural:
            for index, detail in enumerate(details[:20], start=1):
                step_attrs: dict[str, str] = {}
                if options.auto_ids:
                    step_attrs["id"] = f"{base}-step-{index}"
                step = ET.SubElement(steps_el, "step", step_attrs)
                cmd_part, info_part = _split_cmd_and_info(detail)
                cmd_el = ET.SubElement(step, "cmd")
                applied = use_codeph and _apply_codeph_in_cmd(cmd_el, cmd_part, code_tokens)
                if not applied:
                    _fill_cmd_uicontrol(cmd_el, cmd_part, ui_label_hints, use_uicontrol)
                if info_part:
                    info_el = ET.SubElement(step, "info")
                    ET.SubElement(info_el, "p").text = info_part

    def emit_sections() -> None:
        for section in draft.sections:
            ln = section.name.lower()
            if ln in reserved or "acceptance" in ln:
                continue
            ex = ET.SubElement(
                taskbody,
                "example",
                {"id": _slug(section.name, "example")} if options.auto_ids else {},
            )
            ET.SubElement(ex, "title").text = _preferred_section_title(section.name, draft)
            _append_paragraphs(ex, section)

    def emit_examples() -> None:
        if draft.tables[:3]:
            ex_attrs = {"id": _slug("figures-and-tables", "example")} if options.auto_ids else {}
            ex = ET.SubElement(taskbody, "example", ex_attrs)
            ET.SubElement(ex, "title").text = "Figures and tables"
            for tbl in draft.tables[:3]:
                _add_simpletable(ex, tbl.caption or "", tbl.rows)
        extra_code = draft.code_snippets[:4]
        if extra_code:
            ex2_attrs = {"id": _slug("commands-and-code", "example")} if options.auto_ids else {}
            ex2 = ET.SubElement(taskbody, "example", ex2_attrs)
            ET.SubElement(ex2, "title").text = "Commands and code"
            for code in extra_code:
                cb = ET.SubElement(ex2, "codeblock")
                cb.text = code

    def emit_result() -> None:
        if result_section:
            res = ET.SubElement(taskbody, "result")
            _append_paragraphs(res, result_section)
        elif draft.procedural_model and draft.procedural_model.result:
            res = ET.SubElement(taskbody, "result")
            for item in draft.procedural_model.result[:8]:
                ET.SubElement(res, "p").text = item.text

    def emit_postreq() -> None:
        if ac_section:
            postreq = ET.SubElement(taskbody, "postreq")
            ET.SubElement(postreq, "p").text = (
                "Verify the following before you close this change request or publish."
            )
            ol = ET.SubElement(postreq, "ol")
            for item in _section_content_items(ac_section, include_purpose_when_no_details=False)[:20]:
                li = ET.SubElement(ol, "li")
                ET.SubElement(li, "p").text = item

    emitters = {
        "prereq": emit_prereq,
        "context": emit_context,
        "note": emit_notes,
        "steps": emit_steps,
        "section": emit_sections,
        "example": emit_examples,
        "result": emit_result,
        "postreq": emit_postreq,
    }
    emitted: set[str] = set()
    for tag in _taskbody_sequence(draft, profile):
        fn = emitters.get(tag)
        if fn:
            fn()
            emitted.add(tag)
    for tag in ("prereq", "context", "note", "steps", "section", "example", "result", "postreq"):
        if tag not in emitted:
            emitters[tag]()


def _serialize_task_body(
    root: ET.Element,
    draft: TopicDraft,
    options: ChatDitaGenerationOptions,
    use_uicontrol: bool,
    ui_label_hints: set[str],
    profile: ReferenceStyleProfile | None,
) -> None:
    """Default task body serializer.

    DITA 1.3 note: ``<section>`` is NOT a valid child of ``<taskbody>``. Free-form
    draft sections and tables that aren't mapped to ``prereq``/``context``/``steps``/
    ``result``/``postreq`` are therefore emitted as ``<example>`` elements, which are
    repeatable in ``<taskbody>`` and accept a ``<title>`` plus rich block content
    (paragraphs, lists, ``<simpletable>``, ``<codeblock>``, etc.).
    """
    taskbody = ET.SubElement(root, "taskbody")
    prereq_section = _find_section_by_names(draft, ("prereq", "prerequisite", "prerequisites"))

    context_section = next((s for s in draft.sections if s.name.lower() == "context"), None)

    steps_section = next((s for s in draft.sections if s.name.lower() == "steps"), None)
    details: list[str] = []
    if steps_section:
        details = _section_content_items(steps_section, include_purpose_when_no_details=False)
    if not details:
        details = [draft.shortdesc or "Complete the procedure shown in the user interface."]
    base = _slug(draft.title, "generated")

    result_section = next((s for s in draft.sections if s.name.lower() == "result"), None)

    ac_section = next((s for s in draft.sections if "acceptance" in s.name.lower()), None)

    def emit_prereq() -> None:
        if prereq_section:
            pr = ET.SubElement(taskbody, "prereq")
            _append_paragraphs(pr, prereq_section)
        elif draft.procedural_model and draft.procedural_model.prerequisites:
            pr = ET.SubElement(taskbody, "prereq")
            for item in draft.procedural_model.prerequisites[:8]:
                ET.SubElement(pr, "p").text = item.text

    def emit_context() -> None:
        if context_section:
            ctx = ET.SubElement(taskbody, "context")
            _append_paragraphs(ctx, context_section)
        elif draft.procedural_model and draft.procedural_model.context:
            ctx = ET.SubElement(taskbody, "context")
            for item in draft.procedural_model.context[:8]:
                ET.SubElement(ctx, "p").text = item.text

    def emit_notes() -> None:
        for note in draft.notes[:6]:
            ntype = _NOTE_TYPE_MAP.get((note.kind or "note").lower(), "note")
            ne = ET.SubElement(taskbody, "note", {"type": ntype})
            ET.SubElement(ne, "p").text = note.text

    def emit_steps() -> None:
        steps_el = ET.SubElement(taskbody, "steps")
        used_procedural = _append_procedural_steps(
            steps_el=steps_el,
            draft=draft,
            options=options,
            base=base,
            use_codeph=False,
            code_tokens=set(),
            ui_label_hints=ui_label_hints,
            use_uicontrol=use_uicontrol,
        )
        if not used_procedural:
            for index, detail in enumerate(details[:20], start=1):
                step_attrs: dict[str, str] = {}
                if options.auto_ids:
                    step_attrs["id"] = f"{base}-step-{index}"
                step = ET.SubElement(steps_el, "step", step_attrs)
                cmd_el = ET.SubElement(step, "cmd")
                _fill_cmd_uicontrol(cmd_el, detail, ui_label_hints, use_uicontrol)

    def emit_sections() -> None:
        for section in draft.sections:
            ln = section.name.lower()
            if ln in {"context", "steps", "result", "prereq", "prerequisite", "prerequisites"} or "acceptance" in ln:
                continue
            ex = ET.SubElement(
                taskbody,
                "example",
                {"id": _slug(section.name, "example")} if options.auto_ids else {},
            )
            ET.SubElement(ex, "title").text = _preferred_section_title(section.name, draft)
            _append_paragraphs(ex, section)
        for tbl in draft.tables[:3]:
            ex = ET.SubElement(
                taskbody,
                "example",
                {"id": _slug(tbl.caption or "table", "table-example")} if options.auto_ids else {},
            )
            if tbl.caption:
                ET.SubElement(ex, "title").text = tbl.caption[:200]
            _add_simpletable(ex, "", tbl.rows)

    def emit_examples() -> None:
        for index, code in enumerate(draft.code_snippets[:4], start=1):
            ex_attrs = {"id": _slug(f"code-example-{index}", "example")} if options.auto_ids else {}
            ex = ET.SubElement(taskbody, "example", ex_attrs)
            cb = ET.SubElement(ex, "codeblock")
            cb.text = code

    def emit_result() -> None:
        if result_section:
            res = ET.SubElement(taskbody, "result")
            _append_paragraphs(res, result_section)
        elif draft.procedural_model and draft.procedural_model.result:
            res = ET.SubElement(taskbody, "result")
            for item in draft.procedural_model.result[:8]:
                ET.SubElement(res, "p").text = item.text

    def emit_postreq() -> None:
        if ac_section:
            postreq = ET.SubElement(taskbody, "postreq")
            ET.SubElement(postreq, "p").text = (
                "Before closing this task, verify the following acceptance criteria "
                "(align with AEM Guides review and release gates)."
            )
            ol = ET.SubElement(postreq, "ol")
            for item in _section_content_items(ac_section, include_purpose_when_no_details=False)[:20]:
                li = ET.SubElement(ol, "li")
                ET.SubElement(li, "p").text = item

    emitters = {
        "prereq": emit_prereq,
        "context": emit_context,
        "note": emit_notes,
        "steps": emit_steps,
        "section": emit_sections,
        "example": emit_examples,
        "result": emit_result,
        "postreq": emit_postreq,
    }
    emitted: set[str] = set()
    for tag in _taskbody_sequence(draft, profile):
        fn = emitters.get(tag)
        if fn:
            fn()
            emitted.add(tag)
    for tag in ("prereq", "context", "note", "steps", "section", "example", "result", "postreq"):
        if tag not in emitted:
            emitters[tag]()


def _serialize_reference_body(
    root: ET.Element,
    draft: TopicDraft,
    use_uicontrol: bool,
    ui_label_hints: set[str],
    options: ChatDitaGenerationOptions,
) -> None:
    policy = _serializer_policy(draft)
    body = ET.SubElement(root, "refbody")
    use_cals = getattr(options, "authoring_pattern", "default") == "cisco_reference" or bool(
        policy and policy.prefer_cals_tables
    )

    for note in draft.notes[:6]:
        ntype = _NOTE_TYPE_MAP.get((note.kind or "note").lower(), "note")
        ne = ET.SubElement(body, "note", {"type": ntype})
        ET.SubElement(ne, "p").text = note.text

    for index, section in enumerate(_ordered_sections(draft, draft.sections), start=1):
        content_items = _section_content_items(section, include_purpose_when_no_details=False)
        if not content_items:
            continue
        sec_attrs: dict[str, str] = {}
        if options.auto_ids:
            sec_attrs["id"] = f"{_slug(section.name, 'section')}-{index}"
        sec = ET.SubElement(body, "section", sec_attrs)
        title = _preferred_section_title(section.name, draft)
        prop_rows = _extract_property_pairs(content_items) if policy and policy.prefer_properties_layout else []
        if policy and policy.prefer_properties_layout and prop_rows and len(prop_rows) >= max(1, min(2, len(content_items))):
            _append_properties(sec, prop_rows, title=title)
            continue
        ET.SubElement(sec, "title").text = title
        kind = (getattr(section, "list_kind", "") or "").strip().lower()
        if kind in ("bullet", "numbered") and len(content_items) >= 2:
            _append_paragraphs(sec, section, max_items=14)
        else:
            for item in content_items:
                item = item.strip()
                if not item:
                    continue
                p_el = ET.SubElement(sec, "p")
                if use_uicontrol and ui_label_hints:
                    for label in sorted(ui_label_hints, key=len, reverse=True):
                        if label and label in item:
                            i = item.index(label)
                            if i > 0:
                                p_el.text = item[:i]
                            uc = ET.SubElement(p_el, "uicontrol")
                            uc.text = label
                            rest = item[i + len(label):]
                            if rest:
                                ph = ET.SubElement(p_el, "ph")
                                ph.text = rest
                            break
                    else:
                        p_el.text = item
                else:
                    p_el.text = item
    for tbl in draft.tables[:4]:
        _emit_tabular(body, tbl.caption, tbl.rows, use_cals=use_cals)
    for code in draft.code_snippets[:4]:
        ex = ET.SubElement(body, "example")
        cb = ET.SubElement(ex, "codeblock")
        cb.text = code


def _serialize_body(
    root: ET.Element,
    body_tag: str,
    draft: TopicDraft,
    use_uicontrol: bool,
    ui_label_hints: set[str],
    options: ChatDitaGenerationOptions,
) -> None:
    body = ET.SubElement(root, body_tag)
    policy = _serializer_policy(draft)
    use_cals = body_tag == "refbody" and (
        getattr(options, "authoring_pattern", "default") == "cisco_reference"
        or bool(policy and policy.prefer_cals_tables)
    )
    for note in draft.notes[:6]:
        ntype = _NOTE_TYPE_MAP.get((note.kind or "note").lower(), "note")
        ne = ET.SubElement(body, "note", {"type": ntype})
        ET.SubElement(ne, "p").text = note.text

    for index, section in enumerate(_ordered_sections(draft, draft.sections), start=1):
        content_items = _section_content_items(section, include_purpose_when_no_details=False)
        if not content_items:
            continue
        sec_attrs: dict[str, str] = {}
        if options.auto_ids:
            sec_attrs["id"] = f"{_slug(section.name, 'section')}-{index}"
        sec = ET.SubElement(body, "section", sec_attrs)
        ET.SubElement(sec, "title").text = _preferred_section_title(section.name, draft)
        kind = (getattr(section, "list_kind", "") or "").strip().lower()
        if kind in ("bullet", "numbered") and len(content_items) >= 2:
            # Delegate to _append_paragraphs which handles list_kind → <ul>/<ol>
            _append_paragraphs(sec, section, max_items=14)
        else:
            for item in content_items:
                item = item.strip()
                if not item:
                    continue
                p_el = ET.SubElement(sec, "p")
                if use_uicontrol and ui_label_hints:
                    for label in sorted(ui_label_hints, key=len, reverse=True):
                        if label and label in item:
                            i = item.index(label)
                            if i > 0:
                                p_el.text = item[:i]
                            uc = ET.SubElement(p_el, "uicontrol")
                            uc.text = label
                            rest = item[i + len(label):]
                            if rest:
                                ph = ET.SubElement(p_el, "ph")
                                ph.text = rest
                            break
                    else:
                        p_el.text = item
                else:
                    p_el.text = item
    for tbl in draft.tables[:4]:
        _emit_tabular(body, tbl.caption, tbl.rows, use_cals=use_cals)
    for code in draft.code_snippets[:4]:
        ex = ET.SubElement(body, "example")
        cb = ET.SubElement(ex, "codeblock")
        cb.text = code
