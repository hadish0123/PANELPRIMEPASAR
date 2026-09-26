import secrets
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import AuditEvent, Customer, Order, OrderStatus, Plan, WebAdmin
from panelprimepasar.security.auth import hash_password, issue_token
from panelprimepasar.security.permissions import AdminRole
from panelprimepasar.services.orders import get_or_create_checkout_order

pytestmark = pytest.mark.asyncio(loop_scope="session")
HEADERS = {"X-Admin-Key": "test-only-legacy-key"}


def plan_body() -> dict[str, object]:
    return {
        "name": "plan-" + uuid4().hex,
        "description": "توضیحات پلن",
        "quota_bytes": 10**12,
        "price_amount": 200000,
        "currency": "IRT",
        "validity_days": 30,
    }


async def token_for(
    session: AsyncSession, role: AdminRole = AdminRole.SUPPORT
) -> tuple[WebAdmin, str]:
    admin = WebAdmin(
        username=uuid4().hex, role=role, password_hash=hash_password("a-test-only-password")
    )
    session.add(admin)
    await session.flush()
    return admin, issue_token(admin)


async def test_api_rejects_missing_and_bad_credentials(api_client: httpx.AsyncClient) -> None:
    for headers in ({}, {"X-Admin-Key": "bad"}, {"Authorization": "Bearer invalid"}):
        response = await api_client.get("/admin/dashboard", headers=headers)
        assert response.status_code == 401


async def test_plan_crud_preserves_order_snapshot_and_safe_delete(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    body = plan_body()
    created = await api_client.post("/admin/plans", json=body, headers=HEADERS)
    assert created.status_code == 201, created.text
    plan_id = created.json()["id"]
    assert (await api_client.post("/admin/plans", json=body, headers=HEADERS)).status_code == 409
    # A duplicate request rolls back only its failed transaction; prior commits remain.
    plan = await db_session.scalar(select(Plan).where(Plan.name == body["name"]))
    customer = Customer(telegram_user_id=int(uuid4().hex[:12], 16))
    db_session.add(customer)
    await db_session.flush()
    assert plan is not None
    order, _ = await get_or_create_checkout_order(
        db_session, customer=customer, plan=plan, idempotency_key=uuid4().hex
    )
    await db_session.commit()
    assert (await api_client.delete(f"/admin/plans/{plan_id}", headers=HEADERS)).status_code == 409
    body.update(price_amount=350000, is_active=False)
    result = await api_client.put(f"/admin/plans/{plan_id}", json=body, headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["active"] is False
    assert order.price_amount == 200000
    assert await db_session.scalar(select(AuditEvent.id).where(AuditEvent.action == "plan.updated"))
    unused = await api_client.post("/admin/plans", json=plan_body(), headers=HEADERS)
    assert (
        await api_client.delete(f"/admin/plans/{unused.json()['id']}", headers=HEADERS)
    ).status_code == 204


async def test_customer_literal_search_bigint_and_pagination(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    prefix = uuid4().hex[:8]
    for i, name in enumerate((prefix + "_abc", prefix + "Xabc", prefix + "%")):
        db_session.add(
            Customer(
                telegram_user_id=int(uuid4().hex[:12], 16),
                telegram_username=name,
                is_blocked=i == 1,
            )
        )
    await db_session.flush()
    response = await api_client.get(
        "/admin/customers", headers=HEADERS, params={"search": prefix + "_"}
    )
    assert len(response.json()) == 1
    assert response.json()[0]["username"] == prefix + "_abc"
    response = await api_client.get(
        "/admin/customers", headers=HEADERS, params={"search": "9999999999999999999"}
    )
    assert response.status_code == 200
    response = await api_client.get(
        "/admin/customers", headers=HEADERS, params={"search": prefix, "limit": 1, "offset": 1}
    )
    assert response.headers["X-Total-Count"] == "3"
    assert len(response.json()) == 1


@pytest.mark.parametrize(
    "path",
    ["customers?limit=0", "customers?limit=101", "orders?offset=-1", "orders?status=unknown"],
)
async def test_query_bounds(api_client: httpx.AsyncClient, path: str) -> None:
    assert (await api_client.get("/admin/" + path, headers=HEADERS)).status_code == 422


async def test_role_permissions_and_revoked_tokens(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin, token = await token_for(db_session)
    bearer = {"Authorization": "Bearer " + token}
    assert (await api_client.get("/admin/customers", headers=bearer)).status_code == 200
    assert (await api_client.get("/admin/payments", headers=bearer)).status_code == 403
    assert (
        await api_client.post("/admin/plans", json=plan_body(), headers=bearer)
    ).status_code == 403
    assert (
        await api_client.patch(
            f"/admin/customers/{uuid4()}", json={"blocked": True}, headers=bearer
        )
    ).status_code == 403
    reset = await api_client.post(
        f"/admin/admins/{admin.id}/password",
        json={"password": "another-test-password"},
        headers=HEADERS,
    )
    assert reset.status_code == 204
    assert (await api_client.get("/admin/me", headers=bearer)).status_code == 401


async def test_last_owner_cannot_be_disabled(
    api_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin, _ = await token_for(db_session, AdminRole.OWNER)
    response = await api_client.patch(
        f"/admin/admins/{admin.id}", json={"role": "support", "is_active": False}, headers=HEADERS
    )
    assert response.status_code == 409


async def test_login_logout_and_throttle(
    api_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin, _ = await token_for(db_session)
    response = await api_client.post(
        "/admin/login", json={"username": admin.username, "password": "a-test-only-password"}
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert (await api_client.get("/admin/me", headers=headers)).status_code == 200
    assert (await api_client.post("/admin/logout", headers=headers)).status_code == 204
    assert (await api_client.get("/admin/me", headers=headers)).status_code == 401
    for _ in range(9):
        assert (
            await api_client.post(
                "/admin/login", json={"username": admin.username, "password": "wrong"}
            )
        ).status_code == 401
    assert (
        await api_client.post(
            "/admin/login", json={"username": admin.username, "password": "wrong"}
        )
    ).status_code == 429


async def test_block_and_cancel_operations(
    api_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    customer = Customer(telegram_user_id=int(secrets.token_hex(6), 16))
    plan = Plan(**plan_body())
    db_session.add_all([customer, plan])
    await db_session.flush()
    order, _ = await get_or_create_checkout_order(
        db_session, customer=customer, plan=plan, idempotency_key=uuid4().hex
    )
    await db_session.commit()
    response = await api_client.patch(
        f"/admin/customers/{customer.id}", json={"blocked": True}, headers=HEADERS
    )
    assert response.status_code == 200
    response = await api_client.post(f"/admin/orders/{order.id}/cancel", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    assert (
        await api_client.post(f"/admin/orders/{order.id}/approve", headers=HEADERS)
    ).status_code == 409
    assert (await db_session.get(Order, order.id)).status == OrderStatus.CANCELED
