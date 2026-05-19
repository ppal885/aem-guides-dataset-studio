"""Generate self-contained flat + hierarchical DITA datasets in one ZIP.

Flat layout:
  flat_{N}/topics/topic_XXXXX.dita
  flat_{N}/rootmap_{N}.ditamap (maprefs to guides when flat_submap_count > 1)
  flat_{N}/maps/*.ditamap (optional guide maps)
  flat_{N}/technicalContent/dtd/{topic,map}.dtd

Hierarchical layout:
  hierarchical_{N}/sections/section_XX/topics/topic_XXXXX.dita
  hierarchical_{N}/sections/section_XX/section_XX.ditamap
  hierarchical_{N}/rootmap_{N}.ditamap  (maprefs to section submaps)
  hierarchical_{N}/technicalContent/dtd/{topic,map}.dtd
"""

from __future__ import annotations

import math
import random
import re
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

_CUSTOMER_GUIDE_CHAPTERS = (
    "Getting started",
    "Installation and deployment",
    "Security and compliance",
    "Integration",
    "Day-two operations",
    "Troubleshooting",
    "API reference",
    "Administration",
)


def _product_label(subject: str) -> str:
    """Display name for customer-style copy (non-validated internal string)."""
    return (subject or "").strip() or "Acme Cloud Suite"


def _split_topic_ranges(count: int, n_maps: int) -> list[tuple[int, int]]:
    """Evenly partition 1..count into n_maps contiguous ranges (inclusive)."""
    n_maps = max(1, min(int(n_maps), count))
    base = count // n_maps
    rem = count % n_maps
    ranges: list[tuple[int, int]] = []
    start = 1
    for i in range(n_maps):
        size = base + (1 if i < rem else 0)
        end = start + size - 1
        ranges.append((start, end))
        start = end + 1
    return ranges


# ---------------------------------------------------------------------------
# DTD rewriting (same technique as bulk_dita_map_topics)
# ---------------------------------------------------------------------------

def _rewrite_doctype_system(doctype_line: str, new_system_path: str) -> str:
    """Replace the SYSTEM literal in a PUBLIC doctype declaration."""
    s = doctype_line.strip()
    if not s:
        return ""
    return re.sub(
        r'(PUBLIC\s+"[^"]+"\s+)"[^"]*"',
        lambda m: f'{m.group(1)}"{new_system_path}"',
        s,
        count=1,
        flags=re.IGNORECASE,
    )


# ---------------------------------------------------------------------------
# Subject-aware fallback content
#
# When `content_titles[idx]` / `content_bodies[idx]` are not provided, these
# helpers produce subject-flavored fallbacks (e.g. "Kubernetes — Topic 00001",
# "This topic explores Kubernetes (entry 00001 of 5000).") so the dataset is
# still themed by the user's prompt rather than the generic "Generated Topic
# 00001" placeholder.
# ---------------------------------------------------------------------------

def _xml_safe(value: str) -> str:
    """XML-escape value for safe inclusion in element text/attribute (rule 8: output encoding)."""
    return _xml_escape(value or "", entities={'"': "&quot;", "'": "&apos;"})


def _navtitle_for(
    index: int,
    subject: str,
    content_titles: list[str] | None,
    *,
    customer_style: bool = False,
) -> str:
    if content_titles and 0 <= index - 1 < len(content_titles) and content_titles[index - 1].strip():
        return content_titles[index - 1].strip()
    label = _product_label(subject)
    if customer_style:
        chapter = _CUSTOMER_GUIDE_CHAPTERS[(index - 1) % len(_CUSTOMER_GUIDE_CHAPTERS)]
        return f"{label}: {chapter} ({index:05d})"
    if subject:
        return f"{subject} — Topic {index:05d}"
    return f"Topic {index:05d}"


def _title_for(
    index: int,
    subject: str,
    content_titles: list[str] | None,
    *,
    customer_style: bool = False,
) -> str:
    if content_titles and 0 <= index - 1 < len(content_titles) and content_titles[index - 1].strip():
        return content_titles[index - 1].strip()
    label = _product_label(subject)
    if customer_style:
        chapter = _CUSTOMER_GUIDE_CHAPTERS[(index - 1) % len(_CUSTOMER_GUIDE_CHAPTERS)]
        return f"{label} — {chapter} ({index:05d})"
    if subject:
        return f"{subject} — Topic {index:05d}"
    return f"Generated Topic {index:05d}"


def _body_for(
    index: int,
    subject: str,
    total: int,
    content_bodies: list[str] | None,
    *,
    customer_style: bool = False,
) -> str:
    if content_bodies and 0 <= index - 1 < len(content_bodies) and content_bodies[index - 1].strip():
        return content_bodies[index - 1].strip()
    label = _product_label(subject)
    if customer_style:
        return (
            f"This customer guide article describes {label} capabilities relevant to administrators "
            f"and authors. It is article {index:05d} of {total:05d} in the delivered documentation set. "
            "Verify licensing and regional availability with your account team before production rollout."
        )
    if subject:
        return (
            f"This topic explores {subject} (entry {index:05d} of {total:05d}). "
            f"It captures one slice of the {subject} domain so authors can review structure, "
            "navigation, and per-topic content together."
        )
    return (
        f"This is generated DITA topic number {index:05d}. "
        "It is included in the dataset for large-scale testing."
    )


def _shortdesc_for(
    index: int,
    subject: str,
    *,
    customer_style: bool = False,
    total: int = 0,
) -> str:
    label = _product_label(subject)
    if customer_style:
        return (
            f"Customer-facing help topic for {label} ({index:05d} of {max(total, index)}). "
            "Applies to supported enterprise deployments."
        )
    if subject:
        return f"Subject-aware DITA topic in the {subject} flat/hierarchical dataset."
    return "Auto-generated topic for flat/hierarchical dataset testing."


# ---------------------------------------------------------------------------
# XML builders
# ---------------------------------------------------------------------------

def _xref_link_xml(href: str, *, peer_scope: bool) -> str:
    """Inline xref to another topic; peer_scope uses DITA 1.3 scope='peer' + format='dita'."""
    safe_href = _xml_safe(href)
    if peer_scope:
        return f'<xref href="{safe_href}" format="dita" scope="peer">related topic</xref>'
    return f'<xref href="{safe_href}">related topic</xref>'


def _topic_xml(
    doctype: str,
    index: int,
    xref_href: str | None = None,
    *,
    peer_xref: bool = False,
    subject: str = "",
    total: int = 0,
    customer_style: bool = False,
    content_titles: list[str] | None = None,
    content_bodies: list[str] | None = None,
) -> str:
    topic_id = f"topic_{index:05d}"
    title_text = _xml_safe(_title_for(index, subject, content_titles, customer_style=customer_style))
    body_p = _xml_safe(
        _body_for(index, subject, total or index, content_bodies, customer_style=customer_style)
    )
    shortdesc = _xml_safe(_shortdesc_for(index, subject, customer_style=customer_style, total=total or index))
    xref_line = ""
    if xref_href:
        xref_line = f"\n    <p>See also: {_xref_link_xml(xref_href, peer_scope=peer_xref)}.</p>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<topic id="{topic_id}">
  <title>{title_text}</title>
  <shortdesc>{shortdesc}</shortdesc>
  <body>
    <p>{body_p}</p>{xref_line}
  </body>
</topic>
"""


def _flat_root_map_xml(
    doctype: str,
    count: int,
    *,
    subject: str = "",
    customer_style: bool = False,
    content_titles: list[str] | None = None,
) -> str:
    lines = []
    for i in range(1, count + 1):
        href = f"topics/topic_{i:05d}.dita"
        navtitle = _xml_safe(_navtitle_for(i, subject, content_titles, customer_style=customer_style))
        lines.append(f'  <topicref href="{href}" navtitle="{navtitle}"/>')
    topicrefs_str = "\n".join(lines)
    label = _product_label(subject)
    if customer_style:
        map_title = _xml_safe(f"{label} — Customer documentation master map ({count} topics)")
        map_short = _xml_safe(
            f"Master deliverable map for {label}. References {count} customer guide topics in a flat hierarchy."
        )
    else:
        map_title = _xml_safe(
            f"{subject} flat root map ({count} topics)" if subject else f"Flat Root Map ({count} topics)"
        )
        map_short = _xml_safe(
            f"Root map for the {subject} flat dataset, referencing {count} topics."
            if subject
            else f"Root map referencing {count} topics in a flat structure."
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<map id="flat_rootmap_{count}">
  <title>{map_title}</title>
  <topicmeta>
    <shortdesc>{map_short}</shortdesc>
  </topicmeta>
{topicrefs_str}
</map>
"""


def _flat_guide_map_xml(
    doctype: str,
    guide_index: int,
    topic_start: int,
    topic_end: int,
    *,
    subject: str = "",
    customer_style: bool = False,
    map_basename: str,
    content_titles: list[str] | None = None,
) -> str:
    lines = []
    for i in range(topic_start, topic_end + 1):
        href = f"../topics/topic_{i:05d}.dita"
        navtitle = _xml_safe(_navtitle_for(i, subject, content_titles, customer_style=customer_style))
        lines.append(f'  <topicref href="{href}" navtitle="{navtitle}"/>')
    topicrefs_str = "\n".join(lines)
    label = _product_label(subject)
    safe_base = _xml_safe(map_basename.replace(".ditamap", ""))
    if customer_style:
        sub_title = _xml_safe(f"{label} — Customer guide volume {guide_index:02d}")
        sub_short = _xml_safe(
            f"{label} customer guide volume {guide_index:02d}: topics {topic_start:05d}–{topic_end:05d}."
        )
    else:
        sub_title = _xml_safe(
            f"{subject} — Flat guide {guide_index:02d}" if subject else f"Flat guide {guide_index:02d}"
        )
        sub_short = _xml_safe(
            f"Flat submap {guide_index:02d} ({topic_start:05d}–{topic_end:05d})."
            if subject
            else f"Flat submap {guide_index:02d} covering topics {topic_start:05d}–{topic_end:05d}."
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<map id="{safe_base}">
  <title>{sub_title}</title>
  <topicmeta>
    <shortdesc>{sub_short}</shortdesc>
  </topicmeta>
{topicrefs_str}
</map>
"""


def _flat_root_maprefs_xml(
    doctype: str,
    count: int,
    flat_submap_count: int,
    *,
    subject: str = "",
    customer_style: bool = False,
    map_basenames: list[str],
) -> str:
    lines = []
    for gi, basename in enumerate(map_basenames, start=1):
        href = f"maps/{basename}"
        label = _product_label(subject)
        if customer_style:
            navtitle = _xml_safe(f"{label} — Guide volume {gi:02d}")
        else:
            navtitle = _xml_safe(
                f"{subject} — Flat guide {gi:02d}" if subject else f"Flat guide map {gi:02d}"
            )
        lines.append(f'  <mapref href="{href}" navtitle="{navtitle}"/>')
    maprefs_str = "\n".join(lines)
    label = _product_label(subject)
    if customer_style:
        map_title = _xml_safe(
            f"{label} — Master map ({flat_submap_count} customer guides, {count} topics)"
        )
        map_short = _xml_safe(
            f"Root map for {label}: aggregates {flat_submap_count} customer guide maps ({count} topics)."
        )
    else:
        map_title = _xml_safe(
            f"{subject} flat master map ({flat_submap_count} guides, {count} topics)"
            if subject
            else f"Flat master map ({flat_submap_count} guides, {count} topics)"
        )
        map_short = _xml_safe(
            f"Root map with {flat_submap_count} maprefs to flat guide maps ({count} topics)."
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<map id="flat_rootmap_{count}">
  <title>{map_title}</title>
  <topicmeta>
    <shortdesc>{map_short}</shortdesc>
  </topicmeta>
{maprefs_str}
</map>
"""


def _section_submap_xml(
    doctype: str,
    section_index: int,
    topic_start: int,
    topic_end: int,
    *,
    subject: str = "",
    customer_style: bool = False,
    content_titles: list[str] | None = None,
) -> str:
    sid = f"section_{section_index:02d}"
    lines = []
    for i in range(topic_start, topic_end + 1):
        href = f"topics/topic_{i:05d}.dita"
        navtitle = _xml_safe(_navtitle_for(i, subject, content_titles, customer_style=customer_style))
        lines.append(f'  <topicref href="{href}" navtitle="{navtitle}"/>')
    topicrefs_str = "\n".join(lines)
    label = _product_label(subject)
    if customer_style:
        sub_title = _xml_safe(f"{label} — Deployment volume {section_index:02d}")
        sub_short = _xml_safe(
            f"{label} hierarchical volume {section_index:02d}: topics {topic_start:05d}–{topic_end:05d}."
        )
    else:
        sub_title = _xml_safe(
            f"{subject} — Section {section_index:02d}" if subject else f"Section {section_index:02d}"
        )
        sub_short = _xml_safe(
            f"{subject} section {section_index:02d} (topics {topic_start:05d}–{topic_end:05d})."
            if subject
            else f"Submap for section {section_index:02d} (topics {topic_start:05d}–{topic_end:05d})."
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<map id="{sid}_map">
  <title>{sub_title}</title>
  <topicmeta>
    <shortdesc>{sub_short}</shortdesc>
  </topicmeta>
{topicrefs_str}
</map>
"""


def _hierarchical_root_map_xml(
    doctype: str,
    count: int,
    section_count: int,
    *,
    subject: str = "",
    customer_style: bool = False,
) -> str:
    lines = []
    label = _product_label(subject)
    for s in range(1, section_count + 1):
        sid = f"section_{s:02d}"
        href = f"sections/{sid}/{sid}.ditamap"
        if customer_style:
            navtitle = _xml_safe(f"{label} — Operations volume {s:02d}")
        else:
            navtitle = _xml_safe(
                f"{subject} — Section {s:02d}" if subject else f"Section {s:02d}"
            )
        lines.append(f'  <mapref href="{href}" navtitle="{navtitle}"/>')
    maprefs_str = "\n".join(lines)
    if customer_style:
        map_title = _xml_safe(
            f"{label} — Hierarchical customer map ({count} topics, {section_count} volumes)"
        )
        map_short = _xml_safe(
            f"Hierarchical deliverable for {label}: {section_count} volume maps, {count} topics."
        )
    else:
        map_title = _xml_safe(
            f"{subject} hierarchical root map ({count} topics, {section_count} sections)"
            if subject
            else f"Hierarchical Root Map ({count} topics, {section_count} sections)"
        )
        map_short = _xml_safe(
            f"{subject} hierarchical root map with maprefs to {section_count} section submaps."
            if subject
            else f"Root map with maprefs to {section_count} section submaps."
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<map id="hierarchical_rootmap_{count}">
  <title>{map_title}</title>
  <topicmeta>
    <shortdesc>{map_short}</shortdesc>
  </topicmeta>
{maprefs_str}
</map>
"""


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_flat_hierarchical_dita(
    dataset_config: Any,
    base: str,
    topic_count: int = 5000,
    *,
    topics_per_section: int = 50,
    include_xrefs: bool = False,
    xref_scope: str = "local",
    flat_submap_count: int = 1,
    customer_style: bool = False,
    pretty_print: bool = True,
    rand: random.Random | None = None,
    content_subject: str = "",
    content_titles: list[str] | None = None,
    content_bodies: list[str] | None = None,
) -> dict[str, bytes]:
    """Build flat + hierarchical DITA datasets as self-contained structures with DTD stubs.

    When ``content_subject`` is non-empty, titles and bodies are themed for that
    subject. ``content_titles`` / ``content_bodies`` (lists indexed 0..topic_count-1)
    take precedence per topic; missing entries fall back to subject-templated text.

    When ``flat_submap_count`` > 1, the flat layout uses one root map with ``mapref``
    links to multiple guide maps under ``maps/``, each owning a contiguous slice of topics.

    When ``customer_style`` is true, default titles, short descriptions, bodies, and map
    labels read like enterprise customer documentation (set ``content_subject`` to your
    product name; if empty, a neutral placeholder product label is used).

    When ``include_xrefs`` is true, each topic (except the last in its linking chain)
    includes a cross-topic ``xref``. Set ``xref_scope`` to ``"peer"`` for DITA 1.3
    ``scope="peer"`` and ``format="dita"`` on those xrefs; targets remain sibling
    ``.dita`` files in the bundle so relative ``href`` values resolve.
    """
    from app.generator.dtd_stubs import BULK_MAP_TOPICS_TOPIC_DTD, STANDARD_MAP_DTD

    _ = rand  # reserved for future variation
    base = (base or "dataset").strip("/")
    count = max(1, int(topic_count))
    xs = (xref_scope or "local").strip().lower()
    peer_xref = bool(include_xrefs and xs == "peer")
    tps = max(1, int(topics_per_section))
    section_count = math.ceil(count / tps)
    subject = (content_subject or "").strip()
    titles = list(content_titles or [])
    bodies = list(content_bodies or [])
    n_flat_maps = max(1, min(int(flat_submap_count), count))

    # Resolve doctypes
    raw_topic = (getattr(dataset_config, "doctype_topic", None) or "").strip()
    raw_map = (getattr(dataset_config, "doctype_map", None) or "").strip()

    def _topic_doctype(dtd_rel_path: str) -> str:
        if raw_topic:
            return _rewrite_doctype_system(raw_topic, dtd_rel_path)
        return f'<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "{dtd_rel_path}">'

    def _map_doctype(dtd_rel_path: str) -> str:
        if raw_map:
            return _rewrite_doctype_system(raw_map, dtd_rel_path)
        return f'<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "{dtd_rel_path}">'

    files: dict[str, bytes] = {}

    def _encode(xml: str) -> bytes:
        if not pretty_print:
            xml = "".join(line.strip() for line in xml.splitlines() if line.strip())
        return xml.encode("utf-8")

    # ── Flat structure ────────────────────────────────────────────────────
    flat = f"{base}/flat_{count}"
    flat_topic_dt = _topic_doctype("../technicalContent/dtd/topic.dtd")
    flat_map_dt_root = _map_doctype("technicalContent/dtd/map.dtd")
    flat_map_dt_nested = _map_doctype("../technicalContent/dtd/map.dtd")

    for i in range(1, count + 1):
        xref = None
        if include_xrefs and i < count:
            xref = f"topic_{i + 1:05d}.dita"
        path = f"{flat}/topics/topic_{i:05d}.dita"
        files[path] = _encode(
            _topic_xml(
                flat_topic_dt,
                i,
                xref,
                peer_xref=peer_xref,
                subject=subject,
                total=count,
                customer_style=customer_style,
                content_titles=titles,
                content_bodies=bodies,
            )
        )

    if n_flat_maps <= 1:
        files[f"{flat}/rootmap_{count}.ditamap"] = _encode(
            _flat_root_map_xml(
                flat_map_dt_root,
                count,
                subject=subject,
                customer_style=customer_style,
                content_titles=titles,
            )
        )
    else:
        ranges = _split_topic_ranges(count, n_flat_maps)
        guide_prefix = "customer_guide" if customer_style else "flat_guide"
        basenames: list[str] = []
        for gi, (ts, te) in enumerate(ranges, start=1):
            fn = f"{guide_prefix}_{gi:02d}.ditamap"
            basenames.append(fn)
            files[f"{flat}/maps/{fn}"] = _encode(
                _flat_guide_map_xml(
                    flat_map_dt_nested,
                    gi,
                    ts,
                    te,
                    subject=subject,
                    customer_style=customer_style,
                    map_basename=fn,
                    content_titles=titles,
                )
            )
        files[f"{flat}/rootmap_{count}.ditamap"] = _encode(
            _flat_root_maprefs_xml(
                flat_map_dt_root,
                count,
                n_flat_maps,
                subject=subject,
                customer_style=customer_style,
                map_basenames=basenames,
            )
        )

    # DTD stubs for flat
    files[f"{flat}/technicalContent/dtd/topic.dtd"] = BULK_MAP_TOPICS_TOPIC_DTD.encode("utf-8")
    files[f"{flat}/technicalContent/dtd/map.dtd"] = STANDARD_MAP_DTD.encode("utf-8")

    # ── Hierarchical structure ────────────────────────────────────────────
    hier = f"{base}/hierarchical_{count}"
    # Topics are 3 levels deep: sections/section_XX/topics/  →  ../../../technicalContent/dtd/topic.dtd
    hier_topic_dt = _topic_doctype("../../../technicalContent/dtd/topic.dtd")
    # Submaps are 2 levels deep: sections/section_XX/  →  ../../technicalContent/dtd/map.dtd
    hier_submap_dt = _map_doctype("../../technicalContent/dtd/map.dtd")
    # Root map is at top:  →  technicalContent/dtd/map.dtd
    hier_rootmap_dt = _map_doctype("technicalContent/dtd/map.dtd")

    topic_idx = 0
    for s in range(1, section_count + 1):
        sid = f"section_{s:02d}"
        sec_start = topic_idx + 1
        sec_end = min(topic_idx + tps, count)

        for i in range(sec_start, sec_end + 1):
            xref = None
            if include_xrefs and i < sec_end:
                xref = f"topic_{i + 1:05d}.dita"
            path = f"{hier}/sections/{sid}/topics/topic_{i:05d}.dita"
            files[path] = _encode(
                _topic_xml(
                    hier_topic_dt,
                    i,
                    xref,
                    peer_xref=peer_xref,
                    subject=subject,
                    total=count,
                    customer_style=customer_style,
                    content_titles=titles,
                    content_bodies=bodies,
                )
            )

        submap_path = f"{hier}/sections/{sid}/{sid}.ditamap"
        files[submap_path] = _encode(
            _section_submap_xml(
                hier_submap_dt,
                s,
                sec_start,
                sec_end,
                subject=subject,
                customer_style=customer_style,
                content_titles=titles,
            )
        )
        topic_idx = sec_end

    files[f"{hier}/rootmap_{count}.ditamap"] = _encode(
        _hierarchical_root_map_xml(
            hier_rootmap_dt,
            count,
            section_count,
            subject=subject,
            customer_style=customer_style,
        )
    )

    # DTD stubs for hierarchical
    files[f"{hier}/technicalContent/dtd/topic.dtd"] = BULK_MAP_TOPICS_TOPIC_DTD.encode("utf-8")
    files[f"{hier}/technicalContent/dtd/map.dtd"] = STANDARD_MAP_DTD.encode("utf-8")

    # ── README ────────────────────────────────────────────────────────────
    readme_lines = [
        "DITA Flat + Hierarchical Dataset (AEM Guides Studio recipe: flat_hierarchical_dita)",
        "",
        f"Topic count per structure: {count}",
        "",
        "== Flat Structure ==",
        f"  Root map:  flat_{count}/rootmap_{count}.ditamap",
        (
            f"  Guide maps: flat_{count}/maps/  ({n_flat_maps} ditamap files)"
            if n_flat_maps > 1
            else "  Guide maps:  (single master map lists topicrefs directly)"
        ),
        f"  Topics:    flat_{count}/topics/  ({count} files)",
        f"  DTD stubs: flat_{count}/technicalContent/dtd/",
        "",
        "== Hierarchical Structure ==",
        f"  Root map:  hierarchical_{count}/rootmap_{count}.ditamap  ({section_count} maprefs)",
        f"  Sections:  hierarchical_{count}/sections/  ({section_count} sections, {tps} topics each)",
        f"  DTD stubs: hierarchical_{count}/technicalContent/dtd/",
        "",
        "All topicref, mapref, and xref links are relative and resolve within this package.",
        "DTD SYSTEM paths are relative to each file's location.",
    ]
    if customer_style:
        readme_lines.extend(
            [
                "",
                "customer_style=true: topic and map titles use enterprise customer-guide phrasing.",
                "Set content_subject to your product or offering name (optional but recommended).",
            ]
        )
    if peer_xref:
        readme_lines.extend(
            [
                "",
                "Cross-topic body links use DITA 1.3 xref with scope=\"peer\" and format=\"dita\" ",
                "(targets are included in this bundle so href + fragment IDs resolve for validation).",
            ]
        )
    files[f"{base}/README.txt"] = "\n".join(readme_lines).encode("utf-8")

    return files
