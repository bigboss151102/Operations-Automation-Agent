"""Application settings loaded from ``src/.env/.env`` and the process environment."""

import os
from datetime import date
from functools import cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SRC_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = SRC_DIR / ".env" / ".env"  # src/.env is a directory; the file inside is .env


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # `REFERENCE_DATE=` in the env file means "not set"
        extra="ignore",
    )

    env: str = "dev"
    openai_api_key: SecretStr
    openai_model: str
    llm_timeout_s: float = 60.0
    high_value_threshold: float = 500.0
    reference_date: date | None = None  # fixed "today" so delay calculations are deterministic
    data_dir: Path = SRC_DIR.parent / "data"
    log_level: str = "INFO"


def _env_file() -> Path | None:
    """The env file to read, or None when disabled (tests set ``OPSPILOT_IGNORE_ENV_FILE=1``)."""
    return None if os.environ.get("OPSPILOT_IGNORE_ENV_FILE") == "1" else ENV_FILE


@cache
def get_settings() -> Settings:
    env_file = _env_file()
    if env_file is not None:
        # LangChain and LangSmith read OPENAI_API_KEY / LANGSMITH_* from os.environ directly;
        # pydantic-settings does not export values, so load the file into the environment too.
        # Existing environment variables win (override=False).
        load_dotenv(env_file, override=False)
    return Settings(_env_file=env_file)  # required fields come from the environment / env file


def today(settings: Settings | None = None) -> date:
    """The business "today": the configured reference date, or the real date if unset."""
    settings = settings or get_settings()
    return settings.reference_date or date.today()
