from pathlib import Path

import importlib.util


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "index_dita_behavior_corpus.py"
spec = importlib.util.spec_from_file_location("index_dita_behavior_corpus", SCRIPT_PATH)
indexer = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(indexer)


def test_learned_behavior_chunks_are_added_from_experience_league_dita(tmp_path):
    topic = tmp_path / "topics" / "sample.dita"
    topic.parent.mkdir()
    topic.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="sample">
  <title>Generate output with baseline and HTML5</title>
  <prolog><metadata>
    <othermeta name="source-url" content="https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/example"/>
  </metadata></prolog>
  <shortdesc>Create output presets and generate HTML5 or PDF output from the map console.</shortdesc>
  <body>
    <section><title>Workflow</title>
      <p>Open the Map Console, select an output preset, choose a baseline, and generate HTML5 output.</p>
      <p>Review generated output and validate that expected map content appears.</p>
    </section>
  </body>
</topic>
""",
        encoding="utf-8",
    )

    records = indexer.topic_to_behavior_records(
        topic,
        corpus_root=tmp_path / "topics",
        allowed_prefixes=("https://experienceleague.adobe.com/",),
        include_out_of_scope=False,
        max_chars=1400,
        min_chars=80,
    )
    evidence_types = {record["evidence_type"] for record in records}

    assert "learned_behavior_profile" in evidence_types
    assert "generation_oracle" in evidence_types
    assert any("Observed workflow cues" in record["content"] for record in records)
    assert any("Check construct-specific source markers" in record["content"] for record in records)
