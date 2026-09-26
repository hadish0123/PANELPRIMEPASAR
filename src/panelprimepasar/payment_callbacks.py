from html import escape
from typing import Annotated
from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.db import get_session
from panelprimepasar.integrations.pasarguard import PasarGuardError
from panelprimepasar.models import (
    Customer,
    Order,
    OrderKind,
    PasarGuardAccount,
    PasarGuardInstance,
    Payment,
    PaymentMethodConfig,
    PaymentStatus,
)
from panelprimepasar.payments.base import PaymentProviderError
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.fulfillment import fulfill_paid_order
from panelprimepasar.services.payment_methods import (
    PaymentMethodStateError,
    verify_external_payment,
)
from panelprimepasar.services.payments import PaymentStateError
from panelprimepasar.services.provisioning import ProvisioningStateError
from panelprimepasar.services.subscriptions import SubscriptionStateError

router = APIRouter(prefix="/payments", tags=["payments"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _page(title: str, message: str, *, ok: bool) -> HTMLResponse:
    accent = "#20b26b" if ok else "#d64545"
    body = f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<style>
body{{font-family:system-ui,sans-serif;background:#0b1020;color:#f2f6ff;margin:0;padding:32px}}
.card{{max-width:560px;margin:10vh auto;background:#121a2d;
border:1px solid #25304a;border-radius:16px;padding:24px}}
h1{{color:{accent}}}p{{line-height:1.9}}code{{direction:ltr;display:inline-block}}
</style>
</head>
<body><div class="card"><h1>{escape(title)}</h1><p>{escape(message)}</p>
<p>می‌توانید این صفحه را ببندید و به ربات تلگرام برگردید.</p></div></body>
</html>"""
    return HTMLResponse(body, status_code=200 if ok else 400)


async def _panel_url(
    session: AsyncSession,
    *,
    order_id: UUID,
) -> str:
    settings = get_settings()
    account = await session.scalar(
        select(PasarGuardAccount).where(PasarGuardAccount.order_id == order_id)
    )
    if account is not None and account.pasarguard_instance_id is not None:
        instance = await session.get(
            PasarGuardInstance,
            account.pasarguard_instance_id,
        )
        if instance is not None:
            return instance.base_url.rstrip("/")
    return str(settings.pasarguard_base_url).rstrip("/")


async def _telegram_bot(request: Request) -> Bot | None:
    runtime = getattr(request.app.state, "telegram_runtime", None)
    bot = getattr(runtime, "bot", None)
    return bot if isinstance(bot, Bot) else None


@router.api_route(
    "/callback/{payment_id}",
    methods=["GET", "POST"],
    response_class=HTMLResponse,
)
async def payment_callback(
    payment_id: UUID,
    request: Request,
    session: SessionDep,
) -> HTMLResponse:
    payment = await session.scalar(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.payment_method_id is None:
        raise HTTPException(
            status_code=400,
            detail="Payment is not associated with an online gateway",
        )

    method = await session.get(PaymentMethodConfig, payment.payment_method_id)
    if method is None:
        raise HTTPException(
            status_code=500,
            detail="Payment gateway configuration no longer exists",
        )

    order = await session.get(Order, payment.order_id)
    if order is None:
        raise HTTPException(status_code=500, detail="Payment order not found")
    customer = await session.get(Customer, order.customer_id)
    if customer is None:
        raise HTTPException(status_code=500, detail="Payment customer not found")

    was_verified = payment.status == PaymentStatus.VERIFIED
    try:
        verified = await verify_external_payment(
            session,
            settings=get_settings(),
            payment=payment,
            method=method,
        )
        await record_audit_event(
            session,
            actor_type="payment_gateway",
            actor_id=method.slug,
            action=(
                "payment.external_verified"
                if verified.status == PaymentStatus.VERIFIED
                else "payment.external_failed"
            ),
            entity_type="payment",
            entity_id=str(payment.id),
            correlation_id=str(order.id),
            metadata={
                "provider": method.kind,
                "payment_method_id": str(method.id),
                "already_verified": was_verified,
            },
        )
        await session.commit()
    except (PaymentMethodStateError, PaymentProviderError, PaymentStateError) as exc:
        await session.rollback()
        return _page(
            "بررسی پرداخت ناموفق بود",
            f"امکان استعلام پرداخت از درگاه وجود نداشت: {exc}",
            ok=False,
        )

    if verified.status != PaymentStatus.VERIFIED:
        return _page(
            "پرداخت تایید نشد",
            "درگاه بانکی این پرداخت را موفق اعلام نکرد.",
            ok=False,
        )

    try:
        outcome = await fulfill_paid_order(
            session,
            settings=get_settings(),
            order_id=order.id,
        )
        await record_audit_event(
            session,
            actor_type="system",
            actor_id=None,
            action=(
                "order.gateway_fulfillment_succeeded"
                if outcome.success
                else "order.gateway_fulfillment_failed"
            ),
            entity_type="order",
            entity_id=str(order.id),
            correlation_id=str(order.id),
            metadata={
                "provider": method.kind,
                "order_kind": outcome.order_kind.value,
                "error_code": outcome.error_code,
            },
        )
        await session.commit()
    except (PasarGuardError, ProvisioningStateError, SubscriptionStateError) as exc:
        await session.rollback()
        bot = await _telegram_bot(request)
        if bot is not None:
            try:
                await bot.send_message(
                    customer.telegram_user_id,
                    "✅ پرداخت بانکی تایید شد، اما اجرای سرویس با خطا مواجه شد. "
                    "پرداخت شما محفوظ است و مدیریت می‌تواند عملیات را دوباره اجرا کند.",
                )
            except TelegramAPIError:
                pass
        return _page(
            "پرداخت موفق",
            f"پرداخت تایید شد، اما اجرای سرویس نیاز به بررسی مدیریت دارد: {exc}",
            ok=True,
        )

    bot = await _telegram_bot(request)
    if bot is not None and outcome.success:
        try:
            if outcome.order_kind == OrderKind.NEW and outcome.credentials is not None:
                panel_url = await _panel_url(session, order_id=order.id)
                await bot.send_message(
                    customer.telegram_user_id,
                    "<b>✅ پرداخت تایید شد و پنل نمایندگی آماده است.</b>\n\n"
                    f"آدرس پنل: <code>{escape(panel_url)}</code>\n"
                    f"نام کاربری: <code>{escape(outcome.credentials.username)}</code>\n"
                    f"رمز عبور: <code>{escape(outcome.credentials.password)}</code>\n\n"
                    "رمز را در محل امن نگه‌داری کنید.",
                )
            elif outcome.order_kind != OrderKind.NEW:
                action = (
                    "تمدید"
                    if outcome.order_kind == OrderKind.RENEWAL
                    else "افزایش حجم"
                )
                await bot.send_message(
                    customer.telegram_user_id,
                    f"✅ پرداخت تایید شد و {action} سرویس با موفقیت انجام شد.",
                )
            else:
                await bot.send_message(
                    customer.telegram_user_id,
                    "✅ پرداخت بانکی و سفارش شما با موفقیت تکمیل شد.",
                )
        except TelegramAPIError:
            pass

    if not outcome.success:
        return _page(
            "پرداخت موفق",
            "پرداخت تایید شد، اما اجرای سرویس کامل نشد و برای تلاش مجدد ثبت شده است.",
            ok=True,
        )

    return _page(
        "پرداخت موفق",
        "پرداخت تایید شد و سفارش شما با موفقیت پردازش شد.",
        ok=True,
    )
