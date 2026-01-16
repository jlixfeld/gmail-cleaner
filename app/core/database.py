"""
Database Module
---------------
SQLite database for persistent storage of valid senders and known recipients.
Uses per-Gmail-account isolation via user_email column.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Generator


# Thread-local storage for connections
_local = threading.local()

# Lock for database initialization
_init_lock = threading.Lock()
_initialized = False


# ----- Connection Management -----


def get_db_path() -> str:
    """Get the database file path.

    Returns /app/data/gmail_cleaner.db in Docker environments,
    otherwise returns data/gmail_cleaner.db relative to working directory.
    """
    if os.path.exists("/app/data") and os.path.isdir("/app/data"):
        return "/app/data/gmail_cleaner.db"
    else:
        # Create data directory if it doesn't exist
        data_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "gmail_cleaner.db")


def get_connection() -> sqlite3.Connection:
    """Get a thread-local database connection.

    Uses check_same_thread=False for thread safety and enables
    foreign keys and WAL mode for better performance.
    """
    if not hasattr(_local, "connection") or _local.connection is None:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.connection = conn
    return _local.connection


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database operations.

    Yields a database connection and handles commit/rollback automatically.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_database() -> None:
    """Initialize the database schema.

    Creates tables if they don't exist. Thread-safe and idempotent.
    """
    global _initialized

    with _init_lock:
        if _initialized:
            return

        with get_db() as conn:
            conn.executescript("""
                -- Valid senders whitelist (per Gmail account)
                CREATE TABLE IF NOT EXISTS valid_senders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_email TEXT NOT NULL,
                    sender_email TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_email, sender_email)
                );
                CREATE INDEX IF NOT EXISTS idx_valid_senders_user
                    ON valid_senders(user_email);
                CREATE INDEX IF NOT EXISTS idx_valid_senders_lookup
                    ON valid_senders(user_email, sender_email);

                -- Recipients from sent mail (per Gmail account)
                CREATE TABLE IF NOT EXISTS my_recipients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_email TEXT NOT NULL,
                    recipient_email TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_email, recipient_email)
                );
                CREATE INDEX IF NOT EXISTS idx_my_recipients_user
                    ON my_recipients(user_email);
                CREATE INDEX IF NOT EXISTS idx_my_recipients_lookup
                    ON my_recipients(user_email, recipient_email);

                -- Recipient overrides (marks known recipients as deletable)
                CREATE TABLE IF NOT EXISTS recipient_overrides (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_email TEXT NOT NULL,
                    sender_email TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_email, sender_email)
                );
                CREATE INDEX IF NOT EXISTS idx_recipient_overrides_user
                    ON recipient_overrides(user_email);
                CREATE INDEX IF NOT EXISTS idx_recipient_overrides_lookup
                    ON recipient_overrides(user_email, sender_email);
            """)

        _initialized = True


# ----- Valid Senders CRUD -----


def add_valid_sender(user_email: str, sender_email: str) -> bool:
    """Add a sender to the valid senders whitelist.

    Args:
        user_email: The Gmail account email
        sender_email: The sender email to whitelist

    Returns:
        True if added, False if already exists
    """
    user_email = user_email.lower().strip()
    sender_email = sender_email.lower().strip()

    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO valid_senders (user_email, sender_email) VALUES (?, ?)",
                (user_email, sender_email),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def remove_valid_sender(user_email: str, sender_email: str) -> bool:
    """Remove a sender from the valid senders whitelist.

    Args:
        user_email: The Gmail account email
        sender_email: The sender email to remove

    Returns:
        True if removed, False if not found
    """
    user_email = user_email.lower().strip()
    sender_email = sender_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM valid_senders WHERE user_email = ? AND sender_email = ?",
            (user_email, sender_email),
        )
        return cursor.rowcount > 0


def get_valid_senders(user_email: str) -> set[str]:
    """Get all valid senders for a user.

    Args:
        user_email: The Gmail account email

    Returns:
        Set of whitelisted sender emails (lowercase)
    """
    user_email = user_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT sender_email FROM valid_senders WHERE user_email = ?",
            (user_email,),
        )
        return {row["sender_email"] for row in cursor.fetchall()}


def get_valid_senders_list(user_email: str) -> list[dict]:
    """Get all valid senders with metadata for display.

    Args:
        user_email: The Gmail account email

    Returns:
        List of dicts with sender_email and created_at
    """
    user_email = user_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT sender_email, created_at FROM valid_senders "
            "WHERE user_email = ? ORDER BY sender_email",
            (user_email,),
        )
        return [
            {"sender_email": row["sender_email"], "created_at": row["created_at"]}
            for row in cursor.fetchall()
        ]


def is_valid_sender(user_email: str, sender_email: str) -> bool:
    """Check if a sender is in the valid senders whitelist.

    Args:
        user_email: The Gmail account email
        sender_email: The sender email to check

    Returns:
        True if sender is whitelisted
    """
    user_email = user_email.lower().strip()
    sender_email = sender_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM valid_senders WHERE user_email = ? AND sender_email = ?",
            (user_email, sender_email),
        )
        return cursor.fetchone() is not None


# ----- My Recipients CRUD -----


def sync_recipients(user_email: str, recipients: set[str]) -> int:
    """Sync recipients from sent mail scan to database.

    Uses INSERT OR IGNORE for idempotent upserts.

    Args:
        user_email: The Gmail account email
        recipients: Set of recipient emails to add

    Returns:
        Number of new recipients added
    """
    user_email = user_email.lower().strip()
    added = 0

    with get_db() as conn:
        for recipient in recipients:
            recipient = recipient.lower().strip()
            try:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO my_recipients (user_email, recipient_email) "
                    "VALUES (?, ?)",
                    (user_email, recipient),
                )
                if cursor.rowcount > 0:
                    added += 1
            except sqlite3.Error:
                continue

    return added


def get_my_recipients(user_email: str) -> set[str]:
    """Get all recipients for a user.

    Args:
        user_email: The Gmail account email

    Returns:
        Set of recipient emails (lowercase)
    """
    user_email = user_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT recipient_email FROM my_recipients WHERE user_email = ?",
            (user_email,),
        )
        return {row["recipient_email"] for row in cursor.fetchall()}


def get_my_recipients_list(user_email: str) -> list[dict]:
    """Get all recipients with metadata for display.

    Args:
        user_email: The Gmail account email

    Returns:
        List of dicts with recipient_email and created_at
    """
    user_email = user_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT recipient_email, created_at FROM my_recipients "
            "WHERE user_email = ? ORDER BY recipient_email",
            (user_email,),
        )
        return [
            {"recipient_email": row["recipient_email"], "created_at": row["created_at"]}
            for row in cursor.fetchall()
        ]


def get_my_recipients_count(user_email: str) -> int:
    """Get count of recipients for a user.

    Args:
        user_email: The Gmail account email
    """
    user_email = user_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM my_recipients WHERE user_email = ?",
            (user_email,),
        )
        return cursor.fetchone()["count"]


def clear_my_recipients(user_email: str) -> int:
    """Clear all recipients for a user (used before rescan).

    Args:
        user_email: The Gmail account email

    Returns:
        Number of recipients cleared
    """
    user_email = user_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM my_recipients WHERE user_email = ?",
            (user_email,),
        )
        return cursor.rowcount


# ----- Recipient Overrides CRUD -----


def add_recipient_override(user_email: str, sender_email: str) -> bool:
    """Add a sender to the recipient overrides list.

    Marks a known recipient as deletable (overrides my_recipients protection).

    Args:
        user_email: The Gmail account email
        sender_email: The sender email to mark as deletable

    Returns:
        True if added, False if already exists
    """
    user_email = user_email.lower().strip()
    sender_email = sender_email.lower().strip()

    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO recipient_overrides (user_email, sender_email) VALUES (?, ?)",
                (user_email, sender_email),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def remove_recipient_override(user_email: str, sender_email: str) -> bool:
    """Remove a sender from the recipient overrides list.

    Args:
        user_email: The Gmail account email
        sender_email: The sender email to remove from overrides

    Returns:
        True if removed, False if not found
    """
    user_email = user_email.lower().strip()
    sender_email = sender_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM recipient_overrides WHERE user_email = ? AND sender_email = ?",
            (user_email, sender_email),
        )
        return cursor.rowcount > 0


def get_recipient_overrides(user_email: str) -> set[str]:
    """Get all recipient overrides for a user.

    Args:
        user_email: The Gmail account email

    Returns:
        Set of sender emails marked as deletable (lowercase)
    """
    user_email = user_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT sender_email FROM recipient_overrides WHERE user_email = ?",
            (user_email,),
        )
        return {row["sender_email"] for row in cursor.fetchall()}


def get_recipient_overrides_list(user_email: str) -> list[dict]:
    """Get all recipient overrides with metadata for display.

    Args:
        user_email: The Gmail account email

    Returns:
        List of dicts with sender_email and created_at
    """
    user_email = user_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT sender_email, created_at FROM recipient_overrides "
            "WHERE user_email = ? ORDER BY sender_email",
            (user_email,),
        )
        return [
            {"sender_email": row["sender_email"], "created_at": row["created_at"]}
            for row in cursor.fetchall()
        ]


def is_recipient_override(user_email: str, sender_email: str) -> bool:
    """Check if a sender is in the recipient overrides list.

    Args:
        user_email: The Gmail account email
        sender_email: The sender email to check

    Returns:
        True if sender is marked as deletable override
    """
    user_email = user_email.lower().strip()
    sender_email = sender_email.lower().strip()

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM recipient_overrides WHERE user_email = ? AND sender_email = ?",
            (user_email, sender_email),
        )
        return cursor.fetchone() is not None
