from datetime import date

from src.agents.customer_updates import decision_message
from src.common.schemas import ApprovalRequest, ApprovalStatus, ExecutedAction


def _approval(status: ApprovalStatus) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id="APR-1001",
        request_id="req-1",
        action="issue_refund",
        reason="Refunds always require human approval.",
        context={"order_id": "ORD-1007", "customer_id": "CUS-102", "amount": 249.99, "currency": "USD"},
        status=status,
        created_at=date(2026, 10, 10),
    )


def test_approved_refund_message_has_exact_amount_and_reference():
    refund = ExecutedAction(action="issue_refund", success=True, result_id="RFD-0001")
    text = decision_message(_approval(ApprovalStatus.APPROVED), refund, "Alex Johnson")
    assert text.startswith("Hi Alex, good news")
    assert "249.99 USD" in text
    assert "ORD-1007" in text
    assert "RFD-0001" in text


def test_approved_but_failed_refund_does_not_claim_it_was_processed():
    refund = ExecutedAction(action="issue_refund", success=False, error="INVALID_REFUND_AMOUNT")
    text = decision_message(_approval(ApprovalStatus.APPROVED), refund, "Alex Johnson")
    assert "processed (reference" not in text
    assert "follow up" in text


def test_rejected_refund_message():
    text = decision_message(_approval(ApprovalStatus.REJECTED), None, None)
    assert text.startswith("Hi there,")
    assert "not able to approve" in text
