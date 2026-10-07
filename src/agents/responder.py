"""Assemble the final ``AnalyzeResponse`` from graph state.

A pure function, used by the ``respond`` node and by the service while a run is paused for approval
(the ``respond`` node has not run yet then; the pending approvals are already in the state).
"""

from collections.abc import Mapping
from typing import Any

from src.common.schemas import AnalyzeResponse, ApprovalRequest, ApprovalStatus, GuardrailOutcome, ResponseStatus

ERROR_MESSAGES = {
    "invalid_input": "The request is empty or too long. Please describe the issue in up to 2,000 characters.",
    "invalid_llm_output": (
        "I couldn't analyze this request reliably, so no action was taken. "
        "Please try again or escalate to a team member."
    ),
    "internal_error": "Something went wrong while processing this request. No action was taken.",
    "no_pending_approval": "There is no pending approval for this request.",
}

_STATUS = {
    GuardrailOutcome.NEEDS_MORE_INFO: ResponseStatus.NEEDS_MORE_INFO,
    GuardrailOutcome.NOT_FOUND: ResponseStatus.NOT_FOUND,
    GuardrailOutcome.REJECTED: ResponseStatus.ERROR,
}


def error_response(request_id: str, error: str = "internal_error") -> AnalyzeResponse:
    return AnalyzeResponse(
        request_id=request_id,
        thread_id=request_id,
        status=ResponseStatus.ERROR,
        message=ERROR_MESSAGES.get(error, ERROR_MESSAGES["internal_error"]),
    )


def build_response(state: Mapping[str, Any]) -> AnalyzeResponse:
    request_id: str = state["request_id"]
    error = state.get("error")
    if error:
        return error_response(request_id, error)

    result = state.get("guardrails")
    if result is None:  # cannot happen in a well-formed run; fail safe
        return error_response(request_id)

    proposal = state.get("proposal")
    # Decided approvals replace the pending ones once human_approval has run.
    approvals: list[ApprovalRequest] = list(state.get("approvals") or state.get("pending_approvals") or [])
    awaiting = any(a.status is ApprovalStatus.PENDING for a in approvals)
    if result.outcome is GuardrailOutcome.PROCEED:
        status = ResponseStatus.AWAITING_APPROVAL if awaiting else ResponseStatus.COMPLETED
    else:
        status = _STATUS[result.outcome]

    return AnalyzeResponse(
        request_id=request_id,
        thread_id=request_id,
        status=status,
        message=result.message,
        intent=proposal.intent if proposal else None,
        order_id=proposal.order_id if proposal else None,
        customer_id=proposal.customer_id if proposal else None,
        issue_summary=proposal.issue_summary if proposal else None,
        severity=result.severity,
        severity_reasons=list(result.severity_reasons),
        evidence=list(proposal.evidence) if proposal else [],
        recommended_actions=list(result.decisions),
        executed_actions=list(state.get("executed_actions", [])),
        approvals=approvals,
        approval_required=awaiting,
        customer_response=state.get("customer_response"),
        draft_policy_violations=list(state.get("draft_violations", [])),
        notification=state.get("notification"),
        customer_updates=list(state.get("customer_updates", [])),
    )
