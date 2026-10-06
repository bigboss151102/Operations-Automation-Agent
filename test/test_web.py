"""Streamlit UI flows with AppTest (no browser, no LLM). The service functions are replaced by fakes."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from src.agents import service
from src.common.schemas import (
    AnalyzeResponse,
    ApprovalRequest,
    ApprovalStatus,
    ExecutedAction,
    Execution,
    GuardrailDecision,
    ResponseStatus,
    Risk,
    RuleId,
    Severity,
)

APP = str(Path(__file__).resolve().parents[1] / "src" / "web" / "app.py")
REFUND_TEXT = "My order ORD-1007 is 15 days late. I want a refund."


def _approval(status: ApprovalStatus = ApprovalStatus.PENDING) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id="APR-1001",
        request_id="req-ui",
        action="issue_refund",
        reason="Refunds are financial actions and always require human approval.",
        context={"order_id": "ORD-1007", "amount": 249.99, "currency": "USD"},
        status=status,
        created_at=date(2026, 10, 10),
    )


def _refund_response(status: ResponseStatus, approval_status: ApprovalStatus) -> AnalyzeResponse:
    executed = [ExecutedAction(action="create_support_ticket", success=True, result_id="TCK-2009")]
    if approval_status is ApprovalStatus.APPROVED:
        executed.append(ExecutedAction(action="issue_refund", success=True, result_id="RFD-0001"))
    return AnalyzeResponse(
        request_id="req-ui",
        thread_id="req-ui",
        status=status,
        order_id="ORD-1007",
        customer_id="CUS-102",
        issue_summary="Order ORD-1007 is 15 days late; the customer wants a refund.",
        severity=Severity.HIGH,
        evidence=["Order status is delayed."],
        recommended_actions=[
            GuardrailDecision(
                action="issue_refund",
                risk=Risk.HIGH,
                execution=Execution.HUMAN_APPROVAL,
                rules=(RuleId.REFUND_REQUIRES_APPROVAL,),
                reason="Refunds always require human approval.",
            )
        ],
        executed_actions=executed,
        approvals=[_approval(approval_status)],
        approval_required=approval_status is ApprovalStatus.PENDING,
        customer_response="Hi Alex,\n\nYour refund request is being reviewed by our team.",
    )


@pytest.fixture
def fake_service(monkeypatch) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"run": [], "resume": []}
    replies: list[AnalyzeResponse] = []

    def fake_run(message: str, history: list[str] | None = None, *, graph: Any = None) -> AnalyzeResponse:
        calls["run"].append((message, list(history or [])))
        return replies.pop(0)

    def fake_resume(thread_id: str, decisions: dict[str, str], *, graph: Any = None) -> AnalyzeResponse:
        calls["resume"].append((thread_id, decisions))
        approved = decisions.get("APR-1001") == "approve"
        return _refund_response(
            ResponseStatus.COMPLETED, ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        )

    monkeypatch.setattr(service, "run_agent", fake_run)
    monkeypatch.setattr(service, "resume_agent", fake_resume)
    monkeypatch.setattr(service, "get_graph", object)  # no real graph is built
    calls["replies"] = replies
    return calls


def _app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=60).run()


def test_initial_page_renders(fake_service):
    at = _app()
    assert not at.exception
    assert at.title[0].value == "OpsPilot"
    assert len([b for b in at.sidebar.button if b.key.startswith("scenario_")]) == 6
    assert at.button(key="analyze").label == "Analyze"


def test_scenario_button_prefills_the_request(fake_service):
    at = _app()
    at.button(key="scenario_1").click().run()
    assert at.text_area(key="message_input").value == REFUND_TEXT


def test_refund_flow_with_approve(fake_service):
    fake_service["replies"].append(_refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING))
    at = _app()
    at.button(key="scenario_1").click().run()
    at.button(key="analyze").click().run()

    assert fake_service["run"] == [(REFUND_TEXT, [])]
    assert "Awaiting human approval" in at.warning[0].value
    assert at.text_area(key="draft_view").value.startswith("Hi Alex")  # the draft is shown, not sent

    at.button(key="approve_APR-1001").click().run()
    assert fake_service["resume"] == [("req-ui", {"APR-1001": "approve"})]
    assert "Completed" in at.success[0].value
    assert not [b for b in at.button if b.key == "approve_APR-1001"]  # decided: no more buttons


def test_refund_flow_with_reject(fake_service):
    fake_service["replies"].append(_refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING))
    at = _app()
    at.text_area(key="message_input").input(REFUND_TEXT).run()
    at.button(key="analyze").click().run()
    at.button(key="reject_APR-1001").click().run()
    assert fake_service["resume"] == [("req-ui", {"APR-1001": "reject"})]


def test_clarification_reply_is_sent_with_history(fake_service):
    question = "Could you share your order ID?"
    fake_service["replies"] += [
        AnalyzeResponse(request_id="req-1", thread_id="req-1", status=ResponseStatus.NEEDS_MORE_INFO, message=question),
        _refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING),
    ]
    at = _app()
    at.text_area(key="message_input").input("My order hasn't arrived and I want a refund.").run()
    at.button(key="analyze").click().run()

    assert [m.markdown[0].value for m in at.chat_message] == ["My order hasn't arrived and I want a refund.", question]
    assert at.button(key="analyze").label == "Send reply"

    at.text_area(key="message_input").input("It's ORD-1007.").run()
    at.button(key="analyze").click().run()
    assert fake_service["run"][1] == ("It's ORD-1007.", ["My order hasn't arrived and I want a refund."])
    assert not at.chat_message  # the exchange ended


def test_reset_clears_the_session(fake_service):
    fake_service["replies"].append(_refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING))
    at = _app()
    at.text_area(key="message_input").input(REFUND_TEXT).run()
    at.button(key="analyze").click().run()
    at.button(key="reset_demo").click().run()
    assert not at.warning
    assert at.text_area(key="message_input").value == ""
