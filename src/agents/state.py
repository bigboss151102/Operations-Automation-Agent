from typing import TypedDict

from src.common.schemas import (
    AgentProposal,
    AnalyzeResponse,
    ApprovalRequest,
    ExecutedAction,
    GuardrailResult,
    PolicyViolation,
)


class OpsState(TypedDict, total=False):
    """State of one request through the outer graph. Nodes return partial updates; they never mutate it."""

    request_id: str
    message: str  # the latest customer message
    history: list[str]  # earlier customer messages of a clarification exchange (D5)
    extracted_ids: list[str]  # IDs the customer wrote (regex, validate_input)
    proposal: AgentProposal | None  # LLM recommendation (investigate)
    verified_ids: list[str]  # customer-written IDs + IDs returned by read tools (investigate)
    guardrails: GuardrailResult | None  # deterministic decisions (guardrails)
    executed_actions: list[ExecutedAction]  # appended by execute_actions and human_approval
    customer_response: str | None  # final reply draft after the R8 check
    draft_violations: list[PolicyViolation]
    approvals: list[ApprovalRequest]  # decided approvals (human_approval)
    error: str | None  # invalid_input | invalid_llm_output
    response: AnalyzeResponse  # final output (respond)
