"""UI transitions + flow-path extraction.

A transition records: from_state --(action)--> to_state, with preconditions,
observed effect, evidence, and version. authority is ALWAYS 'OBSERVED_UI_FLOW' -
the crawler saw it happen; it never asserts EXPECTED_PRODUCT_BEHAVIOR.
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict

# Generic transition relation vocabulary (UI-flow, not business-state creation).
RELATION_TYPES = (
    "NAVIGATES_TO", "OPENS", "CLOSES", "EXPANDS", "COLLAPSES", "SELECTS",
    "ENABLES", "DISABLES", "FILTERS", "RESOLVES", "PREVIEWS", "RETURNS_TO",
    "REQUIRES", "PROVIDES_CONTEXT_FOR", "CREATES_UI_STATE", "UPDATES_UI_STATE",
)


@dataclass
class UITransition:
    transition_id: str = ""
    from_state_id: str = ""
    to_state_id: str = ""
    action: dict = field(default_factory=dict)  # {type, capability, control_pattern, target}
    relation: str = "UPDATES_UI_STATE"
    preconditions: list = field(default_factory=list)
    observed_effects: list = field(default_factory=list)
    surface: str = ""
    entity_context: str = ""
    before_screenshot: str = ""
    after_screenshot: str = ""
    captured_at: str = ""
    product_version: str = "UNKNOWN"
    authority: str = "OBSERVED_UI_FLOW"

    def to_dict(self):
        return asdict(self)


def compute_transition_id(from_state_id, action, to_state_id):
    key = json.dumps(
        {"f": from_state_id, "a": action or {}, "t": to_state_id},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def make_transition(from_state, to_state, action, *, relation="UPDATES_UI_STATE",
                    observed_effects=None, preconditions=None, surface="",
                    entity_context="", before_screenshot="", after_screenshot="",
                    captured_at="", product_version="UNKNOWN"):
    tid = compute_transition_id(from_state.state_id, action, to_state.state_id)
    return UITransition(
        transition_id=tid,
        from_state_id=from_state.state_id,
        to_state_id=to_state.state_id,
        action=action,
        relation=relation if relation in RELATION_TYPES else "UPDATES_UI_STATE",
        preconditions=list(preconditions or []),
        observed_effects=list(observed_effects or []),
        surface=surface or getattr(to_state, "surface", ""),
        entity_context=entity_context,
        before_screenshot=before_screenshot,
        after_screenshot=after_screenshot,
        captured_at=captured_at,
        product_version=product_version,
    )


def extract_flow_paths(transitions, *, min_steps=2):
    """Greedy linear-chain extraction: stitch transitions into maximal simple
    paths (state -> action -> state -> action -> ...). Cycles are broken (a state
    is not revisited within one path). Returns a list of flow dicts.

    This is deterministic and evidence-only; the path is labelled OBSERVED_UI_FLOW
    and never as a formal product contract.
    """
    by_from = {}
    indeg = {}
    for t in transitions:
        by_from.setdefault(t.from_state_id, []).append(t)
        indeg[t.to_state_id] = indeg.get(t.to_state_id, 0) + 1
    # Path roots: states that are a 'from' but never a 'to' (or all, if fully cyclic).
    roots = [s for s in by_from if indeg.get(s, 0) == 0] or list(by_from.keys())

    flows = []
    seen_signatures = set()
    for root in roots:
        steps = []
        visited = set()
        cur = root
        while cur in by_from and cur not in visited:
            visited.add(cur)
            t = by_from[cur][0]  # deterministic: first-discovered edge
            steps.append({
                "state": t.from_state_id,
                "action": (t.action or {}).get("capability") or (t.action or {}).get("type", ""),
                "next_state": t.to_state_id,
            })
            cur = t.to_state_id
        if len(steps) >= min_steps:
            sig = json.dumps(steps, sort_keys=True)
            if sig in seen_signatures:
                continue
            seen_signatures.add(sig)
            flows.append({
                "flow_name": "",
                "surface": "",
                "steps": steps,
                "preconditions": [],
                "terminal_state": steps[-1]["next_state"],
                "authority": "OBSERVED_UI_FLOW",
                "evidence_ids": [],
            })
    return flows
