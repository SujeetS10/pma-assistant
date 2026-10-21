"""Password hashing, session tokens, register-number validation, rate limiting (stdlib only)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict, deque

_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)
_REG = re.compile(r"^[A-Z0-9][A-Z0-9/_-]{3,24}$")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
        got = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_reg_no(raw: str) -> str | None:
    """Upper-case and validate a register number; None if it is not acceptable."""
    v = (raw or "").strip().upper()
    return v if _REG.match(v) else None


def password_problem(pw: str) -> str | None:
    if len(pw) < 10:
        return "Password must be at least 10 characters."
    if pw.lower() in {"password123", "changeme123", "replace_me_please", "replace_with_a_long_password"}:
        return "Password is a known placeholder; choose a real one."
    return None


class RateLimiter:
    """Sliding-window limiter, in memory (per process)."""

    def __init__(self, max_events: int, window_s: float):
        self.max, self.window = max_events, window_s
        self._events: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._events[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max:
                return False
            q.append(now)
            return True
