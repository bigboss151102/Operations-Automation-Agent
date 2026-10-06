"""Shared test setup.

Environment defaults are set at import time, before any ``src`` module reads settings,
so tests never depend on the developer's real ``src/.env/.env`` and never call OpenAI or LangSmith.
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
}
for _key, _value in _TEST_ENV.items():
    os.environ[_key] = _value

import pytest  # noqa: E402

from src.config.settings import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_settings() -> None:
    """Each test sees settings rebuilt from the current environment."""
    get_settings.cache_clear()
