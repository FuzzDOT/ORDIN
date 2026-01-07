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

## Project Structure

```
app/
├── __init__.py              # Package root
├── main.py                  # FastAPI application factory
├── api/
│   ├── __init__.py
│   └── health.py            # Health check endpoints
├── config/
│   ├── __init__.py
│   └── settings.py          # Pydantic BaseSettings configuration
├── core/
│   ├── __init__.py
│   ├── context.py           # Request context (request_id)
│   ├── dependencies.py      # Dependency injection providers
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

See [.env.example](.env.example) for all available options.

## Logging

All logs are structured JSON with automatic context enrichment:

```json
{
  "timestamp": "2026-01-06T12:00:00.000Z",
  "level": "info",
  "event": "Request completed",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "method": "GET",
  "path": "/api/v1/tasks",
  "status_code": 200,
  "latency_ms": 45.23,
  "service": "ordin-backend",
  "version": "0.1.0",
  "environment": "prod"
}
```

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
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | Operation conflicts with existing state |
| `SERVICE_UNAVAILABLE` | 503 | External dependency unavailable |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

## Future Integration Points

This skeleton is prepared for:

- **Firebase Authentication**: User context placeholder in `app/core/dependencies.py`
- **Database**: Readiness check placeholder in `app/api/health.py`
- **External Services**: Service availability checks in readiness probe
- **Business Logic**: API router mounting in `app/main.py`

## License

MIT
