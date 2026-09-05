"""Authenticated shared UAC capture, Human review and publication endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import AdminUser, CurrentUser, UserIdentity
from app.core.shared_uac_learning_http import SanitizedLearningRoute, require_shared_learning_transport_identity
from app.core.schemas_shared_uac_learning import UacDraftRegistration, UacFeedbackBind, UacFeedbackCapture, UacLessonReview
from app.db.session import get_db
from app.services import shared_uac_learning_service as learning
from app.services.tenant_service import ensure_user_can_access_tenant

router = APIRouter(prefix="/test-plan-learning", tags=["test-plan-learning"], route_class=SanitizedLearningRoute,
                   dependencies=[Depends(require_shared_learning_transport_identity)])


def _write(session, operation, **kwargs):
    try:
        result = operation(session, **kwargs)
        session.commit()
        return result
    except learning.LearningConflict as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        session.rollback()
        raise


@router.post("/drafts")
def register_draft(body: UacDraftRegistration, user: UserIdentity = CurrentUser, session: Session = Depends(get_db)):
    return _write(session, learning.register_draft, user=user, body=body)


@router.post("/feedback")
def capture_feedback(body: UacFeedbackCapture, user: UserIdentity = CurrentUser, session: Session = Depends(get_db)):
    # Also used directly by the backward-compatible test-plans feedback branch.
    require_shared_learning_transport_identity(user)
    return _write(session, learning.capture_feedback, user=user, body=body)


@router.get("/feedback")
def list_feedback(tenant_id: str = "kone", jira_key: str = "", plan_fingerprint: str = "",
                  limit: int = Query(50, ge=1, le=200), user: UserIdentity = CurrentUser, session: Session = Depends(get_db)):
    try:
        return learning.list_learning(session, user=user, tenant_id=tenant_id, jira_key=jira_key,
                                      plan_fingerprint=plan_fingerprint, limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/feedback/{feedback_id}")
def feedback_status(feedback_id: str, tenant_id: str = "kone", user: UserIdentity = CurrentUser, session: Session = Depends(get_db)):
    return learning.get_feedback_status(session, user=user, tenant_id=tenant_id, feedback_id=feedback_id)


@router.post("/feedback/{feedback_id}/bind")
def bind_feedback(feedback_id: str, body: UacFeedbackBind, user: UserIdentity = CurrentUser, session: Session = Depends(get_db)):
    return _write(session, learning.bind_feedback, user=user, feedback_id=feedback_id, body=body)


@router.post("/feedback/{feedback_id}/review")
def review_feedback(feedback_id: str, body: UacLessonReview, user: UserIdentity = CurrentUser, session: Session = Depends(get_db)):
    return _write(session, learning.review_lesson, user=user, feedback_id=feedback_id, body=body)


@router.get("/publication")
def publication(tenant_id: str = "kone", cutoff_at: datetime | None = None,
                excluded_source_case_ids: list[str] = Query(default=[]),
                user: UserIdentity = CurrentUser, session: Session = Depends(get_db)):
    tenant = ensure_user_can_access_tenant(user, tenant_id)
    if len(excluded_source_case_ids) > 1000:
        raise HTTPException(400, "At most 1000 source exclusions are supported.")
    try:
        return learning.load_shared_learning_publication(tenant_id=tenant, cutoff_at=cutoff_at,
            excluded_source_case_ids=set(excluded_source_case_ids), session=session)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/index/drain")
def drain_index(tenant_id: str = "kone", limit: int = Query(20, ge=1, le=100),
                user: UserIdentity = AdminUser, session: Session = Depends(get_db)):
    tenant = ensure_user_can_access_tenant(user, tenant_id)
    return learning.drain_learning_outbox(tenant_id=tenant, limit=limit, session=session)


@router.post("/index/retry")
def retry_index(tenant_id: str = "kone", feedback_id: str = "", limit: int = Query(100, ge=1, le=100),
                user: UserIdentity = AdminUser, session: Session = Depends(get_db)):
    return _write(session, learning.retry_failed_index, user=user, tenant_id=tenant_id,
                  feedback_id=feedback_id, limit=limit)
