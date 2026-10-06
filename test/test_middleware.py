"""Investigation-time guardrail middleware (spec §12.7, layer 1)."""

import json
from typing import Any

from fakes import fake_model, tool_call
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from src.agents.investigator import build_investigator
from src.guardrails.middleware import VerifiedIdMiddleware

CALLS: list[str] = []


@tool
def lookup_order(order_id: str) -> dict[str, Any]:
    """Spy tool: records every call."""
    CALLS.append(order_id)
    return {"success": True, "order_id": order_id, "customer_id": "CUS-102"}


@tool
def lookup_customer(customer_id: str) -> dict[str, Any]:
    """Spy tool: records every call."""
    CALLS.append(customer_id)
    return {"success": True, "customer_id": customer_id}


def _run_spy_agent(*turns, message: str) -> list[ToolMessage]:
    CALLS.clear()
    model = fake_model(*turns, AIMessage(content="done"))  # final turn without tool calls ends the loop
    agent = create_agent(model, tools=[lookup_order, lookup_customer], middleware=[VerifiedIdMiddleware()])
    result = agent.invoke({"messages": [HumanMessage(message)]})
    return [m for m in result["messages"] if isinstance(m, ToolMessage)]


def test_unverified_id_lookup_is_blocked():
    (result,) = _run_spy_agent(tool_call("lookup_order", order_id="ORD-5555"), message="My order ORD-1007 is late")
    assert CALLS == []  # the tool never ran
    assert result.status == "error"
    assert json.loads(result.content)["error"] == "UNVERIFIED_ID"


def test_guessed_id_is_blocked_when_the_customer_wrote_none():  # spec Scenario 5
    (result,) = _run_spy_agent(tool_call("lookup_order", order_id="ORD-1001"), message="My order hasn't arrived")
    assert CALLS == []
    assert json.loads(result.content)["error"] == "UNVERIFIED_ID"


def test_model_text_does_not_verify_an_id():
    # An ID the model itself mentioned (AI message) is not evidence; only human and tool messages count.
    guess = AIMessage(
        content="It's probably ORD-5555, let me check.",
        tool_calls=[{"name": "lookup_order", "args": {"order_id": "ORD-5555"}, "id": "call_guess"}],
    )
    (result,) = _run_spy_agent(guess, message="Where is my order?")
    assert CALLS == []
    assert json.loads(result.content)["error"] == "UNVERIFIED_ID"


def test_written_id_lookup_is_allowed():
    (result,) = _run_spy_agent(tool_call("lookup_order", order_id="ORD-1007"), message="My order ORD-1007 is late")
    assert CALLS == ["ORD-1007"]
    assert json.loads(result.content)["success"] is True


def test_id_from_tool_result_is_allowed():
    results = _run_spy_agent(
        tool_call("lookup_order", order_id="ORD-1007"),
        tool_call("lookup_customer", customer_id="CUS-102"),  # returned by lookup_order, never written by the customer
        message="My order ORD-1007 is late",
    )
    assert CALLS == ["ORD-1007", "CUS-102"]
    assert all(json.loads(r.content)["success"] for r in results)


def test_customer_email_is_redacted_from_tool_results():
    agent = build_investigator(
        fake_model(
            tool_call("get_order", order_id="ORD-1007"),
            tool_call("get_customer", customer_id="CUS-102"),
        ),
        model_call_limit=2,  # two scripted turns, then the limit ends the run
    )
    result = agent.invoke({"messages": [HumanMessage("<customer_request>ORD-1007 is late</customer_request>")]})
    customer_result = next(m for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "get_customer")
    assert "[REDACTED_EMAIL]" in customer_result.content
    assert "alex@example.com" not in customer_result.content
    assert "Alex Johnson" in customer_result.content  # the name is still available for the draft
