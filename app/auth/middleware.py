"""
Authentication Middleware
=========================
Firebase ID token verification middleware with opt-in route protection.

ARCHITECTURE:
- This middleware runs on every request but only enforces auth on protected routes
- Public routes (health checks, docs) are explicitly excluded
- Protected routes must have valid Authorization: Bearer <token> headers
- User context is attached to request.state.user for downstream use

OPT-IN PROTECTION PATTERN:
Routes are public by default. Protection is applied via:
1. Route-level: Using require_auth dependency
2. Router-level: Applying dependencies to entire routers
3. Global: Configuring protected path prefixes in middleware

SECURITY DECISIONS:
- Token is extracted from Authorization header only (not cookies/query params)
- Bearer prefix is required and validated
- Invalid tokens receive 401 with generic error message
- Internal error details are logged but never returned to clients
- Rate limiting should be applied upstream (API gateway/load balancer)
"""

from typing import Callable, Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.auth.context import UserContext
from app.auth.firebase import TokenVerificationError, verify_firebase_token
from app.core.context import get_request_id, set_user_id
from app.core.logging import get_logger

logger = get_logger(__name__)

# Standard Authorization header prefix
BEARER_PREFIX = "Bearer "
BEARER_PREFIX_LEN = len(BEARER_PREFIX)


class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware for Firebase ID token verification.
    
    This middleware:
    1. Extracts tokens from Authorization headers on all requests
    2. Verifies tokens and attaches UserContext to request.state
    3. Only enforces authentication on protected paths
    4. Returns 401 for missing/invalid tokens on protected routes
    
    Configuration:
        protected_paths: Set of path prefixes that require authentication
        public_paths: Set of paths that are always public (overrides protected)
        auth_enabled: Global toggle for authentication (useful for testing)
    
    Example:
        app.add_middleware(
            FirebaseAuthMiddleware,
            protected_paths={"/api/v1"},
            public_paths={"/health", "/ready", "/docs"},
        )
    """

    # Default paths that should always be public
    DEFAULT_PUBLIC_PATHS: Set[str] = {
        "/health",
        "/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }

    def __init__(
        self,
        app: Callable,
        protected_paths: Optional[Set[str]] = None,
        public_paths: Optional[Set[str]] = None,
        auth_enabled: bool = True,
    ) -> None:
        """
        Initialize the authentication middleware.
        
        Args:
            app: The ASGI application
            protected_paths: Path prefixes requiring authentication.
                             If None, no paths require auth (opt-in via dependencies).
            public_paths: Paths that are always public, even if under protected prefixes.
            auth_enabled: Global toggle. When False, middleware is a no-op.
        """
        super().__init__(app)
        self.protected_paths = protected_paths or set()
        self.public_paths = (public_paths or set()) | self.DEFAULT_PUBLIC_PATHS
        self.auth_enabled = auth_enabled

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response],
    ) -> Response:
        """Process request with optional authentication enforcement."""
        
        # Initialize user state as None (unauthenticated)
        request.state.user = None

        # Fast path: auth disabled globally
        if not self.auth_enabled:
            return await call_next(request)

        # Extract path for matching
        path = request.url.path

        # Check if this path requires authentication
        requires_auth = self._requires_auth(path)

        # Try to extract and verify token (even for public routes)
        # This allows optional auth: routes can check if user is authenticated
        token = self._extract_token(request)
        user_context: Optional[UserContext] = None

        if token:
            try:
                user_context = verify_firebase_token(token)
                request.state.user = user_context
                
                # Set user_id in context for automatic log enrichment
                set_user_id(user_context.uid)
                
                # Log successful authentication at debug level
                logger.debug(
                    "Request authenticated",
                    uid=user_context.uid,
                    path=path,
                )
            except TokenVerificationError as e:
                # Log the failure with internal details
                logger.warning(
                    "Token verification failed",
                    error=e.message,
                    internal_error=e.internal_message,
                    path=path,
                    request_id=get_request_id(),
                )
                
                # If this is a protected route, reject immediately
                if requires_auth:
                    return self._unauthorized_response(
                        message=e.message,
                        request_id=get_request_id(),
                    )
                # For public routes, continue without user context

        # Enforce authentication on protected routes
        if requires_auth and user_context is None:
            # No token provided or verification failed silently
            if token is None:
                logger.debug(
                    "Missing authentication token on protected route",
                    path=path,
                )
                return self._unauthorized_response(
                    message="Authentication required",
                    request_id=get_request_id(),
                )

        # Continue to next middleware/route handler
        return await call_next(request)

    def _requires_auth(self, path: str) -> bool:
        """
        Determine if a path requires authentication.
        
        Logic:
        1. Explicit public paths are never protected
        2. Paths matching protected prefixes require auth
        3. All other paths are public (opt-in protection)
        """
        # Check explicit public paths first (highest priority)
        if path in self.public_paths:
            return False

        # Check public path prefixes
        for public_path in self.public_paths:
            if path.startswith(public_path + "/"):
                return False

        # Check protected path prefixes
        for protected_path in self.protected_paths:
            if path == protected_path or path.startswith(protected_path + "/"):
                return True

        # Default: not protected (opt-in via dependencies)
        return False

    def _extract_token(self, request: Request) -> Optional[str]:
        """
        Extract Bearer token from Authorization header.
        
        SECURITY: Only accepts tokens from Authorization header.
        Does not check cookies, query parameters, or other sources.
        
        Returns:
            The token string if present and properly formatted, None otherwise.
        """
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return None

        # Validate Bearer prefix (case-sensitive per RFC 6750)
        if not auth_header.startswith(BEARER_PREFIX):
            logger.debug(
                "Invalid Authorization header format",
                header_prefix=auth_header[:10] if len(auth_header) > 10 else auth_header,
            )
            return None

        # Extract token after "Bearer "
        token = auth_header[BEARER_PREFIX_LEN:].strip()

        if not token:
            return None

        return token

    def _unauthorized_response(
        self,
        message: str,
        request_id: Optional[str] = None,
    ) -> JSONResponse:
        """
        Create a standardized 401 Unauthorized response.
        
        SECURITY: Response contains only safe, generic error information.
        The WWW-Authenticate header indicates Bearer auth is required.
        """
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": message,
                    "details": {},
                    "request_id": request_id,
                }
            },
            headers={
                # RFC 6750: Indicate Bearer auth scheme
                "WWW-Authenticate": 'Bearer realm="api"',
            },
        )
