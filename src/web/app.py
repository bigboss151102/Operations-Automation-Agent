"""OpsPilot demo UI (spec §18.1): ``uv run python -m streamlit run src/web/app.py`` from the repo root.

A thin adapter over ``src.agents.service``: it renders the response and forwards human decisions.
All widget changes go through ``on_click`` callbacks, so session state is updated before the rerun.
"""

from typing import Any

import streamlit as st

from src.agents.service import get_graph, resume_agent, run_agent
from src.common.schemas import AnalyzeResponse, ApprovalStatus, Execution, ResponseStatus
from src.config.settings import get_settings
from src.repositories.action_store import get_action_store
from src.utils.logging import configure_logging

DEMO_SCENARIOS: list[tuple[str, str]] = [
    ("1 · Delayed order", "My order ORD-1001 is two days late. Can you check what is happening?"),
    ("2 · Refund request", "My order ORD-1007 is 15 days late. I want a refund."),
    ("3 · Existing ticket", "Please help with my delayed order ORD-1008."),
    ("4 · Unknown order", "Please check order ORD-9999."),
    ("5 · Missing order ID", "My order hasn't arrived and I want a refund."),
    ("6 · High-value refund", "My order ORD-1015 is delayed. Please refund the order."),
]

_STATUS_BADGE = {
    ResponseStatus.COMPLETED: (st.success, "Completed"),
    ResponseStatus.AWAITING_APPROVAL: (st.warning, "Awaiting human approval"),
    ResponseStatus.NEEDS_MORE_INFO: (st.info, "Needs more information"),
    ResponseStatus.NOT_FOUND: (st.error, "Not found"),
    ResponseStatus.ERROR: (st.error, "Error: no action was taken"),
}
_EXECUTION_LABEL = {
    Execution.AUTOMATIC: "✅ automatic",
    Execution.HUMAN_APPROVAL: "⏸️ human approval",
    Execution.BLOCKED: "⛔ blocked",
}


@st.cache_resource(show_spinner="Starting OpsPilot…")
def _graph() -> Any:
    """Built once per process, so paused runs (and their checkpoints) survive Streamlit reruns."""
    return get_graph()


def _init_state() -> None:
    defaults: dict[str, Any] = {"message_input": "", "history": [], "chat": [], "response": None}
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


# --- callbacks ------------------------------------------------------------------------------


def _use_scenario(text: str) -> None:
    st.session_state.message_input = text
    st.session_state.history, st.session_state.chat, st.session_state.response = [], [], None


def _reset_demo() -> None:
    get_action_store().reset()
    st.session_state.message_input = ""
    st.session_state.history, st.session_state.chat, st.session_state.response = [], [], None


def _analyze() -> None:
    message = st.session_state.message_input.strip()
    if not message:
        return
    history = list(st.session_state.history)
    response = run_agent(message, history, graph=_graph())
    st.session_state.response = response
    if response.status is ResponseStatus.NEEDS_MORE_INFO:
        # Keep the conversation: the reply is sent together with the earlier messages (decision D5).
        st.session_state.history = [*history, message]
        st.session_state.chat = [*st.session_state.chat, ("user", message), ("assistant", response.message or "")]
    else:
        st.session_state.history, st.session_state.chat = [], []
    st.session_state.message_input = ""


def _decide(thread_id: str, approval_id: str, decision: str) -> None:
    st.session_state.response = resume_agent(thread_id, {approval_id: decision}, graph=_graph())


# --- rendering ------------------------------------------------------------------------------


def _render_sidebar() -> None:
    with st.sidebar:
        st.header("Demo scenarios")
        for index, (label, text) in enumerate(DEMO_SCENARIOS):
            st.button(label, key=f"scenario_{index}", on_click=_use_scenario, args=(text,), width="stretch")
        st.divider()
        st.button("Reset demo data", key="reset_demo", on_click=_reset_demo, width="stretch")
        st.caption(f"Model: `{get_settings().openai_model}` · Today: `{get_settings().reference_date or 'real date'}`")


def _render_conversation() -> None:
    for role, text in st.session_state.chat:
        with st.chat_message(role):
            st.write(text)


def _render_response(response: AnalyzeResponse) -> None:
    badge, label = _STATUS_BADGE[response.status]
    badge(f"**{label}**" + (f": {response.message}" if response.message else ""))

    columns = st.columns(3)
    columns[0].metric("Severity", response.severity.value if response.severity else "-")
    columns[1].metric("Order", response.order_id or "-")
    columns[2].metric("Customer", response.customer_id or "-")
    if response.severity_reasons:
        st.caption("Severity reasons: " + ", ".join(response.severity_reasons))

    if response.issue_summary:
        st.subheader("Issue summary")
        st.write(response.issue_summary)
    if response.evidence:
        st.subheader("Evidence (from operational data)")
        st.markdown("\n".join(f"- {item}" for item in response.evidence))

    if response.recommended_actions:
        st.subheader("Recommended actions & guardrail decisions")
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
        st.subheader("Executed actions (simulated)")
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

    _render_approvals(response)

    if response.customer_response:
        st.subheader("Customer response")
        st.caption("Draft: not sent. A person reviews and sends it.")
        st.text_area("Draft (not sent)", response.customer_response, height=220, disabled=True, key="draft_view")
        if response.draft_policy_violations:
            st.warning(
                "The AI draft broke the content policy and was replaced by a safe fallback: "
                + ", ".join(f"{v.code} ({v.detail})" for v in response.draft_policy_violations)
            )

    st.caption(f"request_id: `{response.request_id}`")


def _render_approvals(response: AnalyzeResponse) -> None:
    if not response.approvals:
        return
    st.subheader("Human approval")
    for approval in response.approvals:
        amount = approval.context.get("amount")
        currency = approval.context.get("currency") or ""
        st.write(
            f"**{approval.approval_id}** · `{approval.action}` for order `{approval.context.get('order_id')}`"
            + (f" · {amount:.2f} {currency}" if isinstance(amount, int | float) else "")
        )
        st.caption(approval.reason)
        if approval.status is ApprovalStatus.PENDING:
            approve, reject = st.columns(2)
            approve.button(
                "Approve",
                key=f"approve_{approval.approval_id}",
                type="primary",
                on_click=_decide,
                args=(response.thread_id, approval.approval_id, "approve"),
                width="stretch",
            )
            reject.button(
                "Reject",
                key=f"reject_{approval.approval_id}",
                on_click=_decide,
                args=(response.thread_id, approval.approval_id, "reject"),
                width="stretch",
            )
        else:
            st.write(f"Decision: **{approval.status.value}**")


def main() -> None:
    configure_logging(get_settings().log_level)
    st.set_page_config(page_title="OpsPilot", page_icon="🛠️", layout="wide")
    _init_state()
    _graph()

    st.title("OpsPilot")
    st.caption(
        "AI operations agent: it investigates the request with read-only tools, deterministic guardrails decide "
        "what may happen, safe actions run automatically, and refunds wait for a human. Nothing is sent to customers."
    )
    _render_sidebar()
    _render_conversation()

    replying = bool(st.session_state.history)
    st.text_area(
        "Your reply" if replying else "Customer request",
        key="message_input",
        height=100,
        placeholder="Answer the question above…"
        if replying
        else "e.g. My order ORD-1007 is 15 days late. I want a refund.",
    )
    st.button("Send reply" if replying else "Analyze", key="analyze", type="primary", on_click=_analyze)

    response = st.session_state.response
    if response is not None:
        st.divider()
        _render_response(response)


main()
