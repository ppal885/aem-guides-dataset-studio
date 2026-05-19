"""Tests for reference DITA style profiling."""

from app.services.reference_dita_analyzer import (
    analyze_reference_dita,
    build_reference_summary,
    extract_declared_doctype_line,
)


def test_extract_doctype_line():
    raw = '<?xml version="1.0"?>\n<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">\n<task id="t1"></task>'
    line = extract_declared_doctype_line(raw)
    assert line is not None
    assert "DOCTYPE" in line
    assert "task" in line.lower()


def test_analyze_task_reference():
    raw = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">
<task id="orig" xml:lang="en-US" outputclass="howto">
  <title>Sample</title>
  <shortdesc>Short.</shortdesc>
  <prolog><metadata><keywords><keyword>k</keyword></keywords></metadata></prolog>
  <taskbody>
    <context><p>Ctx</p></context>
    <steps>
      <step id="s1"><cmd>Do <uicontrol>Save</uicontrol></cmd></step>
    </steps>
    <result><p>Done</p></result>
  </taskbody>
</task>"""
    profile, _ = analyze_reference_dita(raw)
    assert profile.root_local_name == "task"
    assert profile.root_attributes_sample.get("xml:lang") == "en-US"
    assert profile.root_attributes_sample.get("outputclass") == "howto"
    assert "id" not in profile.root_attributes_sample
    assert "taskbody" in profile.child_order_top_level
    assert profile.uses_prolog is True
    assert "uses_steps" in profile.structural_habits
    assert profile.inline_element_usage.get("uicontrol", 0) >= 1


def test_malformed_reference():
    raw = "<task><unclosed>"
    profile, warnings = analyze_reference_dita(raw)
    assert profile.parse_warnings or warnings
    assert "parse" in " ".join(profile.parse_warnings).lower()


def test_build_reference_summary_includes_profile():
    raw = """<?xml version="1.0"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="c1"><title>T</title><conbody><p>Body</p></conbody></concept>"""
    profile, _ = analyze_reference_dita(raw)
    summary = build_reference_summary(filename="ref.dita", raw_text=raw, profile=profile)
    assert summary.root_type == "concept"
    assert summary.style_profile is not None
    assert summary.title == "T"


def test_analyze_reference_extracts_body_section_titles():
    raw = """<?xml version="1.0"?>
<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">
<reference id="r1">
  <title>Translation settings</title>
  <refbody>
    <section><title>Dialog layout</title><p>Layout details.</p></section>
    <section><title>Properties</title><p>Field/value details.</p></section>
    <example><title>Examples</title><codeblock>dita -f pdf</codeblock></example>
  </refbody>
</reference>"""
    profile, _ = analyze_reference_dita(raw)
    assert profile.root_local_name == "reference"
    assert profile.body_section_titles == ["Dialog layout", "Properties", "Examples"]
