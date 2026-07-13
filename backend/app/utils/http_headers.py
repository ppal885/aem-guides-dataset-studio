"""HTTP header helpers safe for Starlette/FastAPI latin-1 header encoding."""

from __future__ import annotations

from urllib.parse import quote


def content_disposition(filename: str, *, disposition: str = "attachment") -> str:
    """
    Build a Content-Disposition value that is safe for latin-1 HTTP headers.

    Starlette encodes header values as latin-1. Recipe titles like
    ``Curated realtime corpus (1–2 lakh topics)`` contain en-dashes (U+2013)
    and would raise UnicodeEncodeError if placed directly in ``filename="..."``.

    Uses an ASCII ``filename`` fallback plus RFC 5987 ``filename*=UTF-8''...``.
    """
    raw = (filename or "download").replace("\\", "_").replace("/", "_").strip() or "download"
    # Quoted-string fallback: ASCII only, no double-quotes or control chars.
    ascii_name = (
        raw.encode("ascii", errors="replace")
        .decode("ascii")
        .replace("?", "-")
        .replace('"', "_")
        .replace("\r", "")
        .replace("\n", "")
    )
    if not ascii_name.strip("._- "):
        ascii_name = "download"
    encoded = quote(raw, safe="")
    return f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'
