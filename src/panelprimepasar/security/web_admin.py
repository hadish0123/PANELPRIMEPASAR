import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from uuid import UUID

from panelprimepasar.security.permissions import AdminRole

_PASSWORD_SCHEME = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 600_000


class WebAdminSecurityError(ValueError):
    """Raised when a web-admin credential or session token is invalid."""


@dataclass(frozen=True, slots=True)
class WebAdminSessionClaims:
    role: AdminRole
    staff_id: UUID | None
    expires_at: int


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise WebAdminSecurityError("Password must contain at least 12 characters")
    if len(password) > 512:
        raise WebAdminSecurityError("Password is too long")

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PASSWORD_ITERATIONS,
    )
    return (
        f"{_PASSWORD_SCHEME}$"
        f"{_PASSWORD_ITERATIONS}$"
        f"{_b64encode(salt)}$"
        f"{_b64encode(digest)}"
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if encoded is None:
        return False

    try:
        scheme, iterations_raw, salt_raw, digest_raw = encoded.split("$", maxsplit=3)
        if scheme != _PASSWORD_SCHEME:
            return False
        iterations = int(iterations_raw)
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def create_session_token(
    *,
    role: AdminRole,
    staff_id: UUID | None,
    secret: str,
    ttl_seconds: int,
) -> str:
    if not secret:
        raise WebAdminSecurityError("Session signing secret is not configured")
    if ttl_seconds < 300 or ttl_seconds > 604_800:
        raise WebAdminSecurityError("Session TTL must be between 5 minutes and 7 days")

    expires_at = int(time.time()) + ttl_seconds
    payload = json.dumps(
        {
            "v": 1,
            "role": role.value,
            "staff_id": str(staff_id) if staff_id is not None else None,
            "exp": expires_at,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = _b64encode(payload)
    signature = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64encode(signature)}"


def verify_session_token(
    token: str,
    *,
    secret: str,
    now: int | None = None,
) -> WebAdminSessionClaims:
    if not secret:
        raise WebAdminSecurityError("Session signing secret is not configured")

    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        supplied_signature = _b64decode(encoded_signature)
    except (ValueError, TypeError):
        raise WebAdminSecurityError("Invalid session token") from None

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise WebAdminSecurityError("Invalid session token")

    try:
        raw: object = json.loads(_b64decode(encoded_payload))
    except (ValueError, UnicodeDecodeError):
        raise WebAdminSecurityError("Invalid session token") from None

    if not isinstance(raw, dict):
        raise WebAdminSecurityError("Invalid session token")

    version = raw.get("v")
    role_raw = raw.get("role")
    staff_id_raw = raw.get("staff_id")
    expires_raw = raw.get("exp")
    if version != 1 or not isinstance(role_raw, str) or not isinstance(expires_raw, int):
        raise WebAdminSecurityError("Invalid session token")

    try:
        role = AdminRole(role_raw)
        if staff_id_raw is None:
            staff_id = None
        elif isinstance(staff_id_raw, str):
            staff_id = UUID(staff_id_raw)
        else:
            raise ValueError
    except ValueError:
        raise WebAdminSecurityError("Invalid session token") from None

    current_time = int(time.time()) if now is None else now
    if expires_raw <= current_time:
        raise WebAdminSecurityError("Session expired")

    return WebAdminSessionClaims(
        role=role,
        staff_id=staff_id,
        expires_at=expires_raw,
    )
