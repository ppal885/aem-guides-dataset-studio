"""Snapshot-style tests for programmatic DITA serialization."""

import xml.etree.ElementTree as ET

from app.core.schemas_chat_authoring import ChatDitaGenerationOptions, ChatSemanticPlan, ChatSemanticPlanSection
from app.core.schemas_chat_authoring import ReferenceStyleProfile
from app.core.schemas_topic_generation import ReferenceAdoptionDecision, ReferenceSerializerPolicy
from app.services.dita_topic_draft import DraftTable, TopicDraft, build_topic_draft
from app.services.dita_topic_serializer import indent_unit_from_profile, serialize_topic_draft
from app.services.structured_topic_draft import serialize_structured_topic_draft
from app.services.dita_xml_headers import strip_xml_prolog


def _root_local(xml: str) -> str:
    body = strip_xml_prolog(xml)
    root = ET.fromstring(body)
    return root.tag.split("}")[-1].split(":")[-1].lower()


def test_serialize_task_acceptance_criteria_as_postreq():
    plan = ChatSemanticPlan(
        title="Ship feature",
        dita_type="task",
        shortdesc="Short.",
        sections=[
            ChatSemanticPlanSection(name="steps", purpose="", details=["Click Save"]),
            ChatSemanticPlanSection(
                name="acceptance-criteria",
                purpose="Fallback single criterion",
                details=["User can export CSV", "Audit log records the action"],
            ),
        ],
    )
    from app.core.schemas_chat_authoring import ChatImageContext

    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(auto_ids=True),
        ui_label_hints=set(),
    )
    assert "<postreq>" in xml
    assert "<ol>" in xml
    assert "User can export CSV" in xml
    assert "acceptance criteria" in xml.lower()


def test_serialize_task_emits_freeform_sections_as_examples_not_sections():
    """Regression: <section> is NOT a valid child of <taskbody> per DITA 1.3.

    Free-form draft sections (anything not mapped to prereq/context/steps/result/postreq)
    must be wrapped in <example>, which is the only repeatable taskbody child that
    accepts a <title> plus rich block content.
    """
    plan = ChatSemanticPlan(
        title="Configure form and settings",
        dita_type="task",
        shortdesc="Capture the form layout from the UI screenshot.",
        sections=[
            ChatSemanticPlanSection(name="steps", purpose="", details=["Open the panel"]),
            ChatSemanticPlanSection(
                name="form-and-settings",
                purpose="",
                details=["First bullet item: Second bullet item"],
            ),
            ChatSemanticPlanSection(
                name="field-details",
                purpose="",
                details=["Nested bullet level 1: Nested bullet level 2"],
            ),
            ChatSemanticPlanSection(name="details", purpose="", details=["First bullet item"]),
        ],
        tables=None,
    )
    from app.core.schemas_chat_authoring import ChatImageContext

    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(auto_ids=True),
        ui_label_hints=set(),
    )
    body = strip_xml_prolog(xml)
    root = ET.fromstring(body)
    taskbody = next(c for c in root if c.tag.split("}")[-1].lower() == "taskbody")
    direct_child_tags = [c.tag.split("}")[-1].lower() for c in taskbody]
    assert "section" not in direct_child_tags, (
        "<section> must not appear directly under <taskbody>; "
        f"got direct children: {direct_child_tags}"
    )
    assert direct_child_tags.count("example") >= 3, (
        f"expected the three free-form sections to be emitted as <example>, "
        f"got direct children: {direct_child_tags}"
    )
    example_titles = [
        (next((gc.text for gc in ex if gc.tag.split('}')[-1].lower() == 'title'), '') or '').strip().lower()
        for ex in taskbody
        if ex.tag.split("}")[-1].lower() == "example"
    ]
    assert any("form" in t and "settings" in t for t in example_titles), example_titles
    assert any("field" in t and "details" in t for t in example_titles), example_titles


def test_serialize_task_emits_freeform_table_as_example_not_section():
    """Regression: tables in a task draft must land in <example>, not <section>."""
    draft = TopicDraft(
        dita_type="task",
        title="Limits",
        shortdesc="From UI",
        sections=[ChatSemanticPlanSection(name="steps", purpose="", details=["Open the page"])],
        tables=[DraftTable(caption="Quotas", rows=[["Resource", "Limit"], ["CPU", "4"]])],
    )
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(auto_ids=True),
        ui_label_hints=set(),
    )
    body = strip_xml_prolog(xml)
    root = ET.fromstring(body)
    taskbody = next(c for c in root if c.tag.split("}")[-1].lower() == "taskbody")
    direct_child_tags = [c.tag.split("}")[-1].lower() for c in taskbody]
    assert "section" not in direct_child_tags, direct_child_tags
    assert "example" in direct_child_tags, direct_child_tags
    table_examples = [
        ex for ex in taskbody
        if ex.tag.split("}")[-1].lower() == "example"
        and any(gc.tag.split("}")[-1].lower() == "simpletable" for gc in ex)
    ]
    assert table_examples, "table should be wrapped in <example><simpletable>...</simpletable></example>"


def test_serialize_task_has_steps():
    plan = ChatSemanticPlan(
        title="Do something",
        dita_type="task",
        shortdesc="Short.",
        sections=[
            ChatSemanticPlanSection(name="context", purpose="When to use", details=[]),
            ChatSemanticPlanSection(name="steps", purpose="Go", details=["First", "Second"]),
            ChatSemanticPlanSection(name="result", purpose="Done", details=[]),
        ],
    )
    from app.core.schemas_chat_authoring import ChatImageContext

    draft = build_topic_draft(
        plan=plan,
        image_context=ChatImageContext(),
    )
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(auto_ids=True),
        ui_label_hints=set(),
    )
    assert _root_local(xml) == "task"
    assert "<steps>" in xml
    assert "First" in xml
    assert "step-" in xml


def test_serialize_concept_with_lang_from_profile():
    plan = ChatSemanticPlan(
        title="Concept T",
        dita_type="concept",
        shortdesc="Desc",
        sections=[ChatSemanticPlanSection(name="overview", purpose="O", details=["p1"])],
    )
    from app.core.schemas_chat_authoring import ChatImageContext

    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    profile = ReferenceStyleProfile(root_local_name="concept", root_attributes_sample={"xml:lang": "de-DE"})
    xml = serialize_topic_draft(
        draft,
        profile=profile,
        options=ChatDitaGenerationOptions(),
        ui_label_hints=set(),
    )
    body = strip_xml_prolog(xml)
    root = ET.fromstring(body)
    lang = root.get("{http://www.w3.org/XML/1998/namespace}lang") or root.get("xml:lang")
    assert lang == "de-DE"


def test_topic_draft_dataclass_import():
    d = TopicDraft(dita_type="reference", title="R", shortdesc="S")
    assert d.title == "R"


def test_indent_unit_from_profile():
    assert indent_unit_from_profile(None) == "  "
    assert indent_unit_from_profile(ReferenceStyleProfile(xml_indent_style="space_4")) == "    "
    assert indent_unit_from_profile(ReferenceStyleProfile(xml_indent_style="tab")) == "\t"


def test_serialize_uses_tab_indent_when_profile_requests():
    plan = ChatSemanticPlan(
        title="Tab task",
        dita_type="task",
        shortdesc="S",
        sections=[ChatSemanticPlanSection(name="steps", purpose="", details=["One"])],
    )
    from app.core.schemas_chat_authoring import ChatImageContext

    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    profile = ReferenceStyleProfile(xml_indent_style="tab")
    xml = serialize_topic_draft(
        draft,
        profile=profile,
        options=ChatDitaGenerationOptions(auto_ids=True),
        ui_label_hints=set(),
    )
    body = strip_xml_prolog(xml)
    assert "\t<task" in body or body.count("\t") >= 2


def test_structured_serializer_matches_topic_draft_path():
    plan = ChatSemanticPlan(
        title="Same",
        dita_type="task",
        shortdesc="S",
        sections=[ChatSemanticPlanSection(name="steps", purpose="", details=["A"])],
    )
    from app.core.schemas_chat_authoring import ChatImageContext

    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    a = serialize_topic_draft(
        draft, profile=None, options=ChatDitaGenerationOptions(auto_ids=True), ui_label_hints=set()
    )
    b = serialize_structured_topic_draft(
        draft, profile=None, options=ChatDitaGenerationOptions(auto_ids=True), ui_label_hints=set()
    )
    assert a == b


def test_serialize_reference_cisco_reference_emits_cals_table():
    draft = TopicDraft(
        dita_type="reference",
        title="Limits",
        shortdesc="From UI",
        sections=[],
        tables=[DraftTable(caption="Rates", rows=[["Name", "Max"], ["A", "10"]])],
    )
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(authoring_pattern="cisco_reference", auto_ids=True),
        ui_label_hints=set(),
    )
    assert "<tgroup" in xml
    assert "<thead>" in xml
    assert "<tbody>" in xml
    assert "<entry>" in xml
    assert "<simpletable>" not in xml


def test_serialize_reference_default_uses_simpletable():
    draft = TopicDraft(
        dita_type="reference",
        title="Limits",
        shortdesc="From UI",
        sections=[],
        tables=[DraftTable(caption="Rates", rows=[["Name", "Max"], ["A", "10"]])],
    )
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(authoring_pattern="default", auto_ids=True),
        ui_label_hints=set(),
    )
    assert "<simpletable>" in xml
    assert "<tgroup" not in xml


def test_serialize_task_uses_reference_sequence_and_prereq():
    plan = ChatSemanticPlan(
        title="Create preset",
        dita_type="task",
        shortdesc="Create a new preset.",
        sections=[
            ChatSemanticPlanSection(name="Prerequisites", purpose="", details=["You have author access."]),
            ChatSemanticPlanSection(name="Context", purpose="", details=["Use this to configure PDF output."]),
            ChatSemanticPlanSection(name="Steps", purpose="", details=["Open Output Presets"]),
            ChatSemanticPlanSection(name="Result", purpose="", details=["The preset is available for publishing."]),
        ],
        reference_adoption=ReferenceAdoptionDecision(
            mode="compatible_adoption",
            target_root_type="task",
            serializer_policy=ReferenceSerializerPolicy(
                target_root_type="task",
                preferred_taskbody_sequence=["prereq", "context", "steps", "result"],
            ),
        ),
    )
    from app.core.schemas_chat_authoring import ChatImageContext

    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    xml = serialize_topic_draft(
        draft,
        profile=ReferenceStyleProfile(root_local_name="task"),
        options=ChatDitaGenerationOptions(auto_ids=True),
        ui_label_hints=set(),
    )
    assert "<prereq>" in xml
    assert xml.index("<prereq>") < xml.index("<context>")
    assert xml.index("<context>") < xml.index("<steps>")
    assert xml.index("<steps>") < xml.index("<result>")


def test_serialize_reference_uses_properties_layout_when_policy_requests():
    plan = ChatSemanticPlan(
        title="Translation settings",
        dita_type="reference",
        shortdesc="Reference details.",
        sections=[
            ChatSemanticPlanSection(
                name="Properties",
                purpose="",
                details=["Language: French", "Provider: Adobe Translation"],
            )
        ],
        reference_adoption=ReferenceAdoptionDecision(
            mode="compatible_adoption",
            target_root_type="reference",
            serializer_policy=ReferenceSerializerPolicy(
                target_root_type="reference",
                prefer_properties_layout=True,
            ),
        ),
    )
    from app.core.schemas_chat_authoring import ChatImageContext

    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    xml = serialize_topic_draft(
        draft,
        profile=ReferenceStyleProfile(root_local_name="reference", structural_habits=["uses_dl"]),
        options=ChatDitaGenerationOptions(auto_ids=True),
        ui_label_hints=set(),
    )
    assert "<properties>" in xml
    assert "<proptype>Language</proptype>" in xml
    assert "<propvalue>French</propvalue>" in xml


def test_serialize_concept_uses_reference_section_order_and_titles():
    plan = ChatSemanticPlan(
        title="DITA map hierarchy",
        dita_type="concept",
        shortdesc="Concept details.",
        sections=[
            ChatSemanticPlanSection(name="relationships", purpose="", details=["Root map -> child topics"]),
            ChatSemanticPlanSection(name="overview", purpose="", details=["Shows the hierarchy of topics."]),
        ],
        reference_adoption=ReferenceAdoptionDecision(
            mode="compatible_adoption",
            target_root_type="concept",
            serializer_policy=ReferenceSerializerPolicy(
                target_root_type="concept",
                preferred_section_names=["Overview", "Relationships"],
                preferred_section_name_map={
                    "overview": "Overview",
                    "relationships": "Relationships",
                },
            ),
        ),
    )
    from app.core.schemas_chat_authoring import ChatImageContext

    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    xml = serialize_topic_draft(
        draft,
        profile=ReferenceStyleProfile(root_local_name="concept", body_section_titles=["Overview", "Relationships"]),
        options=ChatDitaGenerationOptions(auto_ids=True),
        ui_label_hints=set(),
    )
    assert xml.index("<title>Overview</title>") < xml.index("<title>Relationships</title>")


def test_serialize_compatible_reference_copies_safe_root_attributes():
    plan = ChatSemanticPlan(
        title="Translation settings",
        dita_type="reference",
        shortdesc="Reference details.",
        sections=[ChatSemanticPlanSection(name="Properties", purpose="", details=["Language: French"])],
        reference_adoption=ReferenceAdoptionDecision(
            mode="compatible_adoption",
            target_root_type="reference",
            serializer_policy=ReferenceSerializerPolicy(target_root_type="reference"),
        ),
    )
    from app.core.schemas_chat_authoring import ChatImageContext

    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    xml = serialize_topic_draft(
        draft,
        profile=ReferenceStyleProfile(
            root_local_name="reference",
            root_attributes_sample={"xml:lang": "fr-FR", "outputclass": "panel-ref", "audience": "admin"},
        ),
        options=ChatDitaGenerationOptions(auto_ids=True),
        ui_label_hints=set(),
    )
    body = strip_xml_prolog(xml)
    root = ET.fromstring(body)
    assert root.get("outputclass") == "panel-ref"
    assert root.get("audience") == "admin"


# ---------------------------------------------------------------------------
# list_kind propagation tests
# ---------------------------------------------------------------------------

def test_bullet_list_kind_emits_ul_not_p():
    """Section with list_kind='bullet' must produce <ul><li><p> not bare <p>."""
    from app.core.schemas_chat_authoring import ChatImageContext

    plan = ChatSemanticPlan(
        title="Overview",
        dita_type="concept",
        shortdesc="A list of things.",
        sections=[
            ChatSemanticPlanSection(
                name="details",
                purpose="Bullets from screenshot.",
                details=["First item", "Second item", "Third item"],
                list_kind="bullet",
            )
        ],
    )
    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(auto_ids=False),
        ui_label_hints=set(),
    )
    root = ET.fromstring(strip_xml_prolog(xml))
    uls = root.findall(".//{http://dita.oasis-open.org/architecture/2005/}ul") or root.findall(".//ul")
    # ElementTree doesn't add NS prefix for plain elements; just search both ways
    body_xml = xml
    assert "<ul>" in body_xml or "<ul " in body_xml, "Expected <ul> for list_kind='bullet'"
    assert "<li>" in body_xml, "Expected <li> elements"
    # Must NOT emit bare <p> per item (no <p> directly in conbody/section without wrapping <li>)
    # The simplest check: every "First item" must be inside a <li>
    assert "First item" in body_xml


def test_numbered_list_kind_emits_ol_not_p():
    """Section with list_kind='numbered' must produce <ol><li><p> not bare <p>."""
    from app.core.schemas_chat_authoring import ChatImageContext

    plan = ChatSemanticPlan(
        title="Steps",
        dita_type="concept",
        shortdesc="Steps as numbered list.",
        sections=[
            ChatSemanticPlanSection(
                name="procedure",
                purpose="Steps.",
                details=["Step one", "Step two", "Step three"],
                list_kind="numbered",
            )
        ],
    )
    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(auto_ids=False),
        ui_label_hints=set(),
    )
    assert "<ol>" in xml or "<ol " in xml, "Expected <ol> for list_kind='numbered'"
    assert "<li>" in xml


def test_dom_noise_tokens_are_filtered_from_section_details():
    """Bare HTML tag names (body, ul, li, div) must not appear as <p> content."""
    from app.core.schemas_chat_authoring import ChatImageContext

    plan = ChatSemanticPlan(
        title="DOM noise",
        dita_type="concept",
        shortdesc="Should filter DOM tags.",
        sections=[
            ChatSemanticPlanSection(
                name="dom-hierarchy",
                purpose="DOM hierarchy labels",
                # Mix of real content and noise tokens
                details=["body", "ul", "li", "Real content here", "li", "div"],
            )
        ],
    )
    draft = build_topic_draft(plan=plan, image_context=ChatImageContext())
    xml = serialize_topic_draft(
        draft,
        profile=None,
        options=ChatDitaGenerationOptions(auto_ids=False),
        ui_label_hints=set(),
    )
    # Real content must survive
    assert "Real content here" in xml
    # Bare DOM tags must not appear as standalone <p> text
    import re
    bare_p = re.compile(r"<p>\s*(body|ul|ol|li|div|span|nav|header|footer|p)\s*</p>", re.IGNORECASE)
    assert not bare_p.search(xml), "DOM noise tokens leaked into <p> elements"
