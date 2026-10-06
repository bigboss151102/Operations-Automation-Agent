from typing import Any

from langchain_core.tools import tool

from src.config.settings import today
from src.repositories.data_store import get_data_store
from src.tools.output import ToolErrorCode, ToolOutput
from src.utils import dates
from src.utils.ids import is_order_id

_TOOL = "get_order"


@tool
def get_order(order_id: str) -> dict[str, Any]:
    """Look up an order by its ID (format ORD-<digits>, e.g. ORD-1007).

    Call this whenever the customer mentions an order ID, before reasoning about that order.
    Returns the order record (status, order/expected/actual delivery dates, total amount, currency)
    and `days_late`: days past the expected delivery date as of today (0 if on time or delivered).
    If the order does not exist, returns success=false with error ORDER_NOT_FOUND. Never guess an ID.
    """
    if not is_order_id(order_id):
        return ToolOutput(
            tool=_TOOL,
            error=ToolErrorCode.INVALID_ID_FORMAT,
            message=f"'{order_id}' is not a valid order ID (expected ORD-<digits>).",
        ).to_dict()
    order = get_data_store().order(order_id)
    if order is None:
        return ToolOutput(
            tool=_TOOL,
            error=ToolErrorCode.ORDER_NOT_FOUND,
            message=f"Order {order_id} was not found.",
            log_context={"order_id": order_id},
        ).to_dict()
    late = dates.days_late(order.expected_delivery_date, order.actual_delivery_date, today())
    return ToolOutput(
        tool=_TOOL,
        data={"order": order, "days_late": late},
        log_context={"order_id": order_id},
    ).to_dict()
