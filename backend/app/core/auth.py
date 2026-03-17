"""Authentication and authorization modules."""
from typing import Optional
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)


class UserIdentity(BaseModel):
    """User identity model."""
    id: str
    email: Optional[str] = None
    name: Optional[str] = None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> UserIdentity:
    """
    Get current user from token.
    
    For now, this is a stub implementation.
    In production, validate the token and extract user info.
    """
    # Stub: Return a default user for testing
    # In production, decode and validate the JWT token
    if credentials and credentials.credentials:
        token = credentials.credentials
        # For local testing, accept any token
        if token == "test-token":
            return UserIdentity(id="test-user-1", email="test@example.com", name="Test User")
        # In production, decode token here
        # decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        # return UserIdentity(id=decoded["sub"], email=decoded.get("email"))
    
    # Default user when no auth provided (for local development)
    return UserIdentity(id="test-user-1", email="test@example.com", name="Test User")


# Dependency alias for easier use
CurrentUser = Depends(get_current_user)
