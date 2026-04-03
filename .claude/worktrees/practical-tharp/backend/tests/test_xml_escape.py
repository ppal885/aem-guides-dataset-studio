"""
Tests for XML escaping utilities.

Validates that xml_escape_text and xml_escape_attr correctly escape
invalid XML entities while preserving valid ones.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.xml_escape import xml_escape_text, xml_escape_attr, xml_escape_href


def test_xml_escape_text_basic():
    """Test basic text escaping."""
    assert xml_escape_text("A & B") == "A &amp; B"
    assert xml_escape_text("Price < 100") == "Price &lt; 100"
    assert xml_escape_text("Value > 50") == "Value &gt; 50"
    assert xml_escape_text("A & B < C > D") == "A &amp; B &lt; C &gt; D"


def test_xml_escape_text_preserves_valid_entities():
    """Test that valid entities are preserved."""
    assert xml_escape_text("&amp;") == "&amp;"
    assert xml_escape_text("&lt;") == "&lt;"
    assert xml_escape_text("&gt;") == "&gt;"
    assert xml_escape_text("&quot;") == "&quot;"
    assert xml_escape_text("&apos;") == "&apos;"
    assert xml_escape_text("&#123;") == "&#123;"
    assert xml_escape_text("&#x1F4A9;") == "&#x1F4A9;"
    assert xml_escape_text("A &amp; B &lt; C") == "A &amp; B &lt; C"


def test_xml_escape_text_invalid_ampersands():
    """Test that invalid ampersands are escaped."""
    assert xml_escape_text("A & B") == "A &amp; B"
    assert xml_escape_text("A &invalid; B") == "A &amp;invalid; B"
    assert xml_escape_text("A & B & C") == "A &amp; B &amp; C"
    assert xml_escape_text("Price: $100 & tax") == "Price: $100 &amp; tax"


def test_xml_escape_text_none():
    """Test None handling."""
    assert xml_escape_text(None) == ""
    assert xml_escape_text("") == ""


def test_xml_escape_attr_basic():
    """Test basic attribute escaping."""
    assert xml_escape_attr("A & B") == "A &amp; B"
    assert xml_escape_attr("Price < 100") == "Price &lt; 100"
    assert xml_escape_attr("Value > 50") == "Value &gt; 50"
    assert xml_escape_attr('Title "quoted"') == "Title &quot;quoted&quot;"
    assert xml_escape_attr("It's done") == "It&apos;s done"


def test_xml_escape_attr_preserves_valid_entities():
    """Test that valid entities are preserved in attributes."""
    assert xml_escape_attr("&amp;") == "&amp;"
    assert xml_escape_attr("&lt;") == "&lt;"
    assert xml_escape_attr("&gt;") == "&gt;"
    assert xml_escape_attr("&quot;") == "&quot;"
    assert xml_escape_attr("&apos;") == "&apos;"
    assert xml_escape_attr("&#123;") == "&#123;"
    assert xml_escape_attr("&#x1F4A9;") == "&#x1F4A9;"


def test_xml_escape_attr_quotes():
    """Test quote escaping in attributes."""
    assert xml_escape_attr('Title "quoted"') == "Title &quot;quoted&quot;"
    assert xml_escape_attr("It's done") == "It&apos;s done"
    assert xml_escape_attr('Mixed "quotes" and \'apostrophes\'') == "Mixed &quot;quotes&quot; and &apos;apostrophes&apos;"


def test_xml_escape_attr_none():
    """Test None handling for attributes."""
    assert xml_escape_attr(None) == ""
    assert xml_escape_attr("") == ""


def test_xml_escape_href():
    """Test href escaping."""
    assert xml_escape_href("topic.dita") == "topic.dita"
    assert xml_escape_href("topic & ref.dita") == "topic &amp; ref.dita"
    assert xml_escape_href(None) == ""


def test_real_world_examples():
    """Test real-world examples that might cause FM errors."""
    # Common patterns that cause "The entity name must immediately follow the '&'"
    assert xml_escape_text("Company A & Company B") == "Company A &amp; Company B"
    assert xml_escape_text("Price: $100 & tax") == "Price: $100 &amp; tax"
    assert xml_escape_text("Version 1.0 & 2.0") == "Version 1.0 &amp; 2.0"
    
    # Mixed content
    assert xml_escape_text("A & B < C > D") == "A &amp; B &lt; C &gt; D"
    
    # Already escaped (should not double-escape)
    assert xml_escape_text("A &amp; B") == "A &amp; B"
    assert xml_escape_text("Price &lt; 100") == "Price &lt; 100"


def test_numeric_entities():
    """Test that numeric entities are preserved."""
    assert xml_escape_text("&#123;") == "&#123;"
    assert xml_escape_text("&#x1F4A9;") == "&#x1F4A9;"
    assert xml_escape_text("&#65;") == "&#65;"
    assert xml_escape_text("&#x41;") == "&#x41;"
    
    # Invalid numeric entities should escape the &
    assert xml_escape_text("&#;") == "&amp;#;"
    assert xml_escape_text("&#x;") == "&amp;#x;"


def test_complex_mixed():
    """Test complex mixed content."""
    text = 'Title "A & B" < 100 > 50'
    escaped = xml_escape_text(text)
    assert "&amp;" in escaped
    assert "&lt;" in escaped
    assert "&gt;" in escaped
    
    attr = 'Title "A & B" < 100'
    escaped_attr = xml_escape_attr(attr)
    assert "&amp;" in escaped_attr
    assert "&lt;" in escaped_attr
    assert "&quot;" in escaped_attr


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
