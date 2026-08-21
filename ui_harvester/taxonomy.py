"""Layered, reusable UI taxonomy + deterministic DOM->taxonomy mapping.

PRODUCT -> SURFACE -> REGION -> CONTAINER -> CONTROL_PATTERN -> CAPABILITY -> ACTION -> STATE -> CONTEXT

The taxonomy is generic interaction vocabulary. Surfaces/menus are DISCOVERED at
run time (see the *_HINTS seed lists) - the seeds are entry points, never a claim
that the list is complete. No Jira-specific rules live here.
"""

# --- Control patterns: HOW a control behaves (generic primitives) -------------
CONTROL_PATTERNS = (
    "ACTION_BUTTON", "ICON_BUTTON", "TOGGLE", "CHECKBOX", "RADIO", "COMBOBOX",
    "MULTI_SELECT_COMBOBOX", "DROPDOWN", "DISCLOSURE_TOGGLE", "TAB", "MENU_ITEM",
    "TREE_ITEM", "TEXT_INPUT", "FORM_TEXT_INPUT", "SEARCH_INPUT", "LINK",
    "BREADCRUMB", "PAGINATION", "DRAG_HANDLE", "UNKNOWN",
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
    "FILTER_PANEL", "LIST", "MODAL_FORM", "PREVIEW_CONTAINER",
    "NESTED_CONTEXT_MENU", "ACTION_FAMILY", "SECOND_LEVEL_MENU", "UNKNOWN",
)

# --- Surface seeds (DISCOVERED at run time; this is not the complete taxonomy) -
SURFACE_HINTS = (
    "NEW_EDITOR", "MAP_CONSOLE", "ASSETS_UI", "ASSET_DETAILS", "OUTPUT_PRESET",
    "BASELINE", "TRANSLATION", "REVIEW", "NEW_EDITOR_MAP_COLLECTIONS",
    "LEGACY_MAP_COLLECTIONS",
)

# Product ontology. These records express containment and observed capability
# families only; they deliberately do not claim that the legacy collection UI
# is superseded or replaced without separate lifecycle evidence.
PRODUCT_HIERARCHY_EDGES = (
    ("AEM_GUIDES", "HAS_AREA", "USER_PREFERENCES"),
    ("USER_PREFERENCES", "HAS_SECTION", "GENERAL"),
    ("USER_PREFERENCES", "HAS_SECTION", "APPEARANCE"),
    ("GENERAL", "HAS_PREFERENCE", "FOLDER_PROFILE"),
    ("GENERAL", "HAS_PREFERENCE", "ROOT_MAP"),
    ("GENERAL", "HAS_PREFERENCE", "MAXIMUM_RECENT_FILES"),
    ("GENERAL", "HAS_PREFERENCE", "MAP_OPENING_PREFERENCES"),
    ("APPEARANCE", "HAS_PREFERENCE", "APPLICATION_THEME"),
    ("APPLICATION_THEME", "HAS_OPTION", "LIGHT"),
    ("APPLICATION_THEME", "HAS_OPTION", "DARK"),
    ("APPLICATION_THEME", "HAS_OPTION", "USE_DEVICE_THEME"),
    ("APPEARANCE", "HAS_PREFERENCE", "DISPLAY_BY_TITLE_OR_FILE_NAME"),
    ("APPEARANCE", "HAS_PREFERENCE", "ALWAYS_LOCATE_FILES_IN_REPOSITORY"),
    ("AEM_GUIDES", "HAS_AREA", "MAP_COLLECTIONS"),
    ("MAP_COLLECTIONS", "HAS_CURRENT_SURFACE", "NEW_EDITOR_MAP_COLLECTIONS"),
    ("MAP_COLLECTIONS", "HAS_LEGACY_SURFACE", "LEGACY_MAP_COLLECTIONS"),
)

CAPABILITY_HIERARCHY_EDGES = (
    ("INSERT_IMAGE", "HAS_STEP", "SELECT_IMAGE_FILE"),
    ("INSERT_IMAGE", "HAS_STEP", "SELECT_IMAGE_KEY_REFERENCE"),
    ("INSERT_IMAGE", "HAS_STATE", "IMAGE_PREVIEW"),
    ("INSERT_IMAGE", "HAS_FIELD", "FIGURE_TITLE"),
    ("INSERT_IMAGE", "HAS_FIELD", "ALTERNATE_TEXT"),
    ("SAVE_AS_NEW_VERSION", "HAS_FIELD", "VERSION_COMMENT"),
    ("SAVE_AS_NEW_VERSION", "HAS_FIELD", "VERSION_LABEL_MULTI_SELECT"),
    ("GENERATE", "HAS_ACTION", "GENERATE_SITES_PAGE"),
    ("GENERATE", "HAS_ACTION", "GENERATE_CONTENT_FRAGMENT"),
    ("GENERATE", "HAS_ACTION", "GENERATE_EXPERIENCE_FRAGMENT"),
    ("ADD_TO", "HAS_ACTION", "ADD_TO_COLLECTIONS"),
    ("ADD_TO", "HAS_ACTION", "ADD_TO_REUSABLE_CONTENT"),
    ("SHOW", "HAS_TOGGLE", "TRACK_CHANGES"),
    ("SHOW", "HAS_TOGGLE", "SHOW_TAGS"),
    ("SHOW", "HAS_TOGGLE", "SHOW_NON_BREAKING_SPACES"),
    ("INSERT_OVERFLOW", "HAS_ACTION", "CROSS_REFERENCE"),
    ("INSERT_OVERFLOW", "HAS_ACTION", "REUSABLE_CONTENT"),
    ("INSERT_OVERFLOW", "HAS_ACTION", "SYMBOL"),
    ("INSERT_OVERFLOW", "HAS_ACTION", "CITATIONS"),
    ("INSERT_OVERFLOW", "HAS_ACTION", "SNIPPETS"),
    ("INSERT_OVERFLOW", "HAS_ACTION", "KEYWORD"),
)

BEHAVIORAL_HEURISTICS = (
    "MUTATION_PRESERVES_EXISTING_SEMANTIC_STATE",
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
