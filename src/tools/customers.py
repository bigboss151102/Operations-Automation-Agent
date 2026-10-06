from typing import Any

from langchain_core.tools import tool

from src.repositories.data_store import get_data_store
from src.tools._results import dump, fail, ok
from src.utils.ids import is_customer_id


@tool
def get_customer(customer_id: str) -> dict[str, Any]:
    """Look up a customer by ID (format CUS-<digits>, e.g. CUS-102).

    Call this after get_order (the order contains the customer_id) or when the customer gives their
    customer ID. Returns the customer's name, contact email, and subscription status.
    If the customer does not exist, returns success=false with error CUSTOMER_NOT_FOUND.
    """
    if not is_customer_id(customer_id):
        return fail(
            "get_customer",
            "INVALID_ID_FORMAT",
            f"'{customer_id}' is not a valid customer ID (expected CUS-<digits>).",
        )
    customer = get_data_store().customer(customer_id)
    if customer is None:
        return fail(
            "get_customer", "CUSTOMER_NOT_FOUND", f"Customer {customer_id} was not found.", customer_id=customer_id
        )
    return ok("get_customer", {"customer": dump(customer)}, customer_id=customer_id)
