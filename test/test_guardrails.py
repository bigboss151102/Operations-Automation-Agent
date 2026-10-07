"""Deterministic guardrails (plan Phase 4). Spec Tests 4, 5, and 6 live here."""

import ast
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from src.common.schemas import (
    ActionName,
    AgentProposal,
    Customer,
    Execution,
    Facts,
    GuardrailOutcome,
    Intent,
    IssueType,
    Order,
    OrderStatus,
    ProposedAction,
    RequestedAction,
    Risk,
    RuleId,
    Severity,
    SupportTicket,
    TicketPriority,
    TicketStatus,
)
from src.config.settings import today
from src.guardrails.draft_policy import check_customer_draft
from src.guardrails.rules import MISSING_ORDER_ID_MESSAGE, NO_REQUEST_MESSAGE, evaluate
from src.guardrails.severity import classify_severity
from src.repositories.data_store import get_data_store
from src.repositories.tickets import find_tickets
from src.utils.dates import days_late

THRESHOLD = 500.0
ALL_ACTIONS = list(ActionName)


# --- factories --------------------------------------------------------------------------


def make_order(**overrides: Any) -> Order:
    fields = {
        "order_id": "ORD-1007",
        "customer_id": "CUS-102",
        "status": OrderStatus.DELAYED,
        "order_date": date(2026, 9, 20),
        "expected_delivery_date": date(2026, 9, 25),
        "total_amount": 249.99,
    }
    return Order(**(fields | overrides))


def make_ticket(**overrides: Any) -> SupportTicket:
    fields = {
        "ticket_id": "TCK-2001",
        "customer_id": "CUS-102",
        "order_id": "ORD-1007",
        "status": TicketStatus.OPEN,
        "priority": TicketPriority.HIGH,
        "issue_type": IssueType.DELIVERY_DELAY,
        "created_at": date(2026, 10, 5),
    }
    return SupportTicket(**(fields | overrides))


def make_proposal(*actions: ActionName, **overrides: Any) -> AgentProposal:
    fields = {
        "intent": Intent.DELIVERY_ISSUE,
        "issue_type": IssueType.DELIVERY_DELAY,
        "requested_action": RequestedAction.INFORMATION,
        "order_id": "ORD-1007",
        "customer_id": "CUS-102",
        "issue_summary": "Order is delayed.",
        "evidence": [],
        "missing_fields": [],
        "clarification_question": None,
        "customer_response_draft": None,
        "proposed_actions": [ProposedAction(action=a, reason="test") for a in actions],
    }
    return AgentProposal(**(fields | overrides))


def make_facts(
    order: Order | None = None, *, tickets: tuple[SupportTicket, ...] = (), late: int = 15, **kw: Any
) -> Facts:
    order = order if order is not None else make_order()
    customer = Customer(customer_id=order.customer_id, name="Alex Johnson", email="alex@example.com")
    verified = kw.pop("verified_ids", frozenset({order.order_id, order.customer_id}))
    return Facts(order=order, customer=customer, order_tickets=tickets, days_late=late, verified_ids=verified, **kw)


def decision_for(result, action: ActionName):
    return next(d for d in result.decisions if d.action == action)


# --- spec Test 4: refunds always need approval (R1) -------------------------------------


@pytest.mark.parametrize("amount", [20, 49.99, 50, 249.99])
def test_refund_requires_approval(amount):
    result = evaluate(
        make_proposal(ActionName.ISSUE_REFUND, requested_action=RequestedAction.REFUND),
        make_facts(make_order(total_amount=amount)),
        high_value_threshold=THRESHOLD,
    )
    refund = decision_for(result, ActionName.ISSUE_REFUND)
    assert refund.execution is Execution.HUMAN_APPROVAL
    assert refund.risk is Risk.HIGH
    assert RuleId.REFUND_REQUIRES_APPROVAL in refund.rules


def test_only_refund_requires_approval():  # decision D2
    result = evaluate(make_proposal(*ALL_ACTIONS), make_facts(), high_value_threshold=THRESHOLD)
    needs_approval = [d.action for d in result.decisions if d.execution is Execution.HUMAN_APPROVAL]
    assert needs_approval == [ActionName.ISSUE_REFUND]


# --- spec Test 5: high-value orders (R2, decision D2) -----------------------------------


@pytest.mark.parametrize(("total", "high_value"), [(499.99, False), (500.0, True), (500.01, True)])
def test_high_value_order_requires_approval(total, high_value):
    result = evaluate(
        make_proposal(*ALL_ACTIONS, intent=Intent.REFUND_REQUEST, requested_action=RequestedAction.REFUND),
        make_facts(make_order(total_amount=total)),
        high_value_threshold=THRESHOLD,
    )
    assert decision_for(result, ActionName.ISSUE_REFUND).execution is Execution.HUMAN_APPROVAL
    assert result.severity is (Severity.CRITICAL if high_value else Severity.HIGH)
    assert result.priority is (TicketPriority.CRITICAL if high_value else TicketPriority.HIGH)
    assert (RuleId.HIGH_VALUE_ORDER in result.case_rules) is high_value
    for internal in (ActionName.CREATE_SUPPORT_TICKET, ActionName.SEND_OPERATIONS_NOTIFICATION):
        decision = decision_for(result, internal)
        assert decision.execution is Execution.AUTOMATIC  # D2: no extra approval for internal actions
        assert (RuleId.HIGH_VALUE_ORDER in decision.rules) is high_value


# --- spec Test 6: duplicate ticket protection (R4) --------------------------------------


@pytest.mark.parametrize("status", [TicketStatus.OPEN, TicketStatus.IN_PROGRESS])
def test_duplicate_ticket_is_blocked(status):
    facts = make_facts(tickets=(make_ticket(status=status),))
    ticket = decision_for(
        evaluate(make_proposal(ActionName.CREATE_SUPPORT_TICKET), facts, high_value_threshold=THRESHOLD),
        ActionName.CREATE_SUPPORT_TICKET,
    )
    assert ticket.execution is Execution.BLOCKED
    assert ticket.rules == (RuleId.DUPLICATE_TICKET,)
    assert ticket.related_ticket_id == "TCK-2001"
    assert ticket.reason == f"An existing support ticket already exists. Ticket: TCK-2001, Status: {status.value}"


@pytest.mark.parametrize(
    "ticket",
    [
        make_ticket(status=TicketStatus.CLOSED),
        make_ticket(status=TicketStatus.RESOLVED),
        make_ticket(issue_type=IssueType.ADDRESS_ISSUE),  # open, but a different issue
    ],
)
def test_non_duplicate_ticket_is_allowed(ticket):
    result = evaluate(
        make_proposal(ActionName.CREATE_SUPPORT_TICKET), make_facts(tickets=(ticket,)), high_value_threshold=THRESHOLD
    )
    assert decision_for(result, ActionName.CREATE_SUPPORT_TICKET).execution is Execution.AUTOMATIC


def test_duplicate_block_does_not_stop_other_actions():
    result = evaluate(
        make_proposal(ActionName.CREATE_SUPPORT_TICKET, ActionName.SEND_OPERATIONS_NOTIFICATION),
        make_facts(tickets=(make_ticket(),)),
        high_value_threshold=THRESHOLD,
    )
    assert result.outcome is GuardrailOutcome.PROCEED
    assert decision_for(result, ActionName.SEND_OPERATIONS_NOTIFICATION).execution is Execution.AUTOMATIC


# --- R3 and unknown actions (defense in depth: the schema already forbids them) ---------


def _unchecked_proposal(action_name: str) -> AgentProposal:
    raw = ProposedAction.model_construct(action=action_name, reason="test")  # bypasses schema validation
    return make_proposal().model_copy(update={"proposed_actions": [raw]})


def test_send_customer_message_is_blocked():
    (decision,) = evaluate(
        _unchecked_proposal("send_customer_message"), make_facts(), high_value_threshold=THRESHOLD
    ).decisions
    assert decision.execution is Execution.BLOCKED
    assert decision.rules == (RuleId.EXTERNAL_COMMUNICATION_BLOCKED,)


def test_unknown_action_is_blocked():
    (decision,) = evaluate(
        _unchecked_proposal("delete_database"), make_facts(), high_value_threshold=THRESHOLD
    ).decisions
    assert decision.execution is Execution.BLOCKED
    assert decision.rules == (RuleId.UNKNOWN_ACTION,)


# --- case-level stop rules: R5, R6, R7 --------------------------------------------------


def _assert_everything_blocked(result, outcome: GuardrailOutcome, rule: RuleId):
    assert result.outcome is outcome
    assert result.case_rules == (rule,)
    assert result.severity is None
    assert result.decisions  # the LLM did propose actions...
    assert all(d.execution is Execution.BLOCKED for d in result.decisions)  # ...and none may run


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"missing_fields": ["order_id"], "order_id": None, "customer_id": None}, id="missing-fields"),
        pytest.param(
            {
                "intent": Intent.REFUND_REQUEST,
                "requested_action": RequestedAction.REFUND,
                "order_id": None,
                "customer_id": None,
            },
            id="refund-without-order",
        ),
        pytest.param(
            {
                "intent": Intent.SUBSCRIPTION_ISSUE,
                "issue_type": IssueType.SUBSCRIPTION_ISSUE,
                "order_id": None,
                "customer_id": None,
            },
            id="subscription-without-customer",
        ),
    ],
)
def test_missing_information_blocks_all_actions(overrides):
    proposal = make_proposal(ActionName.ISSUE_REFUND, ActionName.CREATE_SUPPORT_TICKET, **overrides)
    result = evaluate(proposal, Facts(verified_ids=frozenset()), high_value_threshold=THRESHOLD)
    _assert_everything_blocked(result, GuardrailOutcome.NEEDS_MORE_INFO, RuleId.MISSING_INFORMATION)


def test_missing_information_uses_the_llm_question_with_fallback():
    no_ids = {"order_id": None, "customer_id": None, "missing_fields": ["order_id"]}
    asked = make_proposal(**no_ids, clarification_question="Could you share your order ID?")
    assert evaluate(asked, Facts(), high_value_threshold=THRESHOLD).message == "Could you share your order ID?"
    silent = make_proposal(**no_ids)
    assert evaluate(silent, Facts(), high_value_threshold=THRESHOLD).message == MISSING_ORDER_ID_MESSAGE


def test_greeting_asks_how_to_help_instead_of_finishing():
    greeting = {
        "intent": Intent.OTHER,
        "issue_type": IssueType.OTHER,
        "requested_action": RequestedAction.NONE,
        "order_id": None,
        "customer_id": None,
    }
    replied = make_proposal(**greeting, clarification_question="Xin chào! Mình có thể giúp gì cho bạn?")
    result = evaluate(replied, Facts(verified_ids=frozenset()), high_value_threshold=THRESHOLD)
    assert result.outcome is GuardrailOutcome.NEEDS_MORE_INFO
    assert result.message == "Xin chào! Mình có thể giúp gì cho bạn?"  # the LLM's own words
    silent = make_proposal(**greeting)  # the LLM forgot to reply: a friendly fallback, never "the team is on it"
    assert evaluate(silent, Facts(), high_value_threshold=THRESHOLD).message == NO_REQUEST_MESSAGE


def test_invented_id_outranks_missing_information():
    # No ID in the message, yet the proposal names a customer: treat it as a hallucination (R7), not just R5.
    proposal = make_proposal(order_id=None, customer_id="CUS-102", missing_fields=["order_id"])
    result = evaluate(proposal, Facts(verified_ids=frozenset()), high_value_threshold=THRESHOLD)
    assert result.case_rules == (RuleId.UNVERIFIED_ID,)


def test_order_not_found_blocks_all_actions():
    proposal = make_proposal(
        ActionName.CREATE_SUPPORT_TICKET, ActionName.ISSUE_REFUND, order_id="ORD-9999", customer_id=None
    )
    result = evaluate(proposal, Facts(verified_ids=frozenset({"ORD-9999"})), high_value_threshold=THRESHOLD)
    _assert_everything_blocked(result, GuardrailOutcome.NOT_FOUND, RuleId.ORDER_NOT_FOUND)
    assert result.message == "I couldn't find order ORD-9999 in the available operations data."


def test_unverified_order_id_blocks_all_actions():
    # The customer never wrote ORD-1007 and no tool returned it: the LLM made it up.
    facts = make_facts(verified_ids=frozenset())
    result = evaluate(make_proposal(ActionName.ISSUE_REFUND), facts, high_value_threshold=THRESHOLD)
    _assert_everything_blocked(result, GuardrailOutcome.REJECTED, RuleId.UNVERIFIED_ID)


def test_customer_id_returned_by_a_tool_is_verified():
    facts = make_facts(verified_ids=frozenset({"ORD-1007", "CUS-102"}))  # CUS-102 came from get_order's result
    assert evaluate(make_proposal(), facts, high_value_threshold=THRESHOLD).outcome is GuardrailOutcome.PROCEED


# --- severity (decision D3) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("proposal_kw", "facts_kw", "expected", "reason"),
    [
        ({"intent": Intent.ORDER_STATUS}, {"late": 0}, Severity.LOW, "informational"),
        ({}, {"late": 2}, Severity.MEDIUM, "delay_1_to_7_days"),
        ({}, {"late": 7}, Severity.MEDIUM, "delay_1_to_7_days"),
        ({"issue_type": IssueType.SUBSCRIPTION_ISSUE}, {"late": 0}, Severity.MEDIUM, "subscription_issue"),
        ({"requested_action": RequestedAction.REFUND}, {"late": 0}, Severity.HIGH, "refund_requested"),
        ({}, {"late": 8}, Severity.HIGH, "delay_over_7_days"),
        ({"issue_type": IssueType.MISSING_ORDER}, {"late": 0}, Severity.HIGH, "missing_order"),
        (
            {"requested_action": RequestedAction.REFUND},
            {"late": 0, "order": make_order(total_amount=1200)},
            Severity.CRITICAL,
            "high_value_refund",
        ),
        (
            {},
            {"late": 0, "tickets": (make_ticket(issue_type=IssueType.REFUND_REQUEST),) * 2},
            Severity.CRITICAL,
            "repeated_refund_requests",
        ),
        (
            {"issue_type": IssueType.MISSING_ORDER},
            {"late": 0, "order": make_order(total_amount=900)},
            Severity.CRITICAL,
            "high_value_missing_order",
        ),
    ],
)
def test_severity_table(proposal_kw, facts_kw, expected, reason):
    result = classify_severity(make_proposal(**proposal_kw), make_facts(**facts_kw), high_value_threshold=THRESHOLD)
    assert result.severity is expected
    assert reason in result.reasons


def test_highest_severity_wins():
    # 15 days late (HIGH) + refund (HIGH) + $1,200 refund (CRITICAL)
    result = classify_severity(
        make_proposal(requested_action=RequestedAction.REFUND),
        make_facts(make_order(total_amount=1200), late=15),
        high_value_threshold=THRESHOLD,
    )
    assert result.severity is Severity.CRITICAL
    assert result.reasons == ("high_value_refund",)


# --- the spec §16 scenario table, evaluated against the real sample data ----------------


def _facts_from_data(order_id: str) -> Facts:
    order = get_data_store().order(order_id)
    assert order is not None
    return Facts(
        order=order,
        customer=get_data_store().customer(order.customer_id),
        order_tickets=tuple(find_tickets(order_id=order_id)),
        days_late=days_late(order.expected_delivery_date, order.actual_delivery_date, today()),
        verified_ids=frozenset({order_id, order.customer_id}),
    )


@pytest.mark.parametrize(
    ("order_id", "intent", "refund", "expected"),
    [
        ("ORD-1004", Intent.ORDER_STATUS, False, Severity.LOW),
        ("ORD-1001", Intent.DELIVERY_ISSUE, False, Severity.MEDIUM),  # Scenario 1
        ("ORD-1007", Intent.REFUND_REQUEST, True, Severity.HIGH),  # Scenario 2
        ("ORD-1008", Intent.DELIVERY_ISSUE, False, Severity.MEDIUM),  # Scenario 3
        ("ORD-1015", Intent.REFUND_REQUEST, True, Severity.CRITICAL),  # Scenario 6
        ("ORD-1011", Intent.REFUND_REQUEST, True, Severity.CRITICAL),  # repeated refund requests
    ],
)
def test_scenario_severities_on_sample_data(order_id, intent, refund, expected):
    order = get_data_store().order(order_id)
    assert order is not None
    proposal = make_proposal(
        *ALL_ACTIONS,
        intent=intent,
        requested_action=RequestedAction.REFUND if refund else RequestedAction.INFORMATION,
        order_id=order_id,
        customer_id=order.customer_id,
    )
    assert evaluate(proposal, _facts_from_data(order_id), high_value_threshold=THRESHOLD).severity is expected


def test_scenario_3_blocks_the_duplicate_ticket_on_sample_data():
    proposal = make_proposal(ActionName.CREATE_SUPPORT_TICKET, order_id="ORD-1008", customer_id="CUS-107")
    result = evaluate(proposal, _facts_from_data("ORD-1008"), high_value_threshold=THRESHOLD)
    assert decision_for(result, ActionName.CREATE_SUPPORT_TICKET).related_ticket_id == "TCK-2001"


def test_scenario_1_closed_ticket_does_not_block_on_sample_data():
    proposal = make_proposal(ActionName.CREATE_SUPPORT_TICKET, order_id="ORD-1001", customer_id="CUS-101")
    result = evaluate(proposal, _facts_from_data("ORD-1001"), high_value_threshold=THRESHOLD)
    assert decision_for(result, ActionName.CREATE_SUPPORT_TICKET).execution is Execution.AUTOMATIC


# --- R8: customer draft policy (decision D4) --------------------------------------------


@pytest.mark.parametrize(
    "draft",
    [
        "Hi Alex,\n\nYour refund request is being reviewed by our team. We'll update you within 1-2 business days.",
        "Hi Maya, your order ORD-1001 was expected on October 8 and our operations team is looking into it.",
    ],
)
def test_customer_draft_policy_accepts_safe_drafts(draft):
    assert check_customer_draft(draft) == []


@pytest.mark.parametrize(
    ("draft", "code"),
    [
        ("We have refunded your order.", "refund_promise"),
        ("You will receive a full refund within 5 days.", "refund_promise"),
        ("Your refund has been processed.", "refund_promise"),
        ("We will refund the full amount.", "refund_promise"),
        ("We will compensate you for the trouble.", "compensation_promise"),
        ("Here is a voucher for your next order.", "compensation_promise"),
        ("This was classified as HIGH severity.", "internal_detail"),
        ("Ticket TCK-2042 has high priority.", "internal_detail"),
        ("Approval APR-1001 is pending.", "internal_detail"),
        ("Blocked by duplicate_ticket.", "internal_detail"),
        ("", "empty"),
        ("   ", "empty"),
    ],
)
def test_customer_draft_policy_rejects_violations(draft, code):
    assert code in {v.code for v in check_customer_draft(draft)}


def test_customer_draft_policy_handles_missing_draft():
    assert [v.code for v in check_customer_draft(None)] == ["empty"]


# --- architecture: guardrails never touch an LLM ----------------------------------------

_GUARDRAILS_DIR = Path(__file__).resolve().parents[1] / "src" / "guardrails"
_FORBIDDEN_PREFIXES = ("langchain", "openai", "src.llm", "src.agents")


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("filename", ["rules.py", "severity.py", "draft_policy.py"])
def test_guardrails_have_no_llm_imports(filename):
    forbidden = {m for m in _imported_modules(_GUARDRAILS_DIR / filename) if m.startswith(_FORBIDDEN_PREFIXES)}
    assert not forbidden, f"{filename} imports {forbidden}"
