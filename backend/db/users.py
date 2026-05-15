"""
User management functions.
"""

import logging
import secrets

from db.connection import get_sqlite

log = logging.getLogger(__name__)


def get_user_by_clerk_id(clerk_user_id: str) -> dict | None:
    """Return the local user row matching a Clerk user ID, or None."""
    with get_sqlite() as conn:
        row = conn.execute(
            "SELECT id, email, is_active, is_admin FROM users WHERE clerk_user_id = ?",
            (clerk_user_id,),
        ).fetchone()
    return dict(row) if row else None


def create_user_from_clerk(clerk_user_id: str, email: str | None) -> dict:
    """Create (or claim) a local user record on first Clerk login and return it."""
    resolved_email = (email or f"{clerk_user_id}@clerk.local").lower().strip()
    token = secrets.token_urlsafe(32)
    with get_sqlite() as conn:
        conn.execute(
            """INSERT INTO users (email, password_hash, clerk_user_id, webhook_token)
               VALUES (?, '', ?, ?)
               ON CONFLICT(email) DO UPDATE SET
                   clerk_user_id = excluded.clerk_user_id,
                   webhook_token = COALESCE(users.webhook_token, excluded.webhook_token)""",
            (resolved_email, clerk_user_id, token),
        )
        row = conn.execute(
            "SELECT id, email, is_active, is_admin FROM users WHERE clerk_user_id = ?",
            (clerk_user_id,),
        ).fetchone()
    return dict(row)


def set_user_admin(email: str, is_admin: bool) -> bool:
    """Promote or demote a user by email. Returns True if a row was updated."""
    with get_sqlite() as conn:
        cursor = conn.execute(
            "UPDATE users SET is_admin = ? WHERE email = ?",
            (1 if is_admin else 0, email.lower().strip()),
        )
    return cursor.rowcount > 0


def list_users() -> list[dict]:
    """Return all user rows (id, email, is_active, is_admin, created_at)."""
    with get_sqlite() as conn:
        rows = conn.execute(
            "SELECT id, email, is_active, is_admin, created_at FROM users ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


def get_user_by_id(user_id: int) -> dict | None:
    """Return the user row for id, or None."""
    with get_sqlite() as conn:
        row = conn.execute(
            "SELECT id, email, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def create_user(email: str, password_hash: str) -> int:
    """Insert a new user and return their id."""
    with get_sqlite() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email.lower().strip(), password_hash),
        )
        return cur.lastrowid


def get_user_by_email(email: str) -> dict | None:
    """Return the user row for email, or None."""
    with get_sqlite() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? AND is_active = 1",
            (email.lower().strip(),),
        ).fetchone()
    return dict(row) if row else None


def generate_webhook_token(user_id: int) -> str:
    """Generate and store a new webhook token for user. Returns the token."""
    token = secrets.token_urlsafe(32)
    with get_sqlite() as conn:
        conn.execute("UPDATE users SET webhook_token = ? WHERE id = ?", (token, user_id))
    return token


def get_user_by_webhook_token(token: str) -> dict | None:
    """Return {id, email, is_active} for a webhook token, or None."""
    with get_sqlite() as conn:
        row = conn.execute(
            "SELECT id, email, is_active FROM users WHERE webhook_token = ?",
            (token,),
        ).fetchone()
    return dict(row) if row else None
