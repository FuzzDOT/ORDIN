# ORDIN Backend

Production-grade FastAPI backend for an AI-native task orchestration and scheduling system.

> An intelligent system that determines what users should work on next and schedules it realistically.

---

# Overview

ORDIN is designed as the backend orchestration layer for intelligent productivity infrastructure.

The platform combines:
- task ingestion,
- structured validation,
- calendar-aware scheduling,
- availability computation,
- authentication,
- observability,
- and scalable backend architecture.

The system is designed with:
- strict typing,
- production-grade infrastructure patterns,
- privacy-preserving calendar handling,
- and modular service boundaries.

---

# Core Features

- Structured JSON logging with automatic request correlation
- Request ID propagation (`X-Request-ID`)
- Kubernetes-ready health probes (`/health`, `/ready`)
- Global exception handling with typed errors
- Environment-based configuration (`dev`, `staging`, `prod`)
- Fail-fast startup validation
- Production Docker support with multi-stage builds
- Dependency injection architecture
- Latency tracing for all requests
- Firebase Authentication with ID token verification
- Automatic `user_id` injection into logs
- Firestore-backed user profile storage
- Per-user task isolation
- Task filtering and pagination
- Google Calendar OAuth integration
- Privacy-preserving busy block storage
- Availability computation using user preferences

---

# Technical Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI |
| Validation | Pydantic v2 |
| Authentication | Firebase Auth |
| Database | Firestore |
| Logging | Structlog |
| Server | Uvicorn |
| Containerization | Docker |
| Deployment | Kubernetes |

---

# Architecture Philosophy

ORDIN is structured around several core engineering principles:

- Typed domain boundaries
- Modular service architecture
- Per-user data isolation
- Privacy-first calendar integration
- Request-scoped observability
- Deterministic validation behavior
- Infrastructure readiness
- Fail-fast configuration handling

The backend is intentionally designed to support future:
- AI scheduling engines,
- prioritization systems,
- optimization pipelines,
- and autonomous orchestration workflows.

---

# Architecture Overview

```text
Client
   │
   ▼
FastAPI API Layer
   │
   ├── Authentication Middleware
   ├── Request Context Injection
   ├── Structured Logging
   ├── Exception Handling
   │
   ▼
Service Layer
   │
   ├── User Services
   ├── Task Services
   ├── Calendar Services
   │
   ▼
Repository Layer
   │
   ├── Firestore Access
   ├── Calendar Integrations
   │
   ▼
External Systems
   ├── Firebase Auth
   ├── Google Calendar
   └── Firestore
```

---

# Project Structure

```text
app/
├── __init__.py
├── main.py

├── api/
│   ├── health.py
│   └── v1/
│       ├── users.py
│       ├── tasks.py
│       └── calendar.py

├── auth/
│   ├── context.py
│   ├── dependencies.py
│   ├── firebase.py
│   └── middleware.py

├── config/
│   └── settings.py

├── core/
│   ├── context.py
│   ├── dependencies.py
│   ├── exceptions.py
│   ├── handlers.py
│   └── logging.py

├── db/
│   └── firestore.py

├── integrations/
│   └── calendar/
│       ├── base.py
│       └── google.py

├── middleware/
│   ├── logging.py
│   └── request_id.py

├── models/
│   ├── task.py
│   ├── calendar.py
│   └── user.py

├── repositories/
│   ├── user_repository.py
│   ├── task_repository.py
│   └── calendar_repository.py

├── services/
│   ├── user_service.py
│   ├── task_service.py
│   └── calendar_service.py

└── schemas/
    └── responses.py

tests/
├── conftest.py
├── test_auth.py
├── test_health.py
├── test_exceptions.py
├── test_user_profile.py
├── test_tasks.py
└── test_calendar.py
```

---

# Quick Start

## Prerequisites

- Python 3.11 or 3.12
- pip or uv

---

## Installation

```bash
# Clone repository
git clone <repo-url>

cd ORDIN

# Create virtual environment
python -m venv .venv

# Activate environment
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

---

## Running the Server

```bash
# Development mode
python run.py --reload

# Or directly with uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API available at:

```text
http://localhost:8000
```

---

# API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness probe |
| `/ready` | GET | Readiness probe |
| `/api/v1/users/me/profile` | GET | Get current user profile |
| `/api/v1/users/me/profile` | PATCH | Update profile |
| `/api/v1/users/me/preferences` | PATCH | Update preferences |
| `/api/v1/users/me/onboarding/complete` | POST | Complete onboarding |
| `/api/v1/users/me/profile` | DELETE | Delete profile |
| `/api/v1/tasks` | POST | Create task |
| `/api/v1/tasks` | GET | List tasks |
| `/api/v1/tasks/{task_id}` | GET | Get task |
| `/api/v1/tasks/{task_id}` | PATCH | Update task |
| `/api/v1/tasks/{task_id}` | DELETE | Delete task |
| `/api/v1/tasks/{task_id}/complete` | POST | Complete task |
| `/api/v1/tasks/{task_id}/start` | POST | Start task |
| `/api/v1/tasks/{task_id}/archive` | POST | Archive task |
| `/api/v1/tasks/bulk/status` | POST | Bulk update task status |
| `/api/v1/calendar/oauth/{provider}/initiate` | GET | Start OAuth |
| `/api/v1/calendar/oauth/{provider}/callback` | GET | OAuth callback |
| `/api/v1/calendar/integrations` | GET | List integrations |
| `/api/v1/calendar/{provider}/sync` | POST | Sync calendar |
| `/api/v1/calendar/{provider}` | DELETE | Disconnect calendar |
| `/api/v1/calendar/availability` | POST | Compute availability |
| `/docs` | GET | Swagger UI |
| `/redoc` | GET | ReDoc documentation |

---

# Example API Usage

## Create Task

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Complete project proposal",
    "domain": "work",
    "deadline": "2026-01-15T17:00:00Z",
    "importance": 4
  }'
```

---

## Compute Availability

```bash
curl -X POST http://localhost:8000/api/v1/calendar/availability \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2024-01-15T00:00:00Z",
    "end_time": "2024-01-17T00:00:00Z",
    "min_duration_minutes": 30
  }'
```

---

# Authentication

ORDIN uses Firebase Authentication for secure ID token verification.

Authentication flow:

1. Client authenticates using Firebase SDK
2. Client receives Firebase ID token
3. Client sends token in Authorization header
4. Backend verifies token using Firebase Admin SDK
5. User context is injected into request scope

---

## Protected Route Example

```python
@router.get("/profile")
async def get_profile(user: CurrentUserDep):
    return {
        "uid": user.uid,
        "email": user.email
    }
```

---

# User Context

```python
class UserContext(BaseModel):
    uid: str
    email: Optional[str]
    email_verified: bool
    auth_time: Optional[datetime]
```

---

# User Profile Model

```python
UserProfile:
  uid: str
  email: str | None
  display_name: str | None
  preferences: UserPreferences
  onboarding_completed: bool
  created_at: datetime
  updated_at: datetime
  schema_version: int
```

---

# Task Model

```python
Task:
  task_id: str
  user_id: str
  title: str
  description: str | None
  domain: TaskDomain
  deadline: datetime
  effort_estimate_minutes: int | None
  importance: int
  constraints: TaskConstraints | None
  status: TaskStatus
  created_at: datetime
  updated_at: datetime
```

---

# Calendar Integration

ORDIN integrates with external calendars to compute availability.

Current support:
- Google Calendar

Planned support:
- Apple Calendar
- Microsoft Outlook

---

# Privacy Model

ORDIN follows a privacy-first architecture.

Stored:
- Busy/free block information
- Time ranges
- Availability windows

Never stored:
- Event titles
- Descriptions
- Attendees
- Meeting metadata

This allows scheduling computation while preserving user privacy.

---

# OAuth Setup

## Google Calendar

### Required environment variables

```bash
ORDIN_GOOGLE_OAUTH_CLIENT_ID=...
ORDIN_GOOGLE_OAUTH_CLIENT_SECRET=...
ORDIN_GOOGLE_OAUTH_REDIRECT_URI=...
```

---

# Availability Computation

Availability is computed by:

1. Generating waking-hour windows
2. Filtering valid working days
3. Subtracting calendar busy blocks
4. Applying minimum duration filters
5. Returning valid availability slots

---

# Logging

ORDIN uses structured JSON logging with automatic context enrichment.

Example:

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
  "latency_ms": 45.23
}
```

---

# Configuration

Environment variables use the `ORDIN_` prefix.

## Core Settings

| Variable | Description |
|---|---|
| `ORDIN_ENV` | Environment |
| `ORDIN_DEBUG` | Debug mode |
| `ORDIN_HOST` | Host |
| `ORDIN_PORT` | Port |
| `ORDIN_LOG_LEVEL` | Log level |
| `ORDIN_LOG_FORMAT` | Logging format |

---

# Docker

## Build

```bash
docker build -t ordin-backend:latest .
```

---

## Run

```bash
docker run -p 8000:8000 \
  -e ORDIN_ENV=prod \
  ordin-backend:latest
```

---

# Kubernetes

ORDIN includes:
- liveness probes,
- readiness probes,
- containerized deployment support.

Example:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
```

---

# Development

## Install Dev Dependencies

```bash
pip install -r requirements-dev.txt
```

---

## Run Tests

```bash
pytest

pytest --cov=app --cov-report=html
```

---

## Code Quality

```bash
black app tests

isort app tests

ruff check app tests

mypy app
```

---

# Error Handling

Example error format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

---

# Error Codes

| Code | HTTP Status | Description |
|---|---|---|
| `UNAUTHORIZED` | 401 | Authentication required |
| `VALIDATION_ERROR` | 422 | Validation failed |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | State conflict |
| `SERVICE_UNAVAILABLE` | 503 | Dependency unavailable |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

---

# Future Expansion

ORDIN is architected to support future:
- AI scheduling engines
- prioritization systems
- autonomous orchestration
- notification systems
- adaptive planning
- optimization pipelines
- intelligent calendar negotiation

---

# License

MIT
