"""Streamlit UI flows with AppTest (no browser, no LLM). The service functions are replaced by fakes."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from src.agents import service
from src.common.schemas import (
    AnalyzeResponse,
    ApprovalRequest,
    ApprovalStatus,
    CaseRecord,
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
DRAFT = "Hi Alex,\n\nYour refund request for $249.99 is being reviewed by our team."


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
        executed_actions=[ExecutedAction(action="create_support_ticket", success=True, result_id="TCK-2009")],
        approvals=[_approval(approval_status)],
        approval_required=approval_status is ApprovalStatus.PENDING,
        customer_response=DRAFT,
    )


def _case(response: AnalyzeResponse) -> CaseRecord:
    now = datetime(2026, 10, 10, tzinfo=UTC)
    return CaseRecord(
        request_id=response.request_id,
        created_at=now,
        updated_at=now,
        customer_messages=[REFUND_TEXT],
        response=response,
    )


@pytest.fixture
def fake_service(monkeypatch) -> dict[str, Any]:
    state: dict[str, Any] = {"run": [], "resume": [], "resets": 0, "replies": [], "cases": []}

    def fake_run(message: str, history: list[str] | None = None, *, graph: Any = None) -> AnalyzeResponse:
        state["run"].append((message, list(history or [])))
        return state["replies"].pop(0)

    def fake_resume(thread_id: str, decisions: dict[str, str], *, graph: Any = None) -> AnalyzeResponse:
        state["resume"].append((thread_id, decisions))
        approved = decisions.get("APR-1001") == "approve"
        decided = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        response = _refund_response(ResponseStatus.COMPLETED, decided)
        state["cases"] = [_case(response)]
        return response

    def fake_reset() -> None:
        state["resets"] += 1
        state["cases"] = []

    monkeypatch.setattr(service, "run_agent", fake_run)
    monkeypatch.setattr(service, "resume_agent", fake_resume)
    monkeypatch.setattr(service, "list_cases", lambda: state["cases"])
    monkeypatch.setattr(
        service, "get_case", lambda request_id: next((c for c in state["cases"] if c.request_id == request_id), None)
    )
    monkeypatch.setattr(service, "reset_demo_data", fake_reset)
    monkeypatch.setattr(service, "get_graph", object)  # no real graph is built
    return state


def _app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=60).run()


def _chat_texts(at: AppTest) -> list[str]:
    return [m.markdown[0].value for m in at.chat_message]


# --- Chat page (customers) ---------------------------------------------------------------


def test_chat_is_the_default_page(fake_service):
    at = _app()
    assert not at.exception
    assert at.title[0].value == "OpsPilot Support"
    assert _chat_texts(at)[0].startswith("Hi! I'm the OpsPilot support assistant")
    assert len([b for b in at.sidebar.button if b.key.startswith("scenario_")]) == 6


def test_chat_shows_the_reply_draft_and_no_internal_details(fake_service):
    fake_service["replies"].append(_refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING))
    at = _app()
    at.chat_input(key="chat_input").set_value(REFUND_TEXT).run()

    assert fake_service["run"] == [(REFUND_TEXT, [])]
    texts = _chat_texts(at)
    assert texts[-2] == REFUND_TEXT
    assert texts[-1].startswith("Hi Alex,")
    assert "\\$249.99" in texts[-1]  # dollar amounts are escaped, not rendered as LaTeX
    rendered = " ".join(m.value for m in at.markdown)
    for internal in ("HIGH", "refund_requires_approval", "APR-1001"):
        assert internal not in rendered
    assert not any(b.key.startswith(("approve_", "reject_")) for b in at.button)
    assert not at.metric  # no severity / order metrics for customers


def test_chat_clarification_round_trip_sends_history(fake_service):
    question = "Could you share your order ID?"
    fake_service["replies"] += [
        AnalyzeResponse(request_id="req-1", thread_id="req-1", status=ResponseStatus.NEEDS_MORE_INFO, message=question),
        _refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING),
    ]
    at = _app()
    at.chat_input(key="chat_input").set_value("My order hasn't arrived and I want a refund.").run()
    assert _chat_texts(at)[-1] == question

    at.chat_input(key="chat_input").set_value("It's ORD-1007.").run()
    assert fake_service["run"][1] == ("It's ORD-1007.", ["My order hasn't arrived and I want a refund."])
    assert _chat_texts(at)[-1].startswith("Hi Alex,")


def test_scenario_button_sends_the_message(fake_service):
    fake_service["replies"].append(_refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING))
    at = _app()
    at.button(key="scenario_1").click().run()
    assert fake_service["run"] == [(REFUND_TEXT, [])]


def test_new_conversation_clears_the_chat(fake_service):
    fake_service["replies"].append(_refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING))
    at = _app()
    at.chat_input(key="chat_input").set_value(REFUND_TEXT).run()
    at.button(key="new_conversation").click().run()
    assert len(at.chat_message) == 1  # only the greeting


# --- Operation Admin page (operations) -----------------------------------------------------


def _admin(fake_service, *cases: CaseRecord) -> AppTest:
    fake_service["cases"] = list(cases)
    return _app().switch_page("views/admin.py").run()


def test_admin_shows_empty_state(fake_service):
    at = _admin(fake_service)
    assert not at.exception
    assert at.title[0].value == "Operation Admin"
    assert "No cases yet" in at.info[0].value


def test_admin_lists_pending_case_and_approves(fake_service):
    at = _admin(fake_service, _case(_refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING)))
    assert at.metric[0].value == "1"  # waiting for approval
    assert "ORD-1007" in at.expander[0].label
    assert "Awaiting approval" in at.expander[0].label

    at.button(key="approve_APR-1001").click().run()
    assert fake_service["resume"] == [("req-ui", {"APR-1001": "approve"})]
    assert at.metric[0].value == "0"
    assert not any(b.key == "approve_APR-1001" for b in at.button)  # decided: no more buttons


def test_admin_rejects(fake_service):
    at = _admin(fake_service, _case(_refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING)))
    at.button(key="reject_APR-1001").click().run()
    assert fake_service["resume"] == [("req-ui", {"APR-1001": "reject"})]


def test_admin_reset_demo_data(fake_service):
    at = _admin(fake_service, _case(_refund_response(ResponseStatus.COMPLETED, ApprovalStatus.APPROVED)))
    at.button(key="reset_demo").click().run()
    assert fake_service["resets"] == 1
    assert "No cases yet" in at.info[0].value


def test_chat_posts_the_refund_decision_once_it_is_made(fake_service):
    fake_service["replies"].append(_refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING))
    fake_service["cases"] = [_case(_refund_response(ResponseStatus.AWAITING_APPROVAL, ApprovalStatus.PENDING))]
    at = _app()
    at.chat_input(key="chat_input").set_value(REFUND_TEXT).run()  # run_agent saves the case before returning
    at.run()
    assert len(at.chat_message) == 3  # greeting, customer, draft: no decision yet

    decided = _refund_response(ResponseStatus.COMPLETED, ApprovalStatus.APPROVED).model_copy(
        update={"customer_updates": ["Hi Alex, good news: our team has approved your refund of 249.99 USD."]}
    )
    fake_service["cases"] = [_case(decided)]
    at.run()  # what the 3-second poll does
    assert _chat_texts(at)[-1].startswith("Hi Alex, good news")
    at.run()
    assert len(at.chat_message) == 4  # posted exactly once


def test_admin_shows_the_message_sent_to_the_customer(fake_service):
    decided = _refund_response(ResponseStatus.COMPLETED, ApprovalStatus.APPROVED).model_copy(
        update={"customer_updates": ["Hi Alex, good news: our team has approved your refund of 249.99 USD."]}
    )
    at = _admin(fake_service, _case(decided))
    at.expander[0]  # recent case
    assert any("good news" in info.value for info in at.info)
