"""Login logic, independent of the web framework so it can be unit-tested."""
from __future__ import annotations

import logging

from .. import security
from ..config import Settings
from ..db import Database

log = logging.getLogger("pma.auth")
_DUMMY_HASH = security.hash_password("dummy-password-for-timing")


class AuthError(Exception):
    """Message is safe to show to the user."""


def student_login(db: Database, raw_reg_no: str) -> str:
    reg = security.normalize_reg_no(raw_reg_no)
    if reg is None:
        raise AuthError("Enter a valid register number (letters/digits, 4-25 characters).")
    if db.get_setting("roster_mode", "open") == "roster" and not db.roster_has(reg):
        raise AuthError("This register number is not enrolled for this course. Contact your instructor.")
    db.touch_student(reg)
    return reg


def admin_login(db: Database, username: str, password: str) -> str:
    row = db.get_admin((username or "").strip())
    stored = row["password_hash"] if row else _DUMMY_HASH  # equal work whether or not the user exists
    ok = security.verify_password(password or "", stored)
    if not (row and ok):
        raise AuthError("Invalid username or password.")
    return row["username"]


def issue_session(db: Database, settings: Settings, role: str, subject: str) -> str:
    token = security.new_token()
    db.create_session(security.hash_token(token), role, subject, settings.session_hours * 3600)
    return token


def bootstrap_admin(db: Database, s: Settings) -> None:
    """Create/refresh the admin from ADMIN_USERNAME/ADMIN_PASSWORD (editing .env changes the password)."""
    if s.admin_username and s.admin_password:
        problem = security.password_problem(s.admin_password)
        if problem:
            raise SystemExit(f"ADMIN_PASSWORD rejected: {problem}")
        db.upsert_admin(s.admin_username.strip(), security.hash_password(s.admin_password))
        log.info("Admin account '%s' ready.", s.admin_username)
    elif db.admin_count() == 0:
        log.warning("No admin exists. Set ADMIN_USERNAME and ADMIN_PASSWORD in .env, or run scripts/create_admin.py.")
