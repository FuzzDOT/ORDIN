"""
Firebase Admin SDK Integration
==============================
Idempotent initialization and token verification for Firebase Authentication.

SECURITY ARCHITECTURE:
- Firebase Admin SDK verifies ID tokens using Google's public keys
- Token verification is done server-side, never trusting client claims
- Invalid/expired tokens are rejected before any business logic executes
- Internal errors are logged but never exposed to clients

INITIALIZATION:
- Firebase is initialized once at application startup (idempotent)
- Supports service account credentials or Application Default Credentials (ADC)
- Supports Firebase Auth Emulator for local development

TOKEN VERIFICATION:
- Validates token signature against Google's public keys
- Checks token expiration and issuer claims
- Extracts only trusted claims (uid, email, email_verified)
"""

import os
import threading
from datetime import datetime, timezone
from typing import Optional

from app.auth.context import UserContext
from app.core.logging import get_logger

logger = get_logger(__name__)

# Thread-safe initialization flag
_firebase_initialized = False
_firebase_lock = threading.Lock()


class FirebaseAuthError(Exception):
    """
    Base exception for Firebase authentication errors.
    
    SECURITY: Error messages are sanitized before being returned to clients.
    Detailed error information is logged server-side only.
    """

    def __init__(self, message: str, internal_message: Optional[str] = None) -> None:
        """
        Args:
            message: Safe message that can be shown to clients
            internal_message: Detailed message for server-side logging only
        """
        super().__init__(message)
        self.message = message
        self.internal_message = internal_message or message


class TokenVerificationError(FirebaseAuthError):
    """Raised when a Firebase ID token fails verification."""

    pass


class FirebaseInitializationError(FirebaseAuthError):
    """Raised when Firebase Admin SDK fails to initialize."""

    pass


def initialize_firebase(
    project_id: Optional[str] = None,
    credentials_path: Optional[str] = None,
    emulator_host: Optional[str] = None,
) -> bool:
    """
    Initialize Firebase Admin SDK (idempotent).
    
    This function is safe to call multiple times - subsequent calls are no-ops.
    It uses double-checked locking for thread safety during initialization.
    
    Args:
        project_id: Firebase project ID (required for emulator, optional otherwise)
        credentials_path: Path to service account JSON file. If None, uses ADC.
        emulator_host: Firebase Auth Emulator host (e.g., "localhost:9099")
    
    Returns:
        True if initialization succeeded or was already done, False otherwise.
    
    Raises:
        FirebaseInitializationError: If initialization fails critically.
    
    SECURITY: Credentials are never logged. Only initialization status is recorded.
    """
    global _firebase_initialized

    # Fast path: already initialized
    if _firebase_initialized:
        return True

    with _firebase_lock:
        # Double-check after acquiring lock
        if _firebase_initialized:
            return True

        try:
            # Import Firebase Admin SDK
            import firebase_admin
            from firebase_admin import credentials as fb_credentials

            # Check if already initialized by another process/import
            try:
                firebase_admin.get_app()
                logger.info("Firebase Admin SDK already initialized")
                _firebase_initialized = True
                return True
            except ValueError:
                # App not initialized, proceed with initialization
                pass

            # Configure emulator if specified
            if emulator_host:
                os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = emulator_host
                logger.info(
                    "Firebase Auth Emulator configured",
                    emulator_host=emulator_host,
                )

            # Build initialization options
            options = {}
            if project_id:
                options["projectId"] = project_id

            # Initialize with credentials or ADC
            if credentials_path:
                if not os.path.exists(credentials_path):
                    raise FirebaseInitializationError(
                        "Firebase initialization failed",
                        internal_message=f"Credentials file not found: {credentials_path}",
                    )
                cred = fb_credentials.Certificate(credentials_path)
                firebase_admin.initialize_app(cred, options=options if options else None)
                logger.info(
                    "Firebase Admin SDK initialized with service account",
                    project_id=project_id,
                )
            else:
                # Use Application Default Credentials (ADC)
                # This works with:
                # - GOOGLE_APPLICATION_CREDENTIALS env var
                # - GCE/GKE metadata service
                # - Cloud Run/Cloud Functions built-in credentials
                cred = fb_credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred, options=options if options else None)
                logger.info(
                    "Firebase Admin SDK initialized with ADC",
                    project_id=project_id,
                )

            _firebase_initialized = True
            return True

        except ImportError as e:
            raise FirebaseInitializationError(
                "Firebase initialization failed",
                internal_message=f"firebase-admin package not installed: {e}",
            )
        except Exception as e:
            raise FirebaseInitializationError(
                "Firebase initialization failed",
                internal_message=f"Unexpected error during Firebase init: {e}",
            )


def verify_firebase_token(id_token: str) -> UserContext:
    """
    Verify a Firebase ID token and extract user context.
    
    This function performs full cryptographic verification of the token:
    1. Validates the token signature using Google's public keys
    2. Checks token expiration (exp claim)
    3. Verifies the issuer (iss claim) matches the Firebase project
    4. Extracts trusted user claims (uid, email, email_verified)
    
    Args:
        id_token: The Firebase ID token from the Authorization header
    
    Returns:
        UserContext with verified user information
    
    Raises:
        TokenVerificationError: If the token is invalid, expired, or malformed
    
    SECURITY NOTES:
    - Never log the full token (it's a credential)
    - Only log token prefix for debugging correlation
    - Error messages to clients are generic; details are logged server-side
    """
    if not _firebase_initialized:
        raise TokenVerificationError(
            "Authentication service unavailable",
            internal_message="Firebase not initialized when verifying token",
        )

    if not id_token or not isinstance(id_token, str):
        raise TokenVerificationError(
            "Invalid token format",
            internal_message="Token is empty or not a string",
        )

    try:
        from firebase_admin import auth

        # Verify the ID token
        # check_revoked=True adds latency but ensures revoked tokens are rejected
        # For high-performance scenarios, consider check_revoked=False with
        # periodic token refresh requirements
        decoded_token = auth.verify_id_token(id_token, check_revoked=True)

        # Extract user claims
        uid = decoded_token.get("uid") or decoded_token.get("user_id")
        if not uid:
            raise TokenVerificationError(
                "Invalid token",
                internal_message="Token missing uid/user_id claim",
            )

        # Parse auth_time if present (Unix timestamp)
        auth_time = None
        auth_time_claim = decoded_token.get("auth_time")
        if auth_time_claim:
            try:
                auth_time = datetime.fromtimestamp(auth_time_claim, tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                # Non-critical: log but don't fail verification
                logger.warning(
                    "Failed to parse auth_time claim",
                    auth_time_raw=auth_time_claim,
                )

        # Build immutable user context
        user_context = UserContext(
            uid=uid,
            email=decoded_token.get("email"),
            email_verified=decoded_token.get("email_verified", False),
            auth_time=auth_time,
        )

        logger.debug(
            "Token verified successfully",
            uid=uid,
            email_verified=user_context.email_verified,
        )

        return user_context

    except ImportError:
        raise TokenVerificationError(
            "Authentication service unavailable",
            internal_message="firebase-admin package not available",
        )

    # Handle specific Firebase auth errors
    except Exception as e:
        error_type = type(e).__name__

        # Map Firebase exceptions to appropriate error messages
        # SECURITY: Never expose internal error details to clients
        if "ExpiredIdTokenError" in error_type or "expired" in str(e).lower():
            raise TokenVerificationError(
                "Token expired",
                internal_message=f"Firebase token expired: {e}",
            )
        elif "RevokedIdTokenError" in error_type or "revoked" in str(e).lower():
            raise TokenVerificationError(
                "Token revoked",
                internal_message=f"Firebase token revoked: {e}",
            )
        elif "InvalidIdTokenError" in error_type or "invalid" in str(e).lower():
            raise TokenVerificationError(
                "Invalid token",
                internal_message=f"Firebase token invalid: {e}",
            )
        elif "CertificateFetchError" in error_type:
            raise TokenVerificationError(
                "Authentication service temporarily unavailable",
                internal_message=f"Failed to fetch Firebase public keys: {e}",
            )
        else:
            raise TokenVerificationError(
                "Token verification failed",
                internal_message=f"Unexpected Firebase auth error ({error_type}): {e}",
            )


def is_firebase_initialized() -> bool:
    """
    Check if Firebase Admin SDK has been initialized.
    
    Useful for health checks and conditional middleware behavior.
    """
    return _firebase_initialized
