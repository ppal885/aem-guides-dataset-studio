"""Generated learned-QA seeds for the 200 DITA expert evaluation prompts."""

from __future__ import annotations

from typing import Any

ANSWER_STYLE = "senior_technical_docs"

_QUESTIONS = [
    "What is DITA, and what problem does it solve?",
    "What does the acronym DITA stand for?",
    "What are the main benefits of using DITA for technical documentation?",
    "What is topic-based authoring in DITA?",
    "What are the standard topic types available in DITA?",
    "What is the difference between a concept, task, and reference topic?",
    "When should an author use a generic DITA topic?",
    "What is the purpose of the class attribute in DITA?",
    "What is the purpose of the id attribute in a DITA topic?",
    "What is the difference between a DITA topic and a DITA map?",
    "What is the root element of a concept topic?",
    "What is the root element of a task topic?",
    "What is the root element of a reference topic?",
    "What is the root element of a DITA map?",
    "Can a DITA file contain multiple topics?",
    "What is the difference between a compound DITA document and separate topic files?",
    "What is the purpose of the shortdesc element?",
    "Why is shortdesc important for search and content previews?",
    "What is the purpose of the prolog element?",
    "What types of metadata can be stored inside prolog?",
    "What is a DITA map?",
    "What is the purpose of the topicref element?",
    "What is the difference between topicref, topichead, and topicgroup?",
    "Can a DITA map reference another DITA map?",
    "What is the difference between mapref and a topicref pointing to a map?",
    "What is a bookmap, and when should it be used?",
    "What is the difference between a regular DITA map and a bookmap?",
    "What are frontmatter, booklists, chapter, appendix, and backmatter in a bookmap?",
    "How is the navigation title determined for a topic reference?",
    "What is the difference between navtitle and the actual topic title?",
    "What does the locktitle attribute do?",
    "What happens when locktitle=\"yes\" is applied?",
    "How can a topic be included in output but excluded from the table of contents?",
    "How can a topic appear in the table of contents without generating its own page?",
    "What is the purpose of processing-role=\"resource-only\"?",
    "What is the difference between processing-role=\"normal\" and resource-only?",
    "How can the same topic be referenced multiple times in a map?",
    "What problems can occur when a topic is referenced multiple times?",
    "How does the hierarchy of a DITA map affect generated output?",
    "What are the best practices for designing a large DITA map?",
    "What is content reuse in DITA?",
    "What is the difference between conref and conkeyref?",
    "What is the syntax for referencing content with conref?",
    "What happens when the source element referenced by a conref does not exist?",
    "Can a paragraph reuse content from another paragraph through conref?",
    "Can conref reuse content across different element types?",
    "What is conref push?",
    "What is the difference between pushreplace, pushbefore, and pushafter?",
    "When should conref push be used?",
    "What are the risks of excessive conref usage?",
    "What is a key definition in DITA?",
    "How is a key defined in a DITA map?",
    "What is the purpose of the keyref attribute?",
    "What is the difference between href and keyref?",
    "Why are keys preferred over direct file references in reusable content?",
    "What is a key scope?",
    "How does nested key scope work?",
    "What happens when the same key is defined more than once?",
    "What is the purpose of conkeyref?",
    "How can an author troubleshoot an unresolved key reference?",
    "What is the purpose of the xref element?",
    "What is the difference between xref and link?",
    "How do you create a cross-reference to another DITA topic?",
    "How do you create a cross-reference to a specific element inside a topic?",
    "How do you create an external web link in DITA?",
    "What is the purpose of the scope attribute?",
    "What is the difference between scope=\"local\", peer, and external?",
    "What is the purpose of the format attribute?",
    "When should format=\"pdf\" or format=\"html\" be used?",
    "How is link text generated when an xref has no explicit text?",
    "What happens when the referenced target has no title?",
    "What is a relationship table?",
    "What problem does a relationship table solve?",
    "How are related links generated from a relationship table?",
    "What is the difference between hierarchical navigation and relationship-based navigation?",
    "What is the purpose of the collection-type attribute?",
    "What is the difference between collection-type=\"sequence\" and family?",
    "What is the purpose of linking=\"none\"?",
    "How can links be generated in only one direction?",
    "How would you troubleshoot a broken cross-reference in published output?",
    "What is conditional processing in DITA?",
    "Which DITA attributes are commonly used for conditional processing?",
    "What is a DITAVAL file?",
    "What is the difference between include and exclude actions in DITAVAL?",
    "What happens when no DITAVAL rule exists for an attribute value?",
    "How do audience, platform, product, and props differ?",
    "When should custom profiling attributes be used?",
    "What is the purpose of the otherprops attribute?",
    "Can multiple conditional values be applied to the same element?",
    "How are space-separated profiling values evaluated?",
    "What is the difference between filtering and flagging?",
    "How can conditional content be highlighted instead of excluded?",
    "What are startflag and endflag in a DITAVAL file?",
    "Can images be used as conditional-processing flags?",
    "What is a ditavalref element?",
    "How does branch filtering work with ditavalref?",
    "Can different branches of the same map use different DITAVAL files?",
    "How does conditional processing interact with key definitions?",
    "Why might a key remain available even when its defining branch is filtered?",
    "How would you debug content that is unexpectedly missing from generated output?",
    "What is metadata in DITA?",
    "What is the difference between topic metadata and map metadata?",
    "What is the purpose of topicmeta?",
    "What is the purpose of keywords and keyword?",
    "How can metadata be inherited from a DITA map?",
    "What is cascading metadata in DITA?",
    "Which attributes commonly cascade from maps to topics?",
    "How can cascading metadata be prevented or overridden?",
    "What is a subject scheme map?",
    "What problems does a subject scheme solve?",
    "How are controlled values defined in a subject scheme?",
    "What is the purpose of subjectdef?",
    "What is the purpose of enumerationdef?",
    "How is an attribute associated with a controlled-value hierarchy?",
    "Can a subject scheme define values for custom attributes?",
    "What happens when an author enters a value not defined by the subject scheme?",
    "How does a subject scheme improve authoring consistency?",
    "Can multiple subject scheme maps be used in the same publication?",
    "What is the difference between a taxonomy and a subject scheme?",
    "How would you validate whether subject-scheme values are being applied correctly?",
    "What table models are supported in DITA?",
    "What is the difference between a simple table and a CALS table?",
    "When should simpletable be used instead of table?",
    "What are tgroup, colspec, thead, tbody, row, and entry?",
    "What does the morerows attribute do in a DITA table?",
    "How are table cells merged horizontally?",
    "How are table cells merged vertically?",
    "What problems can occur when CALS table column specifications are incorrect?",
    "What is the purpose of the keycol attribute in a simple table?",
    "How can accessibility information be added to a DITA table?",
    "How is an image inserted into a DITA topic?",
    "What is the difference between inline and block placement for an image?",
    "What do the width, height, and scale attributes control?",
    "What is the purpose of the alt element?",
    "How should decorative images be handled for accessibility?",
    "Can SVG images be referenced from DITA topics?",
    "What issues can occur when image filenames contain spaces?",
    "What is the difference between ordered, unordered, and definition lists?",
    "When should a steps element be used instead of an ordered list?",
    "How would you troubleshoot an image that appears in the editor but not in published output?",
    "What is the recommended structure of a DITA task topic?",
    "What is the purpose of taskbody?",
    "What is the difference between prereq, context, steps, result, and postreq?",
    "What is the difference between steps and steps-unordered?",
    "What is the purpose of the cmd element?",
    "Can a task step contain multiple commands?",
    "What is the purpose of info inside a step?",
    "What is the purpose of stepresult?",
    "What is the purpose of choices and choice?",
    "How should optional steps be represented?",
    "How should a single-step procedure be authored?",
    "What is the purpose of the stepxmp element?",
    "How can warnings and notes be added to a task?",
    "What is the difference between note, warning, caution, and danger?",
    "How should troubleshooting information be structured in DITA?",
    "What is a troubleshooting topic type?",
    "How should command-line examples be represented?",
    "What is the difference between codeblock, codeph, and pre?",
    "How should user-interface controls be marked up?",
    "What is the difference between uicontrol, wintitle, menucascade, and shortcut?",
    "What is DITA validation?",
    "What is the difference between a well-formed and a valid XML document?",
    "What is the role of a DTD in DITA?",
    "Can DITA documents be validated using XML Schema or RELAX NG?",
    "What is Schematron, and how does it complement DTD validation?",
    "What types of business rules are suitable for Schematron?",
    "How can Schematron distinguish between fatal errors, errors, warnings, and informational messages?",
    "What is DITA specialization?",
    "Why would an organization create a specialized DITA element?",
    "What is the difference between structural and domain specialization?",
    "What is constraint-based configuration in DITA?",
    "What is a DITA document-type shell?",
    "What is the role of the domains attribute?",
    "Why must specialized elements preserve DITA class ancestry?",
    "What is generalization in DITA?",
    "What is the difference between specialization and generalization?",
    "What risks are associated with creating too many custom specializations?",
    "How can custom specialization affect publishing and tool compatibility?",
    "What is the purpose of an XML catalog in a DITA environment?",
    "How would you troubleshoot a DITA file that validates in one tool but fails in another?",
    "What is the DITA Open Toolkit?",
    "What is a DITA-OT transformation type?",
    "What is the difference between PDF, HTML5, and XHTML transformations?",
    "What is a DITA-OT plug-in?",
    "How can a custom DITA-OT plug-in modify generated output?",
    "What is the purpose of Ant properties in DITA-OT publishing?",
    "What are common reasons for a DITA-OT publishing failure?",
    "What does an unresolved reference warning in DITA-OT usually indicate?",
    "How can temporary and output directories help diagnose a publishing issue?",
    "What is the difference between source validation and output validation?",
    "How does AEM Guides manage DITA topics and maps as DAM assets?",
    "What is the difference between Native PDF publishing and DITA-OT PDF publishing in AEM Guides?",
    "How are output presets used in AEM Guides?",
    "What is a baseline in AEM Guides, and when should it be created?",
    "How does version selection in a baseline affect generated output?",
    "What happens when a referenced topic is missing from an AEM Guides map?",
    "How would you troubleshoot a key reference that works in one map but fails in another?",
    "How would you investigate a topic that appears in HTML5 output but not in PDF output?",
    "How would you diagnose conditional content that behaves differently in the editor preview and published output?",
    "What information should be collected before reporting a DITA publishing defect?",
]

_DIRECT_ANSWERS = {
    "What is DITA, and what problem does it solve?": "DITA is a topic-based XML architecture for creating modular, reusable, structured technical content. It solves problems around reuse, conditional delivery, consistent metadata, and multi-channel publishing.",
    "What does the acronym DITA stand for?": "DITA stands for Darwin Information Typing Architecture.",
    "What is the root element of a concept topic?": "The root element of a concept topic is `<concept>`.",
    "What is the root element of a task topic?": "The root element of a task topic is `<task>`.",
    "What is the root element of a reference topic?": "The root element of a reference topic is `<reference>`.",
    "What is the root element of a DITA map?": "The root element of a basic DITA map is `<map>`.",
    "What is a DITAVAL file?": "A DITAVAL file defines conditional-processing actions such as include, exclude, flag, and passthrough for profiling attributes and values.",
    "What is the DITA Open Toolkit?": "DITA Open Toolkit, or DITA-OT, is an open-source publishing engine that transforms DITA maps and topics into outputs such as HTML5, PDF, and other formats.",
    "What is a DITA-OT transformation type?": "A DITA-OT transformation type, or transtype, selects the output pipeline used to transform DITA content, such as `html5`, `pdf`, or a custom plug-in transtype.",
    "How would you troubleshoot a broken cross-reference in published output?": "Troubleshoot a broken published cross-reference by checking the source `xref` or `link`, the active root map, key resolution, filtering, target IDs, output transform, and processor logs.",
    "What information should be collected before reporting a DITA publishing defect?": "Collect the root map, minimal source files, DITAVAL or branch filters, output preset or DITA-OT command, processor version, plug-ins, logs, temporary files, expected output, and actual output.",
}


def _domain(question: str) -> tuple[str, str, list[str]]:
    q = question.lower()
    if any(term in q for term in ("aem guides", "dita-ot", "publishing", "pdf", "html5", "output", "baseline", "preset", "temporary")):
        return "publishing", "DITA-OT, AEM Guides, and troubleshooting", ["publishing", "dita-ot", "aem-guides"]
    if any(term in q for term in ("validation", "dtd", "schema", "relax", "schematron", "specialization", "catalog", "class ancestry", "generalization", "domains")):
        return "architecture_validation", "Validation, specialization, and DITA architecture", ["validation", "specialization", "architecture"]
    if any(term in q for term in ("task", "step", "cmd", "choice", "warning", "note", "uicontrol", "menucascade", "codeblock", "procedure")):
        return "task_authoring", "Tasks, procedures, and technical authoring", ["task", "procedure", "authoring"]
    if any(term in q for term in ("table", "image", "list", "morerows", "simpletable", "svg", "alt", "keycol")):
        return "structured_content", "Tables, images, lists, and structured content", ["table", "image", "structured-content"]
    if any(term in q for term in ("metadata", "subject scheme", "subjectdef", "enumerationdef", "taxonomy", "topicmeta", "keywords")):
        return "metadata_taxonomy", "Metadata, subject scheme, and taxonomy", ["metadata", "subject-scheme", "taxonomy"]
    if any(term in q for term in ("ditaval", "conditional", "audience", "platform", "product", "props", "otherprops", "filter", "flag", "startflag", "endflag")):
        return "conditional_processing", "Conditional processing and DITAVAL", ["conditional-processing", "ditaval", "profiling"]
    if any(term in q for term in ("xref", "link", "scope", "format", "relationship", "collection-type", "linking")):
        return "links_relationships", "Links, cross-references, and relationships", ["xref", "links", "relationships"]
    if any(term in q for term in ("conref", "conkeyref", "key", "href", "reuse")):
        return "reuse_and_keys", "Content reuse and references", ["reuse", "keys", "references"]
    if any(term in q for term in ("map", "topicref", "topichead", "bookmap", "navtitle", "locktitle", "processing-role")):
        return "maps_information_architecture", "DITA maps and information architecture", ["map", "topicref", "navigation"]
    return "dita_fundamentals", "DITA fundamentals", ["dita", "topic", "fundamentals"]


def _answer(question: str, category_label: str) -> str:
    if question in _DIRECT_ANSWERS:
        short = _DIRECT_ANSWERS[question]
    elif question.startswith("What is the difference between"):
        short = "The correct answer should compare the two DITA constructs by semantic purpose, source XML behavior, processing effect, and publishing impact."
    elif question.startswith("How would you troubleshoot") or question.startswith("How would you diagnose") or question.startswith("How would you investigate"):
        short = "Troubleshoot by separating source markup, effective map context, filtering/key resolution, processor logs, and final output behavior."
    elif question.startswith("Can "):
        short = "The correct answer should state whether the behavior is allowed, then explain the required DITA context and processor constraints."
    elif question.startswith("What happens"):
        short = "The correct answer should describe the expected processing result and the diagnostic or fallback behavior when the condition occurs."
    elif question.startswith("How "):
        short = "The correct answer should explain the DITA mechanism, the relevant XML constructs or attributes, and how the result is verified in the effective output."
    else:
        short = "The correct answer should define the DITA concept directly and explain its practical authoring or processing role."
    return f"""## Short answer
{short}

## Senior answer requirements
- Answer as a DITA expert for the domain: {category_label}.
- Start with the direct concept or behavior, not a generic source summary.
- Distinguish source XML from effective processed content when processing, reuse, filtering, links, maps, or publishing are involved.
- Distinguish DITA specification behavior from DITA-OT, AEM Guides, editor, or output-transform behavior when implementation details may vary.
- Include a small XML example when the question asks about authoring syntax, references, tables, maps, tasks, links, or filtering.
- For troubleshooting questions, cover expected behavior, probable causes, deterministic checks, and evidence to collect.

## Must not claim
- Do not present processor-specific behavior as a universal DITA specification rule.
- Do not claim a topic can be evaluated fully without its active map context when keys, conkeyrefs, branch filtering, metadata cascade, or publishing behavior are involved.
- Do not ignore accessibility, validation, or output-specific constraints when the question touches images, tables, tasks, PDF, HTML, or AEM Guides."""


def get_dita_expert_eval_seed_items() -> list[dict[str, Any]]:
    """Return generated approved learned-QA entries for the 200-question evaluation corpus."""

    items: list[dict[str, Any]] = []
    for question in _QUESTIONS:
        topic, category_label, tags = _domain(question)
        items.append(
            {
                "prompt": question,
                "topic": topic,
                "tags": [*tags, "evaluation", "dita-expert"],
                "answer_style": ANSWER_STYLE,
                "final_answer": _answer(question, category_label),
            }
        )
    return items
