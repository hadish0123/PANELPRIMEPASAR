from panelprimepasar.services.quota import quota_bytes_to_pasarguard_data_limit


def test_pasarguard_receives_exact_binary_gigabyte_scale() -> None:
    assert quota_bytes_to_pasarguard_data_limit(1_000_000_000_000) == 1_073_741_824_000
    assert quota_bytes_to_pasarguard_data_limit(500_000_000_000) == 536_870_912_000


def test_unlimited_quota_stays_zero_for_pasarguard() -> None:
    assert quota_bytes_to_pasarguard_data_limit(0) == 0
