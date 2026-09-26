import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.db import get_session
from panelprimepasar.models import (
    AuditEvent,
    Customer,
    Order,
    OrderKind,
    OrderStatus,
    PasarGuardAccount,
    Payment,
    PaymentStatus,
    Plan,
    StaffAdmin,
    Subscription,
    SupportTicket,
    Wallet,
)
from panelprimepasar.security import (
    ROLE_PERMISSIONS,
    AdminRole,
    Permission,
    WebAdminSecurityError,
    create_session_token,
    has_permission,
    verify_session_token,
)
from panelprimepasar.services.admins import (
    AdminAccessError,
    authenticate_web_staff,
    set_web_staff_password,
    upsert_web_staff_admin,
)
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.wallets import (
    WalletStateError,
    credit_wallet,
    get_or_create_wallet,
    list_wallet_transactions,
)

router = APIRouter(prefix="/admin", tags=["admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
AdminKeyHeader = Annotated[str | None, Header(alias="X-Admin-Key")]
AdminAuthorizationHeader = Annotated[str | None, Header(alias="Authorization")]
SearchQuery = Annotated[str | None, Query(max_length=128)]
OffsetQuery = Annotated[int, Query(ge=0)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]
OrderStatusQuery = Annotated[OrderStatus | None, Query(alias="status")]
OrderKindQuery = Annotated[OrderKind | None, Query(alias="kind")]
PaymentStatusQuery = Annotated[PaymentStatus | None, Query(alias="status")]


class PlanCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    quota_bytes: int = Field(gt=0)
    price_amount: int = Field(ge=0)
    currency: str = Field(default="IRT", min_length=2, max_length=8)
    validity_days: int | None = Field(default=None, gt=0)
    is_active: bool = True
    sort_order: int = 0


class PlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    quota_bytes: int | None = Field(default=None, gt=0)
    price_amount: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=2, max_length=8)
    validity_days: int | None = Field(default=None, gt=0)
    is_active: bool | None = None
    sort_order: int | None = None


class CustomerBlockRequest(BaseModel):
    blocked: bool


class StaffStatusRequest(BaseModel):
    active: bool


class AdminLoginRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64)
    password: str | None = Field(default=None, min_length=1, max_length=512)
    api_key: str | None = Field(default=None, min_length=1, max_length=512)


class StaffCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=512)
    role: AdminRole
    telegram_user_id: int | None = None
    note: str | None = Field(default=None, max_length=255)


class StaffPasswordRequest(BaseModel):
    password: str = Field(min_length=12, max_length=512)


class WalletCreditRequest(BaseModel):
    amount: int = Field(gt=0)
    currency: str = Field(default="IRT", min_length=2, max_length=8)
    idempotency_key: str = Field(min_length=8, max_length=191)
    reference: str | None = Field(default=None, max_length=191)


@dataclass(frozen=True, slots=True)
class WebAdminPrincipal:
    role: AdminRole
    staff_id: UUID | None
    username: str


def _session_secret() -> str:
    settings = get_settings()
    configured = settings.admin_panel_session_secret or settings.admin_panel_api_key
    if configured is None:
        raise HTTPException(
            status_code=503,
            detail="Admin panel session secret is not configured",
        )
    return configured.get_secret_value()


def _owner_key_valid(api_key: str | None) -> bool:
    configured = get_settings().admin_panel_api_key
    return (
        configured is not None
        and api_key is not None
        and secrets.compare_digest(api_key, configured.get_secret_value())
    )


async def _authenticate_web_admin(
    session: AsyncSession,
    *,
    api_key: str | None,
    authorization: str | None,
) -> WebAdminPrincipal:
    if _owner_key_valid(api_key):
        return WebAdminPrincipal(
            role=AdminRole.OWNER,
            staff_id=None,
            username="owner",
        )

    if authorization is None:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    try:
        claims = verify_session_token(token, secret=_session_secret())
    except WebAdminSecurityError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    if claims.staff_id is None:
        if claims.role != AdminRole.OWNER:
            raise HTTPException(status_code=401, detail="Invalid admin session")
        return WebAdminPrincipal(
            role=AdminRole.OWNER,
            staff_id=None,
            username="owner",
        )

    staff = await session.get(StaffAdmin, claims.staff_id)
    if staff is None or not staff.is_active or staff.login_username is None:
        raise HTTPException(status_code=401, detail="Admin account is inactive")

    try:
        current_role = AdminRole(staff.role)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Admin role is invalid") from exc

    return WebAdminPrincipal(
        role=current_role,
        staff_id=staff.id,
        username=staff.login_username,
    )


async def _require_web_permission(
    session: AsyncSession,
    *,
    api_key: str | None,
    authorization: str | None,
    permission: Permission,
) -> WebAdminPrincipal:
    principal = await _authenticate_web_admin(
        session,
        api_key=api_key,
        authorization=authorization,
    )
    if not has_permission(principal.role, permission):
        raise HTTPException(status_code=403, detail="Permission denied")
    return principal


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


@router.post("/auth/login")
async def admin_login(
    payload: AdminLoginRequest,
    session: SessionDep,
) -> dict[str, object]:
    settings = get_settings()
    role: AdminRole
    staff_id: UUID | None
    username: str

    if payload.api_key is not None and _owner_key_valid(payload.api_key):
        role = AdminRole.OWNER
        staff_id = None
        username = "owner"
    elif payload.username is not None and payload.password is not None:
        staff = await authenticate_web_staff(
            session,
            username=payload.username,
            password=payload.password,
        )
        if staff is None or staff.login_username is None:
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
        try:
            role = AdminRole(staff.role)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Admin role is invalid") from exc
        staff.last_login_at = datetime.now(UTC)
        staff_id = staff.id
        username = staff.login_username
    else:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    token = create_session_token(
        role=role,
        staff_id=staff_id,
        secret=_session_secret(),
        ttl_seconds=settings.admin_panel_session_ttl_seconds,
    )
    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(staff_id) if staff_id is not None else "owner",
        action="admin.web_login",
        entity_type="staff_admin",
        entity_id=str(staff_id) if staff_id is not None else None,
        metadata={"role": role.value, "username": username},
    )
    await session.commit()
    return {
        "token": token,
        "token_type": "bearer",
        "expires_in": settings.admin_panel_session_ttl_seconds,
        "role": role.value,
        "username": username,
        "permissions": sorted(
            permission.value for permission in ROLE_PERMISSIONS[role]
        ),
    }


@router.get("/auth/me")
async def admin_me(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.VIEW_DASHBOARD,
    )
    return {
        "role": principal.role.value,
        "username": principal.username,
        "staff_id": str(principal.staff_id) if principal.staff_id is not None else None,
        "permissions": sorted(
            permission.value for permission in ROLE_PERMISSIONS[principal.role]
        ),
    }


@router.get("/dashboard")
async def dashboard(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, int | str]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.VIEW_DASHBOARD,
    )

    customers_count = int(await session.scalar(select(func.count(Customer.id))) or 0)
    plans_count = int(await session.scalar(select(func.count(Plan.id))) or 0)
    orders_count = int(await session.scalar(select(func.count(Order.id))) or 0)
    pending_orders = int(
        await session.scalar(
            select(func.count(Order.id)).where(
                Order.status.in_(
                    (
                        OrderStatus.PENDING,
                        OrderStatus.AWAITING_PAYMENT,
                        OrderStatus.PAID,
                        OrderStatus.PROVISIONING,
                    )
                )
            )
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
    verified_revenue = int(
        await session.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.VERIFIED
            )
        )
        or 0
    )
    active_services = int(
        await session.scalar(
            select(func.count(Subscription.id)).where(
                Subscription.status == "active"
            )
        )
        or 0
    )
    open_tickets = int(
        await session.scalar(
            select(func.count(SupportTicket.id)).where(
                SupportTicket.status != "closed"
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
        "pending_orders": pending_orders,
        "verified_payments": verified_payments_count,
        "verified_revenue": verified_revenue,
        "active_services": active_services,
        "open_tickets": open_tickets,
        "pasarguard_accounts": pasarguard_accounts_count,
    }


@router.get("/customers")
async def customers(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
    search: SearchQuery = None,
    blocked: bool | None = None,
    offset: OffsetQuery = 0,
    limit: LimitQuery = 100,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.VIEW_USERS,
    )
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
            username_condition = Customer.telegram_username.ilike(
                f"%{literal}%",
                escape="\\",
            )
            if term.isdecimal() and len(term) <= 19:
                query = query.where(
                    or_(
                        username_condition,
                        Customer.telegram_user_id == int(term),
                    )
                )
            else:
                query = query.where(username_condition)

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
            "first_name": row.first_name,
            "last_name": row.last_name,
            "blocked": row.is_blocked,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.patch("/customers/{customer_id}/block")
async def set_customer_blocked(
    customer_id: UUID,
    payload: CustomerBlockRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_USERS,
    )
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.is_blocked = payload.blocked
    await session.commit()
    return {
        "id": str(customer.id),
        "blocked": customer.is_blocked,
    }


@router.get("/customers/{customer_id}/wallet")
async def customer_wallet(
    customer_id: UUID,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.VIEW_USERS,
    )
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    wallet = await get_or_create_wallet(
        session,
        customer_id=customer.id,
        currency="IRT",
    )
    transactions = await list_wallet_transactions(
        session,
        wallet_id=wallet.id,
        limit=20,
    )
    return {
        "id": str(wallet.id),
        "customer_id": str(customer.id),
        "balance": wallet.balance,
        "currency": wallet.currency,
        "transactions": [
            {
                "id": str(transaction.id),
                "kind": transaction.kind,
                "amount": transaction.amount,
                "currency": transaction.currency,
                "reference": transaction.reference,
                "created_at": transaction.created_at.isoformat(),
            }
            for transaction in transactions
        ],
    }


@router.post("/customers/{customer_id}/wallet/credit")
async def credit_customer_wallet(
    customer_id: UUID,
    payload: WalletCreditRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_WALLETS,
    )
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        transaction = await credit_wallet(
            session,
            customer_id=customer.id,
            amount=payload.amount,
            currency=payload.currency,
            idempotency_key=payload.idempotency_key,
            reference=payload.reference,
        )
        wallet = await session.get(Wallet, transaction.wallet_id)
        if wallet is None:
            raise WalletStateError("Wallet not found after credit")
    except WalletStateError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="wallet.credited",
        entity_type="customer",
        entity_id=str(customer.id),
        correlation_id=str(transaction.id),
        metadata={
            "amount": transaction.amount,
            "currency": transaction.currency,
            "reference": transaction.reference,
        },
    )
    await session.commit()
    return {
        "wallet_id": str(wallet.id),
        "transaction_id": str(transaction.id),
        "balance": wallet.balance,
        "currency": wallet.currency,
    }


@router.get("/plans")
async def plans(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PLANS,
    )
    rows = (
        await session.scalars(
            select(Plan).order_by(
                Plan.sort_order.asc(),
                Plan.created_at.desc(),
                Plan.id.desc(),
            )
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "name": row.name,
            "quota_bytes": row.quota_bytes,
            "price_amount": row.price_amount,
            "currency": row.currency,
            "validity_days": row.validity_days,
            "active": row.is_active,
            "sort_order": row.sort_order,
        }
        for row in rows
    ]


@router.post("/plans", status_code=201)
async def create_plan(
    payload: PlanCreateRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PLANS,
    )
    normalized_name = payload.name.strip()
    duplicate = await session.scalar(
        select(Plan).where(Plan.name == normalized_name)
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Plan name already exists")

    plan = Plan(
        name=normalized_name,
        quota_bytes=payload.quota_bytes,
        price_amount=payload.price_amount,
        currency=payload.currency.upper(),
        validity_days=payload.validity_days,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    session.add(plan)
    await session.commit()
    return {"id": str(plan.id), "name": plan.name}


@router.patch("/plans/{plan_id}")
async def update_plan(
    plan_id: UUID,
    payload: PlanUpdateRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PLANS,
    )
    plan = await session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        normalized_name = str(changes["name"]).strip()
        duplicate = await session.scalar(
            select(Plan).where(
                Plan.name == normalized_name,
                Plan.id != plan.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Plan name already exists")
        plan.name = normalized_name
    if "quota_bytes" in changes:
        plan.quota_bytes = int(changes["quota_bytes"])
    if "price_amount" in changes:
        plan.price_amount = int(changes["price_amount"])
    if "currency" in changes:
        plan.currency = str(changes["currency"]).upper()
    if "validity_days" in changes:
        plan.validity_days = changes["validity_days"]
    if "is_active" in changes:
        plan.is_active = bool(changes["is_active"])
    if "sort_order" in changes:
        plan.sort_order = int(changes["sort_order"])

    await session.commit()
    return {
        "id": str(plan.id),
        "name": plan.name,
        "active": plan.is_active,
    }


@router.delete("/plans/{plan_id}")
async def archive_plan(
    plan_id: UUID,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PLANS,
    )
    plan = await session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan.is_active = False
    await session.commit()
    return {"id": str(plan.id), "active": False}


@router.get("/orders")
async def orders(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
    order_status: OrderStatusQuery = None,
    order_kind: OrderKindQuery = None,
    offset: OffsetQuery = 0,
    limit: LimitQuery = 100,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.VIEW_ORDERS,
    )
    query = select(Order)

    if order_status is not None:
        query = query.where(Order.status == order_status)
    if order_kind is not None:
        query = query.where(Order.kind == order_kind)

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
            "customer_id": str(row.customer_id),
            "plan_id": str(row.plan_id),
            "kind": row.kind.value,
            "status": row.status.value,
            "amount": row.price_amount,
            "currency": row.currency,
            "quota_bytes": row.quota_bytes,
            "validity_days": row.validity_days,
            "target_subscription_id": (
                str(row.target_subscription_id)
                if row.target_subscription_id is not None
                else None
            ),
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/payments")
async def payments(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
    payment_status: PaymentStatusQuery = None,
    provider: str | None = Query(default=None, max_length=32),
    offset: OffsetQuery = 0,
    limit: LimitQuery = 100,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.VIEW_PAYMENTS,
    )
    query = select(Payment)
    if payment_status is not None:
        query = query.where(Payment.status == payment_status)
    if provider:
        query = query.where(Payment.provider == provider)

    rows = (
        await session.scalars(
            query.order_by(Payment.created_at.desc(), Payment.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "order_id": str(row.order_id),
            "provider": row.provider,
            "transaction_id": row.provider_transaction_id,
            "amount": row.amount,
            "currency": row.currency,
            "status": row.status.value,
            "verified_at": (
                row.verified_at.isoformat() if row.verified_at is not None else None
            ),
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/subscriptions")
async def subscriptions(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
    status: str | None = Query(default=None, max_length=32),
    customer_id: UUID | None = None,
    offset: OffsetQuery = 0,
    limit: LimitQuery = 100,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.VIEW_ORDERS,
    )
    query = select(Subscription)
    if status:
        query = query.where(Subscription.status == status)
    if customer_id is not None:
        query = query.where(Subscription.customer_id == customer_id)

    rows = (
        await session.scalars(
            query.order_by(Subscription.created_at.desc(), Subscription.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "customer_id": str(row.customer_id),
            "plan_id": str(row.plan_id),
            "pasarguard_account_id": str(row.pasar_guard_account_id),
            "status": row.status,
            "quota_bytes": row.quota_bytes,
            "starts_at": row.starts_at.isoformat(),
            "expires_at": (
                row.expires_at.isoformat() if row.expires_at is not None else None
            ),
            "auto_renew": row.auto_renew,
        }
        for row in rows
    ]


@router.get("/pasarguard/accounts")
async def pasar_guard_accounts(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
    active: bool | None = None,
    offset: OffsetQuery = 0,
    limit: LimitQuery = 100,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PASARGUARD,
    )
    query = select(PasarGuardAccount)
    if active is not None:
        query = query.where(PasarGuardAccount.is_active == active)

    rows = (
        await session.scalars(
            query.order_by(
                PasarGuardAccount.created_at.desc(),
                PasarGuardAccount.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "customer_id": str(row.customer_id),
            "order_id": str(row.order_id),
            "pasarguard_admin_id": row.pasarguard_admin_id,
            "username": row.username,
            "role_id": row.role_id,
            "role_name": row.role_name,
            "quota_bytes": row.quota_bytes,
            "active": row.is_active,
        }
        for row in rows
    ]


@router.get("/support")
async def support_tickets(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
    status: str | None = Query(default=None, max_length=32),
    offset: OffsetQuery = 0,
    limit: LimitQuery = 100,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_SUPPORT,
    )
    query = select(SupportTicket)
    if status:
        query = query.where(SupportTicket.status == status)

    rows = (
        await session.scalars(
            query.order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "customer_id": str(row.customer_id),
            "subject": row.subject,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/staff", status_code=201)
async def create_staff(
    payload: StaffCreateRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_ADMINS,
    )
    try:
        staff_admin = await upsert_web_staff_admin(
            session,
            username=payload.username,
            password=payload.password,
            role=payload.role,
            telegram_user_id=payload.telegram_user_id,
            note=payload.note,
        )
    except (AdminAccessError, WebAdminSecurityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="staff.web_upserted",
        entity_type="staff_admin",
        entity_id=str(staff_admin.id),
        metadata={
            "username": staff_admin.login_username,
            "role": staff_admin.role,
            "telegram_user_id": staff_admin.telegram_user_id,
        },
    )
    await session.commit()
    return {
        "id": str(staff_admin.id),
        "username": staff_admin.login_username,
        "telegram_user_id": staff_admin.telegram_user_id,
        "role": staff_admin.role,
        "active": staff_admin.is_active,
    }


@router.patch("/staff/{staff_id}/password")
async def change_staff_password(
    staff_id: UUID,
    payload: StaffPasswordRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_ADMINS,
    )
    try:
        staff_admin = await set_web_staff_password(
            session,
            staff_id=staff_id,
            password=payload.password,
        )
    except (AdminAccessError, WebAdminSecurityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="staff.password_changed",
        entity_type="staff_admin",
        entity_id=str(staff_admin.id),
    )
    await session.commit()
    return {"id": str(staff_admin.id), "password_changed": True}


@router.get("/staff")
async def staff(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_ADMINS,
    )
    rows = (
        await session.scalars(
            select(StaffAdmin).order_by(
                StaffAdmin.created_at.desc(),
                StaffAdmin.id.desc(),
            )
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "telegram_user_id": row.telegram_user_id,
            "username": row.login_username,
            "role": row.role,
            "active": row.is_active,
            "last_login_at": (
                row.last_login_at.isoformat()
                if row.last_login_at is not None
                else None
            ),
        }
        for row in rows
    ]


@router.patch("/staff/{staff_id}/status")
async def set_staff_status(
    staff_id: UUID,
    payload: StaffStatusRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_ADMINS,
    )
    staff_admin = await session.get(StaffAdmin, staff_id)
    if staff_admin is None:
        raise HTTPException(status_code=404, detail="Staff admin not found")

    staff_admin.is_active = payload.active
    await session.commit()
    return {"id": str(staff_admin.id), "active": staff_admin.is_active}


@router.get("/audit")
async def audit_logs(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
    action: str | None = Query(default=None, max_length=128),
    offset: OffsetQuery = 0,
    limit: LimitQuery = 100,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.VIEW_AUDIT_LOGS,
    )
    query = select(AuditEvent)
    if action:
        query = query.where(AuditEvent.action == action)

    rows = (
        await session.scalars(
            query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "correlation_id": row.correlation_id,
            "metadata_json": row.metadata_json,
        }
        for row in rows
    ]
