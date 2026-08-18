"""ImplementationGroundingExplorer - force API/operation/backend tickets to be
grounded in the actual handler code, not in the ticket's prose claims.

WHY THIS EXISTS
---------------
A whole class of weak UACs comes from writing acceptance criteria about a named
code artifact (a REST path, a servlet operation, a handler method, a service
class, a config key) straight from the ticket's description - WITHOUT opening the
handler. The ticket's account of *current* behaviour is frequently stale or
incomplete: a "the API returns no job id" premise can already be false in the
current code. Taking such a premise at face value produces criteria that restate
the ask, accept an outdated premise as fact, and invent generic ACs (auth /
performance) that no code was checked for.

This gate makes the discipline mandatory and generic: whenever the plan names a
code artifact and asserts current behaviour about it, an `implementation_grounding`
block must record that the handler was INSPECTED and cite the file:line, and any
ticket premise about current behaviour must be VERIFIED against that code.

It is generic - it hardcodes no specific endpoint, operation, or class. Stdlib only.
"""

ARTIFACT_KINDS = ("api", "operation", "handler", "method", "service_class", "config_key")

# Strong signals that a ticket concerns a named backend/API *contract* artifact.
# Deliberately narrow: merely citing a .java file (as any code-grounded DITA/publishing
# plan does) must NOT activate this gate - only an API/service-contract surface does.
STRONG_API_SIGNALS = (
    "/bin/", "/api/", "servlet", "endpoint", "rest api", "http api", "public api",
    "api contract", "response dto", "handler method", "operation enum",
    "servlet operation", "rest endpoint", "api signature", "public rest",
)
# Corroborating (weaker) tokens - only meaningful alongside a strong signal.
WEAK_API_SIGNALS = (
    "operation", "handler", "payload", "request parameter", "json response",
    "status code", "http get", "http post", "http put", "http delete",
    "workflow step", "job id", "jobid", "execution id", "response field", ".java",
)
# Current-behaviour assertion markers (the plan claiming what the code does today).
ASSERTION_MARKERS = (
    "currently", "current implementation", "returns", "does not return", "is returned",
    "response contains", "response does not", "no job", "the api", "the servlet",
    "the endpoint", "responds with", "already returns", "does not expose", "exposes",
)


def _issue_text(manifest):
    issue = manifest.get("issue") if isinstance(manifest, dict) else None
    if isinstance(issue, dict):
        return " ".join(str(issue.get(k, "")) for k in ("summary", "description", "title"))
    return str(issue or "")


def _bm_text(manifest):
    bm = manifest.get("behavior_model") if isinstance(manifest, dict) else None
    if not isinstance(bm, dict):
        return ""
    parts = []
    for f in ("trigger", "operations", "consumers", "read_paths", "update_paths",
              "write_paths", "unknowns"):
        parts.extend(str(x) for x in (bm.get(f) or []))
    for fact in (bm.get("facts") or []):
        if isinstance(fact, dict):
            parts.append(str(fact.get("fact", "")))
    return " ".join(parts)


def detect_signals(manifest, plan_text=""):
    """Return the API/implementation signals present in the evidence + plan."""
    text = " ".join([_issue_text(manifest), _bm_text(manifest), plan_text or ""]).lower()
    hits = [s for s in STRONG_API_SIGNALS if s in text]
    if hits:
        hits += [s for s in WEAK_API_SIGNALS if s in text]
    return sorted(set(hits))


def is_active(manifest, plan_text=""):
    """Implementation grounding is expected when a named backend/API artifact is in
    scope (a strong API signal is present). Plain UI/DITA-only tickets do not trigger it."""
    text = " ".join([_issue_text(manifest), _bm_text(manifest), plan_text or ""]).lower()
    return any(s in text for s in STRONG_API_SIGNALS)


def asserts_current_behavior(plan_text):
    """True when the plan's Expected Behaviour makes a current-behaviour claim about a
    named API/implementation artifact - the exact situation that must be code-grounded."""
    if not plan_text:
        return False
    lower = plan_text.lower()
    # Focus on the Expected Behaviour section when present; else the whole body.
    start = lower.find("expected behaviour")
    if start == -1:
        start = lower.find("expected behavior")
    segment = lower[start:start + 2500] if start != -1 else lower
    has_api = any(s in segment for s in STRONG_API_SIGNALS)
    has_assertion = any(m in segment for m in ASSERTION_MARKERS)
    return has_api and has_assertion


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("implementation_grounding"), dict)


def validate_implementation_grounding(block):
    """Validate a manifest `implementation_grounding` block. Returns problem strings."""
    if not isinstance(block, dict):
        return ["implementation_grounding must be a JSON object"]
    problems = []
    if not isinstance(block.get("active", True), bool):
        problems.append("implementation_grounding.active must be a boolean")
    if not block.get("active", True):
        return problems

    artifacts = block.get("named_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return ["implementation_grounding.named_artifacts must be a non-empty list of inspected code artifacts"]

    for i, art in enumerate(artifacts):
        if not isinstance(art, dict):
            problems.append(f"named_artifacts[{i}] must be an object")
            continue
        name = str(art.get("artifact", "")).strip()
        kind = str(art.get("kind", "")).strip()
        inspected = art.get("inspected")
        evidence = art.get("evidence", []) or []
        material = art.get("material", True)
        if not name:
            problems.append(f"named_artifacts[{i}] is missing 'artifact' (the API path / operation / handler / method / class / config key)")
        if kind not in ARTIFACT_KINDS:
            problems.append(f"named_artifacts[{i}].kind must be one of: {', '.join(ARTIFACT_KINDS)}")
        if not isinstance(material, bool):
            problems.append(f"named_artifacts[{i}].material must be a boolean")
        if material:
            if inspected is not True:
                problems.append(
                    f"named_artifacts[{i}] ('{name or '?'}') is material but not inspected - open the handler in the "
                    f"clone/GitHub and set inspected:true; do not write ACs about it from the ticket text alone"
                )
            if not isinstance(evidence, list) or not any(str(e).strip() for e in evidence):
                problems.append(
                    f"named_artifacts[{i}] ('{name or '?'}') must cite at least one file:line evidence for the inspected handler"
                )
        # A ticket premise about CURRENT behaviour must be verified against the code.
        premise = str(art.get("premise", "")).strip()
        if premise:
            if art.get("premise_verified") is not True:
                problems.append(
                    f"named_artifacts[{i}] states a ticket premise ('{premise[:60]}') but premise_verified is not true - "
                    f"confirm the premise against the handler; ticket claims about current behaviour are often stale"
                )
            if not isinstance(art.get("premise_holds"), bool):
                problems.append(
                    f"named_artifacts[{i}].premise_holds must be a boolean recording whether the code confirms the ticket premise"
                )
            if material and not any(str(e).strip() for e in (evidence or [])):
                problems.append(f"named_artifacts[{i}] premise verification needs cited code evidence")
    return problems


def summarize(manifest, plan_text=""):
    lines = [f"ImplementationGroundingExplorer: active={is_active(manifest, plan_text)} signals={detect_signals(manifest, plan_text)}"]
    problems = []
    if is_present(manifest):
        problems = validate_implementation_grounding(manifest["implementation_grounding"])
    elif is_active(manifest, plan_text) and asserts_current_behavior(plan_text):
        problems = ["API/implementation artifact in scope and current behaviour asserted, but no implementation_grounding block cites the inspected handler"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)
