"""
Intent Translator — the most critical piece of the whole platform.

Problem it solves:
  Jira issue = "what broke" (developer perspective)
  DITA topic  = "how user fixes it" (user perspective)

Without this, AI copies Jira content verbatim → useless DITA.
With this, AI understands WHAT to write, not just WHAT happened.

The translator does 3 things:
1. Infers authoring intent from issue type + labels + content
2. Transforms Jira fields into DITA-appropriate inputs
   (description → context only, comments → background, NOT steps)
3. Builds a generation brief that tells the LLM:
   "Write a troubleshooting task for the USER who hits this bug.
    Do NOT copy the reproduction steps. Write the FIX."

Place at: backend/app/services/intent_translator.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


# ── Intent types ──────────────────────────────────────────────────────────────

INTENT_TYPES = {
    "troubleshooting_task": {
        "label":       "Troubleshooting task",
        "description": "User-facing fix procedure — HOW the user resolves this error",
        "dita_type":   "task",
        "audience":    "user",
        "verb":        "resolve",
        "sections":    ["shortdesc", "context", "steps", "result", "postreq"],
    },
    "release_note": {
        "label":       "Release note entry",
        "description": "What changed in this version and what users need to know",
        "dita_type":   "concept",
        "audience":    "user",
        "verb":        "understand",
        "sections":    ["shortdesc", "context", "section:what_changed", "section:impact"],
    },
    "feature_concept": {
        "label":       "Feature concept / overview",
        "description": "What this feature is and why users need it",
        "dita_type":   "concept",
        "audience":    "user",
        "verb":        "understand",
        "sections":    ["shortdesc", "conbody", "section", "example"],
    },
    "configuration_task": {
        "label":       "Configuration procedure",
        "description": "Step-by-step how to configure or set up this feature",
        "dita_type":   "task",
        "audience":    "administrator",
        "verb":        "configure",
        "sections":    ["shortdesc", "prereq", "steps", "result", "postreq"],
    },
    "api_reference": {
        "label":       "API / parameter reference",
        "description": "Technical reference for API endpoints, parameters, or config options",
        "dita_type":   "reference",
        "audience":    "developer",
        "verb":        "reference",
        "sections":    ["shortdesc", "refbody", "properties", "section:example"],
    },
    "glossentry": {
        "label":       "Glossary entry",
        "description": "Definition and context for a technical term",
        "dita_type":   "glossentry",
        "audience":    "all",
        "verb":        "define",
        "sections":    ["glossterm", "glossdef", "glossBody"],
    },
}


# ── Field mapping rules ───────────────────────────────────────────────────────

FIELD_MAPPING_RULES = {
    "summary": {
        "maps_to":    "dita_title",
        "transform":  "action_title",    # "Keyref not resolving" → "Resolve Keyref in Nested Keyscope"
        "rule":       "Convert bug/error description to user-facing action verb title",
    },
    "description": {
        "maps_to":    "context_only",
        "transform":  "extract_cause",   # keep WHY it happens, remove HOW to reproduce
        "rule":       "Extract root cause and background. DISCARD reproduction steps entirely.",
    },
    "comments": {
        "maps_to":    "background_context",
        "transform":  "extract_solution_hints",  # dev comments → solution hints for AI
        "rule":       "Extract fix hints and workarounds. Ignore test/QA comments.",
    },
    "acceptance_criteria": {
        "maps_to":    "result_section",
        "transform":  "user_facing_result",
        "rule":       "Convert QA acceptance criteria to user-visible success state.",
    },
    "labels": {
        "maps_to":    "dita_type_and_audience",
        "transform":  "classify",
        "rule":       "Labels determine topic type and target audience.",
    },
    "fix_version": {
        "maps_to":    "version_context",
        "transform":  "version_note",
        "rule":       "Version where fix applies → add as note in DITA.",
    },
}


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class AuthoringIntent:
    """
    The result of intent translation.
    This is what gets passed to the DITA generation prompt —
    NOT the raw Jira fields.
    """
    # What to write
    intent_type:      str       # troubleshooting_task | feature_concept | etc.
    dita_type:        str       # task | concept | reference | glossentry
    audience:         str       # user | administrator | developer

    # Transformed title — user-facing, action verb
    dita_title:       str       # "Resolve Keyref in Nested Keyscope"
    jira_title:       str       # "Keyref not resolving in nested keyscope" (original)

    # Transformed field content — NOT raw Jira content
    context_content:  str       # WHY this happens (from description, stripped of repro steps)
    solution_hints:   list[str] # hints from dev comments about the fix
    result_content:   str       # what success looks like (from acceptance criteria)
    version_note:     str       # which version this applies to

    # Generation guidance — tells LLM exactly what NOT to do
    generation_brief: str       # full prompt section injected before generation

    # Suggested sections in order
    sections:         list[str]

    # Confidence of AI's intent inference
    confidence:       float     # 0.0 - 1.0
    reasoning:        str       # why this intent was chosen

    def to_dict(self) -> dict:
        return {
            "intent_type":     self.intent_type,
            "dita_type":       self.dita_type,
            "audience":        self.audience,
            "dita_title":      self.dita_title,
            "jira_title":      self.jira_title,
            "context_content": self.context_content,
            "solution_hints":  self.solution_hints,
            "result_content":  self.result_content,
            "version_note":    self.version_note,
            "generation_brief": self.generation_brief,
            "sections":        self.sections,
            "confidence":      round(self.confidence, 2),
            "reasoning":       self.reasoning,
        }


@dataclass
class IntentSuggestion:
    """One of potentially multiple intent options shown to author for confirmation."""
    intent_type:  str
    label:        str
    description:  str
    dita_type:    str
    confidence:   float
    reasoning:    str
    is_primary:   bool    # AI's top recommendation

    def to_dict(self) -> dict:
        return {
            "intent_type": self.intent_type,
            "label":       self.label,
            "description": self.description,
            "dita_type":   self.dita_type,
            "confidence":  round(self.confidence, 2),
            "reasoning":   self.reasoning,
            "is_primary":  self.is_primary,
        }


# ── Intent inference ──────────────────────────────────────────────────────────

def infer_intent(issue: dict) -> list[IntentSuggestion]:
    """
    Infer authoring intent from Jira issue.
    Returns ranked list of suggestions for author to confirm.

    Always returns 2-3 options — AI's best guess + alternatives.
    Author picks one, or edits the title and confirms.
    """
    issue_type = (issue.get("issue_type") or "").lower()
    summary    = (issue.get("summary") or "").lower()
    desc       = (issue.get("description") or "").lower()
    labels     = [l.lower() for l in (issue.get("labels") or [])]
    components = [c.lower() for c in (issue.get("components") or [])]
    all_text   = f"{summary} {desc} {' '.join(labels)}"

    scores: dict[str, float] = {}
    reasons: dict[str, str]  = {}

    # ── Rule-based scoring ────────────────────────────────────────────────

    # Bug → troubleshooting task (primary) or release note (secondary)
    if issue_type in ("bug", "defect", "incident"):
        scores["troubleshooting_task"] = scores.get("troubleshooting_task", 0) + 0.7
        reasons["troubleshooting_task"] = f"Bug issue type → user needs fix procedure"
        scores["release_note"] = scores.get("release_note", 0) + 0.3
        reasons["release_note"] = "Bug fix → may also need release note entry"

    # Story → feature concept or API reference
    if issue_type in ("story", "user story", "feature"):
        if any(kw in all_text for kw in ["api", "endpoint", "parameter", "config", "syntax"]):
            scores["api_reference"] = scores.get("api_reference", 0) + 0.7
            reasons["api_reference"] = "Story with API/config keywords → reference topic"
        else:
            scores["feature_concept"] = scores.get("feature_concept", 0) + 0.6
            reasons["feature_concept"] = "Story issue type → feature overview/concept"
        scores["configuration_task"] = scores.get("configuration_task", 0) + 0.3
        reasons["configuration_task"] = "Story may also need configuration procedure"

    # Task → configuration procedure
    if issue_type in ("task", "sub-task", "improvement"):
        scores["configuration_task"] = scores.get("configuration_task", 0) + 0.65
        reasons["configuration_task"] = f"{issue_type} issue type → procedure topic"

    # Label-based overrides (highest confidence signal)
    label_intent_map = {
        "concept":       ("feature_concept",    0.85, "Label 'concept' explicitly set"),
        "overview":      ("feature_concept",    0.80, "Label 'overview' → concept topic"),
        "reference":     ("api_reference",      0.85, "Label 'reference' explicitly set"),
        "api":           ("api_reference",      0.80, "Label 'api' → reference topic"),
        "troubleshoot":  ("troubleshooting_task", 0.90, "Label 'troubleshoot' → task"),
        "howto":         ("configuration_task", 0.85, "Label 'howto' → procedure"),
        "release-note":  ("release_note",       0.90, "Label 'release-note' explicitly set"),
        "glossary":      ("glossentry",         0.95, "Label 'glossary' → glossentry"),
        "term":          ("glossentry",         0.90, "Label 'term' → glossentry"),
        "configuration": ("configuration_task", 0.80, "Label 'configuration' → procedure"),
    }
    for label in labels:
        if label in label_intent_map:
            intent, conf, reason = label_intent_map[label]
            scores[intent] = conf  # label overrides everything
            reasons[intent] = reason

    # Content-based signals
    error_keywords = ["error", "fails", "broken", "not working", "exception", "cannot", "issue"]
    config_keywords = ["configure", "setup", "enable", "install", "create", "add"]
    concept_keywords = ["overview", "understand", "what is", "introduction", "about"]
    api_keywords = ["api", "endpoint", "request", "response", "parameter", "schema"]

    if sum(1 for kw in error_keywords if kw in all_text) >= 2:
        scores["troubleshooting_task"] = max(scores.get("troubleshooting_task", 0), 0.5)
        if "troubleshooting_task" not in reasons:
            reasons["troubleshooting_task"] = "Error keywords in description → fix procedure"

    if sum(1 for kw in config_keywords if kw in all_text) >= 2:
        scores["configuration_task"] = max(scores.get("configuration_task", 0), 0.5)
        if "configuration_task" not in reasons:
            reasons["configuration_task"] = "Config keywords in description → procedure"

    if sum(1 for kw in concept_keywords if kw in all_text) >= 1:
        scores["feature_concept"] = max(scores.get("feature_concept", 0), 0.45)

    if sum(1 for kw in api_keywords if kw in all_text) >= 2:
        scores["api_reference"] = max(scores.get("api_reference", 0), 0.5)

    # Default fallback
    if not scores:
        scores["configuration_task"] = 0.4
        reasons["configuration_task"] = "No clear signals — defaulting to procedure"

    # Sort by score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    suggestions = []

    for i, (intent_type, confidence) in enumerate(ranked[:3]):
        meta = INTENT_TYPES.get(intent_type, {})
        suggestions.append(IntentSuggestion(
            intent_type = intent_type,
            label       = meta.get("label", intent_type),
            description = meta.get("description", ""),
            dita_type   = meta.get("dita_type", "task"),
            confidence  = min(confidence, 1.0),
            reasoning   = reasons.get(intent_type, ""),
            is_primary  = (i == 0),
        ))

    return suggestions


# ── Field transformation ──────────────────────────────────────────────────────

def transform_summary_to_title(summary: str, intent_type: str) -> str:
    """
    Transform Jira issue summary to user-facing DITA title.

    "Keyref not resolving in nested keyscope"
    → "Resolve Keyref in Nested Keyscope"

    "Add support for predictive maintenance dashboard"
    → "Understanding Predictive Maintenance in KONE"
    """
    if not summary:
        return summary

    # Verb maps per intent
    VERB_PREFIXES = {
        "troubleshooting_task": "Resolve",
        "configuration_task":   "Configure",
        "feature_concept":      "Understanding",
        "api_reference":        "",            # keep as-is for reference
        "release_note":         "What's New:",
        "glossentry":           "",
    }

    # Clean up common Jira anti-patterns in summaries
    cleaned = summary.strip()

    # Remove bug-report phrases
    bug_phrases = [
        r"^(bug|defect|fix|issue):\s*",
        r"^(aem-\d+\s*[-:])?\s*",
        r"\s+(is|are)\s+(not|broken|failing|missing)",
        r"\s+(doesn'?t|don'?t|cant'?|cannot)\s+work",
        r"\s+not\s+(working|resolving|loading|showing)",
        r"^(error|exception|problem)\s+(in|with|on)\s+",
    ]
    for pattern in bug_phrases:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    # Title case the cleaned summary
    words = cleaned.split()
    # Preserve known technical terms
    technical_terms = {
        "aem", "dita", "api", "xml", "json", "url", "uri",
        "keyref", "keyscope", "conref", "ditaval",
        "uuid", "id", "kone",
    }
    title_words = [
        w.upper() if w.lower() in technical_terms
        else w.capitalize()
        for w in words
    ]
    title = " ".join(title_words)

    # Add intent-specific prefix
    prefix = VERB_PREFIXES.get(intent_type, "")
    if prefix and not title.lower().startswith(prefix.lower().rstrip(":")):
        # For troubleshooting: "Keyref Not Resolving" → "Resolve Keyref Issue"
        if intent_type == "troubleshooting_task":
            title = f"{prefix} {title}"
        elif intent_type == "feature_concept":
            title = f"{prefix} {title}"
        elif intent_type == "release_note":
            title = f"{prefix} {title}"
        else:
            title = f"{prefix} {title}".strip()

    return title


def extract_context_from_description(description: str) -> str:
    """
    Extract ONLY the root cause / background from Jira description.
    DISCARD: reproduction steps, test data, environment details, stack traces.

    Jira description:
      "Steps to reproduce:
       1. Create child map
       2. Add keydef
       3. Reference from parent
       Expected: keyref resolves
       Actual: keyref not found
       Root cause: Missing keyscope prefix required since 4.2"

    Output (context only):
      "Since AEM Guides 4.2, keyrefs in nested keyscopes require
       an explicit scope prefix in parent maps. This changed from 4.1."
    """
    if not description or len(description) < 30:
        return ""

    lines = description.split("\n")
    context_lines = []
    skip_mode = False

    # Patterns to skip entirely
    skip_start = [
        r"steps to reproduce", r"reproduction steps", r"how to reproduce",
        r"expected (result|behavior|behaviour)",
        r"actual (result|behavior|behaviour)",
        r"environment:", r"version tested:", r"browser:", r"os:",
        r"stack trace", r"error log", r"exception:", r"traceback",
        r"attached:", r"screenshot:", r"see attached",
        r"^\d+\.\s",  # numbered reproduction steps
        r"^-\s+open ", r"^-\s+navigate ", r"^-\s+click ",
    ]

    # Patterns to keep (context/cause)
    keep_patterns = [
        r"root cause", r"cause:", r"reason:", r"because",
        r"background:", r"context:", r"since version", r"since aem",
        r"this (is|was) (introduced|changed|modified)",
        r"in version \d", r"in aem \d",
        r"the (issue|problem|bug) (is|occurs) (because|when|due)",
        r"affects", r"impacts", r"relates to",
        r"workaround:", r"fixed in", r"resolved by",
    ]

    for line in lines:
        line_lower = line.lower().strip()
        if not line_lower:
            continue

        # Check if we hit a skip section header
        if any(re.search(p, line_lower) for p in skip_start[:6]):
            skip_mode = True
            continue

        # Check if we hit a content section after skip
        if skip_mode and any(re.search(p, line_lower) for p in keep_patterns):
            skip_mode = False

        if not skip_mode:
            # Only keep lines that are likely background/cause
            if any(re.search(p, line_lower) for p in keep_patterns):
                context_lines.append(line.strip())
            elif (
                len(line.strip()) > 40
                and not re.match(r"^\d+\.", line.strip())
                and not re.match(r"^[-*]", line.strip())
                and "click" not in line_lower
                and "navigate to" not in line_lower
                and "open the" not in line_lower
            ):
                context_lines.append(line.strip())

    result = " ".join(context_lines)
    result = re.sub(r"\s+", " ", result).strip()

    # Trim to reasonable length
    if len(result) > 600:
        result = result[:600] + "..."

    return result


def extract_solution_hints_from_comments(comments: list[dict]) -> list[str]:
    """
    Extract fix hints from Jira comments.
    Ignore: test results, QA verification, status updates.
    Keep: workarounds, root cause analysis, fix descriptions.

    Comment: "Found root cause — keyscope prefix missing since 4.2 update"
    → Hint: "keyscope prefix required since 4.2 — add child.keyname format"
    """
    if not comments:
        return []

    hints = []
    solution_patterns = [
        r"(fix|solution|workaround|resolved|root cause)[:.]?\s*(.{20,200})",
        r"(you can|you should|user needs to|try)[:.]?\s*(.{20,150})",
        r"(the (fix|change|update) is)[:.]?\s*(.{20,150})",
        r"(this works by|works if|works when)[:.]?\s*(.{20,150})",
        r"(add|change|update|replace|set)\s+.{10,100}(to|with|from)",
    ]

    ignore_authors = ["jenkins", "jira", "automation", "bot", "ci"]
    ignore_patterns = [
        r"verified (in|on) (qa|staging|prod)",
        r"(qa|test) (passed|failed|blocked)",
        r"moving to", r"transitioning", r"status (changed|updated)",
        r"assigned to", r"linked to",
        r"^\+\d",   # +1 comments
    ]

    for comment in comments:
        author = (comment.get("author") or "").lower()
        body   = (comment.get("body_text") or "").strip()

        # Skip bot/automation comments
        if any(ig in author for ig in ignore_authors):
            continue

        # Skip QA/status comments
        if any(re.search(p, body.lower()) for p in ignore_patterns):
            continue

        # Extract solution hints
        for pattern in solution_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE | re.DOTALL)
            for match in matches:
                hint = match[-1].strip() if isinstance(match, tuple) else match.strip()
                hint = re.sub(r"\s+", " ", hint)
                if 20 < len(hint) < 300 and hint not in hints:
                    hints.append(hint)

        # Also keep short, clearly useful sentences
        sentences = re.split(r"[.!?]\s+", body)
        for sent in sentences:
            sent = sent.strip()
            if (
                30 < len(sent) < 200
                and any(kw in sent.lower() for kw in [
                    "prefix", "scope", "attribute", "element", "value",
                    "config", "setting", "flag", "option", "parameter",
                    "keyscope", "keyref", "conref",  # DITA-specific
                ])
            ):
                if sent not in hints:
                    hints.append(sent)

    return hints[:6]


def extract_result_from_acceptance_criteria(description: str, comments: list[dict]) -> str:
    """
    Find acceptance criteria and convert to user-visible success state.

    AC: "Verify keyref resolves in both parent and child map contexts"
    → Result: "Keyrefs resolve correctly across nested keyscope boundaries."
    """
    if not description:
        return ""

    # Look for AC section
    ac_patterns = [
        r"acceptance criteria[:\n](.*?)(?=\n\n|\Z)",
        r"definition of done[:\n](.*?)(?=\n\n|\Z)",
        r"ac[:\n](.*?)(?=\n\n|\Z)",
        r"done when[:\n](.*?)(?=\n\n|\Z)",
    ]

    for pattern in ac_patterns:
        match = re.search(pattern, description, re.IGNORECASE | re.DOTALL)
        if match:
            ac_text = match.group(1).strip()
            # Convert QA language to user language
            ac_text = re.sub(r"^verify\s+that\s+", "", ac_text, flags=re.IGNORECASE)
            ac_text = re.sub(r"^check\s+that\s+", "", ac_text, flags=re.IGNORECASE)
            ac_text = re.sub(r"^test\s+that\s+", "", ac_text, flags=re.IGNORECASE)
            ac_text = re.sub(r"^ensure\s+that\s+", "", ac_text, flags=re.IGNORECASE)
            ac_text = re.sub(r"\s+", " ", ac_text).strip()
            if len(ac_text) > 20:
                # Capitalize first letter, add period if missing
                ac_text = ac_text[0].upper() + ac_text[1:]
                if not ac_text.endswith("."):
                    ac_text += "."
                return ac_text

    return ""


# ── Generation brief builder ──────────────────────────────────────────────────

def build_generation_brief(
    intent:          AuthoringIntent,
    research_context: str = "",
) -> str:
    """
    Build the generation brief injected BEFORE the DITA generation prompt.
    This is the key instruction that prevents AI from copying Jira content.
    """
    intent_meta = INTENT_TYPES.get(intent.intent_type, {})

    brief_parts = [
        f"=== AUTHORING INTENT ===",
        f"You are writing a {intent_meta.get('label', intent.intent_type)} for AEM Guides documentation.",
        f"Target audience: {intent.audience}",
        f"",
        f"=== WHAT TO WRITE ===",
        f"Topic title: {intent.dita_title}",
        f"Original Jira issue: {intent.jira_title} (DO NOT copy this — it is a bug report, not a doc topic)",
        f"",
        f"=== FIELD MAPPING (STRICT) ===",
        f"CONTEXT SECTION: Use this background — do NOT copy Jira description verbatim:",
        f"  {intent.context_content or '(derive from issue — focus on WHY this happens, not HOW to reproduce)'}",
        f"",
    ]

    if intent.solution_hints:
        brief_parts += [
            f"STEPS SECTION: Base the fix steps on these developer hints:",
            *[f"  - {hint}" for hint in intent.solution_hints],
            f"  Write steps from the USER's perspective — what THEY do to fix it.",
            f"  Do NOT write QA reproduction steps.",
            f"",
        ]

    if intent.result_content:
        brief_parts += [
            f"RESULT SECTION: {intent.result_content}",
            f"",
        ]

    if intent.version_note:
        brief_parts += [
            f"VERSION NOTE: This applies to {intent.version_note}",
            f"",
        ]

    brief_parts += [
        f"=== STRICT RULES ===",
        f"1. DO NOT copy Jira description steps — those are for QA, not users",
        f"2. DO NOT mention bug reproduction — write the FIX, not the defect",
        f"3. DO NOT use QA language: 'verify', 'expected result', 'actual result'",
        f"4. DO write from USER perspective: what THEY do, what THEY see",
        f"5. Steps should be actionable: start each cmd with a verb (Open, Click, Update, Verify)",
        f"6. shortdesc must be ONE sentence, max 50 words, user-facing benefit",
        f"",
    ]

    if research_context:
        brief_parts += [
            f"=== RESEARCH CONTEXT (use this for accuracy) ===",
            research_context[:1500],
            f"",
        ]

    brief_parts += [
        f"=== DITA STRUCTURE TO GENERATE ===",
        f"Sections in order: {', '.join(intent.sections)}",
    ]

    return "\n".join(brief_parts)


# ── Main function ─────────────────────────────────────────────────────────────

async def translate_intent(
    issue:            dict,
    chosen_intent:    Optional[str] = None,    # author's confirmed choice
    custom_title:     Optional[str] = None,    # author's edited title
    research_context: str = "",
) -> AuthoringIntent:
    """
    Full intent translation pipeline.

    1. Infer intent (if not provided by author)
    2. Transform all Jira fields
    3. Build generation brief
    4. Return AuthoringIntent ready for DITA generation

    chosen_intent: one of INTENT_TYPES keys, confirmed by author
    custom_title:  author can edit the AI-suggested title before generation
    """
    # Step 1: Determine intent
    if not chosen_intent:
        suggestions = infer_intent(issue)
        chosen_intent = suggestions[0].intent_type if suggestions else "configuration_task"
        confidence = suggestions[0].confidence if suggestions else 0.5
        reasoning  = suggestions[0].reasoning  if suggestions else "Default"
    else:
        confidence = 0.95   # author confirmed → high confidence
        reasoning  = "Author confirmed"

    intent_meta = INTENT_TYPES.get(chosen_intent, INTENT_TYPES["configuration_task"])

    # Step 2: Transform fields
    raw_title  = issue.get("summary", "")
    dita_title = custom_title or transform_summary_to_title(raw_title, chosen_intent)

    description = issue.get("description", "")
    comments    = issue.get("comments", [])

    context_content  = extract_context_from_description(description)
    solution_hints   = extract_solution_hints_from_comments(comments)
    result_content   = extract_result_from_acceptance_criteria(description, comments)

    # Version note from fix_version field
    fix_versions = issue.get("fix_versions", [])
    version_note = fix_versions[0] if fix_versions else ""

    # Try LLM enhancement if available
    try:
        from app.services.llm_service import generate_json, is_llm_available
        if is_llm_available() and not context_content:
            context_content = await _llm_extract_context(issue, chosen_intent)
    except Exception:
        pass

    # Step 3: Build generation brief
    intent = AuthoringIntent(
        intent_type      = chosen_intent,
        dita_type        = intent_meta["dita_type"],
        audience         = intent_meta["audience"],
        dita_title       = dita_title,
        jira_title       = raw_title,
        context_content  = context_content,
        solution_hints   = solution_hints,
        result_content   = result_content,
        version_note     = version_note,
        generation_brief = "",
        sections         = intent_meta["sections"],
        confidence       = confidence,
        reasoning        = reasoning,
    )

    # Build the brief after constructing the intent
    intent.generation_brief = build_generation_brief(intent, research_context)

    logger.info_structured(
        "Intent translated",
        extra_fields={
            "issue_key":    issue.get("issue_key"),
            "intent_type":  chosen_intent,
            "dita_title":   dita_title,
            "confidence":   confidence,
            "hints":        len(solution_hints),
        },
    )
    return intent


async def _llm_extract_context(issue: dict, intent_type: str) -> str:
    """Use LLM to extract context when rule-based extraction yields nothing."""
    from app.services.llm_service import generate_text

    system = f"""You are extracting BACKGROUND CONTEXT from a Jira issue for a DITA documentation topic.
Intent: {intent_type}

Extract ONLY: why this happens, what changed, background the user needs to understand.
DO NOT include: reproduction steps, test data, environment details, stack traces.
Keep it under 150 words. Plain text, no bullets."""

    user = f"""Jira Summary: {issue.get('summary', '')}
Jira Description: {(issue.get('description') or '')[:500]}

Extract the background context for the DITA topic:"""

    try:
        result = await generate_text(system, user, max_tokens=200, step_name="intent_context")
        return result.strip() if result else ""
    except Exception:
        return ""


def get_intent_suggestions(issue: dict) -> list[dict]:
    """Public function for the API endpoint — returns suggestions as dicts."""
    suggestions = infer_intent(issue)
    return [s.to_dict() for s in suggestions]
