"""Slack notifier with a fake WebClient (no network)."""

from typing import Any

import pytest
from slack_sdk.errors import SlackApiError

from src.common.schemas import OperationsReport, Severity
from src.config.settings import get_settings
from src.integrations.slack import LogNotifier, SlackNotifier, get_notifier, set_notifier

REPORT = OperationsReport(
    request_id="req-1",
    severity=Severity.HIGH,
    order_id="ORD-1007",
    issue_summary="Order ORD-1007 is 15 days late.",
    recommended_action="Review the pending refund approval.",
    mentions=["U0APY0FEP62"],
)


class FakeWebClient:
    def __init__(self, error: str | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error = error

    def chat_postMessage(self, **kwargs: Any) -> dict[str, Any]:  # noqa: N802 (Slack SDK method name)
        self.calls.append(kwargs)
        if self.error:
            raise SlackApiError("failed", {"ok": False, "error": self.error})
        return {"ok": True, "channel": kwargs["channel"], "ts": "1700000000.000100"}


def test_slack_notifier_posts_blocks_to_the_channel():
    client = FakeWebClient()
    result = SlackNotifier(client, "C0OPS").post(REPORT)  # type: ignore[arg-type]
    assert (result.delivered, result.channel, result.ts) == (True, "C0OPS", "1700000000.000100")
    (call,) = client.calls
    assert call["channel"] == "C0OPS"
    assert call["blocks"][0]["type"] == "header"
    assert call["text"].startswith("<@U0APY0FEP62>")


def test_slack_notifier_replies_in_thread():
    client = FakeWebClient()
    SlackNotifier(client, "C0OPS").reply("C0OPS", "1700000000.000100", "✅ Refund approved")  # type: ignore[arg-type]
    assert client.calls[0]["thread_ts"] == "1700000000.000100"


def test_slack_api_error_is_returned_not_raised():
    result = SlackNotifier(FakeWebClient(error="not_in_channel"), "C0OPS").post(REPORT)  # type: ignore[arg-type]
    assert result.delivered is False
    assert result.error == "SLACK_ERROR: not_in_channel"


def test_log_notifier_simulates():
    result = LogNotifier().post(REPORT)
    assert (result.delivered, result.simulated) == (False, True)


def test_get_notifier_falls_back_to_the_log_without_config():
    assert isinstance(get_notifier(), LogNotifier)


def test_get_notifier_uses_slack_when_configured(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C0OPS")
    monkeypatch.setenv("SLACK_MENTION_USER_IDS", " U01 , U02 ,")
    get_settings.cache_clear()
    set_notifier(None)
    assert get_settings().slack_mentions == ["U01", "U02"]
    assert isinstance(get_notifier(), SlackNotifier)  # constructing it makes no network call


@pytest.mark.parametrize(
    ("token", "channel", "enabled"), [("", "C0OPS", False), ("xoxb-x", "", False), ("xoxb-x", "C1", True)]
)
def test_slack_enabled_needs_token_and_channel(monkeypatch, token, channel, enabled):
    monkeypatch.setenv("SLACK_BOT_TOKEN", token)
    monkeypatch.setenv("SLACK_CHANNEL_ID", channel)
    get_settings.cache_clear()
    assert get_settings().slack_enabled is enabled
