"""Tests for compact prompt / grounded reply UX enhancements (citations, follow-ups, thin evidence copy)."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.core.schemas_grounded_answer import NormalizedGroundedFactSet
from app.db.chat_models import ChatMessage
from app.db.session import SessionLocal
from app.services import chat_service
from app.services.learned_qa_advanced_seed import get_advanced_dita_seed_items
from app.services.learned_qa_eval_seed import get_dita_expert_eval_seed_items
from app.services.learned_qa_enterprise_seed import get_enterprise_dita_seed_items
from app.services.learned_qa_senior_seed import get_senior_prompt_seed_items


def test_grounded_user_prompt_notes_internal_evidence_ids_when_present():
    prompt = chat_service._build_grounded_answer_user_prompt(
        question="What does keyref do?",
        evidence_context="[E1] DITA Spec | Keys\nIndirection for key-based references.\n\n[E2] Tenant\nUse consistent keyscopes.",
        transcript="",
    )
    assert "[E1]" in prompt
    assert "ignore those labels" in prompt


def test_grounded_user_prompt_processing_role_gets_tutorial_depth_addon():
    q = 'What is processing-role="resource-only" in DITA?'
    prompt = chat_service._build_grounded_answer_user_prompt(
        question=q,
        evidence_context="Spec excerpt…",
        transcript="",
        tutorial_depth_addon=chat_service._grounded_dita_tutorial_depth_addon(q),
    )
    assert "TUTORIAL DEPTH" in prompt
    assert "toc" in prompt.lower()


def test_grounded_dita_tutorial_depth_addon_empty_for_unrelated_question():
    assert chat_service._grounded_dita_tutorial_depth_addon("What is the weather?") == ""


def test_grounded_user_prompt_omits_extra_citation_line_without_evidence_ids():
    prompt = chat_service._build_grounded_answer_user_prompt(
        question="Hello",
        evidence_context="Some prose with no bracketed evidence ids.",
        transcript="",
    )
    assert "cite them inline" not in prompt


def test_compact_system_prompt_includes_followups_only_when_env_truthy(monkeypatch):
    monkeypatch.delenv("CHAT_SUGGEST_FOLLOWUPS", raising=False)
    off = chat_service._build_compact_chat_system_prompt()
    assert "FOLLOW-UP SUGGESTIONS" not in off

    monkeypatch.setenv("CHAT_SUGGEST_FOLLOWUPS", "true")
    on = chat_service._build_compact_chat_system_prompt()
    assert "FOLLOW-UP SUGGESTIONS" in on
    assert "Next questions" in on


def test_compact_system_prompt_always_includes_evidence_discipline_rule():
    prompt = chat_service._build_compact_chat_system_prompt()
    assert "No evidence line tags" in prompt or "do not include bracketed evidence" in prompt.lower()


def test_compact_system_prompt_sets_senior_dita_expert_contract():
    prompt = chat_service._build_compact_chat_system_prompt(
        rag_context="LEARNED PROMPT CORPUS:\n[1] Prompt: What is keyscope?\nAnswer:\nSenior answer"
    )

    assert "Senior DITA Expert" in prompt
    assert "ask you first before opening docs" in prompt
    assert "LEARNED QA PRIORITY" in prompt
    assert "search result" in prompt


def test_rag_grounded_fallback_uses_senior_guidance_not_generic_source_dump():
    text = chat_service._build_rag_grounded_fallback_response(
        "How do I troubleshoot missing images in AEM Guides Native PDF?",
        "AEM GUIDES DOCUMENTATION:\n[1] Native PDF images\nImages must resolve from repository paths.",
        "kone",
    )

    assert text.startswith("## Short answer")
    assert "## Senior handling" in text
    assert "Best available guidance" not in text
    assert "Using local indexed knowledge" not in text


def test_senior_seed_has_html_success_pdf_failure_answer():
    items = get_senior_prompt_seed_items()
    match = next(
        item for item in items if item["prompt"] == "How do I debug a topic that publishes in HTML but fails in PDF?"
    )

    answer = match["final_answer"].lower()
    assert "output-pipeline parity" in answer
    assert "processing-role" in answer
    assert "unless the actual symptom" in answer


def test_senior_seed_has_exact_high_value_dita_answers():
    items = get_senior_prompt_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    keyscope = by_prompt["What is keyscope in DITA? Show an example."]
    assert "keyref=\"admin.install\"" in keyscope
    assert "keyref=\"user.install\"" in keyscope
    assert "qualified form" in keyscope

    draft = by_prompt["How do I exclude draft-only content at publish time?"]
    assert "DITAVAL" in draft
    assert "audience=\"internal\"" in draft
    assert "--args.draft=no" in draft

    tables = by_prompt["What is the difference between simpletable and table in DITA?"]
    assert "`<simpletable>`" in tables
    assert "`@morerows` applies to CALS `<entry>` cells" in tables


def test_senior_seed_has_exact_common_dita_tag_answers():
    items = get_senior_prompt_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    topicref = by_prompt["What is topicref in DITA? Show an example."]
    assert "<topicref href=\"intro.dita\"/>" in topicref
    assert "map construct" in topicref

    xref = by_prompt["What is xref in DITA? Show an example."]
    assert "<xref href=\"requirements.dita\"" in xref
    assert "keyref=\"support-page\"" in xref

    steps = by_prompt["What are steps, step, and cmd in DITA? Show an example."]
    assert "<steps>" in steps
    assert "<cmd>Open the DITA map.</cmd>" in steps

    reltable = by_prompt["What is reltable in DITA? Show an example."]
    assert "<reltable>" in reltable
    assert "map-level relationship metadata" in reltable

    prolog = by_prompt["What is prolog in DITA? Show an example."]
    assert "<prolog>" in prolog
    assert "not reader body content" in prolog


def test_enterprise_dita_seed_has_all_supplied_architecture_questions():
    items = get_enterprise_dita_seed_items()
    prompts = {str(item.get("prompt") or "") for item in items}

    expected = {
        "When should direct addressing be preferred over key-based indirect addressing?",
        "When does excessive key indirection reduce maintainability instead of improving it?",
        "How many levels of chained key definitions are operationally reasonable?",
        "What governance rules should be established for key naming?",
        "How should key names be namespaced across large documentation repositories?",
        "How should reusable fragments be organized to avoid conref spaghetti?",
        "When should conref be replaced by variables, keys, or conditional content?",
        "When should conkeyref be preferred over conref?",
        "How can circular dependencies be prevented through repository architecture?",
        "How should reusable content be versioned when consumed by multiple products?",
        "How should map context be represented in an enterprise content-management system?",
        "How should a CMS determine the active root map for standalone topic editing?",
        "How should a system index indirect dependencies created by keys and conkeyrefs?",
        "What dependency graph is needed to safely rename or move DITA assets?",
        "How should broken direct references and broken indirect references be reported differently?",
        "How can preprocessing results be cached without returning stale key resolutions?",
        "How should caches be invalidated when a key-defining map changes?",
        "How should a DITA chatbot distinguish specification-defined behavior from processor-specific behavior?",
        "What evidence should the chatbot provide when two DITA processors behave differently?",
        "What should an enterprise-grade DITA expert chatbot say when the DITA specification does not mandate one exact processor behavior?",
    }

    assert expected.issubset(prompts)
    assert len(items) >= len(expected)


def test_enterprise_dita_seed_answers_include_scope_and_guardrails():
    items = get_enterprise_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    direct = by_prompt["When should direct addressing be preferred over key-based indirect addressing?"]
    assert "## Behavior scope" in direct
    assert "direct references name the target in source XML" in direct
    assert "keyref is always better than href" in direct

    cache = by_prompt["How can preprocessing results be cached without returning stale key resolutions?"]
    assert "source XML, intermediate resolved content, and final output artifacts" in cache
    assert "cached resolved topics are valid across all root maps" in cache

    chatbot = by_prompt["How should a DITA chatbot distinguish specification-defined behavior from processor-specific behavior?"]
    assert "DITA-OT behavior is always the DITA specification" in chatbot
    assert "label behavior scope clearly" in chatbot


def test_enterprise_dita_seed_has_failure_behavior_questions():
    items = get_enterprise_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    keyref = by_prompt["A keyref works in one map but not another. What processing contexts should be compared?"]
    assert "effective root map" in keyref
    assert "keyscope" in keyref
    assert "A keyref can be validated completely from the topic alone." in keyref

    conkeyref = by_prompt["A conkeyref works when publishing the root map but fails when previewing the topic. Why?"]
    assert "topic-only preview" in conkeyref
    assert "root map context" in conkeyref

    chatbot = by_prompt[
        "A topic is published correctly but the chatbot gives the wrong explanation of why. How would you design a source-grounded evaluation to detect the hallucination?"
    ]
    assert "source XML, effective map context, processor logs" in chatbot
    assert "Correct final output proves the chatbot explanation is correct." in chatbot


def test_enterprise_dita_seed_has_uri_and_key_resolution_questions():
    items = get_enterprise_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    direct = by_prompt["What is direct URI-based addressing in DITA?"]
    assert "source XML points directly" in direct
    assert "Direct URI addressing is deprecated." in direct

    fragment = by_prompt["What does the URI topic.dita#topicId/elementId address?"]
    assert "element with ID `elementId`" in fragment
    assert "The element ID alone is always enough." in fragment

    xml_base = by_prompt["Can xml:base change how DITA references are resolved?"]
    assert "`xml:base` can change the base URI" in xml_base
    assert "Every DITA tool supports complex `xml:base` use identically." in xml_base

    duplicate_key = by_prompt["How is the effective definition selected when duplicate key definitions exist?"]
    assert "effective map" in duplicate_key
    assert "The last duplicate key always wins universally." in duplicate_key


def test_enterprise_dita_seed_has_resource_semantics_questions():
    items = get_enterprise_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    resource_only = by_prompt['What is the semantic meaning of processing-role="resource-only"?']
    assert "supporting material rather than normal reading-order content" in resource_only
    assert "resource-only` and `toc=\"no\"` are the same thing" in resource_only

    toc = by_prompt['Does toc="no" mean the topic should not be generated?']
    assert "omitted from generated navigation" in toc
    assert "`toc=\"no\"` means do not publish the topic." in toc

    matrix = by_prompt["How would you test every combination of toc, linking, print, and processing-role?"]
    assert "matrix of map fixtures" in matrix
    assert "TOC entry" in matrix
    assert "generated links" in matrix
    assert "print/PDF presence" in matrix


def test_enterprise_dita_seed_has_reltable_link_generation_questions():
    items = get_enterprise_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    generated = by_prompt["How does a relationship table generate related links?"]
    assert "Each `relrow` defines a relationship set." in generated
    assert "A reltable physically inserts xref elements into source topics." in generated

    linking = by_prompt['What is the effect of linking="sourceonly"?']
    assert "source of generated links" in linking
    assert "`sourceonly` means links only point to this topic." in linking

    copy_to = by_prompt["How does copy-to affect relationship-table links?"]
    assert "source-to-copy URI mapping" in copy_to
    assert "`copy-to` never affects related links." in copy_to


def test_enterprise_dita_seed_has_map_reference_integration_questions():
    items = get_enterprise_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    mapref = by_prompt["What is the difference between referencing a map with mapref and referencing it using a normal topicref?"]
    assert "map-to-map composition" in mapref
    assert "`mapref` and normal `topicref` are always identical." in mapref

    keys = by_prompt["How are keys defined in a referenced map added to the effective key space?"]
    assert "effective key space" in keys
    assert "All keys in every repository map are globally available." in keys

    navref = by_prompt["How does navref differ from including a submap through mapref?"]
    assert "navigation-oriented" in navref
    assert "`navref` and `mapref` have identical processing semantics." in navref


def test_enterprise_dita_seed_has_branch_filtering_questions():
    items = get_enterprise_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    branch = by_prompt["What is branch filtering in DITA?"]
    assert "specific branch of a DITA map" in branch
    assert "Branch filtering is the same as one global DITAVAL file." in branch

    rename = by_prompt["How do resourceprefix and resourcesuffix prevent naming collisions?"]
    assert "branch-specific text to generated resource names" in rename
    assert "They affect only TOC labels." in rename

    conkeyref = by_prompt["Can one reusable topic resolve different conkeyrefs in different filtered branches?"]
    assert "correct scoped behavior" in conkeyref
    assert "A reused topic must always resolve identical conkeyrefs." in conkeyref


def test_dita_expert_eval_seed_contains_200_questions():
    items = get_dita_expert_eval_seed_items()
    prompts = {str(item.get("prompt") or "") for item in items}

    assert len(items) == 200
    assert len(prompts) == 200
    assert "What is DITA, and what problem does it solve?" in prompts
    assert "What information should be collected before reporting a DITA publishing defect?" in prompts


def test_dita_expert_eval_seed_has_senior_answer_requirements():
    items = get_dita_expert_eval_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    fundamentals = by_prompt["What is DITA, and what problem does it solve?"]
    assert "topic-based XML architecture" in fundamentals
    assert "Senior answer requirements" in fundamentals

    troubleshooting = by_prompt["How would you troubleshoot a broken cross-reference in published output?"]
    assert "expected behavior, probable causes, deterministic checks" in troubleshooting
    assert "active map context" in troubleshooting


def test_advanced_dita_seed_covers_attached_question_batch():
    items = get_advanced_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    assert len(items) >= 270

    cascade = by_prompt["How does metadata cascade from a root DITA map to nested topicref elements?"]
    assert "effective DITA processing context" in cascade
    assert "source XML was permanently changed" in cascade

    chunk = by_prompt['What does chunk="to-content" mean?']
    assert "generated URIs" in chunk
    assert "Behavior scope" in chunk

    specialization = by_prompt["How does DITA specialization preserve compatibility with base DITA?"]
    assert "Specialization, constraints, generalization" in specialization
    assert "class" in specialization

    dita_ot = by_prompt["What major preprocessing stages occur before DITA-OT transformation?"]
    assert "preprocessing" in dita_ot
    assert "temporary files" in dita_ot

    scenario = by_prompt[
        "A topic is published correctly but the chatbot gives the wrong explanation of why. How would you design a source-grounded evaluation to detect the hallucination?"
    ]
    assert "source markup" in scenario
    assert "processor logs" in scenario


def test_advanced_dita_seed_covers_challenge_questions():
    items = get_advanced_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    challenge_prompts = [
        'A root map sets audience="admin", a nested topicgroup sets audience="developer", and a child topicref sets audience="reviewer". What is the child\'s effective audience under merge and no-merge behavior?',
        "A key is defined three times: once globally, once inside a filtered branch, and once inside a key scope. Which definition should an unqualified reference use?",
        "An xref has a keyref, explicit text, and the key definition has a navtitle. Which text should be displayed?",
        "Can a key be valid for variable text but invalid as a link target?",
        "A keyref works in DITA-OT HTML5 but fails in Native PDF. Which processing stages should be compared first?",
        "When the DITA specification is silent but two processors behave differently, how should the chatbot present the answer without hallucinating a universal rule?",
    ]

    for prompt in challenge_prompts:
        assert prompt in by_prompt
        answer = by_prompt[prompt]
        assert "effective DITA processing context" in answer
        assert "Do not present DITA-OT, AEM Guides, editor preview, HTML5, or PDF behavior" in answer


def test_learned_qa_local_fallback_handles_bare_expert_terms():
    key_answer = chat_service._build_learned_qa_local_fallback_response(
        "Can a key be valid for variable text but invalid as a link target?",
        "kone",
        min_score=0.92,
    )
    assert "variable text" in key_answer
    assert "usable link target" in key_answer
    assert "<link> element" not in key_answer

    cascade_answer = chat_service._build_learned_qa_local_fallback_response(
        'A root map sets audience="admin", a nested topicgroup sets audience="developer", and a child topicref sets audience="reviewer". What is the child\'s effective audience under merge and no-merge behavior?',
        "kone",
        min_score=0.92,
    )
    assert "Under merge behavior" in cascade_answer
    assert "source topic itself remains unchanged" in cascade_answer

    evaluation_answer = chat_service._build_learned_qa_local_fallback_response(
        "Did the answer separate source content from effective processed content?",
        "kone",
        min_score=0.92,
    )
    assert "Evaluate the answer" in evaluation_answer
    assert "separate source from effective processed content" in evaluation_answer

    copy_to_index_answer = chat_service._build_learned_qa_local_fallback_response(
        "Should the index point to the source topic or the copied output identity?",
        "kone",
        min_score=0.92,
    )
    assert "copied output identity" in copy_to_index_answer
    assert "original source topic URI" in copy_to_index_answer

    chunked_url_answer = chat_service._build_learned_qa_local_fallback_response(
        "Why do chunked child-topic URLs sometimes contain generated identifiers?",
        "kone",
        min_score=0.92,
    )
    assert "generated identifiers" in chunked_url_answer
    assert "combined output page" in chunked_url_answer

    temporary_copy_answer = chat_service._build_learned_qa_local_fallback_response(
        "Why must preprocessing always operate on temporary copies rather than original source files?",
        "kone",
        min_score=0.92,
    )
    assert "temporary copies" in temporary_copy_answer
    assert "source corruption" in temporary_copy_answer


def test_advanced_dita_seed_covers_varied_evaluation_questions():
    items = get_advanced_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    expected = {
        "Explain why keyref requires a map context while href does not.": ["`href` directly names a URI", "active map"],
        "Compare href, keyref, conref, and conkeyref.": ["direct URI-based linking", "indirect key-based content reuse"],
        'Compare toc="no" with processing-role="resource-only".': ["removes a normal topic reference from navigation", "support material"],
        'What will be the effective audience value if the parent has audience="admin" and the child has audience="developer"?': ["merge behavior", "no-merge behavior"],
        "What happens when conref resolves successfully but the consuming element contains local text?": ["replaces the consuming element", "fallback content"],
        "What happens when two branches generate the same copy-to output name?": ["collide on output identity", "unique `copy-to` values"],
    }

    for prompt, required_terms in expected.items():
        assert prompt in by_prompt
        answer = by_prompt[prompt]
        for term in required_terms:
            assert term in answer


def test_advanced_dita_seed_covers_correction_and_adversarial_questions():
    items = get_advanced_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    expected = {
        'Correct this statement: "keyref is simply another syntax for href."': ["Correction:", "`href` directly addresses a URI", "`keyref` resolves indirectly"],
        'Correct this statement: "toc="no" prevents the topic from being published."': ["Correction:", "affects navigation", "cannot be generated"],
        "Since a DITA file validates against its DTD, it cannot contain broken key references. Is this correct?": ["No.", "DTD validation checks grammar", "cross-file key"],
        "Root map ke bina keyref resolve hoga kya?": ["Usually no", "active root map", "key-space context"],
        "Create a test scenario for duplicate key definitions.": ["minimal root map", "expected result", "negative assertion"],
        "Did the answer separate source content from effective processed content?": ["Evaluate the answer", "separate source from effective processed content"],
    }

    for prompt, required_terms in expected.items():
        assert prompt in by_prompt
        answer = by_prompt[prompt]
        for term in required_terms:
            assert term in answer


def test_advanced_dita_seed_covers_broader_domain_questions():
    items = get_advanced_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    expected = {
        "How should xml:lang be applied in a DITA topic?": ["`xml:lang` should be set", "accessibility language metadata"],
        "When should a bookmap be used instead of a normal DITA map?": ["Use a `bookmap`", "frontmatter"],
        "What is the purpose of the indexterm element?": ["`indexterm` marks", "generated index"],
        "What is the purpose of a glossary entry topic?": ["controlled term", "generated glossaries"],
        "What accessibility information should be added to images?": ["alternative text", "decorative images"],
        "Why might an SVG appear in the editor but disappear in PDF output?": ["PDF renderer", "image conversion pipeline"],
        "How should DITA validation be integrated into a CI pipeline?": ["grammar", "publishing smoke tests"],
        "What is a publication baseline?": ["reproducible selection", "specific release"],
        "How should permissions affect DITA map resolution?": ["honor permissions", "unauthorized dependencies"],
        "Why does my build pass locally but fail in Jenkins?": ["DITA-OT version", "filesystem case sensitivity"],
    }

    for prompt, required_terms in expected.items():
        assert prompt in by_prompt
        answer = by_prompt[prompt]
        for term in required_terms:
            assert term in answer


def test_advanced_dita_seed_covers_authoring_model_questions():
    items = get_advanced_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    expected = {
        'If a topic contains audience="admin" but its parent topicref applies audience="developer", what is the effective processing context?': ["topic source", "effective processing context"],
        "What is the purpose of the deliveryTarget attribute?": ["`deliveryTarget` identifies output-specific applicability", "publishing presets"],
        "What is the difference between title, navtitle, searchtitle, and linktext?": ["`title` is the topic's primary title", "`searchtitle`"],
        "What is the difference between shortdesc and abstract?": ["`shortdesc` is a concise summary", "`abstract`"],
        "What is the difference between steps, steps-unordered, and steps-informal?": ["`steps` models ordered", "`steps-informal`"],
        "What is the difference between codeblock and codeph?": ["`codeblock` is for block-level", "`codeph`"],
        "What is the difference between uicontrol, wintitle, and menucascade?": ["`uicontrol`", "`menucascade`"],
        "When should conref push be preferred over normal conref pull?": ["conref push", "normal conref pull"],
        "How should a large Word document be split into DITA topics?": ["concepts", "tasks", "references"],
    }

    for prompt, required_terms in expected.items():
        assert prompt in by_prompt
        answer = by_prompt[prompt]
        for term in required_terms:
            assert term in answer


def test_advanced_dita_seed_covers_oxygen_webhelp_pdf_questions():
    items = get_advanced_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    expected = {
        "Why does a key definition remain unresolved when the key map exists but no root map is selected in Oxygen?": ["key map file existing", "active root map"],
        "Does metadata on the root map cascade through a topichead to its child topic references?": ["`topichead`", "effective metadata context"],
        "What is the difference between validating one DITA topic and validating a complete map?": ["Topic validation", "complete map validation"],
        "Why can a topic outside the map directory publish successfully but produce a broken WebHelp navigation link?": ["WebHelp", "output path"],
        "Why might a CSS property work in a browser but not in PDF Chemistry?": ["paged-media renderer", "unsupported"],
        "Why can an SVG render correctly in a browser but appear distorted in PDF?": ["viewBox", "PDF engines"],
        "Should the index point to the source topic or the copied output identity?": ["copied output identity", "original source topic URI"],
        "What information about key definitions appears in DITA-OT temporary files?": ["effective key definitions", "job metadata"],
        "Why can an Ant-based custom plug-in fail after upgrading DITA-OT?": ["internal targets", "documented extension points"],
    }

    for prompt, required_terms in expected.items():
        assert prompt in by_prompt
        answer = by_prompt[prompt]
        for term in required_terms:
            assert term in answer


def test_advanced_dita_seed_covers_oxygen_forum_inspired_questions():
    items = get_advanced_dita_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}
    def answer_for(prompt: str) -> str:
        if prompt in by_prompt:
            return by_prompt[prompt]
        prompt_norm = prompt.replace("'", "")
        for existing_prompt, answer in by_prompt.items():
            if existing_prompt.replace("â€™", "").replace("'", "") == prompt_norm:
                return answer
        return ""

    expected = {
        "What does an externally imposed key context mean in Oxygen?": ["external key manager", "selected DITA map context"],
        "Why can a manually entered keyref work even when Oxygen's key-reference dialog is empty?": ["Manual `keyref` entry can work", "insertion dialog"],
        "Why do chunked child-topic URLs sometimes contain generated identifiers?": ["generated identifiers", "combined output page"],
        "Why can a conref to a topicref that references a DITA map fail during preprocessing?": ["map-reference preprocessing", "original element ID"],
        "Why must preprocessing always operate on temporary copies rather than original source files?": ["temporary copies", "source corruption"],
        "A key publishes correctly but Oxygen marks it unresolved. Which editor-context checks should be performed before changing the DITA source?": ["active root map", "publishing command"],
    }

    for prompt, required_terms in expected.items():
        answer = answer_for(prompt)
        assert answer
        for term in required_terms:
            assert term in answer


def test_fetch_last_messages_returns_latest_not_oldest():
    session_id = chat_service.create_session()
    db = SessionLocal()
    try:
        base = datetime.utcnow()
        for i in range(8):
            db.add(
                ChatMessage(
                    id=str(uuid4()),
                    session_id=session_id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"MSG-{i}",
                    created_at=base + timedelta(seconds=i),
                )
            )
        db.commit()
    finally:
        db.close()

    try:
        last_four = chat_service._fetch_last_messages_for_session(session_id, limit=4)
        assert [m["content"] for m in last_four] == ["MSG-4", "MSG-5", "MSG-6", "MSG-7"]

        tr = chat_service._recent_chat_transcript(session_id, limit=4)
        assert "MSG-7" in tr
        assert "MSG-0" not in tr
    finally:
        chat_service.delete_session(session_id)


def test_expand_follow_up_retrieval_merges_prior_user_turn():
    session_id = chat_service.create_session()
    db = SessionLocal()
    try:
        base = datetime.utcnow()
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="user",
                content="Explain keyref usage in DITA maps.",
                created_at=base,
            )
        )
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="assistant",
                content="Keys let you indirect hrefs.",
                created_at=base + timedelta(seconds=1),
            )
        )
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="user",
                content="What about conref?",
                created_at=base + timedelta(seconds=2),
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        merged = chat_service._expand_follow_up_retrieval_query(session_id, "What about conref?")
        assert "keyref" in merged.lower()
        assert "conref" in merged.lower()
        assert "Follow-up:" in merged
    finally:
        chat_service.delete_session(session_id)


def test_expand_follow_up_does_not_merge_standalone_question():
    session_id = chat_service.create_session()
    db = SessionLocal()
    try:
        base = datetime.utcnow()
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="user",
                content="Hello",
                created_at=base,
            )
        )
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="user",
                content="What is the purpose of keyref in DITA?",
                created_at=base + timedelta(seconds=1),
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        q = "What is the purpose of keyref in DITA?"
        merged = chat_service._expand_follow_up_retrieval_query(session_id, q)
        assert merged == q
    finally:
        chat_service.delete_session(session_id)


def test_render_normalized_grounded_fact_set_strengthen_hint_for_thin_evidence():
    facts = NormalizedGroundedFactSet(
        answer_kind="dita_element",
        source_policy="dita_spec_first",
        canonical_definition="The topic element wraps topic content.",
        thin_evidence=True,
    )
    text = chat_service._render_normalized_grounded_fact_set(facts)
    assert "What would strengthen this answer" in text


def test_render_normalized_grounded_fact_set_strengthen_hint_for_semantic_warnings():
    facts = NormalizedGroundedFactSet(
        answer_kind="dita_element",
        source_policy="dita_spec_first",
        canonical_definition="The topic element wraps topic content.",
        semantic_warnings=["Low semantic similarity to retrieval query."],
    )
    text = chat_service._render_normalized_grounded_fact_set(facts)
    assert "What would strengthen this answer" in text


@pytest.mark.anyio
async def test_synthesize_agent_answer_requests_recommended_step_and_higher_token_budget(monkeypatch):
    calls: list[dict] = []

    async def capture_generate_text(**kwargs):
        calls.append(kwargs)
        return "## Summary\n\nOK.\n\n## Details\n\n- a\n\n## Limits of evidence\n\n- none\n\n## Sources\n\n- s"

    monkeypatch.setattr(chat_service, "generate_text", capture_generate_text)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    plan = {"goal": "Explain reuse"}
    tool_results = {
        "lookup_dita_spec": {
            "spec_chunks": [
                {"element_name": "keydef", "text_content": "Keyref resolves via key space."},
            ],
        },
    }
    await chat_service._synthesize_agent_answer(
        user_content="What is keyref?",
        plan=plan,
        tool_results_by_name=tool_results,
    )
    assert calls, "generate_text should run when LLM is available and evidence is non-empty"
    system_prompt = calls[0]["system_prompt"]
    assert "Recommended next step" in system_prompt
    assert calls[0]["max_tokens"] == 1600


@pytest.mark.anyio
async def test_evidence_pack_prompt_context_numbers_candidates_for_grounded_path():
    """Regression: evidence shown to the LLM uses [E1], [E2] headers (aligned with citation UX)."""
    from app.services.grounding_service import build_evidence_pack

    c1 = type(
        "Candidate",
        (),
        {
            "source": "dita_spec",
            "label": "Keys",
            "text": "Keyref resolves to a key definition.",
            "url": "",
            "metadata": {"title": "Keys"},
            "score": 0.0,
        },
    )()
    c2 = type(
        "Candidate",
        (),
        {
            "source": "aem_guides",
            "label": "Guides",
            "text": "Map-level keys in AEM Guides.",
            "url": "",
            "metadata": {"title": "Guides"},
            "score": 0.0,
        },
    )()
    pack = build_evidence_pack(query="keyref", tenant_id="kone", candidates=[c1, c2])
    ctx = pack.build_prompt_context(limit=6)
    assert "[E1]" in ctx
    assert "[E2]" in ctx
