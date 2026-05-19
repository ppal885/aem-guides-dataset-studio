"""Structured test strategy from reasoning + ticket evidence."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.llm_service import generate_text, is_llm_available


class QATestStrategyEngine:
    async def build(
        self,
        *,
        context_blob: str,
        reasoning: dict[str, Any],
        intent: str,
    ) -> dict[str, Any]:
        base: dict[str, Any] = {
            "test_layers": {"unit": [], "api": [], "integration": [], "ui": []},
            "priority_areas": [],
            "data_strategy": [],
            "environment_matrix": [],
            "regression_suite_impact": [],
        }
        tb = reasoning.get("test_strategy") if isinstance(reasoning.get("test_strategy"), list) else []
        for line in tb[:12]:
            s = str(line).lower()
            if "api" in s or "rest" in s or "endpoint" in s:
                base["test_layers"]["api"].append(str(line)[:400])
            elif "ui" in s or "editor" in s or "web" in s:
                base["test_layers"]["ui"].append(str(line)[:400])
            elif "integration" in s or "publish" in s or "pipeline" in s:
                base["test_layers"]["integration"].append(str(line)[:400])
            else:
                base["test_layers"]["unit"].append(str(line)[:400])

        miss = reasoning.get("missing_information") if isinstance(reasoning.get("missing_information"), list) else []
        base["priority_areas"] = [str(x)[:400] for x in (reasoning.get("risk_hypothesis") or [])][:8]
        if not base["priority_areas"]:
            base["priority_areas"] = [str(x)[:400] for x in miss][:6]

        if "mongo" in (context_blob or "").lower() or "bson" in (context_blob or "").lower():
            base["regression_suite_impact"].append("Large topic / BSON limits — add save+reopen stress on representative map.")
        if "baseline" in (context_blob or "").lower():
            base["regression_suite_impact"].append("Baseline/compare workflows after fix.")

        base["data_strategy"] = [
            "Freeze a minimal DITA map + topics reproducing labels/components named in ticket.",
            "Capture anonymized customer corpus only if licensing permits.",
        ]
        base["environment_matrix"] = [
            "Guides + AEM versions from ticket or default LTS matrix.",
            "Web Editor vs Classic/Oxygen if both in support for customer.",
            "Chrome + corporate browser if policy differs.",
        ]

        if is_llm_available() and len(context_blob or "") > 120:
            try:
                system = (
                    "Produce QA test strategy for AEM Guides. JSON ONLY keys: "
                    "test_layers {unit,api,integration,ui arrays of short strings}, "
                    "priority_areas, data_strategy, environment_matrix, regression_suite_impact. "
                    "Max ~5 items per array. Ground in EVIDENCE."
                )
                raw = await generate_text(
                    system,
                    f"INTENT:{intent}\nREASONING_HINTS:{json.dumps(reasoning)[:3500]}\n\nEVIDENCE:\n{context_blob[:8000]}",
                    max_tokens=700,
                    step_name="jira_copilot_test_strategy",
                )
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                data = json.loads(raw)
                if isinstance(data, dict) and isinstance(data.get("test_layers"), dict):
                    tl = data["test_layers"]
                    for k in base["test_layers"]:
                        if isinstance(tl.get(k), list):
                            base["test_layers"][k] = [str(x)[:400] for x in tl[k] if str(x).strip()][:8]
                    for key in ("priority_areas", "data_strategy", "environment_matrix", "regression_suite_impact"):
                        if isinstance(data.get(key), list):
                            base[key] = [str(x)[:400] for x in data[key] if str(x).strip()][:10]
            except Exception:
                pass
        return base
