"""
Authentication Dependencies
============================
FastAPI dependency injection providers for authenticated routes.

USAGE PATTERNS:

1. Require authentication (401 if not authenticated):
   @router.get("/profile")
   async def get_profile(user: CurrentUserDep):
       return {"uid": user.uid}

2. Optional authentication (None if not authenticated):
   @router.get("/public")
   async def public_endpoint(user: OptionalUserDep):
       if user:
           return {"message": f"Hello, {user.email}"}
       return {"message": "Hello, anonymous"}

3. Require verified email:
   @router.get("/settings")
   async def get_settings(user: Annotated[UserContext, Depends(require_verified_email)]):
       return {"settings": {...}}

4. Protect entire router:
   router = APIRouter(dependencies=[Depends(get_current_user)])

SECURITY NOTES:
- CurrentUserDep enforces authentication at the dependency level
- This provides defense-in-depth beyond middleware path matching
- Using dependencies allows fine-grained control per route
"""

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status

from app.auth.context import UserContext
from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_current_user(request: Request) -> UserContext:
    """
    Dependency that requires an authenticated user.
    
    Use this dependency on routes that must have authentication.
    If the user is not authenticated, raises 401 Unauthorized.
    
    The user context is set by FirebaseAuthMiddleware after
    successful token verification.
    
    Returns:
        UserContext: The authenticated user's context
    
    Raises:
        HTTPException: 401 if user is not authenticated
    
    Usage:
        @router.get("/me")
        async def get_me(user: CurrentUserDep):
            return {"uid": user.uid, "email": user.email}
    """
    user: Optional[UserContext] = getattr(request.state, "user", None)

    if user is None:
        logger.debug(
            "Authentication required but no user in request state",
            path=request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Bearer realm="api"'},
        )

    return user


async def get_optional_user(request: Request) -> Optional[UserContext]:
    """
    Dependency that optionally extracts the authenticated user.
    
    Use this for routes that work with or without authentication,
    but may provide enhanced functionality for authenticated users.
    
    Returns:
        UserContext if authenticated, None otherwise
    
    Usage:
        @router.get("/feed")
        async def get_feed(user: OptionalUserDep):
            if user:
                return get_personalized_feed(user.uid)
            return get_public_feed()
    """
    return getattr(request.state, "user", None)


async def require_verified_email(
    user: Annotated[UserContext, Depends(get_current_user)],
) -> UserContext:
    """
    Dependency that requires an authenticated user with verified email.
    
    Use this for sensitive operations that require email verification.
    Raises 403 if the user's email is not verified.
    
    Returns:
        UserContext: The authenticated user with verified email
    
    Raises:
        HTTPException: 401 if not authenticated, 403 if email not verified
    
    Usage:
        @router.post("/payment")
        async def process_payment(
            user: Annotated[UserContext, Depends(require_verified_email)]
        ):
            ...
    """
    if not user.email_verified:
        logger.warning(
            "Access denied: email not verified",
            uid=user.uid,
            email=user.email,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )

    return user


# Type aliases for cleaner dependency injection syntax
CurrentUserDep = Annotated[UserContext, Depends(get_current_user)]
OptionalUserDep = Annotated[Optional[UserContext], Depends(get_optional_user)]
