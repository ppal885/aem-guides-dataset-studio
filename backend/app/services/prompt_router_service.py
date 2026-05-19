from __future__ import annotations

import re
from typing import Any

from app.core.schemas_prompt_router import PromptRouteDecision
from app.services.generate_dita_preview_service import (
    build_generate_dita_execution_contract,
    build_generate_dita_preview,
)

_NON_DITA_AUTOMATION_PATTERN = re.compile(
    r"\b(feature files?|gherkin|cucumber|step definitions?|page objects?|page object|playwright|selenium)\b",
    re.IGNORECASE,
)
_DITA_GENERATION_PATTERN = re.compile(
    r"\b(generate|create|write|draft|make|build|need|want|get|give|send|export|"
    r"produce|prepare|provide|fetch|grab|pull|output|deliver|share|save|show|add)\b"
    r".*\b(dita|tasks?|task topics?|concepts?|concept topics?|references?|reference topics?|"
    r"glossary|glossaries|glossentry|glossentries|topics?|"
    r"zip|bundle|xml|sample|example|template|scaffold|boilerplate|bookmap|reltable|ditamap|maps?)\b",
    re.IGNORECASE,
)
_EXPLICIT_DITA_GENERATION_PATTERN = re.compile(
    r"\b(generate|create|write|draft|make|build|produce|prepare)\b"
    r".*\b(dita|tasks?|task topics?|concepts?|concept topics?|references?|reference topics?|"
    r"glossary|glossaries|glossentry|glossentries|topics?|files?|zip|bundle|dataset|"
    r"demo|example|template|scaffold|boilerplate|bookmap|reltable|ditamap|maps?)\b",
    re.IGNORECASE,
)
_JIRA_STYLE_PATTERN = re.compile(
    r"\b(issue summary|issue description|acceptance criteria|steps to reproduce|expected behavior|actual behavior)\b",
    re.IGNORECASE,
)
_XML_REVIEW_PATTERN = re.compile(
    r"\b(review|fix|validate|correct|repair|audit)\b.*\b(xml|dita|topic|map|ditamap)\b",
    re.IGNORECASE,
)
_DITA_QUESTION_PATTERN = re.compile(
    r"\b(what|how|where|when|why|can|could|should|must|will|would|do|does|is|are|compare|difference|explain)\b.*\b"
    r"(dita|taskbody|conref|conkeyref|keyref|scope|format|chunk|chunking|type|topicref|topichead|topicgroup|mapref|navref|xref|"
    r"choicetables?|reltable|concept|task|reference|glossentry|ditamap|bookmap|related-links|"
    r"related links?|relatedl|linklist|link\s+list|linkinfo|link\s+info|link\s+element|"
    r"foreign\s+element|data-about|data\s+about|boolean\s+element|index-base|index\s+base|itemgroup|item\s+group|"
    r"no-topic-nesting|no\s+topic\s+nesting|state\s+element|unknown\s+element|required-cleanup|required\s+cleanup|"
    r"ditaval\s+elements?|ditaval\s+val|ditaval\s+prop|revprop|startflag|endflag|alt-text|style-conflict|"
    r"id\s+attributes?|metadata\s+attributes?|localization\s+attributes?|debug\s+attributes?|architectural\s+attributes?|"
    r"common\s+map\s+attributes?|cals\s+table\s+attributes?|display\s+attributes?|date\s+attributes?|"
    r"link\s+relationship\s+attributes?|common\s+attributes?|simpletable\s+attributes?|"
    r"xml:lang|xtrf|xtrc|domains|class\s+attribute|"
    r"translate\s+attribute|dir\s+attribute|colsep|rowsep|rowheader|valign|expanse|frame\s+attribute|"
    r"scale\s+attribute|expiry|golive|role\s+attribute|otherrole|base\s+attribute|status\s+attribute|"
    r"keycol|relcolwidth|refcols|indexterm|"
    r"processing-role|collection-type|linking|locktitle|toc|print|keyscope|keys|href|navtitle)\b",
    re.IGNORECASE,
)
_DITA_TERM_PATTERN = re.compile(
    r"</?[A-Za-z][A-Za-z0-9._:-]*>|"
    r"\b(dita|taskbody|conref|conkeyref|keyref|scope|format|chunk|chunking|type|topicref|topichead|topicgroup|mapref|navref|xref|"
    r"choicetables?|reltable|concept|task|reference|glossentry|ditamap|bookmap|related-links|"
    r"related links?|relatedl|linklist|link\s+list|linkinfo|link\s+info|link\s+element|"
    r"foreign\s+element|data-about|data\s+about|boolean\s+element|index-base|index\s+base|itemgroup|item\s+group|"
    r"no-topic-nesting|no\s+topic\s+nesting|state\s+element|unknown\s+element|required-cleanup|required\s+cleanup|"
    r"ditaval\s+elements?|ditaval\s+val|ditaval\s+prop|revprop|startflag|endflag|alt-text|style-conflict|"
    r"id\s+attributes?|metadata\s+attributes?|localization\s+attributes?|debug\s+attributes?|architectural\s+attributes?|"
    r"common\s+map\s+attributes?|cals\s+table\s+attributes?|display\s+attributes?|date\s+attributes?|"
    r"link\s+relationship\s+attributes?|common\s+attributes?|simpletable\s+attributes?|"
    r"xml:lang|xtrf|xtrc|domains|class\s+attribute|"
    r"translate\s+attribute|dir\s+attribute|colsep|rowsep|rowheader|valign|expanse|frame\s+attribute|"
    r"scale\s+attribute|expiry|golive|role\s+attribute|otherrole|base\s+attribute|status\s+attribute|"
    r"keycol|relcolwidth|refcols|indexterm|"
    r"processing-role|collection-type|linking|locktitle|toc|print|keyscope|keys|href|navtitle)\b",
    re.IGNORECASE,
)
_DITA_ANSWER_INTENT_PATTERN = re.compile(
    r"^\s*(what|how|where|when|why|which|should|must|will|would|do|does|can|could|explain|define)\b|"
    r"\b(?:and\s+then|then|and|also)\s+(?:explain|define)\b|"
    r"\b(compare|difference\s+between|versus|vs\.?)\b",
    re.IGNORECASE,
)
_DITA_EXAMPLE_ANSWER_PATTERN = re.compile(
    r"\b(give|show|share|provide|can\s+you\s+show|could\s+you\s+show)\b"
    r".*\b(examples?|samples?|snippets?|xml\s+examples?)\b|"
    r"\b(examples?|samples?|snippets?|xml\s+examples?)\b.*\b(of|for)\b",
    re.IGNORECASE,
)
_DITA_EXAMPLE_GENERATION_ARTIFACT_PATTERN = re.compile(
    r"\b(generate|create|write|draft|make|build|produce|prepare)\b|"
    r"\b(files?|zip|bundle|dataset|topics?|ditamap|bookmap|full\s+demo|minimal\s+demo|demo\s+bundle)\b",
    re.IGNORECASE,
)
_DITA_RELATED_LINKS_TOC_QUERY_PATTERN = re.compile(
    r"(?=.*\b(?:toc|table\s+of\s+contents|pdf|pdf\s+output)\b)"
    r"(?=.*\b(?:linklist|link\s+list|related-links|related\s+links?)\b)"
    r"(?=.*\btitle\b)",
    re.IGNORECASE,
)
_DITA_OUTPUT_TARGET_PATTERN = re.compile(
    r"\b(pdf|native\s+pdf|web|html|html5|aem\s+sites?|browser|dita-ot|output|outputs|publish|publishing)\b",
    re.IGNORECASE,
)
_DITA_OUTPUT_CONSTRUCT_PATTERN = re.compile(
    r"</?[A-Za-z][A-Za-z0-9._:-]*>|"
    r"\b(taskbody|conref|conkeyref|keyref|topicref|topichead|topicgroup|mapref|navref|xref|choicetables?|reltable|glossentry|"
    r"ditamap|bookmap|related-links|related\s+links?|relatedl|linklist|link\s+list|linkinfo|"
    r"foreign|foreign\s+element|data-about|data\s+about|boolean\s+element|index-base|"
    r"itemgroup|item\s+group|no-topic-nesting|state\s+element|unknown\s+element|required-cleanup|"
    r"ditaval\s+elements?|ditaval\s+val|ditaval\s+prop|revprop|startflag|endflag|alt-text|style-conflict|"
    r"id\s+attributes?|metadata\s+attributes?|localization\s+attributes?|debug\s+attributes?|architectural\s+attributes?|"
    r"common\s+map\s+attributes?|cals\s+table\s+attributes?|display\s+attributes?|date\s+attributes?|"
    r"link\s+relationship\s+attributes?|common\s+attributes?|simpletable\s+attributes?|"
    r"xml:lang|xtrf|xtrc|domains|class\s+attribute|"
    r"translate\s+attribute|dir\s+attribute|colsep|rowsep|rowheader|valign|expanse|frame\s+attribute|"
    r"scale\s+attribute|expiry|golive|role\s+attribute|otherrole|base\s+attribute|status\s+attribute|"
    r"keycol|relcolwidth|refcols|"
    r"processing-role|collection-type|locktitle|keyscope|navtitle)\b",
    re.IGNORECASE,
)
_ASSISTIVE_GENERATION_REQUEST_PATTERN = re.compile(
    r"^\s*(can|could|would)\s+you\s+"
    r"(generate|create|write|draft|make|build|produce|prepare)\b",
    re.IGNORECASE,
)
_AEM_GUIDES_PATTERN = re.compile(
    r"\b(aem guides|guides web editor|web editor|author view|map console|output preset|native pdf|experience manager)\b",
    re.IGNORECASE,
)
_QUESTION_LED_PRODUCT_PATTERN = re.compile(
    r"^\s*(how|what|where|when|why|can|does|is|are|which|who)\b",
    re.IGNORECASE,
)
_NATIVE_PDF_PATTERN = re.compile(
    r"\b(native pdf|pdf output|pdf preset|output preset|toc styling|page layout|headers?|footers?|watermark)\b",
    re.IGNORECASE,
)
# DITA-OT / toolkit: engine id + build-parameter intent (tolerates typos like "Argumernts").
_DITA_OT_ENGINE_PATTERN = re.compile(
    r"\b(dita[-\s]?ot|dita\s+open\s+toolkit|open\s+toolkit)\b|\bargs\.[a-z][a-z0-9._-]+\b",
    re.IGNORECASE,
)
_DITA_OT_BUILD_PARAM_PATTERN = re.compile(
    r"\b(arguments?|argu\w{0,16}nts?|parameters?|params?|command[-\s]?line|build\s+properties)\b"
    r"|\b(what|which)\b.{0,100}\b(given|give|pass|set|use|specify|add|need|required)\b"
    r"|\b(given|give|pass|set|specify)\b.{0,120}\b(dita[-\s]?ot|open\s+toolkit)\b"
    r"|\bdraft[-\s]?comments?|draft\.comments?\b",
    re.IGNORECASE,
)
# Backward-compatible name: any strong DITA-OT / args.* signal (used with Native PDF heuristics).
_DITA_OT_ARGUMENT_PATTERN = re.compile(
    r"\b(dita[-\s]?ot|dita\s+open\s+toolkit|open\s+toolkit|args?\.draft|args?\b|arguments?|argu\w{0,16}nts?|"
    r"parameters?|params?|draft[-\s]?comments?|draft\.comments?)\b",
    re.IGNORECASE,
)
_DATASET_JOB_PATTERN = re.compile(
    r"\b(job|dataset|recipe)\b.*\b(status|history|create|run|start|list|browse)\b|"
    r"\b(create|run|start|browse|list)\b.*\b(job|dataset|recipe)\b",
    re.IGNORECASE,
)
_SCREENSHOT_PATTERN = re.compile(
    r"\b(screenshot|image|screen grab|screen capture)\b",
    re.IGNORECASE,
)
_ARTIFACT_PATTERN = re.compile(
    r"\b(flowchart|mermaid|svg|image|diagram)\b",
    re.IGNORECASE,
)


def _clean_intent_segment(text: str) -> str:
    segment = " ".join(str(text or "").split()).strip(" ,.;:-")
    segment = re.sub(r"^(?:and\s+then|then|and|also|please)\s+", "", segment, flags=re.IGNORECASE).strip(" ,.;:-")
    segment = re.sub(r"\s+(?:and\s+then|then|and|also|please)$", "", segment, flags=re.IGNORECASE).strip(" ,.;:-")
    return segment


def _wants_downloadable_dita_bundle(text: str) -> bool:
    """True when the user asks for a downloadable zip/archive, not a spec definition of 'zip'."""
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    strong = re.search(
        r"\b(\.zip\b|in\s+zip|to\s+zip|as\s+(a\s+)?zip|zip\s+file|zip\s+archive|"
        r"zip\s+download|download\s+(a\s+)?zip|generated\s+in\s+zip)\b",
        low,
    )
    weak_zip = bool(re.search(r"\bzip\b", low))
    gen_verb = bool(
        re.search(
            r"\b(generate|generating|generated|create|creating|created|build|building|built|"
            r"export|exporting|want|need|give\s+me|send\s+me)\b",
            low,
        )
    )
    questionable = t.rstrip().endswith("?") and bool(_DITA_ANSWER_INTENT_PATTERN.search(t))
    if strong:
        if questionable and not gen_verb:
            return False
        return True
    if weak_zip and gen_verb:
        if questionable:
            return False
        return True
    return False


def _mixed_dita_intent_parts(text: str) -> dict[str, Any] | None:
    trimmed = (text or "").strip()
    if not trimmed or trimmed.startswith("/"):
        return None
    if not _DITA_TERM_PATTERN.search(trimmed):
        return None
    answer_match = _DITA_ANSWER_INTENT_PATTERN.search(trimmed)
    generation_match = _EXPLICIT_DITA_GENERATION_PATTERN.search(trimmed) or (
        _wants_downloadable_dita_bundle(trimmed) and _DITA_GENERATION_PATTERN.search(trimmed)
    )
    if not answer_match or not generation_match:
        return None

    if answer_match.start() <= generation_match.start():
        answer_segment = _clean_intent_segment(trimmed[: generation_match.start()])
        generation_segment = _clean_intent_segment(trimmed[generation_match.start() :])
        intent_order = ["answer", "generation"]
    else:
        generation_segment = _clean_intent_segment(trimmed[: answer_match.start()])
        answer_segment = _clean_intent_segment(trimmed[answer_match.start() :])
        intent_order = ["generation", "answer"]

    if not generation_segment:
        return None
    generation_segment_ok = bool(
        _EXPLICIT_DITA_GENERATION_PATTERN.search(generation_segment)
        or (
            _wants_downloadable_dita_bundle(generation_segment)
            and _DITA_GENERATION_PATTERN.search(generation_segment)
        )
    )
    if not generation_segment_ok:
        return None
    if not answer_segment:
        answer_segment = trimmed
    return {
        "answer_segment": answer_segment,
        "generation_segment": generation_segment,
        "intent_order": intent_order,
    }


def _is_dita_answer_request(text: str) -> bool:
    trimmed = (text or "").strip()
    if not trimmed or _ASSISTIVE_GENERATION_REQUEST_PATTERN.search(trimmed):
        return False
    if _wants_downloadable_dita_bundle(trimmed):
        return False
    return bool(
        _DITA_TERM_PATTERN.search(trimmed)
        and (_DITA_QUESTION_PATTERN.search(trimmed) or _DITA_ANSWER_INTENT_PATTERN.search(trimmed))
    )


def _is_dita_example_answer_request(text: str) -> bool:
    trimmed = (text or "").strip()
    if not trimmed or trimmed.startswith("/"):
        return False
    if not _DITA_TERM_PATTERN.search(trimmed) or not _DITA_EXAMPLE_ANSWER_PATTERN.search(trimmed):
        return False
    if re.search(r"\bkeyscope\b", trimmed, re.IGNORECASE):
        # Product decision: keyscope examples require a clarified map bundle shape.
        return False
    return not _DITA_EXAMPLE_GENERATION_ARTIFACT_PATTERN.search(trimmed)


def _is_dita_construct_output_query(text: str) -> bool:
    trimmed = (text or "").strip()
    if not trimmed or trimmed.startswith("/"):
        return False
    return bool(
        _DITA_OUTPUT_TARGET_PATTERN.search(trimmed)
        and _DITA_OUTPUT_CONSTRUCT_PATTERN.search(trimmed)
        and (_DITA_ANSWER_INTENT_PATTERN.search(trimmed) or trimmed.endswith("?"))
    )


def is_dita_ot_parameter_query(text: str) -> bool:
    """True when asking about DITA-Open Toolkit build parameters (with or without Native PDF wording)."""
    trimmed = (text or "").strip()
    if not trimmed:
        return False
    if not _DITA_OT_ENGINE_PATTERN.search(trimmed):
        return False
    if _DITA_OT_BUILD_PARAM_PATTERN.search(trimmed):
        return True
    return bool(re.search(r"\bargs\.[a-z][a-z0-9._-]*\b", trimmed, re.IGNORECASE))


def is_native_pdf_dita_ot_argument_query(text: str) -> bool:
    """Detect product-configuration questions that mention DITA-OT args in a PDF context.

    These are not pure OASIS DITA structure questions. They need AEM Guides
    output-preset / Native PDF grounding first, with DITA spec evidence only as
    secondary context for elements such as ``<draft-comment>``.
    """
    trimmed = (text or "").strip()
    if not trimmed:
        return False
    if not _NATIVE_PDF_PATTERN.search(trimmed):
        return False
    if is_dita_ot_parameter_query(trimmed):
        return True
    return bool(_DITA_OT_ARGUMENT_PATTERN.search(trimmed))


def route_prompt(text: str, *, attachments_present: bool = False) -> PromptRouteDecision:
    trimmed = (text or "").strip()
    lowered = trimmed.lower()
    if not trimmed:
        return PromptRouteDecision(
            intent="unknown",
            confidence=0.0,
            supported=False,
            execution_hint="empty_prompt",
            reasoning_notes=["Prompt is empty."],
        )

    if attachments_present or _SCREENSHOT_PATTERN.search(trimmed):
        return PromptRouteDecision(
            intent="screenshot_authoring",
            confidence=0.92,
            supported=True,
            execution_hint="preview_first",
            legacy_answer_mode="default",
            reasoning_notes=["Detected screenshot/image authoring input."],
        )

    if is_native_pdf_dita_ot_argument_query(trimmed):
        return PromptRouteDecision(
            intent="native_pdf_guidance",
            confidence=0.94,
            supported=True,
            execution_hint="answer_directly",
            legacy_answer_mode="grounded_aem_answer",
            reasoning_notes=[
                "Detected DITA-OT arguments in a Native PDF/PDF output context; route to AEM Guides output-preset guidance before DITA spec fallback."
            ],
        )

    if is_dita_ot_parameter_query(trimmed):
        return PromptRouteDecision(
            intent="dita_ot_build",
            confidence=0.91,
            supported=True,
            execution_hint="answer_directly",
            legacy_answer_mode="grounded_dita_answer",
            reasoning_notes=[
                "Detected DITA-Open Toolkit parameter question; retrieve OT parameter docs (e.g. args.draft) and draft-comment semantics."
            ],
        )

    if _DITA_RELATED_LINKS_TOC_QUERY_PATTERN.search(trimmed):
        return PromptRouteDecision(
            intent="dita_question",
            confidence=0.94,
            supported=True,
            execution_hint="answer_directly",
            legacy_answer_mode="grounded_dita_answer",
            reasoning_notes=[
                "Detected related-links/linklist title and TOC/PDF wording; route as DITA structure/output semantics before Native PDF styling."
            ],
        )

    if _is_dita_construct_output_query(trimmed):
        return PromptRouteDecision(
            intent="dita_question",
            confidence=0.94,
            supported=True,
            execution_hint="answer_directly",
            legacy_answer_mode="grounded_dita_answer",
            reasoning_notes=[
                "Detected DITA construct plus output-target wording; route as DITA construct/output semantics before Native PDF or AEM product guidance."
            ],
        )

    if _AEM_GUIDES_PATTERN.search(trimmed) and (
        _QUESTION_LED_PRODUCT_PATTERN.search(trimmed) or trimmed.endswith("?")
    ):
        # "How do I create a choicetable in AEM Guides?" must not route to Experience League editor JSON dumps.
        if re.search(
            r"\bchoicetables?\b|\bchoptions?\b|\bchrows?\b|\bchheads?\b|\bsimpletables?\b|\bstheads?\b|\bstrows?\b|\bstentry\b|\btgroup\b",
            trimmed,
            re.IGNORECASE,
        ):
            return PromptRouteDecision(
                intent="dita_question",
                confidence=0.93,
                supported=True,
                execution_hint="answer_directly",
                legacy_answer_mode="grounded_dita_answer",
                reasoning_notes=[
                    "DITA table / choicetable (or simpletable) authoring in AEM Guides is a DITA-structure question; "
                    "answer with DITA spec grounding instead of editor toolbar configuration snippets."
                ],
            )
        # Same utterance may need both DITA spec evidence and product/UI context (multi-tool agent plan).
        aem_legacy = "default" if _DITA_TERM_PATTERN.search(trimmed) else "grounded_aem_answer"
        return PromptRouteDecision(
            intent="aem_guides_question",
            confidence=0.9,
            supported=True,
            execution_hint="answer_directly",
            legacy_answer_mode=aem_legacy,
            reasoning_notes=[
                "Detected question-led AEM Guides product/help query."
                + (" DITA terms present; allow chat mode resolution for spec+product research." if aem_legacy == "default" else "")
            ],
        )

    mixed_parts = _mixed_dita_intent_parts(trimmed)
    if mixed_parts:
        generation_segment = str(mixed_parts.get("generation_segment") or "").strip()
        preview = build_generate_dita_preview(text=generation_segment, instructions=None)
        execution_contract = build_generate_dita_execution_contract(preview=preview)
        supported = str(preview.get("bundle_type") or "").strip().lower() != "unsupported"
        return PromptRouteDecision(
            intent="dita_answer_then_generation",
            confidence=0.92,
            supported=supported,
            needs_clarification=bool(preview.get("clarification_needed")),
            execution_hint="answer_then_preview",
            legacy_answer_mode="grounded_dita_answer",
            reasoning_notes=[
                "Detected mixed DITA answer and generation intent; answer should be grounded and generation should remain review-first."
            ],
            candidate_contract={
                "mixed_intent": True,
                "answer_intent": str(mixed_parts.get("answer_segment") or "").strip(),
                "generation_intent": generation_segment,
                "answer_segment": str(mixed_parts.get("answer_segment") or "").strip(),
                "generation_segment": generation_segment,
                "intent_order": list(mixed_parts.get("intent_order") or []),
                "text": generation_segment,
                "instructions": None,
                "preview": preview,
                "execution_contract": execution_contract,
            },
        )

    if _DITA_TERM_PATTERN.search(trimmed) and _wants_downloadable_dita_bundle(trimmed):
        preview = build_generate_dita_preview(text=trimmed, instructions=None)
        execution_contract = build_generate_dita_execution_contract(preview=preview)
        supported = str(preview.get("bundle_type") or "").strip().lower() != "unsupported"
        return PromptRouteDecision(
            intent="dita_generation",
            confidence=0.93,
            supported=supported,
            needs_clarification=bool(preview.get("clarification_needed")),
            execution_hint="preview_first",
            legacy_answer_mode="generation_request",
            reasoning_notes=[
                "Detected downloadable zip/bundle intent for DITA content; use generate_dita preview instead of grounded snippet-only answers."
            ],
            candidate_contract={
                "text": trimmed,
                "instructions": None,
                "preview": preview,
                "execution_contract": execution_contract,
            },
        )

    if _is_dita_example_answer_request(trimmed):
        return PromptRouteDecision(
            intent="dita_question",
            confidence=0.91,
            supported=True,
            execution_hint="answer_directly",
            legacy_answer_mode="grounded_dita_answer",
            reasoning_notes=[
                "Detected a DITA construct example request without artifact-generation wording; answer with grounded explanation and verified snippets instead of generating files."
            ],
        )

    if _is_dita_answer_request(trimmed):
        return PromptRouteDecision(
            intent="dita_question",
            confidence=0.9,
            supported=True,
            execution_hint="answer_directly",
            legacy_answer_mode="grounded_dita_answer",
            reasoning_notes=[
                "Detected question-led DITA explanation/comparison intent; XML examples should be answered from grounded snippets, not generated as a bundle."
            ],
        )

    # Dataset/job recipe flows must win over broad DITA generation patterns ("create … task_topics"
    # matches generation regex via the "task" token inside recipe ids).
    if _DATASET_JOB_PATTERN.search(trimmed):
        return PromptRouteDecision(
            intent="dataset_job",
            confidence=0.82,
            supported=True,
            execution_hint="run_directly",
            legacy_answer_mode="default",
            reasoning_notes=[
                "Detected dataset/job/recipe management; defer to chat mode so explicit dataset routing can pick the agent plan."
            ],
        )

    if _JIRA_STYLE_PATTERN.search(trimmed) or _DITA_GENERATION_PATTERN.search(trimmed):
        preview = build_generate_dita_preview(text=trimmed, instructions=None)
        execution_contract = build_generate_dita_execution_contract(preview=preview)
        supported = str(preview.get("bundle_type") or "").strip().lower() != "unsupported"
        return PromptRouteDecision(
            intent="dita_generation",
            confidence=0.95 if _DITA_GENERATION_PATTERN.search(trimmed) else 0.88,
            supported=supported,
            needs_clarification=bool(preview.get("clarification_needed")),
            execution_hint="preview_first",
            legacy_answer_mode="generation_request",
            reasoning_notes=[
                "Detected DITA generation intent from natural-language generation phrasing."
            ],
            candidate_contract={
                "text": trimmed,
                "instructions": None,
                "preview": preview,
                "execution_contract": execution_contract,
            },
        )

    if _XML_REVIEW_PATTERN.search(trimmed):
        return PromptRouteDecision(
            intent="dita_review",
            confidence=0.9,
            supported=True,
            execution_hint="run_directly",
            legacy_answer_mode="xml_review_answer",
            reasoning_notes=["Detected DITA/XML review or fix request."],
        )

    if _NATIVE_PDF_PATTERN.search(trimmed):
        return PromptRouteDecision(
            intent="native_pdf_guidance",
            confidence=0.9,
            supported=True,
            execution_hint="answer_directly",
            legacy_answer_mode="grounded_aem_answer",
            reasoning_notes=["Detected Native PDF/output guidance request."],
        )

    if _AEM_GUIDES_PATTERN.search(trimmed):
        return PromptRouteDecision(
            intent="aem_guides_question",
            confidence=0.82,
            supported=True,
            execution_hint="answer_directly",
            legacy_answer_mode="grounded_aem_answer",
            reasoning_notes=["Detected AEM Guides product/help query."],
        )

    if _DITA_QUESTION_PATTERN.search(trimmed):
        return PromptRouteDecision(
            intent="dita_question",
            confidence=0.86,
            supported=True,
            execution_hint="answer_directly",
            legacy_answer_mode="grounded_dita_answer",
            reasoning_notes=["Detected DITA structural/spec question."],
        )

    if _ARTIFACT_PATTERN.search(trimmed):
        return PromptRouteDecision(
            intent="artifact_request",
            confidence=0.7,
            supported=True,
            execution_hint="run_directly",
            legacy_answer_mode="default",
            reasoning_notes=["Detected artifact/visualization request."],
        )

    if _NON_DITA_AUTOMATION_PATTERN.search(lowered):
        return PromptRouteDecision(
            intent="unsupported",
            confidence=0.9,
            supported=False,
            execution_hint="reject_as_unsupported",
            legacy_answer_mode="default",
            reasoning_notes=["Detected unsupported test-automation asset request."],
            candidate_contract={"unsupported_reason": "non_dita_automation"},
        )

    return PromptRouteDecision(
        intent="unknown",
        confidence=0.35,
        supported=True,
        execution_hint="answer_directly",
        legacy_answer_mode="default",
        reasoning_notes=["No strong routed intent matched; falling back to existing chat behavior."],
    )
