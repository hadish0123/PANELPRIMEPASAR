import hashlib
import secrets
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request
from pwdlib import PasswordHash
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.db import get_session
from panelprimepasar.models import WebAdmin
from panelprimepasar.security.permissions import AdminRole, Permission, has_permission

Session = Annotated[AsyncSession, Depends(get_session)]
password_hasher = PasswordHash.recommended()
# Unknown users still incur the same password verification cost.
_dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValueError("Password must contain 12 to 128 characters")
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    return password_hasher.verify(password, encoded or _dummy_hash)


def jwt_secret() -> str:
    secret = get_settings().admin_jwt_secret
    if secret is None or len(secret.get_secret_value()) < 32:
        raise HTTPException(503, "ADMIN_JWT_SECRET must contain at least 32 characters")
    return secret.get_secret_value()


def issue_token(admin: WebAdmin) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(admin.id),
            "ver": admin.token_version,
            "iat": now,
            "exp": now + timedelta(minutes=get_settings().admin_token_minutes),
            "iss": "panelprimepasar",
            "aud": "admin",
            "jti": secrets.token_hex(16),
        },
        jwt_secret(),
        algorithm="HS256",
    )


@dataclass(frozen=True)
class Principal:
    id: UUID | None
    username: str
    role: AdminRole

    @property
    def actor_id(self) -> str:
        return str(self.id) if self.id else self.username


async def authenticate(
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
    x_admin_key: Annotated[str | None, Header()] = None,
) -> Principal:
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Invalid admin credentials")
        try:
            claims = jwt.decode(
                token,
                jwt_secret(),
                algorithms=["HS256"],
                audience="admin",
                issuer="panelprimepasar",
                options={"require": ["sub", "ver", "exp", "iat"]},
            )
            admin_id = UUID(claims["sub"])
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as exc:
            raise HTTPException(401, "Invalid or expired admin credentials") from exc
        admin = await session.get(WebAdmin, admin_id)
        if admin is None or not admin.is_active or claims["ver"] != admin.token_version:
            raise HTTPException(401, "Invalid or revoked admin credentials")
        return Principal(admin.id, admin.username, admin.role)

    configured = get_settings().admin_panel_api_key
    if (
        x_admin_key
        and configured
        and secrets.compare_digest(
            x_admin_key.encode(),
            configured.get_secret_value().encode(),
        )
    ):
        return Principal(None, "legacy_api_key", AdminRole.OWNER)
    raise HTTPException(401, "Invalid admin credentials", headers={"WWW-Authenticate": "Bearer"})


def require(permission: Permission) -> Callable[..., Coroutine[Any, Any, Principal]]:
    async def check(principal: Annotated[Principal, Depends(authenticate)]) -> Principal:
        if not has_permission(principal.role, permission):
            raise HTTPException(403, "Permission denied")
        return principal

    return check


async def limit_login(request: Request, username: str) -> None:
    """Atomic shared limits; fail closed if Redis is unavailable.

    The connection IP is used, never a caller-supplied forwarding header. Configure
    Uvicorn's trusted proxy list explicitly when deploying behind a reverse proxy.
    """
    settings = get_settings()
    ip = request.client.host if request.client else "unknown"
    script = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
    return count
    """
    try:
        async with Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        ) as redis:
            for label, value in (("ip", ip), ("user", username)):
                key = "admin-login:" + label + ":" + hashlib.sha256(value.encode()).hexdigest()
                count = await redis.eval(script, 1, key, settings.admin_login_window_seconds)
                if int(count) > settings.admin_login_attempts:
                    raise HTTPException(
                        429,
                        "Too many login attempts",
                        headers={
                            "Retry-After": str(settings.admin_login_window_seconds),
                        },
                    )
    except RedisError as exc:
        raise HTTPException(503, "Login rate limiter is unavailable") from exc
