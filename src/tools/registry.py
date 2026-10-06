"""Which tools exist, and who may call them.

- ``READ_TOOLS``: the only tools given to the LLM (``create_agent(tools=READ_TOOLS)``).
- ``ACTION_TOOLS``: called by workflow nodes after guardrails decide; never given to the LLM.
- ``APPROVAL_ONLY_ACTIONS``: run only after a human approves. A refund is the only one (decision D2).

There is no tool that sends messages to customers: the system only drafts replies (spec Rule 3).
"""

from langchain_core.tools import BaseTool

from src.tools.actions import (
    issue_refund,
    prepare_customer_response,
    request_human_approval,
    send_operations_notification,
)
from src.tools.customers import get_customer
from src.tools.orders import get_order
from src.tools.subscriptions import get_subscription
from src.tools.tickets import create_support_ticket, get_support_tickets

READ_TOOLS: list[BaseTool] = [get_order, get_customer, get_support_tickets, get_subscription]
ACTION_TOOLS: list[BaseTool] = [
    create_support_ticket,
    send_operations_notification,
    prepare_customer_response,
    request_human_approval,
]
APPROVAL_ONLY_ACTIONS: list[BaseTool] = [issue_refund]
