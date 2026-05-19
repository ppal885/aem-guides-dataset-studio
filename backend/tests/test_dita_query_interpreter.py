"""Tests for natural-language DITA query tokenization (element name extraction)."""

from app.services.dita_query_interpreter import extract_element_names


def test_extract_element_names_skips_table_inside_table_of_contents_phrase():
    assert extract_element_names("Table of contents with topics for the product.") == []


def test_extract_element_names_keeps_explicit_table_element():
    names = extract_element_names("Does the <table> element allow nested paragraphs?", explicit_elements=["table"])
    assert "table" in names
