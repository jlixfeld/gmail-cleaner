"""
Unit Tests for Gmail Helper Functions
-------------------------------------
Tests for app/services/gmail/helpers.py
"""

from app.services.gmail.helpers import (
    build_gmail_query,
    get_recipients_from_headers,
    get_sender_info,
    get_subject,
    sanitize_gmail_query_value,
)


class TestGetSenderInfo:
    """Tests for get_sender_info function."""

    def test_standard_format_with_name(self):
        """Standard format: Display Name <email@domain.com>"""
        headers = [{"name": "From", "value": "Display Name <email@domain.com>"}]
        name, email = get_sender_info(headers)
        assert name == "Display Name"
        assert email == "email@domain.com"

    def test_quoted_name(self):
        """Quoted name format: "Display Name" <email@domain.com>"""
        headers = [{"name": "From", "value": '"Display Name" <email@domain.com>'}]
        name, email = get_sender_info(headers)
        assert name == "Display Name"
        assert email == "email@domain.com"

    def test_quoted_name_with_comma(self):
        """Quoted name with comma: "Last, First" <email@domain.com>"""
        headers = [{"name": "From", "value": '"Last, First" <email@domain.com>'}]
        name, email = get_sender_info(headers)
        assert name == "Last, First"
        assert email == "email@domain.com"

    def test_plain_email_only(self):
        """Plain email without name: email@domain.com"""
        headers = [{"name": "From", "value": "email@domain.com"}]
        name, email = get_sender_info(headers)
        assert name == "email@domain.com"
        assert email == "email@domain.com"

    def test_missing_from_header(self):
        """Missing From header should return Unknown."""
        headers = [{"name": "Subject", "value": "Test"}]
        name, email = get_sender_info(headers)
        assert name == "Unknown"
        assert email == "unknown"

    def test_empty_headers(self):
        """Empty headers list should return Unknown."""
        headers = []
        name, email = get_sender_info(headers)
        assert name == "Unknown"
        assert email == "unknown"

    def test_unicode_name(self):
        """Unicode characters in name."""
        headers = [{"name": "From", "value": "Dmitry Petrov <ivan@example.com>"}]
        name, email = get_sender_info(headers)
        assert name == "Dmitry Petrov"
        assert email == "ivan@example.com"

    def test_name_with_brackets_only(self):
        """Email in brackets without name: <email@domain.com>"""
        headers = [{"name": "From", "value": "<email@domain.com>"}]
        name, email = get_sender_info(headers)
        assert name == "email@domain.com"
        assert email == "email@domain.com"

    def test_case_insensitive_header_name(self):
        """From header name should be case insensitive."""
        headers = [{"name": "FROM", "value": "Test <test@example.com>"}]
        name, email = get_sender_info(headers)
        assert name == "Test"
        assert email == "test@example.com"

    def test_lowercase_from(self):
        """Lowercase from header."""
        headers = [{"name": "from", "value": "Test <test@example.com>"}]
        name, email = get_sender_info(headers)
        assert name == "Test"
        assert email == "test@example.com"

    def test_whitespace_in_name(self):
        """Extra whitespace should be stripped."""
        headers = [{"name": "From", "value": "  Display Name  <email@domain.com>"}]
        name, email = get_sender_info(headers)
        assert name == "Display Name"
        assert email == "email@domain.com"


class TestGetSubject:
    """Tests for get_subject function."""

    def test_normal_subject(self):
        """Normal subject extraction."""
        headers = [{"name": "Subject", "value": "Test Subject"}]
        assert get_subject(headers) == "Test Subject"

    def test_missing_subject(self):
        """Missing Subject header returns default."""
        headers = [{"name": "From", "value": "test@example.com"}]
        assert get_subject(headers) == "(No Subject)"

    def test_empty_subject(self):
        """Empty subject value."""
        headers = [{"name": "Subject", "value": ""}]
        assert get_subject(headers) == ""

    def test_empty_headers(self):
        """Empty headers list returns default."""
        headers = []
        assert get_subject(headers) == "(No Subject)"

    def test_special_characters(self):
        """Subject with special characters."""
        headers = [{"name": "Subject", "value": "Re: Fwd: [URGENT] Important!!!"}]
        assert get_subject(headers) == "Re: Fwd: [URGENT] Important!!!"

    def test_unicode_subject(self):
        """Subject with unicode characters."""
        headers = [{"name": "Subject", "value": "Message from cafe"}]
        assert get_subject(headers) == "Message from cafe"

    def test_case_insensitive_header_name(self):
        """Subject header name should be case insensitive."""
        headers = [{"name": "SUBJECT", "value": "Test"}]
        assert get_subject(headers) == "Test"


class TestGetRecipientsFromHeaders:
    """Tests for get_recipients_from_headers function."""

    def test_single_to_recipient(self):
        """Single recipient in To header."""
        headers = [{"name": "To", "value": "recipient@example.com"}]
        result = get_recipients_from_headers(headers)
        assert result == {"recipient@example.com"}

    def test_multiple_to_recipients(self):
        """Multiple recipients in To header."""
        headers = [{"name": "To", "value": "first@example.com, second@example.com"}]
        result = get_recipients_from_headers(headers)
        assert result == {"first@example.com", "second@example.com"}

    def test_recipients_with_names(self):
        """Recipients with display names."""
        headers = [
            {
                "name": "To",
                "value": '"First User" <first@example.com>, Second <second@example.com>',
            }
        ]
        result = get_recipients_from_headers(headers)
        assert result == {"first@example.com", "second@example.com"}

    def test_to_cc_bcc_combined(self):
        """Recipients from To, Cc, and Bcc headers."""
        headers = [
            {"name": "To", "value": "to@example.com"},
            {"name": "Cc", "value": "cc@example.com"},
            {"name": "Bcc", "value": "bcc@example.com"},
        ]
        result = get_recipients_from_headers(headers)
        assert result == {"to@example.com", "cc@example.com", "bcc@example.com"}

    def test_case_normalization(self):
        """Email addresses should be normalized to lowercase."""
        headers = [{"name": "To", "value": "USER@EXAMPLE.COM"}]
        result = get_recipients_from_headers(headers)
        assert result == {"user@example.com"}

    def test_deduplication(self):
        """Duplicate emails should be deduplicated."""
        headers = [
            {"name": "To", "value": "user@example.com, USER@EXAMPLE.COM"},
            {"name": "Cc", "value": "user@example.com"},
        ]
        result = get_recipients_from_headers(headers)
        assert result == {"user@example.com"}

    def test_empty_headers(self):
        """Empty headers should return empty set."""
        headers = []
        result = get_recipients_from_headers(headers)
        assert result == set()

    def test_no_recipient_headers(self):
        """No To/Cc/Bcc headers should return empty set."""
        headers = [{"name": "From", "value": "sender@example.com"}]
        result = get_recipients_from_headers(headers)
        assert result == set()

    def test_plus_addressing(self):
        """Email with plus addressing."""
        headers = [{"name": "To", "value": "user+tag@example.com"}]
        result = get_recipients_from_headers(headers)
        assert result == {"user+tag@example.com"}

    def test_case_insensitive_header_names(self):
        """Header names should be case insensitive."""
        headers = [
            {"name": "TO", "value": "to@example.com"},
            {"name": "cc", "value": "cc@example.com"},
            {"name": "BCC", "value": "bcc@example.com"},
        ]
        result = get_recipients_from_headers(headers)
        assert result == {"to@example.com", "cc@example.com", "bcc@example.com"}


class TestBuildGmailQuery:
    """Tests for build_gmail_query function."""

    def test_none_filters(self):
        """None filters should return empty string."""
        assert build_gmail_query(None) == ""

    def test_empty_dict_filters(self):
        """Empty dict filters should return empty string."""
        assert build_gmail_query({}) == ""

    def test_older_than_filter(self):
        """older_than filter should generate correct query."""
        filters = {"older_than": "30d"}
        assert build_gmail_query(filters) == "older_than:30d"

    def test_after_date_filter(self):
        """after_date filter should generate correct query."""
        filters = {"after_date": "2024/01/15"}
        assert build_gmail_query(filters) == "after:2024/01/15"

    def test_before_date_filter(self):
        """before_date filter should generate correct query."""
        filters = {"before_date": "2024/12/31"}
        assert build_gmail_query(filters) == "before:2024/12/31"

    def test_date_range(self):
        """Both after_date and before_date should be combined."""
        filters = {"after_date": "2024/01/01", "before_date": "2024/12/31"}
        result = build_gmail_query(filters)
        assert "after:2024/01/01" in result
        assert "before:2024/12/31" in result

    def test_date_priority_over_older_than(self):
        """after/before dates should take priority over older_than."""
        filters = {"after_date": "2024/01/01", "older_than": "30d"}
        result = build_gmail_query(filters)
        assert "after:2024/01/01" in result
        assert "older_than" not in result

    def test_larger_than_filter(self):
        """larger_than filter should generate correct query."""
        filters = {"larger_than": "5M"}
        assert build_gmail_query(filters) == "larger:5M"

    def test_category_filter(self):
        """category filter should generate correct query."""
        filters = {"category": "promotions"}
        assert build_gmail_query(filters) == "category:promotions"

    def test_sender_filter(self):
        """sender filter should generate sanitized query."""
        filters = {"sender": "test@example.com"}
        result = build_gmail_query(filters)
        assert 'from:"test@example.com"' in result

    def test_label_filter(self):
        """label filter should generate sanitized query."""
        filters = {"label": "INBOX"}
        result = build_gmail_query(filters)
        assert 'label:"INBOX"' in result

    def test_multiple_filters(self):
        """Multiple filters should be joined with spaces."""
        filters = {
            "older_than": "30d",
            "category": "promotions",
            "larger_than": "5M",
        }
        result = build_gmail_query(filters)
        assert "older_than:30d" in result
        assert "category:promotions" in result
        assert "larger:5M" in result

    def test_empty_filter_values_ignored(self):
        """Empty string filter values should be ignored."""
        filters = {"older_than": "", "category": "promotions"}
        result = build_gmail_query(filters)
        assert "older_than" not in result
        assert "category:promotions" in result

    def test_none_filter_values_ignored(self):
        """None filter values should be ignored."""
        filters = {"older_than": None, "category": "social"}
        result = build_gmail_query(filters)
        assert "older_than" not in result
        assert "category:social" in result

    def test_pydantic_model_input(self):
        """Should handle Pydantic model with model_dump method."""

        class MockFiltersModel:
            def model_dump(self, exclude_none=False):
                return {"older_than": "7d", "category": "updates"}

        filters = MockFiltersModel()
        result = build_gmail_query(filters)
        assert "older_than:7d" in result
        assert "category:updates" in result


class TestSanitizeGmailQueryValue:
    """Tests for sanitize_gmail_query_value function."""

    def test_simple_email(self):
        """Simple email should be quoted."""
        result = sanitize_gmail_query_value("user@example.com")
        assert result == '"user@example.com"'

    def test_empty_value(self):
        """Empty value should return empty string."""
        assert sanitize_gmail_query_value("") == ""

    def test_quote_escaping(self):
        """Quotes in value should be escaped."""
        result = sanitize_gmail_query_value('user"with"quotes@test.com')
        assert result == '"user\\"with\\"quotes@test.com"'

    def test_backslash_escaping(self):
        """Backslashes should be escaped."""
        result = sanitize_gmail_query_value("path\\to\\file")
        assert result == '"path\\\\to\\\\file"'

    def test_injection_prevention(self):
        """Query operators should be safely quoted."""
        result = sanitize_gmail_query_value("evil@test.com OR from:admin@company.com")
        assert result == '"evil@test.com OR from:admin@company.com"'

    def test_parentheses_handling(self):
        """Parentheses should be safely quoted."""
        result = sanitize_gmail_query_value("test(value)")
        assert result == '"test(value)"'

    def test_minus_operator(self):
        """Minus operator should be safely quoted."""
        result = sanitize_gmail_query_value("-important@example.com")
        assert result == '"-important@example.com"'

    def test_special_characters(self):
        """Various special characters should be handled."""
        result = sanitize_gmail_query_value("user+tag@example.com")
        assert result == '"user+tag@example.com"'
