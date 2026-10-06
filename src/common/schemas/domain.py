"""Operational records loaded from ``data/*.json``. Shapes only: no logic, no I/O."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.common.schemas.enums import (
    IssueType,
    OrderStatus,
    SubscriptionPlan,
    SubscriptionStatus,
    TicketPriority,
    TicketStatus,
)
from src.common.schemas.ids import CustomerId, OrderId, SubscriptionId, TicketId


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Order(_Record):
    order_id: OrderId
    customer_id: CustomerId
    status: OrderStatus
    order_date: date
    expected_delivery_date: date | None = None  # None for cancelled orders
    actual_delivery_date: date | None = None
    total_amount: float = Field(ge=0)
    currency: Literal["USD"] = "USD"


class Customer(_Record):
    customer_id: CustomerId
    name: str = Field(min_length=1)
    email: str = Field(pattern=r"^[^@\s]+@example\.com$")  # fictional addresses only
    subscription_status: SubscriptionStatus | None = None  # None: no subscription


class SupportTicket(_Record):
    ticket_id: TicketId
    customer_id: CustomerId
    order_id: OrderId | None = None  # e.g. subscription tickets have no order
    status: TicketStatus
    priority: TicketPriority
    issue_type: IssueType
    created_at: date
    summary: str | None = None


class Subscription(_Record):
    subscription_id: SubscriptionId
    customer_id: CustomerId
    status: SubscriptionStatus
    plan: SubscriptionPlan
    next_billing_date: date | None = None  # None when cancelled
