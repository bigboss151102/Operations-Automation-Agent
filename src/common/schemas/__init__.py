"""Pydantic schemas and enums shared across layers. Shapes only: no logic, no I/O."""

from src.common.schemas.actions import ApprovalRequest, CustomerDraft, OperationsNotification, RefundRecord
from src.common.schemas.domain import Customer, Order, Subscription, SupportTicket
from src.common.schemas.enums import (
    ACTIVE_TICKET_STATUSES,
    ApprovalStatus,
    IssueType,
    OrderStatus,
    Severity,
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
    "ApprovalRequest",
    "ApprovalStatus",
    "Customer",
    "CustomerDraft",
    "CustomerId",
    "IssueType",
    "OperationsNotification",
    "Order",
    "OrderId",
    "OrderStatus",
    "RefundRecord",
    "Severity",
    "Subscription",
    "SubscriptionId",
    "SubscriptionPlan",
    "SubscriptionStatus",
    "SupportTicket",
    "TicketId",
    "TicketPriority",
    "TicketStatus",
]
