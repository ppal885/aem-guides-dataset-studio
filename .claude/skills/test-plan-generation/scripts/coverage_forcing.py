"""Signal-activated, fail-closed coverage forcing.

WHY THIS EXISTS
---------------
The skill already owns rich coverage machinery (performance_contract,
ui_surface_scope, ac_decidability, disposition_classifier). But every one of
those gates is OPT-IN: it validates a block only once the manifest DECLARES it.
So when a plan is authored by hand and simply never declares a
``performance_assessment`` block or a ``ui_surface_scope`` block, the gate stays
dormant and the dimension is silently missed - the recurring failure where a
reviewer has to add the performance AC and the UI-surface ACs after the fact.

This gate closes that hole. It is PROACTIVE and FAIL-CLOSED: it reads the ticket
signals present in the plan text (and manifest) and, when a signal demands a
dimension, it REQUIRES that dimension to be dispositioned - covered in an AC,
raised as an Open Question, or explicitly opted out with a concrete reason -
before the plan can pass. It does not author anything; it forces a decision.

Three independent, conservatively-activated checks:

  1. PERFORMANCE - a scale / timeout / resource signal in the plan requires a
     performance disposition (a Performance AC, a performance_assessment block
     with decision required|conditional, or opt-out ``performance_not_applicable``).
  2. UI SURFACE - naming a cataloged UI feature (data/ui_feature_surface_catalog.json)
     requires each of that feature's surfaces to be addressed in the plan, or
     dispositioned, or opted out with ``ui_surface_coverage_not_applicable``.
  3. INVESTIGATION-AS-AC - an Acceptance Criterion phrased as an investigation
     task ("confirm whether ...", "check if ... shipped") is not a sign-off
     criterion; it must move to Open Questions.

Every check has a global opt-out escape so a genuinely-inapplicable signal never
hard-blocks a correct plan. Generic only. Standard library only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name("data") / "ui_feature_surface_catalog.json"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _acceptance_block(plan_text: str) -> str:
    if not plan_text:
        return ""
    m = re.search(r"\*\*Acceptance Criteria\*\*(.*?)(?:\n\*\*|\Z)", plan_text, re.S)
    return m.group(1) if m else plan_text


def _ac_lines(plan_text: str) -> list[str]:
    lines = []
    for raw in _acceptance_block(plan_text).splitlines():
        s = raw.strip()
        if s.startswith(("-", "*")) or re.match(r"^AC[-\s]?\d", s, re.I):
            lines.append(s)
    return lines


def _opt_out_reason(manifest, key: str) -> str:
    if not isinstance(manifest, dict):
        return ""
    val = manifest.get(key)
    if isinstance(val, dict):
        return str(val.get("reason", "")).strip()
    if isinstance(val, str):
        return val.strip()
    return ""


# ---------------------------------------------------------------------------
# 1. Performance forcing
# ---------------------------------------------------------------------------

# Signals that a change concerns scale / responsiveness / resource use. Kept
# specific so ordinary functional tickets are not swept in.
PERF_SIGNAL_TERMS = (
    "503", "service unavailable", "timeout", "timed out", "time out",
    "out of memory", "oom", "hangs", "hang ", "spinner never",
    "large map", "large file", "large dataset", "big map",
    "performance", "scalab", "slow", "latency", "throughput",
    "too long", "does not respond", "unresponsive", "gateway",
)
# A quantified-workload hint strengthens the signal but is not required.
_PERF_SCALE_RE = re.compile(
    r"\b(\d{2,}[\d,]*)\s*(topics?|topicrefs?|files?|maps?|assets?|nodes?|rows?|entries|users?)\b",
    re.I,
)


def _has_perf_signal(plan_text: str) -> bool:
    low = (plan_text or "").lower()
    if any(term in low for term in PERF_SIGNAL_TERMS):
        return True
    return bool(_PERF_SCALE_RE.search(plan_text or ""))


def _has_performance_disposition(manifest, plan_text: str) -> bool:
    # (a) a Performance AC or Performance section in the plan
    low = (plan_text or "").lower()
    if re.search(r"performance", low) and re.search(r"\bac[-\s]?\d", low):
        # a Performance AC line exists
        for line in _ac_lines(plan_text):
            if "perform" in line.lower() or "within" in line.lower() and "timeout" in low:
                return True
    if re.search(r"\*\*performance", low):  # a dedicated Performance section
        return True
    # (b) a declared performance_assessment with an active decision
    if isinstance(manifest, dict):
        pa = manifest.get("performance_assessment")
        if isinstance(pa, dict) and str(pa.get("decision", "")).strip() in ("required", "conditional"):
            return True
    return False


def _validate_performance(manifest, plan_text: str) -> list[str]:
    if not _has_perf_signal(plan_text):
        return []
    if len(_opt_out_reason(manifest, "performance_not_applicable")) >= 12:
        return []
    if _has_performance_disposition(manifest, plan_text):
        return []
    return [
        "A scale / timeout / resource signal is present but performance is not "
        "dispositioned. Add a Performance AC (bind it to the enforced platform "
        "limit whose breach causes the failure; defer any numeric SLA to Open "
        "Questions), or declare a performance_assessment block with decision "
        "required|conditional, or set performance_not_applicable with a concrete reason."
    ]


# ---------------------------------------------------------------------------
# 2. UI surface forcing
# ---------------------------------------------------------------------------

def _load_feature_catalog(path=None):
    p = Path(path) if path is not None else CATALOG_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _feature_named(plan_text: str, entry: dict) -> bool:
    low = (plan_text or "").lower()
    names = [entry.get("label", "")] + list(entry.get("aliases", []))
    return any(n and n.lower() in low for n in names)


def _surface_addressed(plan_text: str, surface: dict) -> bool:
    low = (plan_text or "").lower()
    return any(term and term.lower() in low for term in surface.get("terms", []))


def _ui_dispositioned(manifest, feature_slug: str, surface_id: str) -> bool:
    if not isinstance(manifest, dict):
        return False
    cov = manifest.get("ui_surface_coverage")
    if not isinstance(cov, dict):
        return False
    feat = cov.get(feature_slug)
    if not isinstance(feat, dict):
        return False
    entry = feat.get(surface_id)
    if isinstance(entry, dict):
        return len(str(entry.get("reason", "")).strip()) >= 8 and bool(str(entry.get("disposition", "")).strip())
    return False


def _validate_ui_surface(manifest, plan_text: str, catalog_path=None) -> list[str]:
    catalog = _load_feature_catalog(catalog_path)
    if not catalog:
        return []
    if len(_opt_out_reason(manifest, "ui_surface_coverage_not_applicable")) >= 12:
        return []
    problems: list[str] = []
    for slug, entry in catalog.items():
        if not isinstance(entry, dict) or not _feature_named(plan_text, entry):
            continue
        for surface in entry.get("surfaces", []):
            sid = surface.get("id", "")
            if _surface_addressed(plan_text, surface):
                continue
            if _ui_dispositioned(manifest, slug, sid):
                continue
            problems.append(
                f"UI feature {entry.get('label', slug)!r}: surface "
                f"{surface.get('label', sid)!r} is not addressed. Cover it in an AC, "
                f"raise it as an Open Question, or disposition it in "
                f"ui_surface_coverage.{slug}.{sid} with a reason "
                f"(or set ui_surface_coverage_not_applicable for the whole feature)."
            )
    return problems


# ---------------------------------------------------------------------------
# 3. Investigation-as-AC
# ---------------------------------------------------------------------------

INVESTIGATION_RES = (
    re.compile(r"\bconfirm whether\b", re.I),
    re.compile(r"\b(check|verify|determine|establish)\s+(whether|if)\b", re.I),
    re.compile(r"\bfind out\b", re.I),
    re.compile(r"\binvestigate\b", re.I),
    re.compile(r"\bis (?:the |a )?(?:prior |previous )?fix (?:present|included|shipped)\b", re.I),
    re.compile(r"\b(did|whether)\b.*\b(ship|shipped|reach(?:ed)? this build|land(?:ed)?)\b", re.I),
    re.compile(r"\bresolve[d]? the .*claim\b", re.I),
)


def _validate_investigation(manifest, plan_text: str) -> list[str]:
    problems: list[str] = []
    for line in _ac_lines(plan_text):
        for rx in INVESTIGATION_RES:
            if rx.search(line):
                snippet = line[:80]
                problems.append(
                    "An Acceptance Criterion is phrased as an investigation task, not a "
                    f"decidable sign-off criterion: {snippet!r}. Move it to Open Questions."
                )
                break
    return problems


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 4. No code identifiers in acceptance criteria (plain-English rule)
# ---------------------------------------------------------------------------
# An AC must read as plain QE English: no method/class/function/file identifiers.
# High-confidence code shapes only, so ordinary prose and legitimate product
# config keys (snake_case / dotted like postprocess.temporary.langcopies) are not
# flagged. Trace the code in the background; state the observable behaviour in the AC.
_CODE_CLASS_METHOD_RE = re.compile(r"\b[A-Z][A-Za-z0-9]+\.[a-z][A-Za-z0-9_]+")   # PublishWorkflowStep.handlePartialPublish
_CODE_CAMEL_RE = re.compile(r"\b[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*\b")              # handlePartialPublish, filterListTopics
_CODE_PASCAL_RE = re.compile(r"\b(?:[A-Z][a-z0-9]+){3,}\b")                       # PublishWorkflowStep (3+ humps)
_CODE_FILE_RE = re.compile(r"\b[\w/]+\.(?:java|py|js|ts|tsx|jsx|xsl|xslt)\b", re.I)
_CODE_FILELINE_RE = re.compile(r"\b[\w./-]+:\d+\b")
# camelCase/Pascal tokens that are real product/brand terms, not code identifiers.
_CODE_ALLOWLIST = {
    "aemaacs", "javascript", "typescript", "github", "gitlab", "powershell",
    "nodejs", "jira", "devops", "ios", "macos", "openapi", "mathml", "svg",
}


def _validate_plain_language(plan_text: str) -> list[str]:
    problems: list[str] = []
    for line in _ac_lines(plan_text):
        hits: list[str] = []
        for rx in (_CODE_CLASS_METHOD_RE, _CODE_CAMEL_RE, _CODE_PASCAL_RE,
                   _CODE_FILE_RE, _CODE_FILELINE_RE):
            for m in rx.findall(line):
                tok = m if isinstance(m, str) else m[0]
                if tok.casefold() in _CODE_ALLOWLIST:
                    continue
                hits.append(tok)
        if hits:
            problems.append(
                "An Acceptance Criterion contains code identifiers "
                f"({', '.join(sorted(set(hits))[:4])}); ACs must be plain QE-readable "
                "English. Trace the code in the background, then state the observable "
                f"behaviour instead: {line[:70]!r}"
            )
    return problems


def validate(manifest, plan_text: str = "", *, catalog_path=None) -> list[str]:
    problems: list[str] = []
    problems += _validate_performance(manifest, plan_text)
    problems += _validate_ui_surface(manifest, plan_text, catalog_path=catalog_path)
    problems += _validate_investigation(manifest, plan_text)
    problems += _validate_plain_language(plan_text)
    return problems


def summarize(manifest, plan_text: str = "") -> str:
    problems = validate(manifest, plan_text)
    lines = [f"CoverageForcing: {'CLEAN' if not problems else 'ISSUES'}"]
    lines.extend(f"  {p}" for p in problems)
    return "\n".join(lines)


def run_self_tests() -> None:
    nl = chr(10)

    # --- performance forcing ---
    perf_missing = nl.join([
        "**Understanding**", "Find returns HTTP 503 on large maps.",
        "**Acceptance Criteria**", "- AC-01: results are returned.", ""])
    probs = validate({}, perf_missing)
    assert any("performance is not dispositioned" in p for p in probs), "503/large-map must force performance"

    perf_ac = nl.join([
        "**Understanding**", "Find returns HTTP 503 on large maps.",
        "**Acceptance Criteria**",
        "- AC-05: Find completes within the platform timeout budget so no 503 is returned (Performance).",
        ""])
    assert not any("performance is not dispositioned" in p for p in validate({}, perf_ac)), "Performance AC satisfies"

    assert not any("performance" in p for p in validate(
        {"performance_not_applicable": {"reason": "Pure static-label change, no workload dimension."}}, perf_missing)), "perf opt-out"

    plain = nl.join(["**Acceptance Criteria**", "- AC-01: the dialog opens on click.", ""])
    assert validate({}, plain) == [], "no signals -> no forcing"

    # --- ui surface forcing (uses the shipped catalog: find-and-replace) ---
    fr_missing = nl.join([
        "**Understanding**", "Find and Replace throws 503 on large maps.",
        "**Acceptance Criteria**",
        "- AC-05: search completes within the platform timeout budget (Performance).",
        ""])
    fr_probs = validate({}, fr_missing)
    assert any("Filters" in p or "filter" in p.lower() for p in fr_probs), "F&R filters surface must be forced"

    fr_covered = nl.join([
        "**Understanding**", "Find and Replace throws 503 on large maps.",
        "**Acceptance Criteria**",
        "- AC-05: search completes within the platform timeout budget (Performance).",
        "- AC-07: the Filters dialog (File Type, Document State, Last Modified) narrows results without a 503.",
        "- AC-08: Path scope and Use source mode work on a large map.",
        "- AC-09: Replace occurrence and Replace all complete via the async job.",
        "- AC-10: Replace settings (Replace unlocked files, Create new version, Version comments) are honored.",
        "- AC-11: the Enable Replace All workspace setting gates the feature.",
        ""])
    assert _validate_ui_surface({}, fr_covered) == [], f"all F&R surfaces covered must pass: {_validate_ui_surface({}, fr_covered)}"

    assert _validate_ui_surface(
        {"ui_surface_coverage_not_applicable": {"reason": "Backend-only change with no F&R panel behaviour."}},
        fr_missing) == [], "ui opt-out"

    # --- investigation-as-AC ---
    inv = nl.join([
        "**Acceptance Criteria**",
        "- AC-09: Confirm whether the 2026.08 fix is present in this build.",
        ""])
    assert any("investigation task" in p for p in validate({}, inv)), "investigation AC must fail"

    # --- no code identifiers in ACs (the GUIDES-52444 failure) ---
    codey = nl.join([
        "**Acceptance Criteria**",
        "- AC-03: The fix is applied in both PublishWorkflowStep.handlePartialPublish and "
        "PublishWorkflowGenerationAEMSiteRenditionStep.handlePartialPublish so filterListTopics does not drop the topic.",
        ""])
    assert any("code identifiers" in p for p in validate({}, codey)), "method names in AC must fail"
    # Plain-English AC with legitimate product/config terms must PASS.
    clean_ac = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: Incremental publish of a selected topic with a no-baseline AEM Site preset completes and produces output.",
        "- AC-02: The result is the same whether Enable DITA-OT Processing is on or off.",
        "- AC-03: Verified on AEMaaCS and on-premise 6.5.1 LTS.",
        "- AC-04: The config property postprocess.temporary.langcopies set to false does not change the outcome.",
        ""])
    assert _validate_plain_language(clean_ac) == [], f"plain-English AC must pass: {_validate_plain_language(clean_ac)}"

    print("coverage_forcing self-tests: PASS")


if __name__ == "__main__":
    run_self_tests()
