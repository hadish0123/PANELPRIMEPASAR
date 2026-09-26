from uuid import uuid4

import pytest

from panelprimepasar.db import SessionFactory
from panelprimepasar.models import Customer, TicketStatus
from panelprimepasar.services.support import (
    add_customer_message,
    add_staff_message,
    close_ticket_by_staff,
    create_ticket,
    get_ticket_messages,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_support_conversation_lifecycle() -> None:
    marker = uuid4().hex

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:14], 16),
            telegram_username=f"support_{marker[:8]}",
            first_name="Support",
            last_name=None,
        )
        session.add(customer)
        await session.flush()

        ticket = await create_ticket(
            session,
            customer_id=customer.id,
            subject="Need help",
            body="Initial request",
        )
        assert ticket.status == TicketStatus.OPEN.value

        ticket, staff_message = await add_staff_message(
            session,
            ticket_id=ticket.id,
            staff_telegram_id=12345,
            body="Staff reply",
        )
        assert ticket.status == TicketStatus.ANSWERED.value
        assert staff_message.sender_type == "staff"

        customer_message = await add_customer_message(
            session,
            customer_id=customer.id,
            ticket_id=ticket.id,
            body="Customer follow-up",
        )
        assert ticket.status == TicketStatus.OPEN.value
        assert customer_message.sender_type == "customer"

        messages = await get_ticket_messages(session, ticket_id=ticket.id)
        assert [message.body for message in messages] == [
            "Initial request",
            "Staff reply",
            "Customer follow-up",
        ]

        ticket = await close_ticket_by_staff(session, ticket_id=ticket.id)
        assert ticket.status == TicketStatus.CLOSED.value
        assert ticket.closed_at is not None
        await session.rollback()
