from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter

from app.core.schemas_chat_authoring import ChatReferenceDitaSummary, ReferenceStyleProfile
from app.services.dita_xml_headers import extract_declared_doctype_line, strip_xml_prolog

# Attributes safe to copy as "style patterns" (no identifiers or link targets).
_SAFE_ROOT_ATTRS = frozenset(
    {
        "xml:lang",
        "lang",
        "outputclass",
        "audience",
        "platform",
        "product",
        "otherprops",
        "props",
        "importance",
        "rev",
        "status",
        "translate",
    }
)

_INLINE_TAGS = frozenset(
    {
        "uicontrol",
        "wintitle",
        "menucascade",
        "shortcut",
        "codeph",
        "filepath",
        "cmdname",
        "varname",
        "apiname",
        "parmname",
        "option",
        "systemoutput",
        "userinput",
        "term",
        "cite",
        "q",
        "xref",
        "ph",
        "note",
        "draft-comment",
        "required-cleanup",
    }
)

_BLOCKED_ATTRS = frozenset(
    {
        "id",
        "href",
        "conref",
        "conrefend",
        "conaction",
        "keyref",
        "keys",
        "copy-to",
        "format",
        "scope",
        "navtitle",
        "locktitle",
    }
)


def _safe_local_name(tag: str) -> str:
    if not tag:
        return ""
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower()


def _sanitize_root_attributes(attribs: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in attribs.items():
        key = str(k)
        lk = key.lower()
        if lk in _BLOCKED_ATTRS or lk.startswith("xmlns"):
            continue
        # ElementTree uses Clark notation for xml:lang
        if key == "{http://www.w3.org/XML/1998/namespace}lang":
            key = "xml:lang"
            lk = "xml:lang"
        if key in _SAFE_ROOT_ATTRS or lk in _SAFE_ROOT_ATTRS:
            val = str(v).strip()[:200]
            if val:
                out[key] = val
    return out


def _collect_child_order(root: ET.Element) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()
    for child in root:
        local = _safe_local_name(child.tag)
        if local and local not in seen:
            seen.add(local)
            order.append(local)
    return order


def _count_inline_usage(root: ET.Element) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for elem in root.iter():
        local = _safe_local_name(elem.tag)
        if local in _INLINE_TAGS:
            counts[local] += 1
    return dict(counts)


def _structural_habits(root: ET.Element, root_type: str) -> list[str]:
    habits: list[str] = []
    tags = {_safe_local_name(e.tag) for e in root.iter()}
    if root_type == "task":
        if "taskbody" in tags:
            habits.append("uses_taskbody")
        if "context" in tags:
            habits.append("uses_context")
        if "prereq" in tags:
            habits.append("uses_prereq")
        if "steps" in tags:
            habits.append("uses_steps")
        if "substeps" in tags:
            habits.append("uses_substeps")
        if "result" in tags:
            habits.append("uses_result")
        if "postreq" in tags:
            habits.append("uses_postreq")
        if "example" in tags:
            habits.append("uses_example")
    if root_type == "concept":
        if "conbody" in tags:
            habits.append("uses_conbody")
    if root_type == "reference":
        if "refbody" in tags:
            habits.append("uses_refbody")
        if "properties" in tags:
            habits.append("uses_properties")
        if "table" in tags:
            habits.append("uses_table")
        if "tgroup" in tags:
            habits.append("uses_tgroup")
        if "dl" in tags:
            habits.append("uses_dl")
    if "section" in tags:
        habits.append("uses_section")
    if "note" in tags:
        habits.append("uses_note")
    return habits


def _task_step_level_habits(root: ET.Element, root_type: str) -> list[str]:
    """Detect info/substeps directly under step (common in enterprise task topics)."""
    if root_type != "task":
        return []
    found: list[str] = []
    for step in root.iter():
        if _safe_local_name(step.tag) != "step":
            continue
        for child in list(step):
            loc = _safe_local_name(child.tag)
            if loc == "info":
                found.append("uses_step_info")
            elif loc == "substeps":
                found.append("uses_substeps_in_step")
    return list(dict.fromkeys(found))


def _avg_text_len(root: ET.Element) -> float:
    lengths: list[int] = []
    for elem in root.iter():
        text = "".join(elem.itertext()).strip()
        if text:
            lengths.append(len(text))
    if not lengths:
        return 0.0
    return sum(lengths) / len(lengths)


def _prolog_info(root: ET.Element) -> tuple[bool, list[str]]:
    for child in root:
        if _safe_local_name(child.tag) == "prolog":
            tags = [_safe_local_name(c.tag) for c in child]
            return True, tags[:20]
    return False, []


_XREF_BASENAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.(?:dita|xml)$")


def _safe_xref_basename(href: str | None) -> str | None:
    if not href or not str(href).strip():
        return None
    h = str(href).strip().split("#", 1)[0].strip()
    if not h or "://" in h or h.startswith("//"):
        return None
    base = h.replace("\\", "/").split("/")[-1].strip()
    if not base or ".." in base or "/" in base:
        return None
    return base if _XREF_BASENAME_RE.match(base) else None


def _collect_xref_basenames(root: ET.Element, *, limit: int = 36) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for el in root.iter():
        if _safe_local_name(el.tag) != "xref":
            continue
        b = _safe_xref_basename(el.attrib.get("href"))
        if b and b not in seen:
            seen.add(b)
            out.append(b)
        if len(out) >= limit:
            break
    return out


def _taskbody_top_level_sequence(root: ET.Element, root_type: str) -> list[str]:
    if root_type != "task":
        return []
    for child in root:
        if _safe_local_name(child.tag) != "taskbody":
            continue
        return [_safe_local_name(c.tag) for c in child if _safe_local_name(c.tag)]
    return []


def _reference_uses_ui_type(root: ET.Element) -> bool:
    for el in root.iter():
        for k in el.attrib or {}:
            if k == "ui-type" or k.lower().endswith("}ui-type"):
                return True
    return False


def _body_section_titles(root: ET.Element, root_type: str) -> list[str]:
    body_tags = {"body", "conbody", "refbody"}
    if root_type == "task":
        body_tags = {"taskbody"}
    titles: list[str] = []
    seen: set[str] = set()
    for child in root:
        if _safe_local_name(child.tag) not in body_tags:
            continue
        for sec in child:
            local = _safe_local_name(sec.tag)
            if local not in {"section", "example"}:
                continue
            title = ""
            for sub in sec:
                if _safe_local_name(sub.tag) == "title":
                    title = " ".join("".join(sub.itertext()).split()).strip()
                    break
            if title:
                norm = title.lower()
                if norm not in seen:
                    seen.add(norm)
                    titles.append(title[:200])
        break
    return titles[:20]


def _structural_outline_hints(
    root: ET.Element,
    root_type: str,
    habits: list[str],
    taskbody_seq: list[str],
) -> list[str]:
    hints: list[str] = []
    tags = {_safe_local_name(e.tag) for e in root.iter()}
    if taskbody_seq:
        hints.append("Reference taskbody order: " + " → ".join(taskbody_seq))
    if _reference_uses_ui_type(root):
        hints.append(
            "Reference uses ui-type (e.g. gui vs cli): plan separate step lines or context lines prefixed "
            "with 'GUI: ' and 'CLI: ' when both modes apply."
        )
    if "synph" in tags:
        hints.append("Reference embeds CLI syntax with synph/kwd/var inside info — mirror with short literal fragments from the screenshot only.")
    if "substep" in tags or "uses_substeps_in_step" in habits:
        hints.append("Reference nests substeps for multi-command sequences; use step detail lines 'Substep: ...' or multiple ' || ' info lines.")
    if "stepxmp" in tags:
        hints.append("Reference uses stepxmp/codeblock for sample output; put sample blocks in source_notes or a dedicated 'example' section as plain text for the serializer.")
    if "ul" in tags and "prereq" in tags:
        hints.append("Reference prereq uses lists: use multiple prereq detail bullets (one per line) for structured assumptions.")
    if "postreq" in tags:
        hints.append("Reference includes postreq for next-topic pointers; add a 'postreq' section with short next-step text (no href unless allowlist permits).")
    return hints[:16]


def analyze_reference_dita(raw_text: str) -> tuple[ReferenceStyleProfile, list[str]]:
    """
    Parse reference DITA and return a sanitized style profile plus parse warnings.

    Does not copy element ``id`` values or ``conref``/``keyref`` targets. Collects **xref href
    basenames** only (no path segments, no ``#`` fragments) for optional reuse in generation.
    """
    warnings: list[str] = []
    doctype = extract_declared_doctype_line(raw_text or "")
    body = strip_xml_prolog(raw_text or "")
    if not body.strip():
        return (
            ReferenceStyleProfile(
                declared_doctype_line=doctype,
                parse_warnings=["Empty reference document."],
            ),
            ["Empty reference document."],
        )
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        return (
            ReferenceStyleProfile(
                declared_doctype_line=doctype,
                parse_warnings=[f"XML parse error: {exc}"],
            ),
            [f"XML parse error: {exc}"],
        )

    root_type = _safe_local_name(root.tag) or "topic"
    attrs = _sanitize_root_attributes(dict(root.attrib))
    child_order = _collect_child_order(root)
    inline_usage = _count_inline_usage(root)
    habits = _structural_habits(root, root_type)
    habits.extend(h for h in _task_step_level_habits(root, root_type) if h not in habits)
    avg_len = _avg_text_len(root)
    if avg_len < 80:
        tone = "terse"
    elif avg_len > 220:
        tone = "verbose"
    else:
        tone = "neutral"

    uses_prolog, prolog_children = _prolog_info(root)
    tb_seq = _taskbody_top_level_sequence(root, root_type)
    body_section_titles = _body_section_titles(root, root_type)
    xref_names = _collect_xref_basenames(root)
    outline_hints = _structural_outline_hints(root, root_type, habits, tb_seq)
    uses_ui_type = _reference_uses_ui_type(root)

    profile = ReferenceStyleProfile(
        declared_doctype_line=doctype,
        root_local_name=root_type,
        root_attributes_sample=attrs,
        child_order_top_level=child_order,
        inline_element_usage=inline_usage,
        structural_habits=habits,
        tone_hint=tone,
        uses_prolog=uses_prolog,
        prolog_child_tags=prolog_children,
        parse_warnings=warnings,
        reference_xref_basenames=xref_names,
        taskbody_top_level_sequence=tb_seq,
        body_section_titles=body_section_titles,
        structural_outline_hints=outline_hints,
        reference_uses_ui_type_attributes=uses_ui_type,
    )
    return profile, warnings


def reference_title_and_shortdesc(root: ET.Element) -> tuple[str, str]:
    title = ""
    shortdesc = ""
    for child in root:
        local = _safe_local_name(child.tag)
        if local == "title" and not title:
            title = " ".join("".join(child.itertext()).split())
        elif local == "shortdesc" and not shortdesc:
            shortdesc = " ".join("".join(child.itertext()).split())
    return title, shortdesc


def build_reference_summary(
    *,
    filename: str,
    raw_text: str,
    profile: ReferenceStyleProfile,
) -> ChatReferenceDitaSummary:
    """Human-facing summary plus embedded style profile."""
    pw = " ".join(profile.parse_warnings).lower()
    if profile.parse_warnings and ("parse error" in pw or "empty reference" in pw):
        return ChatReferenceDitaSummary(
            style_notes=["The attached reference DITA could not be parsed; fall back to conservative DITA 1.3 structure."],
            structure_summary=f"Reference attachment {filename} is not valid XML or empty.",
            style_profile=profile,
        )

    body = strip_xml_prolog(raw_text)
    root: ET.Element | None = None
    if body.strip():
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return ChatReferenceDitaSummary(
                style_notes=["The attached reference DITA could not be parsed; fall back to conservative DITA 1.3 structure."],
                structure_summary=f"Reference attachment {filename} is not valid XML.",
                style_profile=profile,
            )
    section_tags: list[str] = []
    title = ""
    shortdesc = ""
    if root is not None:
        title, shortdesc = reference_title_and_shortdesc(root)
        for elem in root.iter():
            local = _safe_local_name(elem.tag)
            if local in {"section", "p", "steps", "step", "cmd", "note", "example", "taskbody", "conbody", "refbody"}:
                section_tags.append(local)

    style_notes: list[str] = []
    rt = profile.root_local_name or "topic"
    if rt == "task":
        style_notes.append("Follow task/topic patterns: taskbody, steps with cmd, context/result where appropriate.")
    elif rt == "concept":
        style_notes.append("Follow concept patterns: conbody and explanatory sections.")
    elif rt == "reference":
        style_notes.append("Follow reference patterns: refbody and structured property-style sections.")
    for habit in profile.structural_habits[:6]:
        style_notes.append(f"Reference habit: {habit.replace('_', ' ')}.")
    if profile.inline_element_usage.get("uicontrol"):
        style_notes.append("Reference uses uicontrol for UI labels; mirror when describing UI from the screenshot.")
    if profile.inline_element_usage.get("menucascade"):
        style_notes.append("Reference uses menucascade; use for menu paths when visible in the screenshot.")
    for hint in profile.structural_outline_hints[:5]:
        if hint not in style_notes:
            style_notes.append(hint)
    if profile.reference_xref_basenames:
        style_notes.append(
            f"Reference contains {len(profile.reference_xref_basenames)} distinct xref target basename(s); "
            "turn on 'Allow xref href placeholders' to let the model reuse only those filenames."
        )

    structure_summary = f"Reference file {filename} uses <{rt}>" + (f" with title '{title}'." if title else ".")

    return ChatReferenceDitaSummary(
        root_type=rt,
        title=title,
        shortdesc=shortdesc,
        section_tags=section_tags[:20],
        style_notes=style_notes[:14],
        structure_summary=structure_summary,
        style_profile=profile,
    )
