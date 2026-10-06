"""Entity ID formats, the single definition shared by schemas, tools, and guardrails.

Digits are unbounded (``ORD-999999`` is a valid *format* that simply doesn't exist), so a
long-but-unknown ID is reported as "not found" (spec Rule 6) rather than ignored.
"""

from typing import Annotated

from pydantic import StringConstraints

ORDER_ID_PATTERN = r"ORD-\d+"
CUSTOMER_ID_PATTERN = r"CUS-\d+"
TICKET_ID_PATTERN = r"TCK-\d+"
SUBSCRIPTION_ID_PATTERN = r"SUB-\d+"

OrderId = Annotated[str, StringConstraints(pattern=rf"^{ORDER_ID_PATTERN}$")]
CustomerId = Annotated[str, StringConstraints(pattern=rf"^{CUSTOMER_ID_PATTERN}$")]
TicketId = Annotated[str, StringConstraints(pattern=rf"^{TICKET_ID_PATTERN}$")]
SubscriptionId = Annotated[str, StringConstraints(pattern=rf"^{SUBSCRIPTION_ID_PATTERN}$")]
