"""Investigation-time guardrail middleware (spec §12.7, layer 1). Deterministic: no LLM calls.

Only the middleware base class is imported from LangChain, never a chat model.
"""

import json
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from src.common.schemas import RuleId
from src.utils.ids import is_entity_id, verified_ids_from
from src.utils.logging import get_logger, log_event

_log = get_logger("guardrails.middleware")


class VerifiedIdMiddleware(AgentMiddleware):
    """Rule 7, layer 1: a tool may only look up IDs the customer wrote or an earlier tool result returned.

    For any other ID, the tool never runs: the model receives a structured ``UNVERIFIED_ID`` error
    instead, so a guessed order can never be fetched (spec Scenario 5).
    """

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        allowed = verified_ids_from(request.state["messages"])
        requested = {v for v in request.tool_call["args"].values() if isinstance(v, str) and is_entity_id(v)}
        unverified = sorted(requested - allowed)
        if not unverified:
            return handler(request)

        log_event(
            "guardrail_decision",
            rule=RuleId.UNVERIFIED_ID,
            tool=request.tool_call["name"],
            ids=",".join(unverified),
            logger=_log,
        )
        content = {
            "success": False,
            "error": "UNVERIFIED_ID",
            "message": f"{', '.join(unverified)} did not appear in the customer's messages or in any tool result. "
            "Do not guess IDs; ask the customer instead.",
        }
        return ToolMessage(
            content=json.dumps(content),
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
            status="error",
        )
