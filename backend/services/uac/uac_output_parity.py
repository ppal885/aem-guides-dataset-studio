"""Deterministic cross-output parity signals for UAC (no LLM)."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from services.uac_generation_service import (
    DOMAIN_PLAYBOOKS,
    EvidenceContext,
    _json_list,
    _primary_entity,
    _primary_output,
)

_CANONICAL = frozenset({"authoring", "preview", "native_pdf", "aem_sites", "baseline_export"})

# Conservative “A vs B” / divergence cues in Jira narrative (bounded, no user-controlled regex execution).
_CONTRAST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bworks?\b[^.]{0,120}\bbut\b[^.]{0,80}\b(fail|not|doesn|missing|broken)\b", re.I | re.S),
    re.compile(r"\bdiffers?\s+between\b", re.I),
    re.compile(r"\bmissing\s+in\b", re.I),
    re.compile(r"\bnot\s+reflected\s+in\b", re.I),
    re.compile(r"\bin\s+preview\b[^.]{0,160}\b(native\s*pdf|pdf)\b", re.I),
    re.compile(r"\bpreview\b[^.]{0,120}\bfail", re.I),
    re.compile(r"\bnavtitle\b|\btoc\b", re.I),
)

# Ordered candidate pairs (directed); only included if both ends are in the applicable set.
_PAIR_PRIORITY: tuple[tuple[str, str], ...] = (
    ("preview", "native_pdf"),
    ("preview", "aem_sites"),
    ("authoring", "preview"),
    ("authoring", "native_pdf"),
    ("authoring", "aem_sites"),
    ("authoring", "baseline_export"),
    ("baseline_export", "native_pdf"),
    ("baseline_export", "aem_sites"),
    ("baseline_export", "preview"),
    ("native_pdf", "aem_sites"),
)

def _norm_chunk(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _token_to_canonical(raw: str) -> set[str]:
    t = re.sub(r"[\s\-]+", "_", (raw or "").strip().lower())
    t = t.replace("__", "_")
    if not t or t == "output_not_specified":
        return set()
    out: set[str] = set()
    if "baseline" in t:
        out.add("baseline_export")
    if t in ("native_pdf", "nativepdf") or t.startswith("native_pdf"):
        out.add("native_pdf")
    elif "native" in t and "pdf" in t:
        out.add("native_pdf")
    elif t == "pdf" and "native" in raw.lower():
        out.add("native_pdf")

    if t in ("sites", "aem_sites", "html5", "aem_sites_output") or t.endswith("_sites"):
        if "workload" not in t:
            out.add("aem_sites")

    if t in ("editor_preview", "preview", "map_preview", "topic_preview"):
        out.add("preview")

    if t in ("authoring", "web_editor", "source", "editor", "xml_editor"):
        out.add("authoring")

    if not out and t == "pdf":
        out.add("native_pdf")

    return {x for x in out if x in _CANONICAL}


def _playbook_defaults_canonical(domain: str) -> set[str]:
    pb = DOMAIN_PLAYBOOKS.get(domain)
    if not pb:
        return set()
    acc: set[str] = set()
    for d in pb.default_outputs:
        acc |= _token_to_canonical(str(d))
    return acc


def _keyword_boost(blob: str) -> set[str]:
    b = _norm_chunk(blob)
    s: set[str] = set()
    if "preview" in b or "web editor" in b or "in editor" in b:
        s.add("preview")
    if "native pdf" in b or "native_pdf" in b or ("pdf" in b and ("native" in b or "dita-ot" in b or "fop" in b)):
        s.add("native_pdf")
    if "aem sites" in b or re.search(r"\bsites output\b", b) or ("published to" in b and "sites" in b):
        s.add("aem_sites")
    if "baseline" in b or "version snapshot" in b or "versioned content" in b:
        s.add("baseline_export")
    if any(
        x in b
        for x in (
            "save",
            "reload",
            "metadata",
            "prolog",
            "authoring",
            "check in",
            "checkout",
            "dirty metadata",
        )
    ):
        s.add("authoring")
    return {x for x in s if x in _CANONICAL}


def _infer_from_contrast(blob: str) -> set[str]:
    b = _norm_chunk(blob)
    s: set[str] = set()
    if "preview" in b or "editor" in b:
        s.add("preview")
    if ("native" in b and "pdf" in b) or re.search(r"\bpdf\b", b):
        s.add("native_pdf")
    if re.search(r"\bsites\b", b) and "workload" not in b:
        s.add("aem_sites")
    if "baseline" in b:
        s.add("baseline_export")
    if any(x in b for x in ("metadata", "prolog", "web editor")):
        s.add("authoring")
    return {x for x in s if x in _CANONICAL}


def _has_contrast(blob: str) -> bool:
    return any(p.search(blob) for p in _CONTRAST_PATTERNS)


def _collect_applicable(
    ctx: EvidenceContext,
    similar_rows: Sequence[Mapping[str, Any]],
) -> set[str]:
    acc: set[str] = set()
    for o in ctx.outputs:
        acc |= _token_to_canonical(str(o))
    acc |= _playbook_defaults_canonical(ctx.domain)
    for row in similar_rows or ():
        for o in _json_list(row.get("matching_outputs")):
            acc |= _token_to_canonical(str(o))
    blob = " ".join(
        [
            ctx.summary,
            ctx.description,
            str(ctx.enriched.get("raw_text") or ""),
            " ".join(ctx.labels),
        ]
    )
    acc |= _keyword_boost(blob)
    return {x for x in acc if x in _CANONICAL}


def _risk_line(source: str, target: str, domain: str) -> str:
    if source == "preview" and target == "native_pdf":
        return (
            f"Resolution and rendering can differ between Web Editor preview and the Native PDF pipeline "
            f"({domain}); validate {source} vs {target}."
        )
    if source == "preview" and target == "aem_sites":
        return (
            f"Customer Sites output can diverge from editor preview ({domain}); compare visible structure, "
            f"media, and links."
        )
    if source == "authoring" and target == "preview":
        return f"Persisted source/prolog can disagree with preview ({domain}); re-open and compare after save/reload."
    if source == "authoring" and target in ("native_pdf", "aem_sites"):
        return (
            f"Repository-side metadata may not match published {target} ({domain}); verify propagation after publish."
        )
    if source == "authoring" and target == "baseline_export":
        return (
            f"Authoring-time changes may not align with baseline export snapshots ({domain}); compare baseline vs current."
        )
    if source.startswith("baseline") and target in ("native_pdf", "aem_sites", "preview"):
        return (
            f"Baseline export content can differ from live {target} ({domain}); verify version selection and sync."
        )
    if source == "native_pdf" and target == "aem_sites":
        return f"PDF structure/TOC/navlabels can differ from Sites navigation ({domain}); cross-check map and topic titles."
    return f"Cross-output acceptance risk between {source} and {target} for domain {domain}."


def _validation_points(ctx: EvidenceContext, applicable: set[str]) -> list[str]:
    jk = ctx.jira_key or "Ticket"
    ent = _primary_entity(ctx)
    outp = _primary_output(ctx)
    pts: list[str] = []
    if "preview" in applicable and "native_pdf" in applicable:
        pts.append(
            f"{jk}: Resolve or render {ent} in Web Editor preview, regenerate Native PDF, and compare links and text."
        )
    if "preview" in applicable and "aem_sites" in applicable:
        pts.append(
            f"{jk}: Confirm figures/images for {ent} appear in preview and in AEM Sites output with same hrefs."
        )
    if "authoring" in applicable and ("native_pdf" in applicable or "aem_sites" in applicable):
        pts.append(
            f"{jk}: After metadata/prolog edits on {ent}, publish to {outp} and verify attributes appear as expected."
        )
    if "authoring" in applicable and "baseline_export" in applicable:
        pts.append(
            f"{jk}: Compare repository state of {ent} against baseline export; ensure no stale metadata in export."
        )
    if "preview" in applicable and "native_pdf" in applicable and ctx.domain in ("glossary", "keyref", "conref"):
        pts.append(
            f"{jk}: Check navtitle/TOC labels in map preview vs PDF TOC for {ent}."
        )
    if "baseline_export" in applicable and "native_pdf" in applicable:
        pts.append(f"{jk}: Publish Native PDF from baseline snapshot and from latest; diff {ent} behavior.")
    return pts[:7]


def build_output_parity(
    ctx: EvidenceContext,
    *,
    similar_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Return ``parity_required``, ``parity_pairs`` (source/target/risk), and ``validation_points``.

    Uses only evidence on ``ctx`` and structured similar rows (no LLM).
    """
    rows = list(similar_rows or ())
    blob = "\n".join(
        [
            ctx.summary,
            ctx.description,
            str(ctx.enriched.get("raw_text") or ""),
        ]
    )
    applicable = _collect_applicable(ctx, rows)
    contrast = _has_contrast(blob)
    if contrast:
        applicable |= _infer_from_contrast(blob)

    parity_required = len(applicable) >= 2 or contrast
    if not parity_required:
        return {"parity_required": False, "parity_pairs": [], "validation_points": []}

    pairs_out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for src, tgt in _PAIR_PRIORITY:
        if src not in applicable or tgt not in applicable or src == tgt:
            continue
        key = (
            src,
            tgt,
        )
        if key in seen:
            continue
        seen.add(key)
        pairs_out.append({"source": src, "target": tgt, "risk": _risk_line(src, tgt, ctx.domain)})

    points = _validation_points(ctx, applicable)
    return {
        "parity_required": True,
        "parity_pairs": pairs_out,
        "validation_points": points,
    }
