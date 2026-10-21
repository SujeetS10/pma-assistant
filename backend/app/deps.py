"""FastAPI dependencies: service container, session lookup, role guards, rate limiters."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from . import security
from .security import RateLimiter
from .services.factory import Services

COOKIE = "pma_session"

admin_login_limiter = RateLimiter(10, 300)
student_login_limiter = RateLimiter(40, 300)
chat_limiter = RateLimiter(20, 60)


def get_svc(request: Request) -> Services:
    return request.app.state.svc


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def current_session(request: Request, svc: Services = Depends(get_svc)) -> dict:
    token = request.cookies.get(COOKIE)
    row = svc.db.get_session(security.hash_token(token)) if token else None
    if row is None:
        raise HTTPException(401, "Not signed in or session expired.")
    return {"role": row["role"], "subject": row["subject"]}


def require_admin(s: dict = Depends(current_session)) -> str:
    if s["role"] != "admin":
        raise HTTPException(403, "Admin access required.")
    return s["subject"]


def require_student(s: dict = Depends(current_session)) -> str:
    if s["role"] != "student":
        raise HTTPException(403, "Student access required.")
    return s["subject"]
