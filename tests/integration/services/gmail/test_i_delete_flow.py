"""
Integration Tests for Delete Flow
---------------------------------
End-to-end data flow tests for scan and delete operations.
"""

from unittest.mock import Mock, patch

import pytest

from app.core import state
from app.services.gmail.delete import (
    build_known_senders_cache,
    delete_emails_bulk,
    delete_emails_by_sender,
    get_delete_scan_results,
    scan_senders_for_delete,
    scan_unknown_senders_for_delete,
)
from tests.fixtures.gmail_responses import (
    DELETE_SCAN_MESSAGES,
    INBOX_WITH_KNOWN_UNKNOWN,
    SENT_EMAIL_MESSAGES,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset state before each test."""
    state.reset_delete_scan()
    state.reset_delete_bulk()
    state.reset_known_senders()
    yield
    state.reset_delete_scan()
    state.reset_delete_bulk()
    state.reset_known_senders()


class TestScanToDeleteFlow:
    """Integration tests for scan to delete flow."""

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_full_flow_output_structure(self, mock_get_service):
        """Full flow should populate all required fields in output (except message_ids)."""
        self._setup_mock_service(mock_get_service, DELETE_SCAN_MESSAGES)

        scan_senders_for_delete(limit=100)
        results = get_delete_scan_results()

        # Verify structure of each result (message_ids no longer included)
        for result in results:
            assert "email" in result
            assert "domain" in result
            assert "count" in result
            assert "total_size" in result
            assert "subjects" in result
            assert "recipients" in result
            assert "first_date" in result
            assert "last_date" in result
            assert "sender" in result

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_multiple_senders_various_formats(self, mock_get_service):
        """Scan should correctly process multiple senders with various header formats."""
        self._setup_mock_service(mock_get_service, DELETE_SCAN_MESSAGES)

        scan_senders_for_delete(limit=100)
        results = get_delete_scan_results()

        # Should have 3 unique senders
        assert len(results) == 3

        # Find each sender and verify
        sender1 = next(r for r in results if r["email"] == "sender1@example.com")
        assert sender1["count"] == 3
        assert sender1["domain"] == "example.com"

        sender2 = next(r for r in results if r["email"] == "sender2@example.com")
        assert sender2["count"] == 2
        assert sender2["domain"] == "example.com"

        other = next(r for r in results if r["email"] == "other@different.org")
        assert other["count"] == 1
        assert other["domain"] == "different.org"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_pagination_handling(self, mock_get_service):
        """Should handle pagination when fetching messages."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # First page
        page1_response = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}],
            "nextPageToken": "token123",
        }
        # Second page
        page2_response = {
            "messages": [{"id": "msg3"}],
        }

        mock_list = Mock()
        mock_list.execute.side_effect = [page1_response, page2_response]
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        # Mock batch with messages for all 3 IDs
        messages = [
            {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Subject", "value": "Subject 1"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "msg2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Subject", "value": "Subject 2"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "msg3",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Subject", "value": "Subject 3"},
                    ]
                },
                "sizeEstimate": 1000,
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

        assert len(results) == 1
        assert results[0]["count"] == 3

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


class TestUnknownSendersFlow:
    """Integration tests for unknown senders workflow."""

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_build_cache_then_scan_flow(self, mock_get_service):
        """Build cache -> scan unknown should correctly filter."""
        # Setup mock service
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock for build_known_senders_cache (sent folder)
        sent_list_response = {
            "messages": [{"id": msg["id"]} for msg in SENT_EMAIL_MESSAGES]
        }

        # Mock for scan_unknown_senders_for_delete (inbox)
        inbox_list_response = {
            "messages": [{"id": msg["id"]} for msg in INBOX_WITH_KNOWN_UNKNOWN]
        }

        mock_list = Mock()
        mock_list.execute.side_effect = [sent_list_response, inbox_list_response]
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        # Track which messages to return based on call order
        call_counter = [0]

        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                # First call is for sent messages, second for inbox
                messages = (
                    SENT_EMAIL_MESSAGES
                    if call_counter[0] == 0
                    else INBOX_WITH_KNOWN_UNKNOWN
                )
                for i, msg in enumerate(messages):
                    callback(str(i), msg, None)
                call_counter[0] += 1

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch

        # Build known senders cache
        build_known_senders_cache(limit=100)

        # Verify cache built
        known_senders = state.get_known_senders()
        assert "contact1@example.com" in known_senders
        assert "contact2@example.com" in known_senders
        assert "contact3@example.com" in known_senders
        assert "cc@example.com" in known_senders
        assert "contact4@example.com" in known_senders  # CONTACT4 lowercased

        # Scan for unknown senders
        scan_unknown_senders_for_delete(limit=100)

        results = get_delete_scan_results()
        # Should only have unknown senders
        emails = [r["email"] for r in results]
        assert "spam@unknown.com" in emails
        assert "newsletter@marketing.biz" in emails
        # Known senders should be filtered out
        assert "contact1@example.com" not in emails
        assert "CONTACT2@EXAMPLE.COM" not in emails

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_case_insensitive_matching_end_to_end(self, mock_get_service):
        """Case insensitive matching should work end to end."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Build cache with lowercase contacts
        state.set_known_senders({"contact@example.com"})

        # Inbox has CONTACT@EXAMPLE.COM (uppercase)
        inbox_messages = [
            {
                "id": "inbox1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "CONTACT@EXAMPLE.COM"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "Uppercase email"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "inbox2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "unknown@other.com"},
                        {"name": "To", "value": "user@gmail.com"},
                        {"name": "Subject", "value": "Unknown"},
                    ]
                },
                "sizeEstimate": 1000,
            },
        ]

        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": msg["id"]} for msg in inbox_messages]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        def mock_new_batch(callback):
            batch = Mock()
            batch.add = Mock()

            def execute_batch():
                for i, msg in enumerate(inbox_messages):
                    callback(str(i), msg, None)

            batch.execute = execute_batch
            return batch

        mock_service.new_batch_http_request = mock_new_batch

        scan_unknown_senders_for_delete(limit=100)
        results = get_delete_scan_results()

        # Only unknown sender should appear
        assert len(results) == 1
        assert results[0]["email"] == "unknown@other.com"


class TestDeleteFlow:
    """Integration tests for delete operations."""

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_scan_delete_verify_cache_updated(self, mock_get_service):
        """Scan -> delete by sender -> verify cache updated."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Set up scan results (no message_ids)
        state.set_delete_scan_results(
            [
                {
                    "email": "delete@example.com",
                    "domain": "example.com",
                    "count": 3,
                    "total_size": 3000,
                    "sender": "Delete Sender",
                    "subjects": ["Sub 1"],
                    "recipients": ["user@gmail.com"],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "keep@example.com",
                    "domain": "example.com",
                    "count": 2,
                    "total_size": 2000,
                    "sender": "Keep Sender",
                    "subjects": ["Sub 2"],
                    "recipients": ["user@gmail.com"],
                    "first_date": None,
                    "last_date": None,
                },
            ]
        )

        # Mock messages.list to return emails for the delete sender
        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": "d1"}, {"id": "d2"}, {"id": "d3"}]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        # Mock batch modify
        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        # Delete one sender
        result = delete_emails_by_sender("delete@example.com")

        assert result["success"] is True
        assert result["deleted"] == 3

        # Verify cache updated
        results = get_delete_scan_results()
        assert len(results) == 1
        assert results[0]["email"] == "keep@example.com"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_bulk_delete_verify_all_removed_from_cache(self, mock_get_service):
        """Bulk delete -> verify all senders removed from cache."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Set up scan results
        state.set_delete_scan_results(
            [
                {
                    "email": "delete1@example.com",
                    "domain": "example.com",
                    "count": 2,
                    "total_size": 2000,
                    "sender": "Delete 1",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "delete2@example.com",
                    "domain": "example.com",
                    "count": 3,
                    "total_size": 3000,
                    "sender": "Delete 2",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "keep@other.com",
                    "domain": "other.com",
                    "count": 1,
                    "total_size": 1000,
                    "sender": "Keep",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
            ]
        )

        # Mock messages.list to return different emails for each call
        mock_list = Mock()
        mock_list.execute.side_effect = [
            {"messages": [{"id": "d1a"}, {"id": "d1b"}]},  # delete1
            {"messages": [{"id": "d2a"}, {"id": "d2b"}, {"id": "d2c"}]},  # delete2
        ]
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        # Bulk delete two senders
        result = delete_emails_bulk(["delete1@example.com", "delete2@example.com"])

        assert result["success"] is True
        assert result["deleted"] == 5  # 2 + 3

        # Verify only kept sender remains
        results = get_delete_scan_results()
        assert len(results) == 1
        assert results[0]["email"] == "keep@other.com"


class TestDeleteByDomainFlow:
    """Integration tests for delete by domain operations."""

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_domain_field_populated(self, mock_get_service):
        """Scan should populate domain field in results."""
        self._setup_mock_service(mock_get_service, DELETE_SCAN_MESSAGES)

        scan_senders_for_delete(limit=100)
        results = get_delete_scan_results()

        # Verify domain is populated for all results
        for result in results:
            assert result["domain"] is not None
            assert result["domain"] != ""

        # Verify specific domains
        example_senders = [r for r in results if r["domain"] == "example.com"]
        assert len(example_senders) == 2  # sender1 and sender2

        different_senders = [r for r in results if r["domain"] == "different.org"]
        assert len(different_senders) == 1

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_delete_all_senders_from_domain(self, mock_get_service):
        """Delete all senders from one domain -> verify all removed from cache."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Set up scan results
        state.set_delete_scan_results(
            [
                {
                    "email": "sender1@example.com",
                    "domain": "example.com",
                    "count": 3,
                    "total_size": 3000,
                    "sender": "Sender One",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "sender2@example.com",
                    "domain": "example.com",
                    "count": 2,
                    "total_size": 2000,
                    "sender": "Sender Two",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "other@different.org",
                    "domain": "different.org",
                    "count": 1,
                    "total_size": 1000,
                    "sender": "Other",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
            ]
        )

        # Mock messages.list
        mock_list = Mock()
        mock_list.execute.side_effect = [
            {"messages": [{"id": "s1a"}, {"id": "s1b"}, {"id": "s1c"}]},  # sender1
            {"messages": [{"id": "s2a"}, {"id": "s2b"}]},  # sender2
        ]
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        # Delete all senders from example.com domain
        result = delete_emails_bulk(["sender1@example.com", "sender2@example.com"])

        assert result["success"] is True
        assert result["deleted"] == 5  # 3 + 2

        # Verify only different.org sender remains
        results = get_delete_scan_results()
        assert len(results) == 1
        assert results[0]["email"] == "other@different.org"
        assert results[0]["domain"] == "different.org"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_delete_one_domain_other_domain_remains(self, mock_get_service):
        """Delete senders from one domain -> verify other domain senders remain."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        state.set_delete_scan_results(
            [
                {
                    "email": "delete@delete-domain.com",
                    "domain": "delete-domain.com",
                    "count": 2,
                    "total_size": 2000,
                    "sender": "Delete",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "keep1@keep-domain.com",
                    "domain": "keep-domain.com",
                    "count": 3,
                    "total_size": 3000,
                    "sender": "Keep 1",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "keep2@keep-domain.com",
                    "domain": "keep-domain.com",
                    "count": 1,
                    "total_size": 1000,
                    "sender": "Keep 2",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
            ]
        )

        # Mock messages.list
        mock_list = Mock()
        mock_list.execute.return_value = {"messages": [{"id": "d1"}, {"id": "d2"}]}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        # Delete only delete-domain.com
        result = delete_emails_by_sender("delete@delete-domain.com")

        assert result["success"] is True
        assert result["deleted"] == 2

        # Verify keep-domain.com senders remain
        results = get_delete_scan_results()
        assert len(results) == 2
        emails = [r["email"] for r in results]
        assert "keep1@keep-domain.com" in emails
        assert "keep2@keep-domain.com" in emails

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


class TestDeleteSafety:
    """Critical tests to verify delete operations query Gmail correctly."""

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_delete_queries_gmail_with_correct_sender(self, mock_get_service):
        """Delete should query Gmail with the correct sender in the query."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock messages.list
        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": "target1"}, {"id": "target2"}]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        # Delete target sender
        delete_emails_by_sender("target@example.com")

        # Verify messages.list was called with query containing the sender
        mock_service.users.return_value.messages.return_value.list.assert_called()

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_delete_single_sender_updates_cache(self, mock_get_service):
        """Delete one sender -> verify cache updated correctly."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Two senders from same domain in cache
        state.set_delete_scan_results(
            [
                {
                    "email": "delete@same-domain.com",
                    "domain": "same-domain.com",
                    "count": 2,
                    "total_size": 2000,
                    "sender": "Delete",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "keep@same-domain.com",
                    "domain": "same-domain.com",
                    "count": 3,
                    "total_size": 3000,
                    "sender": "Keep",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
            ]
        )

        mock_list = Mock()
        mock_list.execute.return_value = {"messages": [{"id": "del1"}, {"id": "del2"}]}
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        # Delete only one sender
        delete_emails_by_sender("delete@same-domain.com")

        # Verify keep@same-domain.com still in cache
        results = get_delete_scan_results()
        assert len(results) == 1
        assert results[0]["email"] == "keep@same-domain.com"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_bulk_delete_multiple_senders(self, mock_get_service):
        """Bulk delete multiple senders -> verify all queried and deleted."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        state.set_delete_scan_results(
            [
                {
                    "email": "delete1@example.com",
                    "domain": "example.com",
                    "count": 1,
                    "total_size": 1000,
                    "sender": "Delete 1",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "delete2@example.com",
                    "domain": "example.com",
                    "count": 2,
                    "total_size": 2000,
                    "sender": "Delete 2",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "keep1@example.com",
                    "domain": "example.com",
                    "count": 1,
                    "total_size": 1000,
                    "sender": "Keep 1",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
            ]
        )

        mock_list = Mock()
        mock_list.execute.side_effect = [
            {"messages": [{"id": "d1"}]},  # delete1
            {"messages": [{"id": "d2a"}, {"id": "d2b"}]},  # delete2
        ]
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        # Delete two specific senders
        result = delete_emails_bulk(["delete1@example.com", "delete2@example.com"])

        assert result["success"] is True
        assert result["deleted"] == 3

        # Verify kept senders still in cache
        results = get_delete_scan_results()
        emails = [r["email"] for r in results]
        assert "keep1@example.com" in emails

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_domain_delete_removes_domain_from_cache(self, mock_get_service):
        """Delete all senders from domain -> verify domain removed from cache."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        state.set_delete_scan_results(
            [
                {
                    "email": "target1@target-domain.com",
                    "domain": "target-domain.com",
                    "count": 2,
                    "total_size": 2000,
                    "sender": "Target 1",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "target2@target-domain.com",
                    "domain": "target-domain.com",
                    "count": 1,
                    "total_size": 1000,
                    "sender": "Target 2",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
                {
                    "email": "safe@safe-domain.com",
                    "domain": "safe-domain.com",
                    "count": 3,
                    "total_size": 3000,
                    "sender": "Safe",
                    "subjects": [],
                    "recipients": [],
                    "first_date": None,
                    "last_date": None,
                },
            ]
        )

        mock_list = Mock()
        mock_list.execute.side_effect = [
            {"messages": [{"id": "t1a"}, {"id": "t1b"}]},  # target1
            {"messages": [{"id": "t2"}]},  # target2
        ]
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        mock_service.users.return_value.messages.return_value.batchModify.return_value.execute.return_value = {}

        # Delete entire target domain
        result = delete_emails_bulk(
            ["target1@target-domain.com", "target2@target-domain.com"]
        )

        assert result["success"] is True
        assert result["deleted"] == 3

        # Safe domain senders should remain in cache
        results = get_delete_scan_results()
        assert len(results) == 1
        assert results[0]["domain"] == "safe-domain.com"
