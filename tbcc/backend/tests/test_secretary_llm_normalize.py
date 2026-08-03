"""Secretary LLM URL/model sanitizers."""

from app.services.secretary_llm_config import normalize_llm_base_url, normalize_llm_model_id


def test_normalize_cometapi_adds_v1():
    assert normalize_llm_base_url("https://api.cometapi.com") == "https://api.cometapi.com/v1"
    assert normalize_llm_base_url("https://api.cometapi.com/v1") == "https://api.cometapi.com/v1"


def test_normalize_model_takes_first_line():
    assert (
        normalize_llm_model_id("p-e-w/Qwen3-4B-Instruct-2507-heretic\nQwen3-4B-Instruct-2507-heretic")
        == "p-e-w/Qwen3-4B-Instruct-2507-heretic"
    )
    assert normalize_llm_model_id("  openai/gpt-4o-mini  ") == "openai/gpt-4o-mini"
    assert normalize_llm_model_id("") is None
