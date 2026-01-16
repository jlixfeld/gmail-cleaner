# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install dependencies
uv sync

# Run the application (opens at http://localhost:8766)
uv run python main.py

# Run with Docker
docker compose up --build

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/services/gmail/test_scan.py

# Run with coverage
uv run pytest --cov=app --cov-report=html

# Lint and format
uv run ruff check .
uv run ruff format .
```

## Architecture

### Overview

FastAPI backend serving a vanilla JS frontend. Long-running Gmail operations execute in background tasks while frontend polls `/api/status` endpoints for progress.

```
Frontend (static/js/)     →  FastAPI API (app/api/)  →  Services (app/services/)
    ↓                              ↓                            ↓
HTTP/JSON polling         Routes & Background Tasks      Gmail API + State
```

### Key Components

- **`main.py`**: Entry point - checks credentials, starts uvicorn server
- **`app/main.py`**: FastAPI app factory, mounts static files and routers
- **`app/api/actions.py`**: POST endpoints (scan, delete, sign-in, unsubscribe, etc.)
- **`app/api/status.py`**: GET endpoints for polling operation progress
- **`app/core/state.py`**: Thread-safe global state with locks for concurrent operations
- **`app/services/auth.py`**: OAuth 2.0 flow (desktop vs web auth modes)
- **`app/services/gmail/`**: Gmail API operations (scan, delete, mark_read, unsubscribe, labels, etc.)

### State Management

`AppState` class in `app/core/state.py` holds all operation state (scan results, progress, auth status). All state access is protected by locks for thread safety. Operations run as background tasks and update state; frontend polls status endpoints.

### Gmail API Pattern

Uses batch requests (100 operations per HTTP call) for performance:
1. List message IDs with Gmail query
2. Batch-fetch message details
3. Process in callback functions
4. Update state with progress

### Authentication Modes

- **Desktop (`WEB_AUTH=false`)**: Auto-opens browser via `InstalledAppFlow.run_local_server()`
- **Web/Docker (`WEB_AUTH=true`)**: Prints OAuth URL to logs, user copies to browser

### Environment Variables

- `WEB_AUTH`: Enable web-based auth mode (default: false)
- `OAUTH_HOST`: Custom host for OAuth redirect (default: localhost)
- `OAUTH_EXTERNAL_PORT`: External port when using Docker port mapping
- `PORT`: Server port (default: 8766)

## Test Structure

Tests mirror source structure under `tests/unit/`:
- `tests/unit/api/` - API endpoint tests
- `tests/unit/services/auth/` - OAuth and authentication tests
- `tests/unit/services/gmail/` - Gmail service tests
- `tests/unit/models/` - Pydantic schema tests

`conftest.py` provides fixtures including `client` (TestClient), sample email headers, and auto-mocks for Gmail auth to prevent browser opening during tests.

## Key Files to Know

- `app/core/config.py`: Settings via pydantic-settings, auto-detects `/app/data` for token persistence in Docker
- `app/services/gmail/helpers.py`: Gmail query building and email header parsing utilities
- `app/core/database.py`: SQLite database for valid senders/recipients management
