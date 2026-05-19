"""Locator quality and governance for QA automation (reuse-first, fragile detection)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

LocQuality = Literal["reuse", "safe_new", "fragile"]

SOURCE_PAGE_OBJECT = "page_object_method"
SOURCE_XPATH_LIBRARY = "xpath_library"
SOURCE_DOM_SNAPSHOT = "dom_or_snapshot"
SOURCE_PLAYBOOK = "playbook"
SOURCE_UNKNOWN = "unknown"

_NORMALIZE_SOURCE = {
    "page_object": SOURCE_PAGE_OBJECT,
    "page_object_method": SOURCE_PAGE_OBJECT,
    "po": SOURCE_PAGE_OBJECT,
    "xpath_library": SOURCE_XPATH_LIBRARY,
    "library": SOURCE_XPATH_LIBRARY,
    "dom": SOURCE_DOM_SNAPSHOT,
    "dom_snapshot": SOURCE_DOM_SNAPSHOT,
    "snapshot": SOURCE_DOM_SNAPSHOT,
    "playbook": SOURCE_PLAYBOOK,
    "unknown": SOURCE_UNKNOWN,
}

_REACT_SPECTRUM_ID = re.compile(r"react-spectrum-\d+", re.I)
_TABVIEW_JUI_ID = re.compile(r"tabView-jui-react-\d+", re.I)
_TABVIEW_LOOSE = re.compile(r"tabview-jui-react-\d+", re.I)
_TOPIC_STATIC_ID = re.compile(r"topic_id__[\w-]+", re.I)
_SPECTRUM_NUMERIC_TOKEN = re.compile(r"\bspectrum-\d+-\d+\b", re.I)
_HEX_OR_RANDOM_ID = re.compile(r"@id\s*=\s*['\"][^'\"]*(?:[a-f0-9]{8,}|_\d{3,})[^'\"]*['\"]", re.I)

_HASHY_CLASS_RE = re.compile(r"[a-f0-9]{8,}|css-[a-z0-9]{6,}|sc-[A-Za-z0-9]+")
_GLOBAL_INDEX_RE = re.compile(r"\(\s*//[a-z.]+\s*\)\s*\[\s*\d+\s*\]", re.I)
_ROLE_TABLIST_OK = re.compile(r"@role\s*=\s*['\"]tablist['\"]", re.I)
_ROLE_TABPANEL_OK = re.compile(r"@role\s*=\s*['\"]tabpanel['\"]", re.I)
_ROLE_TAB_OK = re.compile(r"@role\s*=\s*['\"]tab['\"]", re.I)
_ROLE_DIALOG_OK = re.compile(r"@role\s*=\s*['\"]dialog['\"]|@role\s*=\s*['\"]alertdialog['\"]", re.I)
_ARIA_OK = re.compile(r"@aria-[a-z][a-z0-9-]*\s*=", re.I)
_NORMALIZE_SPACE_OK = re.compile(r"normalize-space\s*\(\s*\)\s*=", re.I)
_MENU_LABEL_OK = re.compile(r"spectrum-Menu-itemLabel|Menu-itemLabel", re.I)
_BY_LABEL_RELATIVE = re.compile(
    r"following-sibling::|preceding-sibling::|ancestor::|descendant::", re.I
)


@dataclass
class LocatorAssessment:
    quality: LocQuality
    score_0_100: int
    flags: list[str]
    notes: list[str]
    suggestions: list[str] = field(default_factory=list)


def normalize_locator_source(raw: str) -> str:
    """Map API aliases to canonical source tier labels."""
    key = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    return _NORMALIZE_SOURCE.get(key, SOURCE_UNKNOWN)


def infer_stable_anchor(expr: str) -> bool:
    """
    Heuristic: role/ARIA, dialog/menu scoping hints, label-relative axes,
    or Spectrum menu label patterns indicate a more stable anchor than raw generated ids.
    """
    s = expr or ""
    if _ROLE_TABLIST_OK.search(s):
        return True
    if _ROLE_TAB_OK.search(s):
        return True
    if _ROLE_TABPANEL_OK.search(s):
        return True
    if _ROLE_DIALOG_OK.search(s):
        return True
    if _ARIA_OK.search(s):
        return True
    if _NORMALIZE_SPACE_OK.search(s) and "normalize-space()" in s.lower():
        return True
    if _MENU_LABEL_OK.search(s):
        return True
    if _BY_LABEL_RELATIVE.search(s):
        return True
    # Descendant of dialog via path segment
    if re.search(r"//[a-z*]+\[@[^\]]*role\s*=\s*['\"]dialog['\"]", s, re.I):
        return True
    return False


def build_locator_suggestions(flags: list[str], _expr: str) -> list[str]:
    """Human-readable safer patterns keyed off raised flags."""
    fset = set(flags)
    out: list[str] = []
    if "react_spectrum_generated_id" in fset or "spectrum_numeric_token" in fset:
        out.append(
            "Prefer Spectrum-accessible patterns: "
            "//*[@role='tablist']//div[@role='tab' and normalize-space()='…'], "
            "corresponding //*[@role='tabpanel'], or menu paths via "
            ".//*[contains(@class,'spectrum-Menu')]//*[contains(@class,'spectrum-Menu-itemLabel') "
            "and normalize-space()='…']."
        )
    if "tabview_generated_id" in fset:
        out.append(
            "Avoid TabView-generated @id; use tablist/tab/tabpanel roles with visible labels, "
            "or a Page Object that wraps the tab strip."
        )
    if "hardcoded_topic_id" in fset:
        out.append(
            "Avoid hard-coded AEM topic ids (topic_id__…); resolve via PO search/open-by-title "
            "or navigation helpers so content-driven ids do not break suites."
        )
    if "hash_or_generated_class" in fset:
        out.append(
            "Replace hashed build classes with @role, aria-label(ledby), or visible "
            "normalize-space() text scoped under a dialog or landmark."
        )
    if "global_indexed_node" in fset or "positional_index_risk" in fset:
        out.append(
            "Scope first: //*[@role='dialog' or @aria-modal='true']//… then use label-relative "
            "or role-based match; avoid (//button)[n] across the whole document."
        )
    if "unscoped_relative" in fset:
        out.append(
            "Anchor under a scoped dialog, menu, or panel container (role or aria-labelledby) "
            "before using short //relative segments."
        )
    if "generated_id" in fset and "react_spectrum_generated_id" not in fset:
        out.append(
            "Prefer get_by_role / PO methods, aria-labelledby chains, or XPath library entries "
            "over dynamic @id values."
        )
    if not out and fset - {"empty"}:
        out.append(
            "Cross-check against DOM snapshot or playbook evidence; prefer PO or library "
            "before committing new XPath."
        )
    if not out:
        out.append(
            "Hierarchy: (1) Page Object field/method, (2) XPath library, "
            "(3) DOM/playbook/snapshot evidence, (4) new XPath only with evidence, stable anchor, "
            "score, and approval."
        )
    return out


def assess_xpath_or_selector(expr: str) -> LocatorAssessment:
    """
    Heuristic assessment of a single XPath/CSS fragment (typically from a Page Object).
    ``reuse`` = high confidence framework-friendly pattern; ``fragile`` = should block or require review.
    """
    s = (expr or "").strip()
    flags: list[str] = []
    notes: list[str] = []
    if not s:
        return LocatorAssessment("fragile", 0, ["empty"], ["Empty locator"], ["Provide a non-empty locator."])

    low = s.lower()

    if _REACT_SPECTRUM_ID.search(s):
        flags.append("react_spectrum_generated_id")
    if _TABVIEW_JUI_ID.search(s) or _TABVIEW_LOOSE.search(s):
        flags.append("tabview_generated_id")
    if _TOPIC_STATIC_ID.search(s) or re.search(
        r"@id\s*=\s*['\"][^'\"]*topic_id__", s, re.I
    ):
        flags.append("hardcoded_topic_id")
    if _SPECTRUM_NUMERIC_TOKEN.search(s) and not flags:
        flags.append("spectrum_numeric_token")
    if _HEX_OR_RANDOM_ID.search(s) and not any(
        x in flags
        for x in (
            "react_spectrum_generated_id",
            "tabview_generated_id",
            "hardcoded_topic_id",
        )
    ):
        flags.append("generated_id")

    if _HASHY_CLASS_RE.search(s):
        flags.append("hash_or_generated_class")
    if _GLOBAL_INDEX_RE.search(s):
        flags.append("global_indexed_node")
    if re.search(r"\[2\]|\[3\]|\[4\]", s) and "[@" not in s[:80] and "/tbody" not in low:
        flags.append("positional_index_risk")

    framework_friendly = (
        bool(_ROLE_TABLIST_OK.search(s))
        or bool(_ROLE_TABPANEL_OK.search(s))
        or (bool(_NORMALIZE_SPACE_OK.search(s)) and "normalize-space()" in low)
        or bool(_MENU_LABEL_OK.search(s))
        or bool(_ARIA_OK.search(s))
    )

    suggestions = build_locator_suggestions(flags, s)

    if framework_friendly and not flags:
        return LocatorAssessment(
            "reuse",
            92,
            [],
            ["Matches playbook-friendly role/ARIA/label pattern."],
            build_locator_suggestions([], s),
        )

    if flags:
        if framework_friendly:
            return LocatorAssessment(
                "safe_new",
                55,
                flags,
                notes
                + [
                    "Mixed signals: framework-like structure but fragile signals present; review required."
                ],
                suggestions,
            )
        return LocatorAssessment(
            "fragile",
            max(15, 40 - 10 * len(flags)),
            flags,
            notes + ["Fails reuse bar; needs DOM evidence, scoping, and approval."],
            suggestions,
        )

    if len(s) < 80 and ("//*" in s or s.startswith("//")):
        return LocatorAssessment(
            "safe_new",
            68,
            ["unscoped_relative"],
            ["Short relative XPath; confirm panel/dialog scope."],
            build_locator_suggestions(["unscoped_relative"], s),
        )

    return LocatorAssessment(
        "safe_new",
        72,
        [],
        ["No strong fragile signals; still verify against UI snapshot / DOM evidence."],
        build_locator_suggestions([], s),
    )


def evaluate_new_xpath_gate(
    *,
    has_dom_evidence: bool,
    stable_anchor_effective: bool,
    assessment: LocatorAssessment,
    approval_status: str,
) -> tuple[bool, list[str]]:
    """
    Policy for non–PO/non-library locators: DOM evidence, stable anchor,
    non-fragile quality with score floor, and approval.
    """
    approvable = (approval_status or "none").strip().lower()
    blockers: list[str] = []

    if not has_dom_evidence:
        blockers.append("Attach DOM or UI snapshot evidence before adopting a new XPath (third tier).")
    if not stable_anchor_effective:
        blockers.append(
            "Stable anchor required: role/ARIA, tablist/tabpanel, Spectrum menu-label text, "
            "or scoped dialog/menu container — not generated id or global index."
        )
    if assessment.quality == "fragile":
        blockers.append("Locator quality is fragile; refine to role/label-relative or library PO pattern.")
    elif assessment.score_0_100 < 55:
        blockers.append("Quality score below threshold (55) for unapproved new XPath.")
    if approvable != "approved":
        blockers.append("Approval status must be 'approved' to treat this as governed new XPath.")

    return len(blockers) == 0, blockers


def lint_only_defaults(
    source: str,
    has_dom_evidence: bool,
    approval_status: str,
) -> bool:
    """Skip strict gate when user only pasted XPath without policy context."""
    return (
        normalize_locator_source(source) == SOURCE_UNKNOWN
        and not has_dom_evidence
        and (approval_status or "none").strip().lower() == "none"
    )


def assess_locator_full(
    expr: str,
    *,
    source: str = SOURCE_UNKNOWN,
    has_dom_evidence: bool = False,
    stable_anchor_confirmed: bool | None = None,
    approval_status: str = "none",
) -> dict[str, object]:
    """
    Full locator lint + governance gate.
    When source/evidence/approval are left at defaults, only quality + suggestions are emphasized
    (policy_skipped=True).
    """
    assessment = assess_xpath_or_selector(expr)
    inferred = infer_stable_anchor(expr)
    effective_anchor = inferred if stable_anchor_confirmed is None else bool(stable_anchor_confirmed)

    src_norm = normalize_locator_source(source)
    skip_policy = lint_only_defaults(source, has_dom_evidence, approval_status)

    preferred_source_order = [
        "(1) Page Object method or field",
        "(2) Curated XPath library entry",
        "(3) DOM / playbook / UI snapshot evidence",
        (
            "(4) New XPath only with: DOM evidence, stable anchor, quality score, "
            "and approved status"
        ),
    ]

    if skip_policy:
        gate_ok: bool | None = None
        blockers: list[str] = []
        policy_note = (
            "Policy gate not evaluated — set source, DOM evidence, and approval to enforce "
            "new-XPath rules."
        )
    elif src_norm in (SOURCE_PAGE_OBJECT, SOURCE_XPATH_LIBRARY):
        gate_ok = True
        blockers = []
        policy_note = "Reuse tier (PO / library): gate waived; locator quality still applies."
    else:
        gate_ok, blockers = evaluate_new_xpath_gate(
            has_dom_evidence=has_dom_evidence,
            stable_anchor_effective=effective_anchor,
            assessment=assessment,
            approval_status=approval_status,
        )
        policy_note = "New locator path: governance gate applied."

    return {
        "quality": assessment.quality,
        "score_0_100": assessment.score_0_100,
        "flags": assessment.flags,
        "notes": assessment.notes,
        "suggestions": assessment.suggestions,
        "governance": {
            "source_tier": src_norm,
            "preferred_source_order": preferred_source_order,
            "stable_anchor_inferred": inferred,
            "stable_anchor_effective": effective_anchor,
            "stable_anchor_overridden": stable_anchor_confirmed is not None,
            "policy_skipped": skip_policy,
            "policy_note": policy_note,
            "new_xpath_gate_passed": gate_ok,
            "gate_blockers": blockers,
        },
    }
