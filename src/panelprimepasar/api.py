import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Annotated

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from pydantic import ValidationError

from panelprimepasar.admin_panel import router as admin_router
from panelprimepasar.admin_ui import router as admin_ui_router
from panelprimepasar.bot import build_bot, build_dispatcher
from panelprimepasar.config import Settings, get_settings
from panelprimepasar.db import SessionFactory, engine
from panelprimepasar.services.maintenance import subscription_maintenance_loop


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
    maintenance_task: asyncio.Task[None] | None = None

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

    if settings.subscription_maintenance_enabled:
        maintenance_task = asyncio.create_task(
            subscription_maintenance_loop(
                session_factory=SessionFactory,
                settings=settings,
                bot=runtime.bot if runtime is not None else None,
            ),
            name="subscription-maintenance",
        )

    try:
        yield
    finally:
        if maintenance_task is not None:
            maintenance_task.cancel()
            with suppress(asyncio.CancelledError):
                await maintenance_task
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
app.include_router(admin_ui_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
    if secret_token is None or not secrets.compare_digest(secret_token, expected_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Telegram webhook secret",
        )

    try:
        update = Update.model_validate(
            await request.json(),
            context={"bot": runtime.bot},
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram update",
        ) from exc

    await runtime.dispatcher.feed_update(runtime.bot, update)
    return Response(status_code=status.HTTP_200_OK)
