"""
Unit Tests for Unknown Senders Workflow
---------------------------------------
Tests for build_known_senders_cache and scan_unknown_senders_for_delete.
"""

from unittest.mock import Mock, patch

import pytest

from app.core import state
from app.services.gmail.delete import (
    build_known_senders_cache,
    get_delete_scan_results,
    get_known_senders_status,
    scan_unknown_senders_for_delete,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset state before each test."""
    state.reset_delete_scan()
    state.reset_known_senders()
    yield
    state.reset_delete_scan()
    state.reset_known_senders()


class TestBuildKnownSendersCache:
    """Tests for build_known_senders_cache function."""

    def test_negative_limit(self):
        """Negative limit should set error."""
        build_known_senders_cache(limit=-1)
        status = get_known_senders_status()
        assert status["error"] == "Limit cannot be negative"
        assert status["done"] is True

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_auth_error(self, mock_get_service):
        """Auth error should set error status."""
        mock_get_service.return_value = (None, "Auth failed")

        build_known_senders_cache(limit=100)

        status = get_known_senders_status()
        assert status["error"] == "Auth failed"
        assert status["done"] is True

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_empty_sent_folder(self, mock_get_service):
        """Empty sent folder should complete without error."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        mock_list = Mock()
        mock_list.execute.return_value = {"messages": []}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        build_known_senders_cache(limit=100)

        status = get_known_senders_status()
        assert status["done"] is True
        assert status["message"] == "No sent emails found"
        assert status["sender_count"] == 0

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_recipient_extraction(self, mock_get_service):
        """Should extract recipients from To header."""
        sent_messages = [
            {
                "id": "sent1",
                "payload": {
                    "headers": [
                        {"name": "To", "value": "contact@example.com"},
                    ]
                },
            }
        ]

        self._setup_mock_service(mock_get_service, sent_messages)
        build_known_senders_cache(limit=100)

        known_senders = state.get_known_senders()
        assert "contact@example.com" in known_senders

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_multiple_recipients(self, mock_get_service):
        """Should extract multiple recipients from sent emails."""
        sent_messages = [
            {
                "id": "sent1",
                "payload": {
                    "headers": [
                        {
                            "name": "To",
                            "value": "contact1@example.com, contact2@example.com",
                        },
                        {"name": "Cc", "value": "cc@example.com"},
                    ]
                },
            }
        ]

        self._setup_mock_service(mock_get_service, sent_messages)
        build_known_senders_cache(limit=100)

        known_senders = state.get_known_senders()
        assert "contact1@example.com" in known_senders
        assert "contact2@example.com" in known_senders
        assert "cc@example.com" in known_senders

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_lowercase_set_return(self, mock_get_service):
        """Should return lowercase set of contacts."""
        sent_messages = [
            {
                "id": "sent1",
                "payload": {
                    "headers": [
                        {"name": "To", "value": "CONTACT@EXAMPLE.COM"},
                    ]
                },
            }
        ]

        self._setup_mock_service(mock_get_service, sent_messages)
        build_known_senders_cache(limit=100)

        known_senders = state.get_known_senders()
        assert "contact@example.com" in known_senders

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_missing_headers_handling(self, mock_get_service):
        """Should handle messages with missing To/Cc/Bcc headers."""
        sent_messages = [
            {
                "id": "sent1",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "No recipients header"},
                    ]
                },
            },
            {
                "id": "sent2",
                "payload": {
                    "headers": [
                        {"name": "To", "value": "valid@example.com"},
                    ]
                },
            },
        ]

        self._setup_mock_service(mock_get_service, sent_messages)
        build_known_senders_cache(limit=100)

        known_senders = state.get_known_senders()
        # Should still get the valid recipient
        assert "valid@example.com" in known_senders

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_status_updates(self, mock_get_service):
        """Should update status during build."""
        sent_messages = [
            {
                "id": "sent1",
                "payload": {
                    "headers": [
                        {"name": "To", "value": "contact@example.com"},
                    ]
                },
            }
        ]

        self._setup_mock_service(mock_get_service, sent_messages)
        build_known_senders_cache(limit=100)

        status = get_known_senders_status()
        assert status["done"] is True
        assert status["progress"] == 100
        assert status["sender_count"] == 1

    def _setup_mock_service(self, mock_get_service, messages):
        """Set up mock Gmail service."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": msg["id"]} for msg in messages]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                for i, msg in enumerate(messages):
                    callback(str(i), msg, None)

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch
        return mock_service


class TestScanUnknownSendersForDelete:
    """Tests for scan_unknown_senders_for_delete function."""

    def test_negative_limit(self):
        """Negative limit should set error."""
        scan_unknown_senders_for_delete(limit=-1)
        status = state.delete_scan_status
        assert status["error"] == "Limit cannot be negative"
        assert status["done"] is True

    def test_cache_not_built_error(self):
        """Should error if known senders cache not built."""
        scan_unknown_senders_for_delete(limit=100)
        status = state.delete_scan_status
        assert "cache not built" in status["error"].lower()
        assert status["done"] is True

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_case_insensitive_filtering(self, mock_get_service):
        """Should filter known senders case-insensitively."""
        # Set up known senders cache with lowercase
        state.set_known_senders({"known@example.com"})

        inbox_messages = [
            {
                "id": "inbox1",
                "payload": {
                    "headers": [
                        {
                            "name": "From",
                            "value": "KNOWN@EXAMPLE.COM",
                        },  # Different case
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "From known (different case)"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "inbox2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "unknown@spam.com"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "From unknown"},
                    ]
                },
                "sizeEstimate": 1000,
            },
        ]

        self._setup_mock_service(mock_get_service, inbox_messages)
        scan_unknown_senders_for_delete(limit=100)

        results = get_delete_scan_results()
        # Only unknown sender should appear
        assert len(results) == 1
        assert results[0]["email"] == "unknown@spam.com"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_all_known_empty_results(self, mock_get_service):
        """All known senders should result in empty results."""
        state.set_known_senders({"known1@example.com", "known2@example.com"})

        inbox_messages = [
            {
                "id": "inbox1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "known1@example.com"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "From known 1"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "inbox2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "known2@example.com"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "From known 2"},
                    ]
                },
                "sizeEstimate": 1000,
            },
        ]

        self._setup_mock_service(mock_get_service, inbox_messages)
        scan_unknown_senders_for_delete(limit=100)

        results = get_delete_scan_results()
        assert len(results) == 0

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_mixed_known_unknown(self, mock_get_service):
        """Should correctly filter mix of known and unknown senders."""
        state.set_known_senders({"contact1@example.com", "contact2@example.com"})

        inbox_messages = [
            # Known
            {
                "id": "inbox1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "contact1@example.com"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "Known"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            # Unknown
            {
                "id": "inbox2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "spam@unknown.com"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "Unknown 1"},
                    ]
                },
                "sizeEstimate": 2000,
            },
            # Unknown (same sender)
            {
                "id": "inbox3",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "spam@unknown.com"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "Unknown 2"},
                    ]
                },
                "sizeEstimate": 2000,
            },
            # Known (different case)
            {
                "id": "inbox4",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "CONTACT2@EXAMPLE.COM"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "Known uppercase"},
                    ]
                },
                "sizeEstimate": 1000,
            },
        ]

        self._setup_mock_service(mock_get_service, inbox_messages)
        scan_unknown_senders_for_delete(limit=100)

        results = get_delete_scan_results()
        assert len(results) == 1
        assert results[0]["email"] == "spam@unknown.com"
        assert results[0]["count"] == 2  # Both unknown emails from same sender

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_status_shows_skipped_count(self, mock_get_service):
        """Status should show how many known senders were skipped."""
        state.set_known_senders({"known@example.com"})

        inbox_messages = [
            {
                "id": "inbox1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "known@example.com"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "Known"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "inbox2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "unknown@example.com"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "Unknown"},
                    ]
                },
                "sizeEstimate": 1000,
            },
        ]

        self._setup_mock_service(mock_get_service, inbox_messages)
        scan_unknown_senders_for_delete(limit=100)

        status = state.delete_scan_status
        assert status["done"] is True
        assert "skipped" in status["message"].lower()

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_auth_error(self, mock_get_service):
        """Auth error should set error status."""
        state.set_known_senders({"known@example.com"})
        mock_get_service.return_value = (None, "Auth failed")

        scan_unknown_senders_for_delete(limit=100)

        status = state.delete_scan_status
        assert status["error"] == "Auth failed"
        assert status["done"] is True

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_no_emails_found(self, mock_get_service):
        """No emails should complete with appropriate message."""
        state.set_known_senders({"known@example.com"})

        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        mock_list = Mock()
        mock_list.execute.return_value = {"messages": []}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        scan_unknown_senders_for_delete(limit=100)

        status = state.delete_scan_status
        assert status["done"] is True
        assert "no emails" in status["message"].lower()

    def _setup_mock_service(self, mock_get_service, messages):
        """Set up mock Gmail service."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": msg["id"]} for msg in messages]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                for i, msg in enumerate(messages):
                    callback(str(i), msg, None)

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch
        return mock_service
