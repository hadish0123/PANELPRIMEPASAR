import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.db import get_session
from panelprimepasar.models import (
    AuditEvent,
    Customer,
    Order,
    OrderStatus,
    PasarGuardAccount,
    Payment,
    PaymentStatus,
    Plan,
)

router = APIRouter(prefix="/admin", tags=["admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AdminKeyHeader = Annotated[str | None, Header(alias="X-Admin-Key")]
SearchQuery = Annotated[str | None, Query(max_length=128)]
OffsetQuery = Annotated[int, Query(ge=0)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]
OrderStatusQuery = Annotated[OrderStatus | None, Query(alias="status")]


def _check_admin_key(api_key: str | None) -> None:
    settings = get_settings()
    configured = settings.admin_panel_api_key
    if configured is None:
        raise HTTPException(status_code=503, detail="Admin panel key is not configured")

    if api_key is None or not secrets.compare_digest(
        api_key,
        configured.get_secret_value(),
    ):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")


@router.get("/dashboard")
async def dashboard(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
) -> dict[str, int | str]:
    _check_admin_key(x_admin_key)

    customers_count = int(
        await session.scalar(select(func.count(Customer.id))) or 0
    )
    plans_count = int(await session.scalar(select(func.count(Plan.id))) or 0)
    orders_count = int(await session.scalar(select(func.count(Order.id))) or 0)
    paid_orders_count = int(
        await session.scalar(
            select(func.count(Order.id)).where(Order.status == OrderStatus.PAID)
        )
        or 0
    )
    verified_payments_count = int(
        await session.scalar(
            select(func.count(Payment.id)).where(
                Payment.status == PaymentStatus.VERIFIED
            )
        )
        or 0
    )
    pasarguard_accounts_count = int(
        await session.scalar(select(func.count(PasarGuardAccount.id))) or 0
    )

    return {
        "panel": "PANELPRIMEPASAR",
        "customers": customers_count,
        "plans": plans_count,
        "orders": orders_count,
        "paid_orders": paid_orders_count,
        "verified_payments": verified_payments_count,
        "pasarguard_accounts": pasarguard_accounts_count,
    }


@router.get("/customers")
async def customers(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    search: SearchQuery = None,
    blocked: bool | None = None,
    offset: OffsetQuery = 0,
    limit: LimitQuery = 100,
) -> list[dict[str, str | int | bool]]:
    _check_admin_key(x_admin_key)
    query = select(Customer)

    if blocked is not None:
        query = query.where(Customer.is_blocked == blocked)

    if search:
        term = search.strip()
        if term:
            literal = (
                term.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions = [
                Customer.telegram_username.ilike(f"%{literal}%", escape="\\")
            ]
            if term.isdecimal() and len(term) <= 19:
                conditions.append(Customer.telegram_user_id == int(term))
            query = query.where(or_(*conditions))

    rows = (
        await session.scalars(
            query.order_by(Customer.created_at.desc(), Customer.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    return [
        {
            "id": str(row.id),
            "telegram_user_id": row.telegram_user_id,
            "username": row.telegram_username or "",
            "blocked": row.is_blocked,
        }
        for row in rows
    ]


@router.get("/plans")
async def plans(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
) -> list[dict[str, str | int | bool]]:
    _check_admin_key(x_admin_key)
    rows = (
        await session.scalars(
            select(Plan).order_by(Plan.created_at.desc(), Plan.id.desc())
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "name": row.name,
            "quota_bytes": row.quota_bytes,
            "price_amount": row.price_amount,
            "active": row.is_active,
        }
        for row in rows
    ]


@router.get("/orders")
async def orders(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    order_status: OrderStatusQuery = None,
    offset: OffsetQuery = 0,
    limit: LimitQuery = 100,
) -> list[dict[str, str | int]]:
    _check_admin_key(x_admin_key)
    query = select(Order)

    if order_status is not None:
        query = query.where(Order.status == order_status)

    rows = (
        await session.scalars(
            query.order_by(Order.created_at.desc(), Order.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    return [
        {
            "id": str(row.id),
            "status": row.status.value,
            "amount": row.price_amount,
            "currency": row.currency,
        }
        for row in rows
    ]


@router.get("/audit")
async def audit_logs(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
) -> list[dict[str, str | None]]:
    _check_admin_key(x_admin_key)
    rows = (
        await session.scalars(
            select(AuditEvent)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(100)
        )
    ).all()
    return [
        {
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
        }
        for row in rows
    ]
