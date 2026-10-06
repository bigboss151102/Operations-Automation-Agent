"""The investigate step: the only place the LLM runs (spec §9.2).

A LangChain ``create_agent`` that may call only read-only tools and must return an ``AgentProposal``.
Deterministic middleware guards the loop (spec §12.7, layer 1).
"""

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    PIIMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph

from src.common.schemas import AgentProposal
from src.guardrails.middleware import VerifiedIdMiddleware
from src.prompts.loader import load_prompt
from src.tools.registry import READ_TOOLS

DEFAULT_MODEL_CALL_LIMIT = 8
DEFAULT_TOOL_CALL_LIMIT = 10

_SYSTEM = load_prompt("ops_agent_system")
_EXAMPLE = load_prompt("customer_response_example")
SYSTEM_PROMPT_TEXT = _SYSTEM.render(customer_response_example=_EXAMPLE.text)
PROMPT_VERSIONS = {_SYSTEM.name: _SYSTEM.version, _EXAMPLE.name: _EXAMPLE.version}  # LangSmith metadata


def build_investigator(
    model: BaseChatModel,
    *,
    model_call_limit: int = DEFAULT_MODEL_CALL_LIMIT,
    tool_call_limit: int = DEFAULT_TOOL_CALL_LIMIT,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Build the investigator agent. ``result["structured_response"]`` holds the ``AgentProposal``.

    If the model never produces a valid proposal within the call limit, ``structured_response`` is
    absent and the caller must treat the run as failed (no action may run).
    """
    middleware: list[AgentMiddleware[Any, Any, Any]] = [
        VerifiedIdMiddleware(),  # Rule 7: block lookups of IDs nobody wrote
        PIIMiddleware("email", strategy="redact", apply_to_input=False, apply_to_tool_results=True),
        ModelCallLimitMiddleware(run_limit=model_call_limit, exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=tool_call_limit),
    ]
    return create_agent(
        model=model,
        tools=READ_TOOLS,  # never ACTION_TOOLS: the LLM cannot perform actions
        system_prompt=SYSTEM_PROMPT_TEXT,
        response_format=ToolStrategy(AgentProposal),
        middleware=middleware,
        name="investigator",
    )
