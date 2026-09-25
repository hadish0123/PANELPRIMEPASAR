from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from panelprimepasar.config import get_settings
from panelprimepasar.db import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(
    title="PANELPRIMEPASAR",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
