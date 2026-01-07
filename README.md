# ORDIN Backend

Production-grade FastAPI backend skeleton for the AI-driven task and scheduling system.

> An intelligent system that decides what you should work on next—and schedules it realistically

## Architecture Overview

This service provides the foundational infrastructure for the ORDIN platform:

- **FastAPI** - High-performance async web framework
- **Pydantic v2** - Data validation and settings management
- **Structlog** - Structured JSON logging with request correlation
- **Uvicorn** - Lightning-fast ASGI server

### Key Features

- ✅ Structured JSON logging with automatic request_id injection
- ✅ Request ID propagation (X-Request-ID header)
- ✅ Kubernetes-ready health probes (/health, /ready)
- ✅ Global exception handling with typed errors
- ✅ Environment-based configuration (dev/staging/prod)
- ✅ Fail-fast on misconfiguration
- ✅ CORS configuration for frontend integration
- ✅ Production Dockerfile with multi-stage build
- ✅ Dependency injection patterns
- ✅ Latency logging for all requests
- ✅ Firebase Authentication (ID token verification)
- ✅ Automatic user_id injection in all logs for authenticated requests

## Project Structure

```
app/
├── __init__.py              # Package root
├── main.py                  # FastAPI application factory
├── api/
│   ├── __init__.py
│   └── health.py            # Health check endpoints
├── auth/
│   ├── __init__.py          # Auth package exports
│   ├── context.py           # UserContext model (immutable)
│   ├── dependencies.py      # Auth dependency injection
│   ├── firebase.py          # Firebase Admin SDK integration
│   └── middleware.py        # Token verification middleware
├── config/
│   ├── __init__.py
│   └── settings.py          # Pydantic BaseSettings configuration
├── core/
│   ├── __init__.py
│   ├── context.py           # Request context (request_id, user_id)
│   ├── dependencies.py      # Core dependency injection providers
│   ├── exceptions.py        # Typed exception hierarchy
│   ├── handlers.py          # Global exception handlers
│   └── logging.py           # Structured logging setup
├── middleware/
│   ├── __init__.py
│   ├── logging.py           # Request/response logging
│   └── request_id.py        # Request ID generation
└── schemas/
    ├── __init__.py
    └── responses.py         # Pydantic response models
tests/
├── __init__.py
├── conftest.py              # Pytest fixtures
├── test_auth.py             # Authentication tests
├── test_health.py           # Health endpoint tests
└── test_exceptions.py       # Exception handling tests
```

## Quick Start

### Prerequisites

- Python 3.11 or 3.12
- pip or uv package manager

### Installation

```bash
# Clone the repository
cd ORDIN

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment configuration
cp .env.example .env
```

### Running the Server

```bash
# Development mode with auto-reload
python run.py --reload

# Or directly with uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Liveness probe - is the process alive? |
| `/ready` | GET | Readiness probe - can we handle traffic? |
| `/docs` | GET | Swagger UI (dev mode only) |
| `/redoc` | GET | ReDoc documentation (dev mode only) |

## Configuration

Configuration is managed via environment variables with the `ORDIN_` prefix.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ORDIN_ENV` | `dev` | Environment: dev, staging, prod |
| `ORDIN_DEBUG` | `false` | Debug mode (must be false in prod) |
| `ORDIN_HOST` | `0.0.0.0` | Server bind address |
| `ORDIN_PORT` | `8000` | Server port |
| `ORDIN_LOG_LEVEL` | `INFO` | Log level |
| `ORDIN_LOG_FORMAT` | `json` | Log format: json or text |

### Firebase Authentication Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ORDIN_FIREBASE_AUTH_ENABLED` | `true` | Enable/disable Firebase auth |
| `ORDIN_FIREBASE_PROJECT_ID` | - | Firebase project ID (required in prod) |
| `ORDIN_FIREBASE_CREDENTIALS_PATH` | - | Path to service account JSON |
| `ORDIN_FIREBASE_AUTH_EMULATOR_HOST` | - | Emulator host for local dev |

See [.env.example](.env.example) for all available options.

## Firebase Authentication

This service verifies Firebase ID tokens issued by your Firebase project. It does **not** handle login, signup, or token issuance—that happens on the client side via Firebase Auth SDK.

### How It Works

1. **Client authenticates** with Firebase (email/password, Google, etc.)
2. **Client gets ID token** from Firebase (`user.getIdToken()`)
3. **Client sends token** in `Authorization: Bearer <token>` header
4. **Server verifies token** using Firebase Admin SDK
5. **Server extracts user context** (uid, email, email_verified)
6. **Route handler receives** typed `UserContext` via dependency injection

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│   Firebase  │────▶│   Backend   │
│ (Frontend)  │     │  Auth SDK   │     │  (FastAPI)  │
└─────────────┘     └─────────────┘     └─────────────┘
      │                    │                    │
      │  1. Sign in        │                    │
      │───────────────────▶│                    │
      │                    │                    │
      │  2. ID Token       │                    │
      │◀───────────────────│                    │
      │                    │                    │
      │  3. API Request with Bearer Token       │
      │────────────────────────────────────────▶│
      │                    │                    │
      │                    │  4. Verify Token   │
      │                    │◀───────────────────│
      │                    │                    │
      │  5. Response (200/401)                  │
      │◀────────────────────────────────────────│
```

### Protected vs Public Routes

Routes are **public by default**. You can protect them in two ways:

#### Option 1: Path-Based Protection (Middleware)

Configure protected path prefixes in `app/main.py`:

```python
app.add_middleware(
    FirebaseAuthMiddleware,
    protected_paths={"/api/v1"},  # All /api/v1/* routes require auth
    auth_enabled=settings.firebase_auth_enabled,
)
```

#### Option 2: Dependency-Based Protection (Per Route)

Use `CurrentUserDep` to require authentication on specific routes:

```python
from app.auth import CurrentUserDep, OptionalUserDep

# This route REQUIRES authentication (401 if not authenticated)
@router.get("/profile")
async def get_profile(user: CurrentUserDep):
    return {"uid": user.uid, "email": user.email}

# This route OPTIONALLY uses authentication
@router.get("/feed")
async def get_feed(user: OptionalUserDep):
    if user:
        return {"personalized": True, "uid": user.uid}
    return {"personalized": False}

# Require verified email for sensitive operations
from app.auth import require_verified_email

@router.post("/payment")
async def process_payment(
    user: Annotated[UserContext, Depends(require_verified_email)]
):
    # Only users with verified email can access this
    ...
```

#### Option 3: Router-Level Protection

Apply authentication to an entire router:

```python
from fastapi import APIRouter, Depends
from app.auth import get_current_user

# All routes in this router require authentication
router = APIRouter(
    prefix="/api/v1/tasks",
    dependencies=[Depends(get_current_user)],
)
```

### UserContext Model

The `UserContext` is an immutable Pydantic model containing verified user claims:

```python
class UserContext(BaseModel):
    uid: str              # Firebase user ID (unique, stable)
    email: Optional[str]  # User's email (None for phone auth)
    email_verified: bool  # Whether email is verified
    auth_time: Optional[datetime]  # When user authenticated
```

### Error Responses

Authentication failures return 401 with a standard error format:

```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Token expired",
    "details": {},
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

Responses include the `WWW-Authenticate: Bearer realm="api"` header per RFC 6750.

### Local Development

#### Option 1: Disable Authentication

For rapid local development without Firebase:

```bash
# In .env
ORDIN_FIREBASE_AUTH_ENABLED=false
```

#### Option 2: Firebase Emulator

Use [Firebase Emulator Suite](https://firebase.google.com/docs/emulator-suite) for local development with auth:

```bash
# Install Firebase CLI
npm install -g firebase-tools

# Initialize emulators
firebase init emulators

# Start Auth emulator
firebase emulators:start --only auth

# In .env
ORDIN_FIREBASE_AUTH_ENABLED=true
ORDIN_FIREBASE_PROJECT_ID=your-project-id
ORDIN_FIREBASE_AUTH_EMULATOR_HOST=localhost:9099
```

#### Option 3: Real Firebase (Test Project)

1. Create a test Firebase project
2. Download service account JSON from Firebase Console
3. Configure environment:

```bash
# In .env
ORDIN_FIREBASE_AUTH_ENABLED=true
ORDIN_FIREBASE_PROJECT_ID=your-test-project
ORDIN_FIREBASE_CREDENTIALS_PATH=/path/to/service-account.json
```

### Production Configuration

In production, Firebase configuration is strictly validated:

```bash
# Required in production (ORDIN_ENV=prod)
ORDIN_FIREBASE_AUTH_ENABLED=true
ORDIN_FIREBASE_PROJECT_ID=your-production-project

# Option A: Service account file
ORDIN_FIREBASE_CREDENTIALS_PATH=/secrets/firebase-sa.json

# Option B: Application Default Credentials (GCP)
# Set GOOGLE_APPLICATION_CREDENTIALS or run on GCE/GKE/Cloud Run
```

## Logging

All logs are structured JSON with automatic context enrichment:

```json
{
  "timestamp": "2026-01-06T12:00:00.000Z",
  "level": "info",
  "event": "Request completed",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "firebase-uid-123456",
  "method": "GET",
  "path": "/api/v1/tasks",
  "status_code": 200,
  "latency_ms": 45.23,
  "service": "ordin-backend",
  "version": "0.1.0",
  "environment": "prod"
}
```

The `user_id` field is automatically injected when a user is authenticated. For unauthenticated requests, this field is omitted.

## Docker

### Build

```bash
docker build -t ordin-backend:latest .
```

### Run

```bash
docker run -p 8000:8000 \
  -e ORDIN_ENV=prod \
  -e ORDIN_LOG_FORMAT=json \
  ordin-backend:latest
```

## Kubernetes Deployment

The service includes proper health probes:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ordin-backend
spec:
  template:
    spec:
      containers:
        - name: ordin-backend
          image: ordin-backend:latest
          ports:
            - containerPort: 8000
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          env:
            - name: ORDIN_ENV
              value: "prod"
            - name: ORDIN_LOG_FORMAT
              value: "json"
```

## Development

### Install Development Dependencies

```bash
pip install -r requirements-dev.txt
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_health.py -v
```

### Code Quality

```bash
# Format code
black app tests
isort app tests

# Lint
ruff check app tests

# Type check
mypy app
```

## Error Handling

All errors follow a consistent format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": {
      "errors": [
        {"field": "email", "message": "Invalid email format", "type": "value_error"}
      ]
    },
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `UNAUTHORIZED` | 401 | Authentication required or token invalid |
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | Operation conflicts with existing state |
| `SERVICE_UNAVAILABLE` | 503 | External dependency unavailable |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

## Future Integration Points

This skeleton is prepared for:

- **Database**: Readiness check placeholder in `app/api/health.py`
- **External Services**: Service availability checks in readiness probe
- **Business Logic**: API router mounting in `app/main.py`
- **Authorization**: Role-based access control building on `UserContext`
- **Token Refresh**: Background token refresh for long-running operations

## License

MIT
