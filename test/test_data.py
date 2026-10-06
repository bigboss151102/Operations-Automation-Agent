"""Sample data integrity and scenario coverage (plan Phase 2, spec §4)."""

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from src.common.schemas import (
    ACTIVE_TICKET_STATUSES,
    Customer,
    IssueType,
    Order,
    OrderStatus,
    Subscription,
    SupportTicket,
    TicketStatus,
)
from src.config.settings import get_settings, today

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load[T: BaseModel](filename: str, model: type[T]) -> list[T]:
    raw: list[dict[str, Any]] = json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
    return [model.model_validate(item) for item in raw]


@pytest.fixture(scope="module")
def orders() -> dict[str, Order]:
    return {o.order_id: o for o in _load("orders.json", Order)}


@pytest.fixture(scope="module")
def customers() -> dict[str, Customer]:
    return {c.customer_id: c for c in _load("customers.json", Customer)}


@pytest.fixture(scope="module")
def tickets() -> list[SupportTicket]:
    return _load("support_tickets.json", SupportTicket)


@pytest.fixture(scope="module")
def subscriptions() -> list[Subscription]:
    return _load("subscriptions.json", Subscription)


def _days_late(order: Order, on: date) -> int:
    if order.actual_delivery_date is not None or order.expected_delivery_date is None:
        return 0
    return max(0, (on - order.expected_delivery_date).days)


def _active_tickets(tickets: list[SupportTicket], order_id: str) -> list[SupportTicket]:
    return [t for t in tickets if t.order_id == order_id and t.status in ACTIVE_TICKET_STATUSES]


# --- integrity -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "model", "id_field"),
    [
        ("orders.json", Order, "order_id"),
        ("customers.json", Customer, "customer_id"),
        ("support_tickets.json", SupportTicket, "ticket_id"),
        ("subscriptions.json", Subscription, "subscription_id"),
    ],
)
def test_records_validate_and_ids_are_unique(filename, model, id_field):
    records = _load(filename, model)
    ids = [getattr(r, id_field) for r in records]
    assert len(records) >= 8
    assert not [i for i, n in Counter(ids).items() if n > 1]


def test_references_resolve(orders, customers, tickets, subscriptions):
    for order in orders.values():
        assert order.customer_id in customers, order.order_id
    for ticket in tickets:
        assert ticket.customer_id in customers, ticket.ticket_id
        if ticket.order_id is not None:
            assert ticket.order_id in orders, ticket.ticket_id
            assert orders[ticket.order_id].customer_id == ticket.customer_id, ticket.ticket_id
    for sub in subscriptions:
        assert sub.customer_id in customers, sub.subscription_id


def test_at_most_one_subscription_per_customer(subscriptions):
    assert not [c for c, n in Counter(s.customer_id for s in subscriptions).items() if n > 1]


def test_customer_subscription_status_matches_subscriptions(customers, subscriptions):
    by_customer = {s.customer_id: s.status for s in subscriptions}
    for customer in customers.values():
        assert customer.subscription_status == by_customer.get(customer.customer_id), customer.customer_id


def test_order_dates_are_consistent(orders, tickets):
    for order in orders.values():
        if order.status is OrderStatus.DELIVERED:
            assert order.actual_delivery_date is not None, order.order_id
            assert order.actual_delivery_date >= order.order_date
        else:
            assert order.actual_delivery_date is None, order.order_id
        if order.status is OrderStatus.CANCELLED:
            assert order.expected_delivery_date is None, order.order_id
        else:
            assert order.expected_delivery_date is not None, order.order_id
            assert order.expected_delivery_date >= order.order_date
    for ticket in tickets:
        if ticket.order_id is not None:
            assert ticket.created_at >= orders[ticket.order_id].order_date, ticket.ticket_id


def test_every_order_status_is_represented(orders):
    assert {o.status for o in orders.values()} == set(OrderStatus)


def test_customer_emails_are_fictional(customers):
    assert all(c.email.endswith("@example.com") for c in customers.values())


def test_invalid_records_are_rejected():
    with pytest.raises(ValidationError):
        Order.model_validate(
            {
                "order_id": "1007",
                "customer_id": "CUS-102",
                "status": "delayed",
                "order_date": "2026-09-20",
                "total_amount": 1,
            }
        )
    with pytest.raises(ValidationError):
        Customer.model_validate({"customer_id": "CUS-1", "name": "Real Person", "email": "someone@gmail.com"})


# --- scenario coverage (spec §16 / §17, decision D1) -----------------------------------


def test_reference_date_is_fixed_for_the_demo():
    assert today() == date(2026, 10, 10)


@pytest.mark.parametrize(
    ("order_id", "expected_days_late"),
    [("ORD-1001", 2), ("ORD-1007", 15), ("ORD-1008", 7), ("ORD-1011", 10), ("ORD-1015", 18), ("ORD-1004", 0)],
)
def test_days_late_at_reference_date(orders, order_id, expected_days_late):
    assert _days_late(orders[order_id], today()) == expected_days_late


def test_scenario_1_order_has_only_a_closed_ticket(orders, tickets):
    assert orders["ORD-1001"].status is OrderStatus.DELAYED
    related = [t for t in tickets if t.order_id == "ORD-1001"]
    assert related
    assert all(t.status is TicketStatus.CLOSED for t in related)  # closed tickets must not block a new one


def test_scenario_2_refund_order_has_no_active_ticket(orders, customers, tickets):
    order = orders["ORD-1007"]
    assert order.total_amount == pytest.approx(249.99)
    assert order.total_amount < get_settings().high_value_threshold
    assert customers[order.customer_id].name == "Alex Johnson"
    assert _active_tickets(tickets, "ORD-1007") == []


def test_scenario_3_order_has_an_open_delay_ticket(tickets):
    active = _active_tickets(tickets, "ORD-1008")
    assert [(t.ticket_id, t.issue_type) for t in active] == [("TCK-2001", IssueType.DELIVERY_DELAY)]


def test_scenario_4_order_does_not_exist(orders):
    assert "ORD-9999" not in orders
    assert "ORD-999999" not in orders  # spec Rule 6 example


def test_scenario_6_high_value_order(orders):
    order = orders["ORD-1015"]
    assert order.total_amount == pytest.approx(1200.00)
    assert order.total_amount >= get_settings().high_value_threshold
    assert order.status is OrderStatus.DELAYED


def test_duplicate_refund_requests_case(tickets):
    refunds = [t for t in _active_tickets(tickets, "ORD-1011") if t.issue_type is IssueType.REFUND_REQUEST]
    assert len(refunds) >= 2


def test_small_refund_case(orders):
    assert orders["ORD-1009"].total_amount < 50
