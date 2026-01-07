# Authentication package
# Firebase identity verification and user context management.

from app.auth.context import UserContext
from app.auth.dependencies import (
    get_current_user,
    get_optional_user,
    require_verified_email,
    CurrentUserDep,
    OptionalUserDep,
)
from app.auth.firebase import initialize_firebase, verify_firebase_token

__all__ = [
    "UserContext",
    "initialize_firebase",
    "verify_firebase_token",
    "get_current_user",
    "get_optional_user",
    "require_verified_email",
    "CurrentUserDep",
    "OptionalUserDep",
]
