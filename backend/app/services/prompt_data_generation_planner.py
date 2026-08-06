"""Prompt-to-data planning for DITA dataset generation.

The normal generator can produce valid DITA, but weak prompts often lose the
testing purpose: what construct is being exercised, which files prove it, what
negative path matters, and what output oracle should be reviewed. This module
extracts those expectations into a compact, reusable plan that can be injected
into both contract-based and freeform generation.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.dita_publishing_construct_registry import (
    detect_output_format as detect_publishing_output_format,
    detect_publishing_constructs,
)
from app.services.dita_query_interpreter import extract_attribute_names, extract_element_names


_NEGATIVE_SIGNAL = re.compile(r"\b(negative|invalid|broken|missing|empty|null|failure|error|warning|edge|risk)\b", re.I)
_DATASET_SIGNAL = re.compile(r"\b(dataset|test data|corpus|bundle|sample|scenario|qa|regression|evidence)\b", re.I)
_PUBLISH_SIGNAL = re.compile(r"\b(pdf|pdf2|html5|html|xhtml|dita-ot|publish|publishing|transform|transformation|output)\b", re.I)


def build_prompt_generation_plan(text: str, *, instructions: str | None = None) -> dict[str, Any]:
    prompt = "\n".join(part for part in [(text or "").strip(), (instructions or "").strip()] if part).strip()
    elements = extract_element_names(prompt)
    attributes = extract_attribute_names(prompt)
    publishing_constructs = detect_publishing_constructs(prompt)
    requested_output = detect_publishing_output_format(prompt, default="")
    wants_dataset = bool(_DATASET_SIGNAL.search(prompt))
    wants_publishing = bool(_PUBLISH_SIGNAL.search(prompt))
    wants_negative = bool(_NEGATIVE_SIGNAL.search(prompt))

    constructs = list(dict.fromkeys([*publishing_constructs, *elements, *[f"@{attr}" for attr in attributes]]))
    artifact_expectations: list[str] = []
    if wants_dataset or wants_publishing or publishing_constructs:
        artifact_expectations.extend(
            [
                "root DITA map",
                "focused source topics for each requested construct",
                "README explaining expected behavior and review steps",
                "manifest with generated files and oracle summary",
            ]
        )
    else:
        artifact_expectations.append("reviewable DITA topic with explicit title, shortdesc, and body")
    if "keys" in publishing_constructs or "keyref" in prompt.lower():
        artifact_expectations.append("map-level key definitions plus consuming topics")
    if any(item in publishing_constructs for item in ("conref", "conkeyref", "conrefpush", "conref-range")):
        artifact_expectations.append("source and consumer topics with stable IDs for reuse resolution")
    if "conditional-processing" in publishing_constructs or {"audience", "platform", "product", "props"} & set(attributes):
        artifact_expectations.append("DITAVAL/profiled topic coverage where filtering behavior is requested")

    oracle_expectations = [
        "observable source-level checks: required elements/attributes must appear in the correct file type",
        "observable content checks: expected marker text must identify each construct in generated output",
    ]
    if wants_publishing:
        oracle_expectations.append("publishing checks: DITA-OT command, exit status, output files, and PDF/HTML5 review areas")
    if requested_output:
        oracle_expectations.append(f"requested output format coverage: {requested_output}")

    negative_cases = []
    if wants_negative or wants_dataset or wants_publishing:
        negative_cases.extend(
            [
                "requested missing target/reference cases must be authored as isolated fixtures",
                "invalid fixtures must run separately so the positive-control build remains reviewable",
            ]
        )
    if "chunk" in publishing_constructs:
        negative_cases.append("invalid chunk tokens such as split/to-navigation must be isolated from valid controls and executed")
    if "copy-to" in publishing_constructs:
        negative_cases.append("duplicate references and copy-to target collisions must be authored and executed when requested")
    if "xref" in publishing_constructs:
        negative_cases.append("broken href/fragment and wrong scope/format risks must be represented or documented")

    plan = {
        "plan_version": "prompt-data-generation-plan/1.0",
        "wants_dataset": wants_dataset,
        "wants_publishing": wants_publishing,
        "requested_output": requested_output or "",
        "detected_constructs": constructs,
        "detected_elements": elements,
        "detected_attributes": attributes,
        "artifact_expectations": list(dict.fromkeys(artifact_expectations)),
        "oracle_expectations": list(dict.fromkeys(oracle_expectations)),
        "negative_or_risk_cases": list(dict.fromkeys(negative_cases)),
        "quality_rules": [
            "Do not create placeholder-only topics; every topic needs realistic AEM Guides or DITA-OT behavior content.",
            "Do not collapse multi-construct prompts into one generic topic; create separate focused controls plus an integration case.",
            "Every generated dataset must explain expected behavior, QA checklist, source files, and confidence limits.",
            "If PDF/HTML5 is requested, generation must be map-based and publishable, not a single isolated topic.",
            "Never replace an explicitly requested negative fixture with a risk note; isolate it, execute it, and report the observed result.",
        ],
    }
    return plan


def render_prompt_generation_plan(plan: dict[str, Any]) -> str:
    if not plan:
        return ""

    def bullets(key: str) -> str:
        values = [str(item).strip() for item in (plan.get(key) or []) if str(item).strip()]
        return "\n".join(f"- {item}" for item in values) or "- none"

    constructs = ", ".join(str(item) for item in (plan.get("detected_constructs") or [])[:20]) or "none"
    output = str(plan.get("requested_output") or "not requested")
    return (
        "Prompt-derived data generation plan:\n"
        f"- Detected constructs: {constructs}\n"
        f"- Requested output: {output}\n"
        "- Artifact expectations:\n"
        f"{bullets('artifact_expectations')}\n"
        "- Oracle expectations:\n"
        f"{bullets('oracle_expectations')}\n"
        "- Negative/risk cases:\n"
        f"{bullets('negative_or_risk_cases')}\n"
        "- Quality rules:\n"
        f"{bullets('quality_rules')}"
    )
