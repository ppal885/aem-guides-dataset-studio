"""
Best-effort structural validation for generated DITA topics (not a DTD validator).

UI-oriented examples (also asserted in tests):

- Invalid XML: "Not well-formed XML: ..."
- Root mismatch: "Root element is <task> but expected <concept>."
- Missing shortdesc (warning): "Missing <shortdesc> under root — recommended for DITA topics."
- Suspicious attribute (warning): "Suspicious attribute on <step>: onclick=..."
- Unresolved conref (error): "Unresolved conref target \"#missing-id\" (no matching @id in document)."
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from app.services.dita_xml_headers import strip_xml_prolog


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower() if tag else ""


def collect_duplicate_ids(root: ET.Element) -> list[str]:
    seen: dict[str, int] = {}
    for elem in root.iter():
        eid = elem.get("id")
        if eid:
            seen[eid] = seen.get(eid, 0) + 1
    return [i for i, c in seen.items() if c > 1]


def _collect_all_ids(root: ET.Element) -> set[str]:
    return {str(e.get("id")) for e in root.iter() if e.get("id")}


_TASKBODY_ALLOWED = frozenset(
    {
        "prereq",
        "context",
        "steps",
        "steps-unordered",
        "steps-informal",
        "result",
        "postreq",
        "example",
        "tasktroubleshooting",
        "tutorialinfo",
        "consequence",
        "condition",
        "tasksummary",
    }
)
_TASKBODY_FORBIDDEN_DIRECT_CHILDREN = frozenset(
    {
        "section",
        "simpletable",
        "table",
        "p",
        "ul",
        "ol",
        "dl",
        "fig",
        "note",
        "codeblock",
    }
)

_CONBODY_ALLOWED = frozenset(
    {
        "p",
        "note",
        "ul",
        "ol",
        "sl",
        "dl",
        "pre",
        "codeblock",
        "lq",
        "section",
        "example",
        "fig",
        "simpletable",
        "table",
        "data",
    }
)

_REFBODY_ALLOWED = frozenset(
    {
        "section",
        "example",
        "refsyn",
        "properties",
        "table",
        "simpletable",
        "note",
        "p",
        "dl",
        "data",
    }
)


def _parse_href_fragment(href: str) -> tuple[str | None, list[str]]:
    """
    Return (file_part, id_parts). file_part is None for same-document references.
    id_parts are fragment segments after # (may be "topic/element").
    """
    h = (href or "").strip()
    if not h:
        return None, []
    if h.startswith("#"):
        frag = h[1:].strip()
        if not frag:
            return None, []
        return None, [p for p in frag.split("/") if p]
    if "#" in h:
        file_part, frag = h.split("#", 1)
        file_part = file_part.strip() or None
        parts = [p for p in frag.strip().split("/") if p]
        return file_part, parts
    return h, []


def _fragments_resolve(ids: set[str], parts: list[str]) -> bool:
    if not parts:
        return True
    if len(parts) == 1:
        return parts[0] in ids
    return all(p in ids for p in parts)


def _scan_suspicious_attributes(root: ET.Element) -> list[str]:
    warnings: list[str] = []
    for elem in root.iter():
        tag = _local(elem.tag)
        for k, v in elem.attrib.items():
            lk = k.rsplit("}", 1)[-1].split(":")[-1].lower()
            vs = str(v)
            if re.match(r"^on[a-z]+$", lk):
                warnings.append(f"Suspicious attribute on <{tag}>: @{lk}")
            if lk == "style" and "javascript:" in vs.lower():
                warnings.append(f"Suspicious javascript: URL in @style on <{tag}>.")
            if lk.startswith("data-") and len(lk) > 64:
                warnings.append(f"Unusually long data-* attribute on <{tag}> (possible noise).")
    return warnings


def validate_dita_topic_structure_categorized(
    xml: str, *, expected_root: str
) -> tuple[list[str], list[str]]:
    """
    Return (structural_errors, structural_warnings).

    Errors block ``ChatDitaValidationResult.valid``; warnings are merged into
    ``validator_warnings`` by the chat authoring service.
    """
    errors: list[str] = []
    warnings: list[str] = []
    body = strip_xml_prolog(xml or "")
    if not body.strip():
        return (["Document body is empty."], [])

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        return ([f"Not well-formed XML: {exc}"], [])

    root_name = _local(root.tag)
    exp = (expected_root or "").strip().lower()
    if exp and root_name != exp:
        errors.append(f"Root element is <{root_name}> but expected <{exp}>.")

    title_found = any(_local(c.tag) == "title" for c in root)
    if not title_found:
        errors.append("Missing required <title> child of root.")

    shortdesc_found = any(_local(c.tag) == "shortdesc" for c in root)
    if not shortdesc_found:
        warnings.append("Missing <shortdesc> under root — recommended for DITA topics.")

    dup = collect_duplicate_ids(root)
    if dup:
        errors.append(
            f"Duplicate @id values: {', '.join(dup[:8])}{'...' if len(dup) > 8 else ''}"
        )

    all_ids = _collect_all_ids(root)

    for elem in root.iter():
        tag = _local(elem.tag)
        if tag == "xref":
            href = elem.get("href")
            if href is not None and not str(href).strip():
                errors.append("Empty xref @href detected.")
            elif href and str(href).strip():
                file_part, parts = _parse_href_fragment(str(href))
                if file_part is None and parts and not _fragments_resolve(all_ids, parts):
                    errors.append(f'Unresolved xref target "{href}" (no matching @id in document).')
        cr = elem.get("conref")
        if cr is not None:
            if not str(cr).strip():
                errors.append(f"Empty conref on <{tag}> detected.")
            else:
                file_part, parts = _parse_href_fragment(str(cr))
                if file_part is None and parts and not _fragments_resolve(all_ids, parts):
                    errors.append(f'Unresolved conref target "{cr}" (no matching @id in document).')
        kref = elem.get("keyref")
        if kref is not None and not str(kref).strip():
            warnings.append(f"Empty keyref on <{tag}>.")

    # Walk with parent for nesting / placement
    def walk(el: ET.Element, parent: ET.Element | None) -> None:
        plocal = _local(parent.tag) if parent is not None else ""
        local = _local(el.tag)

        if plocal == "p" and local == "p":
            errors.append("Illegal nesting: <p> contains <p>.")

        if local == "steps" and plocal != "taskbody":
            errors.append("<steps> must appear as a direct child of <taskbody>.")

        if local == "cmd" and plocal != "step":
            warnings.append("<cmd> is expected inside <step> for task topics.")

        for child in el:
            walk(child, el)

    walk(root, None)

    if root_name == "task":
        has_taskbody = any(_local(c.tag) == "taskbody" for c in root)
        if not has_taskbody:
            errors.append("Task topic should contain <taskbody>.")
        else:
            tb = next(c for c in root if _local(c.tag) == "taskbody")
            has_steps = any(_local(c.tag) == "steps" for c in tb)
            if not has_steps:
                errors.append("Task <taskbody> should contain <steps> for procedural content.")
            for child in tb:
                ln = _local(child.tag)
                if ln in _TASKBODY_FORBIDDEN_DIRECT_CHILDREN:
                    errors.append(
                        f"<{ln}> is not a valid direct child of <taskbody> "
                        "(per DITA 1.3 task DTD). Wrap it in <example>, <context>, "
                        "<prereq>, <result>, or <postreq>."
                    )
                elif ln not in _TASKBODY_ALLOWED:
                    warnings.append(
                        f"Unusual <taskbody> child <{ln}> — verify against your DITA template."
                    )
            for step in tb.iter():
                if _local(step.tag) != "step":
                    continue
                if not any(_local(c.tag) == "cmd" for c in step):
                    errors.append(
                        "Task <step> is missing <cmd> — required for procedural steps."
                    )
    if root_name == "concept":
        if not any(_local(c.tag) == "conbody" for c in root):
            errors.append("Concept topic should contain <conbody>.")
        else:
            cb = next(c for c in root if _local(c.tag) == "conbody")
            if len(cb) == 0:
                warnings.append("<conbody> appears empty — add narrative content.")
            for child in cb:
                ln = _local(child.tag)
                if ln not in _CONBODY_ALLOWED:
                    warnings.append(
                        f"Unusual <conbody> child <{ln}> — verify against your DITA template."
                    )

    if root_name == "reference":
        if not any(_local(c.tag) == "refbody" for c in root):
            errors.append("Reference topic should contain <refbody>.")
        else:
            rb = next(c for c in root if _local(c.tag) == "refbody")
            if len(rb) == 0:
                warnings.append("<refbody> appears empty — add reference content.")
            for child in rb:
                ln = _local(child.tag)
                if ln not in _REFBODY_ALLOWED:
                    warnings.append(
                        f"Unusual <refbody> child <{ln}> — verify against your DITA template."
                    )

    warnings.extend(_scan_suspicious_attributes(root))

    # De-duplicate warnings while preserving order
    seen_w: set[str] = set()
    dedup_w: list[str] = []
    for w in warnings:
        if w not in seen_w:
            seen_w.add(w)
            dedup_w.append(w)

    return errors, dedup_w


def validate_dita_topic_structure(xml: str, *, expected_root: str) -> list[str]:
    """Return structural **errors** only (backward compatible for strict checks)."""
    errors, _ = validate_dita_topic_structure_categorized(xml, expected_root=expected_root)
    return errors
