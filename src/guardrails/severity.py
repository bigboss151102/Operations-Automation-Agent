"""Deterministic severity classification (spec §13, decision D3).

Every condition is evaluated and the highest matching severity wins. The LLM contributes only the
classification of what the customer wants; every number (days late, amount, open tickets) comes
from the data.
"""

from src.common.schemas import (
    ACTIVE_TICKET_STATUSES,
    AgentProposal,
    Facts,
    Intent,
    IssueType,
    RequestedAction,
    Severity,
    SeverityResult,
)

_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}
_MEDIUM_ISSUES = frozenset({IssueType.SUBSCRIPTION_ISSUE, IssueType.ADDRESS_ISSUE, IssueType.CANCELLED_ORDER})
_DELAY_HIGH_THRESHOLD_DAYS = 7  # more than this many days late is HIGH
_REPEATED_REFUND_REQUESTS = 2


def refund_requested(proposal: AgentProposal) -> bool:
    return (
        proposal.requested_action is RequestedAction.REFUND
        or proposal.intent is Intent.REFUND_REQUEST
        or proposal.issue_type is IssueType.REFUND_REQUEST
    )


def is_high_value(facts: Facts, high_value_threshold: float) -> bool:
    return facts.order is not None and facts.order.total_amount >= high_value_threshold


def classify_severity(proposal: AgentProposal, facts: Facts, *, high_value_threshold: float) -> SeverityResult:
    refund = refund_requested(proposal)
    high_value = is_high_value(facts, high_value_threshold)
    missing_order = proposal.issue_type is IssueType.MISSING_ORDER
    open_refund_tickets = sum(
        1
        for t in facts.order_tickets
        if t.status in ACTIVE_TICKET_STATUSES and t.issue_type is IssueType.REFUND_REQUEST
    )

    matched: list[tuple[Severity, str]] = [(Severity.LOW, "baseline")]
    if proposal.intent is Intent.ORDER_STATUS and facts.days_late == 0:
        matched.append((Severity.LOW, "informational"))
    if 1 <= facts.days_late <= _DELAY_HIGH_THRESHOLD_DAYS:
        matched.append((Severity.MEDIUM, "delay_1_to_7_days"))
    if proposal.issue_type in _MEDIUM_ISSUES:
        matched.append((Severity.MEDIUM, proposal.issue_type.value))
    if refund:
        matched.append((Severity.HIGH, "refund_requested"))
    if facts.days_late > _DELAY_HIGH_THRESHOLD_DAYS:
        matched.append((Severity.HIGH, "delay_over_7_days"))
    if missing_order:
        matched.append((Severity.HIGH, "missing_order"))
    if refund and high_value:
        matched.append((Severity.CRITICAL, "high_value_refund"))
    if open_refund_tickets >= _REPEATED_REFUND_REQUESTS:
        matched.append((Severity.CRITICAL, "repeated_refund_requests"))
    if missing_order and high_value:
        matched.append((Severity.CRITICAL, "high_value_missing_order"))

    severity = max((s for s, _ in matched), key=_RANK.__getitem__)
    reasons = tuple(reason for s, reason in matched if s is severity and reason != "baseline") or ("baseline",)
    return SeverityResult(severity=severity, reasons=reasons)
