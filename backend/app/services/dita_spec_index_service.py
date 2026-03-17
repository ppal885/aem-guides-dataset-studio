"""DITA spec index service - fetch OASIS pages and index into DB."""
import re
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.db.dita_spec_models import DitaSpecChunk
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

OASIS_BASE = "https://docs.oasis-open.org/dita/dita/v1.3/errata02/os/complete/part3-all-inclusive"
DEFAULT_URLS = [
    f"{OASIS_BASE}/archSpec/base/topicstructure.html",
    f"{OASIS_BASE}/archSpec/base/topiccontent.html",
    f"{OASIS_BASE}/archSpec/base/mapstructure.html",
    f"{OASIS_BASE}/langRef/content-reference/content-reference.html",
    f"{OASIS_BASE}/langRef/base/key-reference.html",
    f"{OASIS_BASE}/langRef/base/section.html",
    f"{OASIS_BASE}/langRef/base/example.html",
    f"{OASIS_BASE}/langRef/base/body.html",
    f"{OASIS_BASE}/langRef/base/keydef.html",
    f"{OASIS_BASE}/langRef/base/keyscope.html",
]


def fetch_oasis_page(url: str) -> str:
    """Fetch HTML from OASIS URL and return plain text."""
    try:
        import httpx
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning_structured("OASIS fetch failed", extra_fields={"url": url, "error": str(e)})
        raise

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text)
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html)


def _infer_element_from_url(url: str) -> str | None:
    """Infer element name from OASIS URL (e.g. .../section.html -> section)."""
    if not url:
        return None
    base = url.split("/")[-1].replace(".html", "").replace(".htm", "")
    if base and base != "content-reference" and base != "key-reference":
        return base
    return None


def parse_element_page(html: str, url: str) -> list[dict]:
    """Parse HTML for element definitions, nesting, attributes. Extract chunks."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return [{"text_content": html[:8000], "source_url": url}]

    soup = BeautifulSoup(html, "html.parser")
    chunks = []
    text = soup.get_text(separator=" ", strip=True)
    text_clean = re.sub(r"\s+", " ", text)
    element_name = _infer_element_from_url(url)
    if len(text_clean) > 500:
        chunks.append({
            "element_name": element_name,
            "content_type": "element",
            "text_content": text_clean[:8000],
            "source_url": url,
        })
    return chunks if chunks else [
        {
            "text_content": text_clean[:8000] or "DITA spec content",
            "source_url": url,
            "element_name": element_name,
            "content_type": "element",
        }
    ]


def index_chunk(session: Session, chunk_dict: dict) -> DitaSpecChunk:
    """Upsert a chunk into DB."""
    chunk_id = str(uuid.uuid4())
    chunk = DitaSpecChunk(
        id=chunk_id,
        element_name=chunk_dict.get("element_name"),
        content_type=chunk_dict.get("content_type"),
        parent_element=chunk_dict.get("parent_element"),
        children_elements=chunk_dict.get("children_elements"),
        attributes=chunk_dict.get("attributes"),
        text_content=chunk_dict.get("text_content", ""),
        source_url=chunk_dict.get("source_url"),
    )
    session.add(chunk)
    return chunk


def index_oasis_spec(session: Session, urls: Optional[list[str]] = None) -> dict:
    """Fetch and index OASIS DITA spec pages. Returns stats."""
    urls = urls or DEFAULT_URLS
    indexed = 0
    errors = []
    for url in urls:
        try:
            html = fetch_oasis_page(url)
            chunks = parse_element_page(html, url)
            for c in chunks:
                index_chunk(session, c)
                indexed += 1
        except Exception as e:
            errors.append(str(e))
            logger.warning_structured("OASIS index failed for URL", extra_fields={"url": url, "error": str(e)})
    return {"indexed": indexed, "urls_processed": len(urls), "errors": errors}


def load_seed_into_db(session: Session) -> dict:
    """Load dita_spec_seed.json into DB. Fallback when OASIS fetch fails."""
    import json
    from pathlib import Path
    seed_path = Path(__file__).resolve().parent.parent / "storage" / "dita_spec_seed.json"
    if not seed_path.exists():
        return {"indexed": 0, "error": "Seed file not found"}
    with open(seed_path, encoding="utf-8") as f:
        chunks = json.load(f)
    for c in chunks:
        index_chunk(session, {
            "element_name": c.get("element_name"),
            "content_type": c.get("content_type"),
            "parent_element": c.get("parent_element"),
            "children_elements": c.get("children_elements"),
            "attributes": c.get("attributes"),
            "text_content": c.get("text_content", ""),
            "source_url": None,
        })
    return {"indexed": len(chunks)}
