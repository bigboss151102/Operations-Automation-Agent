from typing import Any

from langchain_core.tools import tool

from src.repositories.data_store import get_data_store
from src.tools.output import ToolErrorCode, ToolOutput
from src.utils.ids import is_customer_id

_TOOL = "get_subscription"


@tool
def get_subscription(customer_id: str) -> dict[str, Any]:
    """Look up a customer's subscription by customer ID (format CUS-<digits>).

    Call this only for subscription-related issues (billing, paused or cancelled plans).
    Returns the subscription status, plan, and next billing date. If the customer has no
    subscription, returns success=false with error SUBSCRIPTION_NOT_FOUND.
    """
    if not is_customer_id(customer_id):
        return ToolOutput(
            tool=_TOOL,
            error=ToolErrorCode.INVALID_ID_FORMAT,
            message=f"'{customer_id}' is not a valid customer ID (expected CUS-<digits>).",
        ).to_dict()
    log_context = {"customer_id": customer_id}
    store = get_data_store()
    if store.customer(customer_id) is None:
        return ToolOutput(
            tool=_TOOL,
            error=ToolErrorCode.CUSTOMER_NOT_FOUND,
            message=f"Customer {customer_id} was not found.",
            log_context=log_context,
        ).to_dict()
    subscription = store.subscription_for(customer_id)
    if subscription is None:
        return ToolOutput(
            tool=_TOOL,
            error=ToolErrorCode.SUBSCRIPTION_NOT_FOUND,
            message=f"Customer {customer_id} has no subscription.",
            log_context=log_context,
        ).to_dict()
    return ToolOutput(tool=_TOOL, data={"subscription": subscription}, log_context=log_context).to_dict()
