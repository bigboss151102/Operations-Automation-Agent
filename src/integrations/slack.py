"""Operations notifications: Slack when configured, otherwise a simulated log (decision D7).

A Slack failure never fails a request: the result says ``delivered=False`` with the error, and the
caller records it.
"""

import logging
from typing import Protocol

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError, SlackClientError
from slack_sdk.http_retry.builtin_handlers import ConnectionErrorRetryHandler, RateLimitErrorRetryHandler

from src.common.schemas import NotificationResult, OperationsReport
from src.config.settings import get_settings
from src.integrations.slack_report import build_report_blocks
from src.utils.logging import get_logger, log_event

_log = get_logger("integrations.slack")


class Notifier(Protocol):
    def post(self, report: OperationsReport) -> NotificationResult: ...

    def reply(self, channel: str, ts: str, text: str) -> NotificationResult: ...


class SlackNotifier:
    """Posts reports with the Slack Web API (``chat.postMessage``)."""

    def __init__(self, client: WebClient, channel: str) -> None:
        self._client = client
        self._channel = channel

    def _send(
        self, *, text: str, blocks: list[dict[str, object]] | None = None, thread_ts: str | None = None
    ) -> NotificationResult:
        try:
            response = self._client.chat_postMessage(
                channel=self._channel, text=text, blocks=blocks, thread_ts=thread_ts, unfurl_links=False
            )
        except SlackApiError as e:
            error = str(e.response.get("error", "unknown_error"))
            log_event("slack_post_failed", error=error, level=logging.WARNING, logger=_log)
            return NotificationResult(delivered=False, error=f"SLACK_ERROR: {error}")
        except (SlackClientError, OSError) as e:
            log_event("slack_post_failed", error=type(e).__name__, level=logging.WARNING, logger=_log)
            return NotificationResult(delivered=False, error=f"SLACK_ERROR: {type(e).__name__}")
        result = NotificationResult(delivered=True, channel=str(response["channel"]), ts=str(response["ts"]))
        log_event("slack_posted", channel=result.channel, ts=result.ts, thread=thread_ts, logger=_log)
        return result

    def post(self, report: OperationsReport) -> NotificationResult:
        blocks, text = build_report_blocks(report)
        return self._send(text=text, blocks=blocks)

    def reply(self, channel: str, ts: str, text: str) -> NotificationResult:
        return self._send(text=text, thread_ts=ts)


class LogNotifier:
    """Used when Slack is not configured: the report is logged as a simulated Slack message."""

    channel = "#operations-alerts"

    def post(self, report: OperationsReport) -> NotificationResult:
        _, text = build_report_blocks(report)
        _log.info("[SIMULATED SLACK]\nChannel: %s\n\n%s\nNext step: %s", self.channel, text, report.recommended_action)
        return NotificationResult(delivered=False, simulated=True, channel=self.channel)

    def reply(self, channel: str, ts: str, text: str) -> NotificationResult:
        _log.info("[SIMULATED SLACK THREAD REPLY]\nChannel: %s\n%s", channel, text)
        return NotificationResult(delivered=False, simulated=True, channel=channel, ts=ts)


class _NotifierHolder:
    """Process-wide notifier, built lazily from settings (and replaceable in tests)."""

    def __init__(self) -> None:
        self.notifier: Notifier | None = None


_holder = _NotifierHolder()


def _build_notifier() -> Notifier:
    settings = get_settings()
    if not settings.slack_enabled or settings.slack_bot_token is None or not settings.slack_channel_id:
        return LogNotifier()
    client = WebClient(
        token=settings.slack_bot_token.get_secret_value(),
        timeout=settings.slack_timeout_s,
        retry_handlers=[ConnectionErrorRetryHandler(), RateLimitErrorRetryHandler(max_retry_count=2)],
    )
    if not settings.slack_mentions:
        log_event("slack_no_mentions", detail="SLACK_MENTION_USER_IDS is empty; reports tag nobody", logger=_log)
    return SlackNotifier(client, settings.slack_channel_id)


def get_notifier() -> Notifier:
    if _holder.notifier is None:
        _holder.notifier = _build_notifier()
    return _holder.notifier


def set_notifier(notifier: Notifier | None) -> None:
    """Override the notifier (tests), or pass ``None`` to rebuild it from settings on next use."""
    _holder.notifier = notifier
