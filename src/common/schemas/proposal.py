"""The LLM's structured output. It recommends; it never decides severity, risk, or approval."""

from pydantic import Field

from src.common.schemas._base import Record
from src.common.schemas.enums import ActionName, Intent, IssueType, RequestedAction


class ProposedAction(Record):
    action: ActionName = Field(description="One action from the catalogue.")
    reason: str = Field(description="Why this action helps, citing facts from tool results.")


class AgentProposal(Record):
    """Investigation result. Guardrails re-check every fact against the data before anything runs."""

    intent: Intent = Field(description="What the customer wants.")
    issue_type: IssueType = Field(description="The operational issue category.")
    requested_action: RequestedAction = Field(description="What the customer explicitly asked for.")
    order_id: str | None = Field(
        default=None, description="Order ID the customer wrote, or null. Never invent or guess one."
    )
    customer_id: str | None = Field(
        default=None, description="Customer ID the customer wrote or a tool returned, or null."
    )
    issue_summary: str = Field(description="One or two sentences describing the issue, based on tool results.")
    evidence: list[str] = Field(
        default_factory=list,
        description="Facts from tool results that support the summary. Not the customer's own claims.",
    )
    proposed_actions: list[ProposedAction] = Field(
        default_factory=list, description="Recommended actions. Empty when information is missing or nothing is found."
    )
    missing_fields: list[str] = Field(
        default_factory=list, description='Information needed but not provided, e.g. ["order_id"]. Empty if none.'
    )
    clarification_question: str | None = Field(
        default=None,
        description="Required when missing_fields is non-empty: a short, polite question asking for exactly that.",
    )
    customer_response_draft: str | None = Field(
        default=None,
        description="Draft reply to the customer following the example template. Null when information is missing.",
    )
