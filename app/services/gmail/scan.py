"""
Gmail Scanning Operations
--------------------------
Functions for scanning emails to find unsubscribe links.
"""

import logging
from collections import defaultdict
from email.utils import parsedate_to_datetime
from typing import Optional

from app.core import state
from app.services.auth import get_gmail_service
from app.services.gmail.helpers import (
    build_gmail_query,
    get_unsubscribe_from_headers,
    get_sender_info,
    get_subject,
    get_list_id,
)

logger = logging.getLogger(__name__)


def scan_emails(limit: int = 500, filters: Optional[dict] = None):
    """Scan emails for unsubscribe links using Gmail Batch API.

    Args:
        limit: Maximum emails to scan. 0 = scan all (no limit).
        filters: Optional Gmail filter options.
    """
    # Validate input - negative values are invalid, 0 means "scan all"
    if limit < 0:
        state.reset_scan()
        state.update_scan_status(error="Limit cannot be negative", done=True)
        return

    scan_all = limit == 0
    state.reset_scan()
    state.update_scan_status(message="Connecting to Gmail...")

    service, error = get_gmail_service()
    if error:
        state.update_scan_status(error=error, done=True)
        return

    try:
        state.update_scan_status(message="Fetching email list...")

        # Build query
        query = build_gmail_query(filters)

        # Get message IDs (fast - just IDs)
        message_ids = []
        page_token = None

        while scan_all or len(message_ids) < limit:
            # When scanning all, always request max batch; otherwise request remaining
            max_results = 500 if scan_all else min(500, limit - len(message_ids))
            list_params = {
                "userId": "me",
                "maxResults": max_results,
            }
            if page_token:
                list_params["pageToken"] = page_token
            if query:  # Only add q parameter if query is not empty
                list_params["q"] = query

            result = service.users().messages().list(**list_params).execute()

            messages = result.get("messages", [])
            message_ids.extend([m["id"] for m in messages])

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        if not message_ids:
            state.update_scan_status(message="No emails found", done=True)
            return

        total = len(message_ids)
        state.update_scan_status(message=f"Found {total} emails. Scanning...")

        # Process in batches using Gmail Batch API (100 requests per HTTP call!)
        unsubscribe_data: dict[str, dict] = defaultdict(
            lambda: {
                "link": None,
                "count": 0,
                "subjects": [],
                "type": None,
                "sender": "",
                "email": "",
                "first_date": None,
                "last_date": None,
                "list_id": None,
                "senders": [],
            }
        )
        processed = 0
        batch_size = 100

        def process_message(request_id, response, exception) -> None:
            nonlocal processed
            processed += 1

            if exception:
                return

            headers = response.get("payload", {}).get("headers", [])
            unsub_link, unsub_type = get_unsubscribe_from_headers(headers)

            if unsub_link:
                sender_name, sender_email = get_sender_info(headers)
                subject = get_subject(headers)
                list_id = get_list_id(headers)

                # Determine grouping key: List-Id if available, otherwise sender email
                if list_id:
                    grouping_key = f"list:{list_id}"
                elif "@" in sender_email:
                    grouping_key = sender_email
                else:
                    grouping_key = sender_email  # Fallback for malformed

                # Extract date from headers
                email_date = None
                for header in headers:
                    if header["name"].lower() == "date":
                        email_date = header["value"]
                        break

                data = unsubscribe_data[grouping_key]
                data["link"] = unsub_link
                data["count"] += 1
                data["type"] = unsub_type
                data["list_id"] = list_id

                # Track all unique senders in this group
                sender_info = {"name": sender_name, "email": sender_email}
                if sender_info not in data["senders"]:
                    data["senders"].append(sender_info)

                # Keep primary sender as the most common one (first encountered)
                if not data["sender"]:
                    data["sender"] = sender_name
                    data["email"] = sender_email

                if len(data["subjects"]) < 3:
                    data["subjects"].append(subject)

                # Track first and last dates (parse dates for accurate comparison)
                if email_date:
                    try:
                        # Parse RFC 2822 date string to datetime for comparison
                        msg_datetime = parsedate_to_datetime(email_date)
                        current_first = data["first_date"]
                        current_last = data["last_date"]

                        # Update first_date if this is earlier
                        if current_first is None:
                            data["first_date"] = email_date
                        else:
                            try:
                                first_datetime = parsedate_to_datetime(current_first)
                                if msg_datetime < first_datetime:
                                    data["first_date"] = email_date
                            except (ValueError, TypeError):
                                # If parsing fails, use string comparison as fallback
                                if email_date < current_first:
                                    data["first_date"] = email_date

                        # Update last_date if this is later
                        if current_last is None:
                            data["last_date"] = email_date
                        else:
                            try:
                                last_datetime = parsedate_to_datetime(current_last)
                                if msg_datetime > last_datetime:
                                    data["last_date"] = email_date
                            except (ValueError, TypeError):
                                # If parsing fails, use string comparison as fallback
                                if email_date > current_last:
                                    data["last_date"] = email_date
                    except (ValueError, TypeError):
                        # If date parsing fails, skip date tracking for this message
                        pass

        # Execute batch requests
        for i in range(0, len(message_ids), batch_size):
            batch_ids = message_ids[i : i + batch_size]
            batch = service.new_batch_http_request(callback=process_message)

            for msg_id in batch_ids:
                batch.add(
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=[
                            "From",
                            "Subject",
                            "Date",
                            "List-Unsubscribe",
                            "List-Unsubscribe-Post",
                            "List-Id",
                        ],
                    )
                )

            batch.execute()

            progress = int((i + len(batch_ids)) / total * 100)
            state.update_scan_status(
                progress=progress,
                message=f"Scanned {processed}/{total} emails ({len(unsubscribe_data)} found)",
            )

        # Sort by count and format results
        sorted_results = sorted(
            [
                {
                    "domain": k.replace("list:", "") if k.startswith("list:") else k,
                    "link": v["link"],
                    "count": v["count"],
                    "subjects": v["subjects"],
                    "type": v["type"],
                    "sender": v.get("sender", ""),
                    "email": v.get("email", ""),
                    "first_date": v.get("first_date"),
                    "last_date": v.get("last_date"),
                    "list_id": v.get("list_id"),
                    "senders": v.get("senders", []),
                }
                for k, v in unsubscribe_data.items()
            ],
            key=lambda x: x.get("count", 0) or 0,  # Handle None values
            reverse=True,
        )

        state.set_scan_results(sorted_results)
        state.update_scan_status(
            message=f"Found {len(sorted_results)} subscriptions", done=True
        )

    except Exception as e:
        state.update_scan_status(error=str(e), done=True)


def get_scan_status() -> dict:
    """Get current scan status."""
    return state.scan_status.copy()


def get_scan_results() -> list:
    """Get scan results."""
    return state.scan_results.copy()
