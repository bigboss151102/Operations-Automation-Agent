from pydantic import BaseModel, ConfigDict


class Record(BaseModel):
    """Immutable record: unknown fields are rejected, updates go through ``model_copy(update=...)``."""

    model_config = ConfigDict(frozen=True, extra="forbid")
