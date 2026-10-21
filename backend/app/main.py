"""FastAPI entry point: JSON API under /api, static frontend at /."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .config import REPO_ROOT, Settings
from .routers import admin, auth, student
from .services import auth_service
from .services.factory import Services

log = logging.getLogger("pma")

CSP = ("default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
       "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; font-src 'self' https://cdn.jsdelivr.net data:; "
       "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    svc = services or Services(settings or Settings.from_env())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        auth_service.bootstrap_admin(svc.db, svc.settings)
        n = svc.db.fail_interrupted_docs()
        if n:
            log.warning("Marked %d interrupted document(s) as failed.", n)
        yield

    app = FastAPI(title="PMA Teaching Assistant", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.svc = svc

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(student.router, prefix="/api/student", tags=["student"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    app.mount("/", StaticFiles(directory=REPO_ROOT / "frontend", html=True), name="frontend")
    return app




def get_app() -> FastAPI:  # uvicorn --factory app.main:get_app
    return create_app()
