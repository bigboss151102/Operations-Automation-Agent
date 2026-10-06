"""Deterministic business rules (spec §11-§12). Pure functions: no I/O, no LLM, no settings.

The LLM proposes actions; these rules decide, for each one, whether it runs automatically, waits for
human approval, or is blocked. Case-level stop rules (R5 missing information, R6 not found,
R7 unverified ID) block every action before anything else is considered.
"""

from langsmith import traceable

from src.common.schemas import (
    ACTIVE_TICKET_STATUSES,
    ORDER_INTENTS,
    ActionName,
    AgentProposal,
    Execution,
    Facts,
    GuardrailDecision,
    GuardrailOutcome,
    GuardrailResult,
    Intent,
    ProposedAction,
    Risk,
    RuleId,
    Severity,
    TicketPriority,
)
from src.guardrails.severity import classify_severity, is_high_value

MISSING_ORDER_ID_MESSAGE = (
    "I can help investigate this, but I need the order ID before I can check the order "
    "or determine whether a refund is appropriate."
)
MISSING_CUSTOMER_ID_MESSAGE = "I can help with your subscription, but I need your customer ID to look it up."
UNVERIFIED_ID_MESSAGE = (
    "I couldn't verify the order or customer referenced in this analysis against your message, "
    "so no action was taken. Please confirm the order ID."
)
CUSTOMER_MESSAGING_ACTION = "send_customer_message"

_RISK = {
    ActionName.PREPARE_CUSTOMER_RESPONSE: Risk.NONE,
    ActionName.SEND_OPERATIONS_NOTIFICATION: Risk.LOW,
    ActionName.CREATE_SUPPORT_TICKET: Risk.LOW,
    ActionName.ISSUE_REFUND: Risk.HIGH,
}
_PRIORITY = {
    Severity.LOW: TicketPriority.LOW,
    Severity.MEDIUM: TicketPriority.MEDIUM,
    Severity.HIGH: TicketPriority.HIGH,
    Severity.CRITICAL: TicketPriority.CRITICAL,
}


# --- case-level stop rules (R7, R5, R6) ---------------------------------------------------


def _stop(proposal: AgentProposal, facts: Facts) -> tuple[GuardrailOutcome, RuleId, str] | None:
    # R7 first: an ID the customer never wrote (and no tool returned) is a hallucination.
    for referenced in (proposal.order_id, proposal.customer_id):
        if referenced is not None and referenced not in facts.verified_ids:
            return GuardrailOutcome.REJECTED, RuleId.UNVERIFIED_ID, UNVERIFIED_ID_MESSAGE

    # R5: required information is missing. Ask; never guess.
    if proposal.missing_fields or (proposal.intent in ORDER_INTENTS and proposal.order_id is None):
        return (
            GuardrailOutcome.NEEDS_MORE_INFO,
            RuleId.MISSING_INFORMATION,
            (proposal.clarification_question or MISSING_ORDER_ID_MESSAGE),
        )
    if proposal.intent is Intent.SUBSCRIPTION_ISSUE and proposal.customer_id is None and proposal.order_id is None:
        return (
            GuardrailOutcome.NEEDS_MORE_INFO,
            RuleId.MISSING_INFORMATION,
            (proposal.clarification_question or MISSING_CUSTOMER_ID_MESSAGE),
        )

    # R6: the referenced record does not exist. Never invent one.
    if proposal.order_id is not None and facts.order is None:
        return (
            GuardrailOutcome.NOT_FOUND,
            RuleId.ORDER_NOT_FOUND,
            (f"I couldn't find order {proposal.order_id} in the available operations data."),
        )
    if proposal.customer_id is not None and proposal.order_id is None and facts.customer is None:
        return (
            GuardrailOutcome.NOT_FOUND,
            RuleId.ORDER_NOT_FOUND,
            (f"I couldn't find customer {proposal.customer_id} in the available operations data."),
        )
    return None


# --- per-action decisions -----------------------------------------------------------------


def _blocked(action: str, rule: RuleId, reason: str, risk: Risk = Risk.HIGH) -> GuardrailDecision:
    return GuardrailDecision(action=action, risk=risk, execution=Execution.BLOCKED, rules=(rule,), reason=reason)


def _decide(proposed: ProposedAction, proposal: AgentProposal, facts: Facts, *, high_value: bool) -> GuardrailDecision:
    name = str(proposed.action)

    # Defense in depth: the proposal schema already restricts actions to the catalogue.
    if name == CUSTOMER_MESSAGING_ACTION:
        return _blocked(
            name,
            RuleId.EXTERNAL_COMMUNICATION_BLOCKED,
            "OpsPilot never messages customers; it prepares a draft for a person to send.",
        )
    if name not in set(ActionName):
        return _blocked(name, RuleId.UNKNOWN_ACTION, f"'{name}' is not an action OpsPilot can perform.")

    action = ActionName(name)
    risk = _RISK[action]
    escalation = (RuleId.HIGH_VALUE_ORDER,) if high_value and action is not ActionName.PREPARE_CUSTOMER_RESPONSE else ()

    if action is ActionName.ISSUE_REFUND:  # R1: any amount, any order value
        return GuardrailDecision(
            action=name,
            risk=risk,
            execution=Execution.HUMAN_APPROVAL,
            rules=(RuleId.REFUND_REQUIRES_APPROVAL, *escalation),
            reason="Refunds are financial actions and always require human approval.",
        )

    if action is ActionName.CREATE_SUPPORT_TICKET:  # R4: an active ticket for the same issue already exists
        existing = next(
            (
                t
                for t in facts.order_tickets
                if t.status in ACTIVE_TICKET_STATUSES and t.issue_type is proposal.issue_type
            ),
            None,
        )
        if existing is not None:
            return GuardrailDecision(
                action=name,
                risk=risk,
                execution=Execution.BLOCKED,
                rules=(RuleId.DUPLICATE_TICKET,),
                reason=(
                    "An existing support ticket already exists. "
                    f"Ticket: {existing.ticket_id}, Status: {existing.status.value}"
                ),
                related_ticket_id=existing.ticket_id,
            )

    reasons = {
        ActionName.PREPARE_CUSTOMER_RESPONSE: "Drafting a reply is safe: nothing is sent to the customer.",
        ActionName.SEND_OPERATIONS_NOTIFICATION: "Internal alert to the operations team.",
        ActionName.CREATE_SUPPORT_TICKET: "No open ticket exists for this issue.",
    }
    reason = reasons[action] + (" High-value order: escalated to critical priority." if escalation else "")
    return GuardrailDecision(action=name, risk=risk, execution=Execution.AUTOMATIC, rules=escalation, reason=reason)


# --- entry point ------------------------------------------------------------------------


@traceable(name="guardrails.evaluate", run_type="chain")
def evaluate(proposal: AgentProposal, facts: Facts, *, high_value_threshold: float) -> GuardrailResult:
    """Decide what may happen for this case. The proposal is a recommendation; facts are ground truth."""
    stop = _stop(proposal, facts)
    if stop is not None:
        outcome, rule, message = stop
        return GuardrailResult(
            outcome=outcome,
            case_rules=(rule,),
            message=message,
            decisions=tuple(
                _blocked(
                    str(a.action),
                    rule,
                    f"Stopped by {rule.value}: no action runs.",
                    risk=_RISK.get(a.action, Risk.HIGH),
                )
                for a in proposal.proposed_actions
            ),
        )

    severity = classify_severity(proposal, facts, high_value_threshold=high_value_threshold)
    high_value = is_high_value(facts, high_value_threshold)
    return GuardrailResult(
        outcome=GuardrailOutcome.PROCEED,
        severity=severity.severity,
        severity_reasons=severity.reasons,
        priority=TicketPriority.CRITICAL if high_value else _PRIORITY[severity.severity],  # R2 escalation
        case_rules=(RuleId.HIGH_VALUE_ORDER,) if high_value else (),
        decisions=tuple(_decide(a, proposal, facts, high_value=high_value) for a in proposal.proposed_actions),
    )
