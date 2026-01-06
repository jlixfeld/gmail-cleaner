"""
Rate Limiting Configuration
---------------------------
Configure rate limiting for API endpoints using slowapi.

This module provides protection against:
- DoS attacks
- Accidental API quota exhaustion
- Runaway client requests
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Create the limiter instance with IP-based rate limiting
# Using in-memory storage (suitable for single-instance local tool)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],  # Default: 60 requests per minute
    storage_uri="memory://",
)

# Rate limit configurations for different endpoint types
# For a local single-user tool, these are set very high to avoid self-blocking.
# Google's API has its own rate limits which are generous for single users.

STATUS_RATE_LIMIT = "6000/minute"
ACTION_RATE_LIMIT = "600/minute"
AUTH_RATE_LIMIT = "300/minute"
HEAVY_OPERATION_RATE_LIMIT = "600/minute"
