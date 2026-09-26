import pytest

from panelprimepasar.services.plan_inputs import (
    normalize_digits,
    parse_price_toman,
    parse_quota,
    parse_validity_days,
)


def test_normalize_persian_digits() -> None:
    assert normalize_digits("۱۲۳۴۵") == "12345"


def test_parse_gigabyte_input_and_legacy_units() -> None:
    assert parse_quota("500") == 500_000_000_000
    assert parse_quota("۲۵۰") == 250_000_000_000
    assert parse_quota("1TB") == 1_000_000_000_000
    assert parse_quota("500 GB") == 500_000_000_000
    assert parse_quota("1TiB") == 1_099_511_627_776
    assert parse_quota("۲۵۰GiB") == 268_435_456_000


def test_zero_quota_means_unlimited() -> None:
    assert parse_quota("0") == 0
    assert parse_quota("۰GB") == 0


def test_parse_toman_price_with_separators() -> None:
    assert parse_price_toman("۲۰۰٬۰۰۰") == 200_000
    assert parse_price_toman("200,000") == 200_000


def test_parse_validity() -> None:
    assert parse_validity_days("30") == 30
    assert parse_validity_days("۳۰") == 30
    assert parse_validity_days("0") is None


def test_invalid_quota_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_quota("1T")
