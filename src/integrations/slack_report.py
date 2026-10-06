"""Render an ``OperationsReport`` as a Slack Block Kit message. Pure functions: no I/O.

Text from customers or the LLM is escaped (``& < >``) so it can never inject Slack mentions or links.
"""

from typing import Any

from src.common.schemas import ApprovalRequest, ApprovalStatus, Execution, OperationsReport, Severity

SEVERITY_EMOJI = {Severity.LOW: "🟢", Severity.MEDIUM: "🟡", Severity.HIGH: "🟠", Severity.CRITICAL: "🔴"}
EXECUTION_LABEL = {
    Execution.AUTOMATIC: "✅ automatic",
    Execution.HUMAN_APPROVAL: "⏸️ human approval",
    Execution.BLOCKED: "⛔ blocked",
}
APPROVAL_LABEL = {
    ApprovalStatus.PENDING: "⏸️ waiting for a decision in Operation Admin",
    ApprovalStatus.APPROVED: "✅ approved",
    ApprovalStatus.REJECTED: "❌ rejected",
}
MAX_HEADER_CHARS = 150  # Slack limit for plain-text headers
MAX_SECTION_CHARS = 2900  # Slack limit is 3000 per section text
MAX_FIELD_CHARS = 1900  # Slack limit is 2000 per field


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _section(markdown: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": truncate(markdown, MAX_SECTION_CHARS)}}


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"• {line}" for line in lines)


def _approval_line(approval: ApprovalRequest) -> str:
    amount = approval.context.get("amount")
    currency = approval.context.get("currency") or ""
    money = f" · {amount:.2f} {currency}".rstrip() if isinstance(amount, int | float) else ""
    order = approval.context.get("order_id")
    return f"{approval.approval_id} · `{approval.action}`" + (f" for {order}" if order else "") + money


def mention_line(mentions: list[str]) -> str:
    return " ".join(f"<@{user_id}>" for user_id in mentions)


def build_report_blocks(report: OperationsReport) -> tuple[list[dict[str, Any]], str]:
    """Return ``(blocks, fallback_text)``. The fallback text is used in notifications and old clients."""
    emoji = SEVERITY_EMOJI[report.severity]
    topic = report.intent.value.replace("_", " ").capitalize() if report.intent else "Customer request"
    subject = report.order_id or report.customer_id or "unknown order"
    header = truncate(f"{emoji} {report.severity.value} · {topic} · {subject}", MAX_HEADER_CHARS)
    mentions = mention_line(report.mentions)

    customer = report.customer_id or "-"
    if report.customer_name:
        customer += f" ({escape(report.customer_name)})"
    fields = [
        f"*Order*\n{report.order_id or '-'}",
        f"*Customer*\n{customer}",
        f"*Severity reasons*\n{escape(', '.join(report.severity_reasons) or '-')}",
        f"*Next step*\n{escape(report.recommended_action)}",
    ]
    if report.high_value:
        fields.append("*High-value order*\nPriority escalated to critical")

    blocks: list[dict[str, Any]] = [{"type": "header", "text": {"type": "plain_text", "text": header, "emoji": True}}]
    if mentions:
        blocks.append(_section(f"{mentions} please review"))
    blocks.append(
        {"type": "section", "fields": [{"type": "mrkdwn", "text": truncate(f, MAX_FIELD_CHARS)} for f in fields]}
    )
    blocks.append(_section(f"*Issue summary*\n{escape(report.issue_summary)}"))
    if report.evidence:
        blocks.append(_section("*Evidence (from operational data)*\n" + _bullets([escape(e) for e in report.evidence])))
    if report.decisions:
        lines = []
        for decision in report.decisions:
            line = f"`{decision.action}`: {EXECUTION_LABEL[decision.execution]}"
            if decision.rules:
                line += f" ({', '.join(decision.rules)})"
            if decision.execution is Execution.BLOCKED:
                line += f": {escape(decision.reason)}"
            lines.append(line)
        blocks.append(_section("*Recommended actions & guardrail decisions*\n" + _bullets(lines)))
    if report.executed_actions:
        lines = [
            f"`{a.action}` → {a.result_id or '-'}" if a.success else f"`{a.action}` → failed ({escape(a.error or '?')})"
            for a in report.executed_actions
        ]
        blocks.append(_section("*Executed actions*\n" + _bullets(lines)))
    if report.approvals:
        lines = [f"{_approval_line(a)}: {APPROVAL_LABEL[a.status]}" for a in report.approvals]
        blocks.append(_section("*Human approval*\n" + _bullets(lines)))
    if report.customer_response:
        lines_out = report.customer_response.splitlines()
        quoted = "\n".join(f"> {escape(line)}" if line.strip() else ">" for line in lines_out)
        note = ""
        if report.draft_policy_violations:
            codes = ", ".join(v.code for v in report.draft_policy_violations)
            note = f"\n_The AI draft broke the content policy ({codes}) and was replaced by a safe fallback._"
        blocks.append(_section(f"*Customer response (shown to the customer)*\n{quoted}{note}"))
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"request_id: `{report.request_id}`"}]})

    fallback = f"{mentions} " if mentions else ""
    fallback += f"{emoji} {report.severity.value} · {subject}: {escape(report.issue_summary)}"
    return blocks, truncate(fallback, MAX_SECTION_CHARS)


def decision_reply_text(approval: ApprovalRequest, refund_id: str | None = None) -> str:
    """Thread reply posted when an admin decides a refund."""
    line = _approval_line(approval)
    if approval.status is ApprovalStatus.APPROVED:
        return f"✅ Refund approved: {line}" + (f" · refund {refund_id}" if refund_id else "")
    return f"❌ Refund rejected: {line}. No refund was issued."
