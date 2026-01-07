"""
User Context Model
==================
Immutable, typed user context extracted from verified Firebase ID tokens.

SECURITY PRINCIPLES:
- UserContext is read-only after creation (frozen=True)
- Only contains claims we explicitly trust from Firebase
- No sensitive data (tokens, passwords) stored in context
- Designed for safe logging and request propagation

This model represents the authenticated user throughout the request lifecycle.
It is attached to request.state.user by the authentication middleware.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """
    Authenticated user context from a verified Firebase ID token.
    
    This is an immutable snapshot of the user's identity at request time.
    All fields are extracted from the verified Firebase token claims.
    
    SECURITY: This object is only created after successful token verification.
    The presence of a UserContext implies the user is authenticated.
    
    Attributes:
        uid: Firebase user ID (unique, stable identifier)
        email: User's email address (may be None for phone auth)
        email_verified: Whether the email has been verified by Firebase
        auth_time: When the user last authenticated (token issued)
        
    Usage:
        # In route handlers via dependency injection
        @router.get("/profile")
        async def get_profile(user: CurrentUserDep):
            return {"uid": user.uid, "email": user.email}
    """

    model_config = {
        # Immutable after creation - security best practice
        "frozen": True,
        # Explicit field assignment only
        "extra": "forbid",
        # JSON serialization config
        "json_schema_extra": {
            "examples": [
                {
                    "uid": "abc123xyz",
                    "email": "user@example.com",
                    "email_verified": True,
                    "auth_time": "2026-01-06T12:00:00Z",
                }
            ]
        },
    }

    uid: str = Field(
        description="Firebase user ID - unique, stable identifier",
        min_length=1,
        max_length=128,
    )
    email: Optional[str] = Field(
        default=None,
        description="User email address (None for phone-only auth)",
    )
    email_verified: bool = Field(
        default=False,
        description="Whether Firebase has verified the user's email",
    )
    auth_time: Optional[datetime] = Field(
        default=None,
        description="Timestamp when user authenticated (token auth_time claim)",
    )

    @property
    def is_authenticated(self) -> bool:
        """
        Check if user is authenticated.
        
        A UserContext only exists for authenticated users, so this is always True.
        This property exists for API consistency with optional auth scenarios.
        """
        return True

    @property
    def display_id(self) -> str:
        """
        Get a display-safe identifier for logging.
        
        Returns email if available, otherwise the uid.
        Use this for user-facing displays and logs.
        """
        return self.email or self.uid

    def __str__(self) -> str:
        """String representation safe for logging."""
        return f"User(uid={self.uid}, email={self.email}, verified={self.email_verified})"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"UserContext(uid='{self.uid}', email='{self.email}', "
            f"email_verified={self.email_verified}, auth_time={self.auth_time})"
        )
