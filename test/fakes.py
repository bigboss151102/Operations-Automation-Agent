"""Test doubles for the LLM. Tests never call OpenAI."""

from collections.abc import Sequence
from itertools import count
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

_call_ids = count(1)


class FakeChatModel(GenericFakeChatModel):
    """Scripted chat model: returns the queued ``messages`` one per call; never touches the network.

    ``GenericFakeChatModel.bind_tools`` raises ``NotImplementedError``; agents need it, so it is a no-op here.
    An exhausted script raises ``StopIteration``, which proves the model was called more often than expected.
    """

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> FakeChatModel:
        return self


def fake_model(*turns: AIMessage) -> FakeChatModel:
    return FakeChatModel(messages=iter(turns))


def tool_call(name: str, **args: Any) -> AIMessage:
    """An assistant turn that calls one tool. With ToolStrategy, the final answer is a call named "AgentProposal"."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{next(_call_ids)}"}])
