"""Validate the operational contract for jobs, incident repair, and async work.

Operational features fail in ways that ordinary happy-path ACs do not expose: a
deployment can trigger work twice, a page can be partially written before a retry,
or shutdown can be reported as success.  This module forces every recurring
operational dimension to have an explicit, referentially valid disposition.

The module is intentionally product- and ticket-neutral.  It validates a manifest
block named ``operational_contract`` and provides a conservative signal detector for
gate integration.  It uses only the Python standard library.
"""

SCHEMA_VERSION = "aem-guides-operational-contract-v1"
BLOCK_NAME = "operational_contract"

REQUIRED_DIMENSIONS = (
    "TRIGGER_AND_DEPLOYMENT_SCOPE",
    "FAILURE_POINTS_AND_MATRIX",
    "SUCCESS_TERMINAL_OUTCOME",
    "FAILURE_TERMINAL_OUTCOME",
    "CANCELLATION_TERMINAL_OUTCOME",
    "SHUTDOWN_TERMINAL_OUTCOME",
    "RETRY_POLICY",
    "DEFENSIVE_PROGRESS_BOUND",
    "PARTIAL_WRITE_RECOVERY_IDEMPOTENCY",
    "CONCURRENCY_AND_SNAPSHOT_MUTATIONS",
    "QUEUE_ISOLATION",
    "OBSERVABILITY",
    "RECOVERY_SAFETY",
    "DETERMINISTIC_AUTOMATION",
)

# Public alias for callers that use the shorter name.
DIMENSIONS = REQUIRED_DIMENSIONS

DISPOSITIONS = (
    "COVERED_BY_AC",
    "COVERED_BY_SCENARIO",
    "OPEN_QUESTION",
    "OUT_OF_SCOPE",
)

# These phrases are deliberately stronger than generic terms such as "operation" or
# "failure".  Gate code may treat one or more hits as a reason to require the block.
OPERATIONAL_TRIGGER_PHRASES = (
    "sling job",
    "background job",
    "scheduled job",
    "maintenance job",
    "repair job",
    "migration job",
    "upgrade job",
    "job consumer",
    "job queue",
    "worker queue",
    "queue isolation",
    "asynchronous consumer",
    "async consumer",
    "event listener",
    "observation listener",
    "deployment hook",
    "startup hook",
    "long-running",
    "long running",
    "batch processor",
    "bulk processing",
    "repository traversal",
    "pagination loop",
    "cursor loop",
    "retry",
    "retry policy",
    "retryable",
    "backoff",
    "restart",
    "cancellation",
    "shutdown",
    "partial write",
    "checkpoint",
    "no progress",
    "unbounded loop",
    "fault injection",
)


def is_present(manifest):
    """Return whether *manifest* contains an operational-contract object."""
    return isinstance(manifest, dict) and isinstance(manifest.get(BLOCK_NAME), dict)


def _text_values(value):
    """Yield text recursively from evidence-bearing manifest fragments."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _text_values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _text_values(item)


def likely_operational(manifest, plan_text=""):
    """Return unique strong operational phrases found outside the contract block.

    The detector is only a routing signal; ``validate_operational_contract`` remains
    the authority for the block itself.  The contract block is deliberately excluded
    so that its own vocabulary cannot make an otherwise non-operational ticket match.
    """
    texts = []
    if isinstance(manifest, dict):
        for key in (
            "issue",
            "behavior_model",
            "enumerated_requirements",
            "comment_claims",
            "implementation_grounding",
            "affected_surface_dimensions",
        ):
            texts.extend(_text_values(manifest.get(key)))
    if plan_text:
        texts.append(str(plan_text))

    haystack = "\n".join(texts).lower()
    return [phrase for phrase in OPERATIONAL_TRIGGER_PHRASES if phrase in haystack]


def _known_ids(values):
    if values is None:
        return None
    return {str(value).strip() for value in values if str(value).strip()}


def _validate_refs(entry, field, known_ids, *, tag, label, required):
    """Validate a reference list and return problem strings.

    Passing ``None`` for a known-ID collection is intentionally different from an
    empty collection.  ``None`` means the caller did not provide the index, so real
    referential integrity cannot be proved and a reference-bearing disposition fails.
    An empty collection likewise rejects every claimed reference.
    """
    if field not in entry:
        return [f"{tag}: {field} is required"] if required else []

    value = entry.get(field)
    if not isinstance(value, list) or not value:
        return [f"{tag}.{field} must be a non-empty list"]

    problems = []
    seen = set()
    for index, raw_ref in enumerate(value):
        ref = str(raw_ref or "").strip()
        ref_tag = f"{tag}.{field}[{index}]"
        if not ref:
            problems.append(f"{ref_tag} must be a non-empty {label} ID")
            continue
        if ref in seen:
            problems.append(f"{ref_tag} duplicates {label} ID '{ref}'")
            continue
        seen.add(ref)
        if known_ids is None:
            problems.append(
                f"{ref_tag} cannot be verified because the known {label} ID set was not supplied"
            )
        elif ref not in known_ids:
            problems.append(f"{ref_tag} '{ref}' is not defined in the plan")
    return problems


def _reject_fields(entry, fields, *, tag, disposition):
    problems = []
    for field in fields:
        if field in entry and entry.get(field) not in (None, [], ""):
            problems.append(f"{tag}: {disposition} must not declare {field}")
    return problems


def validate_operational_contract(
    block,
    *,
    ac_ids=None,
    open_question_ids=None,
    scenario_ids=None,
):
    """Return hard validation problems for one ``operational_contract`` block.

    Callers must pass the plan's known AC, Open Question, and scenario ID collections
    whenever the corresponding disposition is used.  Empty collections are valid
    inputs and correctly reject arbitrary references.
    """
    if not isinstance(block, dict):
        return [f"{BLOCK_NAME} must be an object"]

    problems = []
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(
            f"{BLOCK_NAME}.schema_version must be '{SCHEMA_VERSION}'"
        )

    active = block.get("active")
    if not isinstance(active, bool):
        problems.append(f"{BLOCK_NAME}.active is required and must be true or false")

    reason = str(block.get("reason", "") or "").strip()
    if not reason:
        problems.append(
            f"{BLOCK_NAME}.reason is required and must explain why the contract is active or inactive"
        )

    dimensions = block.get("dimensions")
    if active is False:
        if dimensions not in (None, []):
            problems.append(
                f"{BLOCK_NAME}.dimensions must be omitted or empty when active is false"
            )
        return problems

    if active is not True:
        return problems
    if not isinstance(dimensions, list):
        return problems + [
            f"{BLOCK_NAME}.dimensions must be a list when active is true"
        ]

    known_ac_ids = _known_ids(ac_ids)
    known_oq_ids = _known_ids(open_question_ids)
    known_scenario_ids = _known_ids(scenario_ids)
    seen_dimensions = set()

    for index, entry in enumerate(dimensions):
        tag = f"{BLOCK_NAME}.dimensions[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{tag} must be an object")
            continue

        dimension = str(entry.get("dimension", "") or "").strip()
        if dimension not in REQUIRED_DIMENSIONS:
            problems.append(f"{tag}.dimension is unknown or missing: {dimension!r}")
            continue
        if dimension in seen_dimensions:
            problems.append(f"{tag}.dimension duplicates '{dimension}'")
            continue
        seen_dimensions.add(dimension)

        disposition = entry.get("disposition")
        if disposition not in DISPOSITIONS:
            problems.append(
                f"{tag} ({dimension}): disposition must be one of {DISPOSITIONS}, "
                f"got {disposition!r}"
            )
            continue

        dimension_tag = f"{tag} ({dimension})"
        if disposition == "COVERED_BY_AC":
            problems.extend(
                _validate_refs(
                    entry,
                    "ac_refs",
                    known_ac_ids,
                    tag=dimension_tag,
                    label="AC",
                    required=True,
                )
            )
            if "scenario_refs" in entry:
                problems.extend(
                    _validate_refs(
                        entry,
                        "scenario_refs",
                        known_scenario_ids,
                        tag=dimension_tag,
                        label="scenario",
                        required=False,
                    )
                )
            problems.extend(
                _reject_fields(
                    entry,
                    ("open_question_refs", "reason"),
                    tag=dimension_tag,
                    disposition=disposition,
                )
            )
        elif disposition == "COVERED_BY_SCENARIO":
            problems.extend(
                _validate_refs(
                    entry,
                    "scenario_refs",
                    known_scenario_ids,
                    tag=dimension_tag,
                    label="scenario",
                    required=True,
                )
            )
            if "ac_refs" in entry:
                problems.extend(
                    _validate_refs(
                        entry,
                        "ac_refs",
                        known_ac_ids,
                        tag=dimension_tag,
                        label="AC",
                        required=False,
                    )
                )
            problems.extend(
                _reject_fields(
                    entry,
                    ("open_question_refs", "reason"),
                    tag=dimension_tag,
                    disposition=disposition,
                )
            )
        elif disposition == "OPEN_QUESTION":
            problems.extend(
                _validate_refs(
                    entry,
                    "open_question_refs",
                    known_oq_ids,
                    tag=dimension_tag,
                    label="Open Question",
                    required=True,
                )
            )
            problems.extend(
                _reject_fields(
                    entry,
                    ("ac_refs", "scenario_refs", "reason"),
                    tag=dimension_tag,
                    disposition=disposition,
                )
            )
        elif disposition == "OUT_OF_SCOPE":
            if not str(entry.get("reason", "") or "").strip():
                problems.append(
                    f"{dimension_tag}: OUT_OF_SCOPE requires a non-empty reason"
                )
            problems.extend(
                _reject_fields(
                    entry,
                    ("ac_refs", "scenario_refs", "open_question_refs"),
                    tag=dimension_tag,
                    disposition=disposition,
                )
            )

    missing = set(REQUIRED_DIMENSIONS) - seen_dimensions
    if missing:
        problems.append(
            f"{BLOCK_NAME} is missing disposition(s) for: {sorted(missing)}"
        )
    return problems


def validate_manifest(
    manifest,
    *,
    plan_text="",
    ac_ids=None,
    open_question_ids=None,
    scenario_ids=None,
):
    """Validate applicability and content for a complete evidence manifest.

    Strong operational signals require the contract.  Marking the contract inactive
    while such signals remain is also a failure, preventing an ``active: false``
    bypass.  Non-operational manifests may omit the block.
    """
    hits = likely_operational(manifest, plan_text=plan_text)
    if not is_present(manifest):
        if hits:
            return [
                f"{BLOCK_NAME} is required because operational signals were found: {hits}"
            ]
        return []

    block = manifest[BLOCK_NAME]
    problems = validate_operational_contract(
        block,
        ac_ids=ac_ids,
        open_question_ids=open_question_ids,
        scenario_ids=scenario_ids,
    )
    if block.get("active") is False and hits:
        problems.append(
            f"{BLOCK_NAME}.active cannot be false while operational signals remain: {hits}"
        )
    return problems


# Descriptive alias retained for callers that prefer the full contract name.
validate_operational_incident_contract = validate_operational_contract
