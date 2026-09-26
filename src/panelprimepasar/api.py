import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import RequestResponseEndpoint

from panelprimepasar.admin_panel import router as admin_router
from panelprimepasar.bot import build_bot, build_dispatcher
from panelprimepasar.config import Settings, get_settings
from panelprimepasar.db import SessionFactory, engine


@dataclass(slots=True)
class TelegramRuntime:
    bot: Bot
    dispatcher: Dispatcher


def _webhook_url(settings: Settings) -> str | None:
    if settings.telegram_webhook_base_url is None:
        return None
    return f"{str(settings.telegram_webhook_base_url).rstrip('/')}/telegram/webhook"


def _runtime(app: FastAPI) -> TelegramRuntime | None:
    runtime = getattr(app.state, "telegram_runtime", None)
    if isinstance(runtime, TelegramRuntime):
        return runtime
    return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    runtime: TelegramRuntime | None = None

    if settings.telegram_bot_token is not None:
        webhook_url = _webhook_url(settings)
        if settings.app_env.casefold() == "production":
            if webhook_url is None or settings.telegram_webhook_secret is None:
                raise RuntimeError(
                    "Production Telegram bot requires webhook base URL and webhook secret"
                )

        bot = build_bot(settings)
        dispatcher = build_dispatcher(settings)
        runtime = TelegramRuntime(bot=bot, dispatcher=dispatcher)
        app.state.telegram_runtime = runtime

        await dispatcher.emit_startup(bot=bot)

        if webhook_url is not None:
            if settings.telegram_webhook_secret is None:
                raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is required when webhook URL is set")
            await bot.set_webhook(
                webhook_url,
                secret_token=settings.telegram_webhook_secret.get_secret_value(),
                allowed_updates=dispatcher.resolve_used_update_types(),
            )

    try:
        yield
    finally:
        if runtime is not None:
            await runtime.dispatcher.emit_shutdown(bot=runtime.bot)
            await runtime.bot.session.close()
        await engine.dispose()


app = FastAPI(
    title="PANELPRIMEPASAR",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(admin_router)
app.mount(
    "/admin/assets", StaticFiles(directory=Path(__file__).parent / "static"), name="admin-assets"
)


@app.middleware("http")
async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' blob:; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["system"])
async def ready(response: Response) -> dict[str, str]:
    checks = {"database": "unavailable", "redis": "unavailable"}
    try:
        async with asyncio.timeout(3), SessionFactory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except (SQLAlchemyError, OSError, TimeoutError):
        pass
    try:
        async with Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
        ) as redis:
            await redis.ping()
        checks["redis"] = "ok"
    except (RedisError, OSError):
        pass
    if "unavailable" in checks.values():
        response.status_code = 503
    return checks


@app.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    secret_token: Annotated[
        str | None,
        Header(alias="X-Telegram-Bot-Api-Secret-Token"),
    ] = None,
) -> Response:
    settings = get_settings()
    configured_secret = settings.telegram_webhook_secret
    runtime = _runtime(request.app)

    if configured_secret is None or runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram webhook is not configured",
        )

    expected_secret = configured_secret.get_secret_value()
    if secret_token is None or not secrets.compare_digest(
        secret_token.encode(),
        expected_secret.encode(),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Telegram webhook secret",
        )

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 2 * 1024 * 1024:
            raise HTTPException(413, "Telegram update is too large")
    try:
        update = Update.model_validate(
            json.loads(body),
            context={"bot": runtime.bot},
        )
    except (ValidationError, ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram update",
        ) from exc

    await runtime.dispatcher.feed_update(runtime.bot, update)
    return Response(status_code=status.HTTP_200_OK)
