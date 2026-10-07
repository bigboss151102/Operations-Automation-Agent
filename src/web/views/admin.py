"""Operation Admin (decision D8): review every case and approve or reject refunds.

Cases come from the shared case store, so conversations from any Chat tab appear here. Decisions
resume the paused run; the outcome is also replied in the case's Slack thread. The Tickets tab lists the
sample tickets plus the (simulated) tickets the agent created in this session.
"""

import streamlit as st

from src.agents.service import created_ticket_ids, list_cases, list_tickets, reset_demo_data, resume_agent
from src.common.schemas import CaseRecord
from src.web.components import SEVERITY_EMOJI, STATUS_LABEL, as_markdown, graph, render_report


def _decide(thread_id: str, approval_id: str, decision: str) -> None:
    resume_agent(thread_id, {approval_id: decision}, graph=graph())


def _label(case: CaseRecord) -> str:
    response = case.response
    severity = response.severity
    badge = f"{SEVERITY_EMOJI[severity]} {severity.value}" if severity else "⚪ -"
    subject = response.order_id or response.customer_id or "no order"
    return f"{badge} · {subject} · {STATUS_LABEL[response.status]} · {response.request_id}"


def _render_tickets() -> None:
    tickets = list_tickets()
    created = created_ticket_ids()
    st.caption(
        "Sample tickets from `data/` plus tickets the agent created in this session (🆕). Created tickets are "
        "simulated: they live in memory and are cleared by Reset demo data. Duplicate detection (rule R4) sees both."
    )
    filters = st.columns([3, 1])
    statuses = sorted({t.status.value for t in tickets})
    chosen = filters[0].multiselect("Status", statuses, default=statuses, key="ticket_status")
    only_new = filters[1].checkbox("Only created this session", key="ticket_only_new")
    rows = [
        {
            "ticket": f"🆕 {t.ticket_id}" if t.ticket_id in created else t.ticket_id,
            "status": t.status.value,
            "priority": t.priority.value,
            "issue": t.issue_type.value,
            "order": t.order_id or "-",
            "customer": t.customer_id,
            "created": t.created_at.isoformat(),
            "summary": t.summary or "-",
        }
        for t in tickets
        if t.status.value in chosen and (not only_new or t.ticket_id in created)
    ]
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info("No tickets match the filters.")


def _render_case(case: CaseRecord) -> None:
    if case.customer_messages:
        st.markdown("**Customer messages**")
        for message in case.customer_messages:
            st.markdown(f"> {as_markdown(message)}")
    render_report(case.response, on_decide=_decide)


st.title("Operation Admin")
st.caption("Every customer case with its full analysis. Refunds wait here for a human decision.")

cases = list_cases()
pending = [c for c in cases if c.response.approval_required]
others = [c for c in cases if not c.response.approval_required]

metrics = st.columns(4)
metrics[0].metric("Waiting for approval", len(pending))
metrics[1].metric("Total cases", len(cases))
metrics[2].metric("Tickets created", len(created_ticket_ids()))
with metrics[3]:
    st.button("Reset demo data", key="reset_demo", on_click=reset_demo_data, width="stretch")

cases_tab, tickets_tab = st.tabs(["Cases", "Tickets"])
with cases_tab:
    if not cases:
        st.info("No cases yet. Start a conversation on the Chat page.")

    if pending:
        st.subheader("Waiting for approval")
        for case in pending:
            with st.expander(_label(case), expanded=True):
                _render_case(case)

    if others:
        st.subheader("Recent cases")
        for case in others:
            with st.expander(_label(case)):
                _render_case(case)

with tickets_tab:
    _render_tickets()
