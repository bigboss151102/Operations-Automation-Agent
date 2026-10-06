"""The result every tool returns.

Tools hand LangChain a flat, JSON-serializable dict, because that is what ends up in the
``ToolMessage`` the LLM reads (spec Tool 1):

    {"success": true, "order": {...}, "days_late": 15}
    {"success": false, "error": "ORDER_NOT_FOUND", "message": "Order ORD-9999 was not found."}

Usage::

    ToolOutput(tool="get_order", data={"order": order, "days_late": 15}, log_context={"order_id": "ORD-1007"})
    ToolOutput(tool="get_order", error=ToolErrorCode.ORDER_NOT_FOUND, message="Order ORD-9999 was not found.")

``success`` is derived: an output is a failure exactly when it has an ``error``. Every output is logged
as a ``tool_called`` event when it is created (spec §22); ``log_context`` carries IDs only, never free
text or PII.
"""

import logging
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.utils.logging import get_logger, log_event

_log = get_logger("tools")


class ToolErrorCode(StrEnum):
    """Expected, structured failures. Tools return these instead of raising."""

    INVALID_ID_FORMAT = "INVALID_ID_FORMAT"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    SUBSCRIPTION_NOT_FOUND = "SUBSCRIPTION_NOT_FOUND"
    ORDER_CUSTOMER_MISMATCH = "ORDER_CUSTOMER_MISMATCH"
    REFUND_NOT_APPROVED = "REFUND_NOT_APPROVED"
    INVALID_REFUND_AMOUNT = "INVALID_REFUND_AMOUNT"


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    return value


class ToolOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool: str
    data: dict[str, Any] = Field(default_factory=dict)  # may contain Pydantic models; serialized in to_dict()
    error: ToolErrorCode | None = None
    message: str | None = None
    log_context: dict[str, Any] = Field(default_factory=dict)  # IDs to log; never returned to the LLM

    @property
    def success(self) -> bool:
        return self.error is None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.error is not None and not self.message:
            raise ValueError("A failed output needs a message")
        if self.error is not None and self.data:
            raise ValueError("A failed output cannot carry data")
        return self

    def model_post_init(self, context: Any, /) -> None:
        if self.success:
            log_event("tool_called", tool=self.tool, success=True, logger=_log, **self.log_context)
        else:
            log_event(
                "tool_called",
                tool=self.tool,
                success=False,
                error=self.error,
                level=logging.WARNING,
                logger=_log,
                **self.log_context,
            )

    def to_dict(self) -> dict[str, Any]:
        """The flat contract handed to LangChain and, through it, to the LLM."""
        if self.error is None:
            return {"success": True, **{key: _jsonable(value) for key, value in self.data.items()}}
        return {"success": False, "error": self.error.value, "message": self.message}
