"""Messages the chatbot sends the customer after a human decides their refund.

Deterministic templates, not LLM text: they state a financial outcome, so amounts and references must be
exact, and they are only produced after an actual decision.
"""

from src.common.schemas import ApprovalRequest, ApprovalStatus, ExecutedAction


def _first_name(customer_name: str | None) -> str:
    return customer_name.split(maxsplit=1)[0] if customer_name and customer_name.strip() else "there"


def _amount(approval: ApprovalRequest) -> str:
    amount = approval.context.get("amount")
    currency = approval.context.get("currency") or ""
    return f"{amount:.2f} {currency}".strip() if isinstance(amount, int | float) else "the requested amount"


def decision_message(approval: ApprovalRequest, refund: ExecutedAction | None, customer_name: str | None) -> str:
    """The customer-facing outcome of one refund decision."""
    name = _first_name(customer_name)
    order = approval.context.get("order_id") or "your order"
    if approval.status is ApprovalStatus.APPROVED and refund is not None and refund.success:
        return (
            f"Hi {name}, good news: our team has approved your refund of {_amount(approval)} for order {order}. "
            f"It has been processed (reference {refund.result_id}) and may take a few business days to appear "
            "on your statement."
        )
    if approval.status is ApprovalStatus.APPROVED:
        return (
            f"Hi {name}, our team approved your refund for order {order}, but we ran into a problem processing it. "
            "A team member will follow up with you shortly."
        )
    return (
        f"Hi {name}, our team has reviewed your refund request for order {order}. We're not able to approve "
        "a refund at this time, but a team member will follow up with you about the next steps."
    )
