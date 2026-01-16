"""
Gmail Service Helpers
---------------------
Shared utility functions: security, filters, and email parsing.
"""

import re
import socket
import ipaddress
from email.utils import getaddresses, parseaddr
from urllib.parse import urlparse
from typing import Optional, Union, Any

import tldextract


# Common compound TLDs that need 3 parts (e.g., amazon.co.uk)
COMPOUND_TLDS = {"co.uk", "com.au", "co.nz", "co.jp", "co.kr", "com.br", "com.mx"}


def get_registrable_domain(domain: str) -> str:
    """Extract registrable domain, stripping subdomains.

    Args:
        domain: Full domain with potential subdomains (e.g., mail.example.com)

    Returns:
        Registrable domain (e.g., example.com, amazon.co.uk)

    Examples:
        >>> get_registrable_domain("e.fiverr.com")
        'fiverr.com'
        >>> get_registrable_domain("mail.amazon.co.uk")
        'amazon.co.uk'
        >>> get_registrable_domain("example.com")
        'example.com'
    """
    parts = domain.lower().split(".")
    if len(parts) <= 2:
        return domain.lower()

    # Check for compound TLDs
    last_two = ".".join(parts[-2:])
    if last_two in COMPOUND_TLDS:
        return ".".join(parts[-3:]) if len(parts) >= 3 else domain.lower()

    # Standard TLD: take last 2 parts
    return ".".join(parts[-2:])


def _parse_apple_relay_email(email: str) -> tuple[str, str, int] | None:
    """Parse Apple privacy relay email to extract local part, domain segments, and TLD end index.

    Internal helper for extract_real_domain_from_apple_relay and
    extract_original_email_from_apple_relay.

    Args:
        email: Email address to parse

    Returns:
        Tuple of (local_part, domain_with_subdomains, tld_end_index) or None if not Apple relay
    """
    relay_domains = ("icloud.com", "privaterelay.appleid.com")

    if "@" not in email:
        return None

    local, domain = email.rsplit("@", 1)
    if domain.lower() not in relay_domains:
        return None

    # Pattern: {localpart}_at_{domain}_{hash}
    if "_at_" not in local.lower():
        return None

    # Split on "_at_" preserving original case for local part
    at_idx = local.lower().index("_at_")
    original_local = local[:at_idx]
    domain_part = local[at_idx + 4 :]  # Skip "_at_"
    segments = domain_part.split("_")

    # Try progressively longer domain candidates using tldextract
    best_match_end = -1
    best_fqdn = None
    for end in range(1, len(segments) + 1):
        candidate = ".".join(segments[:end])
        result = tldextract.extract(candidate)

        # Check if this forms a valid domain with a known TLD
        if result.suffix and result.domain:
            best_match_end = end
            # Build full domain including subdomains
            if result.subdomain:
                best_fqdn = f"{result.subdomain}.{result.domain}.{result.suffix}"
            else:
                best_fqdn = f"{result.domain}.{result.suffix}"

    if best_fqdn is None:
        return None

    return (original_local, best_fqdn, best_match_end)


def extract_real_domain_from_apple_relay(email: str) -> str | None:
    """Extract real sender domain from Apple privacy relay addresses.

    Apple's privacy relay services (Hide My Email, Sign in with Apple) encode
    the original sender's email in the local part using `_at_` as a separator.

    Uses `tldextract` with the Public Suffix List to support all valid TLDs,
    including newer gTLDs like .markets, .africa, .app, etc.

    Handles:
    - Hide My Email: xxx_at_domain_com_hash@icloud.com
    - Sign in with Apple: xxx_at_domain_com_hash@privaterelay.appleid.com

    Args:
        email: Email address to check

    Returns:
        Registrable domain (no subdomains) or None if not an Apple relay

    Examples:
        >>> extract_real_domain_from_apple_relay(
        ...     "notification_at_kickstarter_com_f5s7hcm_58cd@icloud.com"
        ... )
        'kickstarter.com'
        >>> extract_real_domain_from_apple_relay(
        ...     "noreply_at_e_fiverr_com_z4gur7mrhh_4fe6f996@privaterelay.appleid.com"
        ... )
        'fiverr.com'
        >>> extract_real_domain_from_apple_relay(
        ...     "support_at_mailer_alpaca_markets_r6601abwwf71rc@icloud.com"
        ... )
        'alpaca.markets'
        >>> extract_real_domain_from_apple_relay("user@example.com")
        # Returns None
    """
    parsed = _parse_apple_relay_email(email)
    if parsed is None:
        return None

    _local, fqdn, _end = parsed
    # Return registrable domain (strip subdomains)
    return get_registrable_domain(fqdn)


def extract_original_email_from_apple_relay(email: str) -> str | None:
    """Extract original sender email from Apple privacy relay addresses.

    Reconstructs the full original email address including subdomains.
    Use this when displaying sender information to users.

    Args:
        email: Apple relay email address

    Returns:
        Original email address or None if not an Apple relay

    Examples:
        >>> extract_original_email_from_apple_relay(
        ...     "noreply_at_skool_com_qrt2f0b6834fxp_j3af7012@icloud.com"
        ... )
        'noreply@skool.com'
        >>> extract_original_email_from_apple_relay(
        ...     "noreply_at_notifs_skool_com_qrtb88b68d94xp_j0bf7012@icloud.com"
        ... )
        'noreply@notifs.skool.com'
        >>> extract_original_email_from_apple_relay(
        ...     "support_at_mailer_alpaca_markets_r6601abwwf71rc@icloud.com"
        ... )
        'support@mailer.alpaca.markets'
        >>> extract_original_email_from_apple_relay("user@example.com")
        # Returns None
    """
    parsed = _parse_apple_relay_email(email)
    if parsed is None:
        return None

    local_part, fqdn, _end = parsed
    return f"{local_part}@{fqdn}"


def sanitize_gmail_query_value(value: str) -> str:
    """Sanitize a value for safe use in Gmail search queries.

    Gmail query syntax uses special operators (OR, AND, -, (), etc.) that could
    be injected via unsanitized user input. This function quotes the value to
    ensure it's treated as a literal string.

    Args:
        value: The raw value to sanitize (e.g., email address, domain)

    Returns:
        A quoted string safe for use in Gmail queries

    Examples:
        >>> sanitize_gmail_query_value("user@example.com")
        '"user@example.com"'
        >>> sanitize_gmail_query_value('evil@test.com OR from:admin@company.com')
        '"evil@test.com OR from:admin@company.com"'
        >>> sanitize_gmail_query_value('user"with"quotes@test.com')
        '"user\\"with\\"quotes@test.com"'
    """
    if not value:
        return ""

    # Escape any existing backslashes first, then escape quotes
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')

    # Wrap in quotes to treat as literal
    return f'"{escaped}"'


def validate_unsafe_url(url: str) -> str:
    """
    Validate URL to prevent SSRF.
    Checks scheme and resolves hostname to ensure it's not a local/private IP.

    Resolves all A and AAAA records to prevent DNS rebinding attacks where
    a hostname resolves to a safe IP during validation but a malicious IP
    during actual request. All resolved IPs must pass validation.

    TOCTOU Risk Warning:
    This validation occurs before the request, but DNS could still change
    between validation and request time. For complete protection against
    DNS rebinding attacks, callers should:
    1. Use the validated IPs directly (if possible) instead of the hostname
    2. Implement request-level IP validation in the HTTP client
    3. Use a custom HTTP client that validates IPs at request time

    Returns:
        The validated URL string (unchanged).
    """
    try:
        parsed = urlparse(url)
    except Exception as err:
        raise ValueError("Invalid URL format") from err

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid URL scheme. Only HTTP and HTTPS are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: No hostname found.")

    # Resolve all A and AAAA records to prevent DNS rebinding
    # Validate all IPs - all must be safe
    # Note: This pins the IPs at validation time, but DNS could still change
    # between validation and actual request (TOCTOU risk).
    validated_ips = []
    try:
        # Get all address info (both IPv4 and IPv6)
        addr_infos = socket.getaddrinfo(
            hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )

        for addr_info in addr_infos:
            # addr_info[4] is (host, port) tuple
            ip_str = addr_info[4][0]

            try:
                ip = ipaddress.ip_address(ip_str)

                # Check for restricted IP ranges
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_unspecified
                ):
                    raise ValueError(f"Blocked restricted IP: {ip_str}")

                validated_ips.append(ip_str)
            except ValueError as err:
                # If any IP is invalid or restricted, reject the URL
                raise ValueError(f"Invalid or restricted IP address: {ip_str}") from err

        if not validated_ips:
            raise ValueError(
                f"Could not resolve any valid IP addresses for hostname: {hostname}"
            )

    except socket.gaierror as err:
        raise ValueError(f"Could not resolve hostname: {hostname}") from err
    except ValueError:
        # Re-raise our own ValueError with context (already chained above)
        raise

    return url


def build_gmail_query(filters: Optional[Union[dict, Any]] = None) -> str:
    """Build Gmail search query from filter parameters.

    Args:
        filters: dict with keys:
            - older_than: '7d', '30d', '90d', '180d', '365d' or empty (for relative dates)
            - after_date: 'YYYY/MM/DD' for emails after this date
            - before_date: 'YYYY/MM/DD' for emails before this date
            - larger_than: '1M', '5M', '10M', '25M' or empty
            - category: 'promotions', 'social', 'updates', 'forums', 'primary' or empty
            - sender: 'email@domain.com' or 'domain.com' to filter by sender

    Returns:
        Gmail query string, empty string if no filters
    """
    if not filters:
        return ""

    # Handle both dict and Pydantic model
    if hasattr(filters, "model_dump"):
        filters = filters.model_dump(exclude_none=True)

    query_parts = []

    # Use after/before dates if provided (custom date range)
    if after_date := filters.get("after_date", ""):
        query_parts.append(f"after:{after_date}")

    if before_date := filters.get("before_date", ""):
        query_parts.append(f"before:{before_date}")

    # Fall back to older_than for preset options
    if not after_date and not before_date:
        if older_than := filters.get("older_than", ""):
            query_parts.append(f"older_than:{older_than}")

    if larger_than := filters.get("larger_than", ""):
        query_parts.append(f"larger:{larger_than}")

    if category := filters.get("category", ""):
        query_parts.append(f"category:{category}")

    if sender := filters.get("sender", ""):
        query_parts.append(f"from:{sanitize_gmail_query_value(sender)}")

    if label := filters.get("label", ""):
        query_parts.append(f"label:{sanitize_gmail_query_value(label)}")

    return " ".join(query_parts)


def build_delete_scan_query(filters: Optional[Union[dict, Any]] = None) -> str:
    """Build Gmail search query for delete scan with default exclusions.

    Excludes sent, trash, and spam folders by default.

    **Args:**
        - `filters`: Optional dict with filter parameters (same as build_gmail_query)

    **Returns:**
        Gmail query string with default exclusions
    """
    base_query = build_gmail_query(filters)
    exclusions = "-in:sent -in:trash -in:spam"

    if base_query:
        return f"{base_query} {exclusions}"
    return exclusions


def get_unsubscribe_from_headers(headers: list) -> tuple[Optional[str], Optional[str]]:
    """Extract unsubscribe link from email headers."""
    for header in headers:
        if header["name"].lower() == "list-unsubscribe":
            value = header["value"]

            # Look for one-click POST header
            for h in headers:
                if h["name"].lower() == "list-unsubscribe-post":
                    # Has one-click support
                    urls = re.findall(r"<(https?://[^>]+)>", value)
                    if urls:
                        return urls[0], "one-click"

            # Standard unsubscribe link
            urls = re.findall(r"<(https?://[^>]+)>", value)
            if urls:
                return urls[0], "manual"

            # mailto: link as fallback
            mailto = re.findall(r"<(mailto:[^>]+)>", value)
            if mailto:
                return mailto[0], "manual"

    return None, None


def get_sender_info(headers: list) -> tuple[str, str]:
    """Extract sender name and email from headers.

    Uses Python's email.utils.parseaddr for RFC 2822 compliant parsing.
    Handles formats like:
    - "Name" <email@domain.com>
    - email@domain.com (Name)
    - email@domain.com

    Args:
        headers: List of email header dicts with 'name' and 'value' keys

    Returns:
        Tuple of (display_name, email_address)
    """
    for header in headers:
        if header["name"].lower() == "from":
            name, email = parseaddr(header["value"])
            if email:
                return name or email, email
            # Fallback if parseaddr couldn't extract email
            return header["value"], header["value"]
    return "Unknown", "unknown"


def get_subject(headers: list) -> str:
    """Extract subject from email headers."""
    for header in headers:
        if header["name"].lower() == "subject":
            return header["value"]
    return "(No Subject)"


def get_recipients_from_headers(headers: list) -> set[str]:
    """Extract recipient email addresses from To, Cc, Bcc headers.

    Uses Python's email.utils.getaddresses for RFC 2822 compliant parsing.
    Handles formats like:
    - "Name" <email@domain.com>, other@domain.com
    - email@domain.com (Name)
    - Multiple comma-separated addresses

    Args:
        headers: List of email header dicts with 'name' and 'value' keys

    Returns:
        Set of lowercase email addresses from To/Cc/Bcc fields
    """
    recipients: set[str] = set()
    header_values = []
    for header in headers:
        if header["name"].lower() in ("to", "cc", "bcc"):
            header_values.append(header["value"])

    for _name, email in getaddresses(header_values):
        if email:
            recipients.add(email.lower())
    return recipients


def get_list_id(headers: list) -> Optional[str]:
    """Extract List-Id from email headers.

    The List-Id header identifies mailing lists and is used to group emails
    from the same list regardless of sender. Format is typically:
    "List Name <list-id.domain.com>" or just "<list-id.domain.com>"

    Args:
        headers: List of email header dicts with 'name' and 'value' keys

    Returns:
        The list identifier string, or None if not found
    """
    for header in headers:
        if header["name"].lower() == "list-id":
            value = header["value"]
            # Extract from <list-name.domain> format
            match = re.search(r"<([^>]+)>", value)
            if match:
                return match.group(1)
            return value.strip()
    return None
