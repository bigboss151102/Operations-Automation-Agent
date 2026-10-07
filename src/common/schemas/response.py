"""The final response of one request, shared by the service, the REST API, and the Streamlit UI (spec §14, §18)."""

from pydantic import Field

from src.common.schemas._base import Record
from src.common.schemas.actions import ApprovalRequest
from src.common.schemas.decisions import GuardrailDecision, PolicyViolation
from src.common.schemas.delivery import NotificationResult
from src.common.schemas.enums import Intent, ResponseStatus, Severity


class ExecutedAction(Record):
    """An action that actually ran (automatically, or after human approval)."""

    action: str
    success: bool
    result_id: str | None = None  # ticket_id, notification_id, draft_id, or refund_id
    error: str | None = None


class AnalyzeResponse(Record):
    request_id: str
    thread_id: str  # pass to resume_agent() to decide pending approvals
    status: ResponseStatus
    message: str | None = Field(
        default=None, description="User-facing text: the clarification question, not-found, or error explanation."
    )
    intent: Intent | None = None
    order_id: str | None = None
    customer_id: str | None = None
    issue_summary: str | None = None
    severity: Severity | None = None
    severity_reasons: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommended_actions: list[GuardrailDecision] = Field(default_factory=list)  # with risk / execution / rules
    executed_actions: list[ExecutedAction] = Field(default_factory=list)
    approvals: list[ApprovalRequest] = Field(default_factory=list)  # pending, approved, or rejected
    approval_required: bool = False  # True while any approval is pending
    customer_response: str | None = Field(
        default=None, description="Reply draft (R8-checked). The chatbot shows it to the customer (decision D6)."
    )
    draft_policy_violations: list[PolicyViolation] = Field(default_factory=list)  # R8: LLM draft was replaced
    notification: NotificationResult | None = None  # operations alert (Slack or simulated), if one was sent
    customer_updates: list[str] = Field(
        default_factory=list, description="Follow-up messages for the customer after a refund decision."
    )
