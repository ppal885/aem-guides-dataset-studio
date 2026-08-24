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

# Provenance of a config KEY string: whether the exact key was verified against
# product code/docs, or merely copied from the reporter/ticket (frequently a typo
# or transposition - e.g. a reporter's "uuid.duplicate.move.old" vs the real
# "duplicate.uuid.move.old.file"). A config_key that grounds an acceptance
# criterion must be code/doc-verified or explicitly carried as an Open Question.
VERIFIED_KEY_PROVENANCE = ("CODE", "PRODUCT_DOC", "OSGI_CONFIG", "DTD", "SPEC")
UNVERIFIED_KEY_PROVENANCE = ("REPORTER", "TICKET", "PARAPHRASE", "UNKNOWN")

# Dependency-delegated implementation: when the real logic lives in an external/
# vendored package (not the ticket's own repo) and neither a local clone of that
# package nor GitHub MCP can reach it, the premise is genuinely UNRESOLVED - not a
# gate failure to route around, and not a silent guess to accept as fact.
DEPENDENCY_RESOLUTION_STATUSES = (
    "RESOLVED_LOCAL_CLONE", "RESOLVED_GITHUB_MCP", "UNRESOLVED_NO_ACCESS", "NOT_APPLICABLE",
)

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


def validate_implementation_grounding(block, *, open_question_ids=None):
    """Validate a manifest `implementation_grounding` block. Returns problem strings."""
    if not isinstance(block, dict):
        return ["implementation_grounding must be a JSON object"]
    problems = []
    open_ids = None if open_question_ids is None else set(open_question_ids)
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
        # Config-key provenance: a config_key artifact must not rest on a
        # reporter/ticket-supplied key string that was never verified in code/docs.
        if kind == "config_key":
            prov = str(art.get("key_provenance", "")).strip()
            if prov and prov not in VERIFIED_KEY_PROVENANCE + UNVERIFIED_KEY_PROVENANCE:
                problems.append(
                    f"named_artifacts[{i}].key_provenance must be one of "
                    f"{', '.join(VERIFIED_KEY_PROVENANCE + UNVERIFIED_KEY_PROVENANCE)}"
                )
            elif prov in UNVERIFIED_KEY_PROVENANCE and material:
                ref = str(art.get("verification_open_question_ref", "") or "").strip()
                if not ref:
                    problems.append(
                        f"named_artifacts[{i}] ('{name or '?'}') is a config_key with UNVERIFIED provenance "
                        f"({prov}) - a reporter/ticket-supplied key is frequently a typo or transposition; grep it "
                        f"against the product code/docs and set key_provenance to a verified source, or carry it as "
                        f"an Open Question via verification_open_question_ref"
                    )
                elif open_ids is not None and ref not in open_ids:
                    problems.append(
                        f"named_artifacts[{i}].verification_open_question_ref '{ref}' is not in the plan's open_questions"
                    )
        # A ticket premise about CURRENT behaviour must be verified against the code.
        premise = str(art.get("premise", "")).strip()
        if premise:
            if art.get("premise_verified") is not True:
                problems.append(
                    f"named_artifacts[{i}] states a ticket premise ('{premise[:60]}') but premise_verified is not true - "
                    f"confirm the premise against the handler; ticket claims about current behaviour are often stale"
                )
            premise_holds = art.get("premise_holds")
            if isinstance(premise_holds, bool):
                pass
            elif premise_holds == "unresolved":
                # A genuine third state: the code was inspected but cannot confirm OR
                # refute the premise (e.g. delegated to an unreachable dependency, or the
                # claimed behaviour depends on runtime state no static read can settle).
                # This must not be used as an escape hatch from actually looking - it
                # requires a premise_note explaining what was checked and why it fell short.
                if not str(art.get("premise_note", "")).strip():
                    problems.append(
                        f"named_artifacts[{i}].premise_holds is 'unresolved' but premise_note is empty - "
                        f"explain what was searched and why the premise could not be confirmed or refuted in code"
                    )
            else:
                problems.append(
                    f"named_artifacts[{i}].premise_holds must be true, false, or 'unresolved' (only when the code "
                    f"genuinely cannot confirm or refute the ticket premise) recording whether the code confirms it"
                )
            if material and not any(str(e).strip() for e in (evidence or [])):
                problems.append(f"named_artifacts[{i}] premise verification needs cited code evidence")

        # Dependency-delegated implementation: optional, only validated when declared.
        dep = art.get("dependency_resolution")
        if dep is not None:
            if not isinstance(dep, dict):
                problems.append(f"named_artifacts[{i}].dependency_resolution must be an object")
            else:
                status = str(dep.get("status", "")).strip()
                if status not in DEPENDENCY_RESOLUTION_STATUSES:
                    problems.append(
                        f"named_artifacts[{i}].dependency_resolution.status must be one of: "
                        f"{', '.join(DEPENDENCY_RESOLUTION_STATUSES)}"
                    )
                if status == "UNRESOLVED_NO_ACCESS" and not str(dep.get("note", "")).strip():
                    problems.append(
                        f"named_artifacts[{i}].dependency_resolution is UNRESOLVED_NO_ACCESS but has no 'note' - "
                        f"name the external/vendored package and why neither a local clone nor GitHub MCP could "
                        f"reach it, and carry the resulting gap as an Open Question"
                    )
    return problems


def config_key_artifacts_missing_provenance(block):
    """Material config_key artifacts that declare no key_provenance at all. The gate
    surfaces these as NEEDS_REVIEW so every config key is explicitly marked as
    code/doc-verified vs reporter/ticket-supplied before it grounds an AC."""
    out = []
    if not isinstance(block, dict):
        return out
    for art in (block.get("named_artifacts") or []):
        if not isinstance(art, dict) or art.get("kind") != "config_key":
            continue
        if art.get("material", True) and not str(art.get("key_provenance", "") or "").strip():
            out.append(str(art.get("artifact", "?")))
    return out


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
