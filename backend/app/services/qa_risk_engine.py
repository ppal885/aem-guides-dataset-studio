"""Risk prediction from ticket text, metadata signals, and related ticket density."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.jira_qa_domain_heuristics import AEM_GUIDES_QA_DOMAIN_KNOWLEDGE
from app.services.llm_service import generate_text, is_llm_available


class QARiskEngine:
    async def predict(
        self,
        *,
        context_blob: str,
        related_hits: list[dict[str, Any]],
        labels: list[str],
        components: list[str],
        customer_context: str | None = None,
        label_context: str | None = None,
    ) -> dict[str, Any]:
        text = (context_blob or "").lower()
        risk_areas: list[str] = []
        impacted: list[str] = []

        sev_terms = ("blocker", "critical", "production", "data loss", "corrupt", "regression", "crash")
        if any(t in text for t in sev_terms):
            risk_areas.append("severity_keywords")
        if any(x in text for x in ("publish", "pdf", "sites", "output")):
            risk_areas.append("publishing_pipeline")
            impacted.append("output_generation")
        if any(x in text for x in ("web editor", "editor", "save", "lock")):
            risk_areas.append("authoring_surface")
        if any(x in text for x in ("conref", "keyref", "xref", "keydef")):
            risk_areas.append("reference_resolution")
            impacted.append("ditamap_topic_linking")
        if any(x in text for x in ("baseline", "version", "compare")):
            risk_areas.append("versioning_baseline")
        if any(x in text for x in ("image", "mime", "dam", "attachment")):
            risk_areas.append("assets")

        score = 0.15
        if "blocker" in text or "production" in text:
            score += 0.35
        if len(related_hits) >= 5:
            score += 0.12
        if len(risk_areas) >= 3:
            score += 0.15
        score = max(0.0, min(1.0, score))

        lab_blob = " ".join(str(x).lower() for x in labels)
        if "customer-escalation" in lab_blob or "p1-escalation" in lab_blob:
            score = min(1.0, score + 0.12)
            risk_areas.append("escalation_label")
        if "regression" in lab_blob or "break-fix" in lab_blob:
            score = min(1.0, score + 0.06)
            risk_areas.append("regression_label")
        if "performance" in lab_blob or "scalability" in lab_blob:
            risk_areas.append("performance_scalability_label")

        if score >= 0.65:
            level = "high"
        elif score >= 0.4:
            level = "medium"
        else:
            level = "low"

        why = (
            f"Signals: {len(related_hits)} related chunks, labels={labels[:4]}, components={components[:4]}, "
            f"risk_areas={risk_areas}."
        )

        out: dict[str, Any] = {
            "risk_level": level,
            "risk_areas": risk_areas,
            "impacted_features": list(dict.fromkeys(impacted))[:12] or list(dict.fromkeys(components))[:8],
            "why": why,
            "confidence": round(0.55 + 0.25 * min(1.0, score), 3),
        }

        if is_llm_available():
            try:
                system = (
                    "You are a QA risk triage assistant for AEM Guides. "
                    'Return JSON only: {"risk_level":"high|medium|low","why":"1-3 sentences",'
                    '"impacted_features":[],"confidence":0-1}. Ground in evidence; if weak evidence, lower confidence.'
                )
                cc = (customer_context or "").strip()
                lc = (label_context or "").strip()
                tail_parts: list[str] = []
                if cc:
                    tail_parts.append(f"### Customer intelligence (indexed corpus; may be partial)\n{cc[:3500]}")
                if lc:
                    tail_parts.append(f"### Label intelligence\n{lc[:3500]}")
                tail = ("\n\n" + "\n\n".join(tail_parts)) if tail_parts else ""
                raw = await generate_text(
                    system,
                    f"{AEM_GUIDES_QA_DOMAIN_KNOWLEDGE[:2000]}\n\nEVIDENCE:\n{context_blob[:7000]}{tail}",
                    max_tokens=350,
                    step_name="jira_copilot_risk",
                )
                raw = raw.strip()
                if "```" in raw:
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                data = json.loads(raw)
                if isinstance(data, dict):
                    rl = str(data.get("risk_level") or "").lower()
                    if rl in {"high", "medium", "low"}:
                        out["risk_level"] = rl
                    if data.get("why"):
                        out["why"] = str(data.get("why"))[:1200]
                    if isinstance(data.get("impacted_features"), list):
                        out["impacted_features"] = [str(x) for x in data["impacted_features"]][:15]
                    conf = float(data.get("confidence") or out["confidence"])
                    out["confidence"] = round(max(0.0, min(1.0, conf)), 3)
            except Exception:
                pass
        return out
