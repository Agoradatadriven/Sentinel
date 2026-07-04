"""Sentinel FastAPI application — REST API + static frontend server.

Run locally:  uvicorn app.main:app --reload   (from the backend/ directory)
Seed first:   python seed.py
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import create_all
from .routers import (
    admin,
    attendance,
    auth,
    gym,
    leave,
    manage,
    meta,
    notifications,
    people,
    reports,
    tasks,
)

# sentinel/backend/app/main.py -> parents[2] == sentinel/
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
PAGES_DIR = FRONTEND_DIR / "pages"

app = FastAPI(
    title="Sentinel API",
    version="1.0.0",
    description="Internal operations command center for Agora — attendance, gym, tasks, people, leave.",
)


@app.on_event("startup")
def _startup() -> None:
    # Create tables if missing (SQLite zero-setup). Prod uses Alembic migrations.
    create_all()


# --- API routers -----------------------------------------------------------
for r in (auth, attendance, gym, tasks, people, leave, notifications, reports, admin, meta, manage):
    app.include_router(r.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"ok": True, "app": settings.app_name, "env": settings.environment}


# --- Static assets ---------------------------------------------------------
# check_dir=False so the API can boot even before the frontend assets are built.
(FRONTEND_DIR / "static").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static"), check_dir=False), name="static")


def _page(name: str) -> FileResponse:
    return FileResponse(str(PAGES_DIR / name))


# PWA files must be served from the root scope.
@app.get("/manifest.json", include_in_schema=False)
def manifest():
    return FileResponse(str(FRONTEND_DIR / "manifest.json"), media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(str(FRONTEND_DIR / "sw.js"), media_type="application/javascript")


# --- Page routes (client-side auth: each page calls /api/auth/me) ----------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard")


_PAGES = {
    "/login": "login.html",
    "/dashboard": "dashboard.html",
    "/attendance": "attendance.html",
    "/gym": "gym.html",
    "/tasks": "tasks.html",
    "/people": "people.html",
    "/leave": "leave.html",
    "/reports": "reports.html",
    "/settings": "settings.html",
    "/manage": "manage.html",
    "/kiosk": "kiosk.html",
    "/scanner": "scanner.html",
}

for _route, _file in _PAGES.items():
    app.add_api_route(
        _route,
        (lambda f=_file: (lambda: _page(f)))(),
        methods=["GET"],
        include_in_schema=False,
    )
