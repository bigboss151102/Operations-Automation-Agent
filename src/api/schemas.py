"""HTTP-only schemas. ``AnalyzeResponse`` is shared with the UI and lives in ``src/common/schemas``."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 10

CustomerMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"message": "My order ORD-1007 is 15 days late. I want a refund."},
                {"message": "It's ORD-1007.", "history": ["My order hasn't arrived and I want a refund."]},
            ]
        },
    )

    message: CustomerMessage = Field(description="The customer's latest message.")
    history: list[CustomerMessage] = Field(
        default_factory=list,
        max_length=MAX_HISTORY_TURNS,
        description="Earlier customer messages, when replying to a clarification question (status needs_more_info).",
    )


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    """Body of an unexpected 500. Never contains stack traces or upstream error details."""

    error: ErrorBody
