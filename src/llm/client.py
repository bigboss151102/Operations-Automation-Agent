"""The only place that constructs a chat model."""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from src.config.settings import Settings, get_settings

MAX_RETRIES = 2  # the SDK retries rate limits, 5xx, and connection errors with backoff


def get_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """OpenAI chat model via LangChain (``"openai:<model>"`` resolves to ``ChatOpenAI``).

    No sampling parameters are set: some OpenAI models reject non-default values.
    """
    settings = settings or get_settings()
    return init_chat_model(
        f"openai:{settings.openai_model}",
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.llm_timeout_s,
        max_retries=MAX_RETRIES,
    )
