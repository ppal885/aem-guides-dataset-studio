"""
DITA Generation Prompt Builder

This is where everything comes together:
  Intent brief + KONE context + Research context + Style rules
  → One precise prompt that tells the LLM exactly what to write

The prompt has 5 sections in strict order:
  1. ROLE — who the AI is (KONE tech writer, not generic AI)
  2. KONE CONTEXT — product, audience, terminology
  3. INTENT BRIEF — what to write (from intent_translator)
  4. RESEARCH — what is factually true (from RAG + Tavily)
  5. RULES — what NOT to do (prevents Jira copying)

Place at: backend/app/services/dita_generation_prompt.py
"""
from __future__ import annotations

from app.services.kone_knowledge_base import (
    build_kone_context,
    load_custom_kb,
    KONE_STYLE_RULES,
    WRITING_PATTERN_EXAMPLES,
    AUDIENCE_PROFILES,
)


def build_generation_prompt(
    issue:           dict,
    intent:          dict,    # from intent_translator.translate_intent()
    research:        str,     # from query_executor.build_context_for_generation()
    similar_topics:  list[dict] = None,  # approved past topics as style ref
) -> str:
    """
    Build the complete generation prompt for DITA creation.

    This replaces whatever generic prompt was used before.
    The output of this function goes directly to the LLM.
    """
    kone_ctx     = build_kone_context(issue, intent.get("intent_type", ""))
    audience_id  = kone_ctx["audience_id"]
    audience     = kone_ctx["audience"]
    custom_kb    = load_custom_kb()

    sections = []

    # ── Section 1: Role ───────────────────────────────────────────────────────
    sections.append(f"""You are a senior technical writer at KONE, the global elevator and escalator company.
You write precise, accurate DITA documentation for {audience.get('label', 'KONE users')}.
You follow KONE's documentation standards and DITA 1.3 specification strictly.
You never copy developer or QA language into documentation — you always translate it to user language.""")

    # ── Section 2: KONE context ───────────────────────────────────────────────
    sections.append(f"""=== KONE PRODUCT CONTEXT ===
Product: {kone_ctx['product_context']}
Target audience: {audience.get('label', '')} — {audience.get('description', '')}

What this audience knows:
{chr(10).join(f"  - {k}" for k in audience.get('knowledge', [])[:4])}

How to write for this audience:
{chr(10).join(f"  - {v}" for v in audience.get('vocabulary', [])[:5])}

Do NOT include:
{chr(10).join(f"  - {a}" for a in audience.get('avoid', [])[:3])}

Step detail level: {audience.get('step_detail', 'standard')}
Shortdesc pattern: {audience.get('shortdesc_pattern', '')}""")

    # ── Section 3: Terminology rules ──────────────────────────────────────────
    terminology_rules = kone_ctx.get("terminology_rules", [])

    # Merge with custom KB terms
    for generic, specific in custom_kb.get("terms", {}).items():
        terminology_rules.append(f"Use '{specific}' instead of '{generic}'")

    if terminology_rules:
        sections.append(f"""=== TERMINOLOGY (MANDATORY) ===
{chr(10).join(f"  - {rule}" for rule in terminology_rules[:12])}

NEVER USE these generic terms (use KONE-specific equivalents):
{chr(10).join(f"  - '{term}'" for term in kone_ctx.get('forbidden_terms', [])[:6])}""")

    # ── Section 4: Intent brief ───────────────────────────────────────────────
    sections.append(f"""=== WHAT TO WRITE ===
Topic type: {intent.get('intent_type', '').replace('_', ' ')}
DITA type:  {intent.get('dita_type', 'task')}
Title:      {intent.get('dita_title', '')}

Original Jira issue (DO NOT COPY THIS — it is a bug report):
  "{intent.get('jira_title', '')}"

BACKGROUND CONTEXT to use in <context> section:
  {intent.get('context_content') or '(derive from the issue — focus on WHY this affects users, not HOW it was reproduced)'}

SOLUTION HINTS from developer comments (base your steps on these):
{chr(10).join(f"  - {hint}" for hint in (intent.get('solution_hints') or [])[:5]) or '  (derive from research context below)'}

RESULT/SUCCESS STATE for <result> section:
  {intent.get('result_content') or '(describe what working correctly looks like for the user)'}

{f"VERSION NOTE: Add <note> — applies to {intent['version_note']}" if intent.get('version_note') else ''}

Sections to generate (in order):
  {', '.join(f'<{s}>' for s in (intent.get('sections') or ['shortdesc','context','steps','result']))}""")

    # ── Section 5: Research context ───────────────────────────────────────────
    if research and len(research) > 50:
        sections.append(f"""=== FACTUAL RESEARCH (use for accuracy) ===
{research[:2000]}""")

    # ── Section 6: Writing examples ───────────────────────────────────────────
    examples = kone_ctx.get("writing_examples", [])
    if examples:
        ex_lines = ["=== KONE WRITING EXAMPLES (follow these patterns) ==="]
        for ex in examples[:3]:
            ex_lines.append(f"\n[{ex.get('type', '').upper()}]")
            ex_lines.append(f"  WRONG: {ex.get('wrong', '')}")
            ex_lines.append(f"  RIGHT: {ex.get('right', '')}")
            ex_lines.append(f"  RULE:  {ex.get('rule', '')}")
        sections.append("\n".join(ex_lines))

    # ── Section 7: Similar past topics ───────────────────────────────────────
    if similar_topics:
        st_lines = ["=== APPROVED PAST TOPICS (match this style) ==="]
        for topic in similar_topics[:2]:
            st_lines.append(f"\nApproved topic: {topic.get('filename', '')}")
            st_lines.append(f"Quality score: {topic.get('quality_score', '')}/100")
            # Show just the first 400 chars of content as style reference
            content_preview = (topic.get("content") or "")[:400]
            if content_preview:
                st_lines.append(f"Style reference:\n{content_preview}...")
        sections.append("\n".join(st_lines))

    # ── Section 8: KONE style rules ───────────────────────────────────────────
    sections.append(KONE_STYLE_RULES)

    # Add custom rules
    if custom_kb.get("rules"):
        sections.append("=== CUSTOM TEAM RULES ===\n" +
                        "\n".join(f"  - {r}" for r in custom_kb["rules"][:10]))

    # ── Section 9: Conref hints ───────────────────────────────────────────────
    conrefs = kone_ctx.get("conref_hints", [])
    if conrefs:
        sections.append(f"""=== CONREF SUGGESTIONS ===
Consider using these standard KONE conrefs instead of writing from scratch:
{chr(10).join(f"  - {c}" for c in conrefs)}""")

    # ── Section 10: Final output instruction ──────────────────────────────────
    dita_type = intent.get("dita_type", "task")
    title     = intent.get("dita_title", "")

    sections.append(f"""=== GENERATE THIS DITA ===
Generate a complete, valid DITA 1.3 {dita_type} topic.
DOCTYPE: {dita_type}
Title: {title}

Output ONLY the XML — no explanation, no markdown, no commentary.
Start with: <?xml version="1.0" encoding="UTF-8"?>

The topic must:
  1. Sound like it was written by a KONE technical writer — not copied from a bug report
  2. Use KONE product names and terminology throughout
  3. Be written for: {audience.get('label', 'the target audience')}
  4. Follow KONE DITA style guide patterns exactly
  5. Be production-ready — an author should need minimal editing""")

    return "\n\n".join(sections)


def build_refinement_prompt(
    current_dita:   str,
    instruction:    str,
    issue:          dict,
    intent:         dict,
) -> str:
    """
    Build a prompt for refining an existing DITA topic.
    Much shorter than the generation prompt — focused on the specific change.
    """
    kone_ctx    = build_kone_context(issue, intent.get("intent_type", ""))
    audience_id = kone_ctx["audience_id"]
    audience    = AUDIENCE_PROFILES.get(audience_id, {})

    return f"""You are a KONE technical writer refining a DITA topic.

Current DITA:
{current_dita}

Refinement instruction from author:
"{instruction}"

Audience: {audience.get('label', 'KONE user')}
Product: {kone_ctx['product_context']}

Apply the refinement instruction to the DITA above.
Maintain:
  - KONE terminology and product names
  - DITA 1.3 validity
  - The existing structure unless the instruction explicitly changes it
  - The writing style for {audience.get('label', 'this audience')}

Output ONLY the complete updated DITA XML — no explanation."""
