"""Exception types for real failures.

Expected business outcomes (order not found, missing ID, duplicate ticket, blocked action)
are returned as structured data, not raised.
"""


class AppError(Exception):
    """Base class for OpsPilot failures."""

    code = "app_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DataError(AppError):
    """Sample data is missing or invalid."""

    code = "data_error"


class LLMError(AppError):
    """The LLM call failed or produced unusable output."""

    code = "llm_error"
