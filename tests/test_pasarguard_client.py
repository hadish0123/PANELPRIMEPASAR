import json

import httpx
import pytest

from panelprimepasar.integrations.pasarguard import (
    PasarGuardClient,
    PasarGuardConfigurationError,
    PasarGuardError,
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
@pytest.mark.parametrize("payload", ["not-json", '{"unexpected": 1}'])
async def test_invalid_upstream_response_is_typed(payload: str) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=payload))
    async with httpx.AsyncClient(transport=transport, base_url="https://panel.example") as http:
        client = PasarGuardClient(base_url="https://panel.example", api_key="test", client=http)
        with pytest.raises(PasarGuardError, match="invalid response"):
            await client.list_roles_simple()


@pytest.mark.asyncio
async def test_api_key_is_never_forwarded_to_redirect_target() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://other.example/steal"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://panel.example",
        follow_redirects=True,
    ) as http:
        client = PasarGuardClient(base_url="https://panel.example", api_key="test", client=http)
        with pytest.raises(PasarGuardError):
            await client.list_roles_simple()
    assert len(calls) == 1
