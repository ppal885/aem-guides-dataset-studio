"""
Label Intelligence Engine for Jira QA Copilot.

Classifies Jira labels into QA/product domains and derives testing, automation, and UAC heuristics.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

# --- Classification buckets (lowercase tokens; Jira labels normalized with .lower().strip()) ---

_FEATURE_EXACT = frozenset(
    x.strip().lower()
    for x in (
        "new-editor,web-editor,editor,authoring,publishing,publish,output,native-pdf,pdf,"
        "baseline,versioning,version,compare,history,metadata,translation,localization,"
        "review,approval,workflow,ditamap,map,topic,conref,keyref,xref,output-preset,"
        "accessibility,a11y,wcag,keyboard,screen-reader,performance,scalability,load,"
        "indexing,search,repository,dam,attachment,import,export,migration"
    ).split(",")
    if x.strip()
)

_FEATURE_SUBSTR = (
    ("editor", "editor"),
    ("publish", "publishing"),
    ("pdf", "publishing"),
    ("baseline", "baseline"),
    ("version", "baseline"),
    ("metadata", "metadata"),
    ("perf", "performance"),
    ("scale", "scalability"),
    ("a11y", "accessibility"),
    ("access", "accessibility"),
    ("conref", "conref"),
    ("keyref", "keyref"),
    ("xref", "xref"),
)

_SEVERITY_EXACT = frozenset(
    x.strip().lower()
    for x in (
        "customer-escalation,escalation,p1-escalation,sev-1,sev1,blocker,critical,p0,p1,"
        "production,hotfix,data-loss,corruption"
    ).split(",")
    if x.strip()
)

_REGRESSION_EXACT = frozenset(
    x.strip().lower() for x in "regression,regressions,break,break-fix,regressed,regression-suite".split(",") if x.strip()
)

_AUTOMATION_EXACT = frozenset(
    x.strip().lower()
    for x in (
        "flaky,flaky-test,flakiness,automate,automation,e2e,ui-test,ui-tests,api-test,"
        "api-tests,integration-test,smoke-test,manual-only,not-automatable,cannot-automate,"
        "selenium,playwright,cypress,ci-only"
    ).split(",")
    if x.strip()
)

# Retrieval: expand issue labels to related tokens found in other tickets' label JSON.
_TOKEN_EXPANSIONS: dict[str, frozenset[str]] = {
    "publishing": frozenset({"publishing", "publish", "pdf", "output", "native-pdf", "oat", "preset"}),
    "regression": frozenset({"regression", "regressions", "regressed", "break", "break-fix"}),
    "baseline": frozenset({"baseline", "version", "compare", "history", "versioning", "audit"}),
    "metadata": frozenset({"metadata", "meta", "element", "attribute", "props"}),
    "performance": frozenset({"performance", "perf", "slow", "latency", "timeout", "oom"}),
    "scalability": frozenset({"scalability", "scale", "large", "bulk", "batch"}),
    "new-editor": frozenset({"new-editor", "web-editor", "editor", "authoring", "save", "ui"}),
    "accessibility": frozenset({"accessibility", "a11y", "wcag", "keyboard", "screen-reader", "aria"}),
    "customer-escalation": frozenset({"customer-escalation", "escalation", "sev", "blocker"}),
}


def _norm_labels(labels: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in labels or []:
        t = str(raw).strip().lower()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _classify_token(token: str) -> set[str]:
    """Return one or more of: feature, customer, severity, regression, automation."""
    kinds: set[str] = set()
    if token in _SEVERITY_EXACT:
        kinds.add("severity")
    if token in _REGRESSION_EXACT:
        kinds.add("regression")
    if token in _AUTOMATION_EXACT:
        kinds.add("automation")
    if token in _FEATURE_EXACT:
        kinds.add("feature")
    for needle, _domain in _FEATURE_SUBSTR:
        if needle in token:
            kinds.add("feature")
            break
    # Customer tokens: reuse customer engine alias list (lazy import).
    try:
        from app.services.customer_intelligence_engine import _LABEL_ALIASES

        if token in _LABEL_ALIASES or token == "internal":
            kinds.add("customer")
    except Exception:
        if token in ("swift", "abs", "topcon", "cisco", "internal"):
            kinds.add("customer")
    return kinds


def _customer_display_names(labels: list[str]) -> list[str]:
    try:
        from app.services.customer_intelligence_engine import detect_customer_labels_from_issue

        return detect_customer_labels_from_issue([str(x) for x in labels])
    except Exception:
        return []


def _build_implications(norm: list[str], kinds_flat: set[str]) -> tuple[list[str], list[str], list[str]]:
    testing: list[str] = []
    automation: list[str] = []
    uac: list[str] = []
    s = set(norm)

    def has(*tokens: str) -> bool:
        return any(t in s for t in tokens)

    if kinds_flat & {"regression"} or has("regression", "break", "break-fix"):
        testing.append("Prioritize old vs new behavior validation; expand regression matrix and known-good baselines.")
    if has("publishing", "publish", "pdf", "output", "native-pdf"):
        testing.append("Include output validation (PDF/web/custom) and publish-related API checks where applicable.")
    if has("baseline", "versioning", "version", "compare"):
        testing.append("Include versioning/history/reference checks and baseline compare scenarios.")
    if has("metadata", "meta"):
        testing.append("Exercise metadata/property round-trips and validation rules across save/reopen cycles.")
    if has("performance", "perf", "scalability", "scale", "load"):
        testing.append("Include scale/load or resource-consumption validation for representative corpora.")
    if has("new-editor", "web-editor"):
        testing.append("Deep-dive web editor UX states: save, lock, concurrent edit, and error surfacing.")
    if has("accessibility", "a11y", "wcag", "keyboard", "screen-reader"):
        testing.append("Include accessibility checks: keyboard paths, focus order, ARIA/roles, and contrast for changed UI.")

    if kinds_flat & {"automation"} or has("flaky", "flaky-test", "flakiness"):
        automation.append("Flaky label: lower automation confidence; prefer quarantined suites, reruns policy, and root-cause isolation before scaling CI.")
    if has("manual-only", "not-automatable", "cannot-automate"):
        automation.append("Manual-only signals: document exploratory charters instead of forcing brittle UI automation.")
    if has("e2e", "ui-test", "ui-tests", "selenium", "playwright", "cypress"):
        automation.append("UI/e2e labels: budget extra stabilization time and selector hygiene reviews.")

    if kinds_flat & {"severity"} or has("customer-escalation", "escalation", "blocker", "critical", "production"):
        uac.append("Escalation/severity labels: align explicit UAC sign-off scope, rollback criteria, and customer-visible impact statements.")
    if kinds_flat & {"customer"} or _customer_display_names(norm):
        uac.append("Customer labels: tie acceptance checks to named customer workflows and contractual wording where relevant.")
    if kinds_flat & {"regression"}:
        uac.append("Regression: document observable before/after and attach evidence IDs for UAC reviewers.")

    raw_extra = (os.getenv("JIRA_QA_LABEL_TESTING_HINTS_JSON") or "").strip()
    if raw_extra:
        try:
            obj = json.loads(raw_extra)
            if isinstance(obj, dict):
                for lab in norm:
                    hint = obj.get(lab)
                    if isinstance(hint, str) and hint.strip():
                        testing.append(hint.strip()[:400])
        except (json.JSONDecodeError, TypeError):
            pass

    return testing, automation, uac


def analyze_issue_labels(labels: list[str] | None) -> dict[str, Any]:
    """
    Full label intelligence payload for one issue's label list.

    Returns:
        feature_domains, customer_domains, risk_domains (severity+regression+escalation-style),
        testing_implications, automation_implications, uac_focus_points
    """
    norm = _norm_labels(labels)
    feature_domains: list[str] = []
    customer_domains: list[str] = []
    risk_domains: list[str] = []
    regression_marked: list[str] = []
    automation_marked: list[str] = []
    kinds_union: set[str] = set()

    for t in norm:
        kinds = _classify_token(t)
        kinds_union |= kinds
        if "feature" in kinds and t not in feature_domains:
            feature_domains.append(t)
        if "customer" in kinds and t not in customer_domains:
            customer_domains.append(t)
        if "severity" in kinds and t not in risk_domains:
            risk_domains.append(t)
        if "regression" in kinds:
            if t not in regression_marked:
                regression_marked.append(t)
            if t not in risk_domains:
                risk_domains.append(t)
        if "automation" in kinds and t not in automation_marked:
            automation_marked.append(t)
        # Performance/scalability as risk-relevant product areas
        if t in ("performance", "scalability", "scalable", "load") or "perf" in t or "scale" in t:
            if t not in risk_domains:
                risk_domains.append(t)

    for disp in _customer_display_names(labels or []):
        if disp not in customer_domains:
            customer_domains.append(disp)

    testing_impl, auto_impl, uac_pts = _build_implications(norm, kinds_union)

    return {
        "feature_domains": feature_domains[:40],
        "customer_domains": customer_domains[:40],
        "risk_domains": risk_domains[:40],
        "testing_implications": testing_impl[:20],
        "automation_implications": auto_impl[:15],
        "uac_focus_points": uac_pts[:15],
    }


def expanded_label_tokens_for_retrieval(labels: list[str] | None) -> frozenset[str]:
    """Lowercase tokens for Chroma label-overlap reranking (issue labels + expansions)."""
    norm = _norm_labels(labels)
    out: set[str] = set(norm)
    for t in norm:
        out.add(t)
        exp = _TOKEN_EXPANSIONS.get(t)
        if exp:
            out |= set(exp)
        for key, bag in _TOKEN_EXPANSIONS.items():
            if key in t or t in key:
                out |= set(bag)
    if len(out) > 96:
        return frozenset(sorted(out)[:96])
    return frozenset(out)


def label_intelligence_context_block(report: dict[str, Any], *, max_chars: int = 3500) -> str:
    """Compact prose block for LLM tails (risk, gap, reasoning)."""
    try:
        blob = json.dumps(report, ensure_ascii=False)
    except (TypeError, ValueError):
        blob = str(report)
    return blob[:max_chars]


class LabelIntelligenceEngine:
    """Entry point aligned with CustomerIntelligenceEngine naming."""

    def analyze(self, labels: list[str] | None) -> dict[str, Any]:
        return analyze_issue_labels(labels)
