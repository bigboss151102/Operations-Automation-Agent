"""Shared test setup.

Environment defaults are set at import time, before any ``src`` module reads settings,
so tests never depend on the developer's real ``src/.env/.env`` and never call OpenAI or LangSmith.
LLM test doubles live in ``test/fakes.py``.
"""

import os

_TEST_ENV = {
    "OPSPILOT_IGNORE_ENV_FILE": "1",  # never read the developer's real src/.env/.env (or its secrets)
    "OPENAI_API_KEY": "test-key",
    "OPENAI_MODEL": "test-model",
    "LANGSMITH_TRACING": "false",
    "REFERENCE_DATE": "2026-10-10",
    "HIGH_VALUE_THRESHOLD": "500",
    "ENV": "test",
    "SLACK_BOT_TOKEN": "",  # tests never post to Slack: the notifier falls back to the simulated log
    "SLACK_CHANNEL_ID": "",
    "SLACK_MENTION_USER_IDS": "",
}
for _key, _value in _TEST_ENV.items():
    os.environ[_key] = _value

import pytest  # noqa: E402

from src.config.settings import get_settings  # noqa: E402
from src.integrations.slack import set_notifier  # noqa: E402
from src.repositories.action_store import get_action_store  # noqa: E402
from src.repositories.case_store import get_case_store  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_settings() -> None:
    """Each test sees settings rebuilt from the current environment."""
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_stores() -> None:
    """Created tickets, approvals, IDs, cases, and notifier overrides never leak between tests."""
    get_action_store().reset()
    get_case_store().reset()
    set_notifier(None)
