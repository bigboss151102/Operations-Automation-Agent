"""Closed value sets shared by data, tools, the LLM proposal, and guardrails."""

from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class IssueType(StrEnum):
    """Operational issue categories. The spec §3.1 example's ``delayed_order`` maps to ``DELIVERY_DELAY``."""

    DELIVERY_DELAY = "delivery_delay"
    MISSING_ORDER = "missing_order"
    CANCELLED_ORDER = "cancelled_order"
    REFUND_REQUEST = "refund_request"
    SUBSCRIPTION_ISSUE = "subscription_issue"
    ADDRESS_ISSUE = "address_issue"
    OTHER = "other"


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


#: Ticket statuses that count as "already being handled" for duplicate protection (Rule 4).
ACTIVE_TICKET_STATUSES = frozenset({TicketStatus.OPEN, TicketStatus.IN_PROGRESS})


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    PAYMENT_FAILED = "payment_failed"


class SubscriptionPlan(StrEnum):
    BASIC = "basic"
    PREMIUM = "premium"
