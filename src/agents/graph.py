"""The outer LangGraph pipeline (spec §9.2).

    validate_input → investigate → guardrails → execute_actions → human_approval → respond
       (code)       (LLM agent)     (code)          (code)          (interrupt)      (code)

Early exits go straight to ``respond``: invalid input, invalid LLM output, or a guardrail stop rule
(missing information, not found, unverified ID).
"""

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.investigator import DEFAULT_MODEL_CALL_LIMIT, DEFAULT_TOOL_CALL_LIMIT, build_investigator
from src.agents.nodes import OpsNodes
from src.agents.state import OpsState


def build_graph(
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver,  # type: ignore[type-arg]
    *,
    high_value_threshold: float,
    model_call_limit: int = DEFAULT_MODEL_CALL_LIMIT,
    tool_call_limit: int = DEFAULT_TOOL_CALL_LIMIT,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    investigator = build_investigator(model, model_call_limit=model_call_limit, tool_call_limit=tool_call_limit)
    nodes = OpsNodes(investigator, high_value_threshold=high_value_threshold)

    graph = StateGraph(OpsState)
    graph.add_node("validate_input", nodes.validate_input)
    graph.add_node("investigate", nodes.investigate)
    graph.add_node("guardrails", nodes.guardrails)
    graph.add_node("execute_actions", nodes.execute_actions)
    graph.add_node("human_approval", nodes.human_approval)
    graph.add_node("respond", nodes.respond)

    graph.add_edge(START, "validate_input")
    graph.add_conditional_edges("validate_input", nodes.route_after_validation, ["investigate", "respond"])
    graph.add_conditional_edges("investigate", nodes.route_after_investigate, ["guardrails", "respond"])
    graph.add_conditional_edges("guardrails", nodes.route_after_guardrails, ["execute_actions", "respond"])
    graph.add_edge("execute_actions", "human_approval")
    graph.add_edge("human_approval", "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer, name="opspilot")
