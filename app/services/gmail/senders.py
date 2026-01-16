"""
Gmail Senders Service
---------------------
Functions for managing valid senders and scanning recipients from sent mail.
"""

import logging
from typing import Optional

from app.core import state
from app.services.gmail.delete import execute_with_retry, execute_batch_with_retry
from app.core.database import (
    add_valid_sender as db_add_valid_sender,
    remove_valid_sender as db_remove_valid_sender,
    get_valid_senders as db_get_valid_senders,
    get_valid_senders_list as db_get_valid_senders_list,
    is_valid_sender as db_is_valid_sender,
    get_my_recipients as db_get_my_recipients,
    get_my_recipients_list as db_get_my_recipients_list,
    get_my_recipients_count as db_get_my_recipients_count,
    sync_recipients as db_sync_recipients,
    clear_my_recipients as db_clear_my_recipients,
    add_recipient_override as db_add_recipient_override,
    remove_recipient_override as db_remove_recipient_override,
    get_recipient_overrides as db_get_recipient_overrides,
    get_recipient_overrides_list as db_get_recipient_overrides_list,
)
from app.services.auth import get_gmail_service
from app.services.gmail.helpers import get_recipients_from_headers

logger = logging.getLogger(__name__)


# =============================================================================
# VALID SENDERS MANAGEMENT
# =============================================================================


def add_valid_sender(sender_email: str) -> dict:
    """
    Add a sender to the valid senders whitelist.

    **Args:**
        - `sender_email`: The sender email to whitelist

    **Returns:**
        Dict with success status and current state
    """
    user = state.get_current_user()
    if not user.get("email"):
        return {"success": False, "error": "Not logged in", "is_valid": False}

    user_email = user["email"]
    added = db_add_valid_sender(user_email, sender_email)

    return {
        "success": True,
        "sender_email": sender_email.lower().strip(),
        "is_valid": True,
        "added": added,
    }


def remove_valid_sender(sender_email: str) -> dict:
    """
    Remove a sender from the valid senders whitelist.

    **Args:**
        - `sender_email`: The sender email to remove

    **Returns:**
        Dict with success status and current state
    """
    user = state.get_current_user()
    if not user.get("email"):
        return {"success": False, "error": "Not logged in", "is_valid": False}

    user_email = user["email"]
    removed = db_remove_valid_sender(user_email, sender_email)

    return {
        "success": True,
        "sender_email": sender_email.lower().strip(),
        "is_valid": False,
        "removed": removed,
    }


def get_valid_senders() -> set[str]:
    """
    Get all valid senders for the current user.

    **Returns:**
        Set of whitelisted sender emails (lowercase)
    """
    user = state.get_current_user()
    if not user.get("email"):
        return set()

    return db_get_valid_senders(user["email"])


def get_valid_senders_list() -> list[dict]:
    """
    Get all valid senders with metadata for display.

    **Returns:**
        List of dicts with sender_email and created_at
    """
    user = state.get_current_user()
    if not user.get("email"):
        return []

    return db_get_valid_senders_list(user["email"])


def is_valid_sender(sender_email: str) -> bool:
    """
    Check if a sender is in the valid senders whitelist.

    **Args:**
        - `sender_email`: The sender email to check

    **Returns:**
        True if sender is whitelisted
    """
    user = state.get_current_user()
    if not user.get("email"):
        return False

    return db_is_valid_sender(user["email"], sender_email)


# =============================================================================
# MY RECIPIENTS MANAGEMENT
# =============================================================================


def get_my_recipients() -> set[str]:
    """
    Get all recipients from sent mail for the current user.

    **Returns:**
        Set of recipient emails (lowercase)
    """
    user = state.get_current_user()
    if not user.get("email"):
        return set()

    return db_get_my_recipients(user["email"])


def get_my_recipients_list() -> list[dict]:
    """
    Get all recipients with metadata for display.

    **Returns:**
        List of dicts with recipient_email and created_at
    """
    user = state.get_current_user()
    if not user.get("email"):
        return []

    return db_get_my_recipients_list(user["email"])


def get_my_recipients_count() -> int:
    """
    Get count of recipients for the current user.

    **Returns:**
        Number of recipients
    """
    user = state.get_current_user()
    if not user.get("email"):
        return 0

    return db_get_my_recipients_count(user["email"])


def get_recipients_scan_status() -> dict:
    """Get the current recipients scan status."""
    return state.get_recipients_scan_status()


# =============================================================================
# RECIPIENT OVERRIDES MANAGEMENT
# =============================================================================


def add_recipient_override(sender_email: str) -> dict:
    """
    Add a sender to the recipient overrides list.

    Marks a known recipient as deletable (overrides my_recipients protection).

    **Args:**
        - `sender_email`: The sender email to mark as deletable

    **Returns:**
        Dict with success status and current state
    """
    user = state.get_current_user()
    if not user.get("email"):
        return {"success": False, "error": "Not logged in", "is_override": False}

    user_email = user["email"]
    added = db_add_recipient_override(user_email, sender_email)

    return {
        "success": True,
        "sender_email": sender_email.lower().strip(),
        "is_override": True,
        "added": added,
    }


def remove_recipient_override(sender_email: str) -> dict:
    """
    Remove a sender from the recipient overrides list.

    **Args:**
        - `sender_email`: The sender email to remove from overrides

    **Returns:**
        Dict with success status and current state
    """
    user = state.get_current_user()
    if not user.get("email"):
        return {"success": False, "error": "Not logged in", "is_override": False}

    user_email = user["email"]
    removed = db_remove_recipient_override(user_email, sender_email)

    return {
        "success": True,
        "sender_email": sender_email.lower().strip(),
        "is_override": False,
        "removed": removed,
    }


def get_recipient_overrides() -> set[str]:
    """
    Get all recipient overrides for the current user.

    **Returns:**
        Set of sender emails marked as deletable (lowercase)
    """
    user = state.get_current_user()
    if not user.get("email"):
        return set()

    return db_get_recipient_overrides(user["email"])


def get_recipient_overrides_list() -> list[dict]:
    """
    Get all recipient overrides with metadata for display.

    **Returns:**
        List of dicts with sender_email and created_at
    """
    user = state.get_current_user()
    if not user.get("email"):
        return []

    return db_get_recipient_overrides_list(user["email"])


# =============================================================================
# RECIPIENTS SCANNING
# =============================================================================


def scan_recipients_background(filters: Optional[dict] = None):
    """
    Scan sent mail and store recipients to database.

    This is triggered automatically when the Delete Emails tab is selected.
    It scans all sent emails and extracts recipients (To, Cc, Bcc).

    **Args:**
        - `filters`: Optional filter options (not typically used for sent scan)
    """
    user = state.get_current_user()
    if not user.get("email"):
        state.update_recipients_scan_status(error="Not logged in", done=True)
        return

    user_email = user["email"]

    state.reset_recipients_scan()
    state.update_recipients_scan_status(
        message="Compiling list of previous recipients from sent mail..."
    )

    service, error = get_gmail_service()
    if error:
        state.update_recipients_scan_status(error=error, done=True)
        return

    try:
        state.update_recipients_scan_status(message="Fetching sent emails...")

        # Query all sent emails (no limit - we want comprehensive coverage)
        results = execute_with_retry(
            service.users().messages().list(userId="me", maxResults=500, q="in:sent"),
            "list sent messages",
        )

        all_messages = results.get("messages", [])

        # Paginate through all sent emails
        while "nextPageToken" in results:
            results = execute_with_retry(
                service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=500,
                    pageToken=results["nextPageToken"],
                    q="in:sent",
                ),
                "list sent messages (pagination)",
            )
            all_messages.extend(results.get("messages", []))

            # Update progress during pagination
            state.update_recipients_scan_status(
                message=f"Found {len(all_messages)} sent emails..."
            )

        total = len(all_messages)
        if total == 0:
            state.update_recipients_scan_status(
                message="No sent emails found",
                done=True,
                recipient_count=0,
                scanned_emails=0,
            )
            return

        state.update_recipients_scan_status(
            message=f"Scanning {total} sent emails for recipients..."
        )

        # Extract recipients from all sent emails
        all_recipients: set[str] = set()
        processed = 0
        failed_ids: list[str] = []
        batch_size = 25  # Reduced from 100 to avoid "too many concurrent requests"

        def process_message(request_id, response, exception) -> None:
            nonlocal processed
            processed += 1

            if exception:
                # Track failed message IDs for retry
                # request_id format is typically "0", "1", etc. within the batch
                return

            headers = response.get("payload", {}).get("headers", [])
            recipients = get_recipients_from_headers(headers)
            all_recipients.update(recipients)

        # Execute batch requests, tracking failures
        for i in range(0, len(all_messages), batch_size):
            batch_ids = all_messages[i : i + batch_size]
            batch_failed: list[str] = []

            def make_callback(msg_id):
                def callback(request_id, response, exception):
                    nonlocal processed
                    processed += 1
                    if exception:
                        batch_failed.append(msg_id)
                        # Log first few failures to understand the cause
                        if len(batch_failed) <= 3:
                            logger.warning(f"Batch message fetch failed: {exception}")
                        return
                    headers = response.get("payload", {}).get("headers", [])
                    recipients = get_recipients_from_headers(headers)
                    all_recipients.update(recipients)

                return callback

            batch = service.new_batch_http_request()
            for msg_data in batch_ids:
                batch.add(
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_data["id"],
                        format="metadata",
                        metadataHeaders=["To", "Cc", "Bcc"],
                    ),
                    callback=make_callback(msg_data["id"]),
                )

            execute_batch_with_retry(batch, f"recipients batch {i // batch_size + 1}")
            failed_ids.extend(batch_failed)

            progress = int((i + len(batch_ids)) / total * 100)
            state.update_recipients_scan_status(
                progress=progress,
                message=f"Processed {processed}/{total} sent emails",
                scanned_emails=processed,
                recipient_count=len(all_recipients),
            )

        # Retry failed messages individually (with smaller batches)
        if failed_ids:
            logger.info(f"Retrying {len(failed_ids)} failed message fetches")
            retry_batch_size = 10
            for i in range(0, len(failed_ids), retry_batch_size):
                retry_ids = failed_ids[i : i + retry_batch_size]
                retry_batch = service.new_batch_http_request()

                for msg_id in retry_ids:
                    retry_batch.add(
                        service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=msg_id,
                            format="metadata",
                            metadataHeaders=["To", "Cc", "Bcc"],
                        ),
                        callback=process_message,
                    )

                try:
                    execute_batch_with_retry(
                        retry_batch, f"retry batch {i // retry_batch_size + 1}"
                    )
                except Exception as e:
                    logger.warning(f"Retry batch failed: {e}")

        # Clear existing recipients and sync new ones
        db_clear_my_recipients(user_email)
        db_sync_recipients(user_email, all_recipients)

        state.update_recipients_scan_status(
            progress=100,
            done=True,
            message=f"Found {len(all_recipients)} recipients from {total} sent emails",
            recipient_count=len(all_recipients),
            scanned_emails=total,
        )

        logger.info(
            f"Recipients scan complete: {len(all_recipients)} recipients from {total} emails"
        )

    except Exception as e:
        logger.exception("Error scanning recipients")
        state.update_recipients_scan_status(error=str(e), done=True)
