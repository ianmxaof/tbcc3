"""
Shared OpenAI-compatible chat completions.

Providers (same /v1/chat/completions shape):
  - openai — api.openai.com
  - openrouter — openrouter.ai (TBCC default uncensored Dolphin/Venice free)
  - featherless — api.featherless.ai (abliterated / Heretic-style HF models)
  - venice — api.venice.ai (venice-uncensored-*)
  - custom — TBCC_LLM_BASE_URL + TBCC_OPENAI_API_KEY (or TBCC_LLM_API_KEY)
  - zlm / glm / zai — Zhipu / Z.ai GLM (OpenAI-compatible)
  - deepinfra — api.deepinfra.com/v1/openai
  - together — api.together.xyz/v1
  - anythingllm — TBCC_ANYTHINGLLM_BASE_URL (OpenAI-compatible workspace)
  - groq — api.groq.com/openai/v1 (TBCC_GROQ_API_KEY / TBCC_GROQ_API)
  - cerebras — api.cerebras.ai/v1 (TBCC_CEREBRAS_API_KEY / TBCC_CEREBRAS_API)
  - nvidia — integrate.api.nvidia.com/v1 NIM (TBCC_NVIDIA_API_KEY / TBCC_NVIDIA_API)
  - mistral — api.mistral.ai/v1 (TBCC_MISTRAL_API_KEY / TBCC_MISTRAL_API)

Env:
  TBCC_LLM_PROVIDER — openai | openrouter | featherless | venice | custom | zlm | deepinfra | together | anythingllm | groq | cerebras | nvidia | mistral
  TBCC_OPENROUTER_API_KEY / OPENROUTER_API_KEY
  TBCC_OPENROUTER_BASE_URL — default https://openrouter.ai/api/v1
  TBCC_FEATHERLESS_API_KEY / FEATHERLESS_API_KEY
  TBCC_VENICE_API_KEY / VENICE_API_KEY
  TBCC_ZLM_API_KEY / TBCC_ZAI_API_KEY / TBCC_GLM_API_KEY
  TBCC_DEEPINFRA_API_KEY / DEEPINFRA_API_KEY
  TBCC_TOGETHER_API_KEY / TOGETHER_API_KEY
  TBCC_GROQ_API_KEY / TBCC_GROQ_API / GROQ_API_KEY
  TBCC_CEREBRAS_API_KEY / TBCC_CEREBRAS_API / CEREBRAS_API_KEY
  TBCC_NVIDIA_API_KEY / TBCC_NVIDIA_API / NVIDIA_API_KEY
  TBCC_MISTRAL_API_KEY / TBCC_MISTRAL_API / MISTRAL_API_KEY
  TBCC_ANYTHINGLLM_API_KEY / TBCC_ANYTHINGLLM_BASE_URL
  TBCC_OPENAI_API_KEY / OPENAI_API_KEY / TBCC_LLM_API_KEY
  TBCC_OPENAI_BASE_URL / TBCC_LLM_BASE_URL — custom or openai-compatible host
  TBCC_LLM_MODEL — model id for the active provider
  TBCC_OPENROUTER_MODEL / TBCC_FEATHERLESS_MODEL / TBCC_VENICE_MODEL — provider defaults
  TBCC_ZLM_MODEL / TBCC_DEEPINFRA_MODEL / TBCC_TOGETHER_MODEL / TBCC_ANYTHINGLLM_MODEL
  TBCC_CEREBRAS_MODEL / TBCC_NVIDIA_MODEL / TBCC_MISTRAL_MODEL
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# OpenRouter Dolphin (paid; ~$0.20/M in, $0.90/M out as of 2026-08). :free tier retired.
DEFAULT_OPENROUTER_MODEL = "cognitivecomputations/dolphin-mistral-24b-venice-edition"
DEFAULT_FEATHERLESS_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"
DEFAULT_VENICE_MODEL = "venice-uncensored-1-2"

# Curated Dolphin slugs on OpenRouter (extend when Cognitive Computations adds more).
OPENROUTER_DOLPHIN_MODELS: tuple[str, ...] = (
    "cognitivecomputations/dolphin-mistral-24b-venice-edition",
)

# Free-only OpenRouter cloud path (no Featherless / no Venice paid).
# Dolphin :free was sunset — use OPENROUTER_DOLPHIN_MODELS with --allow-paid for Dolphin.
FREE_OPENROUTER_CHAT_MODELS: tuple[str, ...] = (
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "google/gemma-4-31b-it:free",
)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
FEATHERLESS_BASE = "https://api.featherless.ai/v1"
VENICE_BASE = "https://api.venice.ai/api/v1"
OPENAI_BASE = "https://api.openai.com/v1"
ZLM_BASE = "https://open.bigmodel.cn/api/paas/v4"
DEEPINFRA_BASE = "https://api.deepinfra.com/v1/openai"
TOGETHER_BASE = "https://api.together.xyz/v1"
GROQ_BASE = "https://api.groq.com/openai/v1"
CEREBRAS_BASE = "https://api.cerebras.ai/v1"
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
MISTRAL_BASE = "https://api.mistral.ai/v1"
DEFAULT_ZLM_MODEL = "glm-4.5"
DEFAULT_DEEPINFRA_MODEL = "cognitivecomputations/dolphin-2.9-llama3-8b"
DEFAULT_TOGETHER_MODEL = "cognitivecomputations/dolphin-2.9-llama3-8b"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
# Cerebras public catalog (2026-08): gpt-oss-120b (text) + gemma-4-31b (vision). Override with TBCC_CEREBRAS_MODEL.
DEFAULT_CEREBRAS_MODEL = "gpt-oss-120b"
DEFAULT_NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
DEFAULT_MISTRAL_MODEL = "mistral-small-latest"


@dataclass(frozen=True)
class TextLlmRuntime:
    provider: str
    api_key: str
    model: str
    base_url: str | None = None
    referer: str | None = None
    title: str | None = None


def is_openrouter_free_model(model: str | None) -> bool:
    mid = (model or "").strip().lower()
    if not mid:
        return False
    if mid == "openrouter/free":
        return True
    return mid.endswith(":free")


def assert_free_only_runtime(runtime: TextLlmRuntime) -> None:
    """Raise if runtime is not a $0 OpenRouter cloud path."""
    p = (runtime.provider or "").strip().lower()
    if p != "openrouter":
        raise RuntimeError(
            f"free-only mode allows provider=openrouter only (got {p!r}). "
            "Paid Featherless/Venice need --allow-paid."
        )
    if not is_openrouter_free_model(runtime.model):
        raise RuntimeError(
            f"free-only mode requires an OpenRouter :free model (got {runtime.model!r}). "
            "Pick from FREE_OPENROUTER_CHAT_MODELS or pass --allow-paid."
        )


def free_openrouter_fallback_models(preferred: str | None = None) -> list[str]:
    """Ordered free models to try (preferred first, then curated chain, deduped)."""
    out: list[str] = []
    for mid in ((preferred or "").strip(), *FREE_OPENROUTER_CHAT_MODELS):
        if mid and mid not in out and is_openrouter_free_model(mid):
            out.append(mid)
    return out


def openai_api_key() -> str:
    return (
        os.getenv("TBCC_OPENAI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("TBCC_LLM_API_KEY")
        or ""
    ).strip()


def openrouter_api_key() -> str:
    return (os.getenv("TBCC_OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY") or "").strip()


def featherless_api_key() -> str:
    return (os.getenv("TBCC_FEATHERLESS_API_KEY") or os.getenv("FEATHERLESS_API_KEY") or "").strip()


def venice_api_key() -> str:
    return (os.getenv("TBCC_VENICE_API_KEY") or os.getenv("VENICE_API_KEY") or "").strip()


def zlm_api_key() -> str:
    return (
        os.getenv("TBCC_ZLM_API_KEY")
        or os.getenv("TBCC_ZAI_API_KEY")
        or os.getenv("TBCC_GLM_API_KEY")
        or os.getenv("ZHIPUAI_API_KEY")
        or ""
    ).strip()


def deepinfra_api_key() -> str:
    return (
        os.getenv("TBCC_DEEPINFRA_API_KEY")
        or os.getenv("DEEPINFRA_API_KEY")
        or os.getenv("TBCC_DEEPINFRA_API")
        or ""
    ).strip()


def together_api_key() -> str:
    return (os.getenv("TBCC_TOGETHER_API_KEY") or os.getenv("TOGETHER_API_KEY") or "").strip()


def groq_api_key() -> str:
    return (
        os.getenv("TBCC_GROQ_API_KEY")
        or os.getenv("TBCC_GROQ_API")
        or os.getenv("GROQ_API_KEY")
        or ""
    ).strip()


def cerebras_api_key() -> str:
    return (
        os.getenv("TBCC_CEREBRAS_API_KEY")
        or os.getenv("TBCC_CEREBRAS_API")
        or os.getenv("CEREBRAS_API_KEY")
        or ""
    ).strip()


def nvidia_api_key() -> str:
    return (
        os.getenv("TBCC_NVIDIA_API_KEY")
        or os.getenv("TBCC_NVIDIA_API")
        or os.getenv("NVIDIA_API_KEY")
        or os.getenv("NIM_API_KEY")
        or ""
    ).strip()


def mistral_api_key() -> str:
    return (
        os.getenv("TBCC_MISTRAL_API_KEY")
        or os.getenv("TBCC_MISTRAL_API")
        or os.getenv("MISTRAL_API_KEY")
        or ""
    ).strip()


def anythingllm_api_key() -> str:
    return (os.getenv("TBCC_ANYTHINGLLM_API_KEY") or os.getenv("ANYTHINGLLM_API_KEY") or "").strip()


def text_llm_provider() -> str:
    return (os.getenv("TBCC_LLM_PROVIDER") or "openai").strip().lower()


def text_llm_configured() -> bool:
    try:
        resolve_text_llm_runtime()
        return True
    except RuntimeError:
        return False


def resolve_text_model(explicit: str | None = None, *, provider: str | None = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    p = (provider or text_llm_provider()).strip().lower()
    # TBCC_LLM_MODEL is the active-provider override — ignore it when CLI/API
    # switches to a different provider without an explicit model id.
    global_model = (os.getenv("TBCC_LLM_MODEL") or "").strip()
    if global_model and (provider is None or p == text_llm_provider()):
        return global_model
    if p == "openrouter":
        return (os.getenv("TBCC_OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL).strip()
    if p == "featherless":
        return (os.getenv("TBCC_FEATHERLESS_MODEL") or DEFAULT_FEATHERLESS_MODEL).strip()
    if p == "venice":
        return (os.getenv("TBCC_VENICE_MODEL") or DEFAULT_VENICE_MODEL).strip()
    if p in ("zlm", "glm", "zai"):
        return (os.getenv("TBCC_ZLM_MODEL") or os.getenv("TBCC_GLM_MODEL") or DEFAULT_ZLM_MODEL).strip()
    if p == "deepinfra":
        return (os.getenv("TBCC_DEEPINFRA_MODEL") or DEFAULT_DEEPINFRA_MODEL).strip()
    if p == "together":
        return (os.getenv("TBCC_TOGETHER_MODEL") or DEFAULT_TOGETHER_MODEL).strip()
    if p == "groq":
        return (os.getenv("TBCC_GROQ_MODEL") or DEFAULT_GROQ_MODEL).strip()
    if p == "cerebras":
        return (os.getenv("TBCC_CEREBRAS_MODEL") or DEFAULT_CEREBRAS_MODEL).strip()
    if p in ("nvidia", "nim"):
        return (os.getenv("TBCC_NVIDIA_MODEL") or os.getenv("TBCC_NIM_MODEL") or DEFAULT_NVIDIA_MODEL).strip()
    if p == "mistral":
        return (os.getenv("TBCC_MISTRAL_MODEL") or DEFAULT_MISTRAL_MODEL).strip()
    if p == "anythingllm":
        return (os.getenv("TBCC_ANYTHINGLLM_MODEL") or "anythingllm").strip()
    return "gpt-4o-mini"


def resolve_text_llm_runtime(
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> TextLlmRuntime:
    """Build a TextLlmRuntime for any supported OpenAI-compatible host."""
    p = (provider or text_llm_provider() or "openai").strip().lower()
    if p in ("local",):
        p = "openai"
    referer = (os.getenv("TBCC_OPENROUTER_REFERER") or "https://tbcc.local").strip()
    title = (os.getenv("TBCC_OPENROUTER_TITLE") or "TBCC").strip()

    if p == "openrouter":
        key = (api_key or openrouter_api_key()).strip()
        if not key:
            raise RuntimeError("Set TBCC_OPENROUTER_API_KEY for OpenRouter")
        base = (base_url or os.getenv("TBCC_OPENROUTER_BASE_URL") or OPENROUTER_BASE).strip().rstrip("/")
        return TextLlmRuntime(
            provider="openrouter",
            api_key=key,
            model=resolve_text_model(model, provider="openrouter"),
            base_url=base,
            referer=referer,
            title=title,
        )

    if p == "featherless":
        key = (api_key or featherless_api_key()).strip()
        if not key:
            raise RuntimeError("Set TBCC_FEATHERLESS_API_KEY (or FEATHERLESS_API_KEY)")
        base = (base_url or os.getenv("TBCC_FEATHERLESS_BASE_URL") or FEATHERLESS_BASE).strip().rstrip("/")
        return TextLlmRuntime(
            provider="featherless",
            api_key=key,
            model=resolve_text_model(model, provider="featherless"),
            base_url=base,
            referer=referer,
            title=title or "TBCC",
        )

    if p == "venice":
        key = (api_key or venice_api_key()).strip()
        if not key:
            raise RuntimeError("Set TBCC_VENICE_API_KEY (or VENICE_API_KEY)")
        base = (base_url or os.getenv("TBCC_VENICE_BASE_URL") or VENICE_BASE).strip().rstrip("/")
        return TextLlmRuntime(
            provider="venice",
            api_key=key,
            model=resolve_text_model(model, provider="venice"),
            base_url=base,
        )

    if p in ("zlm", "glm", "zai"):
        key = (api_key or zlm_api_key()).strip()
        if not key:
            raise RuntimeError("Set TBCC_ZLM_API_KEY (or TBCC_ZAI_API_KEY / TBCC_GLM_API_KEY)")
        base = (base_url or os.getenv("TBCC_ZLM_BASE_URL") or os.getenv("TBCC_ZAI_BASE_URL") or ZLM_BASE).strip().rstrip("/")
        return TextLlmRuntime(
            provider="zlm",
            api_key=key,
            model=resolve_text_model(model, provider="zlm"),
            base_url=base,
        )

    if p == "deepinfra":
        key = (api_key or deepinfra_api_key()).strip()
        if not key:
            raise RuntimeError("Set TBCC_DEEPINFRA_API_KEY (or DEEPINFRA_API_KEY)")
        base = (base_url or os.getenv("TBCC_DEEPINFRA_BASE_URL") or DEEPINFRA_BASE).strip().rstrip("/")
        return TextLlmRuntime(
            provider="deepinfra",
            api_key=key,
            model=resolve_text_model(model, provider="deepinfra"),
            base_url=base,
        )

    if p == "together":
        key = (api_key or together_api_key()).strip()
        if not key:
            raise RuntimeError("Set TBCC_TOGETHER_API_KEY (or TOGETHER_API_KEY)")
        base = (base_url or os.getenv("TBCC_TOGETHER_BASE_URL") or TOGETHER_BASE).strip().rstrip("/")
        return TextLlmRuntime(
            provider="together",
            api_key=key,
            model=resolve_text_model(model, provider="together"),
            base_url=base,
        )

    if p == "groq":
        key = (api_key or groq_api_key()).strip()
        if not key:
            raise RuntimeError("Set TBCC_GROQ_API_KEY (or TBCC_GROQ_API / GROQ_API_KEY)")
        base = (base_url or os.getenv("TBCC_GROQ_BASE_URL") or GROQ_BASE).strip().rstrip("/")
        return TextLlmRuntime(
            provider="groq",
            api_key=key,
            model=resolve_text_model(model, provider="groq"),
            base_url=base,
        )

    if p == "cerebras":
        key = (api_key or cerebras_api_key()).strip()
        if not key:
            raise RuntimeError("Set TBCC_CEREBRAS_API_KEY (or TBCC_CEREBRAS_API / CEREBRAS_API_KEY)")
        base = (base_url or os.getenv("TBCC_CEREBRAS_BASE_URL") or CEREBRAS_BASE).strip().rstrip("/")
        return TextLlmRuntime(
            provider="cerebras",
            api_key=key,
            model=resolve_text_model(model, provider="cerebras"),
            base_url=base,
        )

    if p in ("nvidia", "nim"):
        key = (api_key or nvidia_api_key()).strip()
        if not key:
            raise RuntimeError("Set TBCC_NVIDIA_API_KEY (or TBCC_NVIDIA_API / NVIDIA_API_KEY)")
        base = (base_url or os.getenv("TBCC_NVIDIA_BASE_URL") or os.getenv("TBCC_NIM_BASE_URL") or NVIDIA_BASE).strip().rstrip("/")
        return TextLlmRuntime(
            provider="nvidia",
            api_key=key,
            model=resolve_text_model(model, provider="nvidia"),
            base_url=base,
        )

    if p == "mistral":
        key = (api_key or mistral_api_key()).strip()
        if not key:
            raise RuntimeError("Set TBCC_MISTRAL_API_KEY (or TBCC_MISTRAL_API / MISTRAL_API_KEY)")
        base = (base_url or os.getenv("TBCC_MISTRAL_BASE_URL") or MISTRAL_BASE).strip().rstrip("/")
        return TextLlmRuntime(
            provider="mistral",
            api_key=key,
            model=resolve_text_model(model, provider="mistral"),
            base_url=base,
        )

    if p == "anythingllm":
        key = (api_key or anythingllm_api_key() or "local").strip()
        base = (base_url or os.getenv("TBCC_ANYTHINGLLM_BASE_URL") or "").strip().rstrip("/")
        if not base:
            raise RuntimeError("Set TBCC_ANYTHINGLLM_BASE_URL for AnythingLLM / custom inference")
        return TextLlmRuntime(
            provider="anythingllm",
            api_key=key,
            model=resolve_text_model(model, provider="anythingllm"),
            base_url=base,
        )

    if p in ("openai", "custom", ""):
        key = (api_key or openai_api_key()).strip()
        custom = (
            base_url
            or os.getenv("TBCC_OPENAI_BASE_URL")
            or os.getenv("TBCC_LLM_BASE_URL")
            or ""
        ).strip().rstrip("/")
        if p == "custom" and not custom:
            raise RuntimeError("custom provider needs TBCC_LLM_BASE_URL or --base-url")
        if not key and custom:
            # Some local proxies ignore auth; still require a placeholder bearer.
            key = (os.getenv("TBCC_LLM_API_KEY") or "local").strip()
        if not key:
            raise RuntimeError("Set TBCC_OPENAI_API_KEY (or TBCC_LLM_API_KEY)")
        return TextLlmRuntime(
            provider="openai" if not custom else "custom",
            api_key=key,
            model=resolve_text_model(model, provider="openai"),
            base_url=custom or OPENAI_BASE,
        )

    raise RuntimeError(
        f"Unknown TBCC_LLM_PROVIDER={p!r}; use openai|openrouter|featherless|venice|custom|zlm|deepinfra|together|groq|cerebras|nvidia|mistral|anythingllm"
    )


def chat_completions_url(runtime: TextLlmRuntime | None = None) -> str:
    if runtime is not None:
        base = (runtime.base_url or "").rstrip("/")
        if base:
            return f"{base}/chat/completions"
        if runtime.provider == "openrouter":
            return f"{OPENROUTER_BASE}/chat/completions"
        if runtime.provider == "featherless":
            return f"{FEATHERLESS_BASE}/chat/completions"
        if runtime.provider == "venice":
            return f"{VENICE_BASE}/chat/completions"
        return f"{OPENAI_BASE}/chat/completions"
    return chat_completions_url(resolve_text_llm_runtime())


def chat_completions_headers(runtime: TextLlmRuntime | None = None) -> dict[str, str]:
    rt = runtime or resolve_text_llm_runtime()
    headers = {
        "Authorization": f"Bearer {rt.api_key}",
        "Content-Type": "application/json",
    }
    if rt.provider in ("openrouter", "featherless") or rt.referer or rt.title:
        headers["HTTP-Referer"] = (rt.referer or "https://tbcc.local").strip()
        headers["X-Title"] = (rt.title or "TBCC").strip()
    return headers


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
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()
    return (content or "").strip()


def _ensure_runtime(runtime: TextLlmRuntime | None) -> TextLlmRuntime:
    if runtime is not None:
        if not (runtime.api_key or "").strip():
            raise RuntimeError("LLM runtime missing api_key")
        return runtime
    return resolve_text_llm_runtime()


def post_chat_completions_sync(
    payload: dict[str, Any],
    *,
    timeout: float = 90.0,
    runtime: TextLlmRuntime | None = None,
) -> dict[str, Any]:
    rt = _ensure_runtime(runtime)
    if "model" not in payload or not payload.get("model"):
        payload = {**payload, "model": _resolve_model_for_runtime(None, rt)}
    with httpx.Client(timeout=timeout) as client:
        r = client.post(
            chat_completions_url(rt),
            headers=chat_completions_headers(rt),
            json=payload,
        )
        if not r.is_success:
            detail = (r.text or "")[:500]
            logger.warning("LLM HTTP %s (%s): %s", r.status_code, rt.provider, detail)
            raise RuntimeError(f"LLM error {r.status_code}: {detail[:200]}")
        return r.json()


async def post_chat_completions_async(
    payload: dict[str, Any],
    *,
    timeout: float = 90.0,
    runtime: TextLlmRuntime | None = None,
) -> dict[str, Any]:
    rt = _ensure_runtime(runtime)
    if "model" not in payload or not payload.get("model"):
        payload = {**payload, "model": _resolve_model_for_runtime(None, rt)}
    async with httpx.AsyncClient() as client:
        r = await client.post(
            chat_completions_url(rt),
            headers=chat_completions_headers(rt),
            json=payload,
            timeout=timeout,
        )
        if not r.is_success:
            detail = (r.text or "")[:500]
            logger.warning("LLM HTTP %s (%s): %s", r.status_code, rt.provider, detail)
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
