"""In-memory store for records created by (simulated) actions.

It resets on process start, which keeps the demo deterministic. Access is locked because
FastAPI runs sync routes in a threadpool.
"""

from functools import cache
from threading import RLock

from src.common.schemas import (
    ApprovalRequest,
    ApprovalStatus,
    CustomerDraft,
    OperationsNotification,
    RefundRecord,
    SupportTicket,
)
from src.repositories.data_store import get_data_store

APPROVAL_ID_START = 1000  # first approval is APR-1001 (spec Tool 8 example)


class ActionStore:
    def __init__(self, ticket_id_start: int) -> None:
        self._ticket_id_start = ticket_id_start
        self._lock = RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.tickets: list[SupportTicket] = []
            self.notifications: list[OperationsNotification] = []
            self.drafts: list[CustomerDraft] = []
            self.refunds: list[RefundRecord] = []
            self._approvals: dict[str, ApprovalRequest] = {}
            self._approval_by_key: dict[tuple[str, str], str] = {}
            self._counters = {"TCK": self._ticket_id_start, "APR": APPROVAL_ID_START}

    def next_id(self, prefix: str) -> str:
        """Sequential IDs (``TCK-2009``, ``APR-1001``, ``NTF-0001``) above any sample-data ID."""
        with self._lock:
            self._counters[prefix] = self._counters.get(prefix, 0) + 1
            return f"{prefix}-{self._counters[prefix]:04d}"

    def add_ticket(self, ticket: SupportTicket) -> None:
        with self._lock:
            self.tickets.append(ticket)

    def add_notification(self, notification: OperationsNotification) -> None:
        with self._lock:
            self.notifications.append(notification)

    def add_draft(self, draft: CustomerDraft) -> None:
        with self._lock:
            self.drafts.append(draft)

    def add_refund(self, refund: RefundRecord) -> None:
        with self._lock:
            self.refunds.append(refund)

    def find_approval(self, request_id: str, action: str) -> ApprovalRequest | None:
        with self._lock:
            approval_id = self._approval_by_key.get((request_id, action))
            return self._approvals.get(approval_id) if approval_id else None

    def save_approval(self, approval: ApprovalRequest) -> None:
        with self._lock:
            self._approvals[approval.approval_id] = approval
            self._approval_by_key[(approval.request_id, approval.action)] = approval.approval_id

    def approval(self, approval_id: str) -> ApprovalRequest | None:
        with self._lock:
            return self._approvals.get(approval_id)

    @property
    def approvals(self) -> list[ApprovalRequest]:
        with self._lock:
            return list(self._approvals.values())

    def decide_approval(self, approval_id: str, status: ApprovalStatus) -> ApprovalRequest:
        """Record a human decision. A decision is final: deciding twice is an error."""
        if status is ApprovalStatus.PENDING:
            raise ValueError("A decision must be approved or rejected")
        with self._lock:
            current = self._approvals.get(approval_id)
            if current is None:
                raise KeyError(approval_id)
            if current.status is not ApprovalStatus.PENDING:
                raise ValueError(f"Approval {approval_id} is already {current.status}")
            decided = current.model_copy(update={"status": status})
            self._approvals[approval_id] = decided
            return decided


@cache
def get_action_store() -> ActionStore:
    return ActionStore(ticket_id_start=get_data_store().max_ticket_number)
