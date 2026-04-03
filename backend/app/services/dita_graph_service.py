"""DITA graph service - model elements and nesting for graph-based retrieval."""
import json
from pathlib import Path
from typing import Any, Optional

from app.db.dita_spec_models import DitaSpecChunk
from app.db.session import SessionLocal
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

SEED_PATH = Path(__file__).resolve().parent.parent / "storage" / "dita_spec_seed.json"

# In-memory graph: {element_name: {children: [...], attributes: {...}, text_content: str}}
_graph: dict[str, dict] = {}
_graph_loaded = False


def _parse_children(raw: Optional[Any]) -> list[str]:
    """Parse children_elements payload to a normalized list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(child).strip() for child in raw if str(child).strip()]
    if isinstance(raw, tuple):
        return [str(child).strip() for child in raw if str(child).strip()]
    if not isinstance(raw, str):
        raw = str(raw)
    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
        return [str(c) for c in parsed] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _parse_attributes(raw: Optional[Any]) -> dict[str, str]:
    """Parse attributes payload to a normalized dict."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    if not isinstance(raw, str):
        raw = str(raw)
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return dict(parsed) if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _load_from_db(session) -> list[dict]:
    """Load chunks from DB."""
    chunks = (
        session.query(DitaSpecChunk)
        .filter(DitaSpecChunk.element_name.isnot(None))
        .all()
    )
    return [
        {
            "element_name": c.element_name,
            "parent_element": c.parent_element,
            "children_elements": c.children_elements,
            "attributes": c.attributes,
            "text_content": c.text_content or "",
        }
        for c in chunks
    ]


def _load_from_seed() -> list[dict]:
    """Load chunks from seed JSON."""
    if not SEED_PATH.exists():
        return []
    try:
        with open(SEED_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning_structured("Failed to load DITA seed for graph", extra_fields={"error": str(e)})
        return []


def _build_graph(chunks: list[dict]) -> dict[str, dict]:
    """Build graph from chunk list."""
    graph: dict[str, dict] = {}
    for c in chunks:
        name = (c.get("element_name") or "").strip()
        if not name:
            continue
        children = _parse_children(c.get("children_elements"))
        attrs = _parse_attributes(c.get("attributes"))
        text = (c.get("text_content") or "").strip()
        if name not in graph:
            graph[name] = {"children": [], "attributes": {}, "text_content": ""}
        graph[name]["children"] = list(dict.fromkeys(graph[name]["children"] + children))
        graph[name]["attributes"] = {**graph[name]["attributes"], **attrs}
        if text:
            graph[name]["text_content"] = text
    return graph


def _ensure_graph_loaded(session=None) -> None:
    """Load graph from DB or seed on first use."""
    global _graph, _graph_loaded
    if _graph_loaded:
        return
    chunks = []
    db_session = session
    own_session = False
    if db_session is None:
        db_session = SessionLocal()
        own_session = True
    try:
        count = db_session.query(DitaSpecChunk).filter(DitaSpecChunk.element_name.isnot(None)).count()
        if count > 0:
            chunks = _load_from_db(db_session)
    except Exception as e:
        logger.warning_structured("DITA graph DB load failed", extra_fields={"error": str(e)})
    finally:
        if own_session and db_session:
            db_session.close()
    if not chunks:
        chunks = _load_from_seed()
    _graph = _build_graph(chunks)
    _graph_loaded = True


def get_children_of(element: str, session=None) -> list[str]:
    """Return elements that can nest inside the given element."""
    _ensure_graph_loaded(session)
    key = (element or "").strip().lower()
    if not key:
        return []
    for name, data in _graph.items():
        if name.lower() == key:
            return list(data.get("children", []))
    return []


def get_attributes_of(element: str, session=None) -> dict[str, str]:
    """Return attributes for the given element (required/optional)."""
    _ensure_graph_loaded(session)
    key = (element or "").strip().lower()
    if not key:
        return {}
    for name, data in _graph.items():
        if name.lower() == key:
            return dict(data.get("attributes", {}))
    return {}


def get_element_summary(element: str, session=None) -> str:
    """Return short text summary for prompt injection."""
    _ensure_graph_loaded(session)
    key = (element or "").strip().lower()
    if not key:
        return ""
    for name, data in _graph.items():
        if name.lower() == key:
            return (data.get("text_content") or "")[:500]
    return ""


def get_graph_summary_for_elements(elements: list[str], session=None) -> str:
    """
    Return structured text block for prompt: nesting and attributes for given elements.
    Used for "what can nest inside X?" and "what attributes does Y have?".
    """
    _ensure_graph_loaded(session)
    if not elements:
        return ""
    lines = []
    seen = set()
    for el in elements:
        el_clean = (el or "").strip()
        if not el_clean or el_clean.lower() in seen:
            continue
        seen.add(el_clean.lower())
        children = get_children_of(el_clean, session)
        attrs = get_attributes_of(el_clean, session)
        summary = get_element_summary(el_clean, session)
        parts = [f"Element '{el_clean}':"]
        if children:
            parts.append(f"  children=[{', '.join(children)}]")
        if attrs:
            attrs_str = ", ".join(f"{k}={v}" for k, v in attrs.items())
            parts.append(f"  attributes={{{attrs_str}}}")
        if summary:
            parts.append(f"  summary={summary[:200]}...")
        lines.append(" ".join(parts))
    return "\n".join(lines) if lines else ""


def reset_graph() -> None:
    """Reset graph state (for tests or reload)."""
    global _graph, _graph_loaded
    _graph = {}
    _graph_loaded = False
