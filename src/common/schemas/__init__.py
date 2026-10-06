"""Pydantic schemas and enums shared across layers. Shapes only: no logic, no I/O."""

from src.common.schemas.domain import Customer, Order, Subscription, SupportTicket
from src.common.schemas.enums import (
    ACTIVE_TICKET_STATUSES,
    IssueType,
    OrderStatus,
    SubscriptionPlan,
    SubscriptionStatus,
    TicketPriority,
    TicketStatus,
)
from src.common.schemas.ids import (
    CUSTOMER_ID_PATTERN,
    ORDER_ID_PATTERN,
    SUBSCRIPTION_ID_PATTERN,
    TICKET_ID_PATTERN,
    CustomerId,
    OrderId,
    SubscriptionId,
    TicketId,
)

__all__ = [
    "ACTIVE_TICKET_STATUSES",
    "CUSTOMER_ID_PATTERN",
    "ORDER_ID_PATTERN",
    "SUBSCRIPTION_ID_PATTERN",
    "TICKET_ID_PATTERN",
    "Customer",
    "CustomerId",
    "IssueType",
    "Order",
    "OrderId",
    "OrderStatus",
    "Subscription",
    "SubscriptionId",
    "SubscriptionPlan",
    "SubscriptionStatus",
    "SupportTicket",
    "TicketId",
    "TicketPriority",
    "TicketStatus",
]
