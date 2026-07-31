from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import Base, engine
from lendery import models
from lendery.routes import router as lendery_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Library Tools API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(lendery_router)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "message": "Library Tools API",
        "docs": "/docs",
    }


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
