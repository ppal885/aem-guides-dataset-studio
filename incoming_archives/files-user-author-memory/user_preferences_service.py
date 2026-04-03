"""
User Preferences Service — per-author memory for the authoring platform.

Remembers per author:
- Last issue worked on
- Preferred DITA type per issue type
- Author name and display preferences
- Recent issues list (last 10)
- Custom query templates they saved
- Quality score thresholds they prefer
- Which sections they always approve/reject

Storage: backend/app/storage/user_prefs/{author_id}.json
No database needed — simple JSON per author.

Place at: backend/app/services/user_preferences_service.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

PREFS_DIR = Path(__file__).resolve().parent.parent / "storage" / "user_prefs"
PREFS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_AUTHOR_ID = "default"


# ── Data shape ────────────────────────────────────────────────────────────────

def _default_prefs(author_id: str) -> dict:
    return {
        "author_id":         author_id,
        "display_name":      "",
        "email":             "",
        "created_at":        datetime.utcnow().isoformat(),
        "updated_at":        datetime.utcnow().isoformat(),

        # Last session state — restored on next open
        "last_issue_key":    "",
        "last_issue_summary": "",
        "last_dita_type":    "task",
        "last_stage":        "idle",   # idle | research | generating | done

        # DITA type preferences per Jira issue type
        # Author can override: "Bug → task", "Story → concept", etc.
        "dita_type_map": {
            "Bug":          "task",
            "Story":        "concept",
            "Task":         "task",
            "Epic":         "concept",
            "Sub-task":     "task",
            "Improvement":  "task",
        },

        # Recent issues — last 10 worked on, newest first
        "recent_issues": [],

        # Saved custom query templates per category
        "saved_queries": {
            "dita_elements":  [],
            "aem_guides":     [],
            "bugs_fixes":     [],
            "expert_examples":[],
            "dita_spec":      [],
        },

        # Review preferences — sections author always approves without reading
        "auto_approve_sections": [],    # e.g. ["shortdesc", "prereq"]
        "always_review_sections": [],   # e.g. ["steps", "result"]

        # Quality threshold — author's personal minimum before publishing
        "min_quality_score": 80,

        # UI preferences
        "default_tab":        "preview",  # preview | xml | rendered
        "show_research_step": True,        # show query plan step or skip it
        "compact_mode":       False,

        # Stats
        "total_topics_generated": 0,
        "total_topics_approved":  0,
        "total_topics_rejected":  0,
        "total_scratch_started":  0,
    }


# ── Load / Save ───────────────────────────────────────────────────────────────

def _load(author_id: str) -> dict:
    path = PREFS_DIR / f"{author_id}.json"
    if not path.exists():
        return _default_prefs(author_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Merge with defaults so new fields always exist
        defaults = _default_prefs(author_id)
        defaults.update(data)
        return defaults
    except Exception as e:
        logger.warning_structured(
            "Failed to load user prefs",
            extra_fields={"author_id": author_id, "error": str(e)},
        )
        return _default_prefs(author_id)


def _save(prefs: dict) -> None:
    author_id = prefs.get("author_id", DEFAULT_AUTHOR_ID)
    prefs["updated_at"] = datetime.utcnow().isoformat()
    path = PREFS_DIR / f"{author_id}.json"
    path.write_text(json.dumps(prefs, indent=2), encoding="utf-8")


# ── Public API ────────────────────────────────────────────────────────────────

def get_prefs(author_id: str = DEFAULT_AUTHOR_ID) -> dict:
    """Get all preferences for an author."""
    return _load(author_id)


def set_author_name(
    author_id: str,
    display_name: str,
    email: str = "",
) -> dict:
    """Set author display name and email."""
    prefs = _load(author_id)
    prefs["display_name"] = display_name
    prefs["email"]        = email
    _save(prefs)
    return prefs


def remember_last_issue(
    author_id:    str,
    issue_key:    str,
    issue_summary: str,
    dita_type:    str = "task",
    stage:        str = "idle",
) -> dict:
    """
    Called every time author opens an issue or changes stage.
    Restores this on next session open.
    """
    prefs = _load(author_id)

    prefs["last_issue_key"]     = issue_key
    prefs["last_issue_summary"] = issue_summary
    prefs["last_dita_type"]     = dita_type
    prefs["last_stage"]         = stage

    # Add to recent issues (deduplicated, newest first)
    recent = [r for r in prefs["recent_issues"] if r["issue_key"] != issue_key]
    recent.insert(0, {
        "issue_key":   issue_key,
        "summary":     issue_summary,
        "dita_type":   dita_type,
        "opened_at":   datetime.utcnow().isoformat(),
    })
    prefs["recent_issues"] = recent[:10]   # keep last 10

    _save(prefs)
    return prefs


def get_preferred_dita_type(
    author_id:   str,
    jira_issue_type: str,
    labels:      list[str] = None,
) -> str:
    """
    Get author's preferred DITA type for this kind of issue.
    Checks label overrides first, then issue type map.
    Falls back to "task".
    """
    prefs = _load(author_id)
    labels = labels or []

    # Label-based override takes highest priority
    label_map = {
        "concept":    "concept",
        "overview":   "concept",
        "reference":  "reference",
        "api":        "reference",
        "glossary":   "glossentry",
        "term":       "glossentry",
        "task":       "task",
        "howto":      "task",
    }
    for label in labels:
        if label.lower() in label_map:
            return label_map[label.lower()]

    # Author's personal issue type map
    dita_map = prefs.get("dita_type_map", {})
    return dita_map.get(jira_issue_type, "task")


def set_dita_type_preference(
    author_id:       str,
    jira_issue_type: str,
    dita_type:       str,
) -> dict:
    """Author manually overrides: 'for Bug issues, I always want task'."""
    prefs = _load(author_id)
    prefs["dita_type_map"][jira_issue_type] = dita_type
    _save(prefs)
    return prefs


def save_custom_query(
    author_id: str,
    category:  str,
    query:     str,
    purpose:   str = "",
) -> dict:
    """Author saves a custom query template for future use."""
    prefs = _load(author_id)
    saved = prefs["saved_queries"].get(category, [])

    # Deduplicate
    if not any(q["query"] == query for q in saved):
        saved.append({
            "query":    query,
            "purpose":  purpose,
            "saved_at": datetime.utcnow().isoformat(),
            "use_count": 0,
        })
    prefs["saved_queries"][category] = saved[-20:]   # keep last 20 per category
    _save(prefs)
    return prefs


def increment_query_use(author_id: str, category: str, query: str) -> None:
    """Track which custom queries the author uses most."""
    prefs = _load(author_id)
    for q in prefs["saved_queries"].get(category, []):
        if q["query"] == query:
            q["use_count"] = q.get("use_count", 0) + 1
            break
    _save(prefs)


def record_generation(
    author_id: str,
    action:    str,   # generated | approved | rejected | scratch_started
) -> dict:
    """Track authoring stats."""
    prefs = _load(author_id)
    key = {
        "generated":      "total_topics_generated",
        "approved":       "total_topics_approved",
        "rejected":       "total_topics_rejected",
        "scratch_started":"total_scratch_started",
    }.get(action)

    if key:
        prefs[key] = prefs.get(key, 0) + 1
    _save(prefs)
    return prefs


def update_ui_pref(
    author_id: str,
    key:       str,
    value,
) -> dict:
    """Update a single UI preference."""
    prefs = _load(author_id)
    allowed = {
        "default_tab", "show_research_step",
        "compact_mode", "min_quality_score",
        "auto_approve_sections", "always_review_sections",
    }
    if key in allowed:
        prefs[key] = value
        _save(prefs)
    return prefs


def get_session_restore(author_id: str) -> dict:
    """
    Called when author opens the platform.
    Returns everything needed to restore last session state.
    """
    prefs = _load(author_id)
    return {
        "author_id":         prefs["author_id"],
        "display_name":      prefs["display_name"],
        "last_issue_key":    prefs["last_issue_key"],
        "last_issue_summary": prefs["last_issue_summary"],
        "last_dita_type":    prefs["last_dita_type"],
        "last_stage":        prefs["last_stage"],
        "recent_issues":     prefs["recent_issues"],
        "default_tab":       prefs["default_tab"],
        "show_research_step":prefs["show_research_step"],
        "min_quality_score": prefs["min_quality_score"],
        "stats": {
            "generated": prefs["total_topics_generated"],
            "approved":  prefs["total_topics_approved"],
            "rejected":  prefs["total_topics_rejected"],
        },
    }
