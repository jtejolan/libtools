import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from database import Base, SessionLocal, engine, migrate_existing_database
from dependencies import DatabaseSession
from accounts import models as account_models
from accounts.auth import get_current_user, require_platform_admin
from accounts.bootstrap import (
    initialize_platform_accounts,
    remove_legacy_lendery_accounts,
)
from accounts.routes import admin_router as account_admin_router
from accounts.routes import router as account_router
from bookclub import models as bookclub_models
from bookclub.club_routes import public_router as public_bookclub_router
from bookclub.club_routes import router as bookclub_club_router
from bookclub.routes import router as bookclub_router
from lendery import models
from lendery.routes import router as lendery_router

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def public_homepage_response() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "index.html",
        headers={"Cache-Control": "private, no-store"},
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    migrate_existing_database()
    with SessionLocal() as db:
        initialize_platform_accounts(db)
    remove_legacy_lendery_accounts()
    yield


app = FastAPI(
    title="Library Tools API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    openapi_url=None,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv(
        "LIBTOOLS_SESSION_SECRET",
        secrets.token_urlsafe(32),
    ),
    session_cookie="libtools_session",
    max_age=60 * 60 * 24 * 30,
    same_site="lax",
    https_only=bool(os.getenv("RAILWAY_ENVIRONMENT")),
)
app.include_router(account_router)
app.include_router(account_admin_router)
app.include_router(lendery_router)
app.include_router(bookclub_club_router)
app.include_router(bookclub_router)
app.include_router(public_bookclub_router)
app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR),
    name="static",
)


@app.get("/", include_in_schema=False)
def homepage(
    request: Request,
    db: DatabaseSession,
) -> Response:
    try:
        get_current_user(request, db)
    except HTTPException:
        return public_homepage_response()
    return RedirectResponse(
        "/dashboard",
        status_code=302,
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/home", include_in_schema=False)
def public_homepage() -> FileResponse:
    return public_homepage_response()


@app.get("/lendery", include_in_schema=False)
def lendery_app() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "lendery.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/lendery/export", include_in_schema=False)
def lendery_export_app() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "lendery-export.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/bookclub", include_in_schema=False)
def bookclub_app() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "bookclub.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "account.html")


@app.get("/signup", include_in_schema=False)
def signup_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "account.html")


@app.get("/forgot-password", include_in_schema=False)
def forgot_password_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "account.html")


@app.get("/reset-password", include_in_schema=False)
def reset_password_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "account.html")


@app.get("/verify-email", include_in_schema=False)
def verify_email_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "account.html")


@app.get("/account", include_in_schema=False)
def account_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "account.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "dashboard.html")


@app.get("/admin/accounts", include_in_schema=False)
def accounts_admin_page() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "admin-accounts.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/admin/users", include_in_schema=False)
def users_admin_page() -> RedirectResponse:
    return RedirectResponse(
        "/admin/accounts",
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/clubs/{slug}", include_in_schema=False)
def public_club_page(slug: str) -> FileResponse:
    return FileResponse(FRONTEND_DIR / "public-club.html")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/public/stats", tags=["system"])
def public_stats(db: DatabaseSession) -> dict[str, int]:
    item_count = db.scalar(
        select(func.count(models.LenderyItem.id)).where(
            models.LenderyItem.lifecycle_status != "removed"
        )
    ) or 0
    club_count = (
        db.scalar(
            select(func.count(bookclub_models.BookClub.id)).where(
                bookclub_models.BookClub.public.is_(True)
            )
        )
        or 0
    )
    return {"lendery_items": item_count, "bookclub_clubs": club_count}


@app.get("/docs", include_in_schema=False)
def api_docs(_admin=Depends(require_platform_admin)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{app.title} - Swagger UI",
    )


@app.get("/openapi.json", include_in_schema=False)
def openapi_schema(_admin=Depends(require_platform_admin)) -> JSONResponse:
    return JSONResponse(app.openapi())
