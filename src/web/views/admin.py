"""Operation Admin (decision D8): review every case and approve or reject refunds.

Cases come from the shared case store, so conversations from any Chat tab appear here. Decisions
resume the paused run; the outcome is also replied in the case's Slack thread.
"""

import streamlit as st

from src.agents.service import list_cases, reset_demo_data, resume_agent
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

metrics = st.columns(3)
metrics[0].metric("Waiting for approval", len(pending))
metrics[1].metric("Total cases", len(cases))
with metrics[2]:
    st.button("Reset demo data", key="reset_demo", on_click=reset_demo_data, width="stretch")

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
