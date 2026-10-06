from src.common.schemas import SupportTicket
from src.repositories.action_store import get_action_store
from src.repositories.data_store import get_data_store


def find_tickets(*, customer_id: str | None = None, order_id: str | None = None) -> list[SupportTicket]:
    """Sample tickets plus tickets created in this process. Duplicate detection needs both."""
    created = [
        t
        for t in get_action_store().tickets
        if (customer_id is None or t.customer_id == customer_id) and (order_id is None or t.order_id == order_id)
    ]
    return get_data_store().tickets(customer_id=customer_id, order_id=order_id) + created
