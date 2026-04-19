"""DITA enrichment service - add shortdesc, prolog, metadata to topics that lack them."""
from datetime import datetime
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from app.core.structured_logging import get_structured_logger
from app.services.dita_xml_headers import serialize_normalized_dita_tree

logger = get_structured_logger(__name__)

# DITA topic root elements (exclude map types)
TOPIC_ROOTS = {"topic", "concept", "task", "reference", "glossentry", "glossary"}


def _strip_ns(tag: str) -> str:
    """Strip XML namespace from tag."""
    return tag.split("}")[-1] if "}" in tag else tag


def _get_title_text(root: ET.Element) -> str:
    """Extract title text from topic root."""
    for child in root:
        if _strip_ns(child.tag) == "title":
            return (child.text or "") + "".join(ET.tostring(c, encoding="unicode", method="text") for c in child)
    title = root.find(".//{http://dita.oasis-open.org/architecture/2005/}title")
    if title is not None:
        return (title.text or "") + "".join(ET.tostring(c, encoding="unicode", method="text") for c in title)
    return ""


def _get_first_paragraph_text(root: ET.Element, max_len: int = 80) -> str:
    """Extract text from first paragraph in body."""
    for p in root.iter():
        if _strip_ns(p.tag) == "p":
            text = (p.text or "") + "".join(ET.tostring(c, encoding="unicode", method="text") for c in p)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:max_len] + ("..." if len(text) > max_len else "")
    return ""


def _derive_shortdesc(root: ET.Element, root_tag: str) -> str:
    """Derive shortdesc from title or first paragraph."""
    title = _get_title_text(root)
    if title:
        type_label = root_tag.capitalize()
        return f"{type_label}: {title[:60]}" + ("..." if len(title) > 60 else "")
    first_p = _get_first_paragraph_text(root)
    if first_p:
        return first_p
    return "Topic description."


def _has_shortdesc(root: ET.Element) -> bool:
    """Check if topic has shortdesc."""
    for child in root:
        if _strip_ns(child.tag) == "shortdesc":
            text = (child.text or "") + "".join(ET.tostring(c, encoding="unicode", method="text") for c in child)
            if text.strip():
                return True
    return False


def _has_prolog_with_metadata(root: ET.Element) -> bool:
    """Check if topic has prolog with metadata."""
    for child in root:
        if _strip_ns(child.tag) == "prolog":
            for c in child:
                if _strip_ns(c.tag) == "metadata":
                    return True
    return False


def _insert_shortdesc(root: ET.Element, root_tag: str, shortdesc_text: str) -> None:
    """Insert shortdesc after title. DITA order: title, shortdesc?, prolog?, body."""
    children = list(root)
    insert_idx = 0
    for i, c in enumerate(children):
        if _strip_ns(c.tag) == "title":
            insert_idx = i + 1
            break
    shortdesc = ET.Element("shortdesc")
    shortdesc.text = shortdesc_text
    root.insert(insert_idx, shortdesc)


def _insert_prolog(root: ET.Element) -> None:
    """Insert prolog with metadata (author, created) after shortdesc/title."""
    children = list(root)
    insert_idx = 0
    for i, c in enumerate(children):
        tag = _strip_ns(c.tag)
        if tag in ("title", "shortdesc"):
            insert_idx = i + 1
    prolog = ET.Element("prolog")
    metadata = ET.SubElement(prolog, "metadata")
    author = ET.SubElement(metadata, "othermeta")
    author.set("name", "author")
    author.set("content", "AEM Guides Dataset Studio")
    created = ET.SubElement(metadata, "othermeta")
    created.set("name", "created")
    created.set("content", datetime.utcnow().strftime("%Y-%m-%d"))
    root.insert(insert_idx, prolog)


def _enrich_topic_file(path: Path) -> dict:
    """
    Enrich a single DITA topic file. Returns {shortdesc_added: bool, prolog_added: bool, error: str|None}.
    """
    result = {"shortdesc_added": False, "prolog_added": False, "error": None}
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        root_tag = _strip_ns(root.tag)
        if root_tag not in TOPIC_ROOTS:
            return result

        modified = False
        if not _has_shortdesc(root):
            shortdesc_text = _derive_shortdesc(root, root_tag)
            _insert_shortdesc(root, root_tag, shortdesc_text)
            result["shortdesc_added"] = True
            modified = True

        if not _has_prolog_with_metadata(root):
            _insert_prolog(root)
            result["prolog_added"] = True
            modified = True

        if modified:
            xml_bytes = serialize_normalized_dita_tree(root, root_tag)
            path.write_bytes(xml_bytes)
    except ET.ParseError as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = str(e)
    return result


def enrich_dita_folder(folder: Path) -> dict:
    """
    Enrich all DITA topics in folder: add shortdesc and prolog/metadata where missing.
    Returns {topics_processed: int, shortdesc_added: int, prolog_added: int, errors: []}.
    """
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        return {"topics_processed": 0, "shortdesc_added": 0, "prolog_added": 0, "errors": []}

    stats = {"topics_processed": 0, "shortdesc_added": 0, "prolog_added": 0, "errors": []}
    for p in folder.rglob("*"):
        if p.suffix.lower() != ".dita":
            continue
        r = _enrich_topic_file(p)
        stats["topics_processed"] += 1
        if r["shortdesc_added"]:
            stats["shortdesc_added"] += 1
        if r["prolog_added"]:
            stats["prolog_added"] += 1
        if r["error"]:
            stats["errors"].append(f"{p.relative_to(folder)}: {r['error']}")

    if stats["shortdesc_added"] or stats["prolog_added"]:
        logger.info_structured(
            "DITA enrichment completed",
            extra_fields={
                "folder": str(folder),
                "topics_processed": stats["topics_processed"],
                "shortdesc_added": stats["shortdesc_added"],
                "prolog_added": stats["prolog_added"],
            },
        )
    return stats
