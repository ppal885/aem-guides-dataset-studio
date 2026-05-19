"""Jira-grounded must-test scenario generator (stdlib only)."""

from __future__ import annotations

import re
from typing import Any


def _norm_dedupe(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    t = re.sub(r"^\s*[\d]+[.)]\s+", "", t)
    t = re.sub(r"^\s*[-*•]\s+", "", t)
    return t


def _collect_anchors(enriched_jira: dict, similar_jiras: list) -> tuple[list[str], list[str]]:
    """Return (display anchors for grounding, jira keys)."""
    anchors: list[str] = []
    keys: list[str] = []
    jk = str(enriched_jira.get("jira_key") or "").strip()
    if jk:
        keys.append(jk)

    for field in ("dita_entities", "affected_outputs", "components", "customer_names", "labels"):
        raw = enriched_jira.get(field)
        if not isinstance(raw, list):
            continue
        for x in raw:
            s = str(x).strip()
            if s and s not in anchors:
                anchors.append(s)

    for sim in similar_jiras or []:
        if not isinstance(sim, dict):
            continue
        sk = str(sim.get("jira_key") or "").strip()
        if sk and sk not in keys:
            keys.append(sk)
        for fld in ("matching_entities", "matching_outputs", "matching_customers"):
            arr = sim.get(fld)
            if isinstance(arr, list):
                for x in arr:
                    s = str(x).strip()
                    if s and s not in anchors:
                        anchors.append(s)

    return anchors, keys


def _blob(enriched_jira: dict) -> str:
    parts = [
        str(enriched_jira.get("summary") or ""),
        str(enriched_jira.get("description") or ""),
        " ".join(str(s) for s in (enriched_jira.get("symptoms") or []) if s),
    ]
    return "\n".join(parts).lower()


def _risk_score(enriched_jira: dict, similar_jiras: list) -> int:
    n = 0
    n += len(enriched_jira.get("symptoms") or []) if isinstance(enriched_jira.get("symptoms"), list) else 0
    n += len(enriched_jira.get("qa_risk_tags") or []) if isinstance(enriched_jira.get("qa_risk_tags"), list) else 0
    n += len(similar_jiras or [])
    if enriched_jira.get("customer_names"):
        n += 2
    outs = enriched_jira.get("affected_outputs")
    if isinstance(outs, list) and any("pdf" in str(o).lower() or "publish" in str(o).lower() for o in outs):
        n += 2
    return n


def _pick_primary_anchor(anchors: list[str], seed: int, offset: int) -> str:
    if not anchors:
        return ""
    i = (abs(seed) + offset) % len(anchors)
    return anchors[i]


def _automation_from_fit(raw: str, layer: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("yes", "y", "high", "good", "strong"):
        return "yes"
    if s in ("no", "n", "low", "poor", "none"):
        return "no"
    if s in ("partial", "maybe", "medium", "mixed"):
        return "partial"
    if layer == "API":
        return "yes"
    if layer == "Publishing":
        return "partial"
    if layer == "UI":
        return "partial"
    return "no"


def _priority_from_signals(enriched_jira: dict, idx: int) -> str:
    risk = _risk_score(enriched_jira, [])
    if risk >= 5 or idx == 0:
        return "P0"
    if risk >= 2:
        return "P1"
    return "P2"


def _layer_heuristic(enriched_jira: dict, anchor: str, prefer: str) -> str:
    blob = _blob(enriched_jira) + " " + anchor.lower()
    if prefer in ("UI", "API", "Publishing", "Manual"):
        pass
    else:
        prefer = "Manual"
    if prefer != "Manual":
        return prefer
    if any(k in blob for k in ("api", "rest", "graphql", "servlet", "endpoint", "listener")):
        return "API"
    if any(k in blob for k in ("publish", "dita-ot", "pdf", "html5", "output preset", "fop")):
        return "Publishing"
    if any(k in blob for k in ("editor", "web editor", "ui", "author")):
        return "UI"
    return "Manual"


def _mentions_anchor(text: str, anchor: str, jira_keys: list[str]) -> bool:
    blob = text or ""
    if anchor and anchor in blob:
        return True
    low = blob.lower()
    if anchor and anchor.lower() in low:
        return True
    for k in jira_keys:
        if k and k.upper() in blob.upper():
            return True
    return False


def generate_test_scenarios(enriched_jira: dict, similar_jiras: list) -> list[dict]:
    """
    Produce up to 7 grounded test scenarios. Each references at least one anchor
    (entity, output, component, customer, label, or Jira key).
    """
    if not isinstance(enriched_jira, dict):
        enriched_jira = {}
    if not isinstance(similar_jiras, list):
        similar_jiras = []

    anchors, _ = _collect_anchors(enriched_jira, similar_jiras)
    primary_keys = [str(enriched_jira.get("jira_key") or "").strip()] + [
        str(s.get("jira_key") or "") for s in similar_jiras if isinstance(s, dict) and s.get("jira_key")
    ]
    primary_keys = [k for k in primary_keys if k]

    if not anchors and not primary_keys:
        return []

    work_anchors = list(anchors)
    if not work_anchors and primary_keys:
        work_anchors = [primary_keys[0]]

    seed = hash(primary_keys[0] or "x") % 10000
    similar_sorted = sorted(
        [s for s in similar_jiras if isinstance(s, dict) and s.get("jira_key")],
        key=lambda s: -float((s.get("scores") or {}).get("final") or 0),
    )
    top_similar = similar_sorted[0] if similar_sorted else {}
    top_sim_key = str(top_similar.get("jira_key") or "") if top_similar else ""

    auto_fit = str(enriched_jira.get("automation_fit") or "")
    candidates: list[dict] = []

    def add_scn(
        *,
        title: str,
        pre: str,
        steps: list[str],
        expected: str,
        layer: str,
        evidence: dict[str, Any],
        anchor: str,
        idx: int,
    ) -> None:
        layer_eff = _layer_heuristic(enriched_jira, anchor, layer)
        body = " ".join([title, pre, expected] + steps)
        if not _mentions_anchor(body, anchor, primary_keys):
            return
        candidates.append(
            {
                "title": title[:240],
                "preconditions": pre[:1200],
                "steps": [s[:500] for s in steps],
                "expected_result": expected[:800],
                "test_layer": layer_eff,
                "automation_candidate": _automation_from_fit(auto_fit, layer_eff),
                "evidence": evidence,
                "priority": _priority_from_signals(enriched_jira, idx),
            }
        )

    if top_sim_key:
        a = _pick_primary_anchor(work_anchors, seed, 0)
        add_scn(
            title=f"Regression parity vs {top_sim_key} for {a or 'shared behavior'}",
            pre=f"Environment matches production-like Guides; indexed similar {top_sim_key} as baseline.",
            steps=[
                f"Reproduce current {primary_keys[0]} scope with same map/topics as described.",
                f"Compare outcome to patterns called out for {top_sim_key} (see excerpt).",
                "Capture logs/output artifacts for diff.",
            ],
            expected=f"Behavior aligns with acceptance for {primary_keys[0]}; no unexplained divergence vs {top_sim_key}.",
            layer="Manual",
            evidence={
                "source": "similar_jira",
                "similar_jira_key": top_sim_key,
                "anchors": [x for x in [a, top_sim_key] if x],
            },
            anchor=a or top_sim_key,
            idx=0,
        )

    outs = [str(x) for x in (enriched_jira.get("affected_outputs") or []) if str(x).strip()]
    ents = [str(x) for x in (enriched_jira.get("dita_entities") or []) if str(x).strip()]
    out0 = outs[0] if outs else work_anchors[0]
    ent0 = ents[0] if ents else work_anchors[min(1, len(work_anchors) - 1)]
    add_scn(
        title=f"Publishing edge: {out0} preserves {ent0}",
        pre=f"Corpus includes topics/maps referencing {ent0}; output preset targets {out0}.",
        steps=[
            f"Author or load content stressing {ent0} under real constraints from {primary_keys[0]}.",
            f"Generate {out0} and inspect for lossy transforms.",
            "Re-run with minimal vs expanded map to detect order/size sensitivity.",
        ],
        expected=f"{ent0} appears in output per spec; no silent drops for {out0}.",
        layer="Publishing",
        evidence={"source": "current_jira", "anchors": [out0, ent0]},
        anchor=out0,
        idx=1,
    )

    a = _pick_primary_anchor(work_anchors, seed, 2)
    add_scn(
        title=f"API error handling around {a}",
        pre="Invalid payload or boundary request sizes per ticket symptoms.",
        steps=[
            f"Invoke validation/listener path relevant to {a} with invalid input.",
            "Verify structured error surfaces (no 500-only blob).",
            "Retry with minimal valid payload to confirm recovery.",
        ],
        expected="Failures are diagnosable; service remains stable.",
        layer="API",
        evidence={"source": "current_jira", "anchors": [a]},
        anchor=a,
        idx=2,
    )

    comp = next(
        (str(c) for c in (enriched_jira.get("components") or []) if str(c).strip()),
        work_anchors[min(2, len(work_anchors) - 1)],
    )
    add_scn(
        title=f"UI workflow: {comp} and {primary_keys[0]}",
        pre=f"Web Editor session; user can edit content tied to {comp}.",
        steps=[
            f"Open map/topic referenced in {primary_keys[0]}.",
            f"Exercise insert/replace flows touching {comp}.",
            "Save, reload, verify persistence.",
        ],
        expected="No data loss; UI state matches server after reload.",
        layer="UI",
        evidence={"source": "current_jira", "anchors": [comp]},
        anchor=comp,
        idx=3,
    )

    cust = next((str(x) for x in (enriched_jira.get("customer_names") or []) if str(x).strip()), "")
    if cust:
        a = _pick_primary_anchor(work_anchors, seed, 4)
        add_scn(
            title=f"Customer config sanity: {cust} × {a}",
            pre=f"Tenant/profile reflects {cust}-specific constraints from ticket.",
            steps=[
                f"Apply configuration described for {cust}.",
                f"Validate {a} under that profile.",
                "Compare to default profile for delta.",
            ],
            expected=f"Behavior matches {cust} expectations; deltas documented.",
            layer="Manual",
            evidence={"source": "current_jira", "anchors": [cust, a]},
            anchor=cust,
            idx=4,
        )

    blob = _blob(enriched_jira)
    if "conref" in blob or "keyref" in blob or any("conref" in str(e).lower() for e in ents):
        kw = "conref" if "conref" in blob or any("conref" in str(e).lower() for e in ents) else "keyref"
        add_scn(
            title=f"Link resolution stress: {kw} ({primary_keys[0]})",
            pre="Maps include cross-topic references as in reproduction.",
            steps=[
                f"Break {kw} target temporarily; observe author-time warning.",
                "Restore target; publish/preview and verify resolution.",
                "Rename resource to simulate customer rename drift.",
            ],
            expected="Stable xref/key/conref resolution after corrective actions.",
            layer="Publishing",
            evidence={"source": "current_jira", "anchors": [kw, primary_keys[0]]},
            anchor=kw,
            idx=5,
        )

    if "bson" in blob or "large" in blob or "slow" in blob:
        a = _pick_primary_anchor(work_anchors, seed, 6)
        add_scn(
            title=f"Scale boundary: {a} under load",
            pre="Representative large map from ticket or synthesized to match symptoms.",
            steps=[
                "Open/save cycle with expanded topic set.",
                "Measure save/publish latency vs baseline.",
                "Watch server logs for truncation or size errors.",
            ],
            expected="No silent truncation; acceptable latency or clear failure mode.",
            layer="API",
            evidence={"source": "current_jira", "anchors": [a]},
            anchor=a,
            idx=6,
        )

    seen: set[str] = set()
    out: list[dict] = []
    for c in candidates:
        fp = _norm_dedupe(c["title"] + " " + " ".join(c["steps"]))
        if fp in seen:
            continue
        seen.add(fp)
        out.append(c)

    pri_order = {"P0": 0, "P1": 1, "P2": 2}
    out.sort(key=lambda x: (pri_order.get(x["priority"], 3), x["title"]))
    return out[:7]
