"""Guardrail inputs and outputs. Shapes only: the logic lives in ``src/guardrails``."""

from pydantic import Field

from src.common.schemas._base import Record
from src.common.schemas.domain import Customer, Order, SupportTicket
from src.common.schemas.enums import Execution, GuardrailOutcome, Risk, RuleId, Severity, TicketPriority


class Facts(Record):
    """Ground truth for a decision, re-read from the repositories. Never taken from the LLM's narrative."""

    order: Order | None = None
    customer: Customer | None = None
    order_tickets: tuple[SupportTicket, ...] = ()  # every ticket for the order, any status
    days_late: int = 0
    verified_ids: frozenset[str] = frozenset()  # IDs the customer wrote or tool results returned


class SeverityResult(Record):
    severity: Severity
    reasons: tuple[str, ...]  # every severity condition that matched, e.g. ("refund_requested", ...)


class GuardrailDecision(Record):
    """What happens to one proposed action, and which rules decided it."""

    action: str
    risk: Risk
    execution: Execution
    rules: tuple[RuleId, ...] = ()
    reason: str
    related_ticket_id: str | None = None  # the existing ticket when a duplicate is blocked


class GuardrailResult(Record):
    outcome: GuardrailOutcome
    severity: Severity | None = None  # None unless the case proceeds
    severity_reasons: tuple[str, ...] = ()
    priority: TicketPriority | None = None  # ticket priority / notification level for this case
    case_rules: tuple[RuleId, ...] = ()  # case-level rules: a stop rule (R5/R6/R7) or R2
    message: str | None = None  # user-facing explanation when the case does not proceed
    decisions: tuple[GuardrailDecision, ...] = ()


class PolicyViolation(Record):
    """A customer draft broke the content policy (R8)."""

    rule: RuleId = RuleId.CUSTOMER_DRAFT_POLICY
    code: str = Field(description="refund_promise | compensation_promise | internal_detail | empty")
    detail: str
