"""The single entry point used by Streamlit and FastAPI. Neither embeds graph logic.

- ``run_agent(message, history)`` starts a request. It returns ``status="awaiting_approval"`` when a
  refund is waiting for a human decision.
- ``resume_agent(thread_id, decisions)`` records those decisions and finishes the run.
- ``list_cases`` / ``pending_cases`` / ``list_tickets`` / ``reset_demo_data`` serve the Operation Admin page;
  ``get_case`` lets the chat page pick up refund decisions for its customer.

Every result is saved in the case store, so the admin page sees cases created from the chat.

The service is stateless per turn: for a clarification follow-up (decision D5) the client re-sends the
earlier customer messages as ``history``.
"""

import logging
import time
from functools import cache
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from src.agents.graph import build_graph
from src.agents.investigator import PROMPT_VERSIONS
from src.agents.responder import build_response, error_response
from src.common.schemas import AnalyzeResponse, CaseRecord, SupportTicket
from src.config.settings import get_settings
from src.llm.client import get_chat_model
from src.memory.checkpointer import get_checkpointer
from src.repositories.action_store import get_action_store
from src.repositories.case_store import get_case_store
from src.repositories.tickets import find_tickets
from src.utils.logging import get_logger, log_event, set_request_id

RECURSION_LIMIT = 25

_log = get_logger("service")


@cache
def get_graph() -> CompiledStateGraph:  # type: ignore[type-arg]
    settings = get_settings()
    return build_graph(get_chat_model(settings), get_checkpointer(), high_value_threshold=settings.high_value_threshold)


def _config(request_id: str) -> RunnableConfig:
    return {
        "configurable": {"thread_id": request_id},
        "recursion_limit": RECURSION_LIMIT,
        "run_name": "opspilot",
        "tags": ["opspilot", get_settings().env],
        "metadata": {"request_id": request_id, "prompt_versions": PROMPT_VERSIONS},
    }


def _to_response(graph: CompiledStateGraph, result: dict[str, Any], config: RunnableConfig) -> AnalyzeResponse:  # type: ignore[type-arg]
    if result.get("__interrupt__"):  # paused in human_approval: the respond node has not run yet
        return build_response(graph.get_state(config).values)
    response: AnalyzeResponse = result["response"]
    return response


def _finish(response: AnalyzeResponse, started: float) -> AnalyzeResponse:
    log_event(
        "request_completed",
        status=response.status,
        severity=response.severity,
        duration_ms=round((time.perf_counter() - started) * 1000),
        logger=_log,
    )
    return response


def run_agent(
    message: str,
    history: list[str] | None = None,
    *,
    graph: CompiledStateGraph | None = None,  # type: ignore[type-arg]
) -> AnalyzeResponse:
    started = time.perf_counter()
    request_id = f"req-{uuid4().hex[:8]}"
    set_request_id(request_id)
    graph = graph or get_graph()
    config = _config(request_id)
    try:
        result = graph.invoke({"request_id": request_id, "message": message, "history": history or []}, config)
        response = _to_response(graph, result, config)
    except Exception:
        # OpenAI/network failures, recursion limit, bugs: fail safe. Actions run only in deterministic
        # nodes after guardrails, so a failure before them means nothing was executed.
        _log.exception("request_failed")
        response = error_response(request_id)
    get_case_store().save(response, customer_messages=[*(history or []), message])
    return _finish(response, started)


def resume_agent(
    thread_id: str,
    decisions: dict[str, str],
    *,
    graph: CompiledStateGraph | None = None,  # type: ignore[type-arg]
) -> AnalyzeResponse:
    """Resume a paused run with ``{approval_id: "approve" | "reject"}``; missing decisions count as reject."""
    started = time.perf_counter()
    set_request_id(thread_id)
    graph = graph or get_graph()
    config = _config(thread_id)
    try:
        if not graph.get_state(config).next:
            log_event("resume_rejected", reason="no_pending_approval", level=logging.WARNING, logger=_log)
            return _finish(error_response(thread_id, "no_pending_approval"), started)
        # Always wrap: LangGraph reads a dict whose keys all look like interrupt IDs (including an empty
        # dict) as a per-interrupt resume map, which would leave the run paused.
        result = graph.invoke(Command(resume={"decisions": decisions}), config)
        response = _to_response(graph, result, config)
    except Exception:
        _log.exception("resume_failed")
        return _finish(error_response(thread_id), started)
    get_case_store().save(response)  # keeps the customer messages recorded by run_agent
    return _finish(response, started)


# --- read side for the Operation Admin page (decision D8) ---------------------------------


def list_cases() -> list[CaseRecord]:
    """All cases, most recently updated first."""
    return get_case_store().all()


def get_case(request_id: str) -> CaseRecord | None:
    """One case by request ID (the chat page polls it for refund decisions)."""
    return get_case_store().get(request_id)


def pending_cases() -> list[CaseRecord]:
    """Cases with a refund waiting for a human decision."""
    return [case for case in get_case_store().all() if case.response.approval_required]


def list_tickets() -> list[SupportTicket]:
    """Sample tickets plus tickets created in this session, newest first."""
    return sorted(find_tickets(), key=lambda t: (t.created_at, t.ticket_id), reverse=True)


def created_ticket_ids() -> set[str]:
    """IDs of tickets the agent created in this session (simulated; gone after a reset or restart)."""
    return {t.ticket_id for t in get_action_store().tickets}


def reset_demo_data() -> None:
    """Forget created tickets, approvals, refunds, and cases (sample data in data/ is untouched)."""
    get_action_store().reset()
    get_case_store().reset()
