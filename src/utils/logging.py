"""Key=value application logging with a per-request ``request_id`` (spec §22.2)."""

import logging
from contextvars import ContextVar
from typing import Any, TextIO

LOGGER_NAME = "opspilot"
_NO_REQUEST = "-"

_request_id: ContextVar[str] = ContextVar("request_id", default=_NO_REQUEST)


def set_request_id(request_id: str) -> None:
    _request_id.set(request_id)


def get_request_id() -> str:
    return _request_id.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def make_handler(stream: TextIO | None = None) -> logging.Handler:
    """A handler with the OpsPilot format: ``[LEVEL] request_id=<id> <message>``."""
    handler = logging.StreamHandler(stream)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(logging.Formatter("[%(levelname)s] request_id=%(request_id)s %(message)s"))
    return handler


def configure_logging(level: str = "INFO") -> None:
    """Configure the ``opspilot`` logger once; safe to call repeatedly."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    logger.propagate = False
    if any(getattr(h, "_opspilot", False) for h in logger.handlers):
        return
    handler = make_handler()
    handler._opspilot = True  # type: ignore[attr-defined]  # marker for idempotency
    logger.addHandler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def _format_value(value: Any) -> str:
    text = "-" if value is None else str(value)
    if text == "" or any(ch in text for ch in ' ="'):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def format_event(event: str, **fields: Any) -> str:
    """Render ``event=<event> k=v ...``; values containing spaces are quoted."""
    parts = [f"event={_format_value(event)}"]
    parts += [f"{key}={_format_value(value)}" for key, value in fields.items()]
    return " ".join(parts)


def log_event(event: str, *, level: int = logging.INFO, logger: logging.Logger | None = None, **fields: Any) -> None:
    (logger or get_logger()).log(level, format_event(event, **fields))
