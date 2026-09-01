"""UI state model + deterministic state signature.

A stateful SPA presents many UI states behind one URL, so state identity must be
built from stable *semantic* signals (surface, panels, dialog, menu, mode, tab,
entity/empty context, major visible capabilities), NOT from the raw URL and NOT
from volatile data (timestamps, counts, usernames, fixture/test names, temp ids).

state_id = SHA256(canonical_state_signature)
"""

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# Query/path fragments that are volatile per-visit and must never enter identity.
_VOLATILE_QUERY_KEYS = {
    "timestamp", "ts", "_", "cachebust", "cb", "nonce", "token", "sessionid",
    "jcr:", "wcmmode", "debugclientlibs",
}
# Substrings that mark a path segment as a volatile fixture/temp id.
_VOLATILE_PATH_RE = re.compile(
    r"(?i)(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"  # uuid
    r"|(?:\bGUID-[0-9a-f-]+)"                                                 # GUID-file
    r"|(?:\d{10,})"                                                            # long numeric ids/epochs
)

# Fields that are captured for context but MUST be excluded from the signature
# because they are volatile (they describe the moment, not the state).
_NON_SIGNATURE_FIELDS = {
    "url", "captured_at", "screenshot_id", "state_id", "currentness",
    "product_version", "state_properties",
}

# Query keys that identify a product route/surface rather than the opened
# customer asset. Asset paths such as ``src`` and ``ditamap`` are intentionally
# excluded so fixture data never becomes part of a surface identity.
_ROUTE_QUERY_KEYS = {
    "appmode",
    "leftpanel",
    "mode",
    "panel",
    "rail",
    "view",
    "workspace",
}


@dataclass
class UIState:
    state_id: str = ""
    product: str = "AEM_GUIDES"
    product_area: str = ""
    surface: str = ""
    workspace: str = ""
    region: str = ""
    container: str = ""
    active_left_panel: str = ""
    active_right_panel: str = ""
    active_editor_mode: str = ""
    active_tab: str = ""
    open_dialog: str = ""
    open_menu: str = ""
    open_submenu: str = ""
    active_entity_type: str = ""
    active_file_type: str = ""
    selection_count: int = 0
    empty_state: str = ""
    visible_capabilities: list = field(default_factory=list)
    disabled_capabilities: list = field(default_factory=list)
    state_properties: dict = field(default_factory=dict)
    url: str = ""
    url_normalized: str = ""
    route_identity: str = ""
    captured_at: str = ""
    product_version: str = "UNKNOWN"
    currentness: str = ""
    screenshot_id: str = ""

    def to_dict(self):
        return asdict(self)


def normalize_url(url):
    """Drop scheme host-case, fragment, trailing slash, volatile query keys, and
    mask volatile path segments. Two visits to the same logical location produce
    the same normalized URL."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    path = _VOLATILE_PATH_RE.sub("*", parts.path.rstrip("/")) or "/"
    kept = []
    for pair in parts.query.split("&"):
        if not pair:
            continue
        key = pair.split("=", 1)[0].lower()
        if any(key.startswith(v) for v in _VOLATILE_QUERY_KEYS):
            continue
        kept.append(pair)
    query = "&".join(sorted(kept))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def normalize_route_identity(url):
    """Return the stable route identity for lifecycle-aware surface matching.

    The route keeps the application path and semantic routing query keys, but
    deliberately drops opened asset identifiers and all volatile values. This
    lets one capability exist independently on current and legacy surfaces.
    """
    if not url:
        return ""
    parts = urlsplit(url.strip())
    path = _VOLATILE_PATH_RE.sub("*", parts.path.rstrip("/")) or "/"
    lowered_path = path.lower()
    if lowered_path.startswith("/libs/fmdita/mapcollections"):
        path = "/libs/fmdita/mapcollections"
    elif lowered_path.startswith(
        "/libs/fmdita/clientlibs/xmleditor/page.html"
    ):
        path = "/libs/fmdita/clientlibs/xmleditor/page.html"

    route_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in _ROUTE_QUERY_KEYS:
            route_query.append((key.lower(), value.strip().lower()))
    return path.lower() + (
        "?" + urlencode(sorted(route_query)) if route_query else ""
    )


def _canonical_signature(state):
    """Stable, order-independent semantic signature for a state (dict or UIState)."""
    data = state.to_dict() if isinstance(state, UIState) else dict(state)
    sig = {}
    for key, value in data.items():
        if key in _NON_SIGNATURE_FIELDS:
            continue
        if isinstance(value, list):
            # capability lists are sets for identity - order and dupes do not matter
            value = sorted({str(v) for v in value})
        sig[key] = value
    # url_normalized IS part of identity (it is already de-volatilized)
    sig["url_normalized"] = normalize_url(data.get("url_normalized") or data.get("url", ""))
    return json.dumps(sig, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_state_id(state):
    """state_id = SHA256(canonical semantic signature)."""
    return "sha256:" + hashlib.sha256(_canonical_signature(state).encode("utf-8")).hexdigest()


def finalize_state(state):
    """Fill normalized URL, route identity, and state id on a UIState."""
    if not state.url_normalized:
        state.url_normalized = normalize_url(state.url)
    if not state.route_identity:
        state.route_identity = normalize_route_identity(state.url)
    state.state_id = compute_state_id(state)
    return state
