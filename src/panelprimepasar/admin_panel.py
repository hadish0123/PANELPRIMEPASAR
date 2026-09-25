import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.db import get_session
from panelprimepasar.models import (
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin panel key is not configured",
        )

    if api_key is None or not secrets.compare_digest(
        api_key,
        configured.get_secret_value(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )


@router.get("/dashboard")
async def dashboard(
    x_admin_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int | str]:
    _check_admin_key(x_admin_key)

    customers = await session.scalar(select(func.count(Customer.id))) or 0
    plans = await session.scalar(select(func.count(Plan.id))) or 0
    orders = await session.scalar(select(func.count(Order.id))) or 0
    paid_orders = await session.scalar(
        select(func.count(Order.id)).where(Order.status == OrderStatus.PAID)
    ) or 0
    payments = await session.scalar(
        select(func.count(Payment.id)).where(Payment.status == PaymentStatus.VERIFIED)
    ) or 0
    accounts = await session.scalar(select(func.count(PasarGuardAccount.id))) or 0

    return {
        "panel": "PANELPRIMEPASAR",
        "status": "ready",
        "customers": int(customers),
        "plans": int(plans),
        "orders": int(orders),
        "paid_orders": int(paid_orders),
        "verified_payments": int(payments),
        "pasarguard_accounts": int(accounts),
    }
