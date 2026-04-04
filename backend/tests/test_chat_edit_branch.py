from datetime import datetime, timedelta
from uuid import uuid4

from app.db.chat_models import ChatMessage, ChatSession
from app.db.session import SessionLocal
from app.services.chat_service import branch_session_from_message, delete_session


def _create_message(session_id: str, role: str, content: str, created_at: datetime, message_id: str | None = None):
    return ChatMessage(
        id=message_id or str(uuid4()),
        session_id=session_id,
        role=role,
        content=content,
        created_at=created_at,
    )


def test_branch_session_from_middle_user_message_copies_only_prior_history():
    source_session_id = str(uuid4())
    edit_message_id = str(uuid4())
    branched_session_id = None
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        db.add(ChatSession(id=source_session_id, title="Original chat", created_at=now, updated_at=now))
        db.flush()
        db.add_all(
            [
                _create_message(source_session_id, "user", "First prompt", now),
                _create_message(source_session_id, "assistant", "First answer", now + timedelta(seconds=1)),
                _create_message(
                    source_session_id,
                    "user",
                    "Second prompt that will be edited",
                    now + timedelta(seconds=2),
                    message_id=edit_message_id,
                ),
                _create_message(source_session_id, "assistant", "Second answer", now + timedelta(seconds=3)),
            ]
        )
        db.commit()
    finally:
        db.close()

    try:
        session, messages = branch_session_from_message(source_session_id, edit_message_id)
        branched_session_id = session["id"]

        assert branched_session_id != source_session_id
        assert session["title"] == "New Chat"
        assert [message["content"] for message in messages] == ["First prompt", "First answer"]
    finally:
        delete_session(source_session_id)
        if branched_session_id:
            delete_session(branched_session_id)


def test_branch_session_from_first_user_message_resets_title_and_history():
    source_session_id = str(uuid4())
    first_message_id = str(uuid4())
    branched_session_id = None
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        db.add(ChatSession(id=source_session_id, title="Old title", created_at=now, updated_at=now))
        db.flush()
        db.add(_create_message(source_session_id, "user", "Original first prompt", now, message_id=first_message_id))
        db.add(_create_message(source_session_id, "assistant", "Original answer", now + timedelta(seconds=1)))
        db.commit()
    finally:
        db.close()

    try:
        session, messages = branch_session_from_message(source_session_id, first_message_id)
        branched_session_id = session["id"]

        assert session["title"] == "New Chat"
        assert messages == []
    finally:
        delete_session(source_session_id)
        if branched_session_id:
            delete_session(branched_session_id)
