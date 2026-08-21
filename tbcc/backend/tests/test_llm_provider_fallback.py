from __future__ import annotations

import asyncio

import pytest

from app.services.llm_completions import (
    CEREBRAS_BASE,
    DEEPINFRA_BASE,
    DEFAULT_GROQ_MODEL,
    GROQ_BASE,
    MISTRAL_BASE,
    NVIDIA_BASE,
    TOGETHER_BASE,
    ZLM_BASE,
    TextLlmRuntime,
    resolve_text_llm_runtime,
)
from app.services.llm_refusal import looks_like_refusal
from app.services.system_prompts import prompt_text


def test_looks_like_refusal():
    assert looks_like_refusal("As an AI I cannot assist with that.")
    assert looks_like_refusal("")
    assert not looks_like_refusal("hey — yeah we have that lane. want the payment bot?")


def test_resolve_zlm_deepinfra_together(monkeypatch):
    monkeypatch.setenv("TBCC_ZLM_API_KEY", "zlm-test")
    monkeypatch.delenv("TBCC_LLM_MODEL", raising=False)
    monkeypatch.delenv("TBCC_ZLM_MODEL", raising=False)
    z = resolve_text_llm_runtime(provider="zlm")
    assert z.provider == "zlm"
    assert z.base_url == ZLM_BASE

    monkeypatch.setenv("TBCC_DEEPINFRA_API_KEY", "di-test")
    monkeypatch.delenv("TBCC_DEEPINFRA_MODEL", raising=False)
    d = resolve_text_llm_runtime(provider="deepinfra")
    assert d.base_url == DEEPINFRA_BASE

    monkeypatch.setenv("TBCC_TOGETHER_API_KEY", "tg-test")
    t = resolve_text_llm_runtime(provider="together")
    assert t.base_url == TOGETHER_BASE


def test_resolve_groq_accepts_alias_env(monkeypatch):
    monkeypatch.setenv("TBCC_GROQ_API", "gsk-test")
    monkeypatch.delenv("TBCC_GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_LLM_MODEL", raising=False)
    monkeypatch.delenv("TBCC_GROQ_MODEL", raising=False)
    g = resolve_text_llm_runtime(provider="groq")
    assert g.provider == "groq"
    assert g.base_url == GROQ_BASE
    assert g.api_key == "gsk-test"
    assert g.model == DEFAULT_GROQ_MODEL


def test_iter_fallback_includes_groq_when_keyed(monkeypatch):
    from app.services.llm_provider_fallback import iter_fallback_runtimes

    monkeypatch.setenv("TBCC_GROQ_API_KEY", "gsk-test")
    monkeypatch.delenv("TBCC_ZLM_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_DEEPINFRA_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_TOGETHER_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_LLM_FALLBACK", raising=False)
    monkeypatch.delenv("TBCC_SECRETARY_LLM_FALLBACK", raising=False)
    hops = [rt.provider for rt in iter_fallback_runtimes(None)]
    assert "groq" in hops


def test_iter_fallback_includes_cerebras_nvidia_mistral_when_keyed(monkeypatch):
    from app.services.llm_provider_fallback import iter_fallback_runtimes

    monkeypatch.setenv("TBCC_CEREBRAS_API", "csk-test")
    monkeypatch.setenv("TBCC_NVIDIA_API", "nvapi-test")
    monkeypatch.setenv("TBCC_MISTRAL_API", "mistral-test")
    monkeypatch.delenv("TBCC_CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_ZLM_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_DEEPINFRA_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_DEEPINFRA_API", raising=False)
    monkeypatch.delenv("TBCC_TOGETHER_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_GROQ_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_GROQ_API", raising=False)
    monkeypatch.delenv("TBCC_OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("TBCC_LLM_FALLBACK", raising=False)
    monkeypatch.delenv("TBCC_SECRETARY_LLM_FALLBACK", raising=False)
    hops = [rt.provider for rt in iter_fallback_runtimes(None)]
    assert hops.index("cerebras") < hops.index("nvidia") < hops.index("mistral")
    by_provider = {rt.provider: rt for rt in iter_fallback_runtimes(None)}
    assert by_provider["cerebras"].base_url == CEREBRAS_BASE
    assert by_provider["nvidia"].base_url == NVIDIA_BASE
    assert by_provider["mistral"].base_url == MISTRAL_BASE


def test_anythingllm_needs_base(monkeypatch):
    monkeypatch.delenv("TBCC_ANYTHINGLLM_BASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="ANYTHINGLLM_BASE"):
        resolve_text_llm_runtime(provider="anythingllm")


def test_aggressive_sales_prompt_not_predatory():
    text = prompt_text("aggressive_sales").lower()
    assert "direct" in text or "closer" in text
    assert "predatory" not in text
    assert "fake scarcity" in text


def test_fallback_rotates_on_refusal(monkeypatch):
    from app.services.llm_provider_fallback import complete_chat_text_with_fallback
    from app.services import llm_provider_fallback as mod

    calls: list[str] = []

    async def fake_complete(messages, **kwargs):
        rt = kwargs["runtime"]
        calls.append(rt.provider)
        if rt.provider == "zlm":
            return "I'm not able to help with that."
        return "got it — payment bot when you're ready"

    monkeypatch.setattr("app.services.llm_completions.complete_chat_text_async", fake_complete)

    a = TextLlmRuntime(provider="zlm", api_key="a", model="glm-4.5", base_url=ZLM_BASE)
    b = TextLlmRuntime(provider="deepinfra", api_key="b", model="dolphin", base_url=DEEPINFRA_BASE)
    monkeypatch.setattr(mod, "iter_fallback_runtimes", lambda primary=None: [a, b])

    text = asyncio.run(
        complete_chat_text_with_fallback(
            [{"role": "user", "content": "hi"}],
            primary=a,
        )
    )
    assert "payment bot" in text
    assert calls == ["zlm", "deepinfra"]
