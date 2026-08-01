"""llm_chat custom OpenAI-compatible proxy (companion / island LLM)."""

from __future__ import annotations

import pytest

from app.services.llm_chat import _custom_base_url, provider_configured


def test_custom_base_url_from_env(monkeypatch):
    monkeypatch.setenv("TBCC_LLM_BASE_URL", "https://api.hcnsec.cn/v1/")
    assert _custom_base_url() == "https://api.hcnsec.cn/v1"


def test_provider_configured_custom(monkeypatch):
    monkeypatch.setenv("TBCC_LLM_CHAT_PROVIDER", "custom")
    monkeypatch.setenv("TBCC_LLM_BASE_URL", "https://api.hcnsec.cn/v1")
    monkeypatch.setenv("TBCC_LLM_API_KEY", "sk-test")
    assert provider_configured() is True


def test_provider_configured_custom_missing_base(monkeypatch):
    monkeypatch.setenv("TBCC_LLM_CHAT_PROVIDER", "custom")
    monkeypatch.delenv("TBCC_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("TBCC_OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("TBCC_LLM_API_KEY", "sk-test")
    assert provider_configured() is False


def test_provider_configured_openai_with_proxy_base(monkeypatch):
    monkeypatch.setenv("TBCC_LLM_CHAT_PROVIDER", "openai")
    monkeypatch.setenv("TBCC_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TBCC_OPENAI_BASE_URL", "https://api.hcnsec.cn/v1")
    assert provider_configured() is True
