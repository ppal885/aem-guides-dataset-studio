"""
Best-effort parse of a DITA topic XML string into :class:`ChatSemanticPlan` + :class:`TopicDraft`.

Used by the repair pipeline to re-serialize through :func:`serialize_structured_topic_draft` so we can
change topic type or reference style without LLM regeneration, while preserving extracted text content.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.core.schemas_chat_authoring import ChatSemanticPlan, ChatSemanticPlanSection
from app.services.dita_topic_draft import DraftNote, DraftTable, TopicDraft
from app.services.dita_xml_headers import strip_xml_prolog


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower() if tag else ""


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def _find_child(parent: ET.Element, local: str) -> ET.Element | None:
    for c in parent:
        if _ln(c.tag) == local:
            return c
    return None


def _collect_p_texts(container: ET.Element | None) -> list[str]:
    if container is None:
        return []
    out: list[str] = []
    for child in container:
        if _ln(child.tag) == "p":
            t = _text(child).strip()
            if t:
                out.append(t)
    return out


def parse_dita_xml_to_plan_and_draft(xml: str) -> tuple[ChatSemanticPlan | None, TopicDraft | None, list[str]]:
    """
    Parse topic/task/concept/reference root into plan + draft.

    Returns (None, None, reasons) if the document is not well-formed or root is unsupported.
    """
    warnings: list[str] = []
    body = strip_xml_prolog(xml or "")
    if not body.strip():
        return None, None, ["empty_xml"]
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        return None, None, [f"parse_error:{exc}"]

    root_name = _ln(root.tag)
    if root_name not in {"topic", "task", "concept", "reference"}:
        return None, None, [f"unsupported_root:{root_name}"]

    title_el = _find_child(root, "title")
    title = _text(title_el).strip() or "Topic"
    sd_el = _find_child(root, "shortdesc")
    shortdesc = _text(sd_el).strip() or ""

    dita_type = root_name  # type: ignore[assignment]
    sections: list[ChatSemanticPlanSection] = []
    notes: list[DraftNote] = []
    tables: list[DraftTable] = []
    code_snippets: list[str] = []

    if root_name == "task":
        tb = _find_child(root, "taskbody")
        if tb is not None:
            ctx = _find_child(tb, "context")
            ctx_texts = _collect_p_texts(ctx)
            if ctx_texts:
                sections.append(
                    ChatSemanticPlanSection(
                        name="context",
                        purpose="Context from the original topic.",
                        details=ctx_texts,
                    )
                )
            steps_el = None
            for child in tb:
                if _ln(child.tag) == "steps":
                    steps_el = child
                    break
            step_cmds: list[str] = []
            if steps_el is not None:
                for step in steps_el:
                    if _ln(step.tag) != "step":
                        continue
                    cmd = _find_child(step, "cmd")
                    t = _text(cmd).strip()
                    if t:
                        step_cmds.append(t)
            if step_cmds:
                sections.append(
                    ChatSemanticPlanSection(
                        name="steps",
                        purpose="Procedure steps recovered from XML.",
                        details=step_cmds,
                    )
                )
            res = _find_child(tb, "result")
            res_texts = _collect_p_texts(res)
            if res_texts:
                sections.append(
                    ChatSemanticPlanSection(
                        name="result",
                        purpose="Expected outcome.",
                        details=res_texts,
                    )
                )
            for child in tb:
                ln = _ln(child.tag)
                if ln in {"context", "steps", "result"}:
                    continue
                if ln == "section":
                    st = _find_child(child, "title")
                    sn = _text(st).strip() or "section"
                    paras = []
                    for sub in child:
                        if _ln(sub.tag) == "p":
                            pt = _text(sub).strip()
                            if pt:
                                paras.append(pt)
                    if paras:
                        sections.append(ChatSemanticPlanSection(name=sn[:120], purpose="", details=paras))
                elif ln == "note":
                    ntype = (child.get("type") or "note").strip()
                    nt = _text(child).strip()
                    if nt:
                        notes.append(DraftNote(kind=ntype, text=nt))
        if not sections:
            warnings.append("task_parse_thin_body")

    elif root_name in {"concept", "reference", "topic"}:
        body_tag = {"concept": "conbody", "reference": "refbody", "topic": "body"}[root_name]
        bel = _find_child(root, body_tag)
        if bel is None:
            warnings.append(f"missing_{body_tag}")
        else:
            for child in bel:
                ln = _ln(child.tag)
                if ln == "section":
                    st = _find_child(child, "title")
                    sn = _text(st).strip() or "section"
                    paras = []
                    for sub in child:
                        if _ln(sub.tag) == "p":
                            pt = _text(sub).strip()
                            if pt:
                                paras.append(pt)
                    if paras:
                        sections.append(ChatSemanticPlanSection(name=sn[:120], purpose="", details=paras))
                elif ln == "p":
                    pt = _text(child).strip()
                    if pt:
                        sections.append(ChatSemanticPlanSection(name="body", purpose="", details=[pt]))
                elif ln == "note":
                    ntype = (child.get("type") or "note").strip()
                    nt = _text(child).strip()
                    if nt:
                        notes.append(DraftNote(kind=ntype, text=nt))
                elif ln == "example":
                    cb = _find_child(child, "codeblock")
                    ct = _text(cb).strip()
                    if ct:
                        code_snippets.append(ct)

    if not shortdesc and sections:
        shortdesc = (sections[0].details[0] if sections[0].details else sections[0].purpose)[:500] or shortdesc

    plan = ChatSemanticPlan(
        title=title[:500],
        dita_type=dita_type,
        shortdesc=shortdesc[:2000] or "Recovered from edited topic.",
        audience="",
        purpose="Workspace repair",
        sections=sections,
        style_notes=[],
        source_notes=["parsed_from_xml"],
    )
    draft = TopicDraft(
        dita_type=dita_type,
        title=plan.title,
        shortdesc=plan.shortdesc,
        sections=list(plan.sections),
        notes=notes,
        tables=tables,
        code_snippets=code_snippets,
    )
    return plan, draft, warnings


def synthetic_plan_for_xml(xml: str, dita_type: str, *, title_fallback: str = "Topic") -> ChatSemanticPlan:
    """Minimal plan when parse fails; keeps validation and review hooks working."""
    body = strip_xml_prolog(xml or "")
    title = title_fallback
    if "<title" in body.lower():
        try:
            root = ET.fromstring(body)
            te = _find_child(root, "title")
            if te is not None:
                title = _text(te).strip() or title
        except ET.ParseError:
            pass
    dt = dita_type if dita_type in {"topic", "task", "concept", "reference"} else "topic"
    return ChatSemanticPlan(
        title=title[:500],
        dita_type=dt,  # type: ignore[arg-type]
        shortdesc="",
        audience="",
        purpose="Workspace repair (fallback plan)",
        sections=[],
        style_notes=[],
        source_notes=[],
    )
