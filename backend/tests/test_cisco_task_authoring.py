"""Cisco-style task authoring: detection, serialization order, safe IDs, DOCTYPE handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.schemas_chat_authoring import (
    ChatAuthoringPattern,
    ChatDitaGenerationOptions,
    ChatSemanticPlan,
    ChatSemanticPlanSection,
    ReferenceStyleProfile,
)
from app.services import reference_dita_analyzer as ref_mod
from app.services.cisco_task_authoring import (
    analyze_task_xml_for_cisco_signals,
    resolve_effective_authoring_pattern,
)
from app.services.dita_topic_draft import TopicDraft
from app.services.dita_topic_serializer import serialize_topic_draft
from app.services.dita_xml_headers import extract_declared_doctype_line, replace_first_doctype_line


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cisco_style_reference_task.dita"

CISCO_LIKE_REFERENCE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">
<reference>
<refbody>
<section><title>Sec</title><p>x</p></section>
<table><tgroup cols="2"><thead><row><entry>H1</entry><entry>H2</entry></row></thead><tbody><row><entry>A</entry><entry>B</entry></row></tbody></tgroup></table>
</refbody>
</reference>
"""


def _load_fixture() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_extract_declared_doctype_line_finds_reference():
    line = extract_declared_doctype_line(CISCO_LIKE_REFERENCE)
    assert line
    assert "DOCTYPE" in line
    assert "reference" in line.lower()


def test_cisco_like_reference_triggers_auto_cisco_reference():
    raw = CISCO_LIKE_REFERENCE
    profile, _w = ref_mod.analyze_reference_dita(raw)
    assert profile is not None
    assert profile.root_local_name == "reference"
    resolved = resolve_effective_authoring_pattern("auto", reference_text=raw, style_profile=profile)
    assert resolved == "cisco_reference"


def test_cisco_fixture_triggers_auto_resolve():
    raw = _load_fixture()
    profile, _w = ref_mod.analyze_reference_dita(raw)
    assert profile is not None
    assert profile.root_local_name == "task"
    assert "uses_step_info" in (profile.structural_habits or [])
    resolved = resolve_effective_authoring_pattern("auto", reference_text=raw, style_profile=profile)
    assert resolved == "cisco_task"


def test_auto_without_reference_stays_default():
    p = ReferenceStyleProfile(root_local_name="task")
    assert resolve_effective_authoring_pattern("auto", reference_text="", style_profile=p) == "default"


def test_explicit_cisco_task_passthrough():
    p = ReferenceStyleProfile(root_local_name="topic")
    assert resolve_effective_authoring_pattern("cisco_task", reference_text="", style_profile=p) == "cisco_task"


def test_profile_does_not_expose_reference_root_id():
    raw = _load_fixture()
    profile, _ = ref_mod.analyze_reference_dita(raw)
    attrs = profile.root_attributes_sample or {}
    assert "id" not in attrs
    assert "T-sample-ref-only" not in str(attrs)


def test_cisco_serializer_taskbody_order_and_fresh_ids():
    raw = _load_fixture()
    profile, _ = ref_mod.analyze_reference_dita(raw)
    draft = TopicDraft(
        dita_type="task",
        title="Configure VLAN from UI",
        shortdesc="New topic from screenshot — not from reference.",
        sections=[
            ChatSemanticPlanSection(
                name="prereq",
                purpose="You need network admin role.",
                details=[],
            ),
            ChatSemanticPlanSection(
                name="context",
                purpose="Goal: mirror VLAN settings shown in the capture.",
                details=[],
            ),
            ChatSemanticPlanSection(
                name="steps",
                purpose="",
                details=[
                    "Open VLANs panel || Expand the VLANs section if it is collapsed.",
                    "Enter vlan 10 in the CLI field",
                ],
            ),
            ChatSemanticPlanSection(name="result", purpose="VLAN list updates.", details=[]),
        ],
        code_snippets=["vlan 10"],
    )
    opts = ChatDitaGenerationOptions(
        authoring_pattern="cisco_task",
        auto_ids=True,
    )
    xml = serialize_topic_draft(
        draft,
        profile=profile,
        options=opts,
        ui_label_hints={"Save", "VLANs"},
    )
    assert "T-sample-ref-only" not in xml
    assert 'id="configure-vlan-from-ui"' in xml or "configure-vlan-from-ui" in xml
    assert "<prereq>" in xml
    i_prereq = xml.index("<prereq>")
    i_context = xml.index("<context>")
    i_steps = xml.index("<steps>")
    i_result = xml.index("<result>")
    assert i_prereq < i_context < i_steps < i_result
    assert "<info>" in xml
    assert "<codeph>vlan 10</codeph>" in xml
    assert "<codeblock>vlan 10</codeblock>" in xml
    assert "xref" not in xml.lower() or "<xref" not in xml
    assert "conref" not in xml.lower()


def test_replace_first_doctype_line():
    doc = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE task PUBLIC "-//OLD//EN" "old.dtd">\n<task/>'
    new_line = '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">'
    out = replace_first_doctype_line(doc, new_line)
    assert "-//OASIS//DTD DITA Task//EN" in out
    assert "-//OLD//EN" not in out


def test_analyze_task_xml_for_cisco_signals_minimal_task():
    raw = "<task><taskbody><steps><step><cmd>x</cmd></step></steps></taskbody></task>"
    score, sigs = analyze_task_xml_for_cisco_signals(raw)
    assert score >= 2
    assert sigs == []


@pytest.mark.parametrize(
    "pattern,expect",
    [
        ("default", "default"),
        ("cisco_task", "cisco_task"),
        ("cisco_reference", "cisco_reference"),
    ],
)
def test_resolve_non_auto(pattern: ChatAuthoringPattern, expect: ChatAuthoringPattern):
    raw = _load_fixture()
    prof, _ = ref_mod.analyze_reference_dita(raw)
    assert resolve_effective_authoring_pattern(pattern, reference_text=raw, style_profile=prof) == expect
