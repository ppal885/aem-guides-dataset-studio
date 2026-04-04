"""
DITA Image Service — 4 image types:
1. Screenshots from Jira attachments
2. Architecture diagrams (Mermaid auto-generated)
3. Flowcharts for task topics (from steps)
4. Product images from AEM DAM (path reference)

All wrapped in DITA <fig> with <title> and <image>.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

AEM_DAM_BASE = os.getenv("AEM_DAM_BASE_PATH", "/content/dam/images")


# =============================================================================
# TYPE 1 — Screenshots from Jira attachments
# =============================================================================

def extract_images_from_jira(issue_key: str, max_images: int = 5) -> list[dict]:
    """
    Download image attachments from a Jira issue.
    Returns list of {type, filename, local_path, mime_type, dam_path, fig_xml}
    """
    results = []
    try:
        from app.services.jira_client import JiraClient
        jira = JiraClient()
        attachments = jira.get_issue_attachments(issue_key)
        image_atts = [
            a for a in attachments
            if _is_image(a.get("mimeType", ""), a.get("filename", ""))
        ]
        if not image_atts:
            return []

        issue_dir = IMAGES_DIR / issue_key
        issue_dir.mkdir(parents=True, exist_ok=True)

        for att in image_atts[:max_images]:
            filename    = att.get("filename", "image.png")
            content_url = att.get("content", "")
            mime_type   = att.get("mimeType", "image/png")
            if not content_url:
                continue
            try:
                content      = jira.download_attachment(content_url)
                safe_name    = _safe_filename(filename)
                local_path   = issue_dir / safe_name
                local_path.write_bytes(content)
                dam_path = f"{AEM_DAM_BASE}/{issue_key}/{safe_name}"
                results.append({
                    "type":       "screenshot",
                    "filename":   safe_name,
                    "local_path": str(local_path),
                    "mime_type":  mime_type,
                    "dam_path":   dam_path,
                    "fig_xml":    _fig_xml(dam_path, f"Screenshot: {safe_name}", f"Screenshot from {issue_key}"),
                })
            except Exception as e:
                logger.warning_structured("Image download failed", extra_fields={"filename": filename, "error": str(e)})
    except Exception as e:
        logger.warning_structured("Jira image extraction failed", extra_fields={"issue_key": issue_key, "error": str(e)})
    return results


# =============================================================================
# TYPE 2 — Architecture diagrams (Mermaid)
# =============================================================================

def generate_architecture_diagram(
    issue_key: str,
    components: list[str],
    relationships: list[tuple[str, str, str]],
    title: str = "Architecture Overview",
) -> Optional[dict]:
    """
    Generate architecture diagram from components + relationships.
    components:    ["DITA Map", "Topic A", "Topic B"]
    relationships: [("DITA Map", "references", "Topic A")]
    """
    try:
        mermaid   = _mermaid_architecture(components, relationships)
        issue_dir = IMAGES_DIR / issue_key
        issue_dir.mkdir(parents=True, exist_ok=True)
        mmd_file  = issue_dir / "architecture.mmd"
        mmd_file.write_text(mermaid, encoding="utf-8")
        svg_file  = issue_dir / "architecture.svg"
        rendered  = _render_mermaid(mmd_file, svg_file)
        filename  = "architecture.svg" if rendered else "architecture.mmd"
        path      = svg_file if rendered else mmd_file
        dam_path  = f"{AEM_DAM_BASE}/{issue_key}/{filename}"
        return {
            "type":           "architecture",
            "filename":       filename,
            "local_path":     str(path),
            "mermaid_source": mermaid,
            "dam_path":       dam_path,
            "fig_xml":        _fig_xml(dam_path, title, f"Architecture diagram for {issue_key}"),
        }
    except Exception as e:
        logger.warning_structured("Architecture diagram failed", extra_fields={"issue_key": issue_key, "error": str(e)})
        return None


def generate_architecture_from_dita(issue_key: str, dita_content: str) -> Optional[dict]:
    """Auto-parse topicrefs/keydefs from DITA and generate architecture diagram."""
    try:
        components    = []
        relationships = []
        map_match     = re.search(r'<title>([^<]+)</title>', dita_content)
        map_title     = map_match.group(1) if map_match else "DITA Map"
        components.append(map_title)
        for m in re.finditer(r'<topicref[^>]+href="([^"]+)"', dita_content):
            name = Path(m.group(1)).stem
            components.append(name)
            relationships.append((map_title, "references", name))
        for m in re.finditer(r'<keydef[^>]+keys="([^"]+)"', dita_content):
            key = f"keydef:{m.group(1)}"
            components.append(key)
            relationships.append((map_title, "defines", key))
        if len(components) < 2:
            return None
        return generate_architecture_diagram(issue_key, components, relationships, "Content Architecture")
    except Exception as e:
        logger.warning_structured("Architecture from DITA failed", extra_fields={"error": str(e)})
        return None


# =============================================================================
# TYPE 3 — Flowcharts for task topics
# =============================================================================

def generate_task_flowchart(
    issue_key: str,
    steps: list[str],
    title: str = "Task Flow",
    decision_points: Optional[list[int]] = None,
) -> Optional[dict]:
    """
    Generate flowchart from task steps list.
    decision_points: list of step indices that are decision diamonds.
    """
    try:
        if not steps:
            return None
        mermaid   = _mermaid_flowchart(steps, title, decision_points or [])
        issue_dir = IMAGES_DIR / issue_key
        issue_dir.mkdir(parents=True, exist_ok=True)
        mmd_file  = issue_dir / "flowchart.mmd"
        mmd_file.write_text(mermaid, encoding="utf-8")
        svg_file  = issue_dir / "flowchart.svg"
        rendered  = _render_mermaid(mmd_file, svg_file)
        filename  = "flowchart.svg" if rendered else "flowchart.mmd"
        path      = svg_file if rendered else mmd_file
        dam_path  = f"{AEM_DAM_BASE}/{issue_key}/{filename}"
        return {
            "type":           "flowchart",
            "filename":       filename,
            "local_path":     str(path),
            "mermaid_source": mermaid,
            "dam_path":       dam_path,
            "fig_xml":        _fig_xml(dam_path, title, f"Flowchart: {title}"),
            "steps_count":    len(steps),
        }
    except Exception as e:
        logger.warning_structured("Flowchart failed", extra_fields={"issue_key": issue_key, "error": str(e)})
        return None


def generate_flowchart_from_dita(issue_key: str, dita_content: str) -> Optional[dict]:
    """Auto-extract <cmd> steps from DITA task and generate flowchart."""
    try:
        cmds = [
            c.strip() for c in
            re.findall(r'<cmd[^>]*>([^<]+)</cmd>', dita_content, re.IGNORECASE)
            if c.strip()
        ]
        if not cmds:
            return None
        title_m = re.search(r'<title>([^<]+)</title>', dita_content)
        title   = title_m.group(1) if title_m else "Task Flow"
        return generate_task_flowchart(issue_key, cmds, title)
    except Exception as e:
        logger.warning_structured("Flowchart from DITA failed", extra_fields={"error": str(e)})
        return None


# =============================================================================
# TYPE 4 — AEM DAM image references
# =============================================================================

def reference_aem_dam_image(
    dam_path: str,
    title: str,
    alt: str = "",
    width: Optional[str] = None,
) -> dict:
    """
    Reference an existing AEM DAM image — no download needed.
    Returns DITA fig XML pointing to the DAM path.
    """
    return {
        "type":     "aem_dam",
        "dam_path": dam_path,
        "filename": Path(dam_path).name,
        "fig_xml":  _fig_xml(dam_path, title, alt or title, width=width),
    }


# =============================================================================
# Master function + DITA injection
# =============================================================================

def get_all_images_for_issue(
    issue_key: str,
    dita_content: str = "",
    include_flowchart: bool = True,
    include_architecture: bool = False,
) -> dict:
    """
    Get all images for a DITA topic in one call.
    Returns organized dict of all image types.
    """
    result = {
        "screenshots":    extract_images_from_jira(issue_key),
        "flowchart":      generate_flowchart_from_dita(issue_key, dita_content) if include_flowchart and dita_content else None,
        "architecture":   generate_architecture_from_dita(issue_key, dita_content) if include_architecture and dita_content else None,
        "dam_references": [],
    }
    result["total"] = (
        len(result["screenshots"]) +
        (1 if result["flowchart"] else 0) +
        (1 if result["architecture"] else 0)
    )
    return result


def inject_images_into_dita(
    dita_content: str,
    images: list[dict],
    inject_after: str = "context",
) -> str:
    """
    Inject <fig> elements into DITA content after a given element.
    inject_after: 'context' | 'shortdesc' | 'prereq' | etc.
    """
    if not images or not dita_content:
        return dita_content

    figs = "\n".join(img["fig_xml"] for img in images if img.get("fig_xml"))
    if not figs:
        return dita_content

    # Try injecting after specified element
    modified = re.sub(
        f"(</{inject_after}>)",
        f"\\1\n{figs}",
        dita_content, count=1, flags=re.IGNORECASE,
    )

    # Fallback: inject before closing body element
    if modified == dita_content:
        for body in ["taskbody", "conbody", "refbody", "body"]:
            modified = re.sub(
                f"(</{body}>)",
                f"{figs}\n\\1",
                dita_content, count=1, flags=re.IGNORECASE,
            )
            if modified != dita_content:
                break

    return modified


# =============================================================================
# Private helpers
# =============================================================================

def _is_image(mime_type: str, filename: str) -> bool:
    return (
        mime_type.lower() in {"image/png","image/jpeg","image/jpg","image/gif","image/svg+xml","image/webp"}
        or Path(filename).suffix.lower() in {".png",".jpg",".jpeg",".gif",".svg",".webp"}
    )


def _safe_filename(filename: str) -> str:
    return re.sub(r'[^\w\-.]', '-', filename)[:100]


def _escape_xml(text: str) -> str:
    return text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


def _fig_xml(
    image_path: str,
    title: str,
    alt: str = "",
    width: Optional[str] = None,
) -> str:
    w = f' width="{width}"' if width else ""
    return (
        f'<fig>\n'
        f'  <title>{_escape_xml(title)}</title>\n'
        f'  <image href="{image_path}" placement="break"{w}>\n'
        f'    <alt>{_escape_xml(alt or title)}</alt>\n'
        f'  </image>\n'
        f'</fig>'
    )


def _mermaid_flowchart(steps: list[str], title: str, decision_points: list[int]) -> str:
    lines = ["flowchart TD", f'    START(["{_escape_xml(title[:40])}"])']
    prev  = "START"
    for i, step in enumerate(steps):
        nid   = f"S{i+1}"
        short = step[:50].replace('"', "'")
        shape = f'{{{{"  {short}  "}}}}' if i in decision_points else f'["{short}"]'
        lines.append(f"    {nid}{shape}")
        lines.append(f"    {prev} --> {nid}")
        prev = nid
    lines.append('    END(["Done"])')
    lines.append(f"    {prev} --> END")
    return "\n".join(lines)


def _mermaid_architecture(
    components: list[str],
    relationships: list[tuple[str, str, str]],
) -> str:
    lines    = ["graph LR"]
    node_ids = {}
    for i, comp in enumerate(components):
        nid          = f"N{i}"
        node_ids[comp] = nid
        lines.append(f'    {nid}["{comp[:30].replace(chr(34), chr(39))}"]')
    for src, rel, tgt in relationships:
        sid = node_ids.get(src, "")
        tid = node_ids.get(tgt, "")
        if sid and tid:
            lines.append(f'    {sid} -->|"{rel}"| {tid}')
    return "\n".join(lines)


def _render_mermaid(input_file: Path, output_file: Path) -> bool:
    """Try mmdc CLI — returns True if rendered, False if not installed."""
    try:
        r = subprocess.run(
            ["mmdc", "-i", str(input_file), "-o", str(output_file)],
            capture_output=True, timeout=30,
        )
        return r.returncode == 0 and output_file.exists()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
