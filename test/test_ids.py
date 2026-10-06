from dataclasses import dataclass
from datetime import date

import pytest

from src.utils.dates import days_late
from src.utils.ids import extract_ids, is_customer_id, is_entity_id, is_order_id, verified_ids_from


def test_extract_ids_finds_order_and_customer_ids():
    ids = extract_ids("Order ORD-1007 (customer CUS-102) and also ORD-999999, plus ORD-1007 again.")
    assert ids.order_ids == ("ORD-1007", "ORD-999999")  # de-duplicated, first-seen order
    assert ids.customer_ids == ("CUS-102",)
    assert ids.all == {"ORD-1007", "ORD-999999", "CUS-102"}


@pytest.mark.parametrize("text", ["ORD-99x is wrong", "XORD-1007", "order 1007", "ORD-", "ord-1007", ""])
def test_extract_ids_ignores_non_ids(text):
    assert not extract_ids(text)


def test_extract_ids_handles_punctuation():
    assert extract_ids("It's ORD-1007.").order_ids == ("ORD-1007",)


@pytest.mark.parametrize(
    ("value", "order", "customer"),
    [("ORD-1007", True, False), ("CUS-102", False, True), ("ORD-99x", False, False), ("TCK-2001", False, False)],
)
def test_id_predicates(value, order, customer):
    assert is_order_id(value) is order
    assert is_customer_id(value) is customer
    assert is_entity_id(value) is (order or customer)


@dataclass
class _Msg:
    type: str
    content: object


def test_verified_ids_come_from_human_and_tool_messages_only():
    messages = [
        _Msg("human", "<customer_request>ORD-1007 is late</customer_request>"),
        _Msg("ai", "Let me check ORD-5555"),  # the model's own words never verify an ID
        _Msg("tool", '{"order": {"order_id": "ORD-1007", "customer_id": "CUS-102"}}'),
    ]
    assert verified_ids_from(messages) == {"ORD-1007", "CUS-102"}


@pytest.mark.parametrize(
    ("expected", "actual", "expected_days"),
    [
        (date(2026, 9, 25), None, 15),
        (date(2026, 10, 12), None, 0),  # not due yet
        (date(2026, 9, 27), date(2026, 9, 26), 0),  # delivered
        (None, None, 0),  # cancelled: no expected date
    ],
)
def test_days_late(expected, actual, expected_days):
    assert days_late(expected, actual, date(2026, 10, 10)) == expected_days
