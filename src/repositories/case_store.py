"""In-memory store of customer cases for the Operation Admin page (Phase 9, decision D8).

Shared by all Streamlit sessions in the process, so a customer tab and an admin tab see the same cases.
Reset with the demo data; lost on restart (README: Known Limitations).
"""

from datetime import UTC, datetime
from functools import cache
from threading import RLock

from src.common.schemas import AnalyzeResponse, CaseRecord


class CaseStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._cases: dict[str, CaseRecord] = {}

    def save(self, response: AnalyzeResponse, customer_messages: list[str] | None = None) -> CaseRecord:
        """Create or update the case for ``response.request_id``; messages are kept when not given."""
        with self._lock:
            now = datetime.now(UTC)
            existing = self._cases.get(response.request_id)
            if customer_messages is None:
                customer_messages = existing.customer_messages if existing else []
            record = CaseRecord(
                request_id=response.request_id,
                created_at=existing.created_at if existing else now,
                updated_at=now,
                customer_messages=customer_messages,
                response=response,
            )
            self._cases[response.request_id] = record
            return record

    def get(self, request_id: str) -> CaseRecord | None:
        with self._lock:
            return self._cases.get(request_id)

    def all(self) -> list[CaseRecord]:
        """Most recently updated first."""
        with self._lock:
            return sorted(self._cases.values(), key=lambda c: c.updated_at, reverse=True)


@cache
def get_case_store() -> CaseStore:
    return CaseStore()
