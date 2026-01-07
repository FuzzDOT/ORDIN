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
- ✅ Firestore user profile storage with auto-initialization
- ✅ User preferences (timezone, schedule, focus blocks)
- ✅ Task ingestion and validation with Firestore storage
- ✅ Per-user task isolation via subcollection structure
- ✅ Task filtering and pagination
- ✅ Google Calendar OAuth integration (read-only)
- ✅ Privacy-preserving busy block storage (no event titles)
- ✅ Availability computation using user preferences

## Project Structure

```
app/
├── __init__.py              # Package root
├── main.py                  # FastAPI application factory
├── api/
│   ├── __init__.py
│   ├── health.py            # Health check endpoints
│   └── v1/
│       ├── __init__.py      # API v1 router aggregation
│       ├── users.py         # User profile endpoints
│       ├── tasks.py         # Task CRUD endpoints
│       └── calendar.py      # Calendar & availability endpoints (A5)
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
├── db/
│   ├── __init__.py          # Database package exports
│   └── firestore.py         # Firestore client initialization
├── integrations/
│   ├── __init__.py          # External integrations
│   └── calendar/
│       ├── __init__.py      # Calendar provider exports
│       ├── base.py          # Abstract CalendarProvider interface
│       └── google.py        # Google Calendar implementation
├── middleware/
│   ├── __init__.py
│   ├── logging.py           # Request/response logging
│   └── request_id.py        # Request ID generation
├── models/
│   ├── __init__.py          # User profile & preferences models
│   ├── task.py              # Task models (Task, TaskCreate, etc.)
│   ├── calendar.py          # Calendar models (BusyBlock, etc.) (A5)
│   └── user.py              # Re-exports for convenience
├── repositories/
│   ├── __init__.py          # Repository exports
│   ├── user_repository.py   # Firestore user data access
│   ├── task_repository.py   # Firestore task data access
│   └── calendar_repository.py # Calendar integrations & busy blocks (A5)
├── services/
│   ├── __init__.py          # Service exports
│   ├── user_service.py      # User profile service
│   ├── task_service.py      # Task service
│   └── calendar_service.py  # Calendar sync & availability (A5)
└── schemas/
    ├── __init__.py
    └── responses.py         # Pydantic response models
tests/
├── __init__.py
├── conftest.py              # Pytest fixtures
├── test_auth.py             # Authentication tests
├── test_health.py           # Health endpoint tests
├── test_exceptions.py       # Exception handling tests
├── test_user_profile.py     # User profile tests
├── test_tasks.py            # Task model and service tests
└── test_calendar.py         # Calendar integration tests (A5)
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
| -------- | ------ | ----------- |
| `/health` | GET | Liveness probe - is the process alive? |
| `/ready` | GET | Readiness probe - can we handle traffic? |
| `/api/v1/users/me/profile` | GET | Get current user's profile |
| `/api/v1/users/me/profile` | PATCH | Update profile fields |
| `/api/v1/users/me/preferences` | PATCH | Update preference fields |
| `/api/v1/users/me/onboarding/complete` | POST | Mark onboarding complete |
| `/api/v1/users/me/profile` | DELETE | Delete user profile |
| `/api/v1/tasks` | POST | Create a new task |
| `/api/v1/tasks` | GET | List tasks (with filters) |
| `/api/v1/tasks/{task_id}` | GET | Get a specific task |
| `/api/v1/tasks/{task_id}` | PATCH | Update task fields |
| `/api/v1/tasks/{task_id}` | DELETE | Delete a task |
| `/api/v1/tasks/{task_id}/complete` | POST | Mark task as done |
| `/api/v1/tasks/{task_id}/start` | POST | Mark task as in progress |
| `/api/v1/tasks/{task_id}/archive` | POST | Archive task (soft delete) |
| `/api/v1/tasks/bulk/status` | POST | Bulk update task statuses |
| `/api/v1/calendar/oauth/{provider}/initiate` | GET | Start OAuth flow |
| `/api/v1/calendar/oauth/{provider}/callback` | GET | OAuth callback |
| `/api/v1/calendar/integrations` | GET | List calendar integrations |
| `/api/v1/calendar/{provider}/sync` | POST | Sync calendar events |
| `/api/v1/calendar/{provider}` | DELETE | Disconnect calendar |
| `/api/v1/calendar/availability` | POST | Compute availability |
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
| `ORDIN_FIREBASE_AUTH_EMULATOR_HOST` | - | Auth emulator host for local dev |

### Firestore Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ORDIN_FIRESTORE_EMULATOR_HOST` | - | Firestore emulator host for local dev |

See [.env.example](.env.example) for all available options.

## User Profile & Preferences

User profiles are stored in Firestore and auto-initialized on first access.

### Data Model

```python
UserProfile:
  uid: str                    # Firebase UID (document ID)
  email: str | None           # Cached from Firebase
  display_name: str | None    # User's display name
  preferences: UserPreferences
  onboarding_completed: bool  # Default: false
  created_at: datetime        # Auto-set
  updated_at: datetime        # Auto-updated
  schema_version: int         # Default: 1

UserPreferences:
  timezone: str               # IANA timezone (default: "UTC")
  typical_wake_time: TimeOfDay    # Default: 07:00
  typical_sleep_time: TimeOfDay   # Default: 23:00
  preferred_focus_block_lengths: list[int]  # Default: [45]
  preferred_working_days: list[str]         # Default: Mon-Fri
  notifications_enabled: bool               # Default: true
  quiet_hours_start: TimeOfDay | None
  quiet_hours_end: TimeOfDay | None
```

### Firestore Collection Structure

```
firestore/
└── users/                    # Collection
    └── {firebase_uid}/       # Document (auto-created on first access)
        ├── uid
        ├── email
        ├── display_name
        ├── preferences {
        │     timezone
        │     typical_wake_time { hour, minute }
        │     typical_sleep_time { hour, minute }
        │     preferred_focus_block_lengths []
        │     preferred_working_days []
        │     notifications_enabled
        │     quiet_hours_start
        │     quiet_hours_end
        │   }
        ├── onboarding_completed
        ├── created_at
        ├── updated_at
        └── schema_version
```

### API Examples

#### Get Profile

```bash
curl -X GET http://localhost:8000/api/v1/users/me/profile \
  -H "Authorization: Bearer <firebase_id_token>"
```

Response:
```json
{
  "uid": "firebase-uid-123",
  "email": "user@example.com",
  "display_name": null,
  "preferences": {
    "timezone": "UTC",
    "typical_wake_time": {"hour": 7, "minute": 0},
    "typical_sleep_time": {"hour": 23, "minute": 0},
    "preferred_focus_block_lengths": [45],
    "preferred_working_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "notifications_enabled": true,
    "quiet_hours_start": null,
    "quiet_hours_end": null
  },
  "onboarding_completed": false,
  "created_at": "2026-01-06T12:00:00Z",
  "updated_at": "2026-01-06T12:00:00Z",
  "schema_version": 1
}
```

#### Update Profile

```bash
curl -X PATCH http://localhost:8000/api/v1/users/me/profile \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{"display_name": "John Doe"}'
```

#### Update Preferences

```bash
curl -X PATCH http://localhost:8000/api/v1/users/me/preferences \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "timezone": "America/New_York",
    "typical_wake_time": {"hour": 6, "minute": 30},
    "preferred_focus_block_lengths": [25, 45, 60],
    "preferred_working_days": ["monday", "tuesday", "wednesday", "thursday"]
  }'
```

### Focus Block Lengths

Valid values: `25` (short), `45` (medium), `60` (long), `90` (extended)

### Days of Week

Valid values: `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday`, `sunday`

## Task Ingestion & Validation

Tasks are the core work items in ORDIN. This layer handles ingestion, validation, and state management only—no prioritization, scoring, or scheduling logic.

### Task Data Model

```python
Task:
  task_id: str              # UUID (auto-generated)
  user_id: str              # Firebase UID (owner)
  title: str                # 1-256 characters (required)
  description: str | None   # Up to 4096 characters
  domain: TaskDomain        # Category (see below)
  deadline: datetime        # ISO 8601 (required)
  effort_estimate_minutes: int | None  # 1-1440 (24 hours max)
  importance: int           # 1-5 scale (default: 3)
  constraints: TaskConstraints | None  # Scheduling hints
  status: TaskStatus        # Lifecycle state
  created_at: datetime      # Auto-set
  updated_at: datetime      # Auto-updated

TaskConstraints:
  earliest_start: datetime | None      # Don't start before this time
  must_be_single_block: bool           # Complete in one session (default: false)
  preferred_time_of_day: str | None    # "morning", "afternoon", "evening"
  location_bound: str | None           # e.g., "office", "home" (max 64 chars)
```

### Task Domains

| Value | Description |
| ----- | ----------- |
| `work` | Professional/job-related tasks |
| `personal` | Personal life tasks |
| `admin` | Administrative tasks (bills, paperwork) |
| `health` | Health and fitness tasks |
| `learning` | Education and skill development |
| `social` | Social commitments |
| `creative` | Creative projects |
| `other` | Uncategorized (default) |

### Task Statuses

| Value | Description |
| ----- | ----------- |
| `pending` | Created but not started (default) |
| `in_progress` | Currently being worked on |
| `done` | Completed successfully |
| `archived` | No longer active (soft delete) |

### Firestore Collection Structure

Tasks are stored in per-user subcollections for strict isolation:

```text
firestore/
└── users/                    # Collection
    └── {firebase_uid}/       # Document
        └── tasks/            # Subcollection
            └── {task_id}/    # Document (UUID)
                ├── task_id
                ├── user_id
                ├── title
                ├── description
                ├── domain
                ├── deadline
                ├── effort_estimate_minutes
                ├── importance
                ├── constraints {
                │     earliest_start
                │     must_be_single_block
                │     preferred_time_of_day
                │     location_bound
                │   }
                ├── status
                ├── created_at
                └── updated_at
```

### Firestore Indexing

For efficient queries, create composite indexes:

```text
Collection: users/{uid}/tasks
  - (status ASC, deadline ASC)
  - (domain ASC, deadline ASC)
  - (deadline ASC)
```

### Task API Examples

#### Create a Task

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Complete project proposal",
    "description": "Draft and review the Q2 project proposal",
    "domain": "work",
    "deadline": "2026-01-15T17:00:00Z",
    "effort_estimate_minutes": 120,
    "importance": 4,
    "constraints": {
      "must_be_single_block": true,
      "preferred_time_of_day": "morning"
    }
  }'
```

Response (201 Created):
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Complete project proposal",
  "description": "Draft and review the Q2 project proposal",
  "domain": "work",
  "deadline": "2026-01-15T17:00:00+00:00",
  "effort_estimate_minutes": 120,
  "importance": 4,
  "constraints": {
    "earliest_start": null,
    "must_be_single_block": true,
    "preferred_time_of_day": "morning",
    "location_bound": null
  },
  "status": "pending",
  "created_at": "2026-01-07T10:30:00+00:00",
  "updated_at": "2026-01-07T10:30:00+00:00"
}
```

#### List Tasks with Filters

```bash
# List pending tasks due this week
curl -X GET "http://localhost:8000/api/v1/tasks?status=pending&deadline_before=2026-01-14T23:59:59Z&limit=20" \
  -H "Authorization: Bearer <firebase_id_token>"
```

Response:
```json
{
  "tasks": [
    {
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Complete project proposal",
      "domain": "work",
      "deadline": "2026-01-15T17:00:00+00:00",
      "importance": 4,
      "status": "pending",
      ...
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

#### Get a Specific Task

```bash
curl -X GET http://localhost:8000/api/v1/tasks/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer <firebase_id_token>"
```

#### Update a Task (PATCH)

Only provided fields are updated; others remain unchanged:

```bash
curl -X PATCH http://localhost:8000/api/v1/tasks/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "importance": 5,
    "deadline": "2026-01-14T12:00:00Z"
  }'
```

#### Complete a Task

```bash
curl -X POST http://localhost:8000/api/v1/tasks/550e8400-e29b-41d4-a716-446655440000/complete \
  -H "Authorization: Bearer <firebase_id_token>"
```

#### Delete a Task

```bash
curl -X DELETE http://localhost:8000/api/v1/tasks/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer <firebase_id_token>"
```

Response: 204 No Content

#### Bulk Update Status

```bash
curl -X POST http://localhost:8000/api/v1/tasks/bulk/status \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": [
      "550e8400-e29b-41d4-a716-446655440000",
      "660e8400-e29b-41d4-a716-446655440001"
    ],
    "status": "archived"
  }'
```

### Task Validation Rules

| Field | Validation |
| ----- | ---------- |
| `title` | Required, 1-256 characters |
| `description` | Optional, max 4096 characters |
| `deadline` | Required, ISO 8601 datetime |
| `importance` | Integer 1-5 (default: 3) |
| `effort_estimate_minutes` | Optional, 1-1440 |
| `constraints.earliest_start` | Must be before deadline if set |
| `constraints.preferred_time_of_day` | Must be "morning", "afternoon", or "evening" |
| `constraints.location_bound` | Max 64 characters |

### Delete Behavior

- **Hard delete**: `DELETE /api/v1/tasks/{task_id}` permanently removes the task
- **Soft delete**: `POST /api/v1/tasks/{task_id}/archive` sets status to `archived`

Use archived status for tasks you want to preserve for history/analytics.

## Calendar Integration (A5)

ORDIN integrates with external calendars to determine user availability. Currently supports Google Calendar with plans for Apple Calendar and Microsoft Outlook.

### Privacy-First Design

**Minimal data retention**: Only busy/free information is stored. Event titles, descriptions, attendees, and other metadata are **never** stored in ORDIN. This protects user privacy while enabling intelligent scheduling.

### Key Features

- ✅ OAuth 2.0 authentication (read-only calendar access)
- ✅ Provider-agnostic interface (easy to add new providers)
- ✅ Idempotent sync (safe to retry, handles deletions)
- ✅ Availability computation using user preferences
- ✅ Automatic token refresh
- ✅ Rate limit handling with exponential backoff

### OAuth Setup (Google Calendar)

1. **Create OAuth credentials** in [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
   - Application type: Web application
   - Authorized redirect URI: `http://localhost:8000/api/v1/calendar/oauth/google/callback`

2. **Enable Google Calendar API** in [Google Cloud Console](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)

3. **Configure environment variables**:
   ```bash
   ORDIN_GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
   ORDIN_GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
   ORDIN_GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/calendar/oauth/google/callback
   ```

### Calendar API Endpoints

| Endpoint | Method | Description |
| -------- | ------ | ----------- |
| `/api/v1/calendar/oauth/{provider}/initiate` | GET | Start OAuth flow |
| `/api/v1/calendar/oauth/{provider}/callback` | GET | OAuth callback |
| `/api/v1/calendar/integrations` | GET | List all integrations |
| `/api/v1/calendar/{provider}/status` | GET | Get integration status |
| `/api/v1/calendar/{provider}/sync` | POST | Trigger calendar sync |
| `/api/v1/calendar/{provider}` | DELETE | Disconnect integration |
| `/api/v1/calendar/availability` | POST | Compute availability |

### Firestore Structure

```
firestore/
└── users/
    └── {firebase_uid}/
        ├── integrations/
        │   └── calendar/
        │       └── google/
        │           └── state/          # OAuth tokens, sync metadata
        │               ├── provider
        │               ├── status
        │               ├── access_token (encrypted at rest)
        │               ├── refresh_token (encrypted at rest)
        │               ├── token_expires_at
        │               ├── scopes
        │               ├── connected_at
        │               ├── last_sync_at
        │               └── sync_error
        └── calendar_busy_blocks/
            └── {block_id}/             # Deterministic hash
                ├── provider
                ├── calendar_id
                ├── source_event_id
                ├── start_time
                ├── end_time
                ├── block_type          # busy, tentative, focus
                ├── is_all_day
                └── synced_at
```

### OAuth Flow Example

**1. Initiate OAuth**
```bash
curl -X GET http://localhost:8000/api/v1/calendar/oauth/google/initiate \
  -H "Authorization: Bearer <firebase_id_token>"
```

Response:
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "abc123...",
  "provider": "google"
}
```

**2. Redirect user to `auth_url`**

The frontend should:
1. Store `state` in session storage
2. Redirect user to `auth_url`
3. User grants calendar access
4. Google redirects to callback with `code` and `state`

**3. Complete OAuth**
```bash
curl -X GET "http://localhost:8000/api/v1/calendar/oauth/google/callback?code=AUTH_CODE&state=abc123&expected_state=abc123" \
  -H "Authorization: Bearer <firebase_id_token>"
```

### Calendar Sync

```bash
curl -X POST http://localhost:8000/api/v1/calendar/google/sync \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{"days_ahead": 14, "calendar_id": "primary"}'
```

Response:
```json
{
  "provider": "google",
  "events_fetched": 15,
  "blocks_created": 15,
  "blocks_deleted": 2,
  "sync_window_start": "2024-01-15T00:00:00Z",
  "sync_window_end": "2024-01-29T00:00:00Z",
  "synced_at": "2024-01-15T12:00:00Z"
}
```

### Availability Computation

Computes available time slots by subtracting busy blocks from the user's waking hours (based on preferences from A3).

```bash
curl -X POST http://localhost:8000/api/v1/calendar/availability \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2024-01-15T00:00:00Z",
    "end_time": "2024-01-17T00:00:00Z",
    "min_duration_minutes": 30,
    "include_tentative_as_busy": false
  }'
```

Response:
```json
{
  "slots": [
    {
      "start_time": "2024-01-15T08:00:00-05:00",
      "end_time": "2024-01-15T10:00:00-05:00",
      "duration_minutes": 120
    },
    {
      "start_time": "2024-01-15T14:00:00-05:00",
      "end_time": "2024-01-15T17:00:00-05:00",
      "duration_minutes": 180
    }
  ],
  "start_time": "2024-01-15T00:00:00Z",
  "end_time": "2024-01-17T00:00:00Z",
  "timezone": "America/New_York",
  "total_minutes_available": 300
}
```

### Availability Algorithm

1. **Generate waking hours** from user's `typical_wake_time` and `typical_sleep_time`
2. **Filter by working days** from `preferred_working_days`
3. **Subtract busy blocks** from connected calendars
4. **Apply minimum duration** filter
5. **Return available slots** in user's timezone

### Error Handling

| Status | Description | Action |
| ------ | ----------- | ------ |
| 400 | Calendar not connected | User needs to complete OAuth |
| 401 | Token expired | Re-authenticate with OAuth |
| 429 | Rate limited | Retry with exponential backoff |
| 502 | Provider error | Retry later |

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

Use [Firebase Emulator Suite](https://firebase.google.com/docs/emulator-suite) for local development with auth and Firestore:

```bash
# Install Firebase CLI
npm install -g firebase-tools

# Initialize emulators (select Auth and Firestore)
firebase init emulators

# Start emulators
firebase emulators:start --only auth,firestore

# In .env
ORDIN_FIREBASE_AUTH_ENABLED=true
ORDIN_FIREBASE_PROJECT_ID=your-project-id
ORDIN_FIREBASE_AUTH_EMULATOR_HOST=localhost:9099
ORDIN_FIRESTORE_EMULATOR_HOST=localhost:8080
```

The Firestore emulator UI is available at `http://localhost:4000` (default).

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

- **AI Integration**: LLM-based scheduling and prioritization
- **External Services**: Service availability checks in readiness probe
- **Authorization**: Role-based access control building on `UserContext`
- **Token Refresh**: Background token refresh for long-running operations
- **Notifications**: Push notifications based on user preferences
- **Task Scheduling**: Intelligent scheduling based on task constraints and user preferences
- **Calendar Integration**: Sync with external calendars

## License

MIT
