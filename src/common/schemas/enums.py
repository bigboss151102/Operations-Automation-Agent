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


class Severity(StrEnum):
    """Issue severity (spec §13); computed only by deterministic guardrails."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Intent(StrEnum):
    """What the customer wants, as classified by the LLM."""

    ORDER_STATUS = "order_status"
    DELIVERY_ISSUE = "delivery_issue"
    REFUND_REQUEST = "refund_request"
    SUBSCRIPTION_ISSUE = "subscription_issue"
    ADDRESS_ISSUE = "address_issue"
    OTHER = "other"


#: Intents that cannot be investigated without an order ID (Rule 5).
ORDER_INTENTS = frozenset({Intent.ORDER_STATUS, Intent.DELIVERY_ISSUE, Intent.REFUND_REQUEST})


class RequestedAction(StrEnum):
    """What the customer explicitly asked for."""

    REFUND = "refund"
    CANCEL = "cancel"
    UPDATE_ADDRESS = "update_address"
    INFORMATION = "information"
    NONE = "none"


class ActionName(StrEnum):
    """The action catalogue: everything the system can do (decision D2). There is no way to message customers."""

    PREPARE_CUSTOMER_RESPONSE = "prepare_customer_response"
    SEND_OPERATIONS_NOTIFICATION = "send_operations_notification"
    CREATE_SUPPORT_TICKET = "create_support_ticket"
    ISSUE_REFUND = "issue_refund"


class Risk(StrEnum):
    NONE = "none"
    LOW = "low"
    HIGH = "high"


class Execution(StrEnum):
    """How a recommended action is handled (spec §14)."""

    AUTOMATIC = "automatic"
    HUMAN_APPROVAL = "human_approval"
    BLOCKED = "blocked"


class RuleId(StrEnum):
    """Guardrail rules (spec §12). The IDs appear in logs and responses, so decisions are traceable."""

    REFUND_REQUIRES_APPROVAL = "refund_requires_approval"  # R1
    HIGH_VALUE_ORDER = "high_value_order"  # R2
    EXTERNAL_COMMUNICATION_BLOCKED = "external_communication_blocked"  # R3
    DUPLICATE_TICKET = "duplicate_ticket"  # R4
    MISSING_INFORMATION = "missing_information"  # R5
    ORDER_NOT_FOUND = "order_not_found"  # R6
    UNVERIFIED_ID = "unverified_id"  # R7
    CUSTOMER_DRAFT_POLICY = "customer_draft_policy"  # R8
    UNKNOWN_ACTION = "unknown_action"


class GuardrailOutcome(StrEnum):
    """Whether the case may proceed to action execution at all."""

    PROCEED = "proceed"
    NEEDS_MORE_INFO = "needs_more_info"  # R5
    NOT_FOUND = "not_found"  # R6
    REJECTED = "rejected"  # R7: the proposal referenced an unverified ID
