from uuid import uuid4

import pytest

from panelprimepasar.security import (
    AdminRole,
    WebAdminSecurityError,
    create_session_token,
    hash_password,
    verify_password,
    verify_session_token,
)


def test_password_hash_roundtrip() -> None:
    password = "correct-horse-battery-staple"
    encoded = hash_password(password)

    assert encoded != password
    assert verify_password(password, encoded)
    assert not verify_password("wrong-password-value", encoded)


def test_short_password_is_rejected() -> None:
    with pytest.raises(WebAdminSecurityError):
        hash_password("short")


def test_signed_admin_session_roundtrip() -> None:
    staff_id = uuid4()
    token = create_session_token(
        role=AdminRole.FINANCE,
        staff_id=staff_id,
        secret="test-secret-that-is-long-enough",
        ttl_seconds=3600,
    )
    claims = verify_session_token(
        token,
        secret="test-secret-that-is-long-enough",
        now=1,
    )

    assert claims.role == AdminRole.FINANCE
    assert claims.staff_id == staff_id
    assert claims.expires_at > 1


def test_session_signature_tampering_is_rejected() -> None:
    token = create_session_token(
        role=AdminRole.ADMIN,
        staff_id=uuid4(),
        secret="primary-secret",
        ttl_seconds=3600,
    )

    with pytest.raises(WebAdminSecurityError):
        verify_session_token(token, secret="different-secret")


def test_expired_session_is_rejected() -> None:
    token = create_session_token(
        role=AdminRole.SUPPORT,
        staff_id=uuid4(),
        secret="expiry-secret",
        ttl_seconds=300,
    )
    claims = verify_session_token(token, secret="expiry-secret", now=0)

    with pytest.raises(WebAdminSecurityError):
        verify_session_token(
            token,
            secret="expiry-secret",
            now=claims.expires_at,
        )
