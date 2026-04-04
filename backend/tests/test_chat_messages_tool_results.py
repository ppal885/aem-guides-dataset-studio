"""Ensure persisted assistant tool_results are returned by chat session APIs (e.g. generate_dita download_url)."""
import json
from datetime import datetime
from uuid import uuid4

from app.db.session import SessionLocal
from app.db.chat_models import ChatSession, ChatMessage
from app.services.chat_service import create_session, delete_session, get_messages
from app.main import app
from fastapi.testclient import TestClient


def test_get_messages_returns_generate_dita_tool_results():
    session_id = create_session()
    msg_id = str(uuid4())
    download_url = "/api/v1/ai/bundle/TEXT-abc123/run-xyz789/download"
    tool_results = {
        "generate_dita": {
            "jira_id": "TEXT-abc123",
            "run_id": "run-xyz789",
            "download_url": download_url,
            "scenarios": [],
        }
    }
    db = SessionLocal()
    try:
        db.add(
            ChatMessage(
                id=msg_id,
                session_id=session_id,
                role="assistant",
                content="Bundle ready.",
                tool_calls=json.dumps([{"id": "tu1", "name": "generate_dita", "input": {}}]),
                tool_results=json.dumps(tool_results),
                created_at=datetime.utcnow(),
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        rows = get_messages(session_id)
        assert len(rows) >= 1
        assistant = next(m for m in rows if m["role"] == "assistant")
        assert assistant["tool_results"] is not None
        assert assistant["tool_results"]["generate_dita"]["download_url"] == download_url
    finally:
        delete_session(session_id)


def test_api_get_session_messages_includes_tool_results():
    session_id = create_session()
    msg_id = str(uuid4())
    download_url = "/api/v1/ai/bundle/TEXT-api/run-api/download"
    tool_results = {"generate_dita": {"download_url": download_url, "run_id": "r1", "jira_id": "J1"}}
    db = SessionLocal()
    try:
        db.add(
            ChatMessage(
                id=msg_id,
                session_id=session_id,
                role="assistant",
                content="Done.",
                tool_results=json.dumps(tool_results),
                created_at=datetime.utcnow(),
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        client = TestClient(app)
        r = client.get(f"/api/v1/chat/sessions/{session_id}/messages")
        assert r.status_code == 200
        data = r.json()
        msgs = data["messages"]
        assistant = next(m for m in msgs if m["role"] == "assistant")
        assert assistant["tool_results"]["generate_dita"]["download_url"] == download_url
    finally:
        delete_session(session_id)
