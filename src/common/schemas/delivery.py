from src.common.schemas._base import Record


class NotificationResult(Record):
    """Outcome of posting an operations notification."""

    delivered: bool  # posted to Slack (False when simulated or failed)
    simulated: bool = False  # Slack not configured: logged instead
    channel: str | None = None
    ts: str | None = None  # Slack message timestamp: identifies the thread for follow-ups
    error: str | None = None
