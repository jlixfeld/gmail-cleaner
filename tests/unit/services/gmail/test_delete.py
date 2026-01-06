"""
Tests for Gmail Delete Operations
---------------------------------
Tests for delete.py - scanning senders and deleting emails.
"""

from unittest.mock import Mock, patch

import pytest

from app.core import state
from app.services.gmail.delete import (
    scan_senders_for_delete,
    get_delete_scan_status,
    get_delete_scan_results,
    delete_emails_by_sender,
    delete_emails_bulk,
    delete_emails_bulk_background,
    get_delete_bulk_status,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset state before each test."""
    state.reset_delete_scan()
    state.reset_delete_bulk()
    yield
    state.reset_delete_scan()
    state.reset_delete_bulk()


class TestScanSendersForDelete:
    """Tests for scan_senders_for_delete function."""

    def test_invalid_limit_negative(self):
        """Negative limit should set error and return early."""
        scan_senders_for_delete(limit=-10)
        status = get_delete_scan_status()
        assert status["error"] == "Limit cannot be negative"
        assert status["done"] is True

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_auth_error(self, mock_get_service):
        """Auth error should set error status."""
        mock_get_service.return_value = (None, "Authentication failed")

        scan_senders_for_delete(limit=100)

        status = get_delete_scan_status()
        assert status["error"] == "Authentication failed"
        assert status["done"] is True

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_no_emails_found(self, mock_get_service):
        """Empty result should set appropriate message."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock the chained API calls
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": []}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        scan_senders_for_delete(limit=100)

        status = get_delete_scan_status()
        assert status["message"] == "No emails found"
        assert status["done"] is True
        assert status["error"] is None

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_successful_scan(self, mock_get_service):
        """Successful scan should return grouped senders with correct counts."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock list to return message IDs
        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}, {"id": "msg3"}]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        # Prepare mock message responses - 2 from sender1, 1 from sender2
        mock_messages = [
            {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender1@example.com"},
                        {"name": "Subject", "value": "Subject 1"},
                        {"name": "Date", "value": "Mon, 01 Jan 2024 10:00:00 +0000"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "msg2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender1@example.com"},
                        {"name": "Subject", "value": "Subject 2"},
                        {"name": "Date", "value": "Tue, 02 Jan 2024 10:00:00 +0000"},
                    ]
                },
                "sizeEstimate": 2000,
            },
            {
                "id": "msg3",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender2@example.com"},
                        {"name": "Subject", "value": "Subject 3"},
                        {"name": "Date", "value": "Wed, 03 Jan 2024 10:00:00 +0000"},
                    ]
                },
                "sizeEstimate": 500,
            },
        ]

        # Mock batch request to invoke callback with each message
        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                for i, msg in enumerate(mock_messages):
                    callback(str(i), msg, None)

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch

        scan_senders_for_delete(limit=10)

        status = get_delete_scan_status()
        assert status["done"] is True
        assert status["error"] is None

        # Verify scan results
        results = get_delete_scan_results()
        assert len(results) == 2  # 2 unique senders

        # Results should be sorted by count (descending)
        assert results[0]["email"] == "sender1@example.com"
        assert results[0]["count"] == 2
        assert results[0]["total_size"] == 3000  # 1000 + 2000

        assert results[1]["email"] == "sender2@example.com"
        assert results[1]["count"] == 1
        assert results[1]["total_size"] == 500

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_exception_handling(self, mock_get_service):
        """Exceptions should be caught and set error status."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock list to raise exception
        mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = Exception(
            "API Error"
        )

        scan_senders_for_delete(limit=100)

        status = get_delete_scan_status()
        assert status["error"] == "API Error"
        assert status["done"] is True

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_limit_zero_scans_all(self, mock_get_service):
        """limit=0 should scan all emails without limit."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Return 600 messages (more than single page)
        page1 = {
            "messages": [{"id": f"msg{i}"} for i in range(500)],
            "nextPageToken": "token1",
        }
        page2 = {"messages": [{"id": f"msg{i}"} for i in range(500, 600)]}

        mock_list = Mock()
        mock_list.execute.side_effect = [page1, page2]
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        # Mock batch with simple messages
        messages = [
            {
                "id": f"msg{i}",
                "payload": {
                    "headers": [{"name": "From", "value": "sender@example.com"}]
                },
                "sizeEstimate": 100,
            }
            for i in range(600)
        ]
        batch_idx = [0]

        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                batch_size = 100
                start = batch_idx[0]
                end = min(start + batch_size, len(messages))
                for i in range(start, end):
                    callback(str(i), messages[i], None)
                batch_idx[0] = end

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch

        scan_senders_for_delete(limit=0)  # 0 means scan all

        status = get_delete_scan_status()
        assert status["done"] is True
        results = get_delete_scan_results()
        assert results[0]["count"] == 600

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_pagination_multiple_pages(self, mock_get_service):
        """Should handle multiple pages of results."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # First page with nextPageToken
        page1 = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}],
            "nextPageToken": "token123",
        }
        # Second page without nextPageToken
        page2 = {"messages": [{"id": "msg3"}]}

        mock_list = Mock()
        mock_list.execute.side_effect = [page1, page2]
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        messages = [
            {
                "id": "msg1",
                "payload": {"headers": [{"name": "From", "value": "s@e.com"}]},
                "sizeEstimate": 100,
            },
            {
                "id": "msg2",
                "payload": {"headers": [{"name": "From", "value": "s@e.com"}]},
                "sizeEstimate": 100,
            },
            {
                "id": "msg3",
                "payload": {"headers": [{"name": "From", "value": "s@e.com"}]},
                "sizeEstimate": 100,
            },
        ]

        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                for i, msg in enumerate(messages):
                    callback(str(i), msg, None)

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch

        scan_senders_for_delete(limit=100)

        results = get_delete_scan_results()
        assert results[0]["count"] == 3

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_malformed_from_header(self, mock_get_service):
        """Should handle malformed From headers gracefully."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        mock_list = Mock()
        mock_list.execute.return_value = {"messages": [{"id": "msg1"}]}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        # Malformed From header (missing angle brackets)
        messages = [
            {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "malformed-email (Bad Format)"}
                    ]
                },
                "sizeEstimate": 100,
            }
        ]

        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                for i, msg in enumerate(messages):
                    callback(str(i), msg, None)

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch

        scan_senders_for_delete(limit=10)

        status = get_delete_scan_status()
        assert status["done"] is True
        assert status["error"] is None
        results = get_delete_scan_results()
        assert len(results) == 1

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_missing_headers(self, mock_get_service):
        """Should handle messages with missing headers."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        mock_list = Mock()
        mock_list.execute.return_value = {"messages": [{"id": "msg1"}, {"id": "msg2"}]}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        messages = [
            # Missing From header
            {
                "id": "msg1",
                "payload": {"headers": [{"name": "Subject", "value": "Test"}]},
                "sizeEstimate": 100,
            },
            # Normal message
            {
                "id": "msg2",
                "payload": {
                    "headers": [{"name": "From", "value": "sender@example.com"}]
                },
                "sizeEstimate": 100,
            },
        ]

        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                for i, msg in enumerate(messages):
                    callback(str(i), msg, None)

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch

        scan_senders_for_delete(limit=10)

        status = get_delete_scan_status()
        assert status["done"] is True
        results = get_delete_scan_results()
        # Should have results (Unknown sender from missing header + normal sender)
        assert len(results) >= 1

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_domain_extraction_verified(self, mock_get_service):
        """Domain field should be correctly extracted from sender email."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        mock_list = Mock()
        mock_list.execute.return_value = {"messages": [{"id": "msg1"}, {"id": "msg2"}]}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        messages = [
            {
                "id": "msg1",
                "payload": {"headers": [{"name": "From", "value": "user@example.com"}]},
                "sizeEstimate": 100,
            },
            {
                "id": "msg2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "news@subdomain.company.co.uk"}
                    ]
                },
                "sizeEstimate": 100,
            },
        ]

        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                for i, msg in enumerate(messages):
                    callback(str(i), msg, None)

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch

        scan_senders_for_delete(limit=10)

        results = get_delete_scan_results()
        domains = {r["domain"] for r in results}
        assert "example.com" in domains
        assert "subdomain.company.co.uk" in domains

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_recipients_extracted(self, mock_get_service):
        """Recipients field should be populated from To/Cc/Bcc headers."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        mock_list = Mock()
        mock_list.execute.return_value = {"messages": [{"id": "msg1"}]}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        messages = [
            {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "To", "value": "recipient@gmail.com"},
                    ]
                },
                "sizeEstimate": 100,
            }
        ]

        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                for i, msg in enumerate(messages):
                    callback(str(i), msg, None)

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch

        scan_senders_for_delete(limit=10)

        results = get_delete_scan_results()
        assert len(results) == 1
        assert "recipients" in results[0]
        assert "recipient@gmail.com" in results[0]["recipients"]


class TestDeleteEmailsBySender:
    """Tests for delete_emails_by_sender function."""

    def test_empty_sender(self):
        """Empty sender should return error."""
        result = delete_emails_by_sender("")
        assert result["success"] is False
        assert result["message"] == "No sender or list_id specified"

    def test_whitespace_sender(self):
        """Whitespace-only sender should return error."""
        result = delete_emails_by_sender("   ")
        assert result["success"] is False
        assert result["message"] == "No sender or list_id specified"

    def test_invalid_sender_format(self):
        """Invalid sender format should return error."""
        result = delete_emails_by_sender("not-an-email")
        assert result["success"] is False
        assert "Invalid sender format" in result["message"]

    def test_invalid_sender_with_operators(self):
        """Sender with query operators should be rejected (unless quoted)."""
        # This tests our input validation - the value itself is validated before use
        result = delete_emails_by_sender("test OR admin@example.com")
        assert result["success"] is False
        assert "Invalid sender format" in result["message"]

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_valid_email_format_queries_gmail(self, mock_get_service):
        """Valid email should query Gmail directly for message IDs."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to return no emails
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": []}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        result = delete_emails_by_sender("user@example.com")
        assert result["success"] is True
        assert result["message"] == "No emails found"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_valid_email_no_emails_from_gmail(self, mock_get_service):
        """When Gmail returns no emails, should return success with 0 deleted."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to return empty
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": []}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        result = delete_emails_by_sender("user@example.com")
        assert result["success"] is True
        assert result["message"] == "No emails found"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_valid_domain_queries_gmail(self, mock_get_service):
        """Valid domain should query Gmail directly for message IDs."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to return no emails
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": []}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        result = delete_emails_by_sender("example.com")
        assert result["success"] is True
        assert result["message"] == "No emails found"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_auth_error(self, mock_get_service):
        """Auth error should return failure."""
        mock_get_service.return_value = (None, "Auth failed")

        result = delete_emails_by_sender("user@example.com")

        assert result["success"] is False
        assert result["message"] == "Auth failed"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_successful_delete(self, mock_get_service):
        """Successful delete should query Gmail and delete found emails."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to return 5 emails
        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": f"msg{i}"} for i in range(5)]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        # Mock batch modify
        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        result = delete_emails_by_sender("sender@example.com")

        assert result["success"] is True
        assert result["deleted"] == 5
        assert "Moved 5 emails to trash" in result["message"]

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_delete_with_many_messages(self, mock_get_service):
        """Delete should handle batching of many messages from Gmail."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to return 150 emails
        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": f"msg{i}"} for i in range(150)]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        # Mock batch modify
        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        result = delete_emails_by_sender("sender@example.com")

        assert result["success"] is True
        assert result["deleted"] == 150

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_delete_updates_cached_results(self, mock_get_service):
        """Delete should remove sender from cached results."""
        # Set up cached results (no message_ids - we query Gmail now)
        state.set_delete_scan_results(
            [
                {
                    "email": "keep@example.com",
                    "count": 5,
                    "total_size": 500,
                },
                {
                    "email": "delete@example.com",
                    "count": 10,
                    "total_size": 1000,
                },
            ]
        )

        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to return emails
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": [{"id": "d1"}, {"id": "d2"}]}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        delete_emails_by_sender("delete@example.com")

        results = get_delete_scan_results()
        assert len(results) == 1
        assert results[0]["email"] == "keep@example.com"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_delete_by_list_id(self, mock_get_service):
        """Delete should work with list_id for mailing lists."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Set up scan results with list_id (for subscription scan)
        state.scan_results = [
            {
                "email": "sender@example.com",
                "list_id": "test.lists.example.org",
                "count": 5,
                "total_size": 5000,
            }
        ]

        # Mock messages.list to return 5 emails
        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": f"msg{i}"} for i in range(5)]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        result = delete_emails_by_sender("", list_id="test.lists.example.org")

        assert result["success"] is True
        assert result["deleted"] == 5
        assert "Moved 5 emails to trash" in result["message"]

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_delete_by_list_id_queries_and_deletes(self, mock_get_service):
        """Delete by list_id should query Gmail and delete found emails."""
        # Set up subscription scan results (where list_id entries live)
        state.scan_results = [
            {
                "email": "sender@example.com",
                "list_id": "delete.lists.example.org",
                "count": 10,
            }
        ]

        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to return emails
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": [{"id": "d1"}, {"id": "d2"}]}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        result = delete_emails_by_sender("", list_id="delete.lists.example.org")

        assert result["success"] is True
        assert result["deleted"] == 2

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_list_id_queries_gmail(self, mock_get_service):
        """Delete with list_id should query Gmail directly."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Set up subscription scan results
        state.scan_results = [
            {
                "email": "sender@example.com",
                "list_id": "test.lists.example.org",
                "count": 5,
            }
        ]

        # Mock messages.list to return no emails
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": []}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        result = delete_emails_by_sender("", list_id="test.lists.example.org")

        assert result["success"] is True
        assert result["message"] == "No emails found"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_exception_handling(self, mock_get_service):
        """Exceptions should be caught and returned as error."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to raise exception
        mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = Exception(
            "API Error"
        )

        result = delete_emails_by_sender("sender@example.com")

        assert result["success"] is False
        assert result["message"] == "API Error"

    def test_domain_pattern_validation(self):
        """Valid domain patterns should be accepted for format validation."""
        # Test input validation only - invalid patterns should fail
        result_invalid = delete_emails_by_sender("not-valid")
        assert "Invalid sender format" in result_invalid["message"]

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_sender_case_preserved_in_query(self, mock_get_service):
        """Sender should be passed to Gmail query as provided."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": []}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        delete_emails_by_sender("UPPER@example.com")

        # Verify the query was made
        mock_service.users.return_value.messages.return_value.list.assert_called()


class TestDeleteEmailsBulk:
    """Tests for delete_emails_bulk function."""

    def test_empty_senders_list(self):
        """Empty senders list should return error."""
        result = delete_emails_bulk([])
        assert result["success"] is False
        assert result["message"] == "No senders specified"

    @patch("app.services.gmail.delete.delete_emails_by_sender")
    def test_all_successful(self, mock_delete):
        """All successful deletes should return combined counts."""
        mock_delete.side_effect = [
            {"success": True, "deleted": 5, "size_freed": 1000, "message": "ok"},
            {"success": True, "deleted": 10, "size_freed": 2000, "message": "ok"},
        ]

        result = delete_emails_bulk(["sender1@example.com", "sender2@example.com"])

        assert result["success"] is True
        assert result["deleted"] == 15
        assert result["size_freed"] == 3000

    @patch("app.services.gmail.delete.delete_emails_by_sender")
    def test_partial_failure(self, mock_delete):
        """Partial failure should report errors but still count successes."""
        mock_delete.side_effect = [
            {"success": True, "deleted": 5, "size_freed": 1000, "message": "ok"},
            {"success": False, "deleted": 0, "size_freed": 0, "message": "Auth error"},
        ]

        result = delete_emails_bulk(["sender1@example.com", "sender2@example.com"])

        assert result["success"] is True  # At least one succeeded
        assert result["deleted"] == 5
        assert "Errors:" in result["message"]

    @patch("app.services.gmail.delete.delete_emails_by_sender")
    def test_all_failed(self, mock_delete):
        """All failures should report total failure."""
        mock_delete.side_effect = [
            {"success": False, "deleted": 0, "size_freed": 0, "message": "Error 1"},
            {"success": False, "deleted": 0, "size_freed": 0, "message": "Error 2"},
        ]

        result = delete_emails_bulk(["sender1@example.com", "sender2@example.com"])

        assert result["success"] is False
        assert result["deleted"] == 0

    @patch("app.services.gmail.delete.delete_emails_by_sender")
    def test_no_emails_found_for_any(self, mock_delete):
        """No emails found for any sender should report appropriately."""
        mock_delete.side_effect = [
            {"success": True, "deleted": 0, "size_freed": 0, "message": "No emails"},
            {"success": True, "deleted": 0, "size_freed": 0, "message": "No emails"},
        ]

        result = delete_emails_bulk(["sender1@example.com", "sender2@example.com"])

        assert result["success"] is False
        assert result["message"] == "No emails found to delete"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_delete_multiple_senders_same_domain(self, mock_get_service):
        """Should correctly delete multiple senders from the same domain."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Set up scan results (for cache cleanup)
        state.set_delete_scan_results(
            [
                {
                    "email": "sender1@same-domain.com",
                    "domain": "same-domain.com",
                    "count": 2,
                    "total_size": 2000,
                },
                {
                    "email": "sender2@same-domain.com",
                    "domain": "same-domain.com",
                    "count": 3,
                    "total_size": 3000,
                },
            ]
        )

        # Mock messages.list to return different counts for each sender
        mock_list = Mock()
        mock_list.execute.side_effect = [
            {"messages": [{"id": "s1a"}, {"id": "s1b"}]},  # 2 for sender1
            {
                "messages": [{"id": "s2a"}, {"id": "s2b"}, {"id": "s2c"}]
            },  # 3 for sender2
        ]
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        result = delete_emails_bulk(
            ["sender1@same-domain.com", "sender2@same-domain.com"]
        )

        assert result["success"] is True
        assert result["deleted"] == 5  # 2 + 3
        assert result["size_freed"] == 5000  # 2000 + 3000

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_delete_removes_all_from_cache(self, mock_get_service):
        """All specified senders should be removed from cache after delete."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        state.set_delete_scan_results(
            [
                {
                    "email": "delete1@example.com",
                    "domain": "example.com",
                    "count": 1,
                    "total_size": 1000,
                },
                {
                    "email": "delete2@example.com",
                    "domain": "example.com",
                    "count": 1,
                    "total_size": 1000,
                },
                {
                    "email": "keep@other.com",
                    "domain": "other.com",
                    "count": 1,
                    "total_size": 1000,
                },
            ]
        )

        # Mock messages.list
        mock_list = Mock()
        mock_list.execute.side_effect = [
            {"messages": [{"id": "d1"}]},  # for delete1
            {"messages": [{"id": "d2"}]},  # for delete2
        ]
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        delete_emails_bulk(["delete1@example.com", "delete2@example.com"])

        results = get_delete_scan_results()
        assert len(results) == 1
        assert results[0]["email"] == "keep@other.com"


class TestDeleteEmailsBulkBackground:
    """Tests for delete_emails_bulk_background function."""

    def test_empty_senders_list(self):
        """Empty senders list should set error status."""
        delete_emails_bulk_background([])

        status = get_delete_bulk_status()
        assert status["error"] == "No senders specified"
        assert status["done"] is True

    def test_none_senders(self):
        """None senders should set error status."""
        delete_emails_bulk_background(None)

        status = get_delete_bulk_status()
        assert status["error"] == "No senders specified"
        assert status["done"] is True

    def test_invalid_senders_type(self):
        """Invalid senders type should set error status."""
        delete_emails_bulk_background("not-a-list")

        status = get_delete_bulk_status()
        assert status["error"] == "No senders specified"
        assert status["done"] is True

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_auth_error(self, mock_get_service):
        """Auth error should set error status."""
        mock_get_service.return_value = (None, "Auth failed")

        delete_emails_bulk_background(["sender@example.com"])

        status = get_delete_bulk_status()
        assert status["error"] == "Auth failed"
        assert status["done"] is True

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_no_emails_found(self, mock_get_service):
        """No emails found from Gmail should complete without error."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to return empty
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": []}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        delete_emails_bulk_background(["sender@example.com"])

        status = get_delete_bulk_status()
        assert status["done"] is True
        assert status["message"] == "No emails found to delete"
        assert status["progress"] == 100

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_successful_bulk_delete(self, mock_get_service):
        """Successful bulk delete should query Gmail and delete found emails."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to return 10 emails
        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": f"msg{i}"} for i in range(10)]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        # Mock batch modify
        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        delete_emails_bulk_background(["sender@example.com"])

        status = get_delete_bulk_status()
        assert status["done"] is True
        assert status["deleted_count"] == 10
        assert status["progress"] == 100
        assert "Successfully deleted" in status["message"]

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_updates_cached_results(self, mock_get_service):
        """Bulk delete should remove senders from cached results."""
        state.set_delete_scan_results(
            [
                {
                    "email": "keep@example.com",
                    "count": 5,
                    "total_size": 500,
                },
                {
                    "email": "delete@example.com",
                    "count": 10,
                    "total_size": 1000,
                },
            ]
        )

        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list to return emails
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": [{"id": "d1"}, {"id": "d2"}]}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        delete_emails_bulk_background(["delete@example.com"])

        results = get_delete_scan_results()
        assert len(results) == 1
        assert results[0]["email"] == "keep@example.com"


class TestStatusFunctions:
    """Tests for status retrieval functions."""

    def test_get_delete_scan_status_returns_copy(self):
        """get_delete_scan_status should return a copy."""
        state.update_delete_scan_status(message="Test")
        status1 = get_delete_scan_status()
        status2 = get_delete_scan_status()

        status1["message"] = "Modified"
        assert status2["message"] == "Test"

    def test_get_delete_scan_results_returns_copy(self):
        """get_delete_scan_results should return a copy."""
        state.set_delete_scan_results([{"email": "test@example.com"}])
        results1 = get_delete_scan_results()
        results2 = get_delete_scan_results()

        results1.append({"email": "new@example.com"})
        assert len(results2) == 1

    def test_get_delete_bulk_status_returns_copy(self):
        """get_delete_bulk_status should return a copy."""
        state.update_delete_bulk_status(message="Test")
        status1 = get_delete_bulk_status()
        status2 = get_delete_bulk_status()

        status1["message"] = "Modified"
        assert status2["message"] == "Test"
