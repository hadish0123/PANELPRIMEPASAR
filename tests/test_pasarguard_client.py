import json

import httpx
import pytest

from panelprimepasar.integrations.pasarguard import (
    PasarGuardClient,
    PasarGuardConfigurationError,
    PasarGuardPermissionError,
)


@pytest.mark.asyncio
async def test_list_roles_uses_api_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Api-Key"] == "pg_key_test"
        assert request.url.path == "/api/admin-roles/simple"
        return httpx.Response(
            200,
            json={
                "roles": [
                    {"id": 3, "name": "operator", "is_owner": False},
                    {"id": 7, "name": "نمایندگان", "is_owner": False},
                ],
                "total": 2,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://panel.example",
    ) as http_client:
        client = PasarGuardClient(
            base_url="https://panel.example",
            api_key="pg_key_test",
            client=http_client,
        )
        roles = await client.list_roles_simple()

    assert [role.id for role in roles] == [3, 7]


@pytest.mark.asyncio
async def test_resolve_reseller_role_by_name_rejects_owner() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "roles": [{"id": 1, "name": "owner", "is_owner": True}],
                "total": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://panel.example",
    ) as http_client:
        client = PasarGuardClient(
            base_url="https://panel.example",
            api_key="pg_key_test",
            client=http_client,
        )
        with pytest.raises(PasarGuardConfigurationError):
            await client.resolve_reseller_role(role_id=None, role_name="owner")


@pytest.mark.asyncio
async def test_create_admin_includes_role_and_data_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/admin"
        payload = json.loads(request.content)
        assert payload["username"] == "customer_4821"
        assert payload["role_id"] == 7
        assert payload["data_limit"] == 1_000_000_000_000
        return httpx.Response(
            201,
            json={
                "id": 42,
                "username": "customer_4821",
                "data_limit": 1_000_000_000_000,
                "status": "active",
                "role": {"id": 7, "name": "نمایندگان", "is_owner": False},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://panel.example",
    ) as http_client:
        client = PasarGuardClient(
            base_url="https://panel.example",
            api_key="pg_key_test",
            client=http_client,
        )
        admin = await client.create_admin(
            username="customer_4821",
            password="strong-password",
            role_id=7,
            data_limit=1_000_000_000_000,
        )

    assert admin.id == 42
    assert admin.data_limit == 1_000_000_000_000


@pytest.mark.asyncio
async def test_create_admin_sends_zero_data_limit_for_unlimited() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["data_limit"] == 0
        return httpx.Response(
            201,
            json={
                "id": 43,
                "username": "unlimited_customer",
                "data_limit": 0,
                "status": "active",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://panel.example",
    ) as http_client:
        client = PasarGuardClient(
            base_url="https://panel.example",
            api_key="pg_key_test",
            client=http_client,
        )
        admin = await client.create_admin(
            username="unlimited_customer",
            password="strong-password",
            role_id=7,
            data_limit=0,
        )

    assert admin.data_limit == 0


@pytest.mark.asyncio
async def test_permission_error_is_typed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "Permission denied"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://panel.example",
    ) as http_client:
        client = PasarGuardClient(
            base_url="https://panel.example",
            api_key="pg_key_test",
            client=http_client,
        )
        with pytest.raises(PasarGuardPermissionError, match="Permission denied"):
            await client.list_roles_simple()



@pytest.mark.asyncio
async def test_find_admin_by_username_uses_singular_username_filter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/admins"
        assert request.url.params["username"] == "target_admin"
        assert "usernames" not in request.url.params
        return httpx.Response(
            200,
            json={
                "admins": [
                    {
                        "id": 77,
                        "username": "target_admin",
                        "data_limit": 1000,
                        "status": "active",
                    }
                ],
                "total": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://panel.example",
    ) as http_client:
        client = PasarGuardClient(
            base_url="https://panel.example",
            api_key="pg_key_test",
            client=http_client,
        )
        admin = await client.find_admin_by_username("target_admin")

    assert admin is not None
    assert admin.id == 77


@pytest.mark.asyncio
async def test_ensure_admin_refetches_created_admin_by_username() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(f"{request.method} {request.url.path}")
        if request.method == "GET" and request.url.path == "/api/admins":
            username = request.url.params.get("username")
            if requests.count("GET /api/admins") == 1:
                return httpx.Response(200, json={"admins": [], "total": 0})
            assert username == "new_reseller"
            return httpx.Response(
                200,
                json={
                    "admins": [
                        {
                            "id": 222,
                            "username": "new_reseller",
                            "data_limit": 5000,
                            "status": "active",
                        }
                    ],
                    "total": 1,
                },
            )

        if request.method == "POST" and request.url.path == "/api/admin":
            return httpx.Response(
                201,
                json={
                    "id": 124,
                    "username": "new_reseller",
                    "data_limit": 5000,
                    "status": "active",
                },
            )

        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://panel.example",
    ) as http_client:
        client = PasarGuardClient(
            base_url="https://panel.example",
            api_key="pg_key_test",
            client=http_client,
        )
        admin = await client.ensure_admin(
            username="new_reseller",
            password="strong-password",
            role_id=7,
            data_limit=5000,
        )

    assert admin.id == 222
    assert requests == [
        "GET /api/admins",
        "POST /api/admin",
        "GET /api/admins",
    ]
