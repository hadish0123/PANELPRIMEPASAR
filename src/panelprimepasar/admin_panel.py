import secrets

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


def _check_admin_key(api_key: str | None) -> None:
    settings = get_settings()
    configured = settings.admin_panel_api_key
    if configured is None:
        raise HTTPException(status_code=503, detail="Admin panel key is not configured")

    if api_key is None or not secrets.compare_digest(api_key, configured.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")


@router.get("/dashboard")
async def dashboard(
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int | str]:
    _check_admin_key(x_admin_key)

    return {
        "panel": "PANELPRIMEPASAR",
        "customers": int(await session.scalar(select(func.count(Customer.id))) or 0),
        "plans": int(await session.scalar(select(func.count(Plan.id))) or 0),
        "orders": int(await session.scalar(select(func.count(Order.id))) or 0),
        "paid_orders": int(await session.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.PAID)) or 0),
        "verified_payments": int(await session.scalar(select(func.count(Payment.id)).where(Payment.status == PaymentStatus.VERIFIED)) or 0),
        "pasarguard_accounts": int(await session.scalar(select(func.count(PasarGuardAccount.id))) or 0),
    }


@router.get("/customers")
async def customers(
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    search: str | None = Query(default=None, max_length=128),
    blocked: bool | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> list[dict[str, str | int | bool]]:
    _check_admin_key(x_admin_key)
    query = select(Customer)
    if blocked is not None:
        query = query.where(Customer.is_blocked == blocked)
    if search:
        term = search.strip()
        if term:
            literal = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions = [Customer.telegram_username.ilike(f"%{literal}%", escape="\\")]
            if term.isdecimal() and len(term) <= 19:
                conditions.append(Customer.telegram_user_id == int(term))
            query = query.where(or_(*conditions))
    rows = (await session.scalars(
        query.order_by(Customer.created_at.desc(), Customer.id.desc())
        .offset(offset).limit(limit)
    )).all()
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
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, str | int | bool]]:
    _check_admin_key(x_admin_key)
    rows = (await session.scalars(select(Plan).order_by(Plan.created_at.desc()))).all()
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
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> list[dict[str, str | int]]:
    _check_admin_key(x_admin_key)
    query = select(Order)
    if order_status is not None:
        query = query.where(Order.status == order_status)
    rows = (await session.scalars(
        query.order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset).limit(limit)
    )).all()
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
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, str | None]]:
    _check_admin_key(x_admin_key)
    rows = (await session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(100))).all()
    return [
        {
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
        }
        for row in rows
    ]
