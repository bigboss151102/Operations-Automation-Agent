"""Customer chat (decision D6): a conversational front end over the agent.

The customer sees only conversational replies: the clarification question when information is missing,
the not-found / error message, or the R8-checked reply draft. Severity, rules, and approvals stay on the
Operation Admin page and in Slack.
"""

import streamlit as st

from src.agents.service import run_agent
from src.common.schemas import AnalyzeResponse, ResponseStatus
from src.web.components import DEMO_SCENARIOS, as_markdown, graph

GREETING = "Hi! I'm the OpsPilot support assistant. Tell me what's going on with your order and I'll look into it."
FALLBACK_REPLY = "Thanks for reaching out. Our team is looking into your request and will get back to you shortly."


def _init_state() -> None:
    st.session_state.setdefault("chat_messages", [{"role": "assistant", "content": GREETING}])
    st.session_state.setdefault("chat_history", [])  # customer messages of an open clarification (D5)
    st.session_state.setdefault("chat_queued", None)


def _queue(text: str) -> None:
    st.session_state.chat_queued = text


def _new_conversation() -> None:
    st.session_state.chat_messages = [{"role": "assistant", "content": GREETING}]
    st.session_state.chat_history = []


def reply_for(response: AnalyzeResponse) -> str:
    if response.status in (ResponseStatus.NEEDS_MORE_INFO, ResponseStatus.NOT_FOUND, ResponseStatus.ERROR):
        return response.message or FALLBACK_REPLY
    return response.customer_response or FALLBACK_REPLY


def _handle(message: str) -> None:
    history = list(st.session_state.chat_history)
    st.session_state.chat_messages.append({"role": "user", "content": message})
    with st.spinner("Looking into it…"):
        response = run_agent(message, history, graph=graph())
    st.session_state.chat_messages.append({"role": "assistant", "content": reply_for(response)})
    # Keep the context only while the assistant is waiting for missing information.
    st.session_state.chat_history = [*history, message] if response.status is ResponseStatus.NEEDS_MORE_INFO else []


_init_state()
with st.sidebar:
    st.subheader("Try a scenario")
    for index, (label, text) in enumerate(DEMO_SCENARIOS):
        st.button(label, key=f"scenario_{index}", on_click=_queue, args=(text,), width="stretch")
    st.divider()
    st.button("New conversation", key="new_conversation", on_click=_new_conversation, width="stretch")

st.title("OpsPilot Support")
st.caption("Ask about a delayed, missing, or cancelled order, a refund, or your subscription.")

prompt = st.chat_input("Describe your issue…", key="chat_input")
queued = st.session_state.chat_queued
st.session_state.chat_queued = None
if message := (prompt or queued or "").strip():
    _handle(message)

for entry in st.session_state.chat_messages:
    with st.chat_message(entry["role"]):
        st.markdown(as_markdown(entry["content"]))
