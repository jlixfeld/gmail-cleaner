"""
Gmail API Response Fixtures
---------------------------
Realistic Gmail API response mocks for testing.
"""

# Realistic message responses with various header formats
REALISTIC_MESSAGE_RESPONSES = [
    {
        "id": "msg1",
        "payload": {
            "headers": [
                {"name": "From", "value": "Newsletter <news@company.com>"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "Weekly Update"},
                {"name": "Date", "value": "Mon, 01 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 15000,
    },
    {
        "id": "msg2",
        "payload": {
            "headers": [
                {
                    "name": "From",
                    "value": '"Marketing Team" <marketing@promo.example.com>',
                },
                {"name": "To", "value": "user@gmail.com, other@gmail.com"},
                {"name": "Cc", "value": "cc@example.com"},
                {"name": "Subject", "value": "Special Offer!"},
                {"name": "Date", "value": "Tue, 02 Jan 2024 14:30:00 +0000"},
            ]
        },
        "sizeEstimate": 25000,
    },
    {
        "id": "msg3",
        "payload": {
            "headers": [
                {"name": "From", "value": "noreply@alerts.service.com"},
                {"name": "To", "value": '"User Name" <user@gmail.com>'},
                {"name": "Subject", "value": "Security Alert"},
                {"name": "Date", "value": "Wed, 03 Jan 2024 09:15:00 +0000"},
            ]
        },
        "sizeEstimate": 5000,
    },
    {
        "id": "msg4",
        "payload": {
            "headers": [
                {"name": "From", "value": "support@company.com"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Bcc", "value": "bcc@hidden.com"},
                {"name": "Subject", "value": "Re: Your ticket #12345"},
                {"name": "Date", "value": "Thu, 04 Jan 2024 16:45:00 +0000"},
            ]
        },
        "sizeEstimate": 8000,
    },
]

# Edge case header formats for comprehensive testing
EDGE_CASE_HEADERS = {
    "standard": [
        {"name": "From", "value": "Display Name <display@example.com>"},
        {"name": "Subject", "value": "Standard Subject"},
    ],
    "plain_email": [
        {"name": "From", "value": "plain@example.com"},
        {"name": "Subject", "value": "Plain Email"},
    ],
    "quoted_name": [
        {"name": "From", "value": '"Quoted, Name" <quoted@example.com>'},
        {"name": "Subject", "value": "Quoted Name"},
    ],
    "unicode_name": [
        {"name": "From", "value": "Dmitry Petrov <unicode@example.com>"},
        {"name": "Subject", "value": "Unicode Test"},
    ],
    "missing_from": [
        {"name": "Subject", "value": "No From Header"},
    ],
    "empty_from": [
        {"name": "From", "value": ""},
        {"name": "Subject", "value": "Empty From"},
    ],
    "malformed_brackets": [
        {"name": "From", "value": "malformed@example.com (Bad Format)"},
        {"name": "Subject", "value": "Malformed"},
    ],
    "subdomain": [
        {"name": "From", "value": "News <news@marketing.company.co.uk>"},
        {"name": "Subject", "value": "Subdomain Test"},
    ],
    "plus_addressing": [
        {"name": "From", "value": "user+tag@example.com"},
        {"name": "Subject", "value": "Plus Addressing"},
    ],
    "no_subject": [
        {"name": "From", "value": "sender@example.com"},
    ],
    "empty_subject": [
        {"name": "From", "value": "sender@example.com"},
        {"name": "Subject", "value": ""},
    ],
    "special_subject": [
        {"name": "From", "value": "sender@example.com"},
        {"name": "Subject", "value": "Re: Fwd: [URGENT] Important Message!!!"},
    ],
}

# Recipient header variations
RECIPIENT_HEADERS = {
    "single_to": [
        {"name": "To", "value": "recipient@example.com"},
    ],
    "multiple_to": [
        {"name": "To", "value": "first@example.com, second@example.com"},
    ],
    "with_names": [
        {
            "name": "To",
            "value": '"First User" <first@example.com>, Second <second@example.com>',
        },
    ],
    "to_cc_bcc": [
        {"name": "To", "value": "to@example.com"},
        {"name": "Cc", "value": "cc@example.com"},
        {"name": "Bcc", "value": "bcc@example.com"},
    ],
    "duplicates": [
        {"name": "To", "value": "user@example.com, USER@EXAMPLE.COM"},
        {"name": "Cc", "value": "user@example.com"},
    ],
    "mixed_case": [
        {"name": "To", "value": "User@EXAMPLE.COM"},
        {"name": "Cc", "value": "ADMIN@example.com"},
    ],
}

# Messages for delete scan testing
DELETE_SCAN_MESSAGES = [
    # Same sender (sender1@example.com) - 3 emails
    {
        "id": "del1",
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender One <sender1@example.com>"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "First from Sender 1"},
                {"name": "Date", "value": "Mon, 01 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 1000,
    },
    {
        "id": "del2",
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender One <sender1@example.com>"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "Second from Sender 1"},
                {"name": "Date", "value": "Tue, 02 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 1500,
    },
    {
        "id": "del3",
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender One <sender1@example.com>"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "Third from Sender 1"},
                {"name": "Date", "value": "Wed, 03 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 2000,
    },
    # Different sender (sender2@example.com) - 2 emails, same domain
    {
        "id": "del4",
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender Two <sender2@example.com>"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "First from Sender 2"},
                {"name": "Date", "value": "Thu, 04 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 500,
    },
    {
        "id": "del5",
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender Two <sender2@example.com>"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "Second from Sender 2"},
                {"name": "Date", "value": "Fri, 05 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 750,
    },
    # Different domain (other@different.org) - 1 email
    {
        "id": "del6",
        "payload": {
            "headers": [
                {"name": "From", "value": "Other Sender <other@different.org>"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "From Different Domain"},
                {"name": "Date", "value": "Sat, 06 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 3000,
    },
]

# Sent email messages for building known senders cache
SENT_EMAIL_MESSAGES = [
    {
        "id": "sent1",
        "payload": {
            "headers": [
                {"name": "To", "value": "contact1@example.com"},
                {"name": "Subject", "value": "Hello"},
            ]
        },
    },
    {
        "id": "sent2",
        "payload": {
            "headers": [
                {"name": "To", "value": "contact2@example.com, contact3@example.com"},
                {"name": "Cc", "value": "cc@example.com"},
                {"name": "Subject", "value": "Meeting"},
            ]
        },
    },
    {
        "id": "sent3",
        "payload": {
            "headers": [
                {"name": "To", "value": '"Contact Four" <CONTACT4@EXAMPLE.COM>'},
                {"name": "Subject", "value": "Follow up"},
            ]
        },
    },
]

# Messages for unknown senders testing (mix of known and unknown)
INBOX_WITH_KNOWN_UNKNOWN = [
    # Known sender (contact1@example.com - in sent folder)
    {
        "id": "inbox1",
        "payload": {
            "headers": [
                {"name": "From", "value": "Contact One <contact1@example.com>"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "Reply from known contact"},
                {"name": "Date", "value": "Mon, 01 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 1000,
    },
    # Unknown sender (spam@unknown.com - not in sent folder)
    {
        "id": "inbox2",
        "payload": {
            "headers": [
                {"name": "From", "value": "Spammer <spam@unknown.com>"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "You won a prize!"},
                {"name": "Date", "value": "Tue, 02 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 5000,
    },
    # Known sender with different case (CONTACT2@EXAMPLE.COM)
    {
        "id": "inbox3",
        "payload": {
            "headers": [
                {"name": "From", "value": "CONTACT2@EXAMPLE.COM"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "Different case"},
                {"name": "Date", "value": "Wed, 03 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 800,
    },
    # Unknown sender (newsletter@marketing.biz)
    {
        "id": "inbox4",
        "payload": {
            "headers": [
                {"name": "From", "value": "Newsletter <newsletter@marketing.biz>"},
                {"name": "To", "value": "user@gmail.com"},
                {"name": "Subject", "value": "Weekly deals"},
                {"name": "Date", "value": "Thu, 04 Jan 2024 10:00:00 +0000"},
            ]
        },
        "sizeEstimate": 15000,
    },
]


def create_message_list_response(messages: list, next_page_token: str = None) -> dict:
    """Create a Gmail messages.list API response."""
    response = {"messages": [{"id": msg["id"]} for msg in messages]}
    if next_page_token:
        response["nextPageToken"] = next_page_token
    return response


def create_batch_callback(messages: list):
    """Create a batch callback that returns the given messages."""

    def mock_batch_factory(callback):
        """Factory for creating mock batch objects."""
        from unittest.mock import Mock

        batch = Mock()
        batch.add = Mock()
        message_index = [0]  # Use list to allow mutation in nested function

        def execute_batch():
            for msg in messages:
                callback(str(message_index[0]), msg, None)
                message_index[0] += 1

        batch.execute = execute_batch
        return batch

    return mock_batch_factory
