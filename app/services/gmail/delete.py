"""
Gmail Delete Operations
-----------------------
Functions for deleting emails and scanning senders.
"""

import logging
import re
from collections import defaultdict
from typing import Optional

from app.core import state
from app.services.auth import get_gmail_service
from app.services.gmail.helpers import (
    build_gmail_query,
    get_recipients_from_headers,
    get_sender_info,
    get_subject,
)

logger = logging.getLogger(__name__)


def scan_senders_for_delete(limit: int = 1000, filters: Optional[dict] = None):
    """Scan emails and group by sender for bulk delete.

    Args:
        limit: Maximum emails to scan. 0 = scan all (no limit).
        filters: Optional Gmail filter options.
    """
    # Validate input - negative values are invalid, 0 means "scan all"
    if limit < 0:
        state.reset_delete_scan()
        state.update_delete_scan_status(error="Limit cannot be negative", done=True)
        return

    scan_all = limit == 0
    state.reset_delete_scan()
    state.update_delete_scan_status(message="Connecting to Gmail...")

    service, error = get_gmail_service()
    if error:
        state.update_delete_scan_status(error=error, done=True)
        return

    try:
        state.update_delete_scan_status(message="Fetching emails...")

        query = build_gmail_query(filters)

        # When scanning all, always request max batch; otherwise request remaining
        max_results = 500 if scan_all else min(limit, 500)
        results = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=query or None)
            .execute()
        )

        messages = results.get("messages", [])

        while "nextPageToken" in results and (scan_all or len(messages) < limit):
            max_results = 500 if scan_all else min(limit - len(messages), 500)
            results = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=max_results,
                    pageToken=results["nextPageToken"],
                    q=query or None,
                )
                .execute()
            )
            messages.extend(results.get("messages", []))

        # Only apply limit if not scanning all
        if not scan_all:
            messages = messages[:limit]
        total = len(messages)

        if total == 0:
            state.update_delete_scan_status(message="No emails found", done=True)
            return

        state.update_delete_scan_status(message=f"Scanning {total} emails...")

        # Group by sender using Gmail Batch API
        sender_counts: dict[str, dict] = defaultdict(
            lambda: {
                "count": 0,
                "sender": "",
                "email": "",
                "domain": "",
                "subjects": [],
                "first_date": None,
                "last_date": None,
                "message_ids": [],
                "total_size": 0,
                "recipients": set(),
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
            sender_name, sender_email = get_sender_info(headers)
            subject = get_subject(headers)
            msg_id = response.get("id", "")
            size_estimate = response.get("sizeEstimate", 0)

            # Extract date from headers
            email_date = None
            for header in headers:
                if header["name"].lower() == "date":
                    email_date = header["value"]
                    break

            if sender_email:
                sender_counts[sender_email]["count"] += 1
                sender_counts[sender_email]["sender"] = sender_name
                sender_counts[sender_email]["email"] = sender_email
                sender_counts[sender_email]["message_ids"].append(msg_id)
                sender_counts[sender_email]["total_size"] += size_estimate
                if len(sender_counts[sender_email]["subjects"]) < 3:
                    sender_counts[sender_email]["subjects"].append(subject)

                # Extract domain from sender email
                domain = (
                    sender_email.split("@")[-1].lower()
                    if "@" in sender_email
                    else sender_email
                )
                sender_counts[sender_email]["domain"] = domain

                # Extract recipients from To header
                recipients = get_recipients_from_headers(headers)
                sender_counts[sender_email]["recipients"].update(recipients)

                # Track first and last dates
                if email_date:
                    if sender_counts[sender_email]["first_date"] is None:
                        sender_counts[sender_email]["first_date"] = email_date
                    sender_counts[sender_email]["last_date"] = email_date

        # Execute batch requests
        for i in range(0, len(messages), batch_size):
            batch_ids = messages[i : i + batch_size]
            batch = service.new_batch_http_request(callback=process_message)

            for msg_data in batch_ids:
                batch.add(
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_data["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date", "To"],
                    )
                )

            batch.execute()

            progress = int((i + len(batch_ids)) / total * 100)
            state.update_delete_scan_status(
                progress=progress, message=f"Scanned {processed}/{total} emails"
            )

        # Convert recipient sets to lists before returning
        for sender_data in sender_counts.values():
            sender_data["recipients"] = list(sender_data["recipients"])

        # Sort by count
        sorted_senders = sorted(
            [{"email": k, **v} for k, v in sender_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )

        state.set_delete_scan_results(sorted_senders)
        state.update_delete_scan_status(
            message=f"Found {len(sorted_senders)} senders", done=True
        )

    except Exception as e:
        state.update_delete_scan_status(error=str(e), done=True)


def get_delete_scan_status() -> dict:
    """Get delete scan status."""
    return state.delete_scan_status.copy()


def get_delete_scan_results() -> list:
    """Get delete scan results."""
    return state.delete_scan_results.copy()


def delete_emails_by_sender(sender: str, list_id: Optional[str] = None) -> dict:
    """Delete all emails from a specific sender or mailing list.

    Checks both delete scan results (with cached message_ids) and subscription
    scan results. For subscription results without cached message_ids, queries
    Gmail directly.

    Args:
        sender: Sender email address (used when list_id is not provided)
        list_id: List-Id header value for mailing lists (takes precedence over sender)
    """
    # When list_id is provided, use it for lookup; otherwise require sender
    if not list_id and (not sender or not sender.strip()):
        return {
            "success": False,
            "deleted": 0,
            "size_freed": 0,
            "message": "No sender or list_id specified",
        }

    # Determine lookup strategy and find matching data
    sender_data = None
    source = None
    message_ids = []
    size_freed = 0
    need_gmail_query = False

    if list_id:
        # Look up by list_id in subscription scan results
        sub_results = state.scan_results
        sender_data = next((r for r in sub_results if r.get("list_id") == list_id), None)
        if sender_data:
            source = "subscription_scan"
            # Subscription scan doesn't cache message_ids, need to query Gmail
            need_gmail_query = True
    else:
        # Look up by sender email in delete scan results
        sender = sender.strip()
        # Validate sender format - must be a valid email address or domain
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        domain_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$"

        if not (re.match(email_pattern, sender) or re.match(domain_pattern, sender)):
            return {
                "success": False,
                "deleted": 0,
                "size_freed": 0,
                "message": "Invalid sender format. Must be a valid email address or domain.",
            }

        # Check delete scan results (has cached message_ids)
        delete_results = state.get_delete_scan_results()
        sender_data = next((r for r in delete_results if r.get("email") == sender), None)
        if sender_data:
            source = "delete_scan"
            message_ids = sender_data.get("message_ids", [])
            size_freed = sender_data.get("total_size", 0)

    if not sender_data:
        return {
            "success": False,
            "deleted": 0,
            "size_freed": 0,
            "message": "No scan results found. Please scan first.",
        }

    if not message_ids and not need_gmail_query:
        # Delete scan source with empty message_ids = nothing to delete
        return {
            "success": True,
            "deleted": 0,
            "size_freed": 0,
            "message": "No emails found",
        }

    service, error = get_gmail_service()
    if error:
        return {"success": False, "deleted": 0, "size_freed": 0, "message": error}

    try:
        # If no cached message_ids (subscription scan), query Gmail directly
        if need_gmail_query:
            # Build query based on list_id or sender email
            if list_id:
                query = f"list:{list_id}"
            elif sender:
                query = f"from:{sender}"
            else:
                return {
                    "success": True,
                    "deleted": 0,
                    "size_freed": 0,
                    "message": "No emails found",
                }

            # Fetch message IDs from Gmail
            logger.info(f"Querying Gmail with: {query}")
            results = (
                service.users()
                .messages()
                .list(userId="me", maxResults=500, q=query)
                .execute()
            )
            messages = results.get("messages", [])

            # Continue fetching if more pages
            while "nextPageToken" in results:
                results = (
                    service.users()
                    .messages()
                    .list(
                        userId="me",
                        maxResults=500,
                        pageToken=results["nextPageToken"],
                        q=query,
                    )
                    .execute()
                )
                messages.extend(results.get("messages", []))

            message_ids = [m["id"] for m in messages]

        if not message_ids:
            return {
                "success": True,
                "deleted": 0,
                "size_freed": 0,
                "message": "No emails found",
            }

        # Batch delete (move to trash)
        batch_size = 100
        deleted = 0

        for i in range(0, len(message_ids), batch_size):
            batch = message_ids[i : i + batch_size]
            service.users().messages().batchModify(
                userId="me", body={"ids": batch, "addLabelIds": ["TRASH"]}
            ).execute()
            deleted += len(batch)

        # Remove sender from cached results based on source
        if source == "delete_scan":
            current_results = state.get_delete_scan_results()
            if list_id:
                state.set_delete_scan_results(
                    [r for r in current_results if r.get("list_id") != list_id]
                )
            else:
                state.set_delete_scan_results(
                    [r for r in current_results if r.get("email") != sender]
                )

        logger.info(
            f"Delete complete: {deleted} emails moved to trash "
            f"(source={source}, list_id={list_id}, sender={sender})"
        )
        return {
            "success": True,
            "deleted": deleted,
            "size_freed": size_freed,
            "message": f"Moved {deleted} emails to trash",
        }

    except Exception as e:
        logger.exception(f"Error deleting emails (list_id={list_id}, sender={sender})")
        return {"success": False, "deleted": 0, "size_freed": 0, "message": str(e)}


def delete_emails_bulk(senders: list[str]) -> dict:
    """Delete emails from multiple senders."""
    if not senders:
        return {
            "success": False,
            "deleted": 0,
            "size_freed": 0,
            "message": "No senders specified",
        }

    total_deleted = 0
    total_size_freed = 0
    errors = []

    for sender in senders:
        result = delete_emails_by_sender(sender)
        if result["success"]:
            total_deleted += result["deleted"]
            total_size_freed += result.get("size_freed", 0)
        else:
            errors.append(f"{sender}: {result['message']}")

    # Note: delete_emails_by_sender already removes each sender from cached results

    if errors:
        return {
            "success": len(errors) < len(senders),
            "deleted": total_deleted,
            "size_freed": total_size_freed,
            "message": f"Deleted {total_deleted} emails. Errors: {'; '.join(errors[:3])}",
        }

    if total_deleted == 0:
        return {
            "success": False,
            "deleted": 0,
            "size_freed": 0,
            "message": "No emails found to delete",
        }
    return {
        "success": True,
        "deleted": total_deleted,
        "size_freed": total_size_freed,
        "message": f"Deleted {total_deleted} emails",
    }


def delete_emails_bulk_background(senders: list[str]) -> None:
    """Delete emails from multiple senders with progress updates (background task).

    Optimized to collect all message IDs first, then batch delete in larger chunks.
    """
    state.reset_delete_bulk()

    # Validate input
    if not senders or not isinstance(senders, list):
        state.update_delete_bulk_status(done=True, error="No senders specified")
        return

    total_senders = len(senders)
    state.update_delete_bulk_status(
        total_senders=total_senders, message="Collecting emails to delete..."
    )

    service, error = get_gmail_service()
    if error:
        state.update_delete_bulk_status(done=True, error=error)
        return

    # Phase 1: Collect message IDs from cached scan results
    all_message_ids = []
    errors = []
    scan_results = state.get_delete_scan_results()

    for i, sender in enumerate(senders):
        progress = int((i / total_senders) * 40)  # 0-40% for collecting
        state.update_delete_bulk_status(
            current_sender=i + 1,
            progress=progress,
            message=f"Getting cached emails from {sender}...",
        )

        # Look up cached message_ids from scan results
        sender_data = next((r for r in scan_results if r.get("email") == sender), None)

        if sender_data and sender_data.get("message_ids"):
            all_message_ids.extend(sender_data["message_ids"])
        else:
            errors.append(f"{sender}: No scan results found")

    if not all_message_ids:
        state.update_delete_bulk_status(
            progress=100, done=True, message="No emails found to delete"
        )
        return

    # Phase 2: Batch delete all collected IDs (larger batches = fewer API calls)
    total_emails = len(all_message_ids)
    state.update_delete_bulk_status(message=f"Deleting {total_emails} emails...")

    batch_size = 1000  # Gmail allows up to 1000 per batchModify
    deleted = 0

    try:
        for i in range(0, total_emails, batch_size):
            batch = all_message_ids[i : i + batch_size]
            service.users().messages().batchModify(
                userId="me", body={"ids": batch, "addLabelIds": ["TRASH"]}
            ).execute()
            deleted += len(batch)
            # Progress: 40-100% for deleting
            progress = 40 + int((deleted / total_emails) * 60)
            state.update_delete_bulk_status(
                deleted_count=deleted,
                progress=progress,
                message=f"Deleted {deleted}/{total_emails} emails...",
            )
    except Exception as e:
        errors.append(f"Batch delete error: {e!s}")

    # Remove deleted senders from cached scan results
    current_results = state.get_delete_scan_results()
    filtered_results = [r for r in current_results if r.get("email") not in senders]
    state.set_delete_scan_results(filtered_results)

    # Done
    if errors:
        state.update_delete_bulk_status(
            progress=100,
            done=True,
            deleted_count=deleted,
            error=f"Some errors: {'; '.join(errors[:3])}",
            message=f"Deleted {deleted} emails with some errors",
        )
    else:
        state.update_delete_bulk_status(
            progress=100,
            done=True,
            deleted_count=deleted,
            message=f"Successfully deleted {deleted} emails",
        )


def get_delete_bulk_status() -> dict:
    """Get delete bulk operation status."""
    return state.delete_bulk_status.copy()


# =============================================================================
# UNKNOWN SENDERS DETECTION
# =============================================================================


def build_known_senders_cache(limit: int = 5000):
    """Build cache of known senders by scanning Sent folder.

    Scans sent emails to extract all recipients (To, Cc, Bcc) and builds a set
    of known contacts. This cache is used to filter unknown senders in scans.

    Args:
        limit: Maximum sent emails to scan. 0 = scan all (no limit).
    """
    if limit < 0:
        state.update_known_senders_status(error="Limit cannot be negative", done=True)
        return

    scan_all = limit == 0
    state.reset_known_senders()
    state.update_known_senders_status(message="Connecting to Gmail...")

    service, error = get_gmail_service()
    if error:
        state.update_known_senders_status(error=error, done=True)
        return

    try:
        state.update_known_senders_status(message="Fetching sent emails...")

        # Query only sent emails
        max_results = 500 if scan_all else min(limit, 500)
        results = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q="in:sent")
            .execute()
        )

        all_messages = results.get("messages", [])

        while "nextPageToken" in results and (scan_all or len(all_messages) < limit):
            max_results = 500 if scan_all else min(limit - len(all_messages), 500)
            results = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=max_results,
                    pageToken=results["nextPageToken"],
                    q="in:sent",
                )
                .execute()
            )
            all_messages.extend(results.get("messages", []))

        if not scan_all:
            all_messages = all_messages[:limit]

        total = len(all_messages)
        if total == 0:
            state.update_known_senders_status(
                message="No sent emails found", done=True, sender_count=0
            )
            return

        state.update_known_senders_status(message=f"Scanning {total} sent emails...")

        # Extract recipients from all sent emails
        known_senders: set[str] = set()
        processed = 0
        batch_size = 100

        def process_message(request_id, response, exception) -> None:
            nonlocal processed
            processed += 1

            if exception:
                return

            headers = response.get("payload", {}).get("headers", [])
            recipients = get_recipients_from_headers(headers)
            known_senders.update(recipients)

        # Execute batch requests
        for i in range(0, len(all_messages), batch_size):
            batch_ids = all_messages[i : i + batch_size]
            batch = service.new_batch_http_request(callback=process_message)

            for msg_data in batch_ids:
                batch.add(
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_data["id"],
                        format="metadata",
                        metadataHeaders=["To", "Cc", "Bcc"],
                    )
                )

            batch.execute()

            progress = int((i + len(batch_ids)) / total * 100)
            state.update_known_senders_status(
                progress=progress,
                message=f"Processed {processed}/{total} sent emails",
                scanned_emails=processed,
                sender_count=len(known_senders),
            )

        # Store the known senders
        state.set_known_senders(known_senders)
        state.update_known_senders_status(
            progress=100,
            done=True,
            message=f"Found {len(known_senders)} known contacts",
            sender_count=len(known_senders),
            scanned_emails=total,
        )

    except Exception as e:
        logger.exception("Error building known senders cache")
        state.update_known_senders_status(error=str(e), done=True)


def scan_unknown_senders_for_delete(limit: int = 1000, filters: Optional[dict] = None):
    """Scan emails and group by sender, excluding known senders.

    Like scan_senders_for_delete but filters out senders from the known senders cache.
    The cache must be built first using build_known_senders_cache().

    Args:
        limit: Maximum emails to scan. 0 = scan all (no limit).
        filters: Optional Gmail filter options.
    """
    if limit < 0:
        state.reset_delete_scan()
        state.update_delete_scan_status(error="Limit cannot be negative", done=True)
        return

    # Get known senders cache
    known_senders = state.get_known_senders()
    if not known_senders:
        state.reset_delete_scan()
        state.update_delete_scan_status(
            error="Known senders cache not built. Build it first.", done=True
        )
        return

    scan_all = limit == 0
    state.reset_delete_scan()
    state.update_delete_scan_status(message="Connecting to Gmail...")

    service, error = get_gmail_service()
    if error:
        state.update_delete_scan_status(error=error, done=True)
        return

    try:
        state.update_delete_scan_status(message="Fetching emails...")

        query = build_gmail_query(filters)

        max_results = 500 if scan_all else min(limit, 500)
        results = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=query or None)
            .execute()
        )

        messages = results.get("messages", [])

        while "nextPageToken" in results and (scan_all or len(messages) < limit):
            max_results = 500 if scan_all else min(limit - len(messages), 500)
            results = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=max_results,
                    pageToken=results["nextPageToken"],
                    q=query or None,
                )
                .execute()
            )
            messages.extend(results.get("messages", []))

        if not scan_all:
            messages = messages[:limit]
        total = len(messages)

        if total == 0:
            state.update_delete_scan_status(message="No emails found", done=True)
            return

        state.update_delete_scan_status(
            message=f"Scanning {total} emails (filtering {len(known_senders)} known)..."
        )

        # Group by sender using Gmail Batch API
        sender_counts: dict[str, dict] = defaultdict(
            lambda: {
                "count": 0,
                "sender": "",
                "email": "",
                "domain": "",
                "subjects": [],
                "first_date": None,
                "last_date": None,
                "message_ids": [],
                "total_size": 0,
                "recipients": set(),
            }
        )
        processed = 0
        skipped = 0
        batch_size = 100

        def process_message(request_id, response, exception) -> None:
            nonlocal processed, skipped
            processed += 1

            if exception:
                return

            headers = response.get("payload", {}).get("headers", [])
            sender_name, sender_email = get_sender_info(headers)

            # Skip known senders (case-insensitive match)
            if sender_email.lower() in known_senders:
                skipped += 1
                return

            subject = get_subject(headers)
            msg_id = response.get("id", "")
            size_estimate = response.get("sizeEstimate", 0)

            email_date = None
            for header in headers:
                if header["name"].lower() == "date":
                    email_date = header["value"]
                    break

            if sender_email:
                sender_counts[sender_email]["count"] += 1
                sender_counts[sender_email]["sender"] = sender_name
                sender_counts[sender_email]["email"] = sender_email
                sender_counts[sender_email]["message_ids"].append(msg_id)
                sender_counts[sender_email]["total_size"] += size_estimate
                if len(sender_counts[sender_email]["subjects"]) < 3:
                    sender_counts[sender_email]["subjects"].append(subject)

                # Extract domain from sender email
                domain = (
                    sender_email.split("@")[-1].lower()
                    if "@" in sender_email
                    else sender_email
                )
                sender_counts[sender_email]["domain"] = domain

                # Extract recipients from To header
                recipients = get_recipients_from_headers(headers)
                sender_counts[sender_email]["recipients"].update(recipients)

                if email_date:
                    if sender_counts[sender_email]["first_date"] is None:
                        sender_counts[sender_email]["first_date"] = email_date
                    sender_counts[sender_email]["last_date"] = email_date

        # Execute batch requests
        for i in range(0, len(messages), batch_size):
            batch_ids = messages[i : i + batch_size]
            batch = service.new_batch_http_request(callback=process_message)

            for msg_data in batch_ids:
                batch.add(
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_data["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date", "To"],
                    )
                )

            batch.execute()

            progress = int((i + len(batch_ids)) / total * 100)
            state.update_delete_scan_status(
                progress=progress,
                message=f"Scanned {processed}/{total} emails ({skipped} known skipped)",
            )

        # Convert recipient sets to lists before returning
        for sender_data in sender_counts.values():
            sender_data["recipients"] = list(sender_data["recipients"])

        # Sort by count
        sorted_senders = sorted(
            [{"email": k, **v} for k, v in sender_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )

        state.set_delete_scan_results(sorted_senders)
        state.update_delete_scan_status(
            message=f"Found {len(sorted_senders)} unknown senders ({skipped} known skipped)",
            done=True,
        )

    except Exception as e:
        logger.exception("Error scanning unknown senders")
        state.update_delete_scan_status(error=str(e), done=True)


def get_known_senders_status() -> dict:
    """Get known senders cache build status."""
    return state.get_known_senders_status()
