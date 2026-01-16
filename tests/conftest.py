"""
Pytest Configuration and Fixtures
"""

import os
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.core.database import init_database


@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path, request):
    """Use a temporary database for tests that need it.

    Only initializes database for tests in gmail service and delete-related tests.
    Skip for auth tests to avoid interfering with OAuth mocking.
    """
    # Skip database initialization for auth tests
    if "auth" in str(request.fspath):
        yield None
        return

    db_path = str(tmp_path / "test_gmail_cleaner.db")
    monkeypatch.setattr("app.core.database.get_db_path", lambda: db_path)
    init_database()
    yield db_path


@pytest.fixture
def client():
    """FastAPI test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_email_headers():
    """Sample email headers for testing."""
    return [
        {"name": "From", "value": "Newsletter <newsletter@example.com>"},
        {"name": "Subject", "value": "Test Email Subject"},
        {"name": "List-Unsubscribe", "value": "<https://example.com/unsubscribe>"},
    ]


@pytest.fixture
def sample_email_headers_one_click():
    """Sample email headers with one-click unsubscribe."""
    return [
        {"name": "From", "value": "Marketing <marketing@company.com>"},
        {"name": "Subject", "value": "Special Offer"},
        {"name": "List-Unsubscribe", "value": "<https://company.com/unsub?id=123>"},
        {"name": "List-Unsubscribe-Post", "value": "List-Unsubscribe=One-Click"},
    ]


@pytest.fixture(autouse=True)
def mock_gmail_auth(monkeypatch):
    """Automatically mock Gmail authentication to prevent browser opening during tests."""
    # Set environment variable to disable web auth mode (prevents browser opening)
    monkeypatch.setenv("WEB_AUTH", "false")

    # Mock file existence checks for credentials to return False (no credentials)
    # This prevents OAuth flow from starting since get_gmail_service will return early
    original_exists = os.path.exists

    def mock_exists(path):
        """Return False for credential files to prevent OAuth flow."""
        path_str = str(path)
        if "credentials.json" in path_str or "token.json" in path_str:
            return False
        return original_exists(path)

    monkeypatch.setattr("os.path.exists", mock_exists)
