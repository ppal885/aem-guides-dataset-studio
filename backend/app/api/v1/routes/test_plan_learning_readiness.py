"""Read-only shared-learning configuration view; no persistence dependencies."""
from fastapi import APIRouter, Depends, Query, Response

from app.core.auth import CurrentUser, UserIdentity
from app.core.shared_uac_learning_http import SanitizedLearningRoute, require_shared_learning_transport_identity
from app.services.shared_uac_learning_readiness import get_shared_uac_learning_readiness

router = APIRouter(
    prefix="/test-plan-learning", tags=["test-plan-learning"],
    route_class=SanitizedLearningRoute,
    dependencies=[Depends(require_shared_learning_transport_identity)],
)


@router.get("/readiness")
def feedback_readiness(response: Response,
                       tenant_id: str = Query(..., min_length=1, max_length=120),
                       user: UserIdentity = CurrentUser):
    response.headers["Cache-Control"] = "no-store"
    return get_shared_uac_learning_readiness(user=user, tenant_id=tenant_id)
