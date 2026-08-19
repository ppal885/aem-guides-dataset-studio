"""Layered, reusable UI taxonomy + deterministic DOM->taxonomy mapping.

PRODUCT -> SURFACE -> REGION -> CONTAINER -> CONTROL_PATTERN -> CAPABILITY -> ACTION -> STATE -> CONTEXT

The taxonomy is generic interaction vocabulary. Surfaces/menus are DISCOVERED at
run time (see the *_HINTS seed lists) - the seeds are entry points, never a claim
that the list is complete. No Jira-specific rules live here.
"""

# --- Control patterns: HOW a control behaves (generic primitives) -------------
CONTROL_PATTERNS = (
    "ACTION_BUTTON", "ICON_BUTTON", "TOGGLE", "CHECKBOX", "RADIO", "COMBOBOX",
    "DROPDOWN", "DISCLOSURE_TOGGLE", "TAB", "MENU_ITEM", "TREE_ITEM", "TEXT_INPUT",
    "SEARCH_INPUT", "LINK", "BREADCRUMB", "PAGINATION", "DRAG_HANDLE", "UNKNOWN",
)

# --- Regions: WHERE on the surface -------------------------------------------
REGIONS = (
    "LEFT_NAV", "TOP_TOOLBAR", "EDITOR_CANVAS", "RIGHT_PANEL", "STATUS_BAR",
    "DIALOG", "DRAWER", "CONTENT_AREA", "UNKNOWN",
)

# --- Containers: the grouping widget -----------------------------------------
CONTAINERS = (
    "TOOLBAR", "MENU", "OVERFLOW_MENU", "CONTEXT_MENU", "ACCORDION", "TAB_GROUP",
    "TREE", "TABLE", "FORM", "DIALOG", "FILE_PICKER", "SEARCH_PANEL",
    "FILTER_PANEL", "LIST", "UNKNOWN",
)

# --- Surface seeds (DISCOVERED at run time; this is not the complete taxonomy) -
SURFACE_HINTS = (
    "NEW_EDITOR", "MAP_CONSOLE", "ASSETS_UI", "ASSET_DETAILS", "OUTPUT_PRESET",
    "BASELINE", "TRANSLATION", "REVIEW",
)

# --- Deterministic ARIA role -> control pattern -------------------------------
# Generic and stable: no product-specific mapping.
ROLE_TO_CONTROL = {
    "button": "ACTION_BUTTON",
    "tab": "TAB",
    "menuitem": "MENU_ITEM",
    "menuitemcheckbox": "MENU_ITEM",
    "menuitemradio": "MENU_ITEM",
    "treeitem": "TREE_ITEM",
    "checkbox": "CHECKBOX",
    "radio": "RADIO",
    "combobox": "COMBOBOX",
    "listbox": "DROPDOWN",
    "searchbox": "SEARCH_INPUT",
    "textbox": "TEXT_INPUT",
    "link": "LINK",
    "tablist": "TAB_GROUP",
    "dialog": "DIALOG",
    "menu": "MENU",
    "tree": "TREE",
    "grid": "TABLE",
    "table": "TABLE",
    "option": "MENU_ITEM",
}

# aria-* attributes that carry semantic state, and the state token they imply.
ARIA_STATE_TOKENS = {
    ("aria-expanded", "true"): "EXPANDED",
    ("aria-expanded", "false"): "COLLAPSED",
    ("aria-selected", "true"): "SELECTED",
    ("aria-checked", "true"): "CHECKED",
    ("aria-checked", "false"): "UNCHECKED",
    ("aria-pressed", "true"): "PRESSED",
    ("aria-disabled", "true"): "DISABLED",
}


def map_role_to_control(role, has_aria_expanded=False):
    """Deterministic ARIA role -> CONTROL_PATTERN. A control that owns an
    aria-expanded attribute is a DISCLOSURE_TOGGLE regardless of its tag (this is
    the semantic behaviour of a 'chevron', which we store as behaviour not glyph).
    """
    role = (role or "").strip().lower()
    if has_aria_expanded and role in ("button", "", "link"):
        return "DISCLOSURE_TOGGLE"
    return ROLE_TO_CONTROL.get(role, "UNKNOWN")


def is_known_control(pattern):
    return pattern in CONTROL_PATTERNS and pattern != "UNKNOWN"
