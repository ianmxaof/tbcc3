"""OpenAI-compatible provider presets for uncensored chat CLI."""

from __future__ import annotations

import pytest

from app.services.llm_completions import (
    DEFAULT_FEATHERLESS_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    DEFAULT_VENICE_MODEL,
    FEATHERLESS_BASE,
    FREE_OPENROUTER_CHAT_MODELS,
    OPENROUTER_BASE,
    VENICE_BASE,
    assert_free_only_runtime,
    chat_completions_headers,
    chat_completions_url,
    free_openrouter_fallback_models,
    is_openrouter_free_model,
    resolve_text_llm_runtime,
)


def test_resolve_openrouter_runtime(monkeypatch):
    monkeypatch.setenv("TBCC_OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("TBCC_LLM_MODEL", raising=False)
    monkeypatch.delenv("TBCC_OPENROUTER_MODEL", raising=False)
    rt = resolve_text_llm_runtime(provider="openrouter")
    assert rt.provider == "openrouter"
    assert rt.api_key == "sk-or-test"
    assert rt.model == DEFAULT_OPENROUTER_MODEL
    assert chat_completions_url(rt) == f"{OPENROUTER_BASE}/chat/completions"
    headers = chat_completions_headers(rt)
    assert headers["Authorization"] == "Bearer sk-or-test"
    assert "HTTP-Referer" in headers


def test_resolve_featherless_runtime(monkeypatch):
    monkeypatch.setenv("TBCC_FEATHERLESS_API_KEY", "fl-test")
    monkeypatch.delenv("TBCC_LLM_MODEL", raising=False)
    monkeypatch.delenv("TBCC_FEATHERLESS_MODEL", raising=False)
    rt = resolve_text_llm_runtime(provider="featherless")
    assert rt.provider == "featherless"
    assert rt.model == DEFAULT_FEATHERLESS_MODEL
    assert chat_completions_url(rt) == f"{FEATHERLESS_BASE}/chat/completions"


def test_resolve_venice_runtime(monkeypatch):
    monkeypatch.setenv("VENICE_API_KEY", "vv-test")
    monkeypatch.delenv("TBCC_LLM_MODEL", raising=False)
    rt = resolve_text_llm_runtime(provider="venice", model="venice-uncensored-1-2")
    assert rt.provider == "venice"
    assert rt.api_key == "vv-test"
    assert rt.model == DEFAULT_VENICE_MODEL
    assert chat_completions_url(rt) == f"{VENICE_BASE}/chat/completions"


def test_resolve_custom_base_url(monkeypatch):
    monkeypatch.setenv("TBCC_OPENAI_API_KEY", "x")
    rt = resolve_text_llm_runtime(
        provider="custom",
        base_url="https://proxy.example/v1",
        model="heretic-local",
    )
    assert rt.provider == "custom"
    assert chat_completions_url(rt) == "https://proxy.example/v1/chat/completions"


def test_featherless_missing_key(monkeypatch):
    monkeypatch.delenv("TBCC_FEATHERLESS_API_KEY", raising=False)
    monkeypatch.delenv("FEATHERLESS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FEATHERLESS"):
        resolve_text_llm_runtime(provider="featherless")


def test_provider_switch_ignores_global_llm_model(monkeypatch):
    monkeypatch.setenv("TBCC_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("TBCC_LLM_MODEL", "cognitivecomputations/dolphin-mistral-24b-venice-edition:free")
    monkeypatch.setenv("TBCC_FEATHERLESS_API_KEY", "fl-test")
    monkeypatch.delenv("TBCC_FEATHERLESS_MODEL", raising=False)
    rt = resolve_text_llm_runtime(provider="featherless")
    assert rt.model == DEFAULT_FEATHERLESS_MODEL


def test_free_only_helpers():
    assert is_openrouter_free_model("openrouter/free")
    assert is_openrouter_free_model(FREE_OPENROUTER_CHAT_MODELS[0])
    assert not is_openrouter_free_model("cognitivecomputations/dolphin-mistral-24b-venice-edition")
    chain = free_openrouter_fallback_models("qwen/qwen3-coder:free")
    assert chain[0] == "qwen/qwen3-coder:free"
    assert FREE_OPENROUTER_CHAT_MODELS[0] in chain


def test_assert_free_only_runtime(monkeypatch):
    monkeypatch.setenv("TBCC_OPENROUTER_API_KEY", "sk-or-test")
    rt = resolve_text_llm_runtime(
        provider="openrouter",
        model="nousresearch/hermes-3-llama-3.1-405b:free",
    )
    assert_free_only_runtime(rt)
    monkeypatch.setenv("TBCC_FEATHERLESS_API_KEY", "fl-test")
    paid = resolve_text_llm_runtime(provider="featherless")
    with pytest.raises(RuntimeError, match="openrouter"):
        assert_free_only_runtime(paid)
