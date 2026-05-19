"""Enterprise Tool Calling + RAG QA Copilot endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.agents.qa_agent import QACopilotAgent
from app.core.auth import CurrentUser, UserIdentity
from app.models.response_models import QaCopilotChatRequest, QaCopilotChatResponse

router = APIRouter(prefix="/chat", tags=["QA Copilot"], dependencies=[CurrentUser])


@router.post("", response_model=QaCopilotChatResponse)
@router.post("/", response_model=QaCopilotChatResponse, include_in_schema=False)
async def post_qa_copilot_chat(
    body: QaCopilotChatRequest,
    user: UserIdentity = CurrentUser,
) -> QaCopilotChatResponse:
    """Run the enterprise QA copilot planner/executor/grounding flow."""

    del user
    agent = QACopilotAgent()
    return await agent.run(
        body.message.strip(),
        limit=body.limit,
        include_debug=body.include_debug,
    )
