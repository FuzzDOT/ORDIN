#!/usr/bin/env python3
"""
ORDIN Backend - Development Server Runner
==========================================
Convenience script for running the development server.

Usage:
    python run.py                    # Default: localhost:8000
    python run.py --port 8080        # Custom port
    python run.py --reload           # Auto-reload on code changes
    
For production, use:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

import argparse
import sys

import uvicorn

from app.config import get_settings


def main() -> int:
    """Run the development server with CLI argument support."""
    parser = argparse.ArgumentParser(
        description="Run the ORDIN backend development server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host to bind to (defaults to config value)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind to (defaults to config value)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker processes",
    )

    args = parser.parse_args()

    # Load settings (fail-fast on misconfiguration)
    try:
        settings = get_settings()
    except Exception as e:
        print(f"ERROR: Configuration validation failed: {e}", file=sys.stderr)
        return 1

    # Determine runtime configuration
    host = args.host or settings.host
    port = args.port or settings.port
    workers = args.workers or settings.workers
    reload = args.reload or settings.is_development

    print(f"Starting ORDIN backend server...")
    print(f"  Environment: {settings.env.value}")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Workers: {workers}")
    print(f"  Reload: {reload}")
    print(f"  Debug: {settings.debug}")
    print()

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,  # Reload requires single worker
        log_level=settings.log_level.lower(),
        access_log=False,  # Handled by our middleware
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
