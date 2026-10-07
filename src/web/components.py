"""Shared Streamlit building blocks: the cached graph, demo scenarios, and the case report view."""

from collections.abc import Callable
from typing import Any

import streamlit as st

from src.agents.service import get_graph
from src.common.schemas import AnalyzeResponse, ApprovalStatus, Execution, ResponseStatus, Severity

DEMO_SCENARIOS: list[tuple[str, str]] = [
    ("1 · Delayed order", "My order ORD-1001 is two days late. Can you check what is happening?"),
    ("2 · Refund request", "My order ORD-1007 is 15 days late. I want a refund."),
    ("3 · Existing ticket", "Please help with my delayed order ORD-1008."),
    ("4 · Unknown order", "Please check order ORD-9999."),
    ("5 · Missing order ID", "My order hasn't arrived and I want a refund."),
    ("6 · High-value refund", "My order ORD-1015 is delayed. Please refund the order."),
]

STATUS_LABEL = {
    ResponseStatus.COMPLETED: "Completed",
    ResponseStatus.AWAITING_APPROVAL: "Awaiting approval",
    ResponseStatus.NEEDS_MORE_INFO: "Needs more information",
    ResponseStatus.NOT_FOUND: "Not found",
    ResponseStatus.ERROR: "Error: no action was taken",
}
SEVERITY_EMOJI = {Severity.LOW: "🟢", Severity.MEDIUM: "🟡", Severity.HIGH: "🟠", Severity.CRITICAL: "🔴"}
_STATUS_BADGE: dict[ResponseStatus, Callable[..., Any]] = {
    ResponseStatus.COMPLETED: st.success,
    ResponseStatus.AWAITING_APPROVAL: st.warning,
    ResponseStatus.NEEDS_MORE_INFO: st.info,
    ResponseStatus.NOT_FOUND: st.error,
    ResponseStatus.ERROR: st.error,
}
_EXECUTION_LABEL = {
    Execution.AUTOMATIC: "✅ automatic",
    Execution.HUMAN_APPROVAL: "⏸️ human approval",
    Execution.BLOCKED: "⛔ blocked",
}


@st.cache_resource(show_spinner="Starting OpsPilot…")
def graph() -> Any:
    """Built once per process, so paused runs (and their checkpoints) survive reruns and page switches."""
    return get_graph()


def as_markdown(text: str) -> str:
    """Streamlit markdown treats ``$…$`` as LaTeX; escape dollar amounts like ``$249.99``."""
    return text.replace("$", "\\$")


def _render_notification(response: AnalyzeResponse) -> None:
    note = response.notification
    if note is None:
        return
    if note.delivered:
        st.caption(f"📣 Reported to Slack (channel `{note.channel}`)")
    elif note.simulated:
        st.caption("📣 Slack not configured: report logged as a simulated message")
    else:
        st.caption(f"⚠️ Slack report failed: {note.error}")


def render_report(response: AnalyzeResponse, *, on_decide: Callable[[str, str, str], None] | None = None) -> None:
    """The full case analysis (for operations). ``on_decide`` adds Approve/Reject buttons to pending refunds."""
    _STATUS_BADGE[response.status](
        f"**{STATUS_LABEL[response.status]}**" + (f": {response.message}" if response.message else "")
    )

    columns = st.columns(3)
    columns[0].metric("Severity", response.severity.value if response.severity else "-")
    columns[1].metric("Order", response.order_id or "-")
    columns[2].metric("Customer", response.customer_id or "-")
    if response.severity_reasons:
        st.caption("Severity reasons: " + ", ".join(response.severity_reasons))

    if response.issue_summary:
        st.markdown("**Issue summary**")
        st.write(response.issue_summary)
    if response.evidence:
        st.markdown("**Evidence (from operational data)**")
        st.markdown("\n".join(f"- {as_markdown(item)}" for item in response.evidence))

    if response.recommended_actions:
        st.markdown("**Recommended actions & guardrail decisions**")
        st.dataframe(
            [
                {
                    "action": d.action,
                    "risk": d.risk.value,
                    "execution": _EXECUTION_LABEL[d.execution],
                    "rules": ", ".join(d.rules) or "-",
                    "reason": d.reason,
                }
                for d in response.recommended_actions
            ],
            hide_index=True,
            width="stretch",
        )

    if response.executed_actions:
        st.markdown("**Executed actions**")
        st.dataframe(
            [
                {
                    "action": a.action,
                    "result": a.result_id or "-",
                    "status": "ok" if a.success else f"failed: {a.error}",
                }
                for a in response.executed_actions
            ],
            hide_index=True,
            width="stretch",
        )

    _render_notification(response)
    _render_approvals(response, on_decide)
    if response.customer_updates:
        st.markdown("**Message sent to the customer after the decision**")
        for update in response.customer_updates:
            st.info(as_markdown(update))

    if response.customer_response:
        st.markdown("**Customer response** (shown to the customer in the chat)")
        st.text_area(
            "Reply draft",
            response.customer_response,
            height=200,
            disabled=True,
            key=f"draft_{response.request_id}",
            label_visibility="collapsed",
        )
        if response.draft_policy_violations:
            st.warning(
                "The AI draft broke the content policy and was replaced by a safe fallback: "
                + ", ".join(f"{v.code} ({v.detail})" for v in response.draft_policy_violations)
            )

    st.caption(f"request_id: `{response.request_id}`")


def _render_approvals(response: AnalyzeResponse, on_decide: Callable[[str, str, str], None] | None) -> None:
    if not response.approvals:
        return
    st.markdown("**Human approval**")
    for approval in response.approvals:
        amount = approval.context.get("amount")
        currency = approval.context.get("currency") or ""
        st.write(
            f"**{approval.approval_id}** · `{approval.action}` for order `{approval.context.get('order_id')}`"
            + (f" · {amount:.2f} {currency}" if isinstance(amount, int | float) else "")
        )
        st.caption(approval.reason)
        if approval.status is ApprovalStatus.PENDING and on_decide is not None:
            approve, reject = st.columns(2)
            approve.button(
                "Approve",
                key=f"approve_{approval.approval_id}",
                type="primary",
                on_click=on_decide,
                args=(response.thread_id, approval.approval_id, "approve"),
                width="stretch",
            )
            reject.button(
                "Reject",
                key=f"reject_{approval.approval_id}",
                on_click=on_decide,
                args=(response.thread_id, approval.approval_id, "reject"),
                width="stretch",
            )
        else:
            st.write(f"Decision: **{approval.status.value}**")
