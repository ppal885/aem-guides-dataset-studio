"""Tests for DITA element-definition query detection (skips noisy AEM RAG)."""

from app.services.chat_service import (
    _is_dita_element_definition_query,
    _is_dita_structure_feedback_query,
    _should_skip_aem_rag_for_dita_query,
)


def test_dita_faq_positive_uicontrol():
    assert _is_dita_element_definition_query("what is the use of <uicontrol> tag?") is True


def test_dita_faq_positive_short():
    assert _is_dita_element_definition_query("what is <uicontrol>?") is True


def test_dita_faq_positive_explain():
    assert _is_dita_element_definition_query("explain the <xref> element") is True


def test_dita_faq_positive_how_use():
    assert _is_dita_element_definition_query("how do I use <cmdname> in a step") is True


def test_dita_faq_negative_long_task():
    assert _is_dita_element_definition_query("write a task about printers and use uicontrol in step 3") is False


def test_structure_feedback_choicetables():
    assert _is_dita_structure_feedback_query("choicetables example is incorrect") is True
    assert _should_skip_aem_rag_for_dita_query("choicetables example is incorrect") is True


def test_structure_feedback_simpletable_wrong():
    assert _is_dita_structure_feedback_query("simpletable markup is wrong in my topic") is True


def test_structure_feedback_not_dita():
    assert _is_dita_structure_feedback_query("the printer driver is incorrect") is False
