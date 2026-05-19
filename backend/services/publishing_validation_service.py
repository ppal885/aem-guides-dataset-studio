"""
Deterministic publishing validation intelligence for AEM Guides–related Jira.

Grounds strategies in enrichment (domain, ``dita_entities``, ``affected_outputs``) and
optional similar-ticket rows. No LLM; avoids generic “validate output” phrasing.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from services.uac_generation_service import EvidenceContext, _build_context, _primary_entity
from services.uac.uac_output_parity import _collect_applicable, build_output_parity

_CONSUMER_OUTPUTS = frozenset({"preview", "native_pdf", "aem_sites", "baseline_export"})
_PUBLISHINGish_DOMAINS = frozenset(
    {
        "native_pdf",
        "baseline",
        "glossary",
        "keyref",
        "conref",
        "ditaval",
        "assets",
        "image_rendition",
        "metadata",
        "editor",
    }
)
_DITA_OT_RE = re.compile(
    r"\b(dita-ot|dita\s*ot|dita\s+open\s+toolkit|open\s+toolkit|transtype|ant\s+build|\.ant)\b",
    re.I,
)


def _as_mapping(enriched: JiraEnrichedDocument | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(enriched, JiraEnrichedDocument):
        return enriched.model_dump()
    return enriched


def _evidence_blob(ctx: EvidenceContext) -> str:
    return "\n".join(
        [
            ctx.summary,
            ctx.description,
            str(ctx.enriched.get("raw_text") or ""),
            " ".join(ctx.labels),
            " ".join(ctx.components),
        ]
    )


def _mention_dita_ot(blob: str) -> bool:
    return bool(_DITA_OT_RE.search(blob or ""))


def _output_labels(canonical: str) -> str:
    return {
        "native_pdf": "Native PDF",
        "aem_sites": "AEM Sites",
        "preview": "Web Editor preview",
        "baseline_export": "Baseline export",
        "authoring": "repository / Web Editor source",
    }.get(canonical, canonical.replace("_", " "))


def _entities_clause(ctx: EvidenceContext, *, max_entities: int = 3) -> str:
    parts = [e for e in (ctx.entities or []) if str(e).strip()][:max_entities]
    if not parts:
        return _primary_entity(ctx)
    return ", ".join(parts)


def _outputs_clause(applicable: set[str]) -> str:
    order = ("native_pdf", "aem_sites", "preview", "baseline_export", "authoring")
    labels = [_output_labels(o) for o in order if o in applicable]
    return ", ".join(labels) if labels else _output_labels("native_pdf")


def _in_publishing_scope(ctx: EvidenceContext, similar: list[Mapping[str, Any]], blob: str) -> bool:
    applicable = _collect_applicable(ctx, similar)
    if applicable & _CONSUMER_OUTPUTS:
        return True
    if _mention_dita_ot(blob):
        return True
    if ctx.domain in _PUBLISHINGish_DOMAINS and (ctx.outputs or ctx.entities):
        return True
    return False


def _required_artifacts(
    ctx: EvidenceContext,
    applicable: set[str],
    *,
    dita_ot: bool,
    ent: str,
    jk: str,
) -> list[str]:
    arts: list[str] = []
    if "native_pdf" in applicable:
        arts.append(
            f"{jk}: Native PDF job log or generation report for the map/topic set containing «{ent}» "
            f"(preset id, build timestamp, error/warning summary)."
        )
        arts.append(
            f"{jk}: Delivered PDF binary for acceptance (file name + version) generated after the fix build for «{ent}»."
        )
    if "aem_sites" in applicable:
        arts.append(
            f"{jk}: Published Sites path or content URL where «{ent}» should appear, plus dispatcher/cache "
            f"invalidation evidence if customer-facing."
        )
        arts.append(f"{jk}: Sites JSON/HTML fragment export or author UI capture showing «{ent}» structure post-publish.")
    if "preview" in applicable:
        arts.append(
            f"{jk}: Web Editor map/topic preview capture or shareable preview context for «{ent}» "
            f"(before/after regeneration if applicable)."
        )
    if "baseline_export" in applicable:
        arts.append(
            f"{jk}: Baseline export package (ZIP/OSS manifest) identifier and export profile used for «{ent}», "
            f"not only ad-hoc Latest checkout."
        )
    if dita_ot or _mention_dita_ot(ctx.summary + " " + ctx.description):
        arts.append(
            f"{jk}: DITA-OT console log and output folder for the transtype run that exercises «{ent}» "
            f"(include temp workspace path if Support reproduces locally)."
        )
        arts.append(
            f"{jk}: `*.properties` / Ant args or AEM Guides output preset mapping proving which transtype and "
            f"parameters produced the artifact for «{ent}»."
        )
    if not arts:
        arts.append(
            f"{jk}: At least one concrete generated artifact tied to «{ent}» (PDF, Sites page export, or preview bundle) "
            f"with reproducible generation settings."
        )
    return arts


def _broken_link_checks(ctx: EvidenceContext, applicable: set[str], ent: str, jk: str) -> list[str]:
    outs = _outputs_clause(applicable)
    points = [
        f"{jk}: For «{ent}», crawl outbound links in {outs}: compare unresolved vs resolved href/keyref/conref "
        f"in the generated deliverables (not only source XML)."
    ]
    blob_l = (ctx.summary + " " + ctx.description).lower()
    if "keyref" in blob_l or "keyref" in " ".join(ctx.entities).lower():
        points.append(
            f"{jk}: Validate keyref-backed links in Native PDF annotations vs AEM Sites anchors for «{ent}»; "
            f"mismatches often appear only in one renderer."
        )
    if "conref" in blob_l or "conref" in " ".join(ctx.entities).lower():
        points.append(
            f"{jk}: After conref/conkeyref resolution, open the same topic entry points in {outs} and confirm "
            f"no orphan #fragments for «{ent}»."
        )
    return points


def _metadata_checks(ctx: EvidenceContext, applicable: set[str], ent: str, jk: str) -> list[str]:
    outs = _outputs_clause(applicable)
    return [
        f"{jk}: Compare prolog/metadata on «{ent}» in repository against rendered metadata in {outs} "
        f"(title, shortdesc, critdates, audience/product/platform attrs if profiled).",
        f"{jk}: If search/index is in scope, verify indexed fields for «{ent}» match published {outs} rendition "
        f"(no stale attribute values after republish).",
    ]


def _toc_checks(ctx: EvidenceContext, applicable: set[str], ent: str, jk: str) -> list[str]:
    blob = " ".join(ctx.entities).lower() + " " + ctx.summary.lower()
    if not any(x in blob for x in ("map", "bookmap", "topicref", "chapter", "toc", "nav")):
        return []
    outs = _outputs_clause(applicable)
    return [
        f"{jk}: Compare chapter/topic order and numbering for «{ent}» in Web Editor preview vs Native PDF bookmarks/TOC "
        f"vs AEM Sites navigation for the same map root.",
        f"{jk}: For «{ent}», verify TOC depth limits and excluded branches behave identically across {outs} "
        f"(no silent drop on one side only).",
    ]


def _glossary_checks(ctx: EvidenceContext, applicable: set[str], ent: str, jk: str) -> list[str]:
    if ctx.domain != "glossary" and not any("gloss" in e.lower() for e in ctx.entities):
        return []
    outs = _outputs_clause(applicable)
    return [
        f"{jk}: Publish glossary / glossgroup content for «{ent}» and confirm term status (glossStatus) and "
        f"surface forms in {outs}.",
        f"{jk}: From a non-glossary topic, follow glossterm/glossref to rendered output for «{ent}» in {outs}; "
        f"verify hotstop text matches PDF link destinations vs Sites anchors.",
    ]


def _image_rendering_checks(ctx: EvidenceContext, applicable: set[str], ent: str, jk: str) -> list[str]:
    blob = (ctx.summary + " " + " ".join(ctx.entities)).lower()
    if ctx.domain not in ("assets", "image_rendition") and not any(x in blob for x in ("image", "fig", "svg", "media")):
        return []
    outs = _outputs_clause(applicable)
    return [
        f"{jk}: For figures/images touching «{ent}», compare effective DPI/size/cropping in {outs}; "
        f"flag missing alt text or broken ``@href`` to DAM in the published renditions.",
        f"{jk}: Replace or rotate the underlying asset for «{ent}», republish {outs}, and confirm caches "
        f"(PDF regeneration job vs Sites rendition) pick up the new binary.",
    ]


def _keyref_resolution_checks(ctx: EvidenceContext, applicable: set[str], ent: str, jk: str) -> list[str]:
    if ctx.domain != "keyref" and "keyref" not in " ".join(ctx.entities).lower():
        return []
    outs = _outputs_clause(applicable)
    return [
        f"{jk}: With the same root map/keyscope, resolve «{ent}» in {outs}; capture key definition precedence "
        f"(duplicate key wins) in each pipeline.",
        f"{jk}: Temporarily break a keydef backing «{ent}» and confirm Native PDF job vs Sites publish surfaces "
        f"the expected error/warning contract for this ticket.",
    ]


def _navtitle_checks(ctx: EvidenceContext, applicable: set[str], ent: str, jk: str) -> list[str]:
    blob = " ".join(ctx.entities).lower() + ctx.summary.lower()
    if "navtitle" not in blob and "topicref" not in blob and "map" not in blob:
        return []
    outs = _outputs_clause(applicable)
    return [
        f"{jk}: Where «{ent}» uses ``@navtitle`` (or inherited navtitle), compare visible labels in Web Editor preview, "
        f"PDF TOC/bookmarks, and Sites TOC against DITA source.",
        f"{jk}: Rename navtitle on «{ent}», regenerate {outs}, and verify no stale title remains in cached Sites pages or "
        f"older PDF revisions attached to the ticket.",
    ]


def _conditional_processing_checks(ctx: EvidenceContext, applicable: set[str], ent: str, jk: str) -> list[str]:
    if ctx.domain != "ditaval" and not any(
        x in " ".join(ctx.entities).lower() for x in ("ditaval", "props", "audience", "platform", "product")
    ):
        blob = (ctx.summary + " " + ctx.description).lower()
        if "ditaval" not in blob and "profil" not in blob and "conditional" not in blob:
            return []
    outs = _outputs_clause(applicable)
    return [
        f"{jk}: Apply the ticket’s DITAVAL / profiling combination to «{ent}» and diff included topics/snippets "
        f"across {outs}; confirm no excluded material leaks into customer-visible layers.",
        f"{jk}: Toggle one aud/product/platform flag that touches «{ent}», republish {outs}, and verify conditional "
        f"edges (nested phrases, conkeyref envelopes) stay consistent.",
    ]


def _parity_cross_lines(parity: Mapping[str, Any]) -> list[str]:
    pairs = parity.get("parity_pairs") if isinstance(parity, dict) else None
    if not isinstance(pairs, list):
        return []
    lines: list[str] = []
    for row in pairs:
        if not isinstance(row, dict):
            continue
        src = str(row.get("source") or "")
        tgt = str(row.get("target") or "")
        risk = str(row.get("risk") or "").strip()
        if not src or not tgt:
            continue
        label_a = _output_labels(src)
        label_b = _output_labels(tgt)
        if risk:
            lines.append(f"{label_a} vs {label_b}: {risk}")
        else:
            lines.append(f"{label_a} vs {label_b}: parity acceptance required for this ticket.")
    return lines


def _dedupe_lines(lines: list[str], *, cap: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        t = re.sub(r"\s+", " ", (ln or "").strip())
        if not t:
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= cap:
            break
    return out


def build_publishing_validation_payload(
    enriched: JiraEnrichedDocument | Mapping[str, Any],
    *,
    similar_jiras: Sequence[Mapping[str, Any]] | None = None,
    retrieval_debug: Mapping[str, Any] | None = None,
    max_points: int = 48,
    max_artifacts: int = 14,
    max_parity: int = 14,
    max_high_risk: int = 12,
) -> dict[str, list[str]]:
    """
    Build publishing validation intelligence.

    Returns:
        required_artifacts: concrete deliverables (logs, zips, PDFs, URLs).
        validation_points: merged, specific checks (broken links, metadata, TOC, …).
        cross_output_parity: human-readable cross-output parity expectations.
        high_risk_checks: prioritized subset for UAC triage.
    """
    raw = _as_mapping(enriched)
    similar_list = [dict(x) for x in (similar_jiras or []) if isinstance(x, Mapping)]
    ctx = _build_context(raw, similar_list, retrieval_debug)
    blob = _evidence_blob(ctx)
    empty: dict[str, list[str]] = {
        "required_artifacts": [],
        "validation_points": [],
        "cross_output_parity": [],
        "high_risk_checks": [],
    }

    if not _in_publishing_scope(ctx, similar_list, blob):
        return empty

    jk = ctx.jira_key or "TICKET"
    ent = _entities_clause(ctx)
    applicable = _collect_applicable(ctx, similar_list)
    dita_ot = _mention_dita_ot(blob)

    parity = build_output_parity(ctx, similar_rows=similar_list)
    parity_points = parity.get("validation_points") if isinstance(parity, dict) else []
    parity_points_list = [str(p).strip() for p in (parity_points or []) if str(p).strip()]

    required = _required_artifacts(ctx, applicable, dita_ot=dita_ot, ent=ent, jk=jk)

    category_runs: list[list[str]] = [
        parity_points_list,
        _broken_link_checks(ctx, applicable, ent, jk),
        _metadata_checks(ctx, applicable, ent, jk),
        _toc_checks(ctx, applicable, ent, jk),
        _glossary_checks(ctx, applicable, ent, jk),
        _image_rendering_checks(ctx, applicable, ent, jk),
        _keyref_resolution_checks(ctx, applicable, ent, jk),
        _navtitle_checks(ctx, applicable, ent, jk),
        _conditional_processing_checks(ctx, applicable, ent, jk),
    ]
    flat_points: list[str] = []
    for block in category_runs:
        flat_points.extend(block)

    cross = _parity_cross_lines(parity)

    # High risk: parity lines first, then domain-sensitive bullets
    high: list[str] = []
    high.extend(cross[:5])
    if ctx.domain in ("keyref", "conref"):
        high.extend(_keyref_resolution_checks(ctx, applicable, ent, jk)[:2])
        high.extend(_broken_link_checks(ctx, applicable, ent, jk)[:1])
    if ctx.domain == "ditaval":
        high.extend(_conditional_processing_checks(ctx, applicable, ent, jk)[:2])
    if "native_pdf" in applicable and "aem_sites" in applicable:
        high.append(
            f"{jk}: «{ent}» — Native PDF vs AEM Sites acceptance: verify TOC/bookmark labels, xref targets, "
            f"and media paths do not diverge for the same map root."
        )
    if "baseline_export" in applicable and ("native_pdf" in applicable or "aem_sites" in applicable):
        high.append(
            f"{jk}: «{ent}» — Baseline export snapshot vs live publish: confirm version pins so UAC does not "
            f"accidentally validate Latest-only behavior."
        )
    if dita_ot:
        high.append(
            f"{jk}: DITA-OT transtype run for «{ent}»: treat OT warnings as release-relevant if the ticket "
            f"mentions Open Toolkit or custom plug-ins."
        )

    return {
        "required_artifacts": _dedupe_lines(required, cap=max_artifacts),
        "validation_points": _dedupe_lines(flat_points, cap=max_points),
        "cross_output_parity": _dedupe_lines(cross, cap=max_parity),
        "high_risk_checks": _dedupe_lines(high, cap=max_high_risk),
    }


__all__ = ["build_publishing_validation_payload"]
