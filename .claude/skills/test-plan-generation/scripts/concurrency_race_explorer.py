"""ConcurrencyRaceExplorer - force explicit disposition of 3 recurring race patterns
whenever a fix involves a JCR event listener, Sling job/async consumer, or similar
event-driven mechanism.

WHY THIS EXISTS
---------------
GUIDES-47692 (map-delete parent-property cleanup) had a real, confirmed-unaddressed
race: a topic added to a map that's deleted again before the map's identifier was ever
cached left the cleanup un-run. This was only caught because the class's own Javadoc
happened to call it out - nothing forced the check. The same three race shapes recur
across AEM Guides' JCR-listener/Sling-job features generically:

  CREATE_THEN_DELETE_RACE      - resource created then deleted again before some
                                 cache/index/listener has caught up with the create.
  RESTART_MID_PROCESSING_RACE  - a pod/service restart happens while an event is being
                                 processed, or before in-memory state was persisted.
  DUPLICATE_EVENT_RACE         - the same event fires more than once (retries,
                                 at-least-once delivery) and processing isn't idempotent.

This module is deliberately generic - it does not know what any specific ticket's code
does. It only enforces that IF the behavior model shows an event-driven/async mechanism,
each of the three patterns gets a real disposition (covered by an AC, an Open Question,
or explicitly out of scope with a reason) - never silently unaddressed. Stdlib only.
"""

PATTERNS = ("CREATE_THEN_DELETE_RACE", "RESTART_MID_PROCESSING_RACE", "DUPLICATE_EVENT_RACE")
DISPOSITIONS = ("COVERED_BY_AC", "OPEN_QUESTION", "OUT_OF_SCOPE")

# Soft heuristic only (mirrors comment_claim_verifier's signal style) - used to nudge
# when the behavior model looks event/async-driven but no concurrency_race_analysis block
# was declared. Never a hard failure on its own; detecting "this fix is event-driven"
# reliably needs judgement the gate cannot fully automate.
TRIGGER_PHRASES = (
    "event listener", "jcr event", "node_removed", "property_added", "property_changed",
    "sling job", "job consumer", "async", "asynchronous", "observation listener",
    "in-memory cache", "in memory cache", "bounded cache", "lru",
)


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("concurrency_race_analysis"), dict)


def likely_event_driven(manifest):
    """Best-effort, non-blocking: behavior_model text that looks event/async-driven."""
    bm = manifest.get("behavior_model") if isinstance(manifest, dict) else None
    if not isinstance(bm, dict):
        return []
    haystack_fields = ("operations", "processors", "triggers", "side_effects", "facts")
    texts = []
    for field in haystack_fields:
        val = bm.get(field)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    texts.append(str(item.get("fact", item)))
                else:
                    texts.append(str(item))
    hits = []
    for text in texts:
        lower = text.lower()
        matched = [p for p in TRIGGER_PHRASES if p in lower]
        if matched:
            hits.append(text[:160])
    return hits


def validate_concurrency_race_analysis(block, *, ac_ids=None, open_question_ids=None):
    """Return a list of problem strings; empty list means valid."""
    ac_ids = set(ac_ids or [])
    open_question_ids = set(open_question_ids or [])
    problems = []

    if not isinstance(block, dict):
        return ["concurrency_race_analysis must be an object"]

    active = block.get("active")
    if active is None:
        return ["concurrency_race_analysis.active is required (true/false)"]

    if not active:
        return []  # not event/async-driven - nothing else required

    triggers = block.get("triggers")
    if not isinstance(triggers, list) or not triggers:
        problems.append("concurrency_race_analysis.triggers must be a non-empty list when active is true")

    patterns = block.get("patterns")
    if not isinstance(patterns, list):
        return problems + ["concurrency_race_analysis.patterns must be a list when active is true"]

    seen = set()
    for entry in patterns:
        if not isinstance(entry, dict):
            problems.append(f"pattern entry must be an object: {entry!r}")
            continue
        pattern = entry.get("pattern")
        disposition = entry.get("disposition")
        if pattern not in PATTERNS:
            problems.append(f"unknown or missing pattern: {pattern!r}")
            continue
        seen.add(pattern)
        if disposition not in DISPOSITIONS:
            problems.append(f"{pattern}: disposition must be one of {DISPOSITIONS}, got {disposition!r}")
            continue
        if disposition == "COVERED_BY_AC":
            ac_ref = entry.get("ac_ref")
            if not ac_ref or (ac_ids and ac_ref not in ac_ids):
                problems.append(f"{pattern}: COVERED_BY_AC requires a valid ac_ref (got {ac_ref!r})")
        elif disposition == "OPEN_QUESTION":
            oq_ref = entry.get("open_question_ref")
            if not oq_ref or (open_question_ids and oq_ref not in open_question_ids):
                problems.append(f"{pattern}: OPEN_QUESTION requires a valid open_question_ref (got {oq_ref!r})")
        elif disposition == "OUT_OF_SCOPE":
            if not entry.get("reason"):
                problems.append(f"{pattern}: OUT_OF_SCOPE requires a non-empty reason")

    missing = set(PATTERNS) - seen
    if missing:
        problems.append(f"missing disposition for pattern(s): {sorted(missing)}")

    return problems
