"""Validate grounded actor and group-provisioning setup for access-control ACs.

The relationship crosswalk deliberately recognizes only direct, recorded
PRECONDITION neighbors. It cannot infer an indirect authorization dependency
that is absent from the supplied edge list.
"""

from __future__ import annotations

import re


SCHEMA_VERSION = "aem-guides-role-provisioning-v1"
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_AC_RE = re.compile(
    r"(?m)^- (AC-\d{2}) \[(?:Confirmed|Proposed)\]: "
    r"\((?:Basic|Negative|Integration|Performance)\) Given (?P<given>.*?) \| When "
)
PRIVILEGE_CLASSES = ("FULL_ADMIN", "DELEGATED", "NON_ADMIN")
_CODE_FILE_LINE_RE = re.compile(
    r"^(?:[A-Za-z]:)?[\\/]?(?:[^:\\/\r\n]+[\\/])*"
    r"[^:\\/\r\n]+\.(?:"
    r"c|cc|cfg|conf|config|cpp|css|csv|go|groovy|h|hpp|html|ini|java|js|"
    r"json|jsx|jsp|kt|kts|less|php|properties|py|rb|rs|scss|sh|sql|ts|"
    r"tsx|xml|yaml|yml"
    r"):[1-9]\d*(?:-[1-9]\d*)?$",
    re.I,
)
_CHUNK_ID_RE = re.compile(r"^chunk_id:[A-Za-z0-9][A-Za-z0-9._:-]*$")
_ACCESS_GIVEN_RE = re.compile(
    r"\b(?:"
    r"admins?|administrators?|contributors?|reviewers?|publishers?|operators?|"
    r"delegated|non[- ]?admins?|unauthori[sz]ed|authori[sz](?:ed|ation)|"
    r"members?|groups?|roles?|permissions?|privileges?|access|service accounts?"
    r")\b",
    re.I,
)
_AUTH_NEIGHBOR_RE = re.compile(
    r"\b(?:"
    r"admins?|administrators?|authori[sz](?:ed|ation)?|groups?|roles?|"
    r"permissions?|privileges?|access|members?|delegated|non[- ]?admins?"
    r")\b",
    re.I,
)


def _normalise(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _nonempty_strings(value):
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _valid_grounding_item(value):
    text = str(value).strip() if isinstance(value, str) else ""
    return bool(_CODE_FILE_LINE_RE.fullmatch(text) or _CHUNK_ID_RE.fullmatch(text))


def _valid_grounding(value):
    if not _nonempty_strings(value):
        return False
    return all(_valid_grounding_item(item) for item in value)


def _actor_aliases(actor):
    aliases = [
        actor.get("label", ""),
        actor.get("actor_id", ""),
        actor.get("privilege_class", ""),
    ]
    aliases.extend(actor.get("grant_groups") or [])
    automatic = actor.get("auto_added_groups")
    if isinstance(automatic, list):
        aliases.extend(automatic)
    return [alias for alias in aliases if str(alias).strip()]


def _actor_matches_given(actor, given):
    normalized_given = _normalise(given)
    return any(
        normalized and normalized in normalized_given
        for normalized in (_normalise(alias) for alias in _actor_aliases(actor))
    )


def _access_or_actor_given(given, actors):
    return bool(
        _ACCESS_GIVEN_RE.search(str(given))
        or any(_actor_matches_given(actor, given) for actor in actors)
    )


def _actor_matches_neighbor(actor, neighbor):
    normalized_neighbor = _normalise(neighbor)
    if not normalized_neighbor:
        return False
    return any(
        normalized
        and (normalized in normalized_neighbor or normalized_neighbor in normalized)
        for normalized in (_normalise(alias) for alias in _actor_aliases(actor))
    )


def _parse_code_grounding(value):
    text = str(value).strip()
    if not _CODE_FILE_LINE_RE.fullmatch(text):
        return None
    path, line_text = text.rsplit(":", 1)
    start_text, separator, end_text = line_text.partition("-")
    start = int(start_text)
    end = int(end_text) if separator else start
    return path.replace("\\", "/").casefold(), min(start, end), max(start, end)


def _grounding_matches(left, right):
    left_text = str(left).strip()
    right_text = str(right).strip()
    if left_text.casefold() == right_text.casefold():
        return True
    left_code = _parse_code_grounding(left_text)
    right_code = _parse_code_grounding(right_text)
    if left_code is None or right_code is None or left_code[0] != right_code[0]:
        return False
    return left_code[1] <= right_code[2] and right_code[1] <= left_code[2]


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
                f"{tag}.grounding must contain only code file:line or chunk_id:<id> citations"
            )
        refs = actor.get("maps_to_acs")
        if not _nonempty_strings(refs):
            problems.append(f"{tag}.maps_to_acs must be a non-empty AC reference list")
            refs = []
        for ref in refs:
            if known_ac_ids is not None and ref not in known_ac_ids:
                problems.append(f"{tag}.maps_to_acs contains unknown AC {ref!r}")
        valid_actors.append(actor)

    plan_acs = {
        match.group(1): match.group("given")
        for match in _AC_RE.finditer(plan_text or "")
    }
    for actor in valid_actors:
        actor_id = str(actor.get("actor_id", "")).strip() or "?"
        for ac_id in actor.get("maps_to_acs") or []:
            given = plan_acs.get(ac_id)
            if given is not None and not _actor_matches_given(actor, given):
                problems.append(
                    f"role_provisioning actor {actor_id!r} maps to {ac_id}, but that AC's "
                    "Given clause does not name the actor or one of its groups"
                )

    for ac_id, given in plan_acs.items():
        if known_ac_ids is not None and ac_id not in known_ac_ids:
            continue
        matching = [actor for actor in valid_actors if _actor_matches_given(actor, given)]
        if not _access_or_actor_given(given, valid_actors):
            continue
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


def validate_precondition_edges(block, edges, *, ac_ids=None, plan_text=""):
    """Cross-check authorization PRECONDITION edges with provisioned actors.

    The umbrella relationship validator remains responsible for the complete
    edge schema and Open Question references. This helper checks the role block,
    identifies only group/privilege/access PRECONDITION edges, and proves that
    each such edge names a recorded actor or group and shares grounded evidence
    with that actor. A COVERED_BY_AC edge must map to an AC assigned to the same
    actor.
    """
    problems = list(
        validate_role_provisioning(block, ac_ids=ac_ids, plan_text=plan_text)
    )
    if not isinstance(block, dict):
        return problems
    actors = [actor for actor in (block.get("actors") or []) if isinstance(actor, dict)]
    if not actors:
        return problems
    if not isinstance(edges, list):
        return problems + ["relationship edges must be a list for role PRECONDITION validation"]

    auth_edges = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict) or edge.get("relation_type") != "PRECONDITION":
            continue
        neighbor = str(edge.get("neighbor", "")).strip()
        if _AUTH_NEIGHBOR_RE.search(neighbor) or any(
            _actor_matches_neighbor(actor, neighbor) for actor in actors
        ):
            auth_edges.append((index, edge))

    if not auth_edges:
        problems.append(
            "role_provisioning requires at least one auth/group PRECONDITION edge"
        )
        return problems

    known_ac_ids = None if ac_ids is None else set(ac_ids)
    for index, edge in auth_edges:
        tag = f"construct_relationships.edges[{index}]"
        neighbor = str(edge.get("neighbor", "")).strip()
        source = edge.get("source")
        if not _valid_grounding_item(source):
            problems.append(
                f"{tag}.source must be a code file:line or chunk_id:<id> citation"
            )

        matching = [
            actor for actor in actors if _actor_matches_neighbor(actor, neighbor)
        ]
        if not matching:
            problems.append(
                f"{tag} auth/group neighbor {neighbor!r} matches no role_provisioning actor or group"
            )
            continue

        if _valid_grounding_item(source) and not any(
            _grounding_matches(source, grounding)
            for actor in matching
            for grounding in (actor.get("grounding") or [])
        ):
            problems.append(
                f"{tag}.source is not present in the matching actor's grounding"
            )

        if edge.get("disposition") == "COVERED_BY_AC":
            ac_ref = str(edge.get("ac_ref", "")).strip()
            if not ac_ref or (known_ac_ids is not None and ac_ref not in known_ac_ids):
                problems.append(
                    f"{tag} COVERED_BY_AC requires a valid ac_ref"
                )
            elif not any(
                ac_ref in set(actor.get("maps_to_acs") or []) for actor in matching
            ):
                problems.append(
                    f"{tag}.ac_ref {ac_ref!r} is not mapped to the matching actor"
                )
    return problems


def _run_self_tests():
    plan = "\n".join(
        [
            "- AC-01 [Proposed]: (Basic) Given a delegated operator | When access is requested | Then the action is allowed | Evidence: code.",
            "- AC-02 [Proposed]: (Negative) Given a contributor | When access is requested | Then the action is denied | Evidence: code.",
            "- AC-03 [Proposed]: (Basic) Given a document is open | When it is saved | Then its content persists | Evidence: code.",
        ]
    )
    block = {
        "schema_version": SCHEMA_VERSION,
        "actors": [
            {
                "actor_id": "delegated-operator",
                "label": "delegated operator",
                "privilege_class": "DELEGATED",
                "grant_groups": ["profile-operators"],
                "withhold_groups": ["system-administrators"],
                "auto_added_groups": "none",
                "grounding": ["C:/repo/AuthorizationService.java:20-24"],
                "maps_to_acs": ["AC-01"],
            },
            {
                "actor_id": "contributor",
                "label": "contributor",
                "privilege_class": "NON_ADMIN",
                "grant_groups": ["content-contributors"],
                "withhold_groups": ["profile-operators"],
                "auto_added_groups": "none",
                "grounding": ["chunk_id:authorization_contributor"],
                "maps_to_acs": ["AC-02"],
            },
        ],
    }
    ac_ids = {"AC-01", "AC-02", "AC-03"}
    assert validate_role_provisioning(block, ac_ids=ac_ids, plan_text=plan) == []
    bad_grounding = {**block, "actors": [dict(actor) for actor in block["actors"]]}
    bad_grounding["actors"][0]["grounding"] = ["RAG: remembered behavior"]
    assert any(
        "grounding" in problem
        for problem in validate_role_provisioning(
            bad_grounding, ac_ids=ac_ids, plan_text=plan
        )
    )
    missing_actor = {**block, "actors": [block["actors"][0]]}
    assert any(
        "AC-02 has no role_provisioning actor" in problem
        for problem in validate_role_provisioning(
            missing_actor, ac_ids=ac_ids, plan_text=plan
        )
    )
    edge = {
        "relation_type": "PRECONDITION",
        "neighbor": "profile-operators group membership",
        "source": "C:/repo/AuthorizationService.java:22",
        "disposition": "COVERED_BY_AC",
        "ac_ref": "AC-01",
    }
    assert validate_precondition_edges(
        block, [edge], ac_ids=ac_ids, plan_text=plan
    ) == []
    wrong_group = dict(edge)
    wrong_group["neighbor"] = "unlisted-privilege group"
    assert any(
        "matches no role_provisioning actor" in problem
        for problem in validate_precondition_edges(
            block, [wrong_group], ac_ids=ac_ids, plan_text=plan
        )
    )


if __name__ == "__main__":
    _run_self_tests()
    print("ROLE PROVISIONING SELF-TESTS PASSED")
