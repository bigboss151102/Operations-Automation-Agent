"""Operations notification payloads and admin case records (Phase 9). Shapes only: no logic, no I/O."""

from datetime import datetime

from pydantic import Field

from src.common.schemas._base import Record
from src.common.schemas.actions import ApprovalRequest
from src.common.schemas.decisions import GuardrailDecision, PolicyViolation
from src.common.schemas.enums import Intent, Severity
from src.common.schemas.response import AnalyzeResponse, ExecutedAction


class OperationsReport(Record):
    """The full analysis of one case, posted to the operations channel for review."""

    request_id: str
    severity: Severity
    severity_reasons: list[str] = Field(default_factory=list)
    high_value: bool = False
    intent: Intent | None = None
    order_id: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    issue_summary: str
    evidence: list[str] = Field(default_factory=list)
    decisions: list[GuardrailDecision] = Field(default_factory=list)
    executed_actions: list[ExecutedAction] = Field(default_factory=list)
    approvals: list[ApprovalRequest] = Field(default_factory=list)
    customer_response: str | None = None
    draft_policy_violations: list[PolicyViolation] = Field(default_factory=list)
    recommended_action: str
    mentions: list[str] = Field(default_factory=list)  # Slack member IDs to tag


class CaseRecord(Record):
    """A customer case as the Operation Admin page sees it."""

    request_id: str
    created_at: datetime
    updated_at: datetime
    customer_messages: list[str] = Field(default_factory=list)
    response: AnalyzeResponse
