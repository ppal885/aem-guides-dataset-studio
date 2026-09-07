"""Keep submitted corrections and credentials out of HTTP validation responses."""
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.core.auth import CurrentUser, UserIdentity


def require_shared_learning_transport_identity(user: UserIdentity = CurrentUser) -> UserIdentity:
    """Development bypass is never a shared-memory transport credential."""
    if user.auth_method != "token":
        raise HTTPException(403, "Shared feedback transport requires an authenticated personal or service token.")
    return user


class SanitizedLearningRoute(APIRoute):
    def should_sanitize(self, body):
        return True

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError:
                try:
                    body = await request.json()
                except (ValueError, UnicodeError):
                    body = None
                if self.should_sanitize(body):
                    return JSONResponse(status_code=422, content={
                        "detail": "Invalid shared feedback request; check the endpoint schema. Submitted values are omitted."})
                raise
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                try:
                    body = await request.json()
                except (ValueError, UnicodeError):
                    body = None
                if self.should_sanitize(body):
                    return JSONResponse(status_code=403, headers=exc.headers, content={
                        "detail": "Shared feedback access denied; check personal identity, tenant access and current Jira QE Assignee."})
                raise
        return handler


class SharedCaptureValidationRoute(SanitizedLearningRoute):
    """Preserve legacy test-plan errors unless the body selects shared capture."""
    def should_sanitize(self, body):
        return isinstance(body, dict) and (
            body.get("contract_version") == "shared-uac-feedback-v1"
            or any(key in body for key in ("raw_feedback", "proposed_correction", "ai_classification", "draft")))
