"""Read-only operational data loaded once from ``data/*.json``."""

import json
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ValidationError

from src.common.schemas import Customer, Order, Subscription, SupportTicket
from src.config.settings import get_settings
from src.utils.errors import DataError


def _load[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [model.model_validate(item) for item in raw]
    except (OSError, json.JSONDecodeError, ValidationError) as e:
        raise DataError(f"Cannot load {path.name}: {e}") from e


class DataStore:
    def __init__(self, data_dir: Path) -> None:
        self._orders = {o.order_id: o for o in _load(data_dir / "orders.json", Order)}
        self._customers = {c.customer_id: c for c in _load(data_dir / "customers.json", Customer)}
        self._subscriptions = {s.customer_id: s for s in _load(data_dir / "subscriptions.json", Subscription)}
        self._tickets = _load(data_dir / "support_tickets.json", SupportTicket)

    def order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def customer(self, customer_id: str) -> Customer | None:
        return self._customers.get(customer_id)

    def subscription_for(self, customer_id: str) -> Subscription | None:
        return self._subscriptions.get(customer_id)

    def tickets(self, *, customer_id: str | None = None, order_id: str | None = None) -> list[SupportTicket]:
        return [
            t
            for t in self._tickets
            if (customer_id is None or t.customer_id == customer_id) and (order_id is None or t.order_id == order_id)
        ]

    @property
    def max_ticket_number(self) -> int:
        """Highest numeric part of the sample ticket IDs, so created tickets never collide."""
        return max((int(t.ticket_id.split("-")[1]) for t in self._tickets), default=0)


@cache
def get_data_store() -> DataStore:
    return DataStore(get_settings().data_dir)
