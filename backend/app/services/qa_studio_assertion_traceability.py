"""Then-step traceability to Jira observables (no generic assertions, no invented expected outcomes)."""

from __future__ import annotations

import re
from typing import Any, Literal

from app.services.qa_studio_plan_gate import extract_jira_observables

SourceKey = Literal[
    "observed_bug",
    "reproduction_trigger",
    "expected_fixed_behavior",
    "acceptance_criteria",
    "source_quote",
]

SOURCE_KEYS: tuple[SourceKey, ...] = (
    "observed_bug",
    "reproduction_trigger",
    "expected_fixed_behavior",
    "acceptance_criteria",
    "source_quote",
)

# Visual / screenshot-derived Then steps need a labeled snapshot or strong Jira expected/AC mapping.
_THEN_VISUAL_EVIDENCE_RE = re.compile(
    r"(?i)\b("
    r"screenshot|screen[\s-]?grab|snapshot|ui\s+image|pixel\s+match|visual(?:ly)?|"
    r"as\s+shown|figure|image\s+matches|looks\s+like\s+the\s+(?:ui|screen|picture)|"
    r"matches?\s+the\s+(?:screenshot|snapshot|image|fig\.)"
    r")\b"
)

# When a Then cites screenshot/snapshot/visual evidence, token-trivial overlap with expected/AC
# (e.g. one shared word like "editor") must not satisfy traceability without a labeled snapshot.
_MIN_RELEVANCE_FOR_VISUAL_THEN = 0.32

_STOPWORDS = frozenset(
    """
    the and that with from this then when given for are was but not you all can has had
    her was one our out day get use man new now way may say she her per via its any off
    """.split()
)

_GENERIC_THEN_LINE_RES = (
    re.compile(r"^Then\s+it\s+works\.?$", re.I),
    re.compile(r"^Then\s+.*\b(page|ui|screen|feature|workflow)\s+works\b", re.I),
    re.compile(r"^Then\s+.*\b(i\s+)?verify\s+that\s+the\s+(page|ui|screen)\s+works\b", re.I),
    re.compile(r"^Then\s+.*\bverify\s+the\s+page\s+works\b", re.I),
    re.compile(r"^Then\s+.*\b(everything|nothing)\s+(works|is\s+fine|looks\s+good)\b", re.I),
    re.compile(r"^Then\s+.*\bit\s+(works|is\s+fine|looks\s+good)\b", re.I),
    re.compile(r"^Then\s+.*\b(should\s+work|works\s+correctly|behaves\s+correctly)\s*$", re.I),
    re.compile(r"^Then\s+.*\b(assert|confirm)\s+(success|pass|ok)\b", re.I),
    re.compile(r"^Then\s+.*\bno\s+errors?\s*$", re.I),
    re.compile(r"^Then\s+.*\bis\s+successful\s*$", re.I),
    re.compile(r"^Then\s+.*\b(success|done|passed)\s*$", re.I),
    re.compile(r"^Then\s+the\s+UI\s+is\s+(?:ok|fine|good)\s*$", re.I),
)

# Legacy patterns kept in sync with qa_studio_automation_validator generic checks
_LEGACY_GENERIC_RES = (
    re.compile(r"^Then\s+.*\b(should work|is fine|looks good)\b", re.I),
)


def list_generic_then_violations(then_line: str) -> list[str]:
    """Human-readable rejections for vague Then steps."""
    stripped = (then_line or "").strip()
    if not stripped:
        return ["Empty Then step."]
    violations: list[str] = []
    if re.match(r"^Then\b", stripped, re.I):
        for pat in _GENERIC_THEN_LINE_RES:
            if pat.search(stripped):
                violations.append(
                    "Generic Then step rejected — tie each Then to an observable outcome from Jira "
                    "(acceptance criteria, expected behavior, or what changes vs observed bug / repro)."
                )
                break
        for pat in _LEGACY_GENERIC_RES:
            if pat.search(stripped) and not violations:
                violations.append(
                    "Generic Then step rejected — use observable outcomes from Jira AC or expected behavior."
                )
                break
    return violations


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z][a-z0-9]{2,}", (text or "").lower())
        if t not in _STOPWORDS
    }


def _non_empty(s: str | None) -> bool:
    return bool((s or "").strip())


def _truthy(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "y", "on")


UNLABELED_SNAPSHOT_THEN = (
    "Then step references screenshot, snapshot, or visual evidence, but no properly labeled UI snapshot supports it. "
    "Label the snapshot as expected fixed behavior, link it to Jira acceptance criteria, add expected_behavior "
    "metadata, or document that it confirms post-action UI described by Jira/repro — or restate the Then using "
    "verbatim expected/AC wording instead of unlabeled screenshots."
)


def ui_snapshot_supports_assertion(meta: dict[str, Any]) -> bool:
    """
    A snapshot may support an assertion when (and only when) it is explicitly labeled or tied to Jira expected/AC.

    Unsupported: generic screen only, bug-state-only capture, or rows marked rejected/disposition without labels.
    """
    if not isinstance(meta, dict):
        return False
    disp = str(meta.get("disposition") or "").strip().lower()
    if disp == "rejected":
        return False
    if _truthy(meta.get("is_generic_screen")):
        return False
    if _truthy(meta.get("is_bug_state_only")):
        return False

    label = str(meta.get("label") or meta.get("snapshot_role") or "").strip().lower()
    fixed_labels = frozenset(
        {
            "expected_fixed_behavior",
            "expected_outcome",
            "expected",
            "post_action_expected",
            "golden",
            "baseline",
            "ac_reference",
        }
    )
    exp_fixed = _truthy(meta.get("expected_fixed_behavior")) or label in fixed_labels
    linked_ac = _truthy(meta.get("linked_acceptance_criteria")) or _non_empty(
        meta.get("jira_ac_reference") or meta.get("acceptance_criteria_ref")
    )
    exp_beh = _non_empty(meta.get("expected_behavior")) or _non_empty(meta.get("expected_behavior_text"))
    post_action = _truthy(meta.get("confirms_post_action_ui_from_jira")) or _truthy(
        meta.get("confirms_post_action_ui")
    )
    jira_tie = (
        _non_empty(meta.get("jira_key"))
        or _non_empty(meta.get("jira_reference"))
        or _non_empty(meta.get("repro_reference"))
        or _truthy(meta.get("ties_to_jira_context"))
    )

    if exp_fixed or linked_ac or exp_beh:
        return True
    if post_action and jira_tie:
        return True
    return False


def has_qualifying_ui_snapshot(ui_snapshots: list[dict[str, Any]] | None) -> bool:
    if not ui_snapshots:
        return False
    return any(ui_snapshot_supports_assertion(x) for x in ui_snapshots if isinstance(x, dict))


def then_step_mentions_visual_snapshot_evidence(then_line: str) -> bool:
    return bool(_THEN_VISUAL_EVIDENCE_RE.search(then_line or ""))


def snapshot_jira_sources(fields: dict[str, Any]) -> dict[str, str]:
    """Six user-facing Jira fields (strings; may be empty)."""
    return {
        "observed_bug": str(fields.get("observed_bug") or "")[:8000],
        "reproduction_trigger": str(fields.get("reproduction_trigger") or "")[:8000],
        "expected_fixed_behavior": str(fields.get("expected_fixed_behavior") or "")[:8000],
        "acceptance_criteria": str(fields.get("acceptance_criteria") or "")[:8000],
        "source_quote": str(fields.get("source_quote") or "")[:8000],
        "assertion_method": str(fields.get("assertion_method") or "")[:2000],
    }


def observable_expected_configured(fields: dict[str, Any]) -> bool:
    return _non_empty(fields.get("expected_fixed_behavior")) or _non_empty(
        fields.get("acceptance_criteria")
    )


OPEN_QUESTION_NO_OBSERVABLE = (
    "What concrete, observable outcome (expected behavior or acceptance criteria) proves this Jira is fixed? "
    "Add that to Jira or the form before writing Then steps — do not invent assertions."
)


def merge_user_and_jira_fields(
    *,
    jira_summary: str,
    jira_description: str,
    jira_raw: str,
    repro_steps: str,
    expected_behavior: str,
    acceptance_criteria: str,
) -> dict[str, Any]:
    """Same merge rules as planning gate (form overrides extracted Jira body)."""
    summary = (jira_summary or "").strip()
    desc = (jira_description or "").strip()
    raw = (jira_raw or "").strip()
    if raw:
        blob = raw
        if not summary:
            summary = blob[:500]
        if not desc:
            desc = blob
    extracted = extract_jira_observables(summary, desc)
    exp = (expected_behavior or "").strip() or extracted["expected_fixed_behavior"]
    ac = (acceptance_criteria or "").strip() or extracted["acceptance_criteria"]
    repro = (repro_steps or "").strip() or extracted["reproduction_trigger"]

    out = {
        **extracted,
        "expected_fixed_behavior": exp or extracted["expected_fixed_behavior"],
        "acceptance_criteria": ac or extracted["acceptance_criteria"],
        "reproduction_trigger": repro or extracted["reproduction_trigger"],
    }
    if (out["expected_fixed_behavior"] or out["acceptance_criteria"]) and not out.get("source_quote"):
        quote_src = out["acceptance_criteria"] or out["expected_fixed_behavior"]
        out["source_quote"] = quote_src[:2000]
    if not out.get("assertion_method"):
        if out["expected_fixed_behavior"] or out["acceptance_criteria"]:
            out["assertion_method"] = "Trace Then assertions to Jira expected/AC quote."
        elif out["observed_bug"]:
            out["assertion_method"] = (
                "Prefer expected/AC as primary source; if only Actual is given, "
                "Then steps must state measurable absence of those symptoms or cite agreed expected text once added."
            )
    return out


def extract_then_lines_from_feature(feature_text: str) -> list[str]:
    out: list[str] = []
    for line in (feature_text or "").splitlines():
        s = line.strip()
        if re.match(r"^Then\b", s, re.I):
            out.append(s)
    return out


def _best_then_source(then_text: str, sources: dict[str, str]) -> tuple[SourceKey | None, float, str]:
    """Pick best Jira field that the Then text can cite (heuristic overlap)."""
    body_then = re.sub(r"^Then\s+", "", then_text.strip(), flags=re.I).strip()
    tt = _tokens(body_then)
    if not tt:
        return None, 0.0, "Then step has no substantive text to align with Jira."

    best_key: SourceKey | None = None
    best_score = 0.0

    for key in SOURCE_KEYS:
        blob = (sources.get(key) or "").strip()
        if not blob:
            continue
        st = _tokens(blob)
        if not st:
            continue
        inter = len(tt & st)
        union = len(tt | st) or 1
        jaccard = inter / union
        low_then = body_then.lower()
        bonus = 0.0
        for phrase in re.split(r"[.\n;]+", blob[:1500]):
            p = phrase.strip().lower()
            if len(p) > 12 and p in low_then:
                bonus = 0.35
                break
            if len(p) > 12 and p[:50] in low_then:
                bonus = 0.2
                break
        score = min(1.0, jaccard + bonus)
        if score > best_score:
            best_score = score
            best_key = key

    if best_key is None:
        return None, 0.0, "No non-empty Jira source field overlaps this Then step."

    reason = (
        f"Then text best aligns with Jira field `{best_key}` "
        f"(token overlap / quoted fragment heuristic, score {best_score:.2f})."
    )
    return best_key, best_score, reason


def build_traceability_report(
    *,
    fields: dict[str, Any],
    then_steps: list[str],
    ui_snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Validate that each Then maps to a Jira observable source; reject generic Then lines.
    When expected/AC is missing, do not attempt mapping — return open question only.

    UI snapshots may supplement traceability only when ``ui_snapshot_supports_assertion`` holds
    for at least one row in ``ui_snapshots``. Otherwise, Then steps that cite screenshot/snapshot
    language must map strongly to expected/AC/source_quote.
    """
    sources = snapshot_jira_sources(fields)
    errors: list[str] = []
    blocked = not observable_expected_configured(fields)
    open_questions: list[str] = []
    if blocked:
        open_questions.append(OPEN_QUESTION_NO_OBSERVABLE)

    snap_qualifying = has_qualifying_ui_snapshot(ui_snapshots)

    if not then_steps:
        return {
            "ok": True,
            "blocked_no_observable_expected": blocked,
            "open_questions": open_questions if blocked else [],
            "jira_sources": sources,
            "then_step_results": [],
            "errors": [],
            "ui_snapshot_qualifying_count": sum(
                1 for x in (ui_snapshots or []) if isinstance(x, dict) and ui_snapshot_supports_assertion(x)
            ),
        }

    results: list[dict[str, Any]] = []

    if blocked:
        for raw in then_steps:
            gen = list_generic_then_violations(raw)
            if gen:
                errors.extend(gen)
            results.append(
                {
                    "then_text": raw,
                    "ok": False,
                    "skipped_mapping": True,
                    "generic_violations": gen,
                    "mapped_source": None,
                    "relevance": 0.0,
                    "reason": "Traceability mapping skipped — add observable expected behavior or AC first.",
                }
            )
        return {
            "ok": len(errors) == 0 and len(then_steps) == 0,
            "blocked_no_observable_expected": True,
            "open_questions": open_questions,
            "jira_sources": sources,
            "then_step_results": results,
            "errors": errors + ([OPEN_QUESTION_NO_OBSERVABLE] if then_steps else []),
            "ui_snapshot_qualifying_count": sum(
                1 for x in (ui_snapshots or []) if isinstance(x, dict) and ui_snapshot_supports_assertion(x)
            ),
        }

    min_relevance = 0.06
    all_ok = True
    for raw in then_steps:
        gen = list_generic_then_violations(raw)
        if gen:
            errors.extend(gen)
            all_ok = False
            results.append(
                {
                    "then_text": raw,
                    "ok": False,
                    "skipped_mapping": False,
                    "generic_violations": gen,
                    "mapped_source": None,
                    "relevance": 0.0,
                    "reason": gen[0] if gen else "Invalid Then step.",
                    "visual_evidence_without_labeled_snapshot": False,
                }
            )
            continue

        src_key, rel, why = _best_then_source(raw, sources)
        vis = then_step_mentions_visual_snapshot_evidence(raw)

        strong_jira_base = src_key is not None and rel >= min_relevance and src_key in (
            "expected_fixed_behavior",
            "acceptance_criteria",
            "source_quote",
        )
        strong_jira = strong_jira_base and (
            not vis or rel >= _MIN_RELEVANCE_FOR_VISUAL_THEN
        )

        if src_key is None or rel < min_relevance:
            if vis and snap_qualifying:
                excerpt = ""
                for row in ui_snapshots or []:
                    if isinstance(row, dict) and ui_snapshot_supports_assertion(row):
                        excerpt = str(
                            row.get("expected_behavior")
                            or row.get("expected_behavior_text")
                            or row.get("reason")
                            or row.get("title")
                            or ""
                        )[:400]
                        break
                results.append(
                    {
                        "then_text": raw,
                        "ok": True,
                        "skipped_mapping": False,
                        "generic_violations": [],
                        "mapped_source": "labeled_ui_snapshot",
                        "relevance": round(rel, 3),
                        "reason": (
                            "Then references visual evidence; a properly labeled UI snapshot satisfies traceability "
                            f"({why})."
                        ),
                        "source_excerpt": excerpt,
                        "visual_evidence_without_labeled_snapshot": False,
                    }
                )
                continue
            msg = (
                f"Then step must reference an observable outcome from Jira "
                f"(acceptance_criteria, expected_fixed_behavior, source_quote, observed_bug, or reproduction_trigger). "
                f"Increase specificity or quote Jira text: {raw[:120]}"
            )
            errors.append(msg)
            all_ok = False
            results.append(
                {
                    "then_text": raw,
                    "ok": False,
                    "skipped_mapping": False,
                    "generic_violations": [],
                    "mapped_source": src_key,
                    "relevance": round(rel, 3),
                    "reason": why if rel > 0 else msg,
                    "visual_evidence_without_labeled_snapshot": bool(vis) and not snap_qualifying,
                }
            )
        elif vis and not strong_jira and not snap_qualifying:
            errors.append(UNLABELED_SNAPSHOT_THEN)
            all_ok = False
            results.append(
                {
                    "then_text": raw,
                    "ok": False,
                    "skipped_mapping": False,
                    "generic_violations": [],
                    "mapped_source": src_key,
                    "relevance": round(rel, 3),
                    "reason": UNLABELED_SNAPSHOT_THEN,
                    "source_excerpt": (sources.get(src_key) or "")[:400] if src_key else "",
                    "visual_evidence_without_labeled_snapshot": True,
                }
            )
        else:
            results.append(
                {
                    "then_text": raw,
                    "ok": True,
                    "skipped_mapping": False,
                    "generic_violations": [],
                    "mapped_source": src_key,
                    "relevance": round(rel, 3),
                    "reason": why,
                    "source_excerpt": (sources.get(src_key) or "")[:400],
                    "visual_evidence_without_labeled_snapshot": False,
                }
            )

    return {
        "ok": all_ok,
        "blocked_no_observable_expected": False,
        "open_questions": open_questions,
        "jira_sources": sources,
        "then_step_results": results,
        "errors": errors,
        "ui_snapshot_qualifying_count": sum(
            1 for x in (ui_snapshots or []) if isinstance(x, dict) and ui_snapshot_supports_assertion(x)
        ),
    }


def traceability_errors_for_feature_and_fields(
    feature_text: str,
    fields: dict[str, Any],
    ui_snapshots: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Flat error list for automation validator."""
    thens = extract_then_lines_from_feature(feature_text)
    if not thens:
        return []
    report = build_traceability_report(fields=fields, then_steps=thens, ui_snapshots=ui_snapshots)
    return list(report.get("errors") or [])
