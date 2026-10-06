from typing import Any

from langchain_core.tools import tool

from src.repositories.data_store import get_data_store
from src.tools._results import dump, fail, ok
from src.utils.ids import is_customer_id


@tool
def get_subscription(customer_id: str) -> dict[str, Any]:
    """Look up a customer's subscription by customer ID (format CUS-<digits>).

    Call this only for subscription-related issues (billing, paused or cancelled plans).
    Returns the subscription status, plan, and next billing date. If the customer has no
    subscription, returns success=false with error SUBSCRIPTION_NOT_FOUND.
    """
    if not is_customer_id(customer_id):
        return fail(
            "get_subscription",
            "INVALID_ID_FORMAT",
            f"'{customer_id}' is not a valid customer ID (expected CUS-<digits>).",
        )
    store = get_data_store()
    if store.customer(customer_id) is None:
        return fail(
            "get_subscription",
            "CUSTOMER_NOT_FOUND",
            f"Customer {customer_id} was not found.",
            customer_id=customer_id,
        )
    subscription = store.subscription_for(customer_id)
    if subscription is None:
        return fail(
            "get_subscription",
            "SUBSCRIPTION_NOT_FOUND",
            f"Customer {customer_id} has no subscription.",
            customer_id=customer_id,
        )
    return ok("get_subscription", {"subscription": dump(subscription)}, customer_id=customer_id)
