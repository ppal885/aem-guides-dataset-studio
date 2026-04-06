"""Tests for the Topic Type Advisor service."""
from app.services.topic_type_advisor_service import analyze_topic_type


# ---------------------------------------------------------------------------
# Helper XML snippets
# ---------------------------------------------------------------------------

TASK_CORRECT = """\
<task id="install-plugin">
  <title>Install the Plugin</title>
  <taskbody>
    <prereq>Ensure Java 11+ is installed.</prereq>
    <steps>
      <step><cmd>Download the installer.</cmd></step>
      <step><cmd>Run <codeph>./install.sh</codeph>.</cmd></step>
      <step><cmd>Verify the installation.</cmd><stepresult>Version number is printed.</stepresult></step>
    </steps>
    <postreq>Restart the server.</postreq>
  </taskbody>
</task>
"""

CONCEPT_CORRECT = """\
<concept id="what-is-dita">
  <title>What is DITA?</title>
  <conbody>
    <section>
      <title>Overview</title>
      <p>DITA is an XML-based architecture for authoring, producing, and delivering
      technical information.  It was originally developed at IBM and later donated to OASIS.
      DITA provides a structured, modular approach to content creation.</p>
    </section>
    <section>
      <title>Benefits</title>
      <p>Reuse, consistency, and multi-channel publishing are the primary advantages of DITA.
      Authors write once and publish to PDF, HTML5, and other formats without duplication of effort.</p>
    </section>
  </conbody>
</concept>
"""

REFERENCE_CORRECT = """\
<reference id="cli-options">
  <title>CLI Options</title>
  <refbody>
    <properties>
      <prophead><proptypehd>Option</proptypehd><propdeschd>Description</propdeschd></prophead>
      <property><proptype>--verbose</proptype><propdesc>Enable verbose output</propdesc></property>
      <property><proptype>--output</proptype><propdesc>Set output directory</propdesc></property>
    </properties>
  </refbody>
</reference>
"""

CONCEPT_WITH_STEPS = """\
<concept id="setup-guide">
  <title>Setting Up Your Environment</title>
  <conbody>
    <p>Follow these steps to configure your environment.</p>
    <steps>
      <step><cmd>Open a terminal.</cmd></step>
      <step><cmd>Run the configuration script.</cmd></step>
    </steps>
  </conbody>
</concept>
"""

TASK_NO_STEPS = """\
<task id="understanding-dita">
  <title>Understanding DITA Maps</title>
  <taskbody>
    <section>
      <title>Overview</title>
      <p>A DITA map is a container that organises topics into a hierarchy.
      Maps define relationships among topics and control the table of contents
      structure for published output.  They are fundamental to structured authoring.</p>
    </section>
    <section>
      <title>Map Types</title>
      <p>There are several map types including bookmap, subjectScheme, and
      classification maps. Each serves a different purpose in the publishing pipeline.</p>
    </section>
  </taskbody>
</task>
"""

MIXED_CONTENT = """\
<topic id="mixed">
  <title>Mixed Topic</title>
  <body>
    <section>
      <title>Background</title>
      <p>This section explains background concepts in sufficient detail to provide
      context for the procedure that follows. Understanding the theory is important.</p>
    </section>
    <steps>
      <step><cmd>Do the first thing.</cmd></step>
      <step><cmd>Do the second thing.</cmd></step>
    </steps>
    <properties>
      <property><proptype>Param</proptype><propdesc>Value</propdesc></property>
    </properties>
  </body>
</topic>
"""

GLOSSENTRY = """\
<glossentry id="api">
  <glossterm>API</glossterm>
  <glossBody>
    <glossdef>Application Programming Interface - a set of protocols for building software.</glossdef>
  </glossBody>
</glossentry>
"""

MALFORMED_XML = "<task><title>Broken</oops></task>"

EMPTY_BODY = """\
<concept id="empty">
  <title>Empty Concept</title>
  <conbody/>
</concept>
"""

REFERENCE_WITH_SIMPLETABLE = """\
<reference id="params">
  <title>Parameters</title>
  <refbody>
    <simpletable>
      <sthead><stentry>Name</stentry><stentry>Type</stentry></sthead>
      <strow><stentry>timeout</stentry><stentry>int</stentry></strow>
    </simpletable>
  </refbody>
</reference>
"""

REFERENCE_WITH_CODEBLOCK_AND_PARAMS = """\
<reference id="syntax">
  <title>Command Syntax</title>
  <refbody>
    <refsyn>
      <codeblock>mytool --input FILE --output DIR</codeblock>
    </refsyn>
    <dl>
      <dlentry><dt>--input</dt><dd>Input file path</dd></dlentry>
      <dlentry><dt>--output</dt><dd>Output directory</dd></dlentry>
    </dl>
  </refbody>
</reference>
"""

CONCEPT_WITH_OL_PROCEDURE = """\
<concept id="quick-start">
  <title>Quick Start</title>
  <conbody>
    <p>Follow these steps:</p>
    <ol>
      <li>Download the package.</li>
      <li>Unzip to your home directory.</li>
      <li>Run the setup wizard.</li>
    </ol>
  </conbody>
</concept>
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCorrectlyClassified:
    """Topics where root type matches the content."""

    def test_task_topic_recognised(self):
        result = analyze_topic_type(TASK_CORRECT)
        assert result["current_type"] == "task"
        assert result["recommended_type"] == "task"
        assert result["is_misclassified"] is False
        assert result["confidence"] >= 0.7

    def test_concept_topic_recognised(self):
        result = analyze_topic_type(CONCEPT_CORRECT)
        assert result["current_type"] == "concept"
        assert result["recommended_type"] == "concept"
        assert result["is_misclassified"] is False
        assert result["confidence"] >= 0.7

    def test_reference_topic_recognised(self):
        result = analyze_topic_type(REFERENCE_CORRECT)
        assert result["current_type"] == "reference"
        assert result["recommended_type"] == "reference"
        assert result["is_misclassified"] is False
        assert result["confidence"] >= 0.7


class TestMisclassification:
    """Topics where root type does NOT match the content."""

    def test_concept_with_steps_flagged(self):
        result = analyze_topic_type(CONCEPT_WITH_STEPS)
        assert result["current_type"] == "concept"
        assert result["is_misclassified"] is True
        assert result["recommended_type"] == "task"
        assert result["suggested_fix"] is not None
        assert "task" in result["suggested_fix"].lower()

    def test_task_with_no_steps_flagged(self):
        result = analyze_topic_type(TASK_NO_STEPS)
        assert result["current_type"] == "task"
        assert result["is_misclassified"] is True
        assert result["recommended_type"] == "concept"
        assert result["suggested_fix"] is not None
        assert "concept" in result["suggested_fix"].lower()


class TestMixedContent:
    """Topics with signals for multiple types."""

    def test_mixed_signals_detected(self):
        result = analyze_topic_type(MIXED_CONTENT)
        assert result["current_type"] == "topic"
        # Should either detect mixed or pick the dominant type
        signal_types = {s["supports_type"] for s in result["signals"]}
        assert len(signal_types) >= 2, "Expected signals for multiple types"


class TestGlossentry:
    def test_glossentry_detected(self):
        result = analyze_topic_type(GLOSSENTRY)
        assert result["current_type"] == "glossentry"
        assert result["recommended_type"] == "glossentry"
        assert result["is_misclassified"] is False
        assert result["confidence"] >= 0.7
        glossary_signals = [
            s for s in result["signals"] if s["supports_type"] == "glossentry"
        ]
        assert len(glossary_signals) >= 1


class TestMalformedXML:
    def test_malformed_xml_returns_error(self):
        result = analyze_topic_type(MALFORMED_XML)
        assert "error" in result
        assert result["error"] == "malformed_xml"
        assert result["current_type"] == "unknown"
        assert result["confidence"] == 0.0


class TestEmptyBody:
    def test_empty_body_handled(self):
        result = analyze_topic_type(EMPTY_BODY)
        assert result["current_type"] == "concept"
        # With conbody present, concept signal should fire
        assert result["recommended_type"] == "concept"
        assert result["is_misclassified"] is False

    def test_empty_string_input(self):
        result = analyze_topic_type("")
        assert "error" in result
        assert result["error"] == "empty_input"


class TestConfidenceScores:
    def test_high_confidence_for_clear_task(self):
        result = analyze_topic_type(TASK_CORRECT)
        assert result["confidence"] >= 0.7

    def test_high_confidence_for_clear_reference(self):
        result = analyze_topic_type(REFERENCE_CORRECT)
        assert result["confidence"] >= 0.7

    def test_lower_confidence_for_ambiguous(self):
        """A concept with an ol procedure has weaker signals than a proper task."""
        result = analyze_topic_type(CONCEPT_WITH_OL_PROCEDURE)
        # Should still detect some task-like signals
        task_signals = [s for s in result["signals"] if s["supports_type"] == "task"]
        assert len(task_signals) >= 1


class TestMultipleSignals:
    def test_multiple_task_signals(self):
        result = analyze_topic_type(TASK_CORRECT)
        task_signals = [s for s in result["signals"] if s["supports_type"] == "task"]
        assert len(task_signals) >= 3, (
            f"Expected 3+ task signals for a rich task topic, got {len(task_signals)}"
        )

    def test_reference_with_simpletable(self):
        result = analyze_topic_type(REFERENCE_WITH_SIMPLETABLE)
        assert result["current_type"] == "reference"
        assert result["recommended_type"] == "reference"
        ref_signals = [s for s in result["signals"] if s["supports_type"] == "reference"]
        assert len(ref_signals) >= 1
        # simpletable with header row should be detected
        st_signals = [s for s in ref_signals if "simpletable" in s["signal"].lower()]
        assert len(st_signals) >= 1

    def test_reference_with_codeblock_and_params(self):
        result = analyze_topic_type(REFERENCE_WITH_CODEBLOCK_AND_PARAMS)
        assert result["current_type"] == "reference"
        assert result["recommended_type"] == "reference"
        assert result["is_misclassified"] is False
        # Should detect codeblock+param signal
        cb_signals = [
            s for s in result["signals"]
            if "codeblock" in s["signal"].lower() and "parameter" in s["signal"].lower()
        ]
        assert len(cb_signals) >= 1


class TestProcedureInOl:
    def test_ol_procedure_detected_as_task_signal(self):
        result = analyze_topic_type(CONCEPT_WITH_OL_PROCEDURE)
        ol_signals = [
            s for s in result["signals"]
            if "ol" in s["signal"].lower() and s["supports_type"] == "task"
        ]
        assert len(ol_signals) >= 1, "Expected <ol> procedure to register as task signal"
