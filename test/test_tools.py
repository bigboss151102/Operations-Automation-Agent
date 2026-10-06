"""Tools and stores (plan Phase 3). Spec Tests 1 and 2 live here."""

import json
from pathlib import Path

import pytest

from src.common.schemas import ApprovalStatus, IssueType, Severity, TicketPriority, TicketStatus
from src.repositories.action_store import get_action_store
from src.tools.actions import (
    fallback_customer_draft,
    issue_refund,
    prepare_customer_response,
    request_human_approval,
    send_operations_notification,
)
from src.tools.customers import get_customer
from src.tools.orders import get_order
from src.tools.registry import ACTION_TOOLS, APPROVAL_ONLY_ACTIONS, READ_TOOLS
from src.tools.subscriptions import get_subscription
from src.tools.tickets import create_support_ticket, get_support_tickets

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _new_ticket(**overrides):
    args = {
        "customer_id": "CUS-102",
        "order_id": "ORD-1007",
        "issue_type": IssueType.DELIVERY_DELAY,
        "priority": TicketPriority.HIGH,
        "summary": "Order delayed 15 days; refund requested.",
    }
    return create_support_ticket.invoke(args | overrides)


# --- read tools -------------------------------------------------------------------------


def test_get_order_returns_existing_order():  # spec Test 1
    raw = next(o for o in json.loads((DATA_DIR / "orders.json").read_text()) if o["order_id"] == "ORD-1007")
    result = get_order.invoke({"order_id": "ORD-1007"})
    assert result["success"] is True
    assert result["order"] == raw
    assert result["days_late"] == 15


def test_get_order_returns_not_found_for_unknown_id():  # spec Test 2
    result = get_order.invoke({"order_id": "ORD-9999"})
    assert result == {"success": False, "error": "ORDER_NOT_FOUND", "message": "Order ORD-9999 was not found."}


def test_get_order_reports_long_unknown_id_as_not_found():  # spec Rule 6 example
    assert get_order.invoke({"order_id": "ORD-999999"})["error"] == "ORDER_NOT_FOUND"


@pytest.mark.parametrize("bad_id", ["ORD-99x", "1007", "CUS-102", ""])
def test_get_order_rejects_malformed_id(bad_id):
    assert get_order.invoke({"order_id": bad_id})["error"] == "INVALID_ID_FORMAT"


def test_get_customer():
    assert get_customer.invoke({"customer_id": "CUS-102"})["customer"]["name"] == "Alex Johnson"
    assert get_customer.invoke({"customer_id": "CUS-999"})["error"] == "CUSTOMER_NOT_FOUND"


def test_get_subscription():
    assert get_subscription.invoke({"customer_id": "CUS-102"})["subscription"]["plan"] == "premium"
    assert get_subscription.invoke({"customer_id": "CUS-104"})["error"] == "SUBSCRIPTION_NOT_FOUND"
    assert get_subscription.invoke({"customer_id": "CUS-999"})["error"] == "CUSTOMER_NOT_FOUND"


def test_get_support_tickets_for_order():
    result = get_support_tickets.invoke({"customer_id": "CUS-107", "order_id": "ORD-1008"})
    assert [(t["ticket_id"], t["status"]) for t in result["tickets"]] == [("TCK-2001", "open")]


def test_get_support_tickets_includes_created_tickets():
    assert get_support_tickets.invoke({"customer_id": "CUS-102", "order_id": "ORD-1007"})["count"] == 0
    created = _new_ticket()
    tickets = get_support_tickets.invoke({"customer_id": "CUS-102", "order_id": "ORD-1007"})["tickets"]
    assert [t["ticket_id"] for t in tickets] == [created["ticket_id"]]


# --- action tools -----------------------------------------------------------------------


def test_create_support_ticket_generates_non_colliding_id():
    first, second = _new_ticket(), _new_ticket()
    assert first["ticket_id"] == "TCK-2009"  # sample tickets go up to TCK-2008
    assert second["ticket_id"] == "TCK-2010"
    assert first["ticket"]["status"] == TicketStatus.OPEN
    assert first["ticket"]["created_at"] == "2026-10-10"  # business "today"


def test_create_support_ticket_validates_ownership():
    assert _new_ticket(order_id="ORD-1008")["error"] == "ORDER_CUSTOMER_MISMATCH"
    assert _new_ticket(order_id="ORD-9999")["error"] == "ORDER_NOT_FOUND"
    assert get_action_store().tickets == []


def test_send_operations_notification_is_stored():
    result = send_operations_notification.invoke(
        {
            "severity": Severity.HIGH,
            "summary": "Order ORD-1007 has been delayed for 15 days.",
            "order_id": "ORD-1007",
            "recommended_action": "Review refund request.",
        }
    )
    assert result == {"success": True, "notification_id": "NTF-0001", "channel": "#operations-alerts"}
    assert get_action_store().notifications[0].severity is Severity.HIGH


def test_prepare_customer_response_stores_draft_unchanged():
    draft = "Hi Alex,\n\nYour refund request is being reviewed by our team.\n\nBest regards"
    result = prepare_customer_response.invoke(
        {
            "customer_name": "Alex Johnson",
            "issue_summary": "Delayed order",
            "recommended_action": "Review",
            "draft": draft,
        }
    )
    assert result["draft"] == draft
    assert get_action_store().drafts[0].draft == draft


def test_fallback_customer_draft_is_safe():
    text = fallback_customer_draft("Alex Johnson", "ORD-1007")
    assert text.startswith("Hi Alex,")
    assert "ORD-1007" in text
    assert "refund" not in text.lower()
    assert "compensat" not in text.lower()
    assert fallback_customer_draft("").startswith("Hi there,")


def _request_refund_approval(request_id="req-1"):
    return request_human_approval.invoke(
        {
            "action": "issue_refund",
            "reason": "Refund is a financial action.",
            "context": {"order_id": "ORD-1007", "amount": 249.99},
            "request_id": request_id,
        }
    )


def test_request_human_approval_is_idempotent():
    first = _request_refund_approval()
    again = _request_refund_approval()
    assert first["approval_id"] == again["approval_id"] == "APR-1001"
    assert first["status"] == "pending"
    assert len(get_action_store().approvals) == 1
    assert _request_refund_approval(request_id="req-2")["approval_id"] == "APR-1002"


def test_issue_refund_requires_an_approved_request():
    approval_id = _request_refund_approval()["approval_id"]
    refund = {"order_id": "ORD-1007", "amount": 249.99, "approval_id": approval_id}

    assert issue_refund.invoke(refund)["error"] == "REFUND_NOT_APPROVED"  # still pending
    assert issue_refund.invoke(refund | {"approval_id": "APR-9999"})["error"] == "REFUND_NOT_APPROVED"

    get_action_store().decide_approval(approval_id, ApprovalStatus.APPROVED)
    assert issue_refund.invoke(refund | {"order_id": "ORD-1001"})["error"] == "REFUND_NOT_APPROVED"  # other order
    assert issue_refund.invoke(refund | {"amount": 5000})["error"] == "INVALID_REFUND_AMOUNT"

    result = issue_refund.invoke(refund)
    assert result["success"] is True
    assert result["refund_id"] == "RFD-0001"
    assert len(get_action_store().refunds) == 1


def test_rejected_refund_is_never_issued():
    approval_id = _request_refund_approval()["approval_id"]
    get_action_store().decide_approval(approval_id, ApprovalStatus.REJECTED)
    assert issue_refund.invoke({"order_id": "ORD-1007", "amount": 10, "approval_id": approval_id})["success"] is False
    with pytest.raises(ValueError, match="already"):
        get_action_store().decide_approval(approval_id, ApprovalStatus.APPROVED)


# --- registry ---------------------------------------------------------------------------


def test_registry_separates_read_and_action_tools():
    read = {t.name for t in READ_TOOLS}
    assert read == {"get_order", "get_customer", "get_support_tickets", "get_subscription"}
    assert read.isdisjoint(t.name for t in ACTION_TOOLS + APPROVAL_ONLY_ACTIONS)
    assert [t.name for t in APPROVAL_ONLY_ACTIONS] == ["issue_refund"]  # decision D2


def test_no_tool_can_message_customers():
    all_names = {t.name for t in READ_TOOLS + ACTION_TOOLS + APPROVAL_ONLY_ACTIONS}
    assert not any("send_customer" in name for name in all_names)  # spec Rule 3: drafts only


def test_read_tool_descriptions_tell_the_model_when_to_use_them():
    for read_tool in READ_TOOLS:
        assert len(read_tool.description) > 80, read_tool.name
