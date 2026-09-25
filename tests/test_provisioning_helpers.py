import re
from uuid import UUID

import pytest

from panelprimepasar.services.provisioning import (
    build_reseller_username,
    generate_reseller_password,
)


def test_generated_username_fits_pasarguard_admin_column() -> None:
    username = build_reseller_username(
        telegram_user_id=9_223_372_036_854_775_807,
        order_id=UUID("12345678-1111-2222-3333-444444444444"),
    )

    assert len(username) <= 34
    assert re.fullmatch(r"[a-zA-Z0-9-_@.]+", username)


def test_generated_password_meets_pasarguard_policy() -> None:
    password = generate_reseller_password(username="r123_abcdef12")

    assert 12 <= len(password) <= 72
    assert len(re.findall(r"\d", password)) >= 2
    assert len(re.findall(r"[A-Z]", password)) >= 2
    assert len(re.findall(r"[a-z]", password)) >= 2
    assert re.search(r"[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/~\x60]", password)
    assert '"' not in password


def test_password_generator_rejects_invalid_requested_length() -> None:
    with pytest.raises(ValueError):
        generate_reseller_password(username="customer", length=11)

    with pytest.raises(ValueError):
        generate_reseller_password(username="customer", length=73)
