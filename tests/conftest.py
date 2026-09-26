import secrets
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.api import app
from panelprimepasar.config import get_settings
from panelprimepasar.db import engine, get_session


@pytest.fixture
def admin_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ADMIN_JWT_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("ADMIN_PANEL_API_KEY", "test-only-legacy-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session() -> AsyncIterator[AsyncSession]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        await transaction.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def api_client(
    db_session: AsyncSession, admin_settings: None
) -> AsyncIterator[httpx.AsyncClient]:
    async def session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = session_override
    transport = httpx.ASGITransport(app=app, client=(secrets.token_hex(16), 50000))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="https://test.local") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
