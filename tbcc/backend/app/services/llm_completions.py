"""
Shared OpenAI-compatible chat completions (OpenAI or OpenRouter).

OpenRouter: https://openrouter.ai/api/v1/chat/completions
  - Key: https://openrouter.ai/keys
  - Model ids like cognitivecomputations/dolphin-mistral-24b-venice-edition:free

Env:
  TBCC_LLM_PROVIDER — openai | openrouter (default openai)
  TBCC_OPENROUTER_API_KEY / OPENROUTER_API_KEY
  TBCC_OPENROUTER_BASE_URL — default https://openrouter.ai/api/v1
  TBCC_OPENROUTER_REFERER — optional HTTP-Referer for rankings
  TBCC_OPENROUTER_TITLE — optional X-Title (default TBCC)
  TBCC_LLM_MODEL — model id for the active provider
  TBCC_OPENROUTER_MODEL — default OpenRouter model when TBCC_LLM_MODEL unset
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OPENROUTER_MODEL = "cognitivecomputations/dolphin-mistral-24b-venice-edition:free"


@dataclass(frozen=True)
class TextLlmRuntime:
    provider: str
    api_key: str
    model: str
    base_url: str | None = None
    referer: str | None = None
    title: str | None = None


def openai_api_key() -> str:
    return (os.getenv("TBCC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def openrouter_api_key() -> str:
    return (os.getenv("TBCC_OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "").strip()


def text_llm_provider() -> str:
    return (os.getenv("TBCC_LLM_PROVIDER") or "openai").strip().lower()


def text_llm_configured() -> bool:
    p = text_llm_provider()
    if p == "openrouter":
        return bool(openrouter_api_key())
    if p in ("openai", ""):
        return bool(openai_api_key())
    return False


def resolve_text_model(explicit: str | None = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    global_model = (os.getenv("TBCC_LLM_MODEL") or "").strip()
    if global_model:
        return global_model
    if text_llm_provider() == "openrouter":
        return (os.getenv("TBCC_OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL).strip()
    return "gpt-4o-mini"


def chat_completions_url(runtime: TextLlmRuntime | None = None) -> str:
    if runtime is not None:
        if runtime.base_url:
            return f"{runtime.base_url.rstrip('/')}/chat/completions"
        if runtime.provider == "openrouter":
            return "https://openrouter.ai/api/v1/chat/completions"
        return "https://api.openai.com/v1/chat/completions"
    if text_llm_provider() == "openrouter":
        base = (os.getenv("TBCC_OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        return f"{base}/chat/completions"
    custom = (os.getenv("TBCC_OPENAI_BASE_URL") or os.getenv("TBCC_LLM_BASE_URL") or "").strip().rstrip("/")
    if custom:
        return f"{custom}/chat/completions"
    return "https://api.openai.com/v1/chat/completions"


def chat_completions_headers(runtime: TextLlmRuntime | None = None) -> dict[str, str]:
    if runtime is not None:
        if runtime.provider == "openrouter":
            return {
                "Authorization": f"Bearer {runtime.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": (runtime.referer or "https://tbcc.local").strip(),
                "X-Title": (runtime.title or "TBCC").strip(),
            }
        return {
            "Authorization": f"Bearer {runtime.api_key}",
            "Content-Type": "application/json",
        }
    p = text_llm_provider()
    if p == "openrouter":
        headers = {
            "Authorization": f"Bearer {openrouter_api_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": (os.getenv("TBCC_OPENROUTER_REFERER") or "https://tbcc.local").strip(),
            "X-Title": (os.getenv("TBCC_OPENROUTER_TITLE") or "TBCC").strip(),
        }
        return headers
    return {
        "Authorization": f"Bearer {openai_api_key()}",
        "Content-Type": "application/json",
    }


def _runtime_configured(runtime: TextLlmRuntime | None) -> bool:
    if runtime is not None:
        return bool((runtime.api_key or "").strip())
    return text_llm_configured()


def _resolve_model_for_runtime(model: str | None, runtime: TextLlmRuntime | None) -> str:
    if model and str(model).strip():
        return str(model).strip()
    if runtime is not None:
        return runtime.model
    return resolve_text_model(None)


def _extract_message_text(data: dict[str, Any]) -> str:
    choice0 = (data.get("choices") or [{}])[0]
    msg = choice0.get("message") or {}
    return (msg.get("content") or "").strip()


def post_chat_completions_sync(
    payload: dict[str, Any],
    *,
    timeout: float = 90.0,
    runtime: TextLlmRuntime | None = None,
) -> dict[str, Any]:
    if not _runtime_configured(runtime):
        raise RuntimeError(
            "LLM not configured: set TBCC_OPENROUTER_API_KEY (TBCC_LLM_PROVIDER=openrouter) "
            "or TBCC_OPENAI_API_KEY (openai)"
        )
    if "model" not in payload or not payload.get("model"):
        payload = {**payload, "model": _resolve_model_for_runtime(None, runtime)}
    with httpx.Client(timeout=timeout) as client:
        r = client.post(
            chat_completions_url(runtime),
            headers=chat_completions_headers(runtime),
            json=payload,
        )
        if not r.is_success:
            detail = (r.text or "")[:500]
            prov = runtime.provider if runtime else text_llm_provider()
            logger.warning("LLM HTTP %s (%s): %s", r.status_code, prov, detail)
            raise RuntimeError(f"LLM error {r.status_code}: {detail[:200]}")
        return r.json()


async def post_chat_completions_async(
    payload: dict[str, Any],
    *,
    timeout: float = 90.0,
    runtime: TextLlmRuntime | None = None,
) -> dict[str, Any]:
    if not _runtime_configured(runtime):
        raise RuntimeError(
            "LLM not configured: set TBCC_OPENROUTER_API_KEY (TBCC_LLM_PROVIDER=openrouter) "
            "or TBCC_OPENAI_API_KEY (openai)"
        )
    if "model" not in payload or not payload.get("model"):
        payload = {**payload, "model": _resolve_model_for_runtime(None, runtime)}
    async with httpx.AsyncClient() as client:
        r = await client.post(
            chat_completions_url(runtime),
            headers=chat_completions_headers(runtime),
            json=payload,
            timeout=timeout,
        )
        if not r.is_success:
            detail = (r.text or "")[:500]
            prov = runtime.provider if runtime else text_llm_provider()
            logger.warning("LLM HTTP %s (%s): %s", r.status_code, prov, detail)
            raise RuntimeError(f"LLM error {r.status_code}: {detail[:200]}")
        return r.json()


def complete_chat_text_sync(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    response_format: dict[str, str] | None = None,
    timeout: float = 90.0,
    runtime: TextLlmRuntime | None = None,
) -> str:
    payload: dict[str, Any] = {"model": _resolve_model_for_runtime(model, runtime), "messages": messages}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    if response_format is not None:
        payload["response_format"] = response_format
    data = post_chat_completions_sync(payload, timeout=timeout, runtime=runtime)
    text = _extract_message_text(data)
    if not text:
        raise RuntimeError("LLM returned empty content")
    return text


async def complete_chat_text_async(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    response_format: dict[str, str] | None = None,
    timeout: float = 90.0,
    runtime: TextLlmRuntime | None = None,
) -> str:
    payload: dict[str, Any] = {"model": _resolve_model_for_runtime(model, runtime), "messages": messages}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    if response_format is not None:
        payload["response_format"] = response_format
    data = await post_chat_completions_async(payload, timeout=timeout, runtime=runtime)
    text = _extract_message_text(data)
    if not text:
        raise RuntimeError("LLM returned empty content")
    return text
