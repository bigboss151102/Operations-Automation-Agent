import pytest

from src.agents.investigator import PROMPT_VERSIONS, SYSTEM_PROMPT_TEXT
from src.prompts.loader import PROMPTS_DIR, available_prompts, load_prompt


def test_expected_prompts_exist():
    assert {"ops_agent_system", "customer_response_example"} <= set(available_prompts())


@pytest.mark.parametrize("name", available_prompts())
def test_prompt_file_is_well_formed(name):
    prompt = load_prompt(name)
    assert prompt.name == name
    assert isinstance(prompt.version, int)
    assert prompt.version >= 1
    assert prompt.description
    assert prompt.text
    rendered = prompt.render(**dict.fromkeys(prompt.variables, "X"))  # raises on a stray `$`
    assert rendered


def test_render_requires_declared_variables():
    with pytest.raises(KeyError, match="customer_response_example"):
        load_prompt("ops_agent_system").render()


def test_system_prompt_embeds_the_example_template():
    example = load_prompt("customer_response_example").text
    assert example in SYSTEM_PROMPT_TEXT
    assert "$customer_response_example" not in SYSTEM_PROMPT_TEXT
    assert "OpsPilot" in SYSTEM_PROMPT_TEXT


def test_prompt_versions_are_exposed_for_tracing():
    assert {
        "ops_agent_system": load_prompt("ops_agent_system").version,
        "customer_response_example": load_prompt("customer_response_example").version,
    } == PROMPT_VERSIONS


def test_example_template_promises_nothing():
    text = load_prompt("customer_response_example").text.lower()
    assert "being reviewed" in text
    for promise in ("we have refunded", "you will receive", "compensat"):
        assert promise not in text


def test_prompts_live_only_in_markdown_files():
    assert PROMPTS_DIR.name == "prompts"
    assert sorted(p.suffix for p in PROMPTS_DIR.iterdir() if p.is_file() and p.suffix not in {".py", ".pyc"}) == [
        ".md"
    ] * len(available_prompts())
