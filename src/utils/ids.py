"""Find and recognise entity IDs in text.

Shared by ``validate_input``, the tools, ``VerifiedIdMiddleware``, and the ``investigate`` node,
so every layer agrees on what counts as an ID the customer actually wrote.
"""

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from src.common.schemas.ids import CUSTOMER_ID_PATTERN, ORDER_ID_PATTERN

# An ID must not be glued to other word characters: "XORD-1007" and "ORD-99x" are not IDs.
_BEFORE = r"(?<![A-Za-z0-9-])"
_AFTER = r"(?![A-Za-z0-9])"

ORDER_ID_RE = re.compile(_BEFORE + ORDER_ID_PATTERN + _AFTER)
CUSTOMER_ID_RE = re.compile(_BEFORE + CUSTOMER_ID_PATTERN + _AFTER)
_ORDER_ID_FULL = re.compile(rf"^{ORDER_ID_PATTERN}$")
_CUSTOMER_ID_FULL = re.compile(rf"^{CUSTOMER_ID_PATTERN}$")


@dataclass(frozen=True, slots=True)
class ExtractedIds:
    order_ids: tuple[str, ...] = ()
    customer_ids: tuple[str, ...] = ()

    @property
    def all(self) -> frozenset[str]:
        return frozenset(self.order_ids + self.customer_ids)

    def __bool__(self) -> bool:
        return bool(self.order_ids or self.customer_ids)


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))  # de-duplicate, keep first-seen order


def extract_ids(text: str) -> ExtractedIds:
    return ExtractedIds(
        order_ids=_unique(ORDER_ID_RE.findall(text)),
        customer_ids=_unique(CUSTOMER_ID_RE.findall(text)),
    )


def is_order_id(value: str) -> bool:
    return bool(_ORDER_ID_FULL.match(value))


def is_customer_id(value: str) -> bool:
    return bool(_CUSTOMER_ID_FULL.match(value))


def is_entity_id(value: str) -> bool:
    return is_order_id(value) or is_customer_id(value)


class _Message(Protocol):
    type: str
    content: Any


def verified_ids_from(messages: Iterable[_Message], *, trusted_tools: Collection[str] | None = None) -> set[str]:
    """IDs the customer wrote (human messages) or that a tool successfully returned.

    Not trusted: the model's own words (AI messages), failed tool calls (``status="error"``; e.g. an
    ``UNVERIFIED_ID`` message quotes the guessed ID), and, when ``trusted_tools`` is given, any other
    tool message, such as the structured-output tool that echoes the model's own proposal.
    """
    verified: set[str] = set()
    for message in messages:
        if message.type == "human":
            verified |= extract_ids(str(message.content)).all
        elif message.type == "tool":
            if getattr(message, "status", "success") == "error":
                continue
            if trusted_tools is not None and getattr(message, "name", None) not in trusted_tools:
                continue
            verified |= extract_ids(str(message.content)).all
    return verified
