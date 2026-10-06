"""Simulated operational actions. Called only by workflow nodes after guardrails, never by the LLM."""

from typing import Any

from langchain_core.tools import tool

from src.common.schemas import (
    ApprovalRequest,
    ApprovalStatus,
    CustomerDraft,
    OperationsNotification,
    RefundRecord,
    Severity,
)
from src.config.settings import today
from src.repositories.action_store import get_action_store
from src.repositories.data_store import get_data_store
from src.tools._results import dump, fail, ok
from src.utils.logging import get_logger

OPERATIONS_CHANNEL = "#operations-alerts"
REFUND_ACTION = "issue_refund"

_log = get_logger("tools.actions")


@tool
def send_operations_notification(
    severity: Severity,
    summary: str,
    order_id: str | None,
    recommended_action: str,
) -> dict[str, Any]:
    """Alert the operations team (simulated Slack message; nothing is sent externally)."""
    actions = get_action_store()
    notification = OperationsNotification(
        notification_id=actions.next_id("NTF"),
        channel=OPERATIONS_CHANNEL,
        severity=severity,
        summary=summary,
        order_id=order_id,
        recommended_action=recommended_action,
        created_at=today(),
    )
    actions.add_notification(notification)
    _log.info(
        "[SIMULATED SLACK]\nChannel: %s\n\n%s PRIORITY\n%s\nRecommended action: %s",
        OPERATIONS_CHANNEL,
        severity,
        summary,
        recommended_action,
    )
    return ok(
        "send_operations_notification",
        {"notification_id": notification.notification_id, "channel": OPERATIONS_CHANNEL},
        notification_id=notification.notification_id,
        severity=severity,
        order_id=order_id,
    )


@tool
def prepare_customer_response(
    customer_name: str,
    issue_summary: str,
    recommended_action: str,
    draft: str,
) -> dict[str, Any]:
    """Store a customer reply draft. It is never sent (spec Rule 3).

    The text was written by the LLM and has already been checked by the draft policy guardrail;
    this tool neither writes nor modifies it.
    """
    actions = get_action_store()
    record = CustomerDraft(
        draft_id=actions.next_id("DRF"),
        customer_name=customer_name,
        issue_summary=issue_summary,
        recommended_action=recommended_action,
        draft=draft,
        created_at=today(),
    )
    actions.add_draft(record)
    return ok(
        "prepare_customer_response",
        {"draft_id": record.draft_id, "draft": record.draft},
        draft_id=record.draft_id,
    )


def fallback_customer_draft(customer_name: str, order_id: str | None = None) -> str:
    """Safe deterministic reply, used when the LLM draft is missing or violates the draft policy.

    It deliberately uses no LLM-written text, so it can never promise a refund.
    """
    first_name = customer_name.split(maxsplit=1)[0] if customer_name.strip() else "there"
    about = f"your order {order_id}" if order_id else "your request"
    return (
        f"Hi {first_name},\n\n"
        f"Thank you for contacting us about {about}. Our team is reviewing it and will get back to you shortly.\n\n"
        "Best regards,\nThe OpsPilot Support Team"
    )


@tool
def request_human_approval(action: str, reason: str, context: dict[str, Any], request_id: str) -> dict[str, Any]:
    """Create a pending approval request (spec Tool 8).

    Idempotent per (request_id, action): the human-approval node re-runs when a paused graph resumes,
    and must not create a second approval.
    """
    actions = get_action_store()
    approval = actions.find_approval(request_id, action)
    if approval is None:
        approval = ApprovalRequest(
            approval_id=actions.next_id("APR"),
            request_id=request_id,
            action=action,
            reason=reason,
            context=context,
            created_at=today(),
        )
        actions.save_approval(approval)
    return ok(
        "request_human_approval",
        dump(approval),
        approval_id=approval.approval_id,
        action=action,
        status=approval.status,
    )


@tool
def issue_refund(order_id: str, amount: float, approval_id: str) -> dict[str, Any]:
    """Issue a refund (simulated). Refuses unless a human approved this exact refund."""
    approval = get_action_store().approval(approval_id)
    if (
        approval is None
        or approval.action != REFUND_ACTION
        or approval.status is not ApprovalStatus.APPROVED
        or approval.context.get("order_id") != order_id
    ):
        return fail(
            "issue_refund",
            "REFUND_NOT_APPROVED",
            f"No approved refund request {approval_id} for order {order_id}.",
            order_id=order_id,
            approval_id=approval_id,
        )
    order = get_data_store().order(order_id)
    if order is None:
        return fail("issue_refund", "ORDER_NOT_FOUND", f"Order {order_id} was not found.", order_id=order_id)
    if not 0 < amount <= order.total_amount:
        return fail(
            "issue_refund",
            "INVALID_REFUND_AMOUNT",
            f"Refund amount {amount} must be positive and at most the order total {order.total_amount}.",
            order_id=order_id,
        )

    actions = get_action_store()
    refund = RefundRecord(
        refund_id=actions.next_id("RFD"),
        order_id=order_id,
        amount=amount,
        approval_id=approval_id,
        created_at=today(),
    )
    actions.add_refund(refund)
    _log.info(
        "[SIMULATED REFUND] %s %.2f %s for %s (approval %s)",
        refund.refund_id,
        amount,
        order.currency,
        order_id,
        approval_id,
    )
    return ok(
        "issue_refund",
        {"refund_id": refund.refund_id, "refund": dump(refund)},
        refund_id=refund.refund_id,
        order_id=order_id,
        approval_id=approval_id,
    )
