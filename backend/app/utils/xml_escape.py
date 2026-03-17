"""
XML escaping utilities for DITA content generation.

This module provides centralized XML escaping functions to ensure all generated
DITA XML (.dita, .ditamap) files are valid and safe, preventing FM post-processing
errors like "The entity name must immediately follow the '&' in the entity reference."

IMPORTANT GUIDELINES:
1. Regex approach is critical: Using regex with negative lookahead prevents
   double-escaping of existing valid entities (e.g., &amp; stays &amp;, not &amp;amp;).
   Naive replace("&", "&amp;") would break valid entities.

2. Doctype + DTD refs must remain exactly as they are:
   - Doctype declarations (e.g., '<!DOCTYPE topic PUBLIC "...">') are NEVER escaped
   - DTD references in doctype strings are inserted directly without escaping
   - Only text content and attribute values are escaped, NOT doctype strings
   - Doctype strings come from config.doctype_topic/config.doctype_map and are
     concatenated directly: f'<?xml...?>\n{config.doctype_map}\n'

Functions:
    xml_escape_text: Escape text content for XML text nodes
    xml_escape_attr: Escape text content for XML attributes
"""

import re
from typing import Optional


# Regex pattern to match invalid ampersands (not part of valid entities)
# Uses negative lookahead to avoid double-escaping existing valid entities
# Matches & that is NOT followed by:
# - amp; lt; gt; quot; apos; (named entities)
# - #\d+; (decimal numeric entities)
# - #x[0-9A-Fa-f]+; (hexadecimal numeric entities)
_INVALID_AMPERSAND_PATTERN = re.compile(
    r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)'
)


def xml_escape_text(text: Optional[str]) -> str:
    """
    Escape text content for XML text nodes.

    Escapes: & < >
    Preserves: &amp; &lt; &gt; &quot; &apos; and numeric entities

    CRITICAL: Uses regex with negative lookahead to prevent double-escaping.
    Naive replace("&", "&amp;") would turn &amp; into &amp;amp;.

    Note: ElementTree automatically escapes < and > when serializing,
    but we escape them here to ensure consistency and prevent any issues.
    Invalid & characters (not part of valid entities) are always escaped.

    Args:
        text: Text to escape, or None

    Returns:
        Escaped text string, or empty string if None

    Examples:
        >>> xml_escape_text("A & B")
        'A &amp; B'
        >>> xml_escape_text("A &amp; B")
        'A &amp; B'  # No double-escaping - regex preserves existing entities
        >>> xml_escape_text("Price < 100")
        'Price &lt; 100'
        >>> xml_escape_text("&#123;")
        '&#123;'  # Preserved
        >>> xml_escape_text(None)
        ''
    """
    if text is None:
        return ""

    if not isinstance(text, str):
        text = str(text)

    # CRITICAL: Use regex with negative lookahead to escape ONLY invalid ampersands
    # This prevents double-escaping of existing valid entities like &amp;, &lt;, etc.
    # Naive replace("&", "&amp;") would break: "A &amp; B" -> "A &amp;amp; B"
    text = _INVALID_AMPERSAND_PATTERN.sub('&amp;', text)

    # Escape < and > - even though ElementTree handles these, we escape them
    # to ensure consistency and prevent any edge cases
    # Check if already escaped to avoid double-escaping
    text = re.sub(r'(?<!&lt;)<(?![/!]?[A-Za-z])', '&lt;', text)
    text = re.sub(r'(?<!&gt;)>', '&gt;', text)

    return text


def xml_escape_attr(text: Optional[str]) -> str:
    """
    Escape text content for XML attributes.

    Escapes: & < > " '
    Preserves: &amp; &lt; &gt; &quot; &apos; and numeric entities

    CRITICAL: Uses regex with negative lookahead to prevent double-escaping.

    Args:
        text: Text to escape, or None

    Returns:
        Escaped text string, or empty string if None

    Examples:
        >>> xml_escape_attr('title="A & B"')
        'title=&quot;A &amp; B&quot;'
        >>> xml_escape_attr("Price < 100")
        'Price &lt; 100'
        >>> xml_escape_attr("It's done")
        'It&apos;s done'
        >>> xml_escape_attr("&#123;")
        '&#123;'  # Preserved
        >>> xml_escape_attr(None)
        ''
    """
    if text is None:
        return ""

    if not isinstance(text, str):
        text = str(text)

    # CRITICAL: Use regex with negative lookahead to escape ONLY invalid ampersands
    # This prevents double-escaping of existing valid entities
    text = _INVALID_AMPERSAND_PATTERN.sub('&amp;', text)

    # Escape < and >
    text = re.sub(r'<', '&lt;', text)
    text = re.sub(r'>', '&gt;', text)

    # Escape quotes
    text = re.sub(r'"', '&quot;', text)
    text = re.sub(r"'", '&apos;', text)

    return text


def xml_escape_href(href: Optional[str]) -> str:
    """
    Escape href attribute values.

    Hrefs typically don't contain quotes or apostrophes, but may contain &, <, >
    This is a convenience wrapper around xml_escape_attr for href attributes.

    Args:
        href: Href value to escape, or None

    Returns:
        Escaped href string, or empty string if None
    """
    return xml_escape_attr(href)
