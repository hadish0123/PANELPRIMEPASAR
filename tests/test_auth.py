from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from panelprimepasar.models import WebAdmin
from panelprimepasar.security.auth import hash_password, issue_token, jwt_secret, verify_password
from panelprimepasar.security.permissions import AdminRole, Permission, has_permission


def test_password_hashing_and_limits() -> None:
    password = "not-a-production-password"
    encoded = hash_password(password)
    assert encoded.startswith("$argon2id$")
    assert password not in encoded
    assert verify_password(password, encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password(password, None)
    with pytest.raises(ValueError):
        hash_password("short")


def test_token_is_expiring_signed_and_scoped(admin_settings: None) -> None:
    admin = WebAdmin(id=uuid4(), username="owner", role=AdminRole.OWNER, token_version=3)
    token = issue_token(admin)
    claims = jwt.decode(
        token, jwt_secret(), algorithms=["HS256"], issuer="panelprimepasar", audience="admin"
    )
    assert claims["sub"] == str(admin.id)
    assert claims["ver"] == 3
    assert claims["exp"] > claims["iat"]
    claims["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    expired = jwt.encode(claims, jwt_secret(), algorithm="HS256")
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(expired, jwt_secret(), algorithms=["HS256"], audience="admin")


def test_role_separation() -> None:
    assert has_permission(AdminRole.OWNER, Permission.MANAGE_ADMINS)
    assert not has_permission(AdminRole.ADMIN, Permission.MANAGE_ADMINS)
    assert not has_permission(AdminRole.SUPPORT, Permission.APPROVE_PAYMENTS)
    assert not has_permission(AdminRole.SUPPORT, Permission.BLOCK_USERS)
    assert has_permission(AdminRole.SUPPORT, Permission.VIEW_USERS)
    assert not has_permission(AdminRole.FINANCE, Permission.MANAGE_PASARGUARD)
