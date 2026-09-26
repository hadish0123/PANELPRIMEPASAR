from uuid import UUID

from panelprimepasar.routers.customer import format_money, format_quota
from panelprimepasar.services.orders import checkout_idempotency_key
from panelprimepasar.services.subscriptions import combined_quota_bytes


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


def test_quota_formatter_always_uses_entered_gigabytes() -> None:
    assert format_quota(1_000_000_000_000) == "1000 GB"
    assert format_quota(500_000_000_000) == "500 GB"
    assert format_quota(0) == "نامحدود"


def test_combining_any_quota_with_unlimited_stays_unlimited() -> None:
    assert combined_quota_bytes(500_000_000_000, 0) == 0
    assert combined_quota_bytes(0, 100_000_000_000) == 0
    assert combined_quota_bytes(500_000_000_000, 100_000_000_000) == 600_000_000_000


def test_money_formatter_does_not_mix_rial_and_toman() -> None:
    assert format_money(2_000_000, "IRR") == "2,000,000 ریال"
    assert format_money(200_000, "IRT") == "200,000 تومان"
