from langchain_openai import ChatOpenAI

from src.llm.client import MAX_RETRIES, get_chat_model


def test_chat_model_comes_from_settings_without_network():
    model = get_chat_model()
    assert isinstance(model, ChatOpenAI)  # "openai:<model>" resolves to ChatOpenAI
    assert model.model_name == "test-model"
    assert model.max_retries == MAX_RETRIES
    assert model.request_timeout == 60.0
    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == "test-key"
