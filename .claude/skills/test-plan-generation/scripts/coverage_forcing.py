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

Representative conservatively-activated checks include:

  1. PERFORMANCE - a scale / timeout / resource signal in the plan requires a
     performance disposition (a Performance AC, a performance_assessment block
     with decision required|conditional, or opt-out ``performance_not_applicable``).
  2. UI SURFACE - naming a cataloged UI feature (data/ui_feature_surface_catalog.json)
     requires each of that feature's surfaces to be addressed in the plan, or
     dispositioned, or opted out with ``ui_surface_coverage_not_applicable``.
  3. INVESTIGATION-AS-AC - an Acceptance Criterion phrased as an investigation
     task ("confirm whether ...", "check if ... shipped") is not a sign-off
     criterion; it must move to Open Questions.
  4. AC REDUNDANCY - near-duplicate ACs must be merged into one product outcome.
  5. CONTRACT PRESENCE - a behavioral plan must contain at least one AC.
  6. HISTORY ATTEMPT - declared history work must record its search outcome.

Signal-specific opt-outs remain available where documented. A non-behavioral plan
skips contract presence only when behaviour_matters is explicitly false. Generic
only. Standard library only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name("data") / "ui_feature_surface_catalog.json"

# Keep these mechanical thresholds aligned with scripts/uac_eval/precision.py.
OVER_DECOMPOSITION_MAX = 12
REDUNDANCY_JACCARD = 0.6

_AC_LABEL_RE = re.compile(r"\bAC[-\s]?(\d+)\b", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*\S)\s*$")
_AC_REDUNDANCY_STOP_WORDS = frozenset(
    "the a an and or of to in on for is are be that this it with as by from at "
    "should must will shall verify ensure when then given user should_be able "
    "not no if into their its each any all both which while".split()
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _extract_ac_block(plan_text: str) -> tuple[str, bool]:
    """Return only the acceptance-contract section and whether it was found.

    This intentionally mirrors scripts/uac_eval/precision.py. Missing sections do
    not fall back to the whole plan because unrelated bullets and AC references are
    not acceptance criteria.
    """
    if not plan_text:
        return "", False
    match = re.search(
        r"(?:^|\n)\s*(?:#{1,4}\s*|\*\*)\s*"
        r"(?:Proposed acceptance contract|Acceptance contract|Acceptance criteria)\b.*?"
        r"(?=\n\s*(?:#{1,4}\s*|\*\*)\s*[A-Z][A-Za-z /]{2,40}\b|\Z)",
        plan_text,
        re.S | re.I,
    )
    if match:
        return match.group(0).strip(), True
    return "", False


def _ac_items(block: str) -> list[str]:
    """Return one single-line item per AC, preferring explicit AC labels."""
    labelled: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if line and _AC_LABEL_RE.search(line):
            labelled.append(line)
    if labelled:
        return labelled

    items: list[str] = []
    for raw in block.splitlines():
        match = _BULLET_RE.match(raw)
        if match:
            items.append(match.group(1).strip())
    return items


def _content_words(text: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_.]+", text.lower())
    return {
        token
        for token in tokens
        if token not in _AC_REDUNDANCY_STOP_WORDS and len(token) > 2
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _plain_ac_text(text: str) -> str:
    """Make an offending AC safe to show in a plain-text gate reason."""
    cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", text.strip())
    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", cleaned)
    cleaned = cleaned.translate(str.maketrans("", "", "`*_~[]<>"))
    return " ".join(cleaned.split())


def _acceptance_block(plan_text: str) -> str:
    block, found = _extract_ac_block(plan_text)
    return block if found else ""


def _ac_lines(plan_text: str) -> list[str]:
    return _ac_items(_acceptance_block(plan_text))


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
    # duration / concurrency / bulk-load signals (a long-running or concurrent job is a
    # performance factor even when nothing 503s - missed on a false-failure output ticket
    # where generation ran minutes and overlapping jobs collided).
    "minutes later", "still running", "already running", "in progress",
    "overlap", "concurrent", "concurrenc", "simultaneous", "parallel",
    "bulk publish", "bulk generation", "queue", "backlog", "long-running",
    "long running",
)
# A cited duration such as "5-10 minutes", "300 s", "11 minutes".
_PERF_DURATION_RE = re.compile(
    r"\b\d+\s*(?:-\s*\d+\s*)?(?:sec|secs|second|seconds|s|min|mins|minute|minutes|hour|hours)\b",
    re.IGNORECASE,
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
    if _PERF_SCALE_RE.search(plan_text or ""):
        return True
    return bool(_PERF_DURATION_RE.search(plan_text or ""))


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
    # (c) a performance-conditional Open Question (the correct disposition when a workload
    # is cited but no approved SLA exists - conditional, not a faked numeric AC).
    for line in plan_text.splitlines() if plan_text else []:
        if re.search(r"\bOQ[-\s]?\d", line, re.I) and re.search(
            r"\b(?:performance|sla|workload|throughput|latency|duration|scale|"
            r"concurrent|baseline|response\s+time)\b", line, re.I):
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


# An added/unit/automation/regression test passing or covering something is Automation
# Coverage EVIDENCE, never an acceptance criterion (non-negotiable). Flag the shape in AC
# lines. Scans only AC bullets, so a separate "Automation Coverage" verdict line is fine.
_TEST_AS_AC_RES = (
    re.compile(r"\b(?:added|unit|automation|new|regression|integration)\b[\w\s,'-]{0,30}\btests?\b", re.I),
    re.compile(r"\btests?\b[\w\s,'-]{0,30}\b(?:pass(?:es|ing)?|is green|are green|covers?|added)\b", re.I),
    re.compile(r"\b[\w/.-]+\.test\.(?:ts|js|py|java)\b|\btest\.(?:ts|js|py)\b", re.I),
    re.compile(r"\bautomation\s+(?:pr|test|suite)\b", re.I),
)


def _oq_lines(plan_text: str) -> list[str]:
    m = re.search(r"\*\*Open Questions\*\*(.*?)(?:\n\*\*|\Z)", plan_text or "", re.S)
    block = m.group(1) if m else ""
    lines = []
    for raw in block.splitlines():
        s = raw.strip()
        if s.startswith(("-", "*")) or re.match(r"^OQ[-\s]?\d", s, re.I):
            lines.append(s)
    return lines


# Only an OQ that cites an AC as its ANSWER/authority ("per AC-7", "see AC-7", "as
# decided in AC-7") contradicts a decided AC. An OQ that references an AC as the thing it
# BOUNDS/completes ("so AC-3 is testable") is a legitimate scope question, not a contradiction.
_AC_ANSWER_REF_RE = re.compile(
    r"\b(?:per|see|as (?:per|decided|stated|in)|answered by|already (?:in|decided in|covered by))\s+AC[-\s]?\d+\b",
    re.I,
)
_RESTATED_INSTANCE_RE = re.compile(
    r"\bthe (?:exact|specific|reported|above) (?:reported )?(?:case|scenario|example|bug)\b"
    r".{0,40}\b(?:pass(?:es)?|is fixed|works|resolves)\b",
    re.I,
)


def _validate_ac_oq_contradiction(manifest, plan_text: str) -> list[str]:
    # An Open Question that cites an AC is confirming something an AC already decides -
    # a decided AC and an open question about the same thing contradict. Decide it in the
    # AC or make it an OQ, not both (for example OQ-1 "per AC-7" vs AC-7).
    problems: list[str] = []
    for line in _oq_lines(plan_text):
        m = _AC_ANSWER_REF_RE.search(line)
        if m:
            ref = m.group(0)
            problems.append(
                f"An Open Question references {ref} ({line[:70]!r}). If that AC already "
                "decides the behaviour, the Open Question is redundant/contradictory - keep "
                "it decided in the AC and remove the OQ, or make it a genuine OQ and drop "
                "the AC's assertion."
            )
    return problems


def _validate_restated_instance_ac(manifest, plan_text: str) -> list[str]:
    # An AC phrased as "the exact reported case passes" usually just restates the specific
    # instance of a general behavioural AC - fold the example into the general AC instead.
    problems: list[str] = []
    for line in _ac_lines(plan_text):
        if _RESTATED_INSTANCE_RE.search(line):
            problems.append(
                f"An Acceptance Criterion restates the specific reported instance "
                f"({line[:70]!r}). Fold the concrete example into the general behavioural AC "
                "rather than keeping a separate 'the reported case passes' AC."
            )
    return problems


_XML_TAG_RE = re.compile(r"<[a-zA-Z][\w:-]*(?:\s|>|/)")


def _validate_no_markup_in_ac(manifest, plan_text: str) -> list[str]:
    # ACs are plain QE English: no code fences and no raw XML/DITA markup. Describe the
    # condition in words ("a key definition with a blank keys attribute"), not <keydef keys="">.
    block = _acceptance_block(plan_text)
    problems: list[str] = []
    if "```" in block:
        problems.append(
            "The Acceptance Criteria contain a code block (```). ACs must be plain English "
            "- describe the condition in words, not embedded markup or code."
        )
    m = _XML_TAG_RE.search(block)
    if m:
        problems.append(
            f"The Acceptance Criteria contain raw markup/XML ({block[m.start():m.start()+24]!r}). "
            "Describe it in plain English (e.g. 'a key definition with a blank keys attribute'), "
            "not literal tags."
        )
    return problems


def _validate_ac_over_decomposition(manifest, plan_text: str) -> list[str]:
    # One behaviour split into a separate AC per micro-variation (blank vs missing, per
    # surface, per edit transition, per structure) produces a bloated, unreadable UAC. A
    # high AC count is a strong over-decomposition signal; generalize into fewer ACs.
    nums = set(re.findall(r"\bAC[-\s]?(\d+)\b", _acceptance_block(plan_text), re.I))
    if len(nums) > OVER_DECOMPOSITION_MAX:
        return [
            f"{len(nums)} acceptance criteria - this is over-decomposed. Generalize "
            "micro-variations (blank vs missing, per surface, per edit transition, per "
            "structure) into fewer behavioural ACs; prefer the fewest ACs that cover the "
            "behaviour, with examples inside an AC rather than a new AC per case. Move "
            "path-divergence or surface-relevance uncertainties to Open Questions."
        ]
    return []


def _validate_no_test_as_ac(manifest, plan_text: str) -> list[str]:
    problems: list[str] = []
    for line in _ac_lines(plan_text):
        if any(rx.search(line) for rx in _TEST_AS_AC_RES):
            problems.append(
                "An Acceptance Criterion asserts that a test/automation passes or covers "
                f"something: {line[:80]!r}. A test is Automation Coverage evidence, never an "
                "AC (non-negotiable). State the observable product behaviour as the AC and "
                "record the test in an Automation Coverage line."
            )
    return problems


# ---------------------------------------------------------------------------
# 4. Mechanical acceptance-contract and history checks
# ---------------------------------------------------------------------------

def _ac_item_name(item: str, index: int) -> str:
    match = _AC_LABEL_RE.search(item)
    if match:
        return f"AC-{int(match.group(1)):02d}"
    return f"acceptance item {index}"


def _validate_ac_redundancy(combined: str) -> list[str]:
    """Fail when two acceptance items are lexical near-duplicates."""
    block, found = _extract_ac_block(combined)
    if not found:
        return []
    items = _ac_items(block)
    word_sets = [_content_words(item) for item in items]
    problems: list[str] = []
    for left_index, left in enumerate(items):
        for right_index in range(left_index + 1, len(items)):
            similarity = _jaccard(word_sets[left_index], word_sets[right_index])
            if similarity < REDUNDANCY_JACCARD:
                continue
            right = items[right_index]
            left_name = _ac_item_name(left, left_index + 1)
            right_name = _ac_item_name(right, right_index + 1)
            problems.append(
                f"{left_name} and {right_name} are near-duplicate acceptance criteria "
                f"(content-word overlap {similarity:.2f}; limit {REDUNDANCY_JACCARD:.2f}). "
                f"Merge them into one product outcome. {left_name} text: "
                f"{_plain_ac_text(left)}. {right_name} text: {_plain_ac_text(right)}."
            )
    return problems


def _validate_acceptance_contract_present(combined: str, manifest) -> list[str]:
    """Require a non-empty acceptance contract for behavioral plans."""
    if isinstance(manifest, dict) and manifest.get("behaviour_matters") is False:
        return []
    block, found = _extract_ac_block(combined)
    if not found:
        return [
            "This behavioral plan has no Acceptance contract or Acceptance criteria "
            "section. Add the product acceptance contract, or explicitly set "
            "behaviour_matters to false for a genuinely non-behavioral change."
        ]
    if not _ac_items(block):
        return [
            "The Acceptance contract or Acceptance criteria section contains no "
            "acceptance items. Add at least one observable product outcome."
        ]
    return []


_HISTORY_INTENT_KEYS = frozenset(
    {
        "evidence_lifecycle",
        "history_attempts",
        "indexed_history_run",
        "jira_history_queries",
        "jira_history_tool",
        "jira_history_unavailable_reason",
        "known_bugs",
        "known_bugs_intent",
        "known_bugs_search_intent",
        "known_jira_bugs",
        "known_jira_bugs_intent",
        "past_similar_tickets",
        "jira_history_intent",
    }
)
_KNOWN_BUG_COLLECTION_KEYS = (
    "known_bugs",
    "known_jira_bugs",
    "past_similar_tickets",
)
_HISTORY_RESULTS = frozenset({"ok", "unavailable", "empty"})


def _declares_history_intent(manifest) -> bool:
    return isinstance(manifest, dict) and any(
        key in manifest for key in _HISTORY_INTENT_KEYS
    )


def _declares_thin_history(manifest: dict) -> bool:
    queries = manifest.get("jira_history_queries")
    if isinstance(queries, list) and not queries:
        return True
    for key in _KNOWN_BUG_COLLECTION_KEYS:
        if key not in manifest:
            continue
        value = manifest.get(key)
        if value is None or value == "" or value == [] or value == {}:
            return True
    return False


def _validate_history_attempt_recorded(manifest) -> list[str]:
    """Require deterministic attempt records whenever history is in scope."""
    if not _declares_history_intent(manifest):
        return []

    attempts = manifest.get("history_attempts")
    if not isinstance(attempts, list) or not attempts:
        return [
            "History or Known Jira Bugs evidence is in scope, but history_attempts "
            "does not record any search. Add at least one attempt with source, query, "
            "result, and count; record unavailable or empty instead of leaving a silent gap."
        ]

    problems: list[str] = []
    valid_outcomes: list[str] = []
    for index, attempt in enumerate(attempts, start=1):
        prefix = f"history_attempts item {index}"
        if not isinstance(attempt, dict):
            problems.append(f"{prefix} must be an object.")
            continue
        source = attempt.get("source")
        query = attempt.get("query")
        result = attempt.get("result")
        count = attempt.get("count")
        if not isinstance(source, str) or not source.strip():
            problems.append(f"{prefix} must have a non-empty source.")
        if not isinstance(query, str) or not query.strip():
            problems.append(f"{prefix} must have a non-empty query.")
        if result not in _HISTORY_RESULTS:
            allowed = ", ".join(sorted(_HISTORY_RESULTS))
            problems.append(f"{prefix} result must be one of: {allowed}.")
        else:
            valid_outcomes.append(result)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            problems.append(f"{prefix} count must be a non-negative integer.")
        elif result == "ok" and count == 0:
            problems.append(f"{prefix} must use result empty when count is zero.")
        elif result in {"empty", "unavailable"} and count != 0:
            problems.append(f"{prefix} count must be zero when result is {result}.")

    if (
        _declares_thin_history(manifest)
        and valid_outcomes
        and not {"empty", "unavailable"}.intersection(valid_outcomes)
    ):
        problems.append(
            "The manifest records an empty history query or Known Jira Bugs result, "
            "but no history attempt is marked empty or unavailable. Record the visible "
            "reason for the thin result."
        )
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


# ---------------------------------------------------------------------------
# 5. Current-status recency and error-surface UI dispositioning
# ---------------------------------------------------------------------------

# A recent comment/evidence saying the reported behaviour now works or is partly
# resolved. reproducibility_gate covers the CANNOT-reproduce case; this covers the
# opposite miss - drafting fix-ACs over behaviour a latest comment says already works
# (e.g. a recent comment reporting the operation now works on stage/prod while a fix-AC
# still asserts that operation must succeed).
_WORKS_NOW_RE = re.compile(
    r"\b(?:working\s+fine|works\s+fine|now\s+works|no\s+longer\s+reproduc|"
    r"already\s+(?:works|fixed)|is\s+working\s+(?:fine|now)|"
    r"resolved\s+(?:on|in)\s+(?:stage|prod|production|develop)|partially\s+resolved|"
    r"currently\s+works|fixed\s+in\s+(?:develop|the\s+latest))\b",
    re.IGNORECASE,
)
_STATUS_ACK_RE = re.compile(
    r"\b(?:no\s+longer\s+reproduc|now\s+works|works\s+now|already\s+works|"
    r"currently\s+works|partially\s+resolved|working\s+fine|resolved\s+on|"
    r"remaining\s+(?:issue|scope)|still\s+(?:fails|returns|503|errors))\b",
    re.IGNORECASE,
)
# A server-error surface the user actually sees.
_ERROR_SURFACE_RE = re.compile(
    r"\b(?:503|502|500|5xx|service\s+unavailable|gateway\s+timeout|"
    r"internal\s+server\s+error|File\s+is\s+not\s+valid)\b",
    re.IGNORECASE,
)
_ERROR_UI_CONTEXT_RE = re.compile(
    r"\b(?:editor|panel|dialog|screen|message|shows?|display(?:s|ed)?|surfaces?d?|"
    r"user|UI|notification|toast)\b",
    re.IGNORECASE,
)
_ERROR_UI_DISPOSITION_RE = re.compile(
    r"\b(?:unavailable|error\s+message|message\s+(?:shown|displayed|is)|"
    r"on\s+(?:failure|error|503|5xx)|behaviou?r\s+on\b|surface[sd]?\b|retry|"
    r"what\s+(?:the\s+)?(?:editor|ui|user)\s+(?:sees|should|does)|notify|"
    r"notification|warning|blocked\s+from|allowed\s+to\s+save)\b",
    re.IGNORECASE,
)


def _manifest_issue_text(manifest) -> str:
    """Flatten the manifest's issue summary/description/comments so a comment-borne
    signal (e.g. 'validatexml is working fine on stage and prod') is visible to gates."""
    if not isinstance(manifest, dict):
        return ""
    parts: list[str] = []
    issue = manifest.get("issue")
    if isinstance(issue, dict):
        for key in ("summary", "description"):
            parts.append(str(issue.get(key, "")))
        comments = issue.get("comments")
        if comments is None:
            comments = issue.get("comment")
        if isinstance(comments, dict):
            comments = comments.get("comments")
        if isinstance(comments, list):
            for entry in comments:
                parts.append(str(entry.get("body", "") if isinstance(entry, dict) else entry))
        elif isinstance(comments, str):
            parts.append(comments)
    for key in ("current_status_signals", "comments_text"):
        value = manifest.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.append(" ".join(str(x) for x in value))
    return "\n".join(parts)


def _validate_current_status_recency(manifest, plan_text: str) -> list[str]:
    """Fail when evidence says the behaviour now works / is partly resolved but the plan
    neither reflects that current status nor raises it as an Open Question and still ships
    acceptance criteria. Forces the author to read the latest comments before drafting."""
    evidence = _manifest_issue_text(manifest)
    if not _WORKS_NOW_RE.search(evidence):
        return []
    reflected = bool(
        _WORKS_NOW_RE.search(plan_text)
        or _STATUS_ACK_RE.search(plan_text)
        or re.search(r"\bOQ[-\s]?\d+\b", plan_text)
    )
    has_acs = bool(re.search(r"\bAC[-\s]?\d+\b", _acceptance_block(plan_text), re.I))
    if has_acs and not reflected:
        return [
            "A recent comment/evidence says the reported behaviour now works or is "
            "partially resolved (works-now signal), but the plan neither reflects the "
            "current status nor raises it as an Open Question and still asserts acceptance "
            "criteria. Run the reproducibility / working-as-designed assessment: confirm "
            "what still reproduces, scope the plan to the remaining issue, and do not draft "
            "fix-ACs for behaviour a comment says already works."
        ]
    return []


def _validate_error_surface_open_question(manifest, plan_text: str) -> list[str]:
    """Fail when evidence shows a user-facing server error (503 / service unavailable /
    'File is not valid') but no AC or Open Question dispositions what the UI should do on
    that error (message, whether the action is blocked/allowed/retried, panel state)."""
    hay = (plan_text or "") + "\n" + _manifest_issue_text(manifest)
    if not (_ERROR_SURFACE_RE.search(hay) and _ERROR_UI_CONTEXT_RE.search(hay)):
        return []
    disposition_lines = [
        line for line in (plan_text or "").splitlines()
        if re.search(r"\b(?:OQ|AC)[-\s]?\d+\b", line)
    ]
    if any(_ERROR_UI_DISPOSITION_RE.search(line) for line in disposition_lines):
        return []
    return [
        "The evidence shows a user-facing server error surface (for example 503 / service "
        "unavailable / 'File is not valid'), but no Acceptance Criterion or Open Question "
        "dispositions what the UI should do on that error: the exact message shown to the "
        "user, whether the action is blocked, allowed, or retried, and the panel/error "
        "state. Add it as an Open Question (or an AC once the behaviour is decided)."
    ]


# ---------------------------------------------------------------------------
# 6. Status-mislabel anti-over-correction and concurrency isolation
# ---------------------------------------------------------------------------

# A status-reporting defect: a run's shown status is wrong (a success shown as a
# failure, a false/red/stale failure, "failed but the files were produced").
_STATUS_MISLABEL_RE = re.compile(
    r"(?:incorrectly|false(?:ly)?|wrong(?:ly)?|erroneous|mis(?:label|report)|appears?|"
    r"shown\s+as|flag(?:s|ged)?|red)\b[^.\n]{0,60}\bfail",
    re.IGNORECASE,
)
_STATUS_FALSEPOS_RE = re.compile(
    r"\bfail\w*\b[^.\n]{0,80}\b(?:but|even\s+though|while|although)\b[^.\n]{0,80}"
    r"(?:succe|produced|complete|generated|correct)",
    re.IGNORECASE,
)
# The anti-over-correction guard: fixing a false failure must not start masking real ones.
_ANTI_OVERCORRECT_RE = re.compile(
    r"\b(?:genuine|real|actual|true)\b[^.\n]{0,40}\bfail|"
    r"\bfail\w*\b[^.\n]{0,40}\b(?:remain|still|stay)\b|"
    r"cancell?ed\b[^.\n]{0,30}\b(?:remain|stay|still)|"
    r"warning\b[^.\n]{0,30}(?:retain|remain|kept|keep)",
    re.IGNORECASE,
)
# Concurrency / overlap signal.
_CONCURRENCY_RE = re.compile(
    r"\b(?:overlap|concurren|already\s+running|still\s+running|"
    r"previous\s+(?:job|run|execution)|in\s+progress|simultaneou|parallel\s+job|"
    r"same\s+map\s+and\s+preset)\b",
    re.IGNORECASE,
)
# Isolation disposition: a rejected/aborted request keeps its own status, and unrelated
# work is unaffected.
_ISOLATION_RE = re.compile(
    r"\b(?:isolat|does\s+not\s+(?:affect|change)|unaffected|not\s+(?:appear|be\s+shown)\s+"
    r"success|other\s+(?:maps?|presets?|jobs?|runs?)|rejected\s+request|independent(?:ly)?|"
    r"own\s+(?:status|result|state))\b",
    re.IGNORECASE,
)


def _validate_status_anti_overcorrection(manifest, plan_text: str) -> list[str]:
    """When the ticket is about a wrong/false run status (a success shown as Failed), the
    plan must also assert that GENUINE failures still show Failed - otherwise the fix can
    over-correct and mask real failures. Missed on a false-failure output-status ticket."""
    evidence = (plan_text or "") + "\n" + _manifest_issue_text(manifest)
    if not (_STATUS_MISLABEL_RE.search(evidence) or _STATUS_FALSEPOS_RE.search(evidence)):
        return []
    if any(_ANTI_OVERCORRECT_RE.search(line) for line in _ac_lines(plan_text)):
        return []
    return [
        "This is a wrong/false run-status ticket (a successful or in-progress run is shown "
        "as Failed), but no acceptance criterion guards against over-correcting: add an AC "
        "that genuine failures still show Failed (and cancelled runs stay Cancelled, "
        "successful-with-warnings keep their warning) so the fix does not start masking real "
        "failures."
    ]


def _validate_concurrency_isolation(manifest, plan_text: str) -> list[str]:
    """When the defect involves overlapping/concurrent runs, the plan must disposition
    isolation: a rejected/aborted overlapping request keeps its own correct status (it is
    not shown as the sibling run's success), and unrelated maps/presets/jobs are
    unaffected. Missed on a concurrent-output-generation ticket."""
    evidence = (plan_text or "") + "\n" + _manifest_issue_text(manifest)
    if not _CONCURRENCY_RE.search(evidence):
        return []
    lines = [
        line for line in (plan_text or "").splitlines()
        if re.search(r"\b(?:AC|OQ)[-\s]?\d+\b", line)
    ]
    if any(_ISOLATION_RE.search(line) for line in lines):
        return []
    return [
        "This defect involves overlapping/concurrent runs, but no acceptance criterion or "
        "Open Question dispositions isolation: assert that a rejected or aborted overlapping "
        "request keeps its own correct status (it is not shown as the other run's success), "
        "and that unrelated maps, presets, or jobs keep their own status, links, and logs."
    ]


# A vague collective surface reference ("both dashboards", "the dashboards", "both
# panels") instead of the exact screen names. plain-language-ac-writing requires the exact
# screen name; this makes it fail-closed so a plural collective cannot stand in for the
# named surfaces (missed by writing "both dashboards" where the ticket named the Map
# Dashboard Outputs tab and the Bulk Publish dashboard).
_VAGUE_SURFACE_RE = re.compile(
    r"\b(?:both|all|either|the)\s+(?:dashboards|panels|screens|views|tabs|surfaces|dialogs)\b",
    re.IGNORECASE,
)


def _validate_vague_surface_reference(manifest, plan_text: str) -> list[str]:
    """Fail an acceptance criterion that refers to a vague collective UI surface (e.g.
    'both dashboards', 'the panels') instead of naming each exact screen. Singular named
    surfaces such as 'the Map Dashboard Outputs tab' or 'the Bulk Publish dashboard' pass."""
    problems: list[str] = []
    for line in _ac_lines(plan_text):
        match = _VAGUE_SURFACE_RE.search(line)
        if match:
            problems.append(
                f"An acceptance criterion names a vague collective surface "
                f"({match.group(0)!r}): name each exact screen instead (for example the Map "
                f"Dashboard Outputs tab and the Bulk Publish dashboard). Line: {line[:70]!r}."
            )
    return problems


def validate(manifest, plan_text: str = "", *, catalog_path=None) -> list[str]:
    problems: list[str] = []
    problems += _validate_performance(manifest, plan_text)
    problems += _validate_ui_surface(manifest, plan_text, catalog_path=catalog_path)
    problems += _validate_investigation(manifest, plan_text)
    problems += _validate_no_test_as_ac(manifest, plan_text)
    problems += _validate_ac_oq_contradiction(manifest, plan_text)
    problems += _validate_restated_instance_ac(manifest, plan_text)
    problems += _validate_no_markup_in_ac(manifest, plan_text)
    problems += _validate_ac_over_decomposition(manifest, plan_text)
    problems += _validate_plain_language(plan_text)
    problems += _validate_ac_redundancy(plan_text)
    problems += _validate_acceptance_contract_present(plan_text, manifest)
    problems += _validate_history_attempt_recorded(manifest)
    problems += _validate_current_status_recency(manifest, plan_text)
    problems += _validate_error_surface_open_question(manifest, plan_text)
    problems += _validate_status_anti_overcorrection(manifest, plan_text)
    problems += _validate_concurrency_isolation(manifest, plan_text)
    problems += _validate_vague_surface_reference(manifest, plan_text)
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

    # --- no test/automation as an AC ---
    test_ac = nl.join([
        "**Acceptance Criteria**",
        "- AC-09: the added translation test covers the created-in-en / moved-to-en_us case across map and topic.",
        ""])
    assert any("Automation Coverage evidence" in p for p in validate({}, test_ac)), "added-test-as-AC must fail"
    testfile_ac = nl.join([
        "**Acceptance Criteria**",
        "- AC-08: The added topic.test.ts case passes.",
        ""])
    assert any("Automation Coverage evidence" in p for p in validate({}, testfile_ac)), "test-file-as-AC must fail"
    # a plain product-behaviour AC that merely contains the word 'test' must NOT trip it
    ok_test = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: the user can use the Test Connection button and see a success message.",
        ""])
    assert not any("Automation Coverage evidence" in p for p in validate({}, ok_test)), "product 'Test Connection' must pass"

    # --- AC/OQ contradiction ---
    contra = nl.join([
        "**Acceptance Criteria**", "- AC-07: the output falls back to the generic value when no regional entry exists.",
        "**Open Questions**", "- OQ-1: confirm the approved behaviour when a regional entry is absent (fall back to generic, per AC-7).",
        ""])
    assert any("redundant/contradictory" in p for p in validate({}, contra)), "OQ referencing an AC must fail"
    # --- restated-instance AC ---
    restated = nl.join([
        "**Acceptance Criteria**", "- AC-02: The exact reported case passes: a map set to pt_br shows the regional text.",
        ""])
    assert any("restates the specific reported instance" in p for p in validate({}, restated)), "restated-instance AC must fail"
    # a genuine OQ with no AC reference must pass
    ok_oq = nl.join([
        "**Acceptance Criteria**", "- AC-01: the dialog opens on click.",
        "**Open Questions**", "- OQ-1: when the map language and preset language differ, which one wins?",
        ""])
    assert not any("redundant/contradictory" in p for p in validate({}, ok_oq)), "genuine OQ must pass"

    # --- no raw markup / code block in ACs ---
    markup = nl.join(["**Acceptance Criteria**", "- AC-01: When a keydef is written as <keydef keys=\"\" href=\"topic.dita\"/> the label is wrong.", ""])
    assert any("raw markup" in p for p in validate({}, markup)), "raw XML in AC must fail"
    fence = nl.join(["**Acceptance Criteria**", "- AC-01: the blank key must error.", "```", "<keydef keys=\"\"/>", "```", ""])
    assert any("code block" in p for p in validate({}, fence)), "code fence in AC must fail"
    # --- over-decomposition ---
    many = nl.join(["**Acceptance Criteria**"] + [f"- AC-{i:02d}: the entry behaves correctly in case {i}." for i in range(1, 14)] + [""])
    assert any("over-decomposed" in p for p in validate({}, many)), ">12 ACs must be flagged"
    few = nl.join(["**Acceptance Criteria**"] + [f"- AC-{i}: the entry behaves correctly." for i in range(1, 7)] + [""])
    assert not any("over-decomposed" in p for p in validate({}, few)), "6 ACs must pass"

    # --- no code identifiers in ACs ---
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

    # --- scoped lexical AC redundancy ---
    distinct_acs = nl.join([
        "## Acceptance contract",
        "- AC-01: Translation succeeds for content moved to a regional folder.",
        "- AC-02: The move preserves the source asset identity.",
        "## Semantic coverage",
        "- AC-01 is mapped to the translation workflow.",
        ""])
    assert _validate_ac_redundancy(distinct_acs) == [], "distinct ACs must pass"
    duplicate_acs = nl.join([
        "## Acceptance criteria",
        "- AC-01: The cross reference label excludes the footnote callout text.",
        "- AC-02: The cross reference label must exclude footnote callout text.",
        ""])
    duplicate_problems = _validate_ac_redundancy(duplicate_acs)
    assert len(duplicate_problems) == 1, "near-duplicate ACs must fail"
    assert "AC-01 text:" in duplicate_problems[0] and "AC-02 text:" in duplicate_problems[0], (
        "redundancy failure must identify both ACs and their text"
    )
    assert _validate_ac_redundancy("## Semantic coverage\n- AC-01 is mentioned here.\n") == [], (
        "redundancy scan must not fall back to the whole plan"
    )

    # --- acceptance contract presence ---
    no_contract = "## Issue understanding\n- A visible behavior is broken.\n"
    assert _validate_acceptance_contract_present(no_contract, {"behaviour_matters": True}), (
        "behavioral plan without a contract must fail"
    )
    assert _validate_acceptance_contract_present(no_contract, {"behaviour_matters": False}) == [], (
        "explicit non-behavioral opt-out must pass"
    )
    assert _validate_acceptance_contract_present("## Acceptance contract\n", {}) != [], (
        "empty acceptance contract must fail"
    )
    assert _validate_acceptance_contract_present(distinct_acs, {}) == [], (
        "populated acceptance contract must pass"
    )

    # --- history-attempt recording ---
    assert _validate_history_attempt_recorded({}) == [], "manifest without history intent must pass"
    assert _validate_history_attempt_recorded({"evidence_lifecycle": []}) != [], (
        "history intent without an attempt must fail"
    )
    recorded_history = {
        "evidence_lifecycle": [],
        "history_attempts": [
            {
                "source": "search_jira_history",
                "query": "same failure mechanism",
                "result": "ok",
                "count": 2,
            }
        ],
    }
    assert _validate_history_attempt_recorded(recorded_history) == [], (
        "complete history attempt must pass"
    )
    unavailable_history = {
        "jira_history_queries": [],
        "history_attempts": [
            {
                "source": "search_jira_history",
                "query": "same failure mechanism",
                "result": "unavailable",
                "count": 0,
            }
        ],
    }
    assert _validate_history_attempt_recorded(unavailable_history) == [], (
        "an unavailable attempt must make a thin history result explicit"
    )
    thin_but_ok = {
        "known_jira_bugs": [],
        "history_attempts": [
            {
                "source": "search_jira_history",
                "query": "same failure mechanism",
                "result": "ok",
                "count": 1,
            }
        ],
    }
    assert any("empty or unavailable" in p for p in _validate_history_attempt_recorded(thin_but_ok)), (
        "empty Known Jira Bugs result needs an empty or unavailable attempt"
    )
    malformed_history = {
        "history_attempts": [
            {"source": "", "query": "", "result": "ok", "count": True}
        ]
    }
    malformed_problems = _validate_history_attempt_recorded(malformed_history)
    assert len(malformed_problems) >= 3, "malformed history attempt must fail closed"

    # --- current-status recency (works-now signal in a comment) ---
    works_now_manifest = {
        "issue": {
            "summary": "save-validation timeout",
            "comments": [{"body": "validatexml is working fine on stage and prod now."}],
        }
    }
    fix_ac_plan = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: saving the high-fan-in topic completes and commits successfully.",
        ""])
    assert any("works-now signal" in p for p in _validate_current_status_recency(works_now_manifest, fix_ac_plan)), (
        "fix-ACs over behaviour a comment says now works must fail"
    )
    reflected_plan = nl.join([
        "**Understanding**", "Per the latest comment the save path now works; only the "
        "references panel still returns 503 (remaining scope).",
        "**Acceptance Criteria**",
        "- AC-01: the references panel loads for the high-fan-in topic.",
        "**Open Questions**",
        "- OQ-01: is save-validation still in scope? QA impact: sets scope.",
        ""])
    assert _validate_current_status_recency(works_now_manifest, reflected_plan) == [], (
        "a plan that reflects current status / raises an OQ must pass"
    )
    assert _validate_current_status_recency({}, fix_ac_plan) == [], "no works-now signal -> no forcing"

    # --- error-surface UI open question ---
    err_plan_missing = nl.join([
        "**Understanding**", "The editor shows 'File is not valid' and the references panel "
        "returns a 503.",
        "**Acceptance Criteria**",
        "- AC-01: the references panel loads for the high-fan-in topic.",
        ""])
    assert any("what the UI should do on that error" in p for p in _validate_error_surface_open_question({}, err_plan_missing)), (
        "a user-facing 503/File-is-not-valid surface with no error-UI disposition must fail"
    )
    err_plan_covered = err_plan_missing + nl.join([
        "**Open Questions**",
        "- OQ-01: on a 503 what message should the editor show and is save blocked or "
        "allowed with a warning? QA impact: the observable oracle for the error behaviour.",
        ""])
    assert _validate_error_surface_open_question({}, err_plan_covered) == [], (
        "an error-UI Open Question satisfies the gate"
    )
    backend_only_503 = nl.join([
        "**Understanding**", "Find returns HTTP 503 on large maps.",
        "**Acceptance Criteria**", "- AC-01: results are returned.", ""])
    assert _validate_error_surface_open_question({}, backend_only_503) == [], (
        "a 503 with no user-facing UI context must not force the error-UI question"
    )

    # --- status anti-over-correction ---
    mislabel_plan = nl.join([
        "**Understanding**", "The dashboard incorrectly shows a successful generation as Failed.",
        "**Acceptance Criteria**",
        "- AC-01: a run that produced its files shows success, not Failed.",
        ""])
    assert any("masking real" in p for p in _validate_status_anti_overcorrection({}, mislabel_plan)), (
        "a false-failure ticket needs an anti-over-correction AC"
    )
    mislabel_covered = mislabel_plan + nl.join([
        "- AC-09: genuine generation failures still show Failed and cancelled runs stay Cancelled.",
        ""])
    assert _validate_status_anti_overcorrection({}, mislabel_covered) == [], (
        "an anti-over-correction AC satisfies the gate"
    )
    assert _validate_status_anti_overcorrection({}, plain) == [], "no status-mislabel signal -> no forcing"

    # --- concurrency isolation ---
    overlap_plan = nl.join([
        "**Understanding**", "Fails when a second request runs while a previous job is still running.",
        "**Acceptance Criteria**",
        "- AC-01: the completed run shows success.",
        ""])
    assert any("isolation" in p for p in _validate_concurrency_isolation({}, overlap_plan)), (
        "a concurrency/overlap ticket needs an isolation AC/OQ"
    )
    overlap_covered = overlap_plan + nl.join([
        "- AC-04: a rejected overlapping request keeps its own status and does not appear "
        "successful; other maps and presets are unaffected.",
        ""])
    assert _validate_concurrency_isolation({}, overlap_covered) == [], (
        "an isolation AC satisfies the gate"
    )
    assert _validate_concurrency_isolation({}, plain) == [], "no concurrency signal -> no forcing"

    # --- vague collective surface reference ---
    vague_plan = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: after a run completes, both dashboards show success.",
        ""])
    assert any("vague collective surface" in p for p in _validate_vague_surface_reference({}, vague_plan)), (
        "'both dashboards' must fail"
    )
    named_plan = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: after a run completes, the Map Dashboard Outputs tab and the Bulk Publish "
        "dashboard show success.",
        ""])
    assert _validate_vague_surface_reference({}, named_plan) == [], (
        "named surfaces must pass"
    )
    assert _validate_vague_surface_reference({}, plain) == [], "no surface reference -> pass"

    # --- performance: duration/concurrency signal + conditional-OQ disposition ---
    dur_missing = nl.join([
        "**Understanding**", "Output is produced 5-10 minutes later while an overlapping job is still running.",
        "**Acceptance Criteria**", "- AC-01: the completed run shows success.", ""])
    assert any("performance is not dispositioned" in p for p in validate({}, dur_missing)), (
        "a duration/concurrency signal must force a performance disposition"
    )
    dur_oq = dur_missing + nl.join([
        "**Open Questions**",
        "- OQ-05: no approved SLA exists for generation duration under concurrent/bulk load; "
        "QA impact: whether a performance AC is needed and the required workload/baseline.",
        ""])
    assert not any("performance is not dispositioned" in p for p in validate({}, dur_oq)), (
        "a performance-conditional Open Question satisfies the disposition"
    )

    print("coverage_forcing self-tests: PASS")


if __name__ == "__main__":
    run_self_tests()
