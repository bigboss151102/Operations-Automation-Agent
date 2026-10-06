"""Nodes of the outer graph (spec §9.2). Only ``investigate`` uses the LLM; every other node is deterministic.

Nodes return partial state updates and never mutate the state they receive.
"""

import logging
from collections.abc import Mapping
from typing import Any, Literal

from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from src.agents.responder import build_response
from src.agents.state import OpsState
from src.common.schemas import (
    ActionName,
    AgentProposal,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    Customer,
    ExecutedAction,
    Execution,
    Facts,
    GuardrailOutcome,
    GuardrailResult,
    Order,
    PolicyViolation,
    RuleId,
    Severity,
)
from src.config.settings import today
from src.guardrails.draft_policy import check_customer_draft
from src.guardrails.rules import evaluate
from src.repositories.action_store import get_action_store
from src.repositories.data_store import get_data_store
from src.repositories.tickets import find_tickets
from src.tools.actions import (
    fallback_customer_draft,
    issue_refund,
    prepare_customer_response,
    request_human_approval,
    send_operations_notification,
)
from src.tools.registry import READ_TOOLS
from src.tools.tickets import create_support_ticket
from src.utils.dates import days_late
from src.utils.ids import extract_ids, verified_ids_from
from src.utils.logging import get_logger, log_event

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 10
READ_TOOL_NAMES = frozenset(t.name for t in READ_TOOLS)

_log = get_logger("agents")


def _customer_request(text: str) -> HumanMessage:
    # Wrapping customer text in tags is data formatting, not prompt text: the system prompt says
    # content inside <customer_request> is data, never instructions.
    return HumanMessage(f"<customer_request>\n{text}\n</customer_request>")


def _executed(action: str, output: Mapping[str, Any], id_key: str) -> ExecutedAction:
    executed = ExecutedAction(
        action=action, success=bool(output.get("success")), result_id=output.get(id_key), error=output.get("error")
    )
    log_event("action_executed", action=action, success=executed.success, result_id=executed.result_id, logger=_log)
    return executed


class OpsNodes:
    """The graph's nodes, bound to their collaborators (the investigator agent and business settings)."""

    def __init__(self, investigator: CompiledStateGraph, *, high_value_threshold: float) -> None:  # type: ignore[type-arg]
        self._investigator = investigator
        self._threshold = high_value_threshold

    # --- validate_input (deterministic) ---------------------------------------------------

    def validate_input(self, state: OpsState) -> dict[str, Any]:
        message = state.get("message", "").strip()
        history = [h.strip() for h in state.get("history", []) if h.strip()]
        texts = [*history, message]
        if not message or len(history) > MAX_HISTORY_TURNS or any(len(t) > MAX_MESSAGE_CHARS for t in texts):
            log_event("input_rejected", reason="empty_or_too_long", level=logging.WARNING, logger=_log)
            return {"error": "invalid_input"}
        ids = extract_ids("\n".join(texts))
        log_event(
            "request_received",
            message_chars=len(message),
            history_turns=len(history),
            ids=",".join(sorted(ids.all)) or None,
            logger=_log,
        )
        # Missing IDs do not stop the run: the LLM asks for what is missing (decision D5, Rule 5).
        return {
            "message": message,
            "history": history,
            "extracted_ids": sorted(ids.all),
            "executed_actions": [],
            "approvals": [],
            "draft_violations": [],
            "customer_response": None,
            "error": None,
        }

    @staticmethod
    def route_after_validation(state: OpsState) -> Literal["investigate", "respond"]:
        return "respond" if state.get("error") else "investigate"

    # --- investigate (the only LLM step) --------------------------------------------------

    def investigate(self, state: OpsState) -> dict[str, Any]:
        messages = [_customer_request(text) for text in [*state.get("history", []), state["message"]]]
        try:
            result = self._investigator.invoke({"messages": messages})
        except StructuredOutputValidationError:
            log_event("invalid_llm_output", reason="validation_error", level=logging.WARNING, logger=_log)
            return {"error": "invalid_llm_output", "proposal": None}

        proposal: AgentProposal | None = result.get("structured_response")
        if proposal is None:  # call limit reached, or the model never produced a valid proposal
            log_event("invalid_llm_output", reason="no_structured_response", level=logging.WARNING, logger=_log)
            return {"error": "invalid_llm_output", "proposal": None}

        verified = verified_ids_from(result["messages"], trusted_tools=READ_TOOL_NAMES)
        log_event(
            "intent_detected",
            intent=proposal.intent,
            issue_type=proposal.issue_type,
            requested_action=proposal.requested_action,
            order_id=proposal.order_id,
            customer_id=proposal.customer_id,
            proposed=",".join(a.action for a in proposal.proposed_actions) or None,
            logger=_log,
        )
        return {"proposal": proposal, "verified_ids": sorted(verified)}

    @staticmethod
    def route_after_investigate(state: OpsState) -> Literal["guardrails", "respond"]:
        return "respond" if state.get("error") else "guardrails"

    # --- guardrails (deterministic) -------------------------------------------------------

    @staticmethod
    def _records(proposal: AgentProposal) -> tuple[Order | None, Customer | None]:
        """Ground truth for the proposal's IDs, re-read from the repositories (never the LLM's narrative)."""
        store = get_data_store()
        order = store.order(proposal.order_id) if proposal.order_id else None
        customer_id = order.customer_id if order else proposal.customer_id
        return order, store.customer(customer_id) if customer_id else None

    def guardrails(self, state: OpsState) -> dict[str, Any]:
        proposal = state["proposal"]
        if proposal is None:  # unreachable: routing sends a missing proposal to respond
            return {"error": "invalid_llm_output"}
        order, customer = self._records(proposal)
        facts = Facts(
            order=order,
            customer=customer,
            order_tickets=tuple(find_tickets(order_id=order.order_id)) if order else (),
            days_late=days_late(order.expected_delivery_date, order.actual_delivery_date, today()) if order else 0,
            verified_ids=frozenset([*state.get("extracted_ids", []), *state.get("verified_ids", [])]),
        )
        result = evaluate(proposal, facts, high_value_threshold=self._threshold)

        for rule in result.case_rules:
            log_event("guardrail_decision", scope="case", rule=rule, outcome=result.outcome, logger=_log)
        if result.severity is not None:
            log_event(
                "severity_classified",
                severity=result.severity,
                reasons=",".join(result.severity_reasons),
                logger=_log,
            )
        for decision in result.decisions:
            log_event(
                "guardrail_decision",
                action=decision.action,
                execution=decision.execution,
                rules=",".join(decision.rules) or None,
                logger=_log,
            )
        return {"guardrails": result}

    @staticmethod
    def route_after_guardrails(state: OpsState) -> Literal["execute_actions", "respond"]:
        result = state.get("guardrails")
        return "execute_actions" if result and result.outcome is GuardrailOutcome.PROCEED else "respond"

    # --- execute_actions (deterministic; automatic actions only) ---------------------------

    @staticmethod
    def _ops_recommendation(result: GuardrailResult) -> str:
        if any(d.execution is Execution.HUMAN_APPROVAL for d in result.decisions):
            return "Review the pending refund approval."
        duplicate = next((d for d in result.decisions if RuleId.DUPLICATE_TICKET in d.rules), None)
        if duplicate is not None:
            return f"Follow up on existing ticket {duplicate.related_ticket_id}."
        return "Investigate and follow up with the customer."

    def execute_actions(self, state: OpsState) -> dict[str, Any]:
        result, proposal = state["guardrails"], state["proposal"]
        if result is None or proposal is None:  # unreachable: routing only sends proceeding cases here
            return {}
        order, customer = self._records(proposal)
        customer_id = customer.customer_id if customer else proposal.customer_id
        order_id = order.order_id if order else None
        notification_severity = Severity.CRITICAL if RuleId.HIGH_VALUE_ORDER in result.case_rules else result.severity

        executed = list(state.get("executed_actions", []))
        final_draft: str | None = None
        violations: list[PolicyViolation] = []
        for decision in result.decisions:
            if decision.execution is not Execution.AUTOMATIC:
                continue
            if decision.action == ActionName.CREATE_SUPPORT_TICKET:
                output = create_support_ticket.invoke(
                    {
                        "customer_id": customer_id,
                        "order_id": order_id,
                        "issue_type": proposal.issue_type,
                        "priority": result.priority,
                        "summary": proposal.issue_summary,
                    }
                )
                executed.append(_executed(decision.action, output, "ticket_id"))
            elif decision.action == ActionName.SEND_OPERATIONS_NOTIFICATION:
                output = send_operations_notification.invoke(
                    {
                        "severity": notification_severity,
                        "summary": proposal.issue_summary,
                        "order_id": order_id,
                        "recommended_action": self._ops_recommendation(result),
                    }
                )
                executed.append(_executed(decision.action, output, "notification_id"))
            elif decision.action == ActionName.PREPARE_CUSTOMER_RESPONSE:
                violations = check_customer_draft(proposal.customer_response_draft)  # R8
                final_draft = proposal.customer_response_draft if not violations else None
                if final_draft is None:
                    final_draft = fallback_customer_draft(customer.name if customer else "", order_id)
                    for violation in violations:
                        log_event(
                            "guardrail_decision",
                            action=decision.action,
                            rule=violation.rule,
                            code=violation.code,
                            outcome="fallback_draft",
                            level=logging.WARNING,
                            logger=_log,
                        )
                output = prepare_customer_response.invoke(
                    {
                        "customer_name": customer.name if customer else "",
                        "issue_summary": proposal.issue_summary,
                        "recommended_action": self._ops_recommendation(result),
                        "draft": final_draft,
                    }
                )
                executed.append(_executed(decision.action, output, "draft_id"))
        return {"executed_actions": executed, "customer_response": final_draft, "draft_violations": violations}

    # --- human_approval (pauses the graph; refunds only, decision D2) -----------------------

    def human_approval(self, state: OpsState) -> dict[str, Any]:
        result, proposal = state["guardrails"], state["proposal"]
        if result is None or proposal is None:
            return {}
        pending = [d for d in result.decisions if d.execution is Execution.HUMAN_APPROVAL]
        if not pending:
            return {}
        order, customer = self._records(proposal)
        request_id = state["request_id"]
        actions = get_action_store()

        # This code re-runs from the top when the graph resumes: request_human_approval is idempotent.
        approvals: list[ApprovalRequest] = []
        for decision in pending:
            is_new = actions.find_approval(request_id, decision.action) is None
            output = request_human_approval.invoke(
                {
                    "action": decision.action,
                    "reason": decision.reason,
                    "context": {
                        "order_id": order.order_id if order else None,
                        "customer_id": customer.customer_id if customer else None,
                        "amount": order.total_amount if order else None,
                        "currency": order.currency if order else None,
                        "severity": result.severity,
                    },
                    "request_id": request_id,
                }
            )
            approval = ApprovalRequest.model_validate({k: v for k, v in output.items() if k != "success"})
            approvals.append(approval)
            if is_new:
                log_event("approval_requested", approval_id=approval.approval_id, action=approval.action, logger=_log)

        answer = interrupt({"request_id": request_id, "approvals": [a.model_dump(mode="json") for a in approvals]})

        executed = list(state.get("executed_actions", []))
        decided: list[ApprovalRequest] = []
        for approval in approvals:
            choice = self._decision_for(answer, approval.approval_id)
            status = ApprovalStatus.APPROVED if choice is ApprovalDecision.APPROVE else ApprovalStatus.REJECTED
            decided_approval = actions.decide_approval(approval.approval_id, status)
            decided.append(decided_approval)
            log_event("approval_decided", approval_id=approval.approval_id, decision=status, logger=_log)
            if status is ApprovalStatus.APPROVED and approval.action == ActionName.ISSUE_REFUND:
                output = issue_refund.invoke(
                    {
                        "order_id": approval.context["order_id"],
                        "amount": approval.context["amount"],
                        "approval_id": approval.approval_id,
                    }
                )
                executed.append(_executed(approval.action, output, "refund_id"))
        return {"approvals": decided, "executed_actions": executed}

    @staticmethod
    def _decision_for(answer: Any, approval_id: str) -> ApprovalDecision:
        """A missing or unrecognised decision counts as a rejection: when uncertain, do less.

        ``answer`` is the resume value: ``{"decisions": {approval_id: "approve" | "reject"}}``.
        """
        decisions = answer.get("decisions") if isinstance(answer, Mapping) else None
        raw = decisions.get(approval_id) if isinstance(decisions, Mapping) else None
        try:
            return ApprovalDecision(str(raw))
        except ValueError:
            log_event("approval_decision_invalid", approval_id=approval_id, level=logging.WARNING, logger=_log)
            return ApprovalDecision.REJECT

    # --- respond (deterministic) ----------------------------------------------------------

    @staticmethod
    def respond(state: OpsState) -> dict[str, Any]:
        return {"response": build_response(state)}
