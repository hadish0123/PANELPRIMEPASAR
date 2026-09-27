DISPLAY_GIGABYTE_BYTES = 1_000_000_000
PASARGUARD_GIGABYTE_BYTES = 1_073_741_824


def quota_bytes_to_pasarguard_data_limit(quota_bytes: int) -> int:
    """Convert stored decimal-GB bytes to PasarGuard's binary-GB byte scale."""
    if quota_bytes <= 0:
        return 0
    numerator = quota_bytes * PASARGUARD_GIGABYTE_BYTES
    return (numerator + DISPLAY_GIGABYTE_BYTES // 2) // DISPLAY_GIGABYTE_BYTES
