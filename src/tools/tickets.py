from typing import Any

from langchain_core.tools import tool

from src.common.schemas import IssueType, SupportTicket, TicketPriority, TicketStatus
from src.config.settings import today
from src.repositories.action_store import get_action_store
from src.repositories.data_store import get_data_store
from src.repositories.tickets import find_tickets
from src.tools._results import dump, fail, ok
from src.utils.ids import is_customer_id, is_order_id


@tool
def get_support_tickets(customer_id: str, order_id: str | None = None) -> dict[str, Any]:
    """List existing support tickets for a customer, optionally narrowed to one order.

    Call this before recommending a new ticket, to detect open tickets for the same issue.
    Returns every matching ticket with its status (open, in_progress, resolved, closed),
    priority, issue type, and creation date. An empty list means no tickets exist.
    """
    if not is_customer_id(customer_id) or (order_id is not None and not is_order_id(order_id)):
        return fail(
            "get_support_tickets", "INVALID_ID_FORMAT", "Expected customer_id CUS-<digits> and order_id ORD-<digits>."
        )
    if get_data_store().customer(customer_id) is None:
        return fail(
            "get_support_tickets",
            "CUSTOMER_NOT_FOUND",
            f"Customer {customer_id} was not found.",
            customer_id=customer_id,
        )
    tickets = find_tickets(customer_id=customer_id, order_id=order_id)
    return ok(
        "get_support_tickets",
        {"tickets": [dump(t) for t in tickets], "count": len(tickets)},
        customer_id=customer_id,
        order_id=order_id,
        count=len(tickets),
    )


@tool
def create_support_ticket(
    customer_id: str,
    order_id: str | None,
    issue_type: IssueType,
    priority: TicketPriority,
    summary: str,
) -> dict[str, Any]:
    """Create a support ticket (simulated, in-memory). Called by the workflow, never by the LLM.

    Duplicate protection is a guardrail decision made before this runs (spec Rule 4); this tool
    only validates that the customer and order exist and belong together.
    """
    store = get_data_store()
    if store.customer(customer_id) is None:
        return fail("create_support_ticket", "CUSTOMER_NOT_FOUND", f"Customer {customer_id} was not found.")
    if order_id is not None:
        order = store.order(order_id)
        if order is None:
            return fail("create_support_ticket", "ORDER_NOT_FOUND", f"Order {order_id} was not found.")
        if order.customer_id != customer_id:
            return fail("create_support_ticket", "ORDER_CUSTOMER_MISMATCH", f"Order {order_id} is not {customer_id}'s.")

    actions = get_action_store()
    ticket = SupportTicket(
        ticket_id=actions.next_id("TCK"),
        customer_id=customer_id,
        order_id=order_id,
        status=TicketStatus.OPEN,
        priority=priority,
        issue_type=issue_type,
        created_at=today(),
        summary=summary,
    )
    actions.add_ticket(ticket)
    return ok(
        "create_support_ticket",
        {"ticket_id": ticket.ticket_id, "ticket": dump(ticket)},
        ticket_id=ticket.ticket_id,
        order_id=order_id,
        priority=priority,
    )
