from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import security
from ..deps import (COOKIE, admin_login_limiter, client_ip, current_session, get_svc,
                    student_login_limiter)
from ..services import auth_service
from ..services.factory import Services

router = APIRouter()


class StudentLogin(BaseModel):
    reg_no: str = Field(max_length=40)


class AdminLogin(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=200)


def _set_cookie(resp: Response, svc: Services, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/",
                    secure=svc.settings.cookie_secure, max_age=svc.settings.session_hours * 3600)


@router.post("/student/login")
def student_login(body: StudentLogin, request: Request, resp: Response, svc: Services = Depends(get_svc)):
    if not student_login_limiter.allow(client_ip(request)):
        raise HTTPException(429, "Too many attempts. Wait a few minutes.")
    try:
        reg = auth_service.student_login(svc.db, body.reg_no)
    except auth_service.AuthError as e:
        raise HTTPException(401, str(e))
    _set_cookie(resp, svc, auth_service.issue_session(svc.db, svc.settings, "student", reg))
    return {"role": "student", "subject": reg}


@router.post("/admin/login")
def admin_login(body: AdminLogin, request: Request, resp: Response, svc: Services = Depends(get_svc)):
    if not admin_login_limiter.allow(client_ip(request)):
        raise HTTPException(429, "Too many attempts. Wait a few minutes.")
    try:
        user = auth_service.admin_login(svc.db, body.username, body.password)
    except auth_service.AuthError as e:
        raise HTTPException(401, str(e))
    _set_cookie(resp, svc, auth_service.issue_session(svc.db, svc.settings, "admin", user))
    return {"role": "admin", "subject": user}


@router.post("/logout")
def logout(request: Request, resp: Response, svc: Services = Depends(get_svc)):
    token = request.cookies.get(COOKIE)
    if token:
        svc.db.delete_session(security.hash_token(token))
    resp.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(s: dict = Depends(current_session)):
    return s
