import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import AnyHttpUrl, BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import Settings, get_settings
from panelprimepasar.db import get_session
from panelprimepasar.models import (
    AuditEvent,
    Customer,
    DiscountCode,
    DiscountKind,
    Order,
    OrderKind,
    OrderStatus,
    PasarGuardAccount,
    PasarGuardInstance,
    Payment,
    PaymentMethodConfig,
    PaymentMethodKind,
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
from panelprimepasar.services.discounts import (
    DiscountStateError,
    normalize_discount_code,
)
from panelprimepasar.services.fulfillment import FulfillmentOutcome, fulfill_paid_order
from panelprimepasar.services.panel_urls import resolve_order_panel_url
from panelprimepasar.services.pasarguard_instances import PasarGuardInstanceRouter
from panelprimepasar.services.payment_methods import (
    PaymentMethodInput,
    PaymentMethodStateError,
    configure_payment_method,
    payment_method_public_view,
)
from panelprimepasar.services.payments import (
    PaymentStateError,
    approve_manual_order,
    cancel_unpaid_order,
    reject_pending_manual_payment,
)
from panelprimepasar.services.provisioning import (
    ProvisioningService,
    ProvisioningStateError,
)
from panelprimepasar.services.subscriptions import SubscriptionStateError
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


class DiscountCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    kind: DiscountKind
    value_amount: int | None = Field(default=None, gt=0)
    value_percent: int | None = Field(default=None, ge=1, le=100)
    max_uses: int | None = Field(default=None, gt=0)
    expires_at: datetime | None = None
    is_active: bool = True


class DiscountUpdateRequest(BaseModel):
    value_amount: int | None = Field(default=None, gt=0)
    value_percent: int | None = Field(default=None, ge=1, le=100)
    max_uses: int | None = Field(default=None, gt=0)
    expires_at: datetime | None = None
    is_active: bool | None = None


class PaymentMethodRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=24)
    kind: PaymentMethodKind
    display_name: str = Field(min_length=1, max_length=128)
    is_enabled: bool = False
    sandbox: bool = False
    sort_order: int = Field(default=0, ge=-1000, le=1000)
    public_config: dict[str, str] = Field(default_factory=dict)
    credentials: dict[str, str] | None = None


class PasarGuardInstanceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    base_url: AnyHttpUrl
    api_key_env_var: str | None = Field(default=None, min_length=1, max_length=128)
    bearer_token_env_var: str | None = Field(default=None, min_length=1, max_length=128)
    reseller_role_name: str | None = Field(default=None, max_length=128)
    reseller_role_id: int | None = Field(default=None, ge=1)
    weight: int = Field(default=100, ge=1, le=10_000)
    is_enabled: bool = True


class PasarGuardInstanceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    base_url: AnyHttpUrl | None = None
    api_key_env_var: str | None = Field(default=None, min_length=1, max_length=128)
    bearer_token_env_var: str | None = Field(default=None, min_length=1, max_length=128)
    reseller_role_name: str | None = Field(default=None, max_length=128)
    reseller_role_id: int | None = Field(default=None, ge=1)
    weight: int | None = Field(default=None, ge=1, le=10_000)
    is_enabled: bool | None = None


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


def _web_bot(request: Request) -> Bot | None:
    runtime = getattr(request.app.state, "telegram_runtime", None)
    bot = getattr(runtime, "bot", None)
    return bot if isinstance(bot, Bot) else None


async def _notify_order_fulfillment(
    *,
    request: Request,
    session: AsyncSession,
    settings: Settings,
    customer: Customer,
    order: Order,
    outcome: FulfillmentOutcome,
) -> bool:
    bot = _web_bot(request)
    if bot is None:
        return False

    try:
        if outcome.order_kind == OrderKind.NEW:
            if outcome.credentials is None:
                return False
            panel_url = await resolve_order_panel_url(
                session,
                settings=settings,
                order_id=order.id,
            )
            await bot.send_message(
                customer.telegram_user_id,
                "<b>پنل نمایندگی شما آماده است.</b>\n\n"
                f"آدرس پنل: <code>{panel_url}</code>\n"
                f"نام کاربری: <code>{outcome.credentials.username}</code>\n"
                f"رمز عبور: <code>{outcome.credentials.password}</code>\n\n"
                "رمز را در محل امن نگه‌داری کنید.",
            )
        else:
            action = (
                "تمدید"
                if outcome.order_kind == OrderKind.RENEWAL
                else "افزایش حجم"
            )
            await bot.send_message(
                customer.telegram_user_id,
                f"✅ {action} سرویس با موفقیت انجام شد.",
            )
    except TelegramAPIError:
        return False
    return True


async def _web_fulfill_order(
    *,
    request: Request,
    session: AsyncSession,
    settings: Settings,
    principal: WebAdminPrincipal,
    order: Order,
    customer: Customer,
) -> dict[str, object]:
    try:
        outcome = await fulfill_paid_order(
            session,
            settings=settings,
            order_id=order.id,
        )
        await record_audit_event(
            session,
            actor_type="web_admin",
            actor_id=(
                str(principal.staff_id)
                if principal.staff_id is not None
                else "owner"
            ),
            action=(
                "order.web_fulfillment_succeeded"
                if outcome.success
                else "order.web_fulfillment_failed"
            ),
            entity_type="order",
            entity_id=str(order.id),
            correlation_id=str(order.id),
            metadata={
                "order_kind": order.kind.value,
                "error_code": outcome.error_code,
            },
        )
        await session.commit()
    except (PasarGuardError, ProvisioningStateError, SubscriptionStateError) as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    delivered = False
    if outcome.success:
        delivered = await _notify_order_fulfillment(
            request=request,
            session=session,
            settings=settings,
            customer=customer,
            order=order,
            outcome=outcome,
        )

    return {
        "order_id": str(order.id),
        "status": order.status.value,
        "success": outcome.success,
        "already_provisioned": outcome.already_provisioned,
        "credentials_delivered": delivered,
        "error_code": outcome.error_code,
        "error_message": outcome.error_message,
    }


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


@router.post("/orders/{order_id}/approve-manual")
async def approve_manual_order_web(
    order_id: UUID,
    request: Request,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.APPROVE_PAYMENTS,
    )
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    customer = await session.get(Customer, order.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        payment = await approve_manual_order(
            session,
            order_id=order.id,
            actor_telegram_id=0,
        )
        await record_audit_event(
            session,
            actor_type="web_admin",
            actor_id=(
                str(principal.staff_id)
                if principal.staff_id is not None
                else "owner"
            ),
            action="payment.manual_approved",
            entity_type="order",
            entity_id=str(order.id),
            correlation_id=str(order.id),
            metadata={"payment_id": str(payment.id)},
        )
        await session.commit()
    except PaymentStateError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await _web_fulfill_order(
        request=request,
        session=session,
        settings=get_settings(),
        principal=principal,
        order=order,
        customer=customer,
    )


@router.post("/orders/{order_id}/reject-payment")
async def reject_manual_payment_web(
    order_id: UUID,
    request: Request,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.APPROVE_PAYMENTS,
    )
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    customer = await session.get(Customer, order.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        payment = await reject_pending_manual_payment(
            session,
            order_id=order.id,
        )
        await record_audit_event(
            session,
            actor_type="web_admin",
            actor_id=(
                str(principal.staff_id)
                if principal.staff_id is not None
                else "owner"
            ),
            action="payment.manual_rejected",
            entity_type="order",
            entity_id=str(order.id),
            correlation_id=str(order.id),
            metadata={"payment_id": str(payment.id)},
        )
        await session.commit()
    except PaymentStateError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    notified = False
    bot = _web_bot(request)
    if bot is not None:
        try:
            await bot.send_message(
                customer.telegram_user_id,
                "❌ رسید پرداخت شما تأیید نشد. "
                "می‌توانید رسید صحیح را دوباره ارسال کنید.",
            )
            notified = True
        except TelegramAPIError:
            pass

    return {
        "order_id": str(order.id),
        "status": order.status.value,
        "payment_id": str(payment.id),
        "customer_notified": notified,
    }


@router.post("/orders/{order_id}/cancel")
async def cancel_order_web(
    order_id: UUID,
    request: Request,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_ORDERS,
    )
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    customer = await session.get(Customer, order.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    try:
        order = await cancel_unpaid_order(
            session,
            order_id=order.id,
        )
        await record_audit_event(
            session,
            actor_type="web_admin",
            actor_id=(
                str(principal.staff_id)
                if principal.staff_id is not None
                else "owner"
            ),
            action="order.canceled",
            entity_type="order",
            entity_id=str(order.id),
            correlation_id=str(order.id),
        )
        await session.commit()
    except PaymentStateError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    notified = False
    bot = _web_bot(request)
    if bot is not None:
        try:
            await bot.send_message(
                customer.telegram_user_id,
                f"🗑 سفارش <code>{order.id}</code> توسط مدیریت لغو شد.",
            )
            notified = True
        except TelegramAPIError:
            pass

    return {
        "order_id": str(order.id),
        "status": order.status.value,
        "customer_notified": notified,
    }


@router.post("/orders/{order_id}/fulfill")
async def fulfill_order_web(
    order_id: UUID,
    request: Request,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PASARGUARD,
    )
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    customer = await session.get(Customer, order.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    return await _web_fulfill_order(
        request=request,
        session=session,
        settings=get_settings(),
        principal=principal,
        order=order,
        customer=customer,
    )


@router.post("/orders/{order_id}/reissue-credentials")
async def reissue_order_credentials_web(
    order_id: UUID,
    request: Request,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PASARGUARD,
    )
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.kind != OrderKind.NEW:
        raise HTTPException(
            status_code=400,
            detail="Only new reseller orders have credentials to reissue",
        )
    customer = await session.get(Customer, order.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    account = await session.scalar(
        select(PasarGuardAccount).where(PasarGuardAccount.order_id == order.id)
    )
    if account is None:
        raise HTTPException(status_code=400, detail="Provisioned account not found")

    settings = get_settings()
    instance_router = PasarGuardInstanceRouter(settings=settings)
    try:
        target = await instance_router.target_for_account(
            session,
            account=account,
        )
        service = ProvisioningService(
            client=target.client,
            reseller_role_id=target.reseller_role_id,
            reseller_role_name=target.reseller_role_name,
            pasarguard_instance_id=target.instance_id,
        )
        outcome = await service.reissue_credentials(
            session,
            order_id=order.id,
        )
    except (PasarGuardError, ProvisioningStateError) as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        if "target" in locals():
            await target.client.close()

    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=(
            str(principal.staff_id)
            if principal.staff_id is not None
            else "owner"
        ),
        action=(
            "credentials.web_reissued"
            if outcome.success
            else "credentials.web_reissue_failed"
        ),
        entity_type="order",
        entity_id=str(order.id),
        correlation_id=str(order.id),
        metadata={"error_code": outcome.error_code},
    )
    await session.commit()

    delivered = False
    bot = _web_bot(request)
    if outcome.success and outcome.credentials is not None and bot is not None:
        panel_url = await resolve_order_panel_url(
            session,
            settings=settings,
            order_id=order.id,
        )
        try:
            await bot.send_message(
                customer.telegram_user_id,
                "<b>مشخصات ورود جدید پنل نمایندگی</b>\n\n"
                f"آدرس پنل: <code>{panel_url}</code>\n"
                f"نام کاربری: <code>{outcome.credentials.username}</code>\n"
                f"رمز عبور: <code>{outcome.credentials.password}</code>\n\n"
                "رمز قبلی دیگر معتبر نیست.",
            )
            delivered = True
        except TelegramAPIError:
            pass

    return {
        "order_id": str(order.id),
        "success": outcome.success,
        "credentials_delivered": delivered,
        "error_code": outcome.error_code,
        "error_message": outcome.error_message,
    }


@router.get("/payment-methods")
async def payment_methods(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PAYMENT_METHODS,
    )
    rows = (
        await session.scalars(
            select(PaymentMethodConfig).order_by(
                PaymentMethodConfig.sort_order.asc(),
                PaymentMethodConfig.created_at.asc(),
            )
        )
    ).all()
    return [payment_method_public_view(row) for row in rows]


@router.post("/payment-methods", status_code=201)
async def create_payment_method(
    payload: PaymentMethodRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PAYMENT_METHODS,
    )
    try:
        method = await configure_payment_method(
            session,
            settings=get_settings(),
            values=PaymentMethodInput(
                slug=payload.slug,
                kind=payload.kind,
                display_name=payload.display_name,
                is_enabled=payload.is_enabled,
                sandbox=payload.sandbox,
                sort_order=payload.sort_order,
                public_config=payload.public_config,
                credentials=payload.credentials,
            ),
        )
    except PaymentMethodStateError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="payment_method.created",
        entity_type="payment_method",
        entity_id=str(method.id),
        metadata={
            "slug": method.slug,
            "kind": method.kind,
            "enabled": method.is_enabled,
            "sandbox": method.sandbox,
        },
    )
    await session.commit()
    return payment_method_public_view(method)


@router.put("/payment-methods/{method_id}")
async def update_payment_method(
    method_id: UUID,
    payload: PaymentMethodRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PAYMENT_METHODS,
    )
    existing = await session.get(PaymentMethodConfig, method_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Payment method not found")

    try:
        method = await configure_payment_method(
            session,
            settings=get_settings(),
            method_id=method_id,
            values=PaymentMethodInput(
                slug=payload.slug,
                kind=payload.kind,
                display_name=payload.display_name,
                is_enabled=payload.is_enabled,
                sandbox=payload.sandbox,
                sort_order=payload.sort_order,
                public_config=payload.public_config,
                credentials=payload.credentials,
            ),
        )
    except PaymentMethodStateError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="payment_method.updated",
        entity_type="payment_method",
        entity_id=str(method.id),
        metadata={
            "slug": method.slug,
            "kind": method.kind,
            "enabled": method.is_enabled,
            "sandbox": method.sandbox,
            "credentials_replaced": payload.credentials is not None,
        },
    )
    await session.commit()
    return payment_method_public_view(method)


@router.delete("/payment-methods/{method_id}")
async def disable_payment_method(
    method_id: UUID,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PAYMENT_METHODS,
    )
    method = await session.get(PaymentMethodConfig, method_id)
    if method is None:
        raise HTTPException(status_code=404, detail="Payment method not found")

    method.is_enabled = False
    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="payment_method.disabled",
        entity_type="payment_method",
        entity_id=str(method.id),
        metadata={"slug": method.slug, "kind": method.kind},
    )
    await session.commit()
    return payment_method_public_view(method)


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


@router.get("/pasarguard/instances")
async def pasarguard_instances(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PASARGUARD,
    )
    rows = (
        await session.scalars(
            select(PasarGuardInstance).order_by(
                PasarGuardInstance.name.asc(),
                PasarGuardInstance.id.asc(),
            )
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "name": row.name,
            "base_url": row.base_url,
            "api_key_env_var": row.api_key_env_var,
            "bearer_token_env_var": row.bearer_token_env_var,
            "reseller_role_name": row.reseller_role_name,
            "reseller_role_id": row.reseller_role_id,
            "weight": row.weight,
            "enabled": row.is_enabled,
            "last_health_at": (
                row.last_health_at.isoformat()
                if row.last_health_at is not None
                else None
            ),
            "last_health_ok": row.last_health_ok,
        }
        for row in rows
    ]


@router.post("/pasarguard/instances", status_code=201)
async def create_pasarguard_instance(
    payload: PasarGuardInstanceCreateRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PASARGUARD,
    )
    if bool(payload.api_key_env_var) == bool(payload.bearer_token_env_var):
        raise HTTPException(
            status_code=400,
            detail="Configure exactly one credential environment variable name",
        )

    name = payload.name.strip()
    duplicate = await session.scalar(
        select(PasarGuardInstance).where(PasarGuardInstance.name == name)
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="PasarGuard instance name already exists")

    instance = PasarGuardInstance(
        name=name,
        base_url=str(payload.base_url).rstrip("/"),
        api_key_env_var=payload.api_key_env_var,
        bearer_token_env_var=payload.bearer_token_env_var,
        reseller_role_name=payload.reseller_role_name,
        reseller_role_id=payload.reseller_role_id,
        weight=payload.weight,
        is_enabled=payload.is_enabled,
    )
    session.add(instance)
    await session.flush()
    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="pasarguard_instance.created",
        entity_type="pasarguard_instance",
        entity_id=str(instance.id),
        metadata={
            "name": instance.name,
            "base_url": instance.base_url,
            "api_key_env_var": instance.api_key_env_var,
            "bearer_token_env_var": instance.bearer_token_env_var,
        },
    )
    await session.commit()
    return {"id": str(instance.id), "name": instance.name, "enabled": instance.is_enabled}


@router.patch("/pasarguard/instances/{instance_id}")
async def update_pasarguard_instance(
    instance_id: UUID,
    payload: PasarGuardInstanceUpdateRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PASARGUARD,
    )
    instance = await session.get(PasarGuardInstance, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="PasarGuard instance not found")

    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        name = str(changes["name"]).strip()
        duplicate = await session.scalar(
            select(PasarGuardInstance).where(
                PasarGuardInstance.name == name,
                PasarGuardInstance.id != instance.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="PasarGuard instance name already exists")
        instance.name = name
    if "base_url" in changes:
        instance.base_url = str(changes["base_url"]).rstrip("/")
    if "api_key_env_var" in changes:
        instance.api_key_env_var = changes["api_key_env_var"]
    if "bearer_token_env_var" in changes:
        instance.bearer_token_env_var = changes["bearer_token_env_var"]
    if bool(instance.api_key_env_var) == bool(instance.bearer_token_env_var):
        raise HTTPException(
            status_code=400,
            detail="Configure exactly one credential environment variable name",
        )
    if "reseller_role_name" in changes:
        instance.reseller_role_name = changes["reseller_role_name"]
    if "reseller_role_id" in changes:
        instance.reseller_role_id = changes["reseller_role_id"]
    if "weight" in changes:
        instance.weight = int(changes["weight"])
    if "is_enabled" in changes:
        instance.is_enabled = bool(changes["is_enabled"])

    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="pasarguard_instance.updated",
        entity_type="pasarguard_instance",
        entity_id=str(instance.id),
        metadata={"fields": sorted(changes)},
    )
    await session.commit()
    return {"id": str(instance.id), "name": instance.name, "enabled": instance.is_enabled}


@router.post("/pasarguard/instances/health")
async def check_pasarguard_instances(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_PASARGUARD,
    )
    router = PasarGuardInstanceRouter(settings=get_settings())
    rows = await router.health_snapshot(session)
    await session.commit()
    return rows


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
            "pasarguard_instance_id": (
                str(row.pasarguard_instance_id)
                if row.pasarguard_instance_id is not None
                else None
            ),
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


@router.get("/discounts")
async def discounts(
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> list[dict[str, object]]:
    await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_DISCOUNTS,
    )
    rows = (
        await session.scalars(
            select(DiscountCode).order_by(
                DiscountCode.created_at.desc(),
                DiscountCode.id.desc(),
            )
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "code": row.code,
            "kind": row.kind,
            "value_amount": row.value_amount,
            "value_percent": row.value_percent,
            "max_uses": row.max_uses,
            "used_count": row.used_count,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "active": row.is_active,
        }
        for row in rows
    ]


@router.post("/discounts", status_code=201)
async def create_discount(
    payload: DiscountCreateRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_DISCOUNTS,
    )
    try:
        code = normalize_discount_code(payload.code)
    except DiscountStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if payload.kind == DiscountKind.FIXED:
        if payload.value_amount is None or payload.value_percent is not None:
            raise HTTPException(
                status_code=400,
                detail="Fixed discount requires value_amount only",
            )
    elif payload.value_percent is None or payload.value_amount is not None:
        raise HTTPException(
            status_code=400,
            detail="Percent discount requires value_percent only",
        )

    duplicate = await session.scalar(
        select(DiscountCode).where(DiscountCode.code == code)
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Discount code already exists")

    discount = DiscountCode(
        code=code,
        kind=payload.kind.value,
        value_amount=payload.value_amount,
        value_percent=payload.value_percent,
        max_uses=payload.max_uses,
        used_count=0,
        expires_at=payload.expires_at,
        is_active=payload.is_active,
    )
    session.add(discount)
    await session.flush()
    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="discount.created",
        entity_type="discount_code",
        entity_id=str(discount.id),
        metadata={"code": discount.code, "kind": discount.kind},
    )
    await session.commit()
    return {"id": str(discount.id), "code": discount.code, "active": discount.is_active}


@router.patch("/discounts/{discount_id}")
async def update_discount(
    discount_id: UUID,
    payload: DiscountUpdateRequest,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_DISCOUNTS,
    )
    discount = await session.get(DiscountCode, discount_id)
    if discount is None:
        raise HTTPException(status_code=404, detail="Discount code not found")

    changes = payload.model_dump(exclude_unset=True)
    if "value_amount" in changes:
        if discount.kind != DiscountKind.FIXED.value:
            raise HTTPException(status_code=400, detail="Discount is not fixed")
        discount.value_amount = changes["value_amount"]
    if "value_percent" in changes:
        if discount.kind != DiscountKind.PERCENT.value:
            raise HTTPException(status_code=400, detail="Discount is not percent")
        discount.value_percent = changes["value_percent"]
    if "max_uses" in changes:
        max_uses = changes["max_uses"]
        if max_uses is not None and int(max_uses) < discount.used_count:
            raise HTTPException(
                status_code=400,
                detail="max_uses cannot be lower than used_count",
            )
        discount.max_uses = max_uses
    if "expires_at" in changes:
        discount.expires_at = changes["expires_at"]
    if "is_active" in changes:
        discount.is_active = bool(changes["is_active"])

    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="discount.updated",
        entity_type="discount_code",
        entity_id=str(discount.id),
        metadata={"fields": sorted(changes)},
    )
    await session.commit()
    return {"id": str(discount.id), "code": discount.code, "active": discount.is_active}


@router.delete("/discounts/{discount_id}")
async def archive_discount(
    discount_id: UUID,
    session: SessionDep,
    x_admin_key: AdminKeyHeader = None,
    authorization: AdminAuthorizationHeader = None,
) -> dict[str, object]:
    principal = await _require_web_permission(
        session,
        api_key=x_admin_key,
        authorization=authorization,
        permission=Permission.MANAGE_DISCOUNTS,
    )
    discount = await session.get(DiscountCode, discount_id)
    if discount is None:
        raise HTTPException(status_code=404, detail="Discount code not found")

    discount.is_active = False
    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=str(principal.staff_id) if principal.staff_id is not None else "owner",
        action="discount.archived",
        entity_type="discount_code",
        entity_id=str(discount.id),
    )
    await session.commit()
    return {"id": str(discount.id), "active": False}


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
