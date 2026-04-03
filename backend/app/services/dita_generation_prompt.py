from __future__ import annotations

import json

from app.services.dita_xml_headers import build_dita_header
from app.services.tenant_service import build_tenant_context


def _content_rules(dita_type: str) -> str:
    if dita_type == "task":
        return "\n".join(
            [
                "- Write a user outcome in the shortdesc, not 'This topic...'.",
                "- Use imperative steps that tell the reader exactly what to do.",
                "- Do not echo Jira bug language like expected result, actual result, workaround, or issue key references.",
                "- End with a concrete user-facing result.",
            ]
        )
    if dita_type == "concept":
        return "\n".join(
            [
                "- Use a subject-oriented title, not a work-item title starting with Add, Fix, Implement, or Update.",
                "- Explain what the capability is, when it matters, and any important scope or constraints.",
                "- Do not write like a bug report or change request.",
            ]
        )
    if dita_type == "reference":
        return "\n".join(
            [
                "- Use a subject-oriented title, not a Jira work item.",
                "- Keep the content factual and structured with concise overview information.",
                "- Remove bug-report wording and focus on the reference facts the reader needs.",
            ]
        )
    return "\n".join(
        [
            "- Write concise user-facing documentation.",
            "- Remove issue-tracker phrasing and bug-report language.",
        ]
    )


def build_generation_prompt(
    *,
    issue: dict,
    intent: dict,
    research: str,
    tenant_id: str = "kone",
    client_knowledge: str = "",
    similar_topics: list[dict] | None = None,
    learned_hints: list[str] | None = None,
    attachment_context: str = "",
    comment_context: str = "",
    evidence_prompt_context: str = "",
    section_evidence_map: dict[str, dict] | None = None,
    grounding_status: str = "",
) -> str:
    tenant_context = build_tenant_context(tenant_id, issue, intent.get("intent_type", ""))
    audience = tenant_context["audience"]
    sections: list[str] = []

    sections.append(
        f"""You are a senior technical writer for {tenant_context['tenant_name']}.
You write production-ready DITA 1.3 documentation for {audience.get('label', 'the target audience')}.
Output XML only. Do not include markdown or commentary."""
    )

    sections.append(
        f"""=== CLIENT CONTEXT ===
Tenant: {tenant_context['tenant_name']}
Product context: {tenant_context['product_context']}
Target audience: {audience.get('label', '')} - {audience.get('description', '')}

What this audience knows:
{chr(10).join(f"- {item}" for item in audience.get('knowledge', [])[:4])}

How to write for this audience:
{chr(10).join(f"- {item}" for item in audience.get('vocabulary', [])[:5])}

Avoid:
{chr(10).join(f"- {item}" for item in audience.get('avoid', [])[:3])}

Step detail level: {audience.get('step_detail', 'standard')}
Shortdesc pattern: {audience.get('shortdesc_pattern', '')}"""
    )

    terminology_rules = tenant_context.get("terminology_rules", [])
    if terminology_rules:
        sections.append(
            f"""=== TERMINOLOGY RULES ===
{chr(10).join(f"- {rule}" for rule in terminology_rules[:12])}

Forbidden generic terms:
{chr(10).join(f"- {term}" for term in tenant_context.get('forbidden_terms', [])[:8])}"""
        )

    sections.append(
        f"""=== WHAT TO WRITE ===
Topic type: {intent.get('intent_type', '').replace('_', ' ')}
DITA type: {intent.get('dita_type', 'task')}
Title: {intent.get('dita_title', '')}
Original Jira title: {intent.get('jira_title', '')}

Context to cover:
{intent.get('context_content') or '(derive the user-facing context from the issue and research)'}

Solution hints:
{chr(10).join(f"- {hint}" for hint in (intent.get('solution_hints') or [])[:6]) or '- Derive the resolution from the validated context.'}

Result section:
{intent.get('result_content') or '(describe the successful end state for the user)'}

Sections to generate:
{', '.join(f'<{section}>' for section in (intent.get('sections') or ['shortdesc', 'context', 'steps', 'result']))}"""
    )

    if research.strip():
        sections.append(f"=== RESEARCH CONTEXT ===\n{research[:3000]}")

    if evidence_prompt_context.strip():
        sections.append(f"=== VERIFIED EVIDENCE ===\n{evidence_prompt_context[:3200]}")

    if section_evidence_map:
        lines = ["=== SECTION EVIDENCE PLAN ==="]
        for section, payload in section_evidence_map.items():
            citation_ids = ", ".join(payload.get("citation_ids") or []) or "none"
            note = payload.get("note") or ""
            lines.append(f"- {section}: {citation_ids}")
            if note:
                lines.append(f"  note: {note}")
        sections.append("\n".join(lines))

    if attachment_context.strip():
        sections.append(f"=== ISSUE ATTACHMENTS ===\n{attachment_context}")

    if comment_context.strip():
        sections.append(f"=== JIRA DISCUSSION ===\n{comment_context[:2200]}")

    if client_knowledge.strip():
        sections.append(f"=== CLIENT KNOWLEDGE BASE ===\n{client_knowledge[:2200]}")

    writing_examples = tenant_context.get("writing_examples") or []
    if writing_examples:
        lines = ["=== WRITING EXAMPLES ==="]
        for example in writing_examples[:3]:
            lines.append(f"[{example.get('type', '').upper()}]")
            lines.append(f"WRONG: {example.get('wrong', '')}")
            lines.append(f"RIGHT: {example.get('right', '')}")
            lines.append(f"RULE: {example.get('rule', '')}")
        sections.append("\n".join(lines))

    if similar_topics:
        lines = ["=== APPROVED TOPIC EXAMPLES ==="]
        for topic in similar_topics[:2]:
            lines.append(f"File: {topic.get('filename', '')}")
            if topic.get("quality_score"):
                lines.append(f"Quality score: {topic.get('quality_score')}")
            preview = (topic.get("content") or "")[:500]
            if preview:
                lines.append(preview)
        sections.append("\n".join(lines))

    if learned_hints:
        sections.append(
            "=== SELF-LEARNING AUTHORING HINTS ===\n"
            + "\n".join(f"- {hint}" for hint in learned_hints[:6])
        )

    style_rules = tenant_context.get("style_rules", "")
    if style_rules:
        sections.append(style_rules)

    conrefs = tenant_context.get("conref_hints") or []
    if conrefs:
        sections.append("=== CONREF HINTS ===\n" + "\n".join(f"- {conref}" for conref in conrefs))

    sections.append(
        f"""=== FINAL OUTPUT ===
Generate a complete, valid DITA 1.3 {intent.get('dita_type', 'task')} topic.
Start exactly with:
{build_dita_header(intent.get('dita_type', 'task'))}
Return XML only.
Sound like a {tenant_context['tenant_name']} technical writer, not a bug report.
Keep terminology consistent with the client rules above.

=== CONTENT QUALITY RULES ===
{_content_rules(intent.get('dita_type', 'task'))}

Preserve product capitalization exactly for terms like AEM, DITA, CircleCI, Experience League, Jira, keyref, and conref.
Translate Jira work-item wording into production-ready documentation wording before you write.
Grounding status for this request: {grounding_status or 'partial'}.
Only add product, version, or workflow details when the verified evidence blocks support them.
If the issue includes a relevant video attachment, reference it with a valid DITA <object> element using the provided cached path."""
    )
    return "\n\n".join(section for section in sections if section.strip())


def build_refinement_prompt(
    *,
    current_dita: str,
    instruction: str,
    issue: dict,
    intent: dict,
    tenant_id: str = "kone",
    learned_hints: list[str] | None = None,
    research: str = "",
    attachment_context: str = "",
    comment_context: str = "",
    similar_topics: list[dict] | None = None,
    evidence_prompt_context: str = "",
    section_evidence_map: dict[str, dict] | None = None,
    grounding_status: str = "",
) -> str:
    tenant_context = build_tenant_context(tenant_id, issue, intent.get("intent_type", ""))
    audience = tenant_context["audience"]
    dita_type = intent.get("dita_type", "task")
    hint_block = ""
    if learned_hints:
        hint_block = "\n".join(f"- {hint}" for hint in learned_hints[:6])
    example_block = ""
    if similar_topics:
        lines = ["Relevant approved examples:"]
        for topic in similar_topics[:2]:
            lines.append(f"- {topic.get('filename', 'example.dita')}")
            preview = (topic.get("content") or "")[:500]
            if preview:
                lines.append(preview)
        example_block = "\n".join(lines)

    return f"""You are refining a DITA topic for {tenant_context['tenant_name']}.

Audience: {audience.get('label', 'target audience')}
Product context: {tenant_context['product_context']}
Instruction: {instruction}

Keep these terminology rules in mind:
{chr(10).join(f"- {rule}" for rule in tenant_context.get('terminology_rules', [])[:8])}

Recurring quality issues to avoid:
{hint_block or "- Preserve valid DITA structure and required elements."}

Current DITA:
{current_dita}

Issue summary:
{issue.get('summary', '')}

Issue context:
{issue.get('description', '')[:700]}

Research context:
{research[:1600] if research else 'Not available'}

Verified evidence:
{evidence_prompt_context[:1800] if evidence_prompt_context else 'No verified evidence blocks available'}

Section evidence plan:
{json.dumps(section_evidence_map or {}, ensure_ascii=True, indent=2)[:1200] if section_evidence_map else 'No section evidence plan available'}

Issue attachments:
{attachment_context[:1200] if attachment_context else 'No attachments available'}

Jira discussion:
{comment_context[:1200] if comment_context else 'No recent Jira comments available'}

Approved examples:
{example_block or 'No approved examples retrieved'}

The XML must start exactly with:
{build_dita_header(dita_type)}

Content quality rules:
{_content_rules(dita_type)}

Mandatory refinement rules:
- Apply the author instruction directly. Do not ignore it.
- If the instruction asks for a title, shortdesc, prerequisite, result, example, note, or clearer steps, the returned XML must contain that change.
- Keep the output DTD-safe for the requested DITA type.
- Preserve any valid existing content unless the instruction clearly replaces it.
- Grounding status: {grounding_status or 'partial'}. Do not invent new version, product, or support claims that are not backed by the verified evidence.

If a relevant video attachment is available, preserve or add a DITA <object> element for it.

Return the complete updated DITA XML only."""


def build_repair_prompt(
    *,
    current_dita: str,
    dita_type: str,
    failed_checks: list[str],
    tenant_id: str,
    issue: dict | None = None,
    learned_hints: list[str] | None = None,
) -> str:
    tenant_context = build_tenant_context(tenant_id, issue or {}, "repair")
    audience = tenant_context["audience"]
    failures = "\n".join(f"- {item}" for item in failed_checks[:10]) or "- The XML quality score is too low."
    hints = "\n".join(f"- {item}" for item in (learned_hints or [])[:6]) or "- Preserve valid structure while repairing missing required elements."
    return f"""You are repairing a DITA topic for {tenant_context['tenant_name']}.

Audience: {audience.get('label', 'target audience')}
Required topic type: {dita_type}

Validation failures to fix:
{failures}

Learned repair hints:
{hints}

Rules:
- Preserve the document intent and the useful content already present.
- Do not return markdown, explanations, or code fences.
- Return a complete DITA document only.
- Ensure the XML starts exactly with:
{build_dita_header(dita_type)}

Current DITA:
{current_dita}
"""


def build_content_polish_prompt(
    *,
    current_dita: str,
    issue: dict,
    intent: dict,
    tenant_id: str,
    research: str = "",
    findings: list[dict] | None = None,
    comment_context: str = "",
    similar_topics: list[dict] | None = None,
) -> str:
    tenant_context = build_tenant_context(tenant_id, issue, intent.get("intent_type", ""))
    dita_type = intent.get("dita_type", "task")
    finding_lines = "\n".join(
        f"- {item.get('message', '')}: {item.get('evidence', '')}"
        for item in (findings or [])[:8]
    ) or "- Improve the title, shortdesc, and content tone."
    example_block = ""
    if similar_topics:
        lines = ["Approved example topics:"]
        for topic in similar_topics[:2]:
            lines.append(f"- {topic.get('filename', 'example.dita')}")
            preview = (topic.get("content") or "")[:500]
            if preview:
                lines.append(preview)
        example_block = "\n".join(lines)

    return f"""You are polishing a DITA topic for {tenant_context['tenant_name']}.

Issue summary:
{issue.get('summary', '')}

Target title:
{intent.get('dita_title', '')}

Target DITA type:
{dita_type}

Quality findings:
{finding_lines}

Research context:
{research[:1800] if research else 'Not available'}

Jira discussion:
{comment_context[:1400] if comment_context else 'No recent Jira comments available'}

Approved examples:
{example_block or 'No approved examples retrieved'}

Rules:
- Keep the topic structurally valid and preserve any good content already present.
- Upgrade the writing so it sounds like production documentation, not a Jira issue.
- For concept and reference topics, remove work-item verbs like Add, Fix, Implement, and Update from the title.
- Rewrite generic shortdescs like 'This topic...' into concise user-facing summaries.
- Remove bug-report language such as expected result, actual result, workaround, defect, and ticket references.
- Preserve product capitalization like AEM, DITA, CircleCI, Experience League, Jira, keyref, and conref.
- Only include version notes when the research actually supports them.
- Return XML only.

The XML must start exactly with:
{build_dita_header(dita_type)}

Current DITA:
{current_dita}
"""
