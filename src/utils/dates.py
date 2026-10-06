from datetime import date


def days_late(expected_delivery: date | None, actual_delivery: date | None, on: date) -> int:
    """Days past the expected delivery date for an undelivered order (0 if on time or delivered)."""
    if expected_delivery is None or actual_delivery is not None:
        return 0
    return max(0, (on - expected_delivery).days)
