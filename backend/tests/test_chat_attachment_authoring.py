import pytest
from app.api.v1.routes import chat as chat_routes

from app.core.schemas_chat_authoring import (
    ChatAction,
    ChatAttachmentRef,
    ChatAuthoringIntentDecision,
    ChatDitaAuthoringResult,
    ChatDitaGenerationOptions,
    ChatDitaValidationResult,
    TopicGenerationValidation,
)
from app.services import chat_service


class _FakeAuthoringService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def should_handle_request(self, **kwargs):
        self.calls.append({"phase": "classify", **kwargs})
        return ChatAuthoringIntentDecision(
            is_authoring_request=True,
            confidence=0.99,
            reason="Screenshot + prompt clearly request DITA authoring.",
            dita_type_hint="task",
        )

    async def generate_topic_from_request(self, *, payload, session_id: str, user_id: str, tenant_id: str):
        self.calls.append(
            {
                "phase": "generate",
                "session_id": session_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "payload": payload.model_dump(mode="json"),
            }
        )
        return ChatDitaAuthoringResult(
            status="valid",
            title="Generated workflow topic",
            dita_type="task",
            xml_preview=(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">\n'
                '<task id="generated-workflow-topic"><title>Generated workflow topic</title></task>'
            ),
            validation=TopicGenerationValidation.from_chat_dita_validation(
                ChatDitaValidationResult(valid=True, quality_score=91)
            ),
            saved_asset_path=None,
            artifact_url="/api/v1/chat/assets/generated-topic",
            actions=[
                ChatAction(
                    key="open_in_editor",
                    label="Open XML",
                    url="/api/v1/chat/assets/generated-topic",
                )
            ],
            message="The topic was generated and validated successfully.",
        )


def _attachments() -> list[ChatAttachmentRef]:
    return [
        ChatAttachmentRef(
            asset_id="image-1",
            kind="image",
            filename="screenshot.png",
            mime_type="image/png",
            size_bytes=1024,
            url="/api/v1/chat/assets/image-1",
        ),
        ChatAttachmentRef(
            asset_id="ref-1",
            kind="reference_dita",
            filename="reference.dita",
            mime_type="application/xml",
            size_bytes=512,
            url="/api/v1/chat/assets/ref-1",
            content_preview="<task id='reference-topic'/>",
        ),
    ]


@pytest.mark.anyio
async def test_authoring_route_resolves_before_message_id_route(client, auth_headers, monkeypatch):
    session_id = chat_service.create_session()

    async def fake_save_upload_asset(*, session_id: str, user_id: str, kind: str, upload):
        return ChatAttachmentRef(
            asset_id=f"{kind}-asset",
            kind=kind,  # type: ignore[arg-type]
            filename=upload.filename or f"{kind}.bin",
            mime_type=upload.content_type or "application/octet-stream",
            size_bytes=32,
            url=f"/api/v1/chat/assets/{kind}-asset",
        )

    async def fake_chat_turn(*args, **kwargs):
        yield {"type": "chunk", "content": "authoring ok"}
        yield {"type": "done"}

    monkeypatch.setattr(chat_routes, "save_upload_asset", fake_save_upload_asset)
    monkeypatch.setattr(chat_routes, "chat_turn", fake_chat_turn)

    try:
        response = client.post(
            f"/api/v1/chat/sessions/{session_id}/messages/authoring",
            headers=auth_headers,
            data={
                "content": "Generate a DITA topic from this screenshot.",
                "strict_validation": "true",
            },
            files={
                "image_attachment": ("screen.png", b"fake-image", "image/png"),
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "authoring ok" in response.text
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_with_attachments_persists_user_metadata_and_returns_authoring_result(monkeypatch):
    session_id = chat_service.create_session()
    fake_service = _FakeAuthoringService()
    monkeypatch.setattr(chat_service, "get_chat_dita_authoring_service", lambda: fake_service)

    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Generate a DITA task topic from this screenshot.",
            user_id="author-1",
            tenant_id="kone",
            attachments=_attachments(),
            generation_options=ChatDitaGenerationOptions(
                dita_type="task",
                save_path="/content/dam/demo/topics",
                file_name="generated-workflow-topic.dita",
                strict_validation=True,
            ),
        ):
            events.append(event)

        assert any(
            event["type"] == "tool" and event.get("name") == "generate_dita_from_attachments"
            for event in events
        )
        assert events[-1]["type"] == "done"

        messages = chat_service.get_messages(session_id)
        user_message = messages[0]
        assistant_message = messages[-1]

        assert user_message["tool_results"]["_attachments"][0]["filename"] == "screenshot.png"
        assert user_message["tool_results"]["_generation_options"]["file_name"] == "generated-workflow-topic.dita"
        assert assistant_message["tool_results"]["generate_dita_from_attachments"]["status"] == "valid"
        assert fake_service.calls[-1]["phase"] == "generate"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_persists_jira_context_and_merges_for_classification(monkeypatch):
    session_id = chat_service.create_session()
    fake_service = _FakeAuthoringService()
    monkeypatch.setattr(chat_service, "get_chat_dita_authoring_service", lambda: fake_service)

    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "Generate a DITA task topic from this screenshot.",
            user_id="author-1",
            tenant_id="kone",
            attachments=_attachments(),
            generation_options=ChatDitaGenerationOptions(dita_type="task", strict_validation=True),
            jira_context="PROJ-99: Must support dark mode toggle.",
        ):
            pass

        classify = fake_service.calls[0]
        assert classify["phase"] == "classify"
        assert "PROJ-99" in (classify.get("user_prompt") or "")
        assert "Jira" in (classify.get("user_prompt") or "")

        messages = chat_service.get_messages(session_id)
        assert messages[0]["tool_results"]["_jira_context"] == "PROJ-99: Must support dark mode toggle."

        gen = next(c for c in fake_service.calls if c["phase"] == "generate")
        assert gen["payload"]["jira_context"] == "PROJ-99: Must support dark mode toggle."
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_regenerate_last_assistant_reuses_persisted_attachment_context(monkeypatch):
    session_id = chat_service.create_session()
    fake_service = _FakeAuthoringService()
    monkeypatch.setattr(chat_service, "get_chat_dita_authoring_service", lambda: fake_service)

    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "Generate a DITA task topic from this screenshot.",
            user_id="author-1",
            tenant_id="kone",
            attachments=_attachments(),
            generation_options=ChatDitaGenerationOptions(dita_type="task", strict_validation=True),
            jira_context="KEY-1: AC line",
        ):
            pass

        async for _ in chat_service.regenerate_last_assistant(
            session_id,
            user_id="author-1",
            tenant_id="kone",
        ):
            pass

        generate_calls = [call for call in fake_service.calls if call["phase"] == "generate"]
        assert len(generate_calls) == 2
        assert generate_calls[1]["payload"]["attachments"][0]["asset_id"] == "image-1"
        assert generate_calls[1]["payload"]["generation_options"]["dita_type"] == "task"
        assert generate_calls[1]["payload"]["jira_context"] == "KEY-1: AC line"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_regenerate_last_assistant_request_generation_options_override(monkeypatch):
    session_id = chat_service.create_session()
    fake_service = _FakeAuthoringService()
    monkeypatch.setattr(chat_service, "get_chat_dita_authoring_service", lambda: fake_service)

    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "Generate a DITA task topic from this screenshot.",
            user_id="author-1",
            tenant_id="kone",
            attachments=_attachments(),
            generation_options=ChatDitaGenerationOptions(dita_type="task", strict_validation=True),
            jira_context="KEY-1: AC line",
        ):
            pass

        override = ChatDitaGenerationOptions(
            dita_type="concept",
            strict_validation=False,
            style_strictness="high",
            preserve_prolog=True,
            xref_placeholders=True,
        )
        async for _ in chat_service.regenerate_last_assistant(
            session_id,
            user_id="author-1",
            tenant_id="kone",
            generation_options=override,
        ):
            pass

        generate_calls = [call for call in fake_service.calls if call["phase"] == "generate"]
        assert len(generate_calls) == 2
        opts = generate_calls[1]["payload"]["generation_options"]
        assert opts["dita_type"] == "concept"
        assert opts["strict_validation"] is False
        assert opts["style_strictness"] == "high"
        assert opts["preserve_prolog"] is True
        assert opts["xref_placeholders"] is True
        assert generate_calls[1]["payload"]["jira_context"] == "KEY-1: AC line"
    finally:
        chat_service.delete_session(session_id)
