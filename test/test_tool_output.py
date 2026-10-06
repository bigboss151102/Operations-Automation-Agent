import io
import logging
from datetime import date

import pytest
from pydantic import ValidationError

from src.common.schemas import Severity, SupportTicket
from src.tools.output import ToolErrorCode, ToolOutput
from src.utils.logging import get_logger, make_handler

TICKET = SupportTicket(
    ticket_id="TCK-2001",
    customer_id="CUS-107",
    order_id="ORD-1008",
    status="open",
    priority="high",
    issue_type="delivery_delay",
    created_at=date(2026, 10, 5),
)


def test_success_flattens_data_and_serializes_models():
    output = ToolOutput(tool="get_support_tickets", data={"tickets": [TICKET], "count": 1, "level": Severity.HIGH})
    assert output.success is True
    assert output.to_dict() == {
        "success": True,
        "tickets": [TICKET.model_dump(mode="json")],
        "count": 1,
        "level": "HIGH",
    }


def test_failure_matches_the_spec_error_shape():  # spec Tool 1 example
    output = ToolOutput(tool="get_order", error=ToolErrorCode.ORDER_NOT_FOUND, message="Order ORD-9999 was not found.")
    assert output.success is False
    assert output.to_dict() == {
        "success": False,
        "error": "ORDER_NOT_FOUND",
        "message": "Order ORD-9999 was not found.",
    }


def test_log_context_is_never_returned_to_the_llm():
    output = ToolOutput(tool="get_order", data={"days_late": 2}, log_context={"order_id": "ORD-1001"})
    assert output.to_dict() == {"success": True, "days_late": 2}


def test_inconsistent_outputs_are_rejected():
    with pytest.raises(ValidationError, match="needs a message"):
        ToolOutput(tool="x", error=ToolErrorCode.ORDER_NOT_FOUND)
    with pytest.raises(ValidationError, match="cannot carry data"):
        ToolOutput(tool="x", error=ToolErrorCode.ORDER_NOT_FOUND, message="m", data={"order": {}})


def test_every_output_is_logged_on_creation_with_ids_only():
    stream = io.StringIO()
    logger = get_logger("tools")
    logger.setLevel(logging.INFO)
    handler = make_handler(stream)
    logger.addHandler(handler)
    try:
        ToolOutput(tool="get_order", data={"order": {"secret": "not logged"}}, log_context={"order_id": "ORD-1007"})
        ToolOutput(
            tool="get_order",
            error=ToolErrorCode.ORDER_NOT_FOUND,
            message="Order ORD-9999 was not found.",
            log_context={"order_id": "ORD-9999"},
        )
    finally:
        logger.removeHandler(handler)
    lines = stream.getvalue().splitlines()
    assert lines[0].endswith("event=tool_called tool=get_order success=True order_id=ORD-1007")
    assert lines[1].startswith("[WARNING]")
    assert lines[1].endswith("event=tool_called tool=get_order success=False error=ORDER_NOT_FOUND order_id=ORD-9999")
    assert "not logged" not in stream.getvalue()
