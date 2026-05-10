"""
Configurable chat completions for the generic LLM Telegram bridge (llm_chat_bot).

Providers: OpenAI Chat Completions API, or local Ollama /api/chat.

Env (llm_chat_bot):
  TBCC_LLM_CHAT_PROVIDER — openai | ollama (default: ollama)
  TBCC_OPENAI_API_KEY / TBCC_LLM_CHAT_OPENAI_MODEL / TBCC_LLM_CHAT_MAX_TOKENS / TBCC_LLM_CHAT_TEMPERATURE
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
    return (os.getenv("TBCC_LLM_CHAT_OPENAI_MODEL") or os.getenv("TBCC_LLM_MODEL") or "gpt-4o-mini").strip()


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
