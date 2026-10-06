"""The tool return contract: ``{"success": true, ...}`` or ``{"success": false, "error", "message"}``.

Every result is logged as a ``tool_called`` event (spec §22). Log fields carry IDs only, never
free text or PII.
"""

import logging
from typing import Any

from pydantic import BaseModel

from src.utils.logging import get_logger, log_event

_log = get_logger("tools")


def ok(tool: str, data: dict[str, Any], **log_fields: Any) -> dict[str, Any]:
    log_event("tool_called", tool=tool, success=True, logger=_log, **log_fields)
    return {"success": True, **data}


def fail(tool: str, error: str, message: str, **log_fields: Any) -> dict[str, Any]:
    log_event("tool_called", tool=tool, success=False, error=error, level=logging.WARNING, logger=_log, **log_fields)
    return {"success": False, "error": error, "message": message}


def dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")
