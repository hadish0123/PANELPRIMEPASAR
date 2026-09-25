from uuid import UUID

from panelprimepasar.routers.customer import format_money, format_quota
from panelprimepasar.services.orders import checkout_idempotency_key


def test_checkout_idempotency_key_is_deterministic() -> None:
    plan_id = UUID("11111111-1111-1111-1111-111111111111")

    first = checkout_idempotency_key(
        telegram_user_id=123,
        message_id=456,
        plan_id=plan_id,
    )
    second = checkout_idempotency_key(
        telegram_user_id=123,
        message_id=456,
        plan_id=plan_id,
    )

    assert first == second
    assert first.endswith(str(plan_id))


def test_quota_formatter_preserves_decimal_and_binary_units() -> None:
    assert format_quota(1_000_000_000_000) == "1 TB"
    assert format_quota(1_099_511_627_776) == "1 TiB"


def test_money_formatter_does_not_mix_rial_and_toman() -> None:
    assert format_money(2_000_000, "IRR") == "2,000,000 ریال"
    assert format_money(200_000, "IRT") == "200,000 تومان"
