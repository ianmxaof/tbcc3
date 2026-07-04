"""Tests for secretary LLM config + live verification helper."""

from unittest.mock import patch

from app.services.llm_completions import TextLlmRuntime
from app.services.secretary_llm_config import (
    normalize_llm_base_url,
    test_llm_credentials,
    test_secretary_llm,
)


def test_normalize_llm_base_url_strips_completions_suffix():
    assert (
        normalize_llm_base_url("https://api.example.com/v1/chat/completions")
        == "https://api.example.com/v1"
    )


def test_test_secretary_llm_success():
    runtime = TextLlmRuntime(
        provider="openai",
        api_key="sk-test-key-12345678",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
    )
    fake = {"choices": [{"message": {"content": "TBCC_OK"}}]}
    with patch("app.services.secretary_llm_config.post_chat_completions_sync", return_value=fake):
        out = test_secretary_llm(runtime=runtime)
    assert out["ok"] is True
    assert out["reply_preview"] == "TBCC_OK"
    assert out["endpoint"] == "https://api.openai.com/v1/chat/completions"


def test_test_secretary_llm_http_error():
    runtime = TextLlmRuntime(
        provider="openai",
        api_key="sk-test-key-12345678",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
    )

    def _boom(*_a, **_k):
        raise RuntimeError("LLM error 401: invalid_api_key")

    with patch("app.services.secretary_llm_config.post_chat_completions_sync", side_effect=_boom):
        out = test_secretary_llm(runtime=runtime)
    assert out["ok"] is False
    assert out["stage"] == "http"
    assert "401" in out["message"]


def test_test_llm_credentials_validation():
    out = test_llm_credentials(api_key="short", provider="openai")
    assert out["ok"] is False
    assert out["stage"] == "validation"
