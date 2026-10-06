"""Slack Block Kit rendering of the operations report (pure functions)."""

import json
from datetime import date

from src.common.schemas import (
    ApprovalRequest,
    ApprovalStatus,
    ExecutedAction,
    Execution,
    GuardrailDecision,
    Intent,
    OperationsReport,
    PolicyViolation,
    Risk,
    RuleId,
    Severity,
)
from src.integrations.slack_report import (
    MAX_SECTION_CHARS,
    build_report_blocks,
    decision_reply_text,
    escape,
)


def _approval(status: ApprovalStatus = ApprovalStatus.PENDING) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id="APR-1002",
        request_id="req-1",
        action="issue_refund",
        reason="Refunds always require human approval.",
        context={"order_id": "ORD-1015", "amount": 1200.0, "currency": "USD"},
        status=status,
        created_at=date(2026, 10, 10),
    )


def _report(**overrides) -> OperationsReport:
    fields = {
        "request_id": "req-75f00288",
        "severity": Severity.CRITICAL,
        "severity_reasons": ["high_value_refund"],
        "high_value": True,
        "intent": Intent.REFUND_REQUEST,
        "order_id": "ORD-1015",
        "customer_id": "CUS-111",
        "customer_name": "Emma Schmidt",
        "issue_summary": "Order ORD-1015 is delayed by 18 days; the customer requested a refund.",
        "evidence": ["Order status is delayed.", "Expected delivery date 2026-09-22 has passed; 18 days late."],
        "decisions": [
            GuardrailDecision(
                action="create_support_ticket",
                risk=Risk.LOW,
                execution=Execution.AUTOMATIC,
                rules=(RuleId.HIGH_VALUE_ORDER,),
                reason="No open ticket.",
            ),
            GuardrailDecision(
                action="issue_refund",
                risk=Risk.HIGH,
                execution=Execution.HUMAN_APPROVAL,
                rules=(RuleId.REFUND_REQUIRES_APPROVAL,),
                reason="Refunds always require human approval.",
            ),
        ],
        "executed_actions": [ExecutedAction(action="create_support_ticket", success=True, result_id="TCK-2011")],
        "approvals": [_approval()],
        "customer_response": "Hi Emma,\n\nYour refund request is being reviewed by our team.",
        "recommended_action": "Review the pending refund approval.",
        "mentions": ["U0APY0FEP62"],
    }
    return OperationsReport(**(fields | overrides))


def _text(blocks) -> str:
    return json.dumps(blocks, ensure_ascii=False)


def test_report_contains_every_section_of_the_client_sample():
    blocks, fallback = build_report_blocks(_report())
    text = _text(blocks)
    assert blocks[0]["type"] == "header"
    assert blocks[0]["text"]["text"] == "🔴 CRITICAL · Refund request · ORD-1015"
    for expected in (
        "<@U0APY0FEP62> please review",
        "CUS-111 (Emma Schmidt)",
        "high_value_refund",
        "*Issue summary*",
        "*Evidence (from operational data)*",
        "18 days late",
        "`issue_refund`: ⏸️ human approval (refund_requires_approval)",
        "`create_support_ticket` → TCK-2011",
        "APR-1002 · `issue_refund` for ORD-1015 · 1200.00 USD: ⏸️ waiting for a decision in Operation Admin",
        "*Customer response (shown to the customer)*",
        "> Your refund request is being reviewed by our team.",
        "request_id: `req-75f00288`",
    ):
        assert expected in text, expected
    assert fallback.startswith("<@U0APY0FEP62> 🔴 CRITICAL · ORD-1015")  # mentions in the notification text too


def test_no_mention_line_when_nobody_is_configured():
    blocks, fallback = build_report_blocks(_report(mentions=[]))
    assert "please review" not in _text(blocks)
    assert not fallback.startswith("<@")


def test_customer_and_llm_text_cannot_inject_mentions_or_links():
    blocks, _ = build_report_blocks(_report(issue_summary="Ping <!channel> and <https://evil.example|click>"))
    text = _text(blocks)
    assert "<!channel>" not in text
    assert "&lt;!channel&gt;" in text


def test_blocked_decisions_show_their_reason_and_fallback_drafts_are_flagged():
    duplicate = GuardrailDecision(
        action="create_support_ticket",
        risk=Risk.LOW,
        execution=Execution.BLOCKED,
        rules=(RuleId.DUPLICATE_TICKET,),
        reason="An existing support ticket already exists. Ticket: TCK-2001, Status: open",
    )
    report = _report(
        decisions=[duplicate],
        draft_policy_violations=[PolicyViolation(code="refund_promise", detail="we have refunded")],
    )
    text = _text(build_report_blocks(report)[0])
    assert "⛔ blocked (duplicate_ticket): An existing support ticket already exists. Ticket: TCK-2001" in text
    assert "replaced by a safe fallback" in text


def test_long_text_is_truncated_to_slack_limits():
    blocks, _ = build_report_blocks(_report(issue_summary="x" * 10_000))
    for block in blocks:
        if block["type"] == "section" and "text" in block:
            assert len(block["text"]["text"]) <= MAX_SECTION_CHARS


def test_decision_reply_text():
    assert decision_reply_text(_approval(ApprovalStatus.APPROVED), "RFD-0001") == (
        "✅ Refund approved: APR-1002 · `issue_refund` for ORD-1015 · 1200.00 USD · refund RFD-0001"
    )
    assert decision_reply_text(_approval(ApprovalStatus.REJECTED)).startswith("❌ Refund rejected: APR-1002")


def test_escape():
    assert escape("a & <b>") == "a &amp; &lt;b&gt;"
