"""Ordered OpenAI-compatible runtimes. Hops with no key are skipped."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.services.llm_completions import TextLlmRuntime, resolve_text_llm_runtime
from app.services.llm_refusal import looks_like_refusal

logger = logging.getLogger(__name__)

# Uncensored-first, then fast hops (Groq/Cerebras/NVIDIA/Mistral — may refuse NSFW), then local/custom, then OpenRouter.
DEFAULT_CHAIN = (
    "zlm",
    "deepinfra",
    "together",
    "groq",
    "cerebras",
    "nvidia",
    "mistral",
    "featherless",
    "venice",
    "anythingllm",
    "custom",
    "openrouter",
)


def _chain_ids() -> list[str]:
    raw = (os.getenv("TBCC_SECRETARY_LLM_FALLBACK") or os.getenv("TBCC_LLM_FALLBACK") or "").strip()
    if not raw:
        return list(DEFAULT_CHAIN)
    out: list[str] = []
    for part in raw.split(","):
        pid = part.strip().lower()
        if pid and pid not in out:
            out.append(pid)
    return out or list(DEFAULT_CHAIN)


def try_resolve_provider(provider: str) -> TextLlmRuntime | None:
    try:
        return resolve_text_llm_runtime(provider=provider)
    except RuntimeError:
        return None


def iter_fallback_runtimes(primary: TextLlmRuntime | None = None) -> list[TextLlmRuntime]:
    seen: set[tuple[str, str, str]] = set()
    out: list[TextLlmRuntime] = []

    def _add(rt: TextLlmRuntime | None, *, require_key: bool) -> None:
        if rt is None:
            return
        api = getattr(rt, "api_key", None)
        if require_key and not str(api or "").strip():
            return
        provider = str(getattr(rt, "provider", "") or "")
        base = str(getattr(rt, "base_url", "") or "").rstrip("/").lower()
        model = str(getattr(rt, "model", "") or "")
        fingerprint = (provider, base, model) if provider else ("stub", str(id(rt)), "")
        if fingerprint in seen:
            return
        seen.add(fingerprint)
        out.append(rt)

    _add(primary, require_key=False)
    for pid in _chain_ids():
        _add(try_resolve_provider(pid), require_key=True)
    return out


async def complete_chat_text_with_fallback(
    messages: list[dict[str, Any]],
    *,
    primary: TextLlmRuntime | None,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    timeout: float = 90.0,
) -> str:
    """Same messages on every hop so the closer voice does not reset to polite-default."""
    from app.services.llm_completions import complete_chat_text_async

    runtimes = iter_fallback_runtimes(primary)
    if not runtimes:
        raise RuntimeError("No LLM providers configured for secretary fallback chain")

    last_err: Exception | None = None
    for i, rt in enumerate(runtimes):
        use_model = model if (i == 0 and model) else None
        try:
            text = await complete_chat_text_async(
                messages,
                model=use_model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                runtime=rt,
            )
        except Exception as exc:
            last_err = exc
            logger.warning(
                "LLM provider %s/%s failed: %s",
                getattr(rt, "provider", "?"),
                getattr(rt, "model", "?"),
                exc,
            )
            continue
        if looks_like_refusal(text) and i < len(runtimes) - 1:
            logger.warning(
                "LLM refusal pattern from %s/%s — rotating provider",
                rt.provider,
                rt.model,
            )
            continue
        return text
    if last_err:
        raise last_err
    raise RuntimeError("All LLM providers refused or returned empty")
