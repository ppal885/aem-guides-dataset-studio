"""
Regression Memory — historical repeat signals from Jira corpus, labels, CI failures, reopen patterns.
"""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any

_AREA_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("repeated_feature_regression", ("regression", "regressed", "broken again", "reintroduced", "came back")),
    (
        "old_editor_vs_new_editor",
        (
            "web editor",
            "new editor",
            "old editor",
            "classic editor",
            "editor parity",
            "oxygen",
            "xml editor",
        ),
    ),
    (
        "repeated_publishing_failures",
        ("publish", "pdf", "dita-ot", "output preset", "sites output", "generation failed", "publish failed"),
    ),
    (
        "repeated_metadata_bugs",
        ("metadata", "dc:", "topicmeta", "navtitle", "props", "attribute", "ditaval"),
    ),
    (
        "repeated_baseline_issues",
        ("baseline", "version compare", "compare versions", "snapshot", "branch"),
    ),
    (
        "repeated_reference_conref_keyref",
        ("conref", "keyref", "keydef", "xref", "href resolution", "reference", "scope="),
    ),
)


def _norm_blob(*parts: str) -> str:
    return " ".join((p or "").lower() for p in parts if p)


def _issue_chunks_only(chunks: list[dict[str, Any]], jira_key: str | None) -> list[dict[str, Any]]:
    if not jira_key:
        return []
    jk = str(jira_key).strip().upper()
    out: list[dict[str, Any]] = []
    for c in chunks or []:
        ck = str(c.get("jira_key") or "").strip().upper()
        if ck == jk:
            out.append(c)
    return out


def _reopened_signal(issue_chunks: list[dict[str, Any]]) -> bool:
    for c in issue_chunks:
        m = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        status = str(m.get("status") or m.get("issue_status") or "").lower()
        if "reopen" in status:
            return True
        doc = str(c.get("document") or "").lower()
        if "reopened" in doc or "re-opened" in doc:
            return True
    return False


def _hits_text(hits: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """(jira_key, title, document_snippet) for related issues."""
    rows: list[tuple[str, str, str]] = []
    for h in hits or []:
        jk = str(h.get("jira_key") or "").strip()
        title = str(h.get("title") or "")
        doc = str(h.get("document") or "")[:1200]
        if jk or title or doc:
            rows.append((jk, title, doc))
    return rows


def _match_areas(text: str) -> set[str]:
    matched: set[str] = set()
    for area, pats in _AREA_PATTERNS:
        for p in pats:
            if p in text:
                matched.add(area)
                break
    return matched


def _failure_intel_text_blob(failure_intel: dict[str, Any]) -> str:
    parts: list[str] = []
    for x in (failure_intel.get("related_failures") or [])[:20]:
        if isinstance(x, dict):
            parts.append(str(x.get("test") or x.get("name") or ""))
        else:
            parts.append(str(x))
    for x in (failure_intel.get("repeated_failure_signals") or [])[:15]:
        parts.append(str(x))
    for x in (failure_intel.get("historical_patterns") or [])[:10]:
        parts.append(str(x))
    return _norm_blob(" ".join(parts))


def _automation_area_hits(failure_intel: dict[str, Any] | None) -> Counter[str]:
    c: Counter[str] = Counter()
    if not failure_intel or not isinstance(failure_intel, dict):
        return c
    blob = _failure_intel_text_blob(failure_intel)
    for name, pats in _AREA_PATTERNS:
        for p in pats:
            if p in blob:
                c[name] += 1
                break
    clusters = failure_intel.get("failure_clusters") or []
    if isinstance(clusters, list):
        for cl in clusters[:8]:
            if not isinstance(cl, dict):
                continue
            sig = str(cl.get("signature") or "").lower()
            ex = " ".join(str(x) for x in (cl.get("examples") or [])[:5]).lower()
            sub = sig + " " + ex
            for area, pats in _AREA_PATTERNS:
                for p in pats:
                    if p in sub:
                        c[area] += 1
                        break
    return c


class RegressionMemoryEngine:
    """Correlate labels, related Jira, issue lifecycle, and CI payloads into regression memory."""

    def analyze(
        self,
        *,
        labels: list[str],
        components: list[str],
        related_hits: list[dict[str, Any]],
        issue_chunks: list[dict[str, Any]],
        jira_key: str | None,
        failure_intelligence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        lab = _norm_blob(" ".join(labels))
        comp = _norm_blob(" ".join(components))
        issue_only = _issue_chunks_only(issue_chunks, jira_key)
        reopened = _reopened_signal(issue_only)

        historical: list[dict[str, Any]] = []
        area_hits: Counter[str] = Counter()

        for jk, title, doc in _hits_text(related_hits):
            blob = _norm_blob(title, doc)
            matched = _match_areas(blob)
            reg_like = "regression" in blob or "regress" in blob
            if reg_like or matched:
                for a in matched:
                    area_hits[a] += 1
                if reg_like and not matched:
                    area_hits["repeated_feature_regression"] += 1
                    matched = {"repeated_feature_regression"}
                historical.append(
                    {
                        "area": next(iter(sorted(matched))) if matched else "repeated_feature_regression",
                        "jira_key": jk or None,
                        "title": (title or "")[:240],
                        "signals": sorted(matched)[:6] or (["regression_language"] if reg_like else []),
                        "source": "historical_jira",
                    }
                )

        if reopened:
            historical.append(
                {
                    "area": "ticket_lifecycle",
                    "jira_key": jira_key,
                    "title": "reopened_or_reopen_status",
                    "signals": ["reopened_ticket"],
                    "source": "issue_metadata",
                }
            )
            area_hits["repeated_feature_regression"] += 1

        for token in ("regression", "reopen", "publish", "baseline", "conref", "keyref"):
            if token in lab or token in comp:
                area_hits[f"label_or_component:{token}"] += 1

        auto_counts = _automation_area_hits(failure_intelligence)
        for area, n in auto_counts.items():
            area_hits[area] += n
            if n > 0:
                historical.append(
                    {
                        "area": area,
                        "jira_key": None,
                        "title": "automation_failure_correlation",
                        "signals": ["ci_or_allure_payload"],
                        "source": "historical_automation_failures",
                    }
                )

        repeat_count = int(sum(area_hits.values()))
        unstable = [a for a, _ in area_hits.most_common(8) if not str(a).startswith("label_or_component:")]
        label_noise = [a for a in area_hits if str(a).startswith("label_or_component:")]
        if not unstable and label_noise:
            unstable = [str(x).split(":", 1)[-1] for x in label_noise[:6]]

        # Confidence: bounded by evidence diversity
        n_hist = len([h for h in historical if h.get("source") == "historical_jira"])
        n_auto = len([h for h in historical if h.get("source") == "historical_automation_failures"])
        base = 0.12
        base += min(0.45, 0.07 * min(n_hist, 6))
        base += min(0.35, 0.12 * min(n_auto, 4))
        if reopened:
            base += 0.12
        if repeat_count >= 6:
            base += 0.1
        regression_confidence = round(max(0.0, min(1.0, base)), 3)

        return {
            "historical_regressions": historical[:24],
            "repeat_count": repeat_count,
            "highly_unstable_areas": unstable[:10],
            "regression_confidence": regression_confidence,
        }

    def enrich_with_failures(
        self,
        memory: dict[str, Any],
        failure_intelligence: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Merge CI/automation regression signals (call after enterprise failure_intel is available)."""
        if not failure_intelligence:
            return memory
        merged = copy.deepcopy(memory)
        prev = {
            _row_fingerprint(r)
            for r in (merged.get("historical_regressions") or [])
            if isinstance(r, dict)
        }
        extra = RegressionMemoryEngine().analyze(
            labels=[],
            components=[],
            related_hits=[],
            issue_chunks=[],
            jira_key=None,
            failure_intelligence=failure_intelligence,
        )
        for row in extra.get("historical_regressions") or []:
            if not isinstance(row, dict):
                continue
            k = _row_fingerprint(row)
            if k not in prev:
                merged.setdefault("historical_regressions", []).append(row)
                prev.add(k)
        merged["historical_regressions"] = (merged.get("historical_regressions") or [])[:24]
        merged["repeat_count"] = int(memory.get("repeat_count") or 0) + int(extra.get("repeat_count") or 0)
        u_areas = list(dict.fromkeys((memory.get("highly_unstable_areas") or []) + (extra.get("highly_unstable_areas") or [])))
        merged["highly_unstable_areas"] = u_areas[:10]
        rc = max(float(memory.get("regression_confidence") or 0), float(extra.get("regression_confidence") or 0))
        merged["regression_confidence"] = round(min(1.0, rc + 0.05), 3)
        return merged


def _row_fingerprint(row: dict[str, Any]) -> str:
    return "|".join(str((row or {}).get(k) or "") for k in ("area", "source", "title", "jira_key"))


def apply_regression_memory_risk_boost(risk_out: dict[str, Any], regression_memory: dict[str, Any]) -> dict[str, Any]:
    """Elevate QA risk level when regression memory shows strong historical repeats."""
    out = dict(risk_out or {})
    rc = float((regression_memory or {}).get("regression_confidence") or 0)
    rcnt = int((regression_memory or {}).get("repeat_count") or 0)
    if rcnt < 2 and rc < 0.35:
        return out
    areas = list(out.get("risk_areas") or [])
    if not isinstance(areas, list):
        areas = []
    if "historical_regression_memory" not in areas:
        areas.append("historical_regression_memory")
    out["risk_areas"] = areas[:20]

    rl = str(out.get("risk_level") or "medium").lower()
    if rc >= 0.55 or rcnt >= 8:
        out["risk_level"] = "high"
    elif rl == "medium" and rcnt >= 4 and rc >= 0.32:
        out["risk_level"] = "high"
    elif rc >= 0.38 or rcnt >= 4:
        if rl == "low":
            out["risk_level"] = "medium"
    why = str(out.get("why") or "")
    tail = " Corpus shows repeated regression themes in related Jira or CI signals; treat as higher blast radius."
    if tail.strip() not in why and (rc >= 0.35 or rcnt >= 3):
        out["why"] = (why + tail)[:1400]
    conf = float(out.get("confidence") or 0.5)
    out["confidence"] = round(min(1.0, conf + min(0.12, rc * 0.15)), 3)
    return out


def boost_release_readiness_for_regression(
    release: dict[str, Any],
    regression_memory: dict[str, Any],
    *,
    current_risk_level: str,
) -> dict[str, Any]:
    """Increase release_risk tier when repeated regressions exist."""
    rel = dict(release or {})
    rcnt = int((regression_memory or {}).get("repeat_count") or 0)
    rc = float((regression_memory or {}).get("regression_confidence") or 0)
    if rcnt < 3 and rc < 0.4:
        return rel

    cur = str(rel.get("release_risk") or "low").lower()
    target = cur
    if rcnt >= 6 or rc >= 0.5 or str(current_risk_level).lower() == "high":
        target = "high"
    elif rcnt >= 3 or rc >= 0.38:
        if cur == "low":
            target = "medium"
        elif cur == "medium":
            target = "high"

    rel["release_risk"] = target
    weak = list(rel.get("weak_areas") or [])
    if not isinstance(weak, list):
        weak = []
    msg = "Repeated regression memory across related Jira and/or automation history"
    if msg not in weak:
        weak.insert(0, msg)
    rel["weak_areas"] = weak[:12]

    manual = list(rel.get("manual_focus_areas") or [])
    if not isinstance(manual, list):
        manual = []
    hint = "Deep-dive areas flagged by regression memory engine (related tickets + CI)"
    if hint not in manual:
        manual.insert(0, hint)
    rel["manual_focus_areas"] = manual[:10]
    return rel
