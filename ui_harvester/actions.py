"""Action safety classification: SAFE / BLOCKED / UNKNOWN.

The crawler is READ_ONLY / NON_DESTRUCTIVE by default. Every interactive
candidate is classified before it may be clicked. UNKNOWN is NEVER clicked
automatically. Policies are configurable (config/ui_crawler.yaml) and must not
rely on button text alone - a capability slug or a selector match can block too.
"""

import re

# Default destructive capability tokens (case-insensitive substring on the
# capability slug or accessible name). Blocked even if not in user config.
DEFAULT_BLOCKED_PATTERNS = (
    "delete", "remove", "move", "rename", "publish", "quick_publish",
    "manage_publication", "save", "upload", "create", "merge", "check_in",
    "checkin", "restore", "reprocess", "submit", "change_metadata",
    "apply_config", "apply_configuration", "review_task", "unlock",
    "discard", "overwrite", "purge", "clear",
)

# Default safe navigation/disclosure tokens.
DEFAULT_SAFE_PATTERNS = (
    "open", "close", "expand", "collapse", "switch", "preview", "search",
    "filter", "navigate", "properties", "outline", "conditions", "select_file",
    "select_root_map", "next", "back", "show", "hide", "view",
)

SAFE, BLOCKED, UNKNOWN = "SAFE", "BLOCKED", "UNKNOWN"

# A separate observation boundary prevents a safe menu/disclosure click from
# being mistaken for permission to execute the business operation it exposes.
OBSERVE, CONFIGURE_EPHEMERAL, COMMIT_MUTATION = (
    "OBSERVE",
    "CONFIGURE_EPHEMERAL",
    "COMMIT_MUTATION",
)


def _norm(text):
    return re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_")


def classify_action(*, capability="", name="", control_pattern="", selector="",
                    safe_patterns=None, blocked_patterns=None,
                    safe_selectors=None, blocked_selectors=None):
    """Return SAFE, BLOCKED, or UNKNOWN for a candidate control.

    Precedence: explicit BLOCKED (selector or token) > explicit SAFE (selector or
    token) > structural disclosure/navigation defaults > UNKNOWN. A destructive
    token always blocks, even when a safe token is also present (fail safe).
    """
    blocked_patterns = tuple(blocked_patterns or ()) + DEFAULT_BLOCKED_PATTERNS
    safe_patterns = tuple(safe_patterns or ()) + DEFAULT_SAFE_PATTERNS
    hay = " ".join(_norm(x) for x in (capability, name))
    sel = (selector or "").strip()

    for bsel in (blocked_selectors or ()):
        if bsel and bsel in sel:
            return BLOCKED
    for bp in blocked_patterns:
        if bp and _norm(bp) in hay:
            return BLOCKED
    for ssel in (safe_selectors or ()):
        if ssel and ssel in sel:
            return SAFE
    for sp in safe_patterns:
        if sp and _norm(sp) in hay:
            return SAFE
    # Structural defaults: pure disclosure/tab/menu-open controls are safe to toggle.
    if control_pattern in ("DISCLOSURE_TOGGLE", "TAB"):
        return SAFE
    return UNKNOWN


def is_clickable(verdict):
    """Only SAFE actions are auto-clicked in read-only mode."""
    return verdict == SAFE


def mutation_boundary(
    *,
    action="",
    opens_container="",
    reversible=False,
    commits_business_operation=False,
):
    """Classify how far a read-only crawler may progress through a workflow."""
    if commits_business_operation:
        return COMMIT_MUTATION
    if reversible and opens_container in (
        "DIALOG",
        "MODAL_FORM",
        "MENU",
        "SUBMENU",
    ):
        return CONFIGURE_EPHEMERAL
    if opens_container in (
        "DIALOG",
        "MODAL_FORM",
        "MENU",
        "SUBMENU",
        "CONTEXT_MENU",
        "NESTED_CONTEXT_MENU",
        "RIGHT_PANEL",
    ):
        return OBSERVE
    if any(
        token in _norm(action)
        for token in ("save", "create", "generate", "add_to")
    ):
        return COMMIT_MUTATION
    return OBSERVE
