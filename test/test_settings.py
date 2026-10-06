import io
import logging
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config.settings import ENV_FILE, SRC_DIR, get_settings, today
from src.main import create_app
from src.utils.logging import configure_logging, format_event, get_logger, log_event, make_handler, set_request_id

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_settings_load_from_environment():
    settings = get_settings()
    assert settings.openai_model == "test-model"
    assert settings.openai_api_key.get_secret_value() == "test-key"
    assert settings.high_value_threshold == 500
    assert settings.data_dir == REPO_ROOT / "data"


def test_secret_is_not_exposed_in_repr():
    assert "test-key" not in repr(get_settings())


def test_today_returns_reference_date():
    assert today() == date(2026, 10, 10)


def test_today_falls_back_to_real_date_when_reference_unset(monkeypatch):
    monkeypatch.setenv("REFERENCE_DATE", "")
    get_settings.cache_clear()
    assert today() == date.today()


def test_env_file_path_is_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    assert ENV_FILE == REPO_ROOT / "src" / ".env" / ".env"
    assert SRC_DIR == REPO_ROOT / "src"
    assert get_settings().data_dir == REPO_ROOT / "data"


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"tool": "get_order", "success": True}, "event=tool_called tool=get_order success=True"),
        ({"reason": "two words"}, 'event=tool_called reason="two words"'),
        ({"error": None}, "event=tool_called error=-"),
    ],
)
def test_format_event(fields, expected):
    assert format_event("tool_called", **fields) == expected


def test_log_event_carries_request_id():
    stream = io.StringIO()
    logger = get_logger("test")
    logger.setLevel(logging.INFO)
    handler = make_handler(stream)
    logger.addHandler(handler)
    try:
        set_request_id("req-test1234")
        log_event("request_received", length=42, logger=logger)
    finally:
        logger.removeHandler(handler)
    assert stream.getvalue().strip() == "[INFO] request_id=req-test1234 event=request_received length=42"


def test_configure_logging_is_idempotent():
    configure_logging("INFO")
    configure_logging("DEBUG")
    handlers = [h for h in logging.getLogger("opspilot").handlers if getattr(h, "_opspilot", False)]
    assert len(handlers) == 1


def test_healthz():
    response = TestClient(create_app()).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
