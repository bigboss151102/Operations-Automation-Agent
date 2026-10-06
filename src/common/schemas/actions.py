"""Records produced by (simulated) actions. Shapes only: no logic, no I/O."""

from datetime import date
from typing import Any

from pydantic import Field

from src.common.schemas._base import Record
from src.common.schemas.delivery import NotificationResult
from src.common.schemas.enums import ApprovalStatus, Severity
from src.common.schemas.ids import OrderId


class OperationsNotification(Record):
    """An alert to the operations team (spec Tool 6): posted to Slack, or simulated when Slack is not configured."""

    notification_id: str
    channel: str
    severity: Severity
    summary: str
    order_id: OrderId | None = None
    recommended_action: str
    created_at: date
    delivery: NotificationResult | None = None


class CustomerDraft(Record):
    """A customer reply draft, R8-checked. The chatbot shows it to the customer (decision D6)."""

    draft_id: str
    customer_name: str
    issue_summary: str
    recommended_action: str
    draft: str
    created_at: date


class ApprovalRequest(Record):
    """A pending/decided human approval (spec Tool 8). Only refunds need approval (decision D2)."""

    approval_id: str
    request_id: str
    action: str
    reason: str
    context: dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: date


class RefundRecord(Record):
    """A simulated refund, only ever created from an approved ``ApprovalRequest``."""

    refund_id: str
    order_id: OrderId
    amount: float = Field(gt=0)
    approval_id: str
    created_at: date
