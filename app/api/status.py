"""
Status API Routes
-----------------
GET endpoints for checking status of various operations.

Rate limits:
- Most status endpoints: 120 requests/minute (high frequency polling)
- Auth endpoints: 30 requests/minute
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response

from app.core.rate_limit import limiter, STATUS_RATE_LIMIT, AUTH_RATE_LIMIT
from app.services import (
    get_scan_status,
    get_scan_results,
    check_login_status,
    get_web_auth_status,
    get_unread_count,
    get_mark_read_status,
    get_delete_scan_status,
    get_delete_scan_results,
    get_delete_bulk_status,
    get_download_status,
    get_download_csv,
    get_labels,
    get_label_operation_status,
    get_archive_status,
    get_important_status,
    get_unread_scan_status,
    get_unread_scan_results,
    get_unread_action_status,
    get_known_senders_status,
    get_valid_senders_list,
    get_my_recipients_list,
    get_recipients_scan_status,
    get_recipient_overrides_list,
)

router = APIRouter(prefix="/api", tags=["Status"])
logger = logging.getLogger(__name__)


# ----- Scan & Unsubscribe Endpoints -----


@router.get("/status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_status(request: Request):
    """Get email scan status."""
    try:
        return get_scan_status()
    except Exception as e:
        logger.exception("Error getting scan status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scan status",
        ) from e


@router.get("/results")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_results(request: Request):
    """Get email scan results."""
    try:
        return get_scan_results()
    except Exception as e:
        logger.exception("Error getting scan results")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scan results",
        ) from e


# ----- Authentication Endpoints -----


@router.get("/auth-status")
@limiter.limit(AUTH_RATE_LIMIT)
async def api_auth_status(request: Request):
    """Get authentication status."""
    try:
        return check_login_status()
    except Exception as e:
        logger.exception("Error getting auth status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get auth status",
        ) from e


@router.get("/web-auth-status")
@limiter.limit(AUTH_RATE_LIMIT)
async def api_web_auth_status(request: Request):
    """Get web auth status for Docker/headless mode."""
    try:
        return get_web_auth_status()
    except Exception as e:
        logger.exception("Error getting web auth status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get web auth status",
        ) from e


# ----- Mark Read Endpoints -----


@router.get("/unread-count")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_unread_count(request: Request):
    """Get unread email count."""
    try:
        return get_unread_count()
    except Exception as e:
        logger.exception("Error getting unread count")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unread count",
        ) from e


@router.get("/mark-read-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_mark_read_status(request: Request):
    """Get mark-as-read operation status."""
    try:
        return get_mark_read_status()
    except Exception as e:
        logger.exception("Error getting mark-read status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mark-read status",
        ) from e


# ----- Delete Scan Endpoints -----


@router.get("/delete-scan-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_delete_scan_status(request: Request):
    """Get delete scan status."""
    try:
        return get_delete_scan_status()
    except Exception as e:
        logger.exception("Error getting delete scan status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get delete scan status",
        ) from e


@router.get("/delete-scan-results")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_delete_scan_results(request: Request):
    """Get delete scan results (senders grouped by count)."""
    try:
        return get_delete_scan_results()
    except Exception as e:
        logger.exception("Error getting delete scan results")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get delete scan results",
        ) from e


@router.get("/download-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_download_status(request: Request):
    """Get download operation status."""
    try:
        return get_download_status()
    except Exception as e:
        logger.exception("Error getting download status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get download status",
        ) from e


@router.get("/download-csv")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_download_csv(request: Request):
    """Get the generated CSV file."""
    try:
        csv_data = get_download_csv()
        if not csv_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No CSV data available",
            )

        filename = f"emails-backup-{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M%S')}.csv"

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error getting CSV download")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get CSV download",
        ) from e


@router.get("/delete-bulk-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_delete_bulk_status(request: Request):
    """Get bulk delete operation status."""
    try:
        return get_delete_bulk_status()
    except Exception as e:
        logger.exception("Error getting delete bulk status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get delete bulk status",
        ) from e


# ----- Label Management Endpoints -----


@router.get("/labels")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_get_labels(request: Request):
    """Get all Gmail labels."""
    try:
        return get_labels()
    except Exception as e:
        logger.exception("Error getting labels")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get labels",
        ) from e


@router.get("/label-operation-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_label_operation_status(request: Request):
    """Get label operation status (apply/remove)."""
    try:
        return get_label_operation_status()
    except Exception as e:
        logger.exception("Error getting label operation status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get label operation status",
        ) from e


@router.get("/archive-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_archive_status(request: Request):
    """Get archive operation status."""
    try:
        return get_archive_status()
    except Exception as e:
        logger.exception("Error getting archive status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get archive status",
        ) from e


@router.get("/important-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_important_status(request: Request):
    """Get mark important operation status."""
    try:
        return get_important_status()
    except Exception as e:
        logger.exception("Error getting important status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get important status",
        ) from e


# ----- Unread Email Endpoints -----


@router.get("/unread-scan-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_unread_scan_status(request: Request):
    """Get unread scan status."""
    try:
        return get_unread_scan_status()
    except Exception as e:
        logger.exception("Error getting unread scan status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unread scan status",
        ) from e


@router.get("/unread-scan-results")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_unread_scan_results(request: Request):
    """Get unread scan results (senders grouped by count)."""
    try:
        return get_unread_scan_results()
    except Exception as e:
        logger.exception("Error getting unread scan results")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unread scan results",
        ) from e


@router.get("/unread-action-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_unread_action_status(request: Request):
    """Get unread action (mark read/archive) status."""
    try:
        return get_unread_action_status()
    except Exception as e:
        logger.exception("Error getting unread action status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unread action status",
        ) from e


# ----- Unknown Sender Endpoints -----


@router.get("/known-senders-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_known_senders_status(request: Request):
    """Get known senders cache build status."""
    try:
        return get_known_senders_status()
    except Exception as e:
        logger.exception("Error getting known senders status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get known senders status",
        ) from e


# ----- Valid Senders & Recipients Endpoints -----


@router.get("/valid-senders")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_get_valid_senders(request: Request):
    """Get list of valid senders for current user."""
    try:
        return {"senders": get_valid_senders_list()}
    except Exception as e:
        logger.exception("Error getting valid senders")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get valid senders",
        ) from e


@router.get("/my-recipients")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_get_my_recipients(request: Request):
    """Get list of recipients from sent mail for current user."""
    try:
        return {"recipients": get_my_recipients_list()}
    except Exception as e:
        logger.exception("Error getting recipients")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get recipients",
        ) from e


@router.get("/recipients-scan-status")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_recipients_scan_status(request: Request):
    """Get recipients scan status."""
    try:
        return get_recipients_scan_status()
    except Exception as e:
        logger.exception("Error getting recipients scan status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get recipients scan status",
        ) from e


@router.get("/recipient-overrides")
@limiter.limit(STATUS_RATE_LIMIT)
async def api_get_recipient_overrides(request: Request):
    """Get list of recipient overrides for current user."""
    try:
        return {"overrides": get_recipient_overrides_list()}
    except Exception as e:
        logger.exception("Error getting recipient overrides")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get recipient overrides",
        ) from e
