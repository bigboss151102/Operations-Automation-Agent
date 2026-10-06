"""Agent memory: the LangGraph checkpointer that lets a run pause for human approval and resume later.

In-memory for the demo: pending approvals are lost on restart (README: Known Limitations). Production
would use a durable checkpointer such as Postgres.

The serializer allowlists our own state types explicitly. LangGraph is moving to block deserializing
unregistered types from checkpoints, which would otherwise break resuming a paused approval.
"""

import inspect
from enum import Enum
from functools import cache

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from src.common import schemas


def state_types() -> tuple[type, ...]:
    """Every Pydantic model and enum exported by ``src.common.schemas``; graph state is built from these."""
    exported = (getattr(schemas, name) for name in schemas.__all__)
    return tuple(t for t in exported if inspect.isclass(t) and issubclass(t, BaseModel | Enum))


def make_checkpointer() -> InMemorySaver:
    return InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=state_types()))


@cache
def get_checkpointer() -> InMemorySaver:
    return make_checkpointer()
