"""The LLM's structured output. It recommends; it never decides severity, risk, or approval.

Every field is required (nullable fields must be sent as an explicit ``null``, lists as ``[]``).
Models tend to skip optional fields; a required field makes the model decide about it every time.
"""

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
    order_id: str | None = Field(description="Order ID the customer wrote, or null. Never invent or guess one.")
    customer_id: str | None = Field(description="Customer ID the customer wrote or a tool returned, or null.")
    issue_summary: str = Field(description="One or two sentences describing the issue, based on tool results.")
    evidence: list[str] = Field(
        description="Facts from tool results that support the summary. Not the customer's own claims. [] if none."
    )
    proposed_actions: list[ProposedAction] = Field(
        description="Recommended actions. [] when information is missing or the record was not found."
    )
    missing_fields: list[str] = Field(
        description='Information needed but not provided, e.g. ["order_id"]. [] if nothing is missing.'
    )
    clarification_question: str | None = Field(
        description="Required when missing_fields is non-empty; it is shown to the customer as the chat reply, in "
        "the language of their latest message. For missing information: a short, polite question asking for "
        "exactly that. For small talk: a warm reply that first answers what the customer said (return a greeting, "
        "say you're welcome, or explain what you can help with), then offers help. Otherwise null."
    )
    customer_response_draft: str | None = Field(
        description="The complete reply draft following the example template. Required whenever "
        "prepare_customer_response is proposed; null only when information is missing or nothing was found."
    )
