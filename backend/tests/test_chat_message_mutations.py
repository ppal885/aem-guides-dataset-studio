"""Chat message edit (truncate after) and regenerate prep helpers."""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.db.session import SessionLocal
from app.db.chat_models import ChatSession, ChatMessage
from app.services.chat_service import (
    delete_all_chat_sessions,
    delete_session,
    get_last_user_message_content,
    get_messages,
    get_session,
    pop_last_assistant_if_any,
    update_user_message_truncate_after,
)


def _add_session_with_messages(rows: list[tuple[str, str, str]]) -> str:
    """rows: (role, content, optional msg_id) — id auto if third empty."""
    session_id = str(uuid4())
    db = SessionLocal()
    try:
        db.add(
            ChatSession(
                id=session_id,
                title="T",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        db.flush()
        base = datetime.utcnow()
        for i, item in enumerate(rows):
            role, content = item[0], item[1]
            mid = item[2] if len(item) > 2 and item[2] else str(uuid4())
            db.add(
                ChatMessage(
                    id=mid,
                    session_id=session_id,
                    role=role,
                    content=content,
                    created_at=base + timedelta(seconds=i),
                )
            )
        db.commit()
    finally:
        db.close()
    return session_id


def test_update_user_message_truncate_after_removes_following():
    u1, u2, a1, a2 = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
    sid = _add_session_with_messages(
        [
            ("user", "first", u1),
            ("assistant", "A1", a1),
            ("user", "second", u2),
            ("assistant", "A2", a2),
        ]
    )
    out = update_user_message_truncate_after(sid, u1, "first edited")
    roles = [m["role"] for m in out]
    assert roles == ["user"]
    assert out[0]["content"] == "first edited"
    assert out[0]["id"] == u1


def test_update_user_message_not_user_raises():
    sid = _add_session_with_messages([("assistant", "only", "")])
    msgs = get_messages(sid)
    aid = msgs[0]["id"]
    with pytest.raises(ValueError, match="Only user messages"):
        update_user_message_truncate_after(sid, aid, "x")


def test_pop_last_assistant_then_last_user_content():
    u1, a1 = str(uuid4()), str(uuid4())
    sid = _add_session_with_messages([("user", "hello", u1), ("assistant", "reply", a1)])
    pop_last_assistant_if_any(sid)
    assert get_last_user_message_content(sid) == "hello"
    msgs = get_messages(sid)
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"


def test_pop_last_assistant_noop_when_last_is_user():
    u1 = str(uuid4())
    sid = _add_session_with_messages([("user", "pending", u1)])
    pop_last_assistant_if_any(sid)
    assert get_last_user_message_content(sid) == "pending"


def test_get_last_user_message_content_after_assistant_removed():
    """Same state as failed stream: only user in DB — regenerate can use this content."""
    u1 = str(uuid4())
    sid = _add_session_with_messages([("user", "retry me", u1)])
    assert get_last_user_message_content(sid) == "retry me"


def test_delete_all_chat_sessions_removes_everything():
    s1 = _add_session_with_messages([("user", "a", "")])
    s2 = _add_session_with_messages([("user", "b", "")])
    assert get_session(s1) is not None
    assert get_session(s2) is not None
    n = delete_all_chat_sessions()
    assert n >= 2
    assert get_session(s1) is None
    assert get_session(s2) is None


def test_patch_user_message_http_smoke(client):
    """API smoke: PATCH truncates after edited user message and returns updated list."""
    u1, a1 = str(uuid4()), str(uuid4())
    sid = _add_session_with_messages(
        [
            ("user", "hello", u1),
            ("assistant", "reply", a1),
        ]
    )
    try:
        res = client.patch(
            f"/api/v1/chat/sessions/{sid}/messages/{u1}",
            json={"content": "hello edited"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "messages" in data
        assert len(data["messages"]) == 1
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "hello edited"
        assert data["messages"][0]["id"] == u1
    finally:
        delete_session(sid)
