from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import (
    SupportMessage,
    SupportTicket,
    TicketStatus,
)


class SupportStateError(RuntimeError):
    """Raised when a support ticket transition is invalid."""


async def create_ticket(
    session: AsyncSession,
    *,
    customer_id: UUID,
    subject: str,
    body: str,
) -> SupportTicket:
    clean_subject = subject.strip()
    clean_body = body.strip()
    if not clean_subject or len(clean_subject) > 160:
        raise SupportStateError("موضوع تیکت باید بین 1 تا 160 کاراکتر باشد.")
    if not clean_body or len(clean_body) > 4000:
        raise SupportStateError("متن پیام باید بین 1 تا 4000 کاراکتر باشد.")

    ticket = SupportTicket(
        customer_id=customer_id,
        subject=clean_subject,
        status=TicketStatus.OPEN.value,
    )
    session.add(ticket)
    await session.flush()
    session.add(
        SupportMessage(
            ticket_id=ticket.id,
            sender_type="customer",
            sender_id=str(customer_id),
            body=clean_body,
        )
    )
    await session.flush()
    return ticket


async def list_customer_tickets(
    session: AsyncSession,
    *,
    customer_id: UUID,
    limit: int = 10,
) -> list[SupportTicket]:
    rows = await session.scalars(
        select(SupportTicket)
        .where(SupportTicket.customer_id == customer_id)
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
    )
    return list(rows.all())


async def add_customer_message(
    session: AsyncSession,
    *,
    customer_id: UUID,
    ticket_id: UUID,
    body: str,
) -> SupportMessage:
    ticket = await session.scalar(
        select(SupportTicket)
        .where(
            SupportTicket.id == ticket_id,
            SupportTicket.customer_id == customer_id,
        )
        .with_for_update()
    )
    if ticket is None:
        raise SupportStateError("تیکت پیدا نشد.")
    if ticket.status == TicketStatus.CLOSED.value:
        raise SupportStateError("این تیکت بسته شده است.")

    clean_body = body.strip()
    if not clean_body or len(clean_body) > 4000:
        raise SupportStateError("متن پیام باید بین 1 تا 4000 کاراکتر باشد.")

    message = SupportMessage(
        ticket_id=ticket.id,
        sender_type="customer",
        sender_id=str(customer_id),
        body=clean_body,
    )
    session.add(message)
    ticket.status = TicketStatus.OPEN.value
    await session.flush()
    return message


async def close_ticket(
    session: AsyncSession,
    *,
    customer_id: UUID,
    ticket_id: UUID,
) -> SupportTicket:
    ticket = await session.scalar(
        select(SupportTicket)
        .where(
            SupportTicket.id == ticket_id,
            SupportTicket.customer_id == customer_id,
        )
        .with_for_update()
    )
    if ticket is None:
        raise SupportStateError("تیکت پیدا نشد.")

    ticket.status = TicketStatus.CLOSED.value
    ticket.closed_at = datetime.now(UTC)
    await session.flush()
    return ticket
