import base64
import hashlib
import json
from collections.abc import Mapping

from cryptography.fernet import Fernet, InvalidToken


class PaymentSecretError(ValueError):
    """Raised when encrypted payment credentials cannot be processed."""


def _fernet(master_key: str) -> Fernet:
    if len(master_key) < 32:
        raise PaymentSecretError(
            "PAYMENT_CREDENTIALS_MASTER_KEY must contain at least 32 characters"
        )
    derived = hashlib.sha256(master_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_payment_secrets(
    values: Mapping[str, str],
    *,
    master_key: str,
) -> str:
    payload = {
        str(key): str(value)
        for key, value in values.items()
        if str(value)
    }
    raw = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _fernet(master_key).encrypt(raw).decode("ascii")


def decrypt_payment_secrets(
    token: str | None,
    *,
    master_key: str,
) -> dict[str, str]:
    if not token:
        return {}
    try:
        raw = _fernet(master_key).decrypt(token.encode("ascii"))
        decoded: object = json.loads(raw)
    except (InvalidToken, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PaymentSecretError(
            "Stored payment credentials cannot be decrypted"
        ) from exc

    if not isinstance(decoded, dict):
        raise PaymentSecretError("Stored payment credentials have invalid format")

    result: dict[str, str] = {}
    for key, value in decoded.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaymentSecretError("Stored payment credentials have invalid format")
        result[key] = value
    return result
