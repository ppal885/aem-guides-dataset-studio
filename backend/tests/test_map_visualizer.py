"""Tests for map_visualizer_service — DITA map graph parsing."""

import time
import pytest
from app.services.map_visualizer_service import parse_map_to_graph, graph_to_mermaid


SIMPLE_DITAMAP = """\
<map title="User Guide">
  <title>User Guide</title>
  <topicref href="intro.dita" navtitle="Introduction"/>
  <topicref href="install.dita" navtitle="Installation"/>
  <topicref href="config.dita" navtitle="Configuration"/>
</map>
"""

NESTED_DITAMAP = """\
<map title="Nested Guide">
  <title>Nested Guide</title>
  <topicref href="a.dita" navtitle="A">
    <topicref href="a1.dita" navtitle="A1">
      <topicref href="a1i.dita" navtitle="A1i">
        <topicref href="a1i_x.dita" navtitle="A1i-X">
          <topicref href="a1i_x_deep.dita" navtitle="A1i-X-Deep"/>
        </topicref>
      </topicref>
    </topicref>
  </topicref>
</map>
"""

BOOKMAP_XML = """\
<bookmap>
  <title>Admin Book</title>
  <chapter href="ch1.dita" navtitle="Chapter 1">
    <topicref href="sec1.dita" navtitle="Section 1"/>
  </chapter>
  <chapter href="ch2.dita" navtitle="Chapter 2"/>
  <appendix href="app_a.dita" navtitle="Appendix A"/>
</bookmap>
"""

NO_NAVTITLE_MAP = """\
<map>
  <title>No Navtitle Map</title>
  <topicref href="some_topic.dita"/>
  <topicref href="another/path/my_file.dita"/>
</map>
"""

RELTABLE_MAP = """\
<map>
  <title>Rel Map</title>
  <topicref href="a.dita" navtitle="A"/>
  <topicref href="b.dita" navtitle="B"/>
  <topicref href="c.dita" navtitle="C"/>
  <reltable>
    <relrow>
      <relcell><topicref href="a.dita"/></relcell>
      <relcell><topicref href="b.dita"/></relcell>
    </relrow>
    <relrow>
      <relcell><topicref href="b.dita"/></relcell>
      <relcell><topicref href="c.dita"/></relcell>
    </relrow>
  </reltable>
</map>
"""

EMPTY_MAP = """\
<map>
  <title>Empty Map</title>
</map>
"""

TOPICGROUP_MAP = """\
<map>
  <title>Grouped Map</title>
  <topicgroup>
    <topicref href="t1.dita" navtitle="T1"/>
    <topicref href="t2.dita" navtitle="T2"/>
  </topicgroup>
  <topichead navtitle="Section Head">
    <topicref href="t3.dita" navtitle="T3"/>
  </topichead>
</map>
"""

MAPREF_MAP = """\
<map>
  <title>Master Map</title>
  <topicref href="intro.dita" navtitle="Intro"/>
  <mapref href="submap.ditamap" navtitle="Sub Map"/>
</map>
"""


class TestSimpleDitamap:
    def test_node_count(self):
        result = parse_map_to_graph(SIMPLE_DITAMAP)
        # 1 map root + 3 topicrefs = 4 nodes
        assert result["stats"]["total_nodes"] == 4

    def test_edge_count(self):
        result = parse_map_to_graph(SIMPLE_DITAMAP)
        # 3 contains edges (root -> each topicref)
        assert len(result["edges"]) == 3

    def test_title(self):
        result = parse_map_to_graph(SIMPLE_DITAMAP)
        assert result["title"] == "User Guide"


class TestNestedTopicrefs:
    def test_correct_depth(self):
        result = parse_map_to_graph(NESTED_DITAMAP)
        assert result["stats"]["max_depth"] == 5

    def test_deep_nesting_suggestion(self):
        result = parse_map_to_graph(NESTED_DITAMAP)
        assert any("nesting" in s for s in result["ai_suggestions"])


class TestBookmap:
    def test_chapter_nodes_typed_correctly(self):
        result = parse_map_to_graph(BOOKMAP_XML)
        chapter_nodes = [n for n in result["nodes"] if n["type"] == "chapter"]
        assert len(chapter_nodes) == 2

    def test_appendix_node(self):
        result = parse_map_to_graph(BOOKMAP_XML)
        appendix_nodes = [n for n in result["nodes"] if n["type"] == "appendix"]
        assert len(appendix_nodes) == 1


class TestMissingNavtitle:
    def test_uses_href_filename(self):
        result = parse_map_to_graph(NO_NAVTITLE_MAP)
        labels = [n["label"] for n in result["nodes"]]
        assert "some_topic" in labels
        assert "my_file" in labels

    def test_missing_navtitle_suggestion(self):
        result = parse_map_to_graph(NO_NAVTITLE_MAP)
        assert any("navtitle" in s for s in result["ai_suggestions"])


class TestReltable:
    def test_related_edges(self):
        result = parse_map_to_graph(RELTABLE_MAP)
        related = [e for e in result["edges"] if e["type"] == "related"]
        assert len(related) == 2

    def test_no_reltable_suggestion_when_present(self):
        result = parse_map_to_graph(RELTABLE_MAP)
        assert not any("reltable" in s.lower() for s in result["ai_suggestions"])


class TestEmptyMap:
    def test_minimal_graph(self):
        result = parse_map_to_graph(EMPTY_MAP)
        # Just the root map node
        assert result["stats"]["total_nodes"] == 1
        assert result["stats"]["topic_count"] == 0
        assert len(result["edges"]) == 0


class TestMalformedXML:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="Malformed XML"):
            parse_map_to_graph("<map><broken")


class TestStatsCalculation:
    def test_stats_correct(self):
        result = parse_map_to_graph(SIMPLE_DITAMAP)
        stats = result["stats"]
        assert stats["total_nodes"] == 4
        assert stats["max_depth"] == 1
        assert stats["topic_count"] == 3
        assert stats["map_count"] == 1
        assert stats["topicgroup_count"] == 0


class TestTopicgroup:
    def test_topicgroup_handling(self):
        result = parse_map_to_graph(TOPICGROUP_MAP)
        types = {n["type"] for n in result["nodes"]}
        assert "topicgroup" in types
        assert "topichead" in types
        assert result["stats"]["topicgroup_count"] == 1


class TestMapref:
    def test_mapref_detected_as_map_type(self):
        result = parse_map_to_graph(MAPREF_MAP)
        map_nodes = [n for n in result["nodes"] if n["type"] == "map"]
        # Root map + mapref = 2
        assert len(map_nodes) == 2


class TestLargeMap:
    def test_performance_ok(self):
        # Build a map with 25 topics
        refs = "\n".join(
            f'  <topicref href="topic_{i}.dita" navtitle="Topic {i}"/>'
            for i in range(25)
        )
        xml = f"<map><title>Large Map</title>\n{refs}\n</map>"
        start = time.time()
        result = parse_map_to_graph(xml)
        elapsed = time.time() - start
        assert result["stats"]["total_nodes"] == 26  # 1 root + 25 topics
        assert elapsed < 1.0  # Should be near-instant


class TestMermaidOutput:
    def test_mermaid_generation(self):
        graph = parse_map_to_graph(SIMPLE_DITAMAP)
        mermaid = graph_to_mermaid(graph)
        assert mermaid.startswith("graph TD")
        assert "-->" in mermaid


class TestManySiblingsSuggestion:
    def test_grouping_suggestion(self):
        refs = "\n".join(
            f'  <topicref href="t{i}.dita" navtitle="T{i}"/>'
            for i in range(12)
        )
        xml = f"<map><title>Wide Map</title>\n{refs}\n</map>"
        result = parse_map_to_graph(xml)
        assert any("grouping" in s.lower() for s in result["ai_suggestions"])
