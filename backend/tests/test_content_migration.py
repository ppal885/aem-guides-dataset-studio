"""Tests for Content Migration Copilot: content_parser_service and content_migration_service."""

import xml.etree.ElementTree as ET

import pytest

from app.services.content_parser_service import (
    ContentBlock,
    detect_format,
    parse_content,
    parse_html,
    parse_markdown,
    parse_plain_text,
)
from app.services.content_migration_service import (
    generate_dita_topics,
    generate_ditamap,
    migrate_content,
    parse_and_classify,
)


# ============================================================================
# Fixtures
# ============================================================================

MARKDOWN_MIXED = """\
# Installation Guide

This guide explains how to install the product.

## Prerequisites

A DITA-aware editor is required for authoring.

## Steps to Install

1. Open the installer package.
2. Click Next to continue.
3. Select the installation directory.
4. Enter your license key.
5. Click Install.

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| timeout   | 30      | Connection timeout in seconds |
| retries   | 3       | Number of retry attempts |
| log_level | INFO    | Logging verbosity |

## Glossary

API is a set of protocols for building software applications.
"""

HTML_INPUT = """\
<html>
<body>
<h1>User Guide</h1>
<p>This document describes the system.</p>
<h2>Getting Started</h2>
<ol>
<li>Open the application.</li>
<li>Click the login button.</li>
<li>Enter your credentials.</li>
</ol>
<h2>Settings</h2>
<table>
<tr><th>Setting</th><th>Value</th><th>Description</th></tr>
<tr><td>Theme</td><td>Dark</td><td>UI theme</td></tr>
<tr><td>Language</td><td>English</td><td>Display language</td></tr>
<tr><td>Timezone</td><td>UTC</td><td>Default timezone</td></tr>
</table>
</body>
</html>
"""

PLAIN_TEXT_STEPS = """\
INSTALLATION PROCEDURE

Before you begin, ensure you have admin rights.

1. Download the package from the website.
2. Run the installer executable.
3. Select the target directory.
4. Click Install to begin.
5. Verify the installation succeeded.
"""

DEFINITION_TEXT = """\
# Cloud Computing

Cloud computing is a model for enabling ubiquitous, convenient,
on-demand network access to a shared pool of configurable computing
resources that can be rapidly provisioned and released with minimal
management effort.
"""

GLOSSARY_MD = """\
# API

API is a set of functions and procedures that allow applications to access features of an operating system.
"""


# ============================================================================
# Parser tests
# ============================================================================

class TestContentParser:
    """Tests for content_parser_service."""

    def test_parse_markdown_headings(self):
        blocks = parse_markdown("# Title\n\n## Subtitle\n\nSome text.")
        headings = [b for b in blocks if b.block_type == "heading"]
        assert len(headings) == 2
        assert headings[0].content == "Title"
        assert headings[0].level == 1
        assert headings[1].content == "Subtitle"
        assert headings[1].level == 2

    def test_parse_markdown_ordered_list(self):
        md = "1. First step\n2. Second step\n3. Third step\n"
        blocks = parse_markdown(md)
        ol_blocks = [b for b in blocks if b.block_type == "ordered_list"]
        assert len(ol_blocks) == 1
        assert len(ol_blocks[0].children) == 3

    def test_parse_markdown_unordered_list(self):
        md = "- Item A\n- Item B\n- Item C\n"
        blocks = parse_markdown(md)
        ul_blocks = [b for b in blocks if b.block_type == "unordered_list"]
        assert len(ul_blocks) == 1
        assert len(ul_blocks[0].children) == 3

    def test_parse_markdown_code_block(self):
        md = "```python\nprint('hello')\n```\n"
        blocks = parse_markdown(md)
        code = [b for b in blocks if b.block_type == "code_block"]
        assert len(code) == 1
        assert "print" in code[0].content
        assert code[0].metadata.get("language") == "python"

    def test_parse_markdown_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
        blocks = parse_markdown(md)
        tables = [b for b in blocks if b.block_type == "table"]
        assert len(tables) == 1
        rows = tables[0].metadata["rows"]
        assert len(rows) >= 2  # header + data rows (separator skipped)

    def test_parse_markdown_image(self):
        md = "![Logo](logo.png)\n"
        blocks = parse_markdown(md)
        images = [b for b in blocks if b.block_type == "image"]
        assert len(images) == 1
        assert images[0].metadata["src"] == "logo.png"

    def test_parse_html_basic(self):
        blocks = parse_html(HTML_INPUT)
        assert len(blocks) > 0
        headings = [b for b in blocks if b.block_type == "heading"]
        assert any(b.content == "User Guide" for b in headings)

    def test_parse_html_ordered_list(self):
        blocks = parse_html(HTML_INPUT)
        ol_blocks = [b for b in blocks if b.block_type == "ordered_list"]
        assert len(ol_blocks) >= 1

    def test_parse_html_table(self):
        blocks = parse_html(HTML_INPUT)
        tables = [b for b in blocks if b.block_type == "table"]
        assert len(tables) >= 1

    def test_parse_plain_text_numbered(self):
        text = "1. First\n2. Second\n3. Third\n"
        blocks = parse_plain_text(text)
        ol_blocks = [b for b in blocks if b.block_type == "ordered_list"]
        assert len(ol_blocks) == 1
        assert len(ol_blocks[0].children) == 3

    def test_parse_plain_text_bullets(self):
        text = "- Alpha\n- Beta\n- Gamma\n"
        blocks = parse_plain_text(text)
        ul_blocks = [b for b in blocks if b.block_type == "unordered_list"]
        assert len(ul_blocks) == 1

    def test_parse_plain_text_heading_detection(self):
        blocks = parse_plain_text("OVERVIEW\n\nSome text here.")
        headings = [b for b in blocks if b.block_type == "heading"]
        assert len(headings) >= 1

    def test_detect_format_markdown(self):
        assert detect_format("# Hello\n\n- item\n- item") == "markdown"

    def test_detect_format_html(self):
        assert detect_format("<html><body><p>Hello</p></body></html>") == "html"

    def test_detect_format_plain_text(self):
        assert detect_format("Just some regular text with no special formatting.") == "plain_text"

    def test_parse_content_auto_detect(self):
        blocks = parse_content("# Heading\n\nA paragraph.")
        assert len(blocks) > 0


# ============================================================================
# Classification tests
# ============================================================================

class TestClassification:
    """Tests for parse_and_classify heuristics."""

    def test_ordered_list_classified_as_task(self):
        md = "# Deploy App\n\n1. Open terminal.\n2. Run deploy command.\n3. Verify status.\n"
        result = parse_and_classify(md)
        sections = result["sections"]
        assert any(s["topic_type"] == "task" for s in sections)

    def test_table_classified_as_reference(self):
        md = (
            "# Parameters\n\n"
            "| Name | Type | Default |\n"
            "|------|------|---------|\n"
            "| host | str  | localhost |\n"
            "| port | int  | 8080 |\n"
            "| debug| bool | false |\n"
        )
        result = parse_and_classify(md)
        sections = result["sections"]
        assert any(s["topic_type"] == "reference" for s in sections)

    def test_definition_classified_as_concept(self):
        result = parse_and_classify(DEFINITION_TEXT)
        sections = result["sections"]
        assert any(s["topic_type"] == "concept" for s in sections)

    def test_mixed_content_multiple_topics(self):
        result = parse_and_classify(MARKDOWN_MIXED)
        sections = result["sections"]
        assert len(sections) >= 3  # Multiple sections from mixed content

    def test_empty_input_handling(self):
        result = parse_and_classify("")
        assert result["sections"] == []
        assert len(result["migration_notes"]) > 0

    def test_source_format_detection(self):
        result = parse_and_classify(MARKDOWN_MIXED)
        assert result["source_format"] == "markdown"

    def test_html_source_format(self):
        result = parse_and_classify(HTML_INPUT, source_format="html")
        assert result["source_format"] == "html"


# ============================================================================
# DITA generation tests
# ============================================================================

class TestDitaGeneration:
    """Tests for DITA XML generation."""

    def _get_topics(self, content):
        result = parse_and_classify(content)
        return generate_dita_topics(result["sections"])

    def test_generated_xml_is_wellformed(self):
        topics = self._get_topics(MARKDOWN_MIXED)
        for topic in topics:
            xml = topic["xml"]
            # Strip the DOCTYPE line to parse with ET
            xml_body = "\n".join(
                line for line in xml.split("\n")
                if not line.startswith("<!DOCTYPE") and not line.startswith("<?xml")
            )
            ET.fromstring(xml_body)  # Should not raise

    def test_task_has_steps(self):
        md = "# Install\n\n1. Click Install.\n2. Select directory.\n3. Confirm.\n"
        topics = self._get_topics(md)
        task_topics = [t for t in topics if t["topic_type"] == "task"]
        assert len(task_topics) >= 1
        xml = task_topics[0]["xml"]
        assert "<steps>" in xml
        assert "<cmd>" in xml

    def test_concept_has_conbody(self):
        topics = self._get_topics(DEFINITION_TEXT)
        concept_topics = [t for t in topics if t["topic_type"] == "concept"]
        assert len(concept_topics) >= 1
        xml = concept_topics[0]["xml"]
        assert "<conbody>" in xml

    def test_reference_has_simpletable(self):
        md = (
            "# Settings\n\n"
            "| Key | Value | Note |\n"
            "|-----|-------|------|\n"
            "| a   | 1     | x    |\n"
            "| b   | 2     | y    |\n"
            "| c   | 3     | z    |\n"
        )
        topics = self._get_topics(md)
        ref_topics = [t for t in topics if t["topic_type"] == "reference"]
        assert len(ref_topics) >= 1
        assert "<simpletable>" in ref_topics[0]["xml"]

    def test_topic_ids_are_valid_xml_ids(self):
        topics = self._get_topics(MARKDOWN_MIXED)
        import re
        valid_id = re.compile(r"^[a-zA-Z_][\w.-]*$")
        for topic in topics:
            xml_body = "\n".join(
                line for line in topic["xml"].split("\n")
                if not line.startswith("<!DOCTYPE") and not line.startswith("<?xml")
            )
            root = ET.fromstring(xml_body)
            topic_id = root.get("id")
            assert topic_id is not None
            assert valid_id.match(topic_id), "Invalid XML ID: %s" % topic_id

    def test_proper_doctype_in_output(self):
        topics = self._get_topics(MARKDOWN_MIXED)
        for topic in topics:
            assert "<!DOCTYPE" in topic["xml"]

    def test_xml_declaration_in_output(self):
        topics = self._get_topics(MARKDOWN_MIXED)
        for topic in topics:
            assert topic["xml"].startswith("<?xml version=")

    def test_filename_generation(self):
        topics = self._get_topics(MARKDOWN_MIXED)
        for topic in topics:
            assert topic["filename"].endswith(".dita")
            assert " " not in topic["filename"]


# ============================================================================
# Ditamap tests
# ============================================================================

class TestDitamap:
    """Tests for ditamap generation."""

    def test_ditamap_references_all_topics(self):
        result = migrate_content(MARKDOWN_MIXED)
        ditamap = result["ditamap"]
        topics = result["topics"]
        for topic in topics:
            assert topic["filename"] in ditamap

    def test_ditamap_is_wellformed_xml(self):
        result = migrate_content(MARKDOWN_MIXED)
        ditamap = result["ditamap"]
        xml_body = "\n".join(
            line for line in ditamap.split("\n")
            if not line.startswith("<!DOCTYPE") and not line.startswith("<?xml")
        )
        root = ET.fromstring(xml_body)
        assert root.tag == "map"

    def test_ditamap_has_doctype(self):
        result = migrate_content(MARKDOWN_MIXED)
        assert "<!DOCTYPE map" in result["ditamap"]


# ============================================================================
# Full migration tests
# ============================================================================

class TestMigrateContent:
    """Tests for the migrate_content main entry point."""

    def test_full_migration_markdown(self):
        result = migrate_content(MARKDOWN_MIXED)
        assert result["summary"]["total_topics"] >= 3
        assert result["summary"]["source_format"] == "markdown"
        assert result["ditamap"] != ""
        assert len(result["topics"]) > 0

    def test_full_migration_html(self):
        result = migrate_content(HTML_INPUT, source_format="html")
        assert result["summary"]["total_topics"] >= 1
        assert result["summary"]["source_format"] == "html"

    def test_full_migration_plain_text(self):
        result = migrate_content(PLAIN_TEXT_STEPS, source_format="plain_text")
        assert result["summary"]["total_topics"] >= 1
        topics = result["topics"]
        # Should detect the numbered steps as a task
        assert any(t["topic_type"] == "task" for t in topics)

    def test_empty_input(self):
        result = migrate_content("")
        assert result["summary"]["total_topics"] == 0
        assert result["topics"] == []
        assert len(result["migration_notes"]) > 0

    def test_whitespace_only_input(self):
        result = migrate_content("   \n\n  \t  ")
        assert result["summary"]["total_topics"] == 0

    def test_very_long_content(self):
        # Generate content with many sections
        sections = []
        for i in range(50):
            sections.append("## Section %d\n\nParagraph content for section %d.\n" % (i, i))
        long_content = "# Big Document\n\n" + "\n".join(sections)
        result = migrate_content(long_content)
        assert result["summary"]["total_topics"] >= 50

    def test_no_heading_content(self):
        result = migrate_content("Just a simple paragraph with no headings at all.")
        assert result["summary"]["total_topics"] >= 1
        assert any("No headings" in n for n in result["migration_notes"])

    def test_by_type_counts(self):
        result = migrate_content(MARKDOWN_MIXED)
        by_type = result["summary"]["by_type"]
        assert "task" in by_type
        assert "concept" in by_type
        assert "reference" in by_type
        total = sum(by_type.values())
        assert total == result["summary"]["total_topics"]

    def test_auto_format_detection(self):
        result = migrate_content(MARKDOWN_MIXED, source_format="auto")
        assert result["summary"]["source_format"] == "markdown"

    def test_migration_notes_for_ambiguous_content(self):
        md = (
            "# Mixed Section\n\n"
            "Some introductory text.\n\n"
            "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n| 7 | 8 | 9 |\n\n"
            "1. Do this step.\n"
            "2. Click here.\n"
        )
        result = migrate_content(md)
        # Should produce migration notes about mixed content
        assert len(result["migration_notes"]) >= 1 or len(result["topics"]) >= 1

    def test_sections_detected_count(self):
        result = migrate_content(MARKDOWN_MIXED)
        assert result["summary"]["sections_detected"] >= 3

    def test_unique_filenames(self):
        md = "# Same Title\n\nContent A.\n\n# Same Title\n\nContent B.\n"
        result = migrate_content(md)
        filenames = [t["filename"] for t in result["topics"]]
        assert len(filenames) == len(set(filenames)), "Duplicate filenames found"

    def test_glossentry_detection(self):
        result = migrate_content(GLOSSARY_MD)
        topics = result["topics"]
        # Short definition should be detected
        assert len(topics) >= 1
