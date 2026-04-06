"""Tests for the Diagram Generation service."""

import asyncio

from app.services.diagram_generation_service import (
    generate_concept_map,
    generate_diagram,
    generate_map_diagram,
    generate_process_flow,
    generate_task_flowchart,
    _escape_label,
)


def _run(coro):
    """Helper to run async functions in sync tests."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Sample DITA XML fixtures
# ---------------------------------------------------------------------------

TASK_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<task id="configure_auth">
  <title>Configure Authentication</title>
  <taskbody>
    <steps>
      <step><cmd>Open the Settings panel.</cmd></step>
      <step><cmd>Enter your username.</cmd></step>
      <step><cmd>Click Save.</cmd></step>
    </steps>
  </taskbody>
</task>"""

TASK_CHOICES_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<task id="setup_auth">
  <title>Set Up Auth Method</title>
  <taskbody>
    <steps>
      <step><cmd>Open Settings.</cmd></step>
      <step>
        <cmd>Choose authentication method</cmd>
        <choices>
          <choice>Use OAuth token</choice>
          <choice>Use API key</choice>
        </choices>
      </step>
      <step><cmd>Save configuration.</cmd></step>
    </steps>
  </taskbody>
</task>"""

TASK_SUBSTEPS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<task id="install_plugin">
  <title>Install Plugin</title>
  <taskbody>
    <steps>
      <step>
        <cmd>Prepare environment</cmd>
        <substeps>
          <substep><cmd>Check Java version</cmd></substep>
          <substep><cmd>Verify Maven installed</cmd></substep>
        </substeps>
      </step>
      <step><cmd>Run installer</cmd></step>
    </steps>
  </taskbody>
</task>"""

TASK_STEPSECTION_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<task id="deploy_app">
  <title>Deploy Application</title>
  <taskbody>
    <steps>
      <stepsection>Preparation phase</stepsection>
      <step><cmd>Build the project.</cmd></step>
      <step><cmd>Run tests.</cmd></step>
    </steps>
  </taskbody>
</task>"""

TASK_EMPTY_STEPS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<task id="empty_task">
  <title>Empty Task</title>
  <taskbody>
    <context>No steps here.</context>
  </taskbody>
</task>"""

CONCEPT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<concept id="cloud_arch">
  <title>Cloud Architecture Overview</title>
  <conbody>
    <section>
      <title>Compute Layer</title>
      <p>Handles processing workloads.</p>
    </section>
    <section>
      <title>Storage Layer</title>
      <dl>
        <dlentry><dt>Block Storage</dt><dd>High performance disks.</dd></dlentry>
        <dlentry><dt>Object Storage</dt><dd>S3-compatible buckets.</dd></dlentry>
      </dl>
    </section>
    <section>
      <title>Network Layer</title>
      <p>Manages connectivity.</p>
    </section>
  </conbody>
</concept>"""

MAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<map>
  <title>Product Guide</title>
  <topicref href="intro.dita" navtitle="Introduction">
    <topicref href="getting_started.dita" navtitle="Getting Started"/>
    <topicref href="installation.dita" navtitle="Installation"/>
  </topicref>
  <topicref href="advanced.dita" navtitle="Advanced Topics">
    <topicref href="config.dita" navtitle="Configuration"/>
  </topicref>
</map>"""

MAP_NESTED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<map>
  <title>Deep Nested Map</title>
  <topicref href="a.dita" navtitle="A">
    <topicref href="b.dita" navtitle="B">
      <topicref href="c.dita" navtitle="C"/>
    </topicref>
  </topicref>
</map>"""

OL_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<topic id="process_overview">
  <title>Onboarding Process</title>
  <body>
    <ol>
      <li>Submit application form.</li>
      <li>Complete background check.</li>
      <li>Attend orientation.</li>
      <li>Set up workstation.</li>
    </ol>
  </body>
</topic>"""

MALFORMED_XML = """<task id="broken"><title>Broken<taskbody><steps></task>"""

SPECIAL_CHARS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<task id="special">
  <title>Handle "Special" &amp; [Chars]</title>
  <taskbody>
    <steps>
      <step><cmd>Use {curly} &amp; [square] brackets | pipes</cmd></step>
    </steps>
  </taskbody>
</task>"""


# ---------------------------------------------------------------------------
# 1. Task flowchart tests
# ---------------------------------------------------------------------------

def test_task_flowchart_basic():
    result = generate_task_flowchart(TASK_XML)
    assert result["diagram_type"] == "flowchart"
    assert result["mermaid_code"].startswith("flowchart TD")
    # 3 steps + Start + End = 5 nodes
    assert result["node_count"] == 5
    assert "Configure Authentication" in result["title"]


def test_task_flowchart_with_choices():
    result = generate_task_flowchart(TASK_CHOICES_XML)
    assert result["diagram_type"] == "flowchart"
    code = result["mermaid_code"]
    assert "flowchart TD" in code
    # Diamond decision node uses { } syntax
    assert "{" in code and "}" in code
    # Two choice branches
    assert "OAuth" in code or "oauth" in code.lower()
    assert "API key" in code or "api key" in code.lower()


def test_task_flowchart_with_substeps():
    result = generate_task_flowchart(TASK_SUBSTEPS_XML)
    assert result["diagram_type"] == "flowchart"
    code = result["mermaid_code"]
    assert "Check Java version" in code
    assert "Verify Maven installed" in code
    # Parent step + 2 substeps + final step + Start + End = 6
    assert result["node_count"] == 6


def test_task_flowchart_with_stepsection():
    result = generate_task_flowchart(TASK_STEPSECTION_XML)
    code = result["mermaid_code"]
    assert "Preparation phase" in code


def test_task_empty_steps():
    result = generate_task_flowchart(TASK_EMPTY_STEPS_XML)
    assert result["diagram_type"] == "flowchart"
    # Minimal diagram
    assert result["node_count"] == 2
    assert "Start" in result["mermaid_code"]
    assert "Done" in result["mermaid_code"]


# ---------------------------------------------------------------------------
# 2. Concept mindmap tests
# ---------------------------------------------------------------------------

def test_concept_mindmap():
    result = generate_concept_map(CONCEPT_XML)
    assert result["diagram_type"] == "mindmap"
    code = result["mermaid_code"]
    assert code.startswith("mindmap")
    assert "Cloud Architecture Overview" in code
    assert "Compute Layer" in code
    assert "Storage Layer" in code
    assert "Network Layer" in code


def test_concept_mindmap_dl_terms():
    result = generate_concept_map(CONCEPT_XML)
    code = result["mermaid_code"]
    assert "Block Storage" in code
    assert "Object Storage" in code


def test_concept_mindmap_node_count():
    result = generate_concept_map(CONCEPT_XML)
    # root + 3 sections + 2 DL terms + 2 paragraphs (Compute + Network) = 8
    assert result["node_count"] >= 6


# ---------------------------------------------------------------------------
# 3. Map structure tests
# ---------------------------------------------------------------------------

def test_map_structure_basic():
    result = generate_map_diagram(MAP_XML)
    assert result["diagram_type"] == "map_structure"
    code = result["mermaid_code"]
    assert code.startswith("flowchart TD")
    assert "Product Guide" in code
    assert "Introduction" in code
    assert "Getting Started" in code
    assert "Advanced Topics" in code


def test_map_structure_node_count():
    result = generate_map_diagram(MAP_XML)
    # 1 root + 2 top-level + 3 children = 6
    assert result["node_count"] == 6


def test_map_nested_topicrefs():
    result = generate_map_diagram(MAP_NESTED_XML)
    code = result["mermaid_code"]
    # A -> B -> C nesting
    assert "A" in code
    assert "B" in code
    assert "C" in code
    assert result["node_count"] == 4  # root + A + B + C


# ---------------------------------------------------------------------------
# 4. Process flow tests
# ---------------------------------------------------------------------------

def test_process_flow():
    result = generate_process_flow(OL_XML)
    assert result["diagram_type"] == "process_flow"
    code = result["mermaid_code"]
    assert code.startswith("flowchart TD")
    assert "Submit application form" in code
    assert "Attend orientation" in code
    # 4 items + Start + End = 6
    assert result["node_count"] == 6


# ---------------------------------------------------------------------------
# 5. Auto-detection tests
# ---------------------------------------------------------------------------

def test_auto_detect_task():
    result = _run(generate_diagram(TASK_XML, diagram_type="auto"))
    assert result["diagram_type"] == "flowchart"


def test_auto_detect_concept():
    result = _run(generate_diagram(CONCEPT_XML, diagram_type="auto"))
    assert result["diagram_type"] == "mindmap"


def test_auto_detect_map():
    result = _run(generate_diagram(MAP_XML, diagram_type="auto"))
    assert result["diagram_type"] == "map_structure"


def test_auto_detect_process_flow():
    result = _run(generate_diagram(OL_XML, diagram_type="auto"))
    assert result["diagram_type"] == "process_flow"


# ---------------------------------------------------------------------------
# 6. Error handling and edge cases
# ---------------------------------------------------------------------------

def test_malformed_xml_returns_error():
    result = _run(generate_diagram(MALFORMED_XML))
    assert "error" in result
    assert result["mermaid_code"] == ""
    assert result["node_count"] == 0


def test_special_characters_escaped():
    result = generate_task_flowchart(SPECIAL_CHARS_XML)
    code = result["mermaid_code"]
    # Brackets and pipes should be escaped/replaced
    assert "[square]" not in code
    assert "|" not in code or "-->|" in code  # pipes only in edge labels
    assert "{curly}" not in code


def test_escape_label_function():
    assert _escape_label('Hello "World"') == "Hello 'World'"
    assert _escape_label("A | B") == "A / B"
    assert _escape_label("Use [brackets]") == "Use (brackets)"
    assert _escape_label("") == ""
    assert _escape_label("A & B") == "A and B"


def test_title_extraction():
    result = generate_task_flowchart(TASK_XML)
    assert result["title"] == "Configure Authentication"


def test_svg_placeholder():
    result = generate_task_flowchart(TASK_XML)
    assert "Flowchart" in result["svg_placeholder"]
    assert "nodes" in result["svg_placeholder"]


# ---------------------------------------------------------------------------
# 7. Explicit diagram_type override
# ---------------------------------------------------------------------------

def test_explicit_type_overrides_auto():
    # Force mindmap on a task topic
    result = _run(generate_diagram(TASK_XML, diagram_type="mindmap"))
    assert result["diagram_type"] == "mindmap"


def test_explicit_flowchart_on_concept():
    result = _run(generate_diagram(CONCEPT_XML, diagram_type="flowchart"))
    assert result["diagram_type"] == "flowchart"
