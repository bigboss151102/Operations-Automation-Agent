"""End-to-end pipeline tests with a scripted model (plan Phase 6). Spec Tests 3, 6, 7, and 8 live here."""

import io
import logging
from typing import Any

import pytest
from fakes import fake_model, tool_call
from langchain_core.messages import AIMessage

from src.agents.graph import build_graph
from src.agents.service import resume_agent, run_agent
from src.common.schemas import ApprovalStatus, Execution, ResponseStatus, RuleId, Severity
from src.memory.checkpointer import make_checkpointer
from src.repositories.action_store import get_action_store
from src.utils.logging import get_logger, make_handler

COMPLIANT_DRAFT = (
    "Hi Alex,\n\nYour refund request is being reviewed by our team.\n\nBest regards,\nThe OpsPilot Support Team"
)


def graph_for(*turns: AIMessage, model_call_limit: int = 8):
    return build_graph(
        fake_model(*turns), make_checkpointer(), high_value_threshold=500.0, model_call_limit=model_call_limit
    )


def proposal(**overrides: Any) -> AIMessage:
    args = {
        "intent": "delivery_issue",
        "issue_type": "delivery_delay",
        "requested_action": "information",
        "order_id": "ORD-1001",
        "customer_id": "CUS-101",
        "issue_summary": "Order ORD-1001 is 2 days late.",
        "evidence": ["Order status is delayed.", "2 days past the expected delivery date."],
        "proposed_actions": [
            {"action": "create_support_ticket", "reason": "Track the delay."},
            {"action": "send_operations_notification", "reason": "Ops should know."},
            {"action": "prepare_customer_response", "reason": "Reply draft."},
        ],
        "customer_response_draft": "Hi Maya,\n\nOur operations team is looking into the delay.\n\nBest regards",
        "missing_fields": [],
        "clarification_question": None,
    }
    return tool_call("AgentProposal", **(args | overrides))


def investigation(order_id: str, customer_id: str) -> list[AIMessage]:
    return [
        tool_call("get_order", order_id=order_id),
        tool_call("get_customer", customer_id=customer_id),
        tool_call("get_support_tickets", customer_id=customer_id, order_id=order_id),
    ]


REFUND_ACTIONS = [
    {"action": "create_support_ticket", "reason": "Track the delay."},
    {"action": "send_operations_notification", "reason": "Ops should know."},
    {"action": "issue_refund", "reason": "Customer asked for a refund."},
    {"action": "prepare_customer_response", "reason": "Reply draft."},
]


def refund_proposal(**overrides: Any) -> AIMessage:
    return proposal(
        **{
            "intent": "refund_request",
            "requested_action": "refund",
            "order_id": "ORD-1007",
            "customer_id": "CUS-102",
            "issue_summary": "Order ORD-1007 is 15 days late; the customer wants a refund.",
            "proposed_actions": REFUND_ACTIONS,
            "customer_response_draft": COMPLIANT_DRAFT,
        }
        | overrides
    )


def refund_graph():
    return graph_for(*investigation("ORD-1007", "CUS-102"), refund_proposal())


def executed(response) -> dict[str, bool]:
    return {a.action: a.success for a in response.executed_actions}


def decision(response, action: str):
    return next(d for d in response.recommended_actions if d.action == action)


# --- Scenario 1 / spec Test 7: safe actions run automatically ---------------------------


def test_safe_actions_execute_automatically():
    response = run_agent(
        "My order ORD-1001 is two days late.", graph=graph_for(*investigation("ORD-1001", "CUS-101"), proposal())
    )
    assert response.status is ResponseStatus.COMPLETED
    assert response.severity is Severity.MEDIUM
    assert executed(response) == {
        "create_support_ticket": True,
        "send_operations_notification": True,
        "prepare_customer_response": True,
    }
    store = get_action_store()
    assert [t.ticket_id for t in store.tickets] == ["TCK-2009"]  # the closed TCK-2004 did not block it
    assert store.notifications[0].severity is Severity.MEDIUM
    assert response.approval_required is False


# --- Scenario 2: refund pauses for a human --------------------------------------------


def test_refund_pauses_for_approval_then_executes_on_approve():
    graph = refund_graph()
    paused = run_agent("My order ORD-1007 is 15 days late. I want a refund.", graph=graph)

    assert paused.status is ResponseStatus.AWAITING_APPROVAL
    assert paused.severity is Severity.HIGH
    assert decision(paused, "issue_refund").execution is Execution.HUMAN_APPROVAL
    assert "issue_refund" not in executed(paused)  # nothing financial happened yet
    assert get_action_store().refunds == []
    (approval,) = paused.approvals
    assert (approval.status, approval.context["amount"]) == (ApprovalStatus.PENDING, 249.99)
    assert paused.customer_response == COMPLIANT_DRAFT

    done = resume_agent(paused.thread_id, {approval.approval_id: "approve"}, graph=graph)
    assert done.status is ResponseStatus.COMPLETED
    assert executed(done)["issue_refund"] is True
    assert done.approvals[0].status is ApprovalStatus.APPROVED
    assert len(get_action_store().refunds) == 1
    assert len(get_action_store().approvals) == 1  # created once, although the node re-ran on resume


def test_refund_rejected_is_not_executed():
    graph = refund_graph()
    paused = run_agent("My order ORD-1007 is 15 days late. I want a refund.", graph=graph)
    done = resume_agent(paused.thread_id, {paused.approvals[0].approval_id: "reject"}, graph=graph)
    assert done.status is ResponseStatus.COMPLETED
    assert "issue_refund" not in executed(done)
    assert done.approvals[0].status is ApprovalStatus.REJECTED
    assert get_action_store().refunds == []


def test_missing_decision_counts_as_rejection():
    graph = refund_graph()
    paused = run_agent("My order ORD-1007 is 15 days late. I want a refund.", graph=graph)
    done = resume_agent(paused.thread_id, {}, graph=graph)
    assert done.approvals[0].status is ApprovalStatus.REJECTED
    assert get_action_store().refunds == []


def test_resume_without_pending_approval_is_an_error():
    graph = graph_for(*investigation("ORD-1001", "CUS-101"), proposal())
    finished = run_agent("My order ORD-1001 is two days late.", graph=graph)
    again = resume_agent(finished.thread_id, {"APR-1001": "approve"}, graph=graph)
    assert again.status is ResponseStatus.ERROR
    assert get_action_store().refunds == []


def test_high_value_refund_is_critical_and_still_needs_approval():  # Scenario 6
    graph = graph_for(
        *investigation("ORD-1015", "CUS-111"),
        refund_proposal(order_id="ORD-1015", customer_id="CUS-111", customer_response_draft=None),
    )
    paused = run_agent("My order ORD-1015 is delayed. Please refund the order.", graph=graph)
    assert paused.status is ResponseStatus.AWAITING_APPROVAL
    assert paused.severity is Severity.CRITICAL
    assert get_action_store().tickets[0].priority == "critical"
    assert get_action_store().notifications[0].severity is Severity.CRITICAL


# --- Scenario 3 / spec Test 6: existing ticket -----------------------------------------


def test_existing_ticket_prevents_duplicate():
    response = run_agent(
        "Please help with my delayed order ORD-1008.",
        graph=graph_for(*investigation("ORD-1008", "CUS-107"), proposal(order_id="ORD-1008", customer_id="CUS-107")),
    )
    ticket = decision(response, "create_support_ticket")
    assert ticket.execution is Execution.BLOCKED
    assert ticket.reason == "An existing support ticket already exists. Ticket: TCK-2001, Status: open"
    assert get_action_store().tickets == []
    assert executed(response)["send_operations_notification"] is True
    assert get_action_store().notifications[0].recommended_action == "Follow up on existing ticket TCK-2001."


# --- Scenario 4: unknown order ---------------------------------------------------------


def test_unknown_order_returns_not_found():
    graph = graph_for(
        tool_call("get_order", order_id="ORD-9999"),
        proposal(
            intent="order_status",
            issue_type="other",
            order_id="ORD-9999",
            customer_id=None,
            issue_summary="Order ORD-9999 was not found.",
            evidence=["Order ORD-9999 was not found."],
            proposed_actions=[],
            customer_response_draft=None,
        ),
    )
    response = run_agent("Please check order ORD-9999.", graph=graph)
    assert response.status is ResponseStatus.NOT_FOUND
    assert response.message == "I couldn't find order ORD-9999 in the available operations data."
    assert response.executed_actions == []


# --- Scenario 5 / spec Test 3: missing order ID ----------------------------------------


def _clarification(**overrides: Any) -> AIMessage:
    return proposal(
        **{
            "intent": "refund_request",
            "issue_type": "missing_order",
            "requested_action": "refund",
            "order_id": None,
            "customer_id": None,
            "issue_summary": "The customer reports an undelivered order and wants a refund; no order ID given.",
            "evidence": [],
            "proposed_actions": [],
            "missing_fields": ["order_id"],
            "clarification_question": "Could you share your order ID so I can check it?",
            "customer_response_draft": None,
        }
        | overrides
    )


def test_missing_order_id_asks_for_it():
    response = run_agent("My order hasn't arrived and I want a refund.", graph=graph_for(_clarification()))
    assert response.status is ResponseStatus.NEEDS_MORE_INFO
    assert response.message == "Could you share your order ID so I can check it?"  # the LLM's own words
    assert response.executed_actions == []
    assert response.approvals == []


def test_missing_id_cannot_be_bypassed():
    # The model guesses an order (blocked by middleware), then proposes a refund anyway (blocked by guardrails).
    graph = graph_for(
        tool_call("get_order", order_id="ORD-1007"),
        refund_proposal(),
    )
    response = run_agent("My order hasn't arrived and I want a refund.", graph=graph)
    assert response.status is ResponseStatus.ERROR
    assert response.executed_actions == []
    assert response.approvals == []
    assert all(d.execution is Execution.BLOCKED for d in response.recommended_actions)
    assert get_action_store().approvals == []


def test_follow_up_with_id_resumes_investigation():  # Scenario 5b
    response = run_agent(
        "It's ORD-1007.", history=["My order hasn't arrived and I want a refund."], graph=refund_graph()
    )
    assert response.status is ResponseStatus.AWAITING_APPROVAL
    assert response.order_id == "ORD-1007"


# --- spec Test 8: malformed LLM output -------------------------------------------------


def test_malformed_llm_output_triggers_no_action():
    bad = tool_call("AgentProposal", intent="nonsense", proposed_actions=[{"action": "delete_everything"}])
    response = run_agent("My order ORD-1007 is late.", graph=graph_for(bad, bad, bad, model_call_limit=2))
    assert response.status is ResponseStatus.ERROR
    assert response.executed_actions == []
    assert response.approvals == []
    store = get_action_store()
    assert (store.tickets, store.notifications, store.drafts, store.approvals) == ([], [], [], [])


def test_hallucinated_order_id_is_rejected():
    # The customer wrote ORD-1001; the model proposes ORD-1007 without ever looking it up (R7, layer 2).
    graph = graph_for(refund_proposal())
    response = run_agent("My order ORD-1001 is late, I want a refund.", graph=graph)
    assert response.status is ResponseStatus.ERROR
    assert RuleId.UNVERIFIED_ID in decision(response, "issue_refund").rules
    assert get_action_store().approvals == []


def test_llm_failure_returns_a_safe_error():
    response = run_agent("My order ORD-1001 is late.", graph=graph_for())  # empty script: the model call fails
    assert response.status is ResponseStatus.ERROR
    assert response.executed_actions == []


def test_invalid_input_never_reaches_the_llm():
    response = run_agent("   ", graph=graph_for())  # an empty script would fail if the model were called
    assert response.status is ResponseStatus.ERROR
    assert response.message is not None
    assert "empty or too long" in response.message


# --- R8: the LLM's customer draft -------------------------------------------------------


def test_llm_customer_draft_is_used_when_compliant():
    response = run_agent(
        "My order ORD-1001 is two days late.", graph=graph_for(*investigation("ORD-1001", "CUS-101"), proposal())
    )
    assert response.customer_response == "Hi Maya,\n\nOur operations team is looking into the delay.\n\nBest regards"
    assert response.draft_policy_violations == []


def test_llm_customer_draft_promising_refund_is_replaced():
    graph = graph_for(
        *investigation("ORD-1007", "CUS-102"),
        refund_proposal(customer_response_draft="Hi Alex, we have refunded your order."),
    )
    response = run_agent("My order ORD-1007 is 15 days late. I want a refund.", graph=graph)
    assert response.customer_response is not None
    assert response.customer_response.startswith("Hi Alex,")
    assert "refund" not in response.customer_response.lower()
    assert [v.code for v in response.draft_policy_violations] == ["refund_promise"]
    assert executed(response)["create_support_ticket"] is True  # other actions unaffected


# --- observability: the spec §22 decision trail -----------------------------------------


@pytest.fixture
def captured_logs():
    stream = io.StringIO()
    logger = get_logger()
    logger.setLevel(logging.INFO)
    handler = make_handler(stream)
    logger.addHandler(handler)
    yield stream
    logger.removeHandler(handler)


def test_decision_trail_is_logged(captured_logs):
    response = run_agent("My order ORD-1007 is 15 days late. I want a refund.", graph=refund_graph())
    log = captured_logs.getvalue()
    assert f"request_id={response.request_id}" in log
    for event in (
        "event=request_received",
        "event=intent_detected intent=refund_request",
        "event=tool_called tool=get_order",
        "event=severity_classified severity=HIGH",
        "event=guardrail_decision action=issue_refund execution=human_approval rules=refund_requires_approval",
        "event=action_executed action=create_support_ticket",
        "event=approval_requested",
        "event=request_completed status=awaiting_approval",
    ):
        assert event in log, event
    assert "15 days late. I want a refund" not in log  # the customer's message text is never logged


def test_resume_round_trips_state_without_unregistered_type_warnings(caplog):
    graph = refund_graph()
    with caplog.at_level(logging.WARNING):
        paused = run_agent("My order ORD-1007 is 15 days late. I want a refund.", graph=graph)
        resume_agent(paused.thread_id, {paused.approvals[0].approval_id: "approve"}, graph=graph)
    assert not [r for r in caplog.records if "unregistered type" in r.getMessage()]
