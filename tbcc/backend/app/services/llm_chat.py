"""
Configurable chat completions for the generic LLM Telegram bridge (llm_chat_bot).

Providers: OpenAI, OpenRouter (OpenAI-compatible), custom proxy (TBCC_LLM_BASE_URL), or local Ollama /api/chat.

Env (llm_chat_bot / companion_bot):
  TBCC_LLM_CHAT_PROVIDER — openai | openrouter | custom | ollama (default: ollama)
  TBCC_OPENROUTER_API_KEY + TBCC_OPENROUTER_CHAT_MODEL (or TBCC_LLM_MODEL)
  TBCC_OPENAI_API_KEY / TBCC_LLM_CHAT_OPENAI_MODEL / TBCC_LLM_CHAT_MAX_TOKENS / TBCC_LLM_CHAT_TEMPERATURE
  TBCC_OPENAI_BASE_URL / TBCC_LLM_BASE_URL — OpenAI-compatible host (e.g. api.hcnsec.cn/v1)
  TBCC_LLM_API_KEY — alternate key env for custom proxies
  TBCC_OLLAMA_BASE_URL (default http://127.0.0.1:11434) / TBCC_OLLAMA_MODEL (default llama3.2)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _openai_key() -> str:
    return (os.getenv("TBCC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def _provider() -> str:
    return (os.getenv("TBCC_LLM_CHAT_PROVIDER") or "ollama").strip().lower()


def _ollama_base() -> str:
    return (os.getenv("TBCC_OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")


def _ollama_model() -> str:
    return (os.getenv("TBCC_OLLAMA_MODEL") or "llama3.2").strip()


def _openai_model() -> str:
    return (
        os.getenv("TBCC_LLM_CHAT_OPENAI_MODEL")
        or os.getenv("TBCC_LLM_MODEL")
        or os.getenv("TBCC_LLM_CHAT_OPENROUTER_MODEL")
        or "gpt-4o-mini"
    ).strip()


def _custom_base_url() -> str:
    return (os.getenv("TBCC_OPENAI_BASE_URL") or os.getenv("TBCC_LLM_BASE_URL") or "").strip().rstrip("/")


def _openrouter_model() -> str:
    from app.services.llm_completions import resolve_text_model

    explicit = (os.getenv("TBCC_LLM_CHAT_OPENROUTER_MODEL") or os.getenv("TBCC_OPENROUTER_MODEL") or "").strip()
    return resolve_text_model(explicit or None)


def _max_tokens() -> int:
    raw = (os.getenv("TBCC_LLM_CHAT_MAX_TOKENS") or "512").strip()
    try:
        return max(32, min(4096, int(raw)))
    except ValueError:
        return 512


def _temperature() -> float:
    raw = (os.getenv("TBCC_LLM_CHAT_TEMPERATURE") or "0.8").strip()
    try:
        return max(0.0, min(2.0, float(raw)))
    except ValueError:
        return 0.8


def default_system_prompt() -> str:
    custom = (os.getenv("TBCC_LLM_CHAT_SYSTEM_PROMPT") or "").strip()
    if custom:
        return custom
    return (
        "You are a helpful assistant in a private Telegram chat. "
        "Be concise unless the user asks for detail. "
        "You must not assist with abuse of minors, illegal activity, or non-consensual content."
    )


def provider_configured() -> bool:
    p = _provider()
    if p == "openai":
        return bool(_openai_key())
    if p == "custom":
        try:
            from app.services.llm_completions import resolve_text_llm_runtime

            resolve_text_llm_runtime(provider="custom")
            return True
        except RuntimeError:
            return False
    if p == "openrouter":
        from app.services.llm_completions import openrouter_api_key

        return bool(openrouter_api_key())
    if p in ("ollama", "local"):
        return True
    return False


async def complete_llm_chat(messages: list[dict[str, str]]) -> str:
    if not messages:
        raise ValueError("messages empty")
    p = _provider()
    if p in ("ollama", "local"):
        return await _complete_ollama(messages)
    if p == "openai":
        return await _complete_openai(messages)
    if p == "custom":
        return await _complete_custom(messages)
    if p == "openrouter":
        return await _complete_openrouter(messages)
    raise RuntimeError(f"Unknown TBCC_LLM_CHAT_PROVIDER: {p}")


async def _complete_ollama(messages: list[dict[str, str]]) -> str:
    base = _ollama_base()
    model = _ollama_model()
    url = f"{base}/api/chat"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": _temperature()},
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json=body, timeout=120.0)
        if not r.is_success:
            logger.warning("Ollama HTTP %s: %s", r.status_code, (r.text or "")[:400])
            raise RuntimeError(f"Ollama error {r.status_code}: {(r.text or '')[:200]}")
        data = r.json()
    msg = data.get("message") or {}
    text = (msg.get("content") or "").strip()
    if not text:
        raise RuntimeError("Ollama returned empty content — is the model pulled? Try: ollama pull " + model)
    return text


async def _complete_openai(messages: list[dict[str, str]]) -> str:
    custom = _custom_base_url()
    if custom:
        return await _complete_custom(messages, base_url=custom)

    key = _openai_key()
    if not key:
        raise RuntimeError("Set TBCC_OPENAI_API_KEY or OPENAI_API_KEY for OpenAI provider")

    payload: dict[str, Any] = {
        "model": _openai_model(),
        "messages": messages,
        "max_tokens": _max_tokens(),
        "temperature": _temperature(),
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=90.0,
        )
        if not r.is_success:
            detail = (r.text or "")[:500]
            logger.warning("OpenAI llm_chat HTTP %s: %s", r.status_code, detail)
            raise RuntimeError(f"OpenAI error {r.status_code}")
        data = r.json()

    try:
        choice0 = (data.get("choices") or [{}])[0]
        msg = choice0.get("message") or {}
        text = (msg.get("content") or "").strip()
    except Exception as e:
        logger.warning("bad OpenAI llm_chat response: %s", e)
        raise RuntimeError("OpenAI response parse error")
    if not text:
        raise RuntimeError("OpenAI returned empty content")
    return text


async def _complete_custom(messages: list[dict[str, str]], *, base_url: str | None = None) -> str:
    from app.services.llm_completions import complete_chat_text_async, resolve_text_llm_runtime

    rt = resolve_text_llm_runtime(provider="custom", base_url=base_url or _custom_base_url() or None)
    return await complete_chat_text_async(
        messages,
        model=_openai_model(),
        max_tokens=_max_tokens(),
        temperature=_temperature(),
        timeout=120.0,
        runtime=rt,
    )


async def _complete_openrouter(messages: list[dict[str, str]]) -> str:
    from app.services.llm_completions import complete_chat_text_async, openrouter_api_key
    import asyncio
    import re

    if not openrouter_api_key():
        raise RuntimeError("Set TBCC_OPENROUTER_API_KEY for OpenRouter provider")

    primary = _openrouter_model()
    fallbacks = _openrouter_fallback_models(primary)
    models = [primary] + [m for m in fallbacks if m != primary]
    last_err: Exception | None = None
    for model in models:
        for attempt in range(2):
            try:
                return await complete_chat_text_async(
                    messages,
                    model=model,
                    max_tokens=_max_tokens(),
                    temperature=_temperature(),
                    timeout=120.0,
                )
            except Exception as e:
                last_err = e
                err = str(e)
                low = err.lower()
                retryable = "429" in err or "rate-limit" in low or "rate limited" in low
                if retryable and attempt == 0 and model == primary:
                    wait_s = 6
                    m = re.search(r"retry_after_seconds(?:_raw)?[\"']?\s*:\s*([0-9.]+)", err)
                    if m:
                        try:
                            wait_s = max(2, min(30, int(float(m.group(1)) + 1)))
                        except ValueError:
                            pass
                    logger.warning("openrouter %s throttled; retry in %ss", model, wait_s)
                    await asyncio.sleep(wait_s)
                    continue
                if retryable and model != models[-1]:
                    logger.warning("openrouter model %s rate-limited; trying fallback", model)
                    break
                if model != models[-1]:
                    logger.warning("openrouter model %s failed: %s; trying fallback", model, e)
                    break
                raise
    if last_err:
        raise last_err
    raise RuntimeError("OpenRouter completion failed")


def _openrouter_fallback_models(primary: str) -> list[str]:
    raw = (os.getenv("TBCC_LLM_CHAT_FALLBACK_MODELS") or "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    # Paid uncensored-ish fallbacks when Venice :free is throttled (uses OpenRouter credits).
    defaults = [
        "gryphe/mythomax-l2-13b",
        "nousresearch/hermes-3-llama-3.1-70b",
    ]
    return [m for m in defaults if m != primary]
