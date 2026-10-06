from typing import Any

from langchain_core.tools import tool

from src.repositories.data_store import get_data_store
from src.tools.output import ToolErrorCode, ToolOutput
from src.utils.ids import is_customer_id

_TOOL = "get_customer"


@tool
def get_customer(customer_id: str) -> dict[str, Any]:
    """Look up a customer by ID (format CUS-<digits>, e.g. CUS-102).

    Call this after get_order (the order contains the customer_id) or when the customer gives their
    customer ID. Returns the customer's name, contact email, and subscription status.
    If the customer does not exist, returns success=false with error CUSTOMER_NOT_FOUND.
    """
    if not is_customer_id(customer_id):
        return ToolOutput(
            tool=_TOOL,
            error=ToolErrorCode.INVALID_ID_FORMAT,
            message=f"'{customer_id}' is not a valid customer ID (expected CUS-<digits>).",
        ).to_dict()
    customer = get_data_store().customer(customer_id)
    if customer is None:
        return ToolOutput(
            tool=_TOOL,
            error=ToolErrorCode.CUSTOMER_NOT_FOUND,
            message=f"Customer {customer_id} was not found.",
            log_context={"customer_id": customer_id},
        ).to_dict()
    return ToolOutput(tool=_TOOL, data={"customer": customer}, log_context={"customer_id": customer_id}).to_dict()
