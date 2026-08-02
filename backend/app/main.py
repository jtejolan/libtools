import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from database import Base, SessionLocal, engine, migrate_existing_database
from accounts import models as account_models
from accounts.auth import require_platform_admin
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
def homepage() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/lendery", include_in_schema=False)
def lendery_app() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "lendery.html")


@app.get("/bookclub", include_in_schema=False)
def bookclub_app() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "bookclub.html")


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "account.html")


@app.get("/account", include_in_schema=False)
def account_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "account.html")


@app.get("/admin/users", include_in_schema=False)
def users_admin_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "admin-users.html")


@app.get("/clubs/{slug}", include_in_schema=False)
def public_club_page(slug: str) -> FileResponse:
    return FileResponse(FRONTEND_DIR / "public-club.html")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/docs", include_in_schema=False)
def api_docs(_admin=Depends(require_platform_admin)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{app.title} - Swagger UI",
    )


@app.get("/openapi.json", include_in_schema=False)
def openapi_schema(_admin=Depends(require_platform_admin)) -> JSONResponse:
    return JSONResponse(app.openapi())
