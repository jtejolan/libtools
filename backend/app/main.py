from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import Base, engine, migrate_existing_database
from lendery import models
from lendery.routes import router as lendery_router

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    migrate_existing_database()
    yield


app = FastAPI(
    title="Library Tools API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(lendery_router)
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


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
