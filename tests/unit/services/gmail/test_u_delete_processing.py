"""
Unit Tests for Delete Processing Logic
--------------------------------------
Tests for data processing in scan_senders_for_delete.
Focus on domain extraction, sender aggregation, and recipient extraction.
"""

from unittest.mock import Mock, patch

import pytest

from app.core import state
from app.services.gmail.delete import (
    get_delete_scan_results,
    scan_senders_for_delete,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset state before each test."""
    state.reset_delete_scan()
    yield
    state.reset_delete_scan()


class TestDomainExtraction:
    """Tests for domain extraction from sender email addresses."""

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_standard_email_domain(self, mock_get_service):
        """Standard email: user@example.com -> example.com"""
        self._setup_mock_service(
            mock_get_service,
            [
                {
                    "id": "msg1",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "user@example.com"},
                            {"name": "Subject", "value": "Test"},
                        ]
                    },
                    "sizeEstimate": 1000,
                }
            ],
        )

        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert len(results) == 1
        assert results[0]["email"] == "user@example.com"
        assert results[0]["domain"] == "example.com"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_subdomain_preserved(self, mock_get_service):
        """Subdomain should be preserved: user@mail.example.com -> mail.example.com"""
        self._setup_mock_service(
            mock_get_service,
            [
                {
                    "id": "msg1",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "user@mail.example.com"},
                            {"name": "Subject", "value": "Test"},
                        ]
                    },
                    "sizeEstimate": 1000,
                }
            ],
        )

        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert results[0]["domain"] == "mail.example.com"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_complex_subdomain(self, mock_get_service):
        """Complex subdomain: news@marketing.company.co.uk -> marketing.company.co.uk"""
        self._setup_mock_service(
            mock_get_service,
            [
                {
                    "id": "msg1",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "news@marketing.company.co.uk"},
                            {"name": "Subject", "value": "Test"},
                        ]
                    },
                    "sizeEstimate": 1000,
                }
            ],
        )

        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert results[0]["domain"] == "marketing.company.co.uk"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_plus_addressing_domain(self, mock_get_service):
        """Plus addressing: user+tag@example.com -> example.com"""
        self._setup_mock_service(
            mock_get_service,
            [
                {
                    "id": "msg1",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "user+tag@example.com"},
                            {"name": "Subject", "value": "Test"},
                        ]
                    },
                    "sizeEstimate": 1000,
                }
            ],
        )

        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert results[0]["domain"] == "example.com"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_case_normalization(self, mock_get_service):
        """Domain should be lowercased: User@EXAMPLE.COM -> example.com"""
        self._setup_mock_service(
            mock_get_service,
            [
                {
                    "id": "msg1",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "User@EXAMPLE.COM"},
                            {"name": "Subject", "value": "Test"},
                        ]
                    },
                    "sizeEstimate": 1000,
                }
            ],
        )

        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert results[0]["domain"] == "example.com"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_no_at_symbol(self, mock_get_service):
        """Malformed sender without @: malformed-sender -> malformed-sender"""
        self._setup_mock_service(
            mock_get_service,
            [
                {
                    "id": "msg1",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "malformed-sender"},
                            {"name": "Subject", "value": "Test"},
                        ]
                    },
                    "sizeEstimate": 1000,
                }
            ],
        )

        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert results[0]["domain"] == "malformed-sender"

    def _setup_mock_service(self, mock_get_service, messages):
        """Set up mock Gmail service with given messages."""
        mock_service = Mock()
        mock_get_service.return_value = (mock_service, None)

        # Mock list to return message IDs
        mock_list = Mock()
        mock_list.execute.return_value = {
            "messages": [{"id": msg["id"]} for msg in messages]
        }
        mock_service.users.return_value.messages.return_value.list.return_value = (
            mock_list
        )

        # Mock batch request
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


class TestSenderAggregation:
    """Tests for sender aggregation logic."""

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_count_accumulation(self, mock_get_service):
        """Multiple emails from same sender should accumulate count."""
        messages = [
            {
                "id": f"msg{i}",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Subject", "value": f"Subject {i}"},
                    ]
                },
                "sizeEstimate": 1000,
            }
            for i in range(5)
        ]

        self._setup_mock_service(mock_get_service, messages)
        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert len(results) == 1
        assert results[0]["count"] == 5

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_size_aggregation(self, mock_get_service):
        """Total size should be sum of all message sizes."""
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
                "sizeEstimate": 2500,
            },
            {
                "id": "msg3",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Subject", "value": "Subject 3"},
                    ]
                },
                "sizeEstimate": 500,
            },
        ]

        self._setup_mock_service(mock_get_service, messages)
        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert results[0]["total_size"] == 4000  # 1000 + 2500 + 500

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_subject_collection_max_three(self, mock_get_service):
        """Should collect maximum 3 subjects per sender."""
        messages = [
            {
                "id": f"msg{i}",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Subject", "value": f"Subject {i}"},
                    ]
                },
                "sizeEstimate": 1000,
            }
            for i in range(5)
        ]

        self._setup_mock_service(mock_get_service, messages)
        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert len(results[0]["subjects"]) == 3

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_date_tracking(self, mock_get_service):
        """First and last dates should be tracked."""
        messages = [
            {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Subject", "value": "First"},
                        {"name": "Date", "value": "Mon, 01 Jan 2024 10:00:00 +0000"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "msg2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "Subject", "value": "Last"},
                        {"name": "Date", "value": "Wed, 03 Jan 2024 10:00:00 +0000"},
                    ]
                },
                "sizeEstimate": 1000,
            },
        ]

        self._setup_mock_service(mock_get_service, messages)
        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert results[0]["first_date"] == "Mon, 01 Jan 2024 10:00:00 +0000"
        assert results[0]["last_date"] == "Wed, 03 Jan 2024 10:00:00 +0000"

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_sorting_by_count(self, mock_get_service):
        """Results should be sorted by count descending."""
        messages = [
            # Sender with 1 email
            {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "low@example.com"},
                        {"name": "Subject", "value": "Low"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            # Sender with 3 emails
            {
                "id": "msg2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "high@example.com"},
                        {"name": "Subject", "value": "High 1"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "msg3",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "high@example.com"},
                        {"name": "Subject", "value": "High 2"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "msg4",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "high@example.com"},
                        {"name": "Subject", "value": "High 3"},
                    ]
                },
                "sizeEstimate": 1000,
            },
        ]

        self._setup_mock_service(mock_get_service, messages)
        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert results[0]["email"] == "high@example.com"
        assert results[0]["count"] == 3
        assert results[1]["email"] == "low@example.com"
        assert results[1]["count"] == 1

    def _setup_mock_service(self, mock_get_service, messages):
        """Set up mock Gmail service with given messages."""
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


class TestRecipientExtraction:
    """Tests for recipient extraction from scan results."""

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_to_header_extraction(self, mock_get_service):
        """Recipients should be extracted from To header."""
        messages = [
            {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "To", "value": "recipient@example.com"},
                        {"name": "Subject", "value": "Test"},
                    ]
                },
                "sizeEstimate": 1000,
            }
        ]

        self._setup_mock_service(mock_get_service, messages)
        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert "recipient@example.com" in results[0]["recipients"]

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_recipients_lowercase_storage(self, mock_get_service):
        """Recipients should be stored in lowercase."""
        messages = [
            {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "To", "value": "USER@EXAMPLE.COM"},
                        {"name": "Subject", "value": "Test"},
                    ]
                },
                "sizeEstimate": 1000,
            }
        ]

        self._setup_mock_service(mock_get_service, messages)
        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert "user@example.com" in results[0]["recipients"]

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_recipients_converted_to_list(self, mock_get_service):
        """Recipients should be converted from set to list in output."""
        messages = [
            {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "To", "value": "recipient@example.com"},
                        {"name": "Subject", "value": "Test"},
                    ]
                },
                "sizeEstimate": 1000,
            }
        ]

        self._setup_mock_service(mock_get_service, messages)
        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        assert isinstance(results[0]["recipients"], list)

    @patch("app.services.gmail.delete.get_gmail_service")
    def test_recipients_accumulated_across_emails(self, mock_get_service):
        """Recipients should be accumulated across multiple emails from same sender."""
        messages = [
            {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "To", "value": "user1@example.com"},
                        {"name": "Subject", "value": "Test 1"},
                    ]
                },
                "sizeEstimate": 1000,
            },
            {
                "id": "msg2",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "sender@example.com"},
                        {"name": "To", "value": "user2@example.com"},
                        {"name": "Subject", "value": "Test 2"},
                    ]
                },
                "sizeEstimate": 1000,
            },
        ]

        self._setup_mock_service(mock_get_service, messages)
        scan_senders_for_delete(limit=10)
        results = get_delete_scan_results()

        recipients = results[0]["recipients"]
        assert "user1@example.com" in recipients
        assert "user2@example.com" in recipients

    def _setup_mock_service(self, mock_get_service, messages):
        """Set up mock Gmail service with given messages."""
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
