from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import ColumnElement, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from panelprimepasar.admin_schemas import (
    AdminInput,
    AdminUpdate,
    BlockCustomer,
    Login,
    PasswordInput,
    PlanInput,
)
from panelprimepasar.bot import build_bot
from panelprimepasar.config import get_settings
from panelprimepasar.integrations.factory import build_pasarguard_client
from panelprimepasar.integrations.pasarguard import PasarGuardError
from panelprimepasar.models import (
    AuditEvent,
    Customer,
    Order,
    OrderStatus,
    PasarGuardAccount,
    Payment,
    PaymentStatus,
    Plan,
    ProvisioningJob,
    ProvisioningStatus,
    WebAdmin,
)
from panelprimepasar.security.auth import (
    Principal,
    Session,
    authenticate,
    hash_password,
    issue_token,
    jwt_secret,
    limit_login,
    require,
    verify_password,
)
from panelprimepasar.security.permissions import ROLE_PERMISSIONS, AdminRole, Permission
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.delivery import deliver_credentials
from panelprimepasar.services.orders import OrderStateError, cancel_order
from panelprimepasar.services.payments import (
    PaymentStateError,
    approve_manual_order,
    fail_payment,
)
from panelprimepasar.services.provisioning import ProvisioningService, ProvisioningStateError

router = APIRouter(prefix="/admin", tags=["admin"])
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
DashboardAccess = Annotated[Principal, Depends(require(Permission.VIEW_DASHBOARD))]
UserAccess = Annotated[Principal, Depends(require(Permission.VIEW_USERS))]
BlockAccess = Annotated[Principal, Depends(require(Permission.BLOCK_USERS))]
PlanAccess = Annotated[Principal, Depends(require(Permission.MANAGE_PLANS))]
OrderAccess = Annotated[Principal, Depends(require(Permission.VIEW_ORDERS))]
OrderWrite = Annotated[Principal, Depends(require(Permission.MANAGE_ORDERS))]
PaymentAccess = Annotated[Principal, Depends(require(Permission.APPROVE_PAYMENTS))]
AuditAccess = Annotated[Principal, Depends(require(Permission.VIEW_AUDIT_LOGS))]
AdminAccess = Annotated[Principal, Depends(require(Permission.MANAGE_ADMINS))]
ProvisionAccess = Annotated[Principal, Depends(require(Permission.MANAGE_PASARGUARD))]


def plan_data(plan: Plan) -> dict[str, Any]:
    return {
        "id": str(plan.id),
        "name": plan.name,
        "description": plan.description,
        "quota_bytes": plan.quota_bytes,
        "price_amount": plan.price_amount,
        "currency": plan.currency,
        "validity_days": plan.validity_days,
        "active": plan.is_active,
        "is_active": plan.is_active,
        "sort_order": plan.sort_order,
    }


def customer_data(customer: Customer) -> dict[str, Any]:
    return {
        "id": str(customer.id),
        "telegram_user_id": customer.telegram_user_id,
        "username": customer.telegram_username or "",
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "blocked": customer.is_blocked,
    }


def order_data(order: Order) -> dict[str, Any]:
    return {
        "id": str(order.id),
        "customer_id": str(order.customer_id),
        "plan_id": str(order.plan_id),
        "status": order.status.value,
        "amount": order.price_amount,
        "currency": order.currency,
        "quota_bytes": order.quota_bytes,
        "validity_days": order.validity_days,
        "created_at": order.created_at,
    }


def payment_data(payment: Payment) -> dict[str, Any]:
    return {
        "id": str(payment.id),
        "order_id": str(payment.order_id),
        "amount": payment.amount,
        "currency": payment.currency,
        "provider": payment.provider,
        "status": payment.status.value,
        "verified_at": payment.verified_at,
        "created_at": payment.created_at,
        "transaction_id": payment.provider_transaction_id,
        "receipt_available": bool(
            payment.raw_reference and payment.raw_reference.startswith("telegram:")
        ),
    }


def account_data(account: PasarGuardAccount) -> dict[str, Any]:
    return {
        "id": str(account.id),
        "order_id": str(account.order_id),
        "customer_id": str(account.customer_id),
        "username": account.username,
        "quota_bytes": account.quota_bytes,
        "is_active": account.is_active,
        "role_name": account.role_name,
        "created_at": account.created_at,
    }


def admin_data(admin: WebAdmin) -> dict[str, Any]:
    return {
        "id": str(admin.id),
        "username": admin.username,
        "role": admin.role.value,
        "is_active": admin.is_active,
    }


async def audit(
    session: Session, actor: Principal, action: str, entity: str, entity_id: UUID, **metadata: Any
) -> None:
    await record_audit_event(
        session,
        actor_type="web_admin",
        actor_id=actor.actor_id,
        action=action,
        entity_type=entity,
        entity_id=str(entity_id),
        correlation_id=str(entity_id),
        metadata=metadata or None,
    )


async def commit(session: Session) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Record conflicts with an existing record") from exc


@router.get("/ui", include_in_schema=False)
async def ui() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "admin.html")


@router.post("/login")
async def login(body: Login, request: Request, session: Session) -> dict[str, Any]:
    jwt_secret()
    await limit_login(request, body.username)
    admin = await session.scalar(select(WebAdmin).where(WebAdmin.username == body.username))
    valid = await run_in_threadpool(
        verify_password,
        body.password,
        admin.password_hash if admin else None,
    )
    if not valid or admin is None or not admin.is_active:
        await record_audit_event(
            session,
            actor_type="anonymous",
            actor_id=None,
            action="admin.login_failed",
            entity_type="admin",
            entity_id=str(admin.id) if admin else None,
        )
        await session.commit()
        raise HTTPException(401, "Invalid admin credentials")
    token = issue_token(admin)
    await audit(
        session, Principal(admin.id, admin.username, admin.role), "admin.login", "admin", admin.id
    )
    await session.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": get_settings().admin_token_minutes * 60,
    }


@router.get("/me")
async def me(actor: Annotated[Principal, Depends(authenticate)]) -> dict[str, Any]:
    return {
        "id": str(actor.id) if actor.id else None,
        "username": actor.username,
        "role": actor.role.value,
        "permissions": sorted(p.value for p in ROLE_PERMISSIONS[actor.role]),
    }


@router.post("/logout", status_code=204)
async def logout(actor: Annotated[Principal, Depends(authenticate)], session: Session) -> Response:
    if actor.id is not None:
        admin = await session.scalar(
            select(WebAdmin).where(WebAdmin.id == actor.id).with_for_update()
        )
        if admin:
            admin.token_version += 1
            await audit(session, actor, "admin.logout", "admin", admin.id)
            await session.commit()
    return Response(status_code=204)


@router.get("/dashboard")
async def dashboard(actor: DashboardAccess, session: Session) -> dict[str, Any]:
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    today = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    metrics: dict[str, Any] = {"panel": "PANELPRIMEPASAR", "reporting_timezone": "Asia/Tehran"}
    counts = {
        "customers": select(func.count(Customer.id)),
        "plans": select(func.count(Plan.id)),
        "orders": select(func.count(Order.id)),
        "paid_orders": select(func.count(Order.id)).where(Order.status == OrderStatus.PAID),
        "verified_payments": select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.VERIFIED
        ),
        "pending_payments": select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.PENDING
        ),
        "pasarguard_accounts": select(func.count(PasarGuardAccount.id)),
        "active_accounts": select(func.count(PasarGuardAccount.id)).where(
            PasarGuardAccount.is_active.is_(True)
        ),
        "failed_provisioning": select(func.count(ProvisioningJob.id)).where(
            ProvisioningJob.status == ProvisioningStatus.FAILED
        ),
    }
    for name, query in counts.items():
        metrics[name] = int(await session.scalar(query) or 0)
    for name, start in (("daily_sales", today), ("monthly_revenue", month)):
        rows = await session.execute(
            select(
                Payment.currency,
                func.sum(Payment.amount),
                func.count(Payment.id),
            )
            .where(Payment.status == PaymentStatus.VERIFIED, Payment.verified_at >= start)
            .group_by(Payment.currency)
        )
        metrics[name] = [
            {"currency": row[0], "amount": int(row[1]), "count": row[2]} for row in rows
        ]
    return metrics


@router.get("/customers")
async def customers(
    actor: UserAccess,
    session: Session,
    response: Response,
    search: Annotated[str | None, Query(max_length=128)] = None,
    blocked: bool | None = None,
    offset: Offset = 0,
    limit: Limit = 100,
) -> list[dict[str, Any]]:
    query = select(Customer)
    if blocked is not None:
        query = query.where(Customer.is_blocked == blocked)
    term = search.strip() if search else ""
    if term:
        literal = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions: list[ColumnElement[bool]] = [
            Customer.telegram_username.ilike(f"%{literal}%", escape="\\"),
        ]
        if term.isdecimal() and len(term) <= 19 and int(term) <= 2**63 - 1:
            conditions.append(Customer.telegram_user_id == int(term))
        query = query.where(or_(*conditions))
    response.headers["X-Total-Count"] = str(
        await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    )
    rows = await session.scalars(
        query.order_by(Customer.created_at.desc(), Customer.id.desc()).offset(offset).limit(limit)
    )
    return [customer_data(row) for row in rows]


@router.get("/customers/{customer_id}")
async def customer_details(
    customer_id: UUID, actor: UserAccess, session: Session
) -> dict[str, Any]:
    customer = await session.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    orders = await session.scalars(
        select(Order)
        .where(Order.customer_id == customer_id)
        .order_by(Order.created_at.desc())
        .limit(100)
    )
    accounts = await session.scalars(
        select(PasarGuardAccount)
        .where(PasarGuardAccount.customer_id == customer_id)
        .order_by(PasarGuardAccount.created_at.desc())
        .limit(100)
    )
    return {
        **customer_data(customer),
        "orders": [order_data(o) for o in orders],
        "accounts": [account_data(a) for a in accounts],
    }


@router.patch("/customers/{customer_id}")
async def block_customer(
    customer_id: UUID, body: BlockCustomer, actor: BlockAccess, session: Session
) -> dict[str, Any]:
    customer = await session.scalar(
        select(Customer).where(Customer.id == customer_id).with_for_update()
    )
    if customer is None:
        raise HTTPException(404, "Customer not found")
    customer.is_blocked = body.blocked
    await audit(
        session,
        actor,
        "customer.blocked" if body.blocked else "customer.unblocked",
        "customer",
        customer.id,
    )
    await commit(session)
    return customer_data(customer)


@router.get("/plans")
async def plans(
    actor: PlanAccess, session: Session, response: Response, offset: Offset = 0, limit: Limit = 100
) -> list[dict[str, Any]]:
    response.headers["X-Total-Count"] = str(await session.scalar(select(func.count(Plan.id))) or 0)
    rows = await session.scalars(
        select(Plan).order_by(Plan.created_at.desc(), Plan.id.desc()).offset(offset).limit(limit)
    )
    return [plan_data(row) for row in rows]


@router.post("/plans", status_code=201)
async def create_plan(body: PlanInput, actor: PlanAccess, session: Session) -> dict[str, Any]:
    plan = Plan(**body.model_dump())
    session.add(plan)
    try:
        await session.flush()
        await audit(session, actor, "plan.created", "plan", plan.id, **body.model_dump())
        await commit(session)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Plan name already exists") from exc
    return plan_data(plan)


@router.put("/plans/{plan_id}")
async def edit_plan(
    plan_id: UUID, body: PlanInput, actor: PlanAccess, session: Session
) -> dict[str, Any]:
    plan = await session.scalar(select(Plan).where(Plan.id == plan_id).with_for_update())
    if plan is None:
        raise HTTPException(404, "Plan not found")
    for key, value in body.model_dump().items():
        setattr(plan, key, value)
    try:
        await audit(session, actor, "plan.updated", "plan", plan.id, **body.model_dump())
        await commit(session)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Plan name already exists") from exc
    return plan_data(plan)


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_plan(plan_id: UUID, actor: PlanAccess, session: Session) -> Response:
    plan = await session.scalar(select(Plan).where(Plan.id == plan_id).with_for_update())
    if plan is None:
        raise HTTPException(404, "Plan not found")
    if await session.scalar(select(Order.id).where(Order.plan_id == plan_id).limit(1)):
        raise HTTPException(409, "Plan has orders; disable it instead")
    await audit(session, actor, "plan.deleted", "plan", plan.id)
    await session.delete(plan)
    await commit(session)
    return Response(status_code=204)


@router.get("/orders")
async def orders(
    actor: OrderAccess,
    session: Session,
    response: Response,
    order_status: Annotated[OrderStatus | None, Query(alias="status")] = None,
    customer_id: UUID | None = None,
    offset: Offset = 0,
    limit: Limit = 100,
) -> list[dict[str, Any]]:
    query = select(Order)
    if order_status is not None:
        query = query.where(Order.status == order_status)
    if customer_id is not None:
        query = query.where(Order.customer_id == customer_id)
    response.headers["X-Total-Count"] = str(
        await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    )
    rows = await session.scalars(
        query.order_by(Order.created_at.desc(), Order.id.desc()).offset(offset).limit(limit)
    )
    return [order_data(row) for row in rows]


@router.get("/orders/{order_id}")
async def order_details(order_id: UUID, actor: OrderAccess, session: Session) -> dict[str, Any]:
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(404, "Order not found")
    payments = await session.scalars(
        select(Payment)
        .where(Payment.order_id == order_id)
        .order_by(Payment.created_at.desc())
        .limit(100)
    )
    job = await session.scalar(select(ProvisioningJob).where(ProvisioningJob.order_id == order_id))
    return {
        **order_data(order),
        "payments": [payment_data(p) for p in payments],
        "provisioning": {
            "status": job.status.value,
            "attempts": job.attempts,
            "error_code": job.last_error_code,
        }
        if job
        else None,
    }


@router.post("/orders/{order_id}/cancel")
async def cancel(order_id: UUID, actor: OrderWrite, session: Session) -> dict[str, Any]:
    try:
        order = await cancel_order(session, order_id=order_id)
    except OrderStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    await audit(session, actor, "order.canceled", "order", order_id)
    await commit(session)
    return order_data(order)


@router.post("/orders/{order_id}/approve")
async def approve(order_id: UUID, actor: PaymentAccess, session: Session) -> dict[str, Any]:
    try:
        payment = await approve_manual_order(session, order_id=order_id, actor_telegram_id=0)
    except PaymentStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Payment has already been processed") from exc
    await audit(
        session,
        actor,
        "payment.manual_approved",
        "order",
        order_id,
        payment_id=str(payment.id),
        amount=payment.amount,
        currency=payment.currency,
    )
    await commit(session)
    return payment_data(payment)


@router.get("/payments")
async def payments(
    actor: PaymentAccess,
    session: Session,
    response: Response,
    payment_status: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    offset: Offset = 0,
    limit: Limit = 100,
) -> list[dict[str, Any]]:
    query = select(Payment)
    if payment_status is not None:
        query = query.where(Payment.status == payment_status)
    response.headers["X-Total-Count"] = str(
        await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    )
    rows = await session.scalars(
        query.order_by(Payment.created_at.desc(), Payment.id.desc()).offset(offset).limit(limit)
    )
    return [payment_data(row) for row in rows]


@router.post("/payments/{payment_id}/reject")
async def reject(payment_id: UUID, actor: PaymentAccess, session: Session) -> dict[str, Any]:
    try:
        payment = await fail_payment(session, payment_id=payment_id)
    except PaymentStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    await audit(session, actor, "payment.rejected", "payment", payment_id)
    await commit(session)
    return payment_data(payment)


@router.get("/payments/{payment_id}/receipt")
async def receipt(payment_id: UUID, actor: PaymentAccess, session: Session) -> Response:
    payment = await session.get(Payment, payment_id)
    if payment is None or not payment.raw_reference:
        raise HTTPException(404, "Receipt not found")
    parts = payment.raw_reference.split(":", 2)
    if len(parts) != 3 or parts[0] != "telegram" or parts[1] not in {"photo", "document"}:
        raise HTTPException(404, "Receipt not found")
    if get_settings().telegram_bot_token is None:
        raise HTTPException(503, "Telegram is not configured")
    from aiogram.exceptions import TelegramAPIError

    bot = build_bot(get_settings())
    try:
        file = await bot.get_file(parts[2])
        if file.file_size is None or file.file_size > 8 * 1024 * 1024:
            raise HTTPException(413, "Receipt exceeds 8 MiB")
        destination = BytesIO()
        await bot.download(file, destination=destination)
    except TelegramAPIError as exc:
        raise HTTPException(502, "Could not retrieve receipt") from exc
    finally:
        await bot.session.close()
    return Response(
        destination.getvalue(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="receipt"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/accounts")
async def accounts(
    actor: ProvisionAccess,
    session: Session,
    response: Response,
    offset: Offset = 0,
    limit: Limit = 100,
) -> list[dict[str, Any]]:
    response.headers["X-Total-Count"] = str(
        await session.scalar(select(func.count(PasarGuardAccount.id))) or 0
    )
    rows = await session.scalars(
        select(PasarGuardAccount)
        .order_by(PasarGuardAccount.created_at.desc(), PasarGuardAccount.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [account_data(row) for row in rows]


@router.get("/audit")
async def audit_logs(
    actor: AuditAccess,
    session: Session,
    response: Response,
    action: Annotated[str | None, Query(max_length=128)] = None,
    offset: Offset = 0,
    limit: Limit = 100,
) -> list[dict[str, Any]]:
    query = select(AuditEvent)
    if action:
        query = query.where(AuditEvent.action == action)
    response.headers["X-Total-Count"] = str(
        await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    )
    rows = await session.scalars(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [
        {
            "id": str(row.id),
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "actor_id": row.actor_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/admins")
async def admins(actor: AdminAccess, session: Session) -> list[dict[str, Any]]:
    rows = await session.scalars(select(WebAdmin).order_by(WebAdmin.username))
    return [admin_data(row) for row in rows]


@router.post("/admins", status_code=201)
async def create_admin(body: AdminInput, actor: AdminAccess, session: Session) -> dict[str, Any]:
    admin = WebAdmin(
        username=body.username,
        role=body.role,
        password_hash=await run_in_threadpool(hash_password, body.password),
    )
    session.add(admin)
    try:
        await session.flush()
        await audit(session, actor, "admin.created", "admin", admin.id, role=admin.role.value)
        await commit(session)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Admin username already exists") from exc
    return admin_data(admin)


@router.patch("/admins/{admin_id}")
async def edit_admin(
    admin_id: UUID, body: AdminUpdate, actor: AdminAccess, session: Session
) -> dict[str, Any]:
    # Serialize role/activation edits so two concurrent requests cannot remove the last owner.
    await session.execute(text("SELECT pg_advisory_xact_lock(7198241)"))
    admin = await session.scalar(select(WebAdmin).where(WebAdmin.id == admin_id).with_for_update())
    if admin is None:
        raise HTTPException(404, "Admin not found")
    if (
        admin.role == AdminRole.OWNER
        and admin.is_active
        and (body.role != AdminRole.OWNER or not body.is_active)
    ):
        owners = await session.scalar(
            select(func.count(WebAdmin.id)).where(
                WebAdmin.role == AdminRole.OWNER, WebAdmin.is_active.is_(True)
            )
        )
        if int(owners or 0) <= 1:
            raise HTTPException(409, "Cannot remove the last active owner")
    admin.role = body.role
    admin.is_active = body.is_active
    admin.token_version += 1
    await audit(
        session,
        actor,
        "admin.updated",
        "admin",
        admin.id,
        role=admin.role.value,
        is_active=admin.is_active,
    )
    await commit(session)
    return admin_data(admin)


@router.post("/admins/{admin_id}/password", status_code=204)
async def reset_password(
    admin_id: UUID, body: PasswordInput, actor: AdminAccess, session: Session
) -> Response:
    encoded = await run_in_threadpool(hash_password, body.password)
    admin = await session.scalar(select(WebAdmin).where(WebAdmin.id == admin_id).with_for_update())
    if admin is None:
        raise HTTPException(404, "Admin not found")
    admin.password_hash = encoded
    admin.token_version += 1
    await audit(session, actor, "admin.password_changed", "admin", admin.id)
    await commit(session)
    return Response(status_code=204)


@router.post("/orders/{order_id}/provision")
async def provision(
    order_id: UUID, actor: ProvisionAccess, session: Session, reissue: bool = False
) -> dict[str, Any]:
    settings = get_settings()
    if settings.telegram_bot_token is None:
        raise HTTPException(503, "Configure Telegram before provisioning credentials")
    try:
        client = build_pasarguard_client(settings)
    except PasarGuardError as exc:
        raise HTTPException(503, "PasarGuard integration is not configured") from exc
    service = ProvisioningService(
        client=client,
        reseller_role_id=settings.pasarguard_reseller_role_id,
        reseller_role_name=settings.pasarguard_reseller_role_name,
    )
    try:
        outcome = (
            await service.reissue_credentials(session, order_id=order_id)
            if reissue
            else await service.provision_paid_order(session, order_id=order_id)
        )
    except ProvisioningStateError as exc:
        raise HTTPException(409, str(exc)) from exc
    finally:
        await client.close()
    action = "credentials.reissued" if reissue else "provisioning.succeeded"
    if not outcome.success:
        action = "provisioning.failed"
    await audit(session, actor, action, "order", order_id, error_code=outcome.error_code)
    # Commit before delivery; a Telegram failure must not roll back the upstream account.
    await session.commit()
    delivered = False
    if outcome.credentials:
        order = await session.get(Order, order_id)
        customer = await session.get(Customer, order.customer_id) if order else None
        if customer:
            bot = build_bot(settings)
            try:
                delivered = await deliver_credentials(
                    bot=bot, settings=settings, customer=customer, outcome=outcome
                )
            finally:
                await bot.session.close()
        await audit(
            session,
            actor,
            "credentials.delivery_succeeded" if delivered else "credentials.delivery_failed",
            "order",
            order_id,
        )
        await session.commit()
    return {
        "success": outcome.success,
        "already_provisioned": outcome.already_provisioned,
        "credentials_delivered": delivered,
        "error_code": outcome.error_code,
    }


@router.get("/system")
async def system(actor: ProvisionAccess) -> dict[str, Any]:
    settings = get_settings()
    result: dict[str, Any] = {
        "telegram_configured": settings.telegram_bot_token is not None,
        "pasarguard_configured": False,
        "pasarguard_healthy": False,
    }
    try:
        client = build_pasarguard_client(settings)
    except PasarGuardError:
        return result
    result["pasarguard_configured"] = True
    try:
        result["pasarguard_healthy"] = await client.health()
        role = await client.resolve_reseller_role(
            role_id=settings.pasarguard_reseller_role_id,
            role_name=settings.pasarguard_reseller_role_name,
        )
        result["reseller_role"] = role.name
    except PasarGuardError as exc:
        result["error_code"] = type(exc).__name__
    finally:
        await client.close()
    return result
