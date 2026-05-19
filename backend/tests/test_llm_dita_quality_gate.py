from app.generator import llm_dita_generator


def test_quality_gate_flags_placeholder_heavy_task_output():
    xml = """
    <task id="configure-radware-vdp-cluster">
      <title>Configure Radware vDP Cluster</title>
      <shortdesc>Configure a Radware vDP cluster</shortdesc>
      <taskbody>
        <section>
          <title>Introduction</title>
          <p>Briefly introduce the task of configuring a Radware vDP cluster.</p>
        </section>
        <section>
          <title>Configuration Steps</title>
          <p>Use the user interface to configure the cluster.</p>
        </section>
      </taskbody>
    </task>
    """

    issues = llm_dita_generator._quality_gate_issues(xml)

    assert issues
    assert any("placeholder" in issue.lower() or "filler" in issue.lower() for issue in issues)


def test_reference_root_is_accepted_and_gets_reference_doctype():
    xml = """
    <reference id="sample-reference">
      <title>Sample reference</title>
      <shortdesc>Summarize what this reference topic covers.</shortdesc>
      <refbody>
        <section>
          <title>Supported values</title>
          <p>Value A enables the feature.</p>
        </section>
      </refbody>
    </reference>
    """

    assert llm_dita_generator._is_valid_dita_xml(xml) is True
    wrapped = llm_dita_generator._wrap_with_doctype(xml).decode("utf-8")
    assert '<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN"' in wrapped
