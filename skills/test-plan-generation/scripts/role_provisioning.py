"""Validate grounded actor and group-provisioning setup for access-control ACs."""

from __future__ import annotations

import re


SCHEMA_VERSION = "aem-guides-role-provisioning-v1"
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_AC_RE = re.compile(
    r"(?m)^- (AC-\d{2}) \[(?:Confirmed|Proposed)\]: "
    r"\((?:Basic|Negative|Integration|Performance)\) Given (?P<given>.*?) \| When "
)
PRIVILEGE_CLASSES = ("FULL_ADMIN", "DELEGATED", "NON_ADMIN")


def _normalise(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _nonempty_strings(value):
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _valid_grounding(value):
    if not _nonempty_strings(value):
        return False
    return all(
        re.search(r":\d+(?:-\d+)?(?:\D|$)", item)
        or re.match(r"(?i)^(RAG|product-doc):", item)
        for item in value
    )


def _actor_matches_given(actor, given):
    normalized_given = _normalise(given)
    aliases = [actor.get("label", ""), actor.get("actor_id", "")]
    aliases.extend(actor.get("grant_groups") or [])
    return any(
        normalized and normalized in normalized_given
        for normalized in (_normalise(alias) for alias in aliases)
    )


def validate_role_provisioning(
    block, *, ac_ids=None, open_question_ids=None, plan_text=""
):
    del open_question_ids
    known_ac_ids = None if ac_ids is None else set(ac_ids)
    if not isinstance(block, dict):
        return ["role_provisioning must be an object"]
    problems = []
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"role_provisioning.schema_version must be {SCHEMA_VERSION}")
    actors = block.get("actors")
    if not isinstance(actors, list) or not actors:
        return problems + ["role_provisioning.actors must be a non-empty list"]

    seen_ids = set()
    valid_actors = []
    for index, actor in enumerate(actors):
        tag = f"role_provisioning.actors[{index}]"
        if not isinstance(actor, dict):
            problems.append(f"{tag} must be an object")
            continue
        actor_id = str(actor.get("actor_id", "")).strip()
        if not _SLUG_RE.fullmatch(actor_id):
            problems.append(f"{tag}.actor_id must be a stable lowercase slug")
        elif actor_id in seen_ids:
            problems.append(f"{tag} duplicates actor_id {actor_id!r}")
        seen_ids.add(actor_id)
        if not str(actor.get("label", "")).strip():
            problems.append(f"{tag}.label must be non-empty")
        privilege_class = actor.get("privilege_class")
        if privilege_class not in PRIVILEGE_CLASSES:
            problems.append(
                f"{tag}.privilege_class must be one of {PRIVILEGE_CLASSES}"
            )
        if not _nonempty_strings(actor.get("grant_groups")):
            problems.append(f"{tag}.grant_groups must be a non-empty string list")
        withhold = actor.get("withhold_groups")
        if not isinstance(withhold, list) or not all(
            isinstance(item, str) and item.strip() for item in withhold
        ):
            problems.append(f"{tag}.withhold_groups must be a string list")
        if privilege_class in {"DELEGATED", "NON_ADMIN"} and not withhold:
            problems.append(
                f"{tag}.withhold_groups must be non-empty for a delegated or non-admin actor"
            )
        if "auto_added_groups" not in actor:
            problems.append(
                f"{tag}.auto_added_groups must be present (use explicit 'none' when empty)"
            )
        else:
            automatic = actor.get("auto_added_groups")
            if automatic != "none" and not (
                isinstance(automatic, list)
                and bool(automatic)
                and all(isinstance(item, str) and item.strip() for item in automatic)
            ):
                problems.append(
                    f"{tag}.auto_added_groups must be a non-empty string list or explicit 'none'"
                )
        grounding = actor.get("grounding")
        if not _valid_grounding(grounding):
            problems.append(
                f"{tag}.grounding must contain only file:line, RAG, or product-doc citations"
            )
        refs = actor.get("maps_to_acs")
        if not _nonempty_strings(refs):
            problems.append(f"{tag}.maps_to_acs must be a non-empty AC reference list")
            refs = []
        for ref in refs:
            if known_ac_ids is not None and ref not in known_ac_ids:
                problems.append(f"{tag}.maps_to_acs contains unknown AC {ref!r}")
        valid_actors.append(actor)

    plan_acs = [(match.group(1), match.group("given")) for match in _AC_RE.finditer(plan_text or "")]
    for ac_id, given in plan_acs:
        if known_ac_ids is not None and ac_id not in known_ac_ids:
            continue
        matching = [actor for actor in valid_actors if _actor_matches_given(actor, given)]
        if not matching:
            problems.append(
                f"{ac_id} has no role_provisioning actor matching its Given clause"
            )
        for actor in matching:
            if ac_id not in set(actor.get("maps_to_acs") or []):
                problems.append(
                    f"{ac_id} references actor {actor.get('actor_id')!r} but maps_to_acs omits it"
                )
    return problems
