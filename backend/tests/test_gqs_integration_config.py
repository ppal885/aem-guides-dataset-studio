"""GQS / QA Studio LLM configuration aligns with the app chat LLM by default."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.gqs_integration_config import (
    authoring_llm_execution_enabled,
    llm_configured_for_authoring,
)


@pytest.fixture
def clear_gqs_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GQS_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GQS_LLM_MODEL", raising=False)
    monkeypatch.delenv("GQS_AUTHORING_ENABLED", raising=False)


def test_llm_configured_when_app_llm_available_no_gqs(clear_gqs_llm_env, monkeypatch):
    monkeypatch.delenv("QA_STUDIO_USE_APP_LLM", raising=False)
    with patch("app.services.llm_service.is_llm_available", return_value=True):
        assert llm_configured_for_authoring()


def test_llm_not_configured_when_opted_out_of_app_llm(clear_gqs_llm_env, monkeypatch):
    monkeypatch.setenv("QA_STUDIO_USE_APP_LLM", "false")
    with patch("app.services.llm_service.is_llm_available", return_value=True):
        assert not llm_configured_for_authoring()


def test_execution_enabled_when_app_llm_available(clear_gqs_llm_env, monkeypatch):
    monkeypatch.delenv("QA_STUDIO_LLM_AUTHORING", raising=False)
    with patch("app.services.llm_service.is_llm_available", return_value=True):
        assert authoring_llm_execution_enabled()


def test_execution_disabled_when_qa_studio_authoring_false(clear_gqs_llm_env, monkeypatch):
    monkeypatch.setenv("QA_STUDIO_LLM_AUTHORING", "false")
    with patch("app.services.llm_service.is_llm_available", return_value=True):
        assert not authoring_llm_execution_enabled()


def test_gqs_credentials_suffice_without_app_llm(clear_gqs_llm_env, monkeypatch):
    monkeypatch.setenv("GQS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("GQS_LLM_MODEL", "gpt-4o-mini")
    with patch("app.services.llm_service.is_llm_available", return_value=False):
        assert llm_configured_for_authoring()
        assert authoring_llm_execution_enabled()
