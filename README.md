# ORDIN

**A production-grade FastAPI backend for an AI-native task orchestration and scheduling system, purpose-built to determine what users should work on next and schedule it realistically against their actual calendar availability.**

ORDIN is the orchestration layer that sits between a user's tasks, their connected calendars, and a future AI scheduling engine. It is not a simple CRUD API bolted onto a database. It is a carefully layered system that handles Firebase authentication with automatic context propagation, structured task lifecycle management with explicit state transitions, privacy-preserving calendar synchronization that stores only the minimum information needed for scheduling, real-time availability computation that intersects user preferences with live calendar data, and the full observability infrastructure that makes all of it debuggable in production at scale.

Every engineering decision in the codebase reflects the same underlying goal: build the cleanest possible foundation for an AI system to make intelligent scheduling decisions on behalf of real users.

---

## Highlights

- **Firebase Authentication** with per-request `UserContext` injection, automatic `user_id` propagation into every log line, and zero boilerplate in route handlers
- **Privacy-first calendar integration**: busy and free time blocks are stored, event titles, descriptions, attendees, locations, and meeting metadata are discarded immediately and never written to the database
- **Availability computation pipeline** that generates waking-hour candidate windows, filters non-working days by user preference, subtracts live calendar busy blocks, applies minimum duration filters, and returns clean free slots
- **Structured JSON logging** via structlog with automatic request correlation, end-to-end latency measurement, and context binding that threads `request_id` and `user_id` through every log line in a request
- **Kubernetes-ready** with distinct liveness and readiness probes, multi-stage Docker builds, and fail-fast startup validation that rejects misconfigured deployments before they receive traffic
- **Explicit task state machine** with dedicated transition endpoints for starting, completing, and archiving tasks rather than a generic PATCH that puts state logic in the client
- **Strict typed boundaries** at every layer: Pydantic v2 models for all request and response shapes, typed exceptions that map to typed HTTP error responses, and a typed user context that route handlers receive directly from dependency injection
- **Per-user data isolation** enforced at the repository layer, not just at the API layer, so no code path can accidentally read or write another user's data
- **Abstract calendar integration interface** that makes adding Apple Calendar and Microsoft Outlook a matter of implementing one class without touching any service or repository code
- Built as the foundation for AI scheduling engines, prioritization systems, autonomous orchestration pipelines, and intelligent calendar negotiation

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Architecture](#architecture)
3. [Authentication and User Context](#authentication-and-user-context)
4. [User Profiles and Preferences](#user-profiles-and-preferences)
5. [Task Management](#task-management)
6. [Calendar Integration](#calendar-integration)
7. [Availability Computation](#availability-computation)
8. [Observability and Logging](#observability-and-logging)
9. [Error Handling](#error-handling)
10. [Requirements](#requirements)
11. [Installation](#installation)
12. [Quick Start](#quick-start)
13. [API Reference](#api-reference)
14. [Configuration](#configuration)
15. [Docker and Kubernetes](#docker-and-kubernetes)
16. [Testing](#testing)
17. [Development](#development)
18. [Project Structure](#project-structure)
19. [Design Decisions Worth Noting](#design-decisions-worth-noting)
20. [Future Expansion](#future-expansion)

---

## What It Does

ORDIN handles the infrastructure layer that intelligent scheduling systems need but rarely get built well. The core product question is: given everything a user has to do and every commitment already on their calendar, what should they work on next, and when can they realistically fit it in? Answering that question cleanly requires solving several distinct infrastructure problems simultaneously.

**Authentication that disappears.** Route handlers should not have to think about tokens. They receive a typed `UserContext` object from dependency injection and work with it directly. Token verification, expiry checking, and context extraction happen entirely in the middleware layer.

**Tasks with real semantics.** A task is not just a row in a database. It has a domain, a deadline, an effort estimate, an importance score, and a status that moves through a defined set of transitions. The API models these transitions explicitly rather than accepting arbitrary status patches.

**Calendar data without privacy violations.** Connecting a user's calendar to a productivity system is sensitive. ORDIN pulls event data from Google Calendar during sync, extracts the time range of each event, and immediately discards everything else. The scheduling engine needs to know that Monday at 2pm is busy. It does not need to know that the meeting is called "Performance Review" or who is attending.

**Availability that is actually usable.** The availability computation endpoint is the interface between the backend and the AI scheduling layer. Given a time window and a minimum slot duration, it returns a list of free slots that a scheduling engine can use to place new work. This computation accounts for the user's waking hours, their preferred working days, and all current calendar busy blocks.

**Infrastructure that is observable in production.** Every request produces a structured log line with the request ID, user ID, method, path, status code, and latency. Every error response carries the request ID. A support engineer looking at a production issue can take the request ID from the error response, filter the logs by it, and see exactly what happened in sequence.

A typical request lifecycle looks like this:

1. A Firebase ID token arrives in the `Authorization: Bearer` header
2. The request ID middleware reads `X-Request-ID` from the header or generates a UUID if absent, and binds it to the request context
3. The authentication middleware verifies the token signature and expiry using the Firebase Admin SDK, extracts a `UserContext`, and binds the `user_id` to the logging context
4. The route handler receives the verified `UserContext` via dependency injection and calls the appropriate service method
5. The service calls the repository layer, which scopes all Firestore queries to the authenticated user's UID
6. The response is serialized through a Pydantic v2 output schema
7. The logging middleware emits a structured JSON log line with all context, including the end-to-end latency in milliseconds

Every piece of that flow is deterministic, typed, and observable.

---

## Architecture

ORDIN is organized into four horizontal layers. Dependencies flow strictly downward: the API layer calls the service layer, the service layer calls the repository layer, and the repository layer calls external systems. No layer skips another. No layer holds a reference to a layer above it.

```
Client
   │
   ▼
FastAPI API Layer
   │
   ├── Authentication Middleware    (token verification, UserContext injection)
   ├── Request Context Middleware   (X-Request-ID propagation and binding)
   ├── Structured Logging Middleware (request/response log lines, latency)
   └── Global Exception Handler    (typed exceptions to typed HTTP responses)
   │
   ▼
Service Layer
   │
   ├── User Service      (profile management, preferences, onboarding state)
   ├── Task Service      (task lifecycle, status transitions, bulk operations)
   └── Calendar Service  (OAuth flows, provider sync, availability computation)
   │
   ▼
Repository Layer
   │
   ├── User Repository      (Firestore user profile reads and writes)
   ├── Task Repository      (Firestore per-user task collection operations)
   └── Calendar Repository  (Firestore busy block storage and retrieval)
   │
   ▼
External Systems
   ├── Firebase Auth        (ID token verification via Admin SDK)
   ├── Google Calendar      (OAuth 2.0, event list, push notifications)
   └── Firestore            (primary document database)
```

### The API layer

The API layer's only job is to accept HTTP requests, validate their shape, call the appropriate service method, and return a typed response. Route handlers are intentionally thin. Business logic does not live here. State machines do not live here. The route handler receives validated inputs and a typed user context, calls one service method, and returns the result.

The middleware stack runs before any route handler and after every response. The request ID middleware runs first, ensuring the ID is available to everything downstream. The authentication middleware runs next, so any route that depends on a verified user context can rely on it being present. The logging middleware wraps the entire request, measuring the time from first byte to last byte.

### The service layer

Services contain the business logic of the application. The user service handles profile creation, preference updates, and onboarding state. The task service handles the rules around valid state transitions and enforces constraints like preventing completion of an archived task. The calendar service handles the OAuth exchange, the translation from raw calendar events to stored busy blocks, and the availability computation algorithm.

Services depend on repositories through constructor injection. They do not hold Firestore references directly. This makes services testable in isolation by swapping in a mock repository.

### The repository layer

Repositories are the only layer that talks to Firestore. They translate between domain objects and Firestore document representations. All Firestore access is scoped to the authenticated user's UID. A task repository method never accepts a query that could return another user's tasks: the user ID is always a required parameter and always part of the Firestore path.

The Firestore document paths follow a consistent convention:

```
users/{uid}/profile
users/{uid}/tasks/{task_id}
users/{uid}/calendar_integrations/{provider}
users/{uid}/busy_blocks/{block_id}
```

This path structure means Firestore security rules can enforce user isolation at the database level as a second line of defense behind the application-level enforcement in the repository layer.

### Design principles applied throughout

**Typed domain boundaries.** Every interface between layers uses Pydantic v2 models. There are no untyped dictionaries crossing layer boundaries anywhere in the codebase. This makes refactoring safe, makes the data contracts explicit and visible in code, and means Pydantic validation catches malformed data the moment it crosses a boundary rather than when it eventually causes a downstream failure.

**Dependency injection.** FastAPI's dependency injection system is used for authentication context, database client access, and service instantiation. This keeps route handlers free of initialization logic and makes the dependency graph explicit and testable.

**Fail-fast configuration.** The `pydantic-settings` configuration class validates all required environment variables at startup. If a required variable is missing or has an invalid value, the service raises an error and exits before accepting any traffic. This is strictly better than a service that starts successfully with a missing `FIREBASE_PROJECT_ID` and fails on the first authenticated request.

---

## Authentication and User Context

Authentication is the first concern in every request that touches user data. ORDIN uses Firebase Authentication because it handles token signing, key rotation, expiry enforcement, and token revocation without any application-level code to maintain.

### How authentication works

The client application authenticates directly with Firebase using any supported method (email and password, Google Sign-In, Apple Sign-In, etc.) and receives a short-lived Firebase ID token. This token is a JWT signed by Firebase's private key. The client includes it in every API request as `Authorization: Bearer <token>`.

The ORDIN authentication middleware:

1. Extracts the token from the `Authorization` header
2. Calls the Firebase Admin SDK's `verify_id_token()`, which checks the signature, the issuer, the audience, and the expiry
3. Extracts the verified claims from the decoded token
4. Constructs a `UserContext` from the claims
5. Stores the `UserContext` in the request state for downstream access
6. Binds the `user_id` to the structlog context so all subsequent log lines for this request carry the user ID automatically

If any step fails, the middleware returns a 401 response immediately and the route handler is never called.

### UserContext model

```python
class UserContext(BaseModel):
    uid: str
    email: Optional[str]
    email_verified: bool
    auth_time: Optional[datetime]
```

The `uid` field is the Firebase user identifier, a stable unique string that never changes for a given user regardless of how they sign in. All Firestore data is keyed on this UID.

### Using authentication in route handlers

Route handlers declare their need for an authenticated user through a typed dependency:

```python
@router.get("/profile")
async def get_profile(user: CurrentUserDep):
    return await user_service.get_profile(user.uid)

@router.post("/tasks")
async def create_task(body: CreateTaskRequest, user: CurrentUserDep):
    return await task_service.create(user.uid, body)
```

`CurrentUserDep` is a FastAPI dependency that reads the `UserContext` from request state. The route handler receives a fully verified, typed user context with no boilerplate. If the middleware rejected the token, this route handler never runs.

---

## User Profiles and Preferences

Every authenticated user has a profile stored in Firestore. The profile is created on first access using a lazy initialization pattern and updated through dedicated PATCH endpoints.

### Profile model

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

The `schema_version` field supports forward-compatible migrations. If the profile schema changes in a future version, the repository layer can detect old versions and apply a migration before returning the profile to the service layer. Clients always receive the current schema regardless of when the profile was originally created.

### Preferences

User preferences feed directly into the availability computation. They encode the user's working patterns:

```python
UserPreferences:
    working_days: list[int]            # 0 = Monday through 6 = Sunday
    work_start_hour: int               # Hour of day when work begins
    work_end_hour: int                 # Hour of day when work ends
    timezone: str                      # IANA timezone identifier e.g. "America/New_York"
    focus_block_duration_minutes: int  # Preferred minimum block for deep work
```

These preferences are the primary input to the availability computation pipeline alongside the calendar busy blocks. A user who works Tuesday through Saturday from 9am to 6pm in Tokyo will get availability slots that correctly reflect those constraints regardless of what timezone the server is running in.

### Onboarding

The onboarding flow is tracked as a boolean on the profile. Once the client signals completion via `POST /api/v1/users/me/onboarding/complete`, the flag is set and the backend can use it to gate certain behaviors or apply post-onboarding defaults. Separating this state from the profile update endpoint means the onboarding transition is a first-class event that can be logged semantically and extended with side effects without changing client code.

---

## Task Management

Tasks are the primary domain object. Each task belongs to a single user and carries the metadata that a scheduling engine needs to reason about it: what domain the work belongs to, when it is due, how long it will take, and how important it is relative to other tasks.

### Task model

```python
Task:
    task_id: str
    user_id: str
    title: str
    description: str | None
    domain: TaskDomain               # work, personal, health, learning, etc.
    deadline: datetime
    effort_estimate_minutes: int | None
    importance: int                  # 1 to 5
    constraints: TaskConstraints | None
    status: TaskStatus               # pending, in_progress, completed, archived
    created_at: datetime
    updated_at: datetime
```

The `effort_estimate_minutes` field is the critical bridge between the task layer and the scheduling layer. A task with a known effort estimate and a known deadline can be placed into a specific availability slot. The AI scheduling engine uses this field to decide not just whether a task fits in a given window, but whether it fits in time for the deadline.

The `constraints` field holds scheduling constraints that a future AI engine will respect: preferred time of day for the work, blocked days, whether the task requires consecutive uninterrupted time, and similar preferences.

### Task state machine

Tasks move through a defined set of states. The valid transitions are:

```
pending ──────────────────→ in_progress   (via POST /tasks/{id}/start)
pending ──────────────────→ archived      (via POST /tasks/{id}/archive)
in_progress ──────────────→ completed     (via POST /tasks/{id}/complete)
in_progress ──────────────→ pending       (via PATCH /tasks/{id})
in_progress ──────────────→ archived      (via POST /tasks/{id}/archive)
completed ────────────────→ archived      (via POST /tasks/{id}/archive)
```

These transitions are exposed as explicit endpoints rather than a generic status PATCH. This is a deliberate design decision that puts the state machine on the server where it can be enforced consistently, audited with semantic meaning in logs, and extended with transition-specific side effects such as recording a completion timestamp or triggering a downstream notification without changing client code.

The service layer validates every transition and returns a `CONFLICT` error if the requested transition is not valid from the current state. The error response includes the current state and the reason the transition was rejected.

### Filtering and pagination

The task list endpoint supports filtering by status, domain, and deadline range, with cursor-based pagination for large task collections. All filters are applied in Firestore queries rather than in-memory, which keeps response time bounded regardless of how many tasks a user has accumulated.

### Bulk operations

The bulk status endpoint accepts a list of task IDs and a target status, and applies the transition to all of them in a single request. This supports multi-select UI patterns where a user wants to archive a batch of completed tasks at once without issuing individual requests for each one.

---

## Calendar Integration

The calendar layer is the most privacy-sensitive part of the system. It handles OAuth credential management, calendar synchronization, and the translation from raw event data to the minimal representation needed for scheduling.

### The privacy model in detail

When a user connects their Google Calendar, they are granting ORDIN read access to their calendar events. ORDIN uses this access for exactly one purpose: determining when the user is busy. The sync process works as follows:

1. Fetch events from the calendar provider for a rolling time window
2. For each event, record only the start time, end time, and free/busy status
3. Discard everything else immediately, before any data is written to Firestore

What is stored in Firestore:

```python
BusyBlock:
    block_id: str
    user_id: str
    provider: str
    start_time: datetime
    end_time: datetime
    is_all_day: bool
    created_at: datetime
```

What is never stored: event title, event description, organizer, attendee list, location, conference link, recurrence rule, event color, or any other event metadata. The system is architecturally incapable of leaking calendar content because it never persists calendar content in the first place. This is not just a policy decision enforced by code review: the `BusyBlock` schema has no fields for event metadata, so a future developer could not add event title storage without adding a new field to the schema, which would be visible and reviewable.

### OAuth flow

The calendar integration uses the standard OAuth 2.0 authorization code flow:

```
Step 1: GET /api/v1/calendar/oauth/google/initiate
        Generates a signed state parameter
        Returns the Google authorization URL

Step 2: User visits the URL and grants permission in Google's consent screen

Step 3: GET /api/v1/calendar/oauth/google/callback?code=...&state=...
        Verifies the state parameter against the signed value (CSRF protection)
        Exchanges the authorization code for access and refresh tokens
        Stores encrypted credentials in Firestore under the user's collection
        Returns success to the client
```

Stored credentials include the access token, refresh token, token type, and expiry timestamp. The calendar service handles token refresh transparently: if an access token is expired when a sync is requested, the service exchanges the refresh token for a new access token before proceeding, updates the stored credentials, and then runs the sync.

### Abstract integration interface

All calendar providers implement a common abstract interface:

```python
class CalendarIntegrationBase:
    async def get_authorization_url(self, state: str) -> str: ...
    async def exchange_code(self, code: str, state: str) -> Credentials: ...
    async def sync_events(self, credentials: Credentials, window: SyncWindow) -> list[BusyBlock]: ...
    async def refresh_credentials(self, credentials: Credentials) -> Credentials: ...
```

The calendar service calls this interface and does not know which provider it is talking to. Adding a new provider requires implementing this interface in a new class and registering it in the provider registry. No service, repository, or route handler code changes.

---

## Availability Computation

The availability endpoint is the primary interface between the ORDIN backend and the AI scheduling layer. It answers the question: given a time window, when is this user actually free to do focused work?

### Computation pipeline

The computation runs in five steps:

**Step 1: Generate candidate windows.** Starting from the beginning of the requested time range, generate a sequence of time windows that fall within the user's configured working hours. For each day in the range, a candidate window spans from `work_start_hour` to `work_end_hour` in the user's configured timezone. All time calculations use the IANA timezone from the user's preferences.

**Step 2: Filter working days.** Remove candidate windows that fall on days the user has not configured as working days. A user who works Monday through Friday will have Saturday and Sunday windows removed entirely before any further processing.

**Step 3: Subtract busy blocks.** For each remaining candidate window, retrieve all stored busy blocks that overlap with it and subtract them. A busy block from 2pm to 3pm splits a 9am-to-5pm window into two windows: 9am to 2pm and 3pm to 5pm. Overlapping busy blocks are merged before subtraction to avoid double-counting.

**Step 4: Apply minimum duration filter.** Remove any resulting windows shorter than the requested `min_duration_minutes`. A 15-minute gap between two meetings is not a useful work slot if the minimum requested duration is 30 minutes.

**Step 5: Return availability slots.** The remaining windows are returned as a sorted list of start and end time pairs with the duration of each slot in minutes.

```bash
curl -X POST http://localhost:8000/api/v1/calendar/availability \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2024-01-15T00:00:00Z",
    "end_time": "2024-01-19T00:00:00Z",
    "min_duration_minutes": 30
  }'
```

Example response:

```json
{
  "slots": [
    {
      "start": "2024-01-15T09:00:00Z",
      "end": "2024-01-15T11:30:00Z",
      "duration_minutes": 150
    },
    {
      "start": "2024-01-15T13:00:00Z",
      "end": "2024-01-15T17:00:00Z",
      "duration_minutes": 240
    },
    {
      "start": "2024-01-16T09:00:00Z",
      "end": "2024-01-16T17:00:00Z",
      "duration_minutes": 480
    }
  ]
}
```

An AI scheduling engine receiving this response can immediately evaluate whether a task requiring 90 minutes of focused work can be placed in any of these slots before its deadline. The backend has done all the work of translating raw calendar data, user timezone preferences, and working day configuration into a clean list of options. The AI layer only needs to choose among them.

---

## Observability and Logging

Production systems fail in ways that are hard to reproduce locally. The observability infrastructure in ORDIN is designed so that any production issue can be investigated entirely from logs, without needing to reproduce the failing request.

### Structured logging

Every log line is a JSON object. Human-readable console formatting is available for local development via the `ORDIN_LOG_FORMAT=console` environment variable, but the default and production format is structured JSON, which is parseable by any log aggregation system including Datadog, Splunk, CloudWatch, and Google Cloud Logging.

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

### Request ID propagation

The `X-Request-ID` header is the primary correlation mechanism. The request ID middleware reads it from incoming requests if present, allowing client-generated IDs to propagate through so a mobile app can generate an ID, include it in the request, and later search logs by that ID to see exactly what happened on the server for a specific user action. If no `X-Request-ID` is provided, a UUID v4 is generated server-side.

The ID is stored in the request context and automatically included in every log line emitted during the request via structlog's context binding. It is also included in all error responses, so the client always has a correlation handle for any error it receives.

### Latency tracing

Latency is measured by the logging middleware, which records the time when the request first enters the middleware stack and the time when the response leaves it. This end-to-end measurement includes authentication verification, service logic, repository access, and serialization. It is more useful than per-function timing for understanding user-facing performance.

Service and repository methods emit their own log lines for operations that are expected to be slow (Firestore writes, external API calls) so unusually high latency can be traced to its source by reading the sequence of log lines for the request ID.

### Health probes

Two separate health endpoints serve distinct purposes and map to distinct Kubernetes probe types.

`GET /health` is the liveness probe. It returns 200 if the process is running and responding. This probe failing causes Kubernetes to restart the pod. It should only fail if the process is genuinely unable to handle requests.

`GET /ready` is the readiness probe. It returns 200 only when all upstream dependencies (Firestore, Firebase Auth) are verified as reachable and operational. This probe failing causes Kubernetes to stop routing traffic to the pod without restarting it. This is the correct behavior during a transient Firestore unavailability event: the pod is alive and will recover, but should not receive traffic it cannot serve in the meantime.

---

## Error Handling

All errors from all routes return the same JSON structure, regardless of whether the error originated in middleware, a route handler, a service, or an unhandled exception.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "request_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

The `request_id` field is always present, even for errors that occur before authentication completes. This allows any error a client application receives to be correlated with the corresponding server-side log entry immediately.

### Error codes

| Code | HTTP Status | When it fires |
|---|---|---|
| `UNAUTHORIZED` | 401 | No `Authorization` header, or token is expired, invalid, or revoked |
| `FORBIDDEN` | 403 | Token is valid but the authenticated user lacks permission for the requested resource |
| `NOT_FOUND` | 404 | The requested task, profile, or calendar integration does not exist |
| `CONFLICT` | 409 | The requested task state transition is not valid from the current state |
| `VALIDATION_ERROR` | 422 | The request body failed Pydantic v2 validation |
| `RATE_LIMIT_EXCEEDED` | 429 | The client has exceeded the rate limit for this endpoint |
| `INTERNAL_ERROR` | 500 | An unexpected exception was raised and not caught by application logic |
| `SERVICE_UNAVAILABLE` | 503 | A required upstream dependency (Firestore, Firebase Auth) is unreachable |

### Global exception handler

A global exception handler registered at application startup catches all unhandled exceptions and converts them to typed HTTP responses. Application code raises typed exception classes (for example `TaskNotFoundError`, `InvalidStateTransitionError`, `CalendarProviderError`) and the handler maps them to the appropriate HTTP status code and error code. Route handlers never manually construct error responses, which guarantees the format is consistent across every endpoint.

Adding a new error type requires adding one typed exception class and one entry in the handler's mapping table. The response format is enforced by the handler, not by convention scattered across route files.

---

## Requirements

### System requirements

- Python 3.11 or 3.12
- pip or uv for dependency management
- A Firebase project with Authentication and Firestore enabled
- A Google Cloud project with the Calendar API enabled and OAuth 2.0 credentials configured for the redirect URI
- Docker if running in a container

### Technical stack

| Layer | Technology | Why |
|---|---|---|
| API framework | FastAPI | Async-native, Pydantic v2 integration, automatic OpenAPI generation |
| Validation | Pydantic v2 | Strict typing, nested model validation, clean serialization |
| Authentication | Firebase Auth via Admin SDK | Managed token infrastructure, no key rotation to handle |
| Database | Firestore | Document model maps naturally to per-user collections with path-based isolation |
| Structured logging | structlog | Context binding, JSON output by default, async-compatible |
| ASGI server | Uvicorn | Production-grade async Python server with graceful shutdown |
| Containerization | Docker | Multi-stage builds, reproducible production environments |
| Deployment target | Kubernetes | Health probes, horizontal scaling, rolling deployments |

---

## Installation

```bash
git clone <repo-url>
cd ORDIN

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
```

Edit `.env` before starting the server. The minimum required variables are the Firebase project ID, the path to a Firebase service account credentials file, and the Google OAuth client credentials. The server will refuse to start with a clear error message if any required variable is absent.

### Development dependencies

```bash
pip install -r requirements-dev.txt
```

Development dependencies include pytest, pytest-asyncio, pytest-cov, httpx (for the FastAPI TestClient), black, isort, ruff, and mypy.

---

## Quick Start

### Start the development server

```bash
# With auto-reload on file changes
python run.py --reload

# Or directly with uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at `http://localhost:8000`. Interactive Swagger documentation is at `http://localhost:8000/docs`. ReDoc documentation is at `http://localhost:8000/redoc`.

### Verify the server is running

```bash
curl http://localhost:8000/health
# {"status": "ok"}

curl http://localhost:8000/ready
# {"status": "ok", "dependencies": {"firestore": "ok", "firebase_auth": "ok"}}
```

### Create a task

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer <firebase_id_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Complete project proposal",
    "domain": "work",
    "deadline": "2026-01-15T17:00:00Z",
    "importance": 4,
    "effort_estimate_minutes": 90
  }'
```

### Compute availability

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

### List tasks with filtering

```bash
curl "http://localhost:8000/api/v1/tasks?status=pending&domain=work&limit=20" \
  -H "Authorization: Bearer <firebase_id_token>"
```

### Start the OAuth flow for Google Calendar

```bash
curl "http://localhost:8000/api/v1/calendar/oauth/google/initiate" \
  -H "Authorization: Bearer <firebase_id_token>"
# Returns the Google authorization URL to redirect the user to
```

---

## API Reference

### Health endpoints

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| `GET` | `/health` | No | Liveness probe: returns 200 if the process is running |
| `GET` | `/ready` | No | Readiness probe: returns 200 if all dependencies are reachable |

### User profile endpoints

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| `GET` | `/api/v1/users/me/profile` | Yes | Get the authenticated user's full profile including preferences |
| `PATCH` | `/api/v1/users/me/profile` | Yes | Update profile fields such as display name |
| `PATCH` | `/api/v1/users/me/preferences` | Yes | Update scheduling preferences (working hours, timezone, working days) |
| `POST` | `/api/v1/users/me/onboarding/complete` | Yes | Mark the onboarding flow as complete |
| `DELETE` | `/api/v1/users/me/profile` | Yes | Delete the profile and all associated tasks, busy blocks, and integrations |

### Task endpoints

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| `POST` | `/api/v1/tasks` | Yes | Create a new task |
| `GET` | `/api/v1/tasks` | Yes | List tasks with optional filtering by status, domain, and deadline range |
| `GET` | `/api/v1/tasks/{task_id}` | Yes | Get a specific task by ID |
| `PATCH` | `/api/v1/tasks/{task_id}` | Yes | Update task fields (title, description, deadline, effort estimate) |
| `DELETE` | `/api/v1/tasks/{task_id}` | Yes | Permanently delete a task |
| `POST` | `/api/v1/tasks/{task_id}/start` | Yes | Transition a pending task to in-progress |
| `POST` | `/api/v1/tasks/{task_id}/complete` | Yes | Mark an in-progress task as completed |
| `POST` | `/api/v1/tasks/{task_id}/archive` | Yes | Archive a task regardless of its current status |
| `POST` | `/api/v1/tasks/bulk/status` | Yes | Update the status of multiple tasks in a single request |

### Calendar endpoints

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| `GET` | `/api/v1/calendar/oauth/{provider}/initiate` | Yes | Start the OAuth flow, returns authorization URL |
| `GET` | `/api/v1/calendar/oauth/{provider}/callback` | No | Receive OAuth callback, exchange code, store credentials |
| `GET` | `/api/v1/calendar/integrations` | Yes | List all currently connected calendar integrations |
| `POST` | `/api/v1/calendar/{provider}/sync` | Yes | Pull latest events from the provider, update busy blocks |
| `DELETE` | `/api/v1/calendar/{provider}` | Yes | Disconnect a calendar, revoke tokens, and delete stored credentials |
| `POST` | `/api/v1/calendar/availability` | Yes | Compute available time slots within a requested window |

### Interactive documentation

| Interface | URL | Description |
|---|---|---|
| Swagger UI | `http://localhost:8000/docs` | Interactive API explorer with request builder and example responses |
| ReDoc | `http://localhost:8000/redoc` | Clean, readable reference documentation |
| OpenAPI JSON | `http://localhost:8000/openapi.json` | Machine-readable schema for client generation |

---

## Configuration

All environment variables use the `ORDIN_` prefix. Configuration is managed through a `pydantic-settings` class that validates all values at startup using type annotations and validators. The service exits immediately with a clear error message naming the missing variable if required configuration is absent.

### Core settings

| Variable | Type | Default | Description |
|---|---|---|---|
| `ORDIN_ENV` | string | `dev` | Runtime environment: `dev`, `staging`, or `prod` |
| `ORDIN_DEBUG` | bool | `false` | Enable debug mode, verbose error details, auto-reload in uvicorn |
| `ORDIN_HOST` | string | `0.0.0.0` | Bind host for the Uvicorn server |
| `ORDIN_PORT` | int | `8000` | Bind port for the Uvicorn server |
| `ORDIN_LOG_LEVEL` | string | `info` | Minimum log level: `debug`, `info`, `warning`, `error` |
| `ORDIN_LOG_FORMAT` | string | `json` | Log format: `json` for production, `console` for local development |

### Firebase settings

| Variable | Type | Required | Description |
|---|---|---|---|
| `ORDIN_FIREBASE_PROJECT_ID` | string | Yes | Firebase project identifier |
| `ORDIN_FIREBASE_CREDENTIALS_PATH` | string | Yes | Absolute path to the service account JSON credentials file |

### Google Calendar OAuth settings

| Variable | Type | Required | Description |
|---|---|---|---|
| `ORDIN_GOOGLE_OAUTH_CLIENT_ID` | string | Yes | OAuth 2.0 client ID from Google Cloud Console |
| `ORDIN_GOOGLE_OAUTH_CLIENT_SECRET` | string | Yes | OAuth 2.0 client secret |
| `ORDIN_GOOGLE_OAUTH_REDIRECT_URI` | string | Yes | Callback URL, must match exactly what is registered in Google Cloud Console |

---

## Docker and Kubernetes

### Building the image

```bash
docker build -t ordin-backend:latest .
```

The Dockerfile uses a two-stage build. The first stage installs all dependencies including build-time tools. The second stage copies only the application code and installed packages into a clean Python base image. The production image does not contain pip, build tools, or any package not required at runtime, which keeps the image size small and the attack surface minimal.

### Running with Docker

```bash
docker run -p 8000:8000 \
  -e ORDIN_ENV=prod \
  -e ORDIN_FIREBASE_PROJECT_ID=your-project-id \
  -e ORDIN_FIREBASE_CREDENTIALS_PATH=/secrets/firebase.json \
  -v /path/to/credentials:/secrets:ro \
  ordin-backend:latest
```

### Kubernetes deployment

ORDIN is designed for Kubernetes deployment from the start. The liveness and readiness probes are distinct and serve different purposes:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 2
```

The liveness probe failing causes the pod to be restarted, which is appropriate when the process has entered a broken state. The readiness probe failing causes traffic to be rerouted to healthy pods without restarting the current one, which is appropriate during a transient Firestore unavailability event. Using the same endpoint for both probes would cause unnecessary pod restarts during upstream outages.

For production deployments, Firebase credentials should be mounted from a Kubernetes secret rather than passed as environment variables:

```yaml
volumes:
  - name: firebase-credentials
    secret:
      secretName: ordin-firebase-credentials
volumeMounts:
  - name: firebase-credentials
    mountPath: /secrets
    readOnly: true
```

---

## Testing

### Running tests

```bash
# All tests
pytest

# With HTML coverage report
pytest --cov=app --cov-report=html

# A specific test file with verbose output
pytest tests/test_tasks.py -v

# Stop on first failure
pytest -x
```

### Test structure

| File | What it covers |
|---|---|
| `conftest.py` | Shared fixtures: FastAPI TestClient, mock Firebase Admin SDK, mock Firestore client, test UserContext, helper functions for creating test tasks and profiles |
| `test_auth.py` | Token verification with valid token, expired token, malformed token, missing header, revoked token; UserContext injection; user_id in log output |
| `test_health.py` | Liveness probe returns 200, readiness probe with all dependencies healthy, readiness probe returns 503 when Firestore is unreachable |
| `test_exceptions.py` | Global handler catches each exception type, correct HTTP status for each error code, request_id present in all error responses, unhandled exceptions become 500 |
| `test_user_profile.py` | Profile lazy creation on first access, profile retrieval, PATCH updates, preference updates, schema_version migration, onboarding completion flag, profile deletion cascades |
| `test_tasks.py` | Task creation, list with status filter, list with domain filter, pagination cursor, single task retrieval, field updates, all valid state transitions succeed, all invalid state transitions return 409, bulk status update, task not found returns 404 |
| `test_calendar.py` | OAuth initiation returns URL with state, callback verifies state, callback stores credentials, sync stores only BusyBlock fields, sync discards event title and description, token refresh on expired credentials, availability with no busy blocks, availability with overlapping busy blocks merged, minimum duration filter removes short windows |

### Testing philosophy

The test suite mocks Firebase Auth and Firestore at the client level, not at the service level. This means the tests exercise the full request lifecycle from HTTP request through middleware, route handler, service, and repository, stopping at the external service boundary. Integration bugs between layers are caught by tests rather than discovered in production.

Every test that requires authentication uses a test `UserContext` fixture injected via FastAPI's dependency override mechanism. This exercises the same dependency injection path that production code uses without requiring real Firebase tokens in the test environment.

---

## Development

### Code quality tools

```bash
black app tests        # Auto-format code to consistent style
isort app tests        # Sort and group imports correctly
ruff check app tests   # Fast linting, catches common mistakes
mypy app               # Static type checking across the entire application
```

All four tools are expected to pass with no warnings. A CI pipeline runs them in sequence on every pull request before any tests are run.

### Adding a new API endpoint

1. Add the route handler to the appropriate file in `app/api/v1/`, keeping it thin: validate inputs, call one service method, return the result
2. Define request and response Pydantic v2 models in `app/models/` with complete type annotations
3. Add the business logic to the appropriate service in `app/services/`
4. Add any required Firestore operations to the appropriate repository in `app/repositories/`, scoped to the user's UID
5. Add the typed exception class to `app/core/exceptions.py` and its mapping to `app/core/handlers.py` if a new error type is needed
6. Add tests covering the happy path, authentication rejection, validation failure, and all domain-specific error cases
7. Verify mypy, ruff, black, and isort pass

### Adding a new calendar provider

1. Create `app/integrations/calendar/your_provider.py`
2. Implement all methods of `CalendarIntegrationBase` defined in `app/integrations/calendar/base.py`
3. Register the provider in the provider registry in `app/integrations/calendar/__init__.py`
4. Add the required OAuth environment variables to `app/config/settings.py` with appropriate validation
5. Add the new variables to `.env.example` with documentation comments
6. Add integration tests in `tests/test_calendar.py` covering the full OAuth flow and sync pipeline for the new provider

No changes to the calendar service, repository, or any route handler are required.

---

## Project Structure

```
app/
├── __init__.py
├── main.py                          # FastAPI application factory, middleware and router registration
│
├── api/
│   ├── health.py                    # GET /health and GET /ready endpoints
│   └── v1/
│       ├── users.py                 # User profile and preference routes
│       ├── tasks.py                 # Full task lifecycle routes
│       └── calendar.py              # OAuth, sync, and availability routes
│
├── auth/
│   ├── context.py                   # UserContext Pydantic model
│   ├── dependencies.py              # CurrentUserDep FastAPI dependency
│   ├── firebase.py                  # Firebase Admin SDK initialization and lifecycle
│   └── middleware.py                # ID token verification middleware
│
├── config/
│   └── settings.py                  # pydantic-settings configuration with startup validation
│
├── core/
│   ├── context.py                   # Request context (request ID storage and binding)
│   ├── dependencies.py              # Shared FastAPI dependencies used across routers
│   ├── exceptions.py                # Typed exception hierarchy (TaskNotFoundError, etc.)
│   ├── handlers.py                  # Global exception handler registration
│   └── logging.py                   # structlog configuration, JSON formatter, context binding
│
├── db/
│   └── firestore.py                 # Firestore async client initialization and connection lifecycle
│
├── integrations/
│   └── calendar/
│       ├── base.py                  # CalendarIntegrationBase abstract class
│       └── google.py                # Google Calendar OAuth and sync implementation
│
├── middleware/
│   ├── logging.py                   # Request/response logging middleware with latency measurement
│   └── request_id.py                # X-Request-ID extraction, generation, and context binding
│
├── models/
│   ├── task.py                      # Task, TaskStatus, TaskDomain, TaskConstraints
│   ├── calendar.py                  # BusyBlock, CalendarIntegration, AvailabilitySlot, Credentials
│   └── user.py                      # UserProfile, UserPreferences, OnboardingState
│
├── repositories/
│   ├── user_repository.py           # Firestore user profile CRUD operations
│   ├── task_repository.py           # Firestore task CRUD with filtering and pagination
│   └── calendar_repository.py       # Firestore busy block storage, retrieval, and cleanup
│
├── services/
│   ├── user_service.py              # User profile and preference business logic
│   ├── task_service.py              # Task lifecycle management and state machine enforcement
│   └── calendar_service.py          # OAuth flow, provider sync pipeline, availability computation
│
└── schemas/
    └── responses.py                 # Shared response envelope, error schema, pagination schema

tests/
├── conftest.py                      # Shared fixtures, mock infrastructure, test utilities
├── test_auth.py
├── test_health.py
├── test_exceptions.py
├── test_user_profile.py
├── test_tasks.py
└── test_calendar.py
```

---

## Design Decisions Worth Noting

**Why Firebase Auth rather than a custom JWT implementation?** Firebase Auth handles token signing, key rotation, expiry enforcement, and revocation without any application-level maintenance. Building equivalent infrastructure that is correct under all edge cases including clock skew, key rotation during active sessions, and token replay attacks is weeks of careful work and an ongoing operational burden. The tradeoff is a dependency on Google's identity infrastructure, which is acceptable given Firestore is already in the stack and adding a second Google dependency does not meaningfully increase operational risk.

**Why Firestore rather than PostgreSQL?** Firestore's document model maps naturally to per-user collections with hierarchical path-based isolation. The Firestore path `users/{uid}/tasks/{task_id}` means Security Rules can enforce user isolation at the database level as a second line of defense behind the repository-level enforcement. For a workload dominated by per-user reads and writes with no cross-user joins required in the current phase, the document model is a strong fit. A relational database would be a better choice if the scheduling engine eventually needs aggregate queries across users or complex multi-table joins, which would require revisiting the storage layer at that point.

**Why are task state transitions explicit endpoints rather than a generic PATCH on the status field?** A generic `PATCH /tasks/{id}` accepting `{"status": "completed"}` puts the state machine in the client: every client has to know which transitions are valid from which states and enforce them locally. Explicit transition endpoints put the valid state machine on the server, where it is enforced consistently for every client, can be logged with semantic meaning (a `task.completed` event is more useful for analytics than a `task.updated` event), and can later be extended with transition-specific side effects like recording a completion timestamp, updating a streak counter, or triggering a notification without any client code changes.

**Why structlog rather than the Python standard library logging module?** The standard library logger is designed for line-oriented human-readable output and retrofitting it for structured JSON logging with request-scoped context binding requires significant configuration and ongoing discipline. structlog is built for structured output with context binding as a first-class feature: calling `log.bind(request_id=req_id, user_id=uid)` once binds those fields to all subsequent log calls in that context automatically. This is the right model for request-scoped observability and it is difficult to replicate cleanly without it.

**Why abstract the calendar integration behind an interface?** The `CalendarIntegrationBase` abstract class creates a clean extension point. Without it, the calendar service would contain `if provider == "google"` branches that need to be updated for every new provider. With the abstraction, the service calls the interface and the provider registry resolves the concrete implementation. Adding Apple Calendar or Outlook is a matter of implementing the interface in a new module. The service, repository, and route handler code does not change.

**Why fail fast on missing configuration rather than applying defaults?** A service that starts with a missing or defaulted `FIREBASE_PROJECT_ID` will appear healthy to Kubernetes and its load balancer until the first authenticated request arrives, at which point every request will fail with a cryptic error. A service that refuses to start and prints a clear message naming the missing variable surfaces the misconfiguration at deploy time rather than at request time. This makes deployments safer and incidents shorter.

**Why measure latency in the middleware rather than in route handlers?** Measuring latency per route handler misses the cost of middleware execution, request parsing, response serialization, and any overhead that occurs before or after the handler runs. Middleware-level measurement captures the full user-facing latency for every request consistently, with no risk of accidentally omitting the measurement from a newly added route.

---

## Future Expansion

ORDIN is deliberately built as a foundation layer. The current system handles authentication, task management, calendar integration, and availability computation cleanly. The availability computation endpoint in particular is designed as the primary interface point for an AI scheduling engine.

**AI scheduling engine.** The availability endpoint provides the free slot list a scheduling algorithm needs. The task model provides the deadline, effort estimate, and importance score it needs to evaluate each task. The engine would receive pending tasks and available slots and output a proposed schedule, which the backend would then persist and surface to the client.

**Prioritization system.** A ranking service that evaluates all pending tasks by urgency (deadline minus effort relative to now), importance, and domain balance. The task model already carries the fields this calculation requires.

**Autonomous rescheduling.** When a new calendar event is added via sync or a task's deadline changes, automatically trigger re-evaluation of affected tasks. This requires a calendar change webhook listener and a rescheduling orchestration layer that calls availability computation and the scheduling engine in sequence.

**Notification system.** Push notifications for approaching deadlines, newly opened availability slots that match pending high-priority tasks, and daily schedule summaries.

**Adaptive effort estimation.** Track actual time spent on completed tasks by recording the duration between task start and completion timestamps. Compare to the original `effort_estimate_minutes` and build per-user, per-domain correction factors that improve scheduling accuracy over time.

**Intelligent calendar negotiation.** For tasks that require coordination with other participants, a negotiation layer that queries availability across multiple ORDIN users and proposes meeting times that respect everyone's working preferences without revealing their calendar content to each other.

---

## License

MIT. See LICENSE for details.
