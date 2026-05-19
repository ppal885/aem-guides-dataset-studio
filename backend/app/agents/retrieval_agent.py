"""Retrieval agent facade for QA copilot."""

from __future__ import annotations

from app.services.retrieval_service import QaCopilotRetrievalService


class RetrievalAgent:
    def __init__(self, service: QaCopilotRetrievalService | None = None) -> None:
        self.service = service or QaCopilotRetrievalService()

