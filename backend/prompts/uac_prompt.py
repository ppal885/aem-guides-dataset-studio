"""Production UAC generation: system-style prompt with grounded evidence context."""

from __future__ import annotations

import json
from typing import Any, Sequence

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services.jira_retrieval_service import RetrievedJira, explain_similarity
from prompts.uac import load_uac_domain_template


def _as_enriched(obj: JiraEnrichedDocument | dict[str, Any]) -> JiraEnrichedDocument:
    if isinstance(obj, JiraEnrichedDocument):
        return obj
    return JiraEnrichedDocument.model_validate(obj)


def _as_retrieved(obj: RetrievedJira | dict[str, Any]) -> RetrievedJira:
    if isinstance(obj, RetrievedJira):
        return obj
    raw = dict(obj) if isinstance(obj, dict) else {}
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    ret = raw.get("retrieval") if isinstance(raw.get("retrieval"), dict) else {}
    why = str(raw.get("why_similar") or ret.get("why_similar") or "")
    score = float(raw.get("score") or ret.get("final_score") or 0.0)
    return RetrievedJira(
        jira_key=str(raw.get("jira_key") or ""),
        title=str(raw.get("title") or meta.get("title") or ""),
        chunk_type=str(raw.get("chunk_type") or meta.get("chunk_type") or ""),
        document=str(raw.get("document") or ""),
        metadata=meta,
        vector_score=float(raw.get("vector_score") or ret.get("vector_score") or 0.0),
        keyword_score=float(raw.get("keyword_score") or ret.get("keyword_score") or 0.0),
        metadata_score=float(raw.get("metadata_score") or ret.get("metadata_score") or 0.0),
        final_score=float(raw.get("final_score") or score),
        why_similar=why,
    )


def _trunc(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _current_jira_facts_block(en: JiraEnrichedDocument) -> str:
    """Compact, deterministic facts for grounding (no instruction leakage)."""
    payload = {
        "jira_key": en.jira_key,
        "summary": _trunc(en.summary, 500),
        "description_excerpt": _trunc(en.description, 6000),
        "issue_type": en.issue_type,
        "status": en.status,
        "priority": en.priority,
        "labels": en.labels[:50],
        "components": en.components[:30],
        "customer_names": en.customer_names[:20],
        "domain": en.domain,
        "sub_domain": en.sub_domain,
        "affected_outputs": en.affected_outputs[:25],
        "affected_features": en.affected_features[:25],
        "dita_entities": en.dita_entities[:40],
        "symptoms": (en.symptoms or [])[:15],
        "expected_behavior_excerpt": _trunc(en.expected_behavior, 1200),
        "actual_behavior_excerpt": _trunc(en.actual_behavior, 1200),
        "qa_risk_tags": en.qa_risk_tags[:30],
        "automation_fit_field": _trunc(en.automation_fit, 200),
        "missing_info_flags": en.missing_info[:15],
        "comments_digest_excerpt": _trunc(en.comments_digest, 2000),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _similar_jira_block(
    rows: Sequence[RetrievedJira],
    current: JiraEnrichedDocument,
    *,
    max_items: int = 5,
) -> str:
    cur = current.model_dump()
    slim: list[dict[str, Any]] = []
    for r in list(rows or [])[:max_items]:
        meta = r.metadata if isinstance(r.metadata, dict) else {}
        expl = explain_similarity(cur, r)
        slim.append(
            {
                **expl,
                "retrieval_scores": {
                    "vector": r.vector_score,
                    "keyword": r.keyword_score,
                    "metadata": r.metadata_score,
                    "final": r.final_score,
                },
                "chunk_excerpt": _trunc(r.document, 900),
                "enrich_sub_domain": str(meta.get("enrich_sub_domain") or ""),
                "enrich_entities_raw": str(meta.get("enrich_entities") or "")[:500],
                "enrich_outputs_raw": str(meta.get("enrich_outputs") or "")[:500],
                "enrich_customers_raw": str(meta.get("enrich_customers") or "")[:400],
            }
        )
    if not slim:
        return "(no similar tickets retrieved — flag weak evidence where applicable)"
    return json.dumps(slim, ensure_ascii=False, indent=2)


def build_uac_prompt(
    current_jira: JiraEnrichedDocument | dict[str, Any],
    similar_jiras: Sequence[RetrievedJira | dict[str, Any]],
    *,
    strict_specificity: bool = False,
) -> str:
    """
    Build a single user prompt (or combined instruction block) for UAC generation.

    The model must follow the output skeleton exactly and ground claims in the
    evidence blocks below.
    """
    en = _as_enriched(current_jira)
    sim = [_as_retrieved(x) for x in (similar_jiras or [])]

    facts = _current_jira_facts_block(en)
    similar = _similar_jira_block(sim, en, max_items=5)
    domain_template = load_uac_domain_template(en.domain)
    domain_template_block = f"\n\n## Domain-specific UAC template\n{domain_template}\n" if domain_template else ""

    strict_extra = ""
    if strict_specificity and en.jira_key:
        sim_nonempty = bool(list(sim or []))
        strict_extra = f"""

## Specificity pass (mandatory — previous draft was too generic)
- The text **must** include the exact current key `{en.jira_key}` at least once (section 1 heading area or a bullet).
- **Banned phrasing** (do not use): "test everything", "validate thoroughly", "general regression", "it depends", "as appropriate", "follow best practices", "ensure quality", "high-level", "all scenarios", bare "TBD" without naming what is unknown.
- **Affected outputs:** copy at least one literal string from `affected_outputs` into section 1 **and** at least one scenario in section 4 **if** that array is non-empty; if empty, keep the insufficient-evidence line.
- **Entities:** copy at least one literal phrase from `dita_entities` **or** a distinctive component / label string from the JSON into section 1 or section 4 **if** those lists are non-empty.
- **Customers / components:** if `customer_names` or `components` is non-empty, mention at least one verbatim value from those arrays somewhere in sections 1–4.
- **Similar tickets:** {"each entry in section 3 must use a real `jira_key` from the similar JSON; section 2 must include at least one `(similar: <KEY>` citation." if sim_nonempty else "if similar JSON is empty, say so plainly once; do not invent keys."}
- **Test layers:** in section 4, at least **three** scenarios must name a concrete `Test Layer` (`UI` | `API` | `Publishing` | `Manual`) with a one-phrase tie to an entity, output, component, customer, or key from evidence.
- **Missing clarifications:** section 5 must reference at least one concrete `missing_info_flags` item verbatim (or state that the array is empty / only `Insufficient evidence` applies).
"""

    return f"""You are a senior QA analyst for Adobe Experience Manager Guides. Produce a User Acceptance Criteria (UAC) readiness brief using **only** the evidence in the JSON blocks below (current issue + similar tickets). Do not invent CRM/customer names, environments, builds, URLs, or ticket keys that are not present in that evidence.
{strict_extra}
{domain_template_block}

If the excerpts are too thin to support a claim, write exactly: Insufficient evidence from indexed Jira data.

## Context-grounding requirement (mandatory)
The `description_excerpt` in the current Jira JSON is the authoritative source of truth for what the bug is.

- **If `actual_behavior_excerpt` and `expected_behavior_excerpt` are both empty or very short:** parse the failure mode directly from `description_excerpt`. Identify the specific incorrect behavior (e.g. "NativePDF displays both the custom text AND the topic title") and the correct expected behavior (e.g. "only the custom text should appear, as it does in AEM Sites and DITA-PDF"). Use these parsed facts to write at least one concrete scenario in section 4.
- **Do NOT substitute generic template phrases** (e.g. "validate output", "test rendering") when the description contains a specific failure. Every must-test scenario must trace to a concrete statement in the description or evidence.
- **Output-specific scenarios:** if the description names multiple outputs that behave differently (e.g. "NativePDF fails but AEM Sites works"), write separate scenarios for each divergent output.

## Evidence — current Jira (ground truth)
```json
{facts}
```

## Evidence — similar historical Jiras (retrieve-ranked; cite when used)
```json
{similar}
```

---

## Required output format (use these headings only, in this order)

Output **only** the following sections. Use Markdown. Be concise; prefer bullets over prose. Do **not** add extra sections, preambles, or closing disclaimers.

### 1. Jira Classification
Use this exact substructure:
- **Domain:** (from evidence: `domain` / `sub_domain`; if unknown use `unknown`)
- **Request Type:** (from evidence: infer from `issue_type`, summary, and description; one short phrase)
- **Customer:** (list names **only** if present under `customer_names` or explicit customer signals in description/labels; otherwise `Insufficient evidence from indexed Jira data.`)
- **Affected Output:** (from `affected_outputs`; if empty, `Insufficient evidence from indexed Jira data.`)
- **Key DITA/AEM Entities:** (from `dita_entities` and concrete terms in description; if none, `Insufficient evidence from indexed Jira data.`)
- **Risk Level:** `Low` | `Medium` | `High` | `Insufficient evidence from indexed Jira data` — pick one; the justification belongs only in section 2.

### 2. Why This Jira Is Risky
- Maximum **5** bullets.
- Each bullet **must** end with a short citation tag in parentheses, e.g. `(current: <field or quote snippet>)` or `(similar: <JIRA-KEY> — <short reason>)`.
- No generic QA platitudes (e.g. "test everything", "validate regression" without naming a concrete artifact from evidence).

### 3. Similar Historical Tickets
- Maximum **5** entries (fewer if evidence lists fewer).
- For **each** entry use exactly this mini-template:

**<JIRA-KEY>**  
- **Similarity reason:** … (grounded in retrieval `why_similar` or your comparison of fields)  
- **What we learned from it:** … (actionable, specific)

If no similar tickets in evidence, write one line: `Insufficient evidence from indexed Jira data.`

### 4. Must-Test Scenarios
- Maximum **7** scenarios.
- For **each** scenario use **exactly** this block (no extra lines inside the block):

```
Scenario: <one line>
Why: <one or two sentences; must reference concrete entity/output/component/customer or Jira key from evidence>
Evidence: <current field/snippet OR similar JIRA-KEY + snippet; if none, say Insufficient evidence from indexed Jira data.>
Test Layer: UI | API | Publishing | Manual (pick one primary)
```

Each scenario **must** mention at least one specific entity, output type, component, customer name **as it appears in evidence**, or a **similar Jira key** from the evidence block.

### 5. Missing Clarifications for UAC
- Maximum **5** questions.
- Each question must reference something concrete missing from the current Jira JSON (version, repro, scope, environment, acceptance metric, dataset, map type, output preset, etc.).
- No generic questions ("Are requirements clear?").

### 6. Automation Fit
Use this exact substructure:
- **Fit:** Yes | No | Partial (one word)
- **Best Layer:** UI | API | Publishing | Manual (one)
- **Reason:** (1–3 sentences; tie to `automation_fit_field`, symptoms, APIs/logs in evidence, or say Insufficient evidence from indexed Jira data.)
- **Suggested test name:** (short snake_case or clear title; must include a concrete anchor from evidence such as component or entity)

---

## Hard rules
1. Do not write generic QA advice unrelated to this ticket’s evidence.
2. Do not repeat the same point across sections; if two bullets would say the same thing, merge or drop one.
3. Prefer short, sharp, actionable phrasing.
4. Every bullet in section 2 and every scenario in section 4 must be clearly tied to **current** or **similar** evidence via citation or inline mention.
5. If similar ticket JSON is empty or unhelpful, state that plainly in section 3 and lean on current Jira only where possible — without fabricating history.

Begin your answer with `### 1. Jira Classification` (no title line before it).
"""
