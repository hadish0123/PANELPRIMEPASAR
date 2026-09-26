from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import (
    DiscountCode,
    DiscountKind,
    DiscountRedemption,
    DiscountRedemptionStatus,
    Order,
    OrderStatus,
)


class DiscountStateError(RuntimeError):
    """Raised when a discount cannot be reserved, redeemed, or released."""


def normalize_discount_code(code: str) -> str:
    normalized = code.strip().upper()
    if len(normalized) < 2 or len(normalized) > 64:
        raise DiscountStateError("Discount code must be between 2 and 64 characters")
    if not all(ch.isalnum() or ch in {"_", "-"} for ch in normalized):
        raise DiscountStateError("Discount code contains unsupported characters")
    return normalized


def calculate_discount_amount(code: DiscountCode, price_amount: int) -> int:
    if price_amount < 0:
        raise DiscountStateError("Order price cannot be negative")

    if code.kind == DiscountKind.FIXED.value:
        value = code.value_amount
        if value is None or value <= 0:
            raise DiscountStateError("Fixed discount value is invalid")
        return min(value, price_amount)

    if code.kind == DiscountKind.PERCENT.value:
        percent = code.value_percent
        if percent is None or percent <= 0 or percent > 100:
            raise DiscountStateError("Percent discount value is invalid")
        return min(price_amount, (price_amount * percent) // 100)

    raise DiscountStateError("Discount type is invalid")


async def reserve_discount_for_order(
    session: AsyncSession,
    *,
    customer_id: UUID,
    order_id: UUID,
    raw_code: str,
    now: datetime | None = None,
) -> DiscountRedemption:
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    if order is None or order.customer_id != customer_id:
        raise DiscountStateError("Order not found")
    if order.status not in {
        OrderStatus.PENDING,
        OrderStatus.AWAITING_PAYMENT,
    }:
        raise DiscountStateError("Discount can only be applied before payment")

    existing = await session.scalar(
        select(DiscountRedemption)
        .where(DiscountRedemption.order_id == order.id)
        .with_for_update()
    )
    if existing is not None:
        if existing.status in {
            DiscountRedemptionStatus.RESERVED.value,
            DiscountRedemptionStatus.REDEEMED.value,
        }:
            return existing
        raise DiscountStateError("This order already used a released discount")

    code_value = normalize_discount_code(raw_code)
    discount = await session.scalar(
        select(DiscountCode)
        .where(DiscountCode.code == code_value)
        .with_for_update()
    )
    if discount is None or not discount.is_active:
        raise DiscountStateError("Discount code is invalid or inactive")

    current = now or datetime.now(UTC)
    if discount.expires_at is not None and discount.expires_at <= current:
        raise DiscountStateError("Discount code has expired")
    if discount.max_uses is not None and discount.used_count >= discount.max_uses:
        raise DiscountStateError("Discount code usage limit has been reached")

    amount = calculate_discount_amount(discount, order.price_amount)
    if amount <= 0:
        raise DiscountStateError("Discount does not reduce this order price")

    redemption = DiscountRedemption(
        discount_code_id=discount.id,
        order_id=order.id,
        customer_id=customer_id,
        amount=amount,
        status=DiscountRedemptionStatus.RESERVED.value,
    )
    discount.used_count += 1
    order.discount_code_id = discount.id
    order.discount_amount = amount
    order.price_amount -= amount
    session.add(redemption)
    await session.flush()
    return redemption


async def redeem_discount_for_order(
    session: AsyncSession,
    *,
    order_id: UUID,
) -> DiscountRedemption | None:
    redemption = await session.scalar(
        select(DiscountRedemption)
        .where(DiscountRedemption.order_id == order_id)
        .with_for_update()
    )
    if redemption is None:
        return None
    if redemption.status == DiscountRedemptionStatus.REDEEMED.value:
        return redemption
    if redemption.status != DiscountRedemptionStatus.RESERVED.value:
        raise DiscountStateError("Released discount cannot be redeemed")

    redemption.status = DiscountRedemptionStatus.REDEEMED.value
    await session.flush()
    return redemption


async def release_discount_for_order(
    session: AsyncSession,
    *,
    order_id: UUID,
) -> DiscountRedemption | None:
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    if order is None:
        raise DiscountStateError("Order not found")

    redemption = await session.scalar(
        select(DiscountRedemption)
        .where(DiscountRedemption.order_id == order.id)
        .with_for_update()
    )
    if redemption is None:
        return None
    if redemption.status == DiscountRedemptionStatus.RELEASED.value:
        return redemption
    if redemption.status == DiscountRedemptionStatus.REDEEMED.value:
        raise DiscountStateError("Redeemed discount cannot be released")

    discount = await session.scalar(
        select(DiscountCode)
        .where(DiscountCode.id == redemption.discount_code_id)
        .with_for_update()
    )
    if discount is not None and discount.used_count > 0:
        discount.used_count -= 1

    order.price_amount += redemption.amount
    order.discount_amount = 0
    order.discount_code_id = None
    redemption.status = DiscountRedemptionStatus.RELEASED.value
    await session.flush()
    return redemption


async def release_stale_discount_reservations(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    max_age_hours: int = 24,
    limit: int = 100,
) -> int:
    current = now or datetime.now(UTC)
    threshold = current - timedelta(hours=max_age_hours)

    rows = await session.scalars(
        select(DiscountRedemption)
        .join(Order, Order.id == DiscountRedemption.order_id)
        .where(
            DiscountRedemption.status == DiscountRedemptionStatus.RESERVED.value,
            Order.status.in_(
                {
                    OrderStatus.PENDING,
                    OrderStatus.AWAITING_PAYMENT,
                    OrderStatus.CANCELED,
                }
            ),
            Order.created_at <= threshold,
        )
        .order_by(DiscountRedemption.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )

    released = 0
    for redemption in rows.all():
        await release_discount_for_order(
            session,
            order_id=redemption.order_id,
        )
        released += 1
    return released
