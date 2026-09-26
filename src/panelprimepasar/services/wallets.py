from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Wallet,
    WalletTransaction,
    WalletTransactionKind,
)
from panelprimepasar.services.discounts import (
    DiscountStateError,
    redeem_discount_for_order,
)


class WalletStateError(RuntimeError):
    """Raised when a wallet operation would violate accounting invariants."""


async def get_or_create_wallet(
    session: AsyncSession,
    *,
    customer_id: UUID,
    currency: str = "IRT",
) -> Wallet:
    normalized_currency = currency.upper()
    wallet = await session.scalar(
        select(Wallet).where(Wallet.customer_id == customer_id)
    )
    if wallet is not None:
        if wallet.currency.upper() != normalized_currency:
            raise WalletStateError(
                "Wallet currency does not match requested currency"
            ) from None
        return wallet

    wallet = Wallet(
        customer_id=customer_id,
        balance=0,
        currency=normalized_currency,
    )
    try:
        async with session.begin_nested():
            session.add(wallet)
            await session.flush()
    except IntegrityError:
        wallet = await session.scalar(
            select(Wallet).where(Wallet.customer_id == customer_id)
        )
        if wallet is None:
            raise
        if wallet.currency.upper() != normalized_currency:
            raise WalletStateError(
                "Wallet currency does not match requested currency"
            ) from None
    return wallet


async def list_wallet_transactions(
    session: AsyncSession,
    *,
    wallet_id: UUID,
    limit: int = 20,
) -> list[WalletTransaction]:
    rows = await session.scalars(
        select(WalletTransaction)
        .where(WalletTransaction.wallet_id == wallet_id)
        .order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc())
        .limit(limit)
    )
    return list(rows.all())


async def credit_wallet(
    session: AsyncSession,
    *,
    customer_id: UUID,
    amount: int,
    currency: str,
    idempotency_key: str,
    reference: str | None = None,
    kind: WalletTransactionKind = WalletTransactionKind.CREDIT,
) -> WalletTransaction:
    if amount <= 0:
        raise WalletStateError("Wallet credit amount must be positive")
    if kind not in {
        WalletTransactionKind.CREDIT,
        WalletTransactionKind.REFUND,
        WalletTransactionKind.COMMISSION,
        WalletTransactionKind.ADJUSTMENT,
    }:
        raise WalletStateError("Invalid wallet credit transaction kind")

    existing = await session.scalar(
        select(WalletTransaction).where(
            WalletTransaction.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return existing

    wallet = await get_or_create_wallet(
        session,
        customer_id=customer_id,
        currency=currency,
    )
    locked_wallet = await session.scalar(
        select(Wallet).where(Wallet.id == wallet.id).with_for_update()
    )
    if locked_wallet is None:
        raise WalletStateError("Wallet not found")

    transaction = WalletTransaction(
        wallet_id=locked_wallet.id,
        kind=kind.value,
        amount=amount,
        currency=locked_wallet.currency,
        reference=reference,
        idempotency_key=idempotency_key,
    )
    locked_wallet.balance += amount
    session.add(transaction)
    await session.flush()
    return transaction


async def debit_wallet(
    session: AsyncSession,
    *,
    customer_id: UUID,
    amount: int,
    currency: str,
    idempotency_key: str,
    reference: str | None = None,
) -> WalletTransaction:
    if amount <= 0:
        raise WalletStateError("Wallet debit amount must be positive")

    existing = await session.scalar(
        select(WalletTransaction).where(
            WalletTransaction.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        if existing.kind != WalletTransactionKind.DEBIT.value:
            raise WalletStateError("Wallet idempotency key belongs to another operation")
        return existing

    wallet = await get_or_create_wallet(
        session,
        customer_id=customer_id,
        currency=currency,
    )
    locked_wallet = await session.scalar(
        select(Wallet).where(Wallet.id == wallet.id).with_for_update()
    )
    if locked_wallet is None:
        raise WalletStateError("Wallet not found")
    if locked_wallet.balance < amount:
        raise WalletStateError("Insufficient wallet balance")

    transaction = WalletTransaction(
        wallet_id=locked_wallet.id,
        kind=WalletTransactionKind.DEBIT.value,
        amount=amount,
        currency=locked_wallet.currency,
        reference=reference,
        idempotency_key=idempotency_key,
    )
    locked_wallet.balance -= amount
    session.add(transaction)
    await session.flush()
    return transaction


async def pay_order_with_wallet(
    session: AsyncSession,
    *,
    customer_id: UUID,
    order_id: UUID,
) -> Payment:
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    if order is None or order.customer_id != customer_id:
        raise WalletStateError("Order not found")

    verified = await session.scalar(
        select(Payment)
        .where(
            Payment.order_id == order.id,
            Payment.status == PaymentStatus.VERIFIED,
        )
        .order_by(Payment.verified_at.desc())
    )
    if verified is not None:
        if verified.provider == "wallet":
            return verified
        raise WalletStateError("Order is already paid using another provider")

    if order.status not in {
        OrderStatus.PENDING,
        OrderStatus.AWAITING_PAYMENT,
    }:
        raise WalletStateError(
            f"Order status {order.status.value!r} cannot be paid from wallet"
        )
    if order.price_amount <= 0:
        raise WalletStateError("Zero-price orders do not require wallet payment")

    transaction = await debit_wallet(
        session,
        customer_id=customer_id,
        amount=order.price_amount,
        currency=order.currency,
        idempotency_key=f"wallet:order:{order.id}",
        reference=str(order.id),
    )

    try:
        await redeem_discount_for_order(
            session,
            order_id=order.id,
        )
    except DiscountStateError as exc:
        raise WalletStateError(str(exc)) from exc

    pending_payments = list(
        (
            await session.scalars(
                select(Payment)
                .where(
                    Payment.order_id == order.id,
                    Payment.status == PaymentStatus.PENDING,
                )
                .with_for_update()
            )
        ).all()
    )
    for pending in pending_payments:
        pending.status = PaymentStatus.FAILED

    payment = Payment(
        order_id=order.id,
        provider="wallet",
        provider_transaction_id=f"wallet:{transaction.id}",
        amount=order.price_amount,
        currency=order.currency,
        status=PaymentStatus.VERIFIED,
        verified_at=datetime.now(UTC),
        raw_reference=str(transaction.id),
    )
    session.add(payment)
    order.status = OrderStatus.PAID
    await session.flush()
    return payment
