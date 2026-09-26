import re
from decimal import Decimal, InvalidOperation

_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

_QUOTA_RE = re.compile(
    r"^([0-9]+(?:\.[0-9]+)?)(GB|TB|GIB|TIB)?$",
    re.IGNORECASE,
)

_QUOTA_MULTIPLIERS = {
    "GB": 1_000_000_000,
    "TB": 1_000_000_000_000,
    "GIB": 1_073_741_824,
    "TIB": 1_099_511_627_776,
}


def normalize_digits(value: str) -> str:
    return (
        value.translate(_DIGIT_TRANSLATION)
        .replace("٫", ".")
        .replace("٬", ",")
        .strip()
    )


def parse_quota(value: str) -> int:
    normalized = normalize_digits(value).replace(" ", "")
    match = _QUOTA_RE.fullmatch(normalized)
    if match is None:
        raise ValueError(
            "حجم را به گیگابایت وارد کنید؛ مثل 500 یا عدد 0 برای نامحدود."
        )

    try:
        amount = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise ValueError("مقدار حجم معتبر نیست.") from exc

    if amount < 0:
        raise ValueError("حجم نمی‌تواند منفی باشد.")
    if amount == 0:
        return 0

    unit = (match.group(2) or "GB").upper()
    byte_value = amount * _QUOTA_MULTIPLIERS[unit]
    if byte_value != byte_value.to_integral_value():
        raise ValueError("حجم واردشده به تعداد صحیح بایت تبدیل نمی‌شود.")
    return int(byte_value)


def parse_price_toman(value: str) -> int:
    normalized = normalize_digits(value)
    compact = (
        normalized.replace(",", "")
        .replace("،", "")
        .replace("_", "")
        .replace(" ", "")
    )
    if not compact.isdigit():
        raise ValueError("قیمت را فقط به عدد و بر حسب تومان وارد کنید.")

    amount = int(compact)
    if amount <= 0:
        raise ValueError("قیمت باید بزرگ‌تر از صفر باشد.")
    return amount


def parse_validity_days(value: str) -> int | None:
    normalized = normalize_digits(value).casefold().strip()
    if normalized in {"0", "-", "بدون", "نامحدود"}:
        return None

    if not normalized.isdigit():
        raise ValueError("اعتبار را به روز وارد کنید؛ برای بدون محدودیت عدد 0 بفرستید.")

    days = int(normalized)
    if days <= 0:
        raise ValueError("اعتبار باید بزرگ‌تر از صفر باشد یا 0 برای بدون محدودیت.")
    return days
