"""The investigator agent with a scripted model (no OpenAI calls)."""

from typing import Any

from fakes import fake_model, tool_call
from langchain_core.messages import HumanMessage, ToolMessage

from src.agents.investigator import build_investigator
from src.common.schemas import ActionName, AgentProposal, Intent
from src.repositories.action_store import get_action_store


def _proposal_args(**overrides: Any) -> dict[str, Any]:
    args = {
        "intent": "refund_request",
        "issue_type": "delivery_delay",
        "requested_action": "refund",
        "order_id": "ORD-1007",
        "customer_id": "CUS-102",
        "issue_summary": "Order ORD-1007 is 15 days late and the customer wants a refund.",
        "evidence": ["Order status is delayed.", "15 days past the expected delivery date."],
        "proposed_actions": [
            {"action": "create_support_ticket", "reason": "Track the delay."},
            {"action": "issue_refund", "reason": "Customer requested a refund."},
        ],
        "customer_response_draft": "Hi Alex, your refund request is being reviewed by our team.",
        "missing_fields": [],
        "clarification_question": None,
    }
    return args | overrides


def _run(*turns, message: str = "<customer_request>My order ORD-1007 is 15 days late.</customer_request>", **kw):
    agent = build_investigator(fake_model(*turns), **kw)
    return agent.invoke({"messages": [HumanMessage(message)]})


def _tool_results(result) -> list[ToolMessage]:
    return [m for m in result["messages"] if isinstance(m, ToolMessage) and m.name != "AgentProposal"]


def test_investigator_returns_structured_proposal():
    result = _run(
        tool_call("get_order", order_id="ORD-1007"),
        tool_call("AgentProposal", **_proposal_args()),
    )
    proposal = result["structured_response"]
    assert isinstance(proposal, AgentProposal)
    assert proposal.intent is Intent.REFUND_REQUEST
    assert [a.action for a in proposal.proposed_actions] == [ActionName.CREATE_SUPPORT_TICKET, ActionName.ISSUE_REFUND]
    assert '"days_late": 15' in _tool_results(result)[0].content  # the read tool really ran


def test_investigator_returns_clarification_when_id_missing():
    result = _run(
        tool_call(
            "AgentProposal",
            **_proposal_args(
                order_id=None,
                customer_id=None,
                proposed_actions=[],
                missing_fields=["order_id"],
                clarification_question="Could you share your order ID so I can check it?",
                customer_response_draft=None,
            ),
        ),
        message="<customer_request>My order hasn't arrived and I want a refund.</customer_request>",
    )
    proposal = result["structured_response"]
    assert proposal.missing_fields == ["order_id"]
    assert proposal.clarification_question.startswith("Could you share your order ID")
    assert _tool_results(result) == []  # no lookup happened


def test_investigator_invalid_output_yields_no_proposal():  # basis for spec Test 8
    bad = {"intent": "not-an-intent", "proposed_actions": [{"action": "delete_everything"}]}
    result = _run(
        tool_call("AgentProposal", **bad),
        tool_call("AgentProposal", **bad),
        tool_call("AgentProposal", **bad),
        model_call_limit=2,
    )
    assert result.get("structured_response") is None


def test_investigator_only_has_read_tools():
    # The model tries to perform an action directly; the agent has no such tool, so nothing happens.
    result = _run(
        tool_call(
            "create_support_ticket",
            customer_id="CUS-102",
            order_id="ORD-1007",
            issue_type="delivery_delay",
            priority="high",
            summary="x",
        ),
        tool_call("AgentProposal", **_proposal_args()),
    )
    (attempt,) = _tool_results(result)
    assert attempt.status == "error"
    assert get_action_store().tickets == []
    assert result["structured_response"] is not None


def test_every_proposal_field_is_required():
    # Models skip optional fields; every key must be sent (null / [] when not applicable).
    schema = AgentProposal.model_json_schema()
    assert set(schema["required"]) == set(AgentProposal.model_fields)
