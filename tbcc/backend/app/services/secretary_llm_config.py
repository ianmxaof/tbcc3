"""Secretary-specific LLM runtime (dashboard + Telegram overrides with env fallbacks)."""

from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.services.llm_completions import (
    TextLlmRuntime,
    _extract_message_text,
    chat_completions_url,
    openai_api_key,
    openrouter_api_key,
    post_chat_completions_sync,
    resolve_text_model,
    text_llm_configured,
    text_llm_provider,
)
from app.services.secretary_settings_effective import ensure_settings_row, get_effective_secretary_settings

COMETAPI_DEFAULT_BASE = "https://api.cometapi.com/v1"
COMETAPI_DEFAULT_MODEL = "gpt-4o-mini"
OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
OPENROUTER_DEFAULT_BASE = "https://openrouter.ai/api/v1"
HCNSEC_DEFAULT_BASE = "https://api.hcnsec.cn/v1"
HCNSEC_DEFAULT_MODEL = "step-3.5-flash"


def cometapi_api_key() -> str:
    return (os.getenv("TBCC_COMETAPI_API_KEY") or os.getenv("COMETAPI_API_KEY") or "").strip()


def custom_gateway_api_key() -> str:
    """Third-party OpenAI-compatible gateway key (hcnsec / Model Square credits)."""
    return (os.getenv("TBCC_LLM_API_KEY") or "").strip()


def custom_gateway_base_url() -> str | None:
    raw = (os.getenv("TBCC_LLM_BASE_URL") or os.getenv("TBCC_OPENAI_BASE_URL") or "").strip()
    if not raw:
        return None
    try:
        return normalize_llm_base_url(raw)
    except ValueError:
        return None


def openai_only_api_key() -> str:
    """OpenAI.com key only — never TBCC_LLM_API_KEY (may be a third-party proxy)."""
    return (os.getenv("TBCC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def env_llm_preset_catalog() -> list[dict[str, Any]]:
    """Env-backed presets the operator can one-tap without pasting keys in Telegram."""
    or_key = openrouter_api_key()
    oa_key = openai_only_api_key()
    custom_key = custom_gateway_api_key()
    custom_base = custom_gateway_base_url() or HCNSEC_DEFAULT_BASE
    comet_key = cometapi_api_key()
    custom_model = (os.getenv("TBCC_LLM_MODEL") or "").strip() or HCNSEC_DEFAULT_MODEL
    return [
        {
            "id": "hcnsec",
            "label": "Hcnsec (env)",
            "available": bool(custom_key and custom_gateway_base_url()),
            "api_key_hint": _mask_api_key(custom_key) if custom_key else None,
            "model": custom_model,
            "base_url": custom_base,
        },
        {
            "id": "openrouter",
            "label": "OpenRouter (env)",
            "available": bool(or_key),
            "api_key_hint": _mask_api_key(or_key) if or_key else None,
            "model": (os.getenv("TBCC_OPENROUTER_MODEL") or "").strip() or "openai/gpt-4o-mini",
            "base_url": OPENROUTER_DEFAULT_BASE,
        },
        {
            "id": "openai",
            "label": "OpenAI (env)",
            "available": bool(oa_key),
            "api_key_hint": _mask_api_key(oa_key) if oa_key else None,
            "model": (os.getenv("TBCC_SECRETARY_LLM_MODEL") or "").strip() or "gpt-4o-mini",
            "base_url": OPENAI_DEFAULT_BASE,
        },
        {
            "id": "cometapi",
            "label": "CometAPI (env)",
            "available": bool(comet_key),
            "api_key_hint": _mask_api_key(comet_key) if comet_key else None,
            "model": COMETAPI_DEFAULT_MODEL,
            "base_url": COMETAPI_DEFAULT_BASE,
        },
    ]


def is_cometapi_base_url(base_url: str | None) -> bool:
    return "cometapi.com" in (base_url or "").lower()


def is_openrouter_base_url(base_url: str | None) -> bool:
    return "openrouter.ai" in (base_url or "").lower()


def is_hcnsec_base_url(base_url: str | None) -> bool:
    return "hcnsec.cn" in (base_url or "").lower()


def is_custom_gateway_base_url(base_url: str | None) -> bool:
    """Non-OpenAI / non-OpenRouter OpenAI-compatible hosts (hcnsec, etc.)."""
    if not base_url:
        return False
    if is_openrouter_base_url(base_url) or "api.openai.com" in base_url.lower():
        return False
    return True


def fetch_cometapi_account_quota(api_key: str) -> dict[str, Any] | None:
    """CometAPI balance API — separate host, key as query param (not Bearer)."""
    key = (api_key or "").strip()
    if not key:
        return None
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get("https://query.cometapi.com/user/quota", params={"key": key})
            if r.is_success:
                data = r.json()
                return data if isinstance(data, dict) else None
    except Exception:
        pass
    return None


def infer_provider_for_base_url(base_url: str | None, explicit: str | None = None) -> str:
    if explicit and str(explicit).strip().lower() in _LLM_PROVIDERS:
        return str(explicit).strip().lower()
    if is_cometapi_base_url(base_url):
        return "openai"
    return "openai"

_LLM_PROVIDERS = ("openai", "openrouter")
_KEY_MIN_LEN = 8
_KEY_MAX_LEN = 512
_URL_MAX_LEN = 256
_MODEL_MAX_LEN = 128


def _mask_api_key(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 8:
        return "••••"
    return f"{k[:4]}…{k[-4:]}"


def normalize_llm_base_url(raw: str | None) -> str | None:
    """Normalize OpenAI-compatible API base (no trailing /chat/completions)."""
    u = (raw or "").strip()
    if not u:
        return None
    u = u.rstrip("/")
    if u.lower().endswith("/chat/completions"):
        u = u[: -len("/chat/completions")].rstrip("/")
    if not re.match(r"^https?://", u, re.I):
        raise ValueError("Endpoint URL must start with http:// or https://")
    # CometAPI OpenAI-compatible surface lives under /v1 (bare host → 404 Invalid URL).
    if re.fullmatch(r"https?://api\.cometapi\.com", u, re.I):
        u = u.rstrip("/") + "/v1"
    if len(u) > _URL_MAX_LEN:
        raise ValueError(f"Endpoint URL too long (max {_URL_MAX_LEN})")
    return u


def normalize_llm_model_id(raw: str | None) -> str | None:
    """Take first non-empty line only (Telegram pastes often glue two model ids)."""
    if raw is None:
        return None
    for line in str(raw).replace("\r", "\n").split("\n"):
        cleaned = line.strip()
        if cleaned:
            if len(cleaned) > _MODEL_MAX_LEN:
                raise ValueError(f"Model id too long (max {_MODEL_MAX_LEN})")
            return cleaned
    return None


def _validate_api_key(key: str) -> str:
    cleaned = (key or "").strip()
    if len(cleaned) < _KEY_MIN_LEN:
        raise ValueError(f"API key too short (min {_KEY_MIN_LEN} characters)")
    if len(cleaned) > _KEY_MAX_LEN:
        raise ValueError(f"API key too long (max {_KEY_MAX_LEN})")
    return cleaned


def resolve_secretary_text_llm_runtime(db: Session | None = None) -> TextLlmRuntime | None:
    """Return secretary LLM credentials; None when nothing is configured."""
    eff = get_effective_secretary_settings(db)
    provider = str(eff.get("llm_provider") or text_llm_provider() or "openai").strip().lower()
    if provider not in _LLM_PROVIDERS:
        provider = "openai"

    api_key = str(eff.get("llm_api_key") or "").strip()
    base_url = str(eff.get("llm_base_url") or "").strip() or None
    if base_url:
        try:
            base_url = normalize_llm_base_url(base_url)
        except ValueError:
            base_url = None
    elif provider == "openrouter":
        base_url = normalize_llm_base_url(
            os.getenv("TBCC_OPENROUTER_BASE_URL") or OPENROUTER_DEFAULT_BASE
        )

    # Base URL wins over a stale provider field (e.g. openai + openrouter URL).
    if is_openrouter_base_url(base_url):
        provider = "openrouter"
    elif is_custom_gateway_base_url(base_url):
        # Comet / hcnsec / other proxies: OpenAI-compatible, no OpenRouter headers.
        provider = "openai"

    if not api_key:
        if provider == "openrouter" or is_openrouter_base_url(base_url):
            api_key = openrouter_api_key()
        elif is_cometapi_base_url(base_url):
            api_key = cometapi_api_key() or custom_gateway_api_key()
        elif is_custom_gateway_base_url(base_url) or is_hcnsec_base_url(base_url):
            api_key = custom_gateway_api_key() or openai_api_key()
        else:
            api_key = openai_only_api_key() or openai_api_key()
    if not api_key:
        return None

    model = normalize_llm_model_id(str(eff.get("llm_model") or "")) or ""
    if not model:
        # Prefer secretary/openrouter model envs — TBCC_LLM_MODEL may be a custom-proxy id
        # (e.g. step-3.5-flash) that is invalid on OpenRouter.
        if provider == "openrouter":
            model = (
                (os.getenv("TBCC_SECRETARY_LLM_MODEL") or "").strip()
                or (os.getenv("TBCC_OPENROUTER_MODEL") or "").strip()
                or "openai/gpt-4o-mini"
            )
        elif is_custom_gateway_base_url(base_url):
            model = (
                (os.getenv("TBCC_LLM_MODEL") or "").strip()
                or (os.getenv("TBCC_SECRETARY_LLM_MODEL") or "").strip()
                or HCNSEC_DEFAULT_MODEL
            )
        else:
            model = resolve_text_model(os.getenv("TBCC_SECRETARY_LLM_MODEL") or None)

    # CometAPI default model when unset.
    if is_cometapi_base_url(base_url) and not normalize_llm_model_id(str(eff.get("llm_model") or "")):
        model = COMETAPI_DEFAULT_MODEL

    return TextLlmRuntime(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        # Only OpenRouter needs these referer headers; omit for custom gateways.
        referer=(os.getenv("TBCC_OPENROUTER_REFERER") or "https://tbcc.local").strip()
        if provider == "openrouter"
        else "",
        title=(os.getenv("TBCC_OPENROUTER_TITLE") or "TBCC Secretary").strip()
        if provider == "openrouter"
        else "",
    )


def build_text_llm_runtime(
    *,
    api_key: str,
    provider: str = "openai",
    model: str | None = None,
    base_url: str | None = None,
) -> TextLlmRuntime:
    prov = (provider or "openai").strip().lower()
    if prov not in _LLM_PROVIDERS:
        prov = "openai"
    key = _validate_api_key(api_key)
    m = (model or "").strip() or resolve_text_model(os.getenv("TBCC_SECRETARY_LLM_MODEL") or None)
    if len(m) > _MODEL_MAX_LEN:
        raise ValueError(f"Model id too long (max {_MODEL_MAX_LEN})")
    url = normalize_llm_base_url(base_url) if base_url else None
    if not url and prov == "openrouter":
        url = normalize_llm_base_url(
            os.getenv("TBCC_OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
        )
    return TextLlmRuntime(
        provider=prov,
        api_key=key,
        model=m,
        base_url=url,
        referer=(os.getenv("TBCC_OPENROUTER_REFERER") or "https://tbcc.local").strip(),
        title=(os.getenv("TBCC_OPENROUTER_TITLE") or "TBCC Secretary").strip(),
    )


def secretary_llm_configured(db: Session | None = None) -> bool:
    return resolve_secretary_text_llm_runtime(db) is not None or text_llm_configured()


def secretary_llm_status(db: Session | None = None) -> dict[str, Any]:
    eff = get_effective_secretary_settings(db)
    runtime = resolve_secretary_text_llm_runtime(db)
    key = str(eff.get("llm_api_key") or "").strip()
    if not key and runtime:
        key = runtime.api_key
    endpoint = chat_completions_url(runtime) if runtime else None
    return {
        "provider": eff.get("llm_provider") or text_llm_provider(),
        "model": eff.get("llm_model") or (runtime.model if runtime else resolve_text_model(None)),
        "base_url": eff.get("llm_base_url") or (runtime.base_url if runtime else None),
        "endpoint_url": endpoint,
        "configured": secretary_llm_configured(db),
        "api_key_override": bool(str(eff.get("llm_api_key") or "").strip()),
        "api_key_hint": _mask_api_key(key) if key else None,
    }


def persist_llm_api_key(api_key: str) -> dict[str, Any]:
    cleaned = _validate_api_key(api_key)
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_api_key = cleaned
        db.commit()
        return {"ok": True, "api_key_hint": _mask_api_key(cleaned)}
    finally:
        db.close()


def persist_llm_base_url(base_url: str | None) -> dict[str, Any]:
    cleaned = normalize_llm_base_url(base_url) if (base_url or "").strip() else None
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_base_url = cleaned
        if is_cometapi_base_url(cleaned):
            row.llm_provider = "openai"
            if not (row.llm_model or "").strip():
                row.llm_model = COMETAPI_DEFAULT_MODEL
        db.commit()
        endpoint = None
        runtime = resolve_secretary_text_llm_runtime(db)
        if runtime:
            endpoint = chat_completions_url(runtime)
        return {"ok": True, "base_url": cleaned, "endpoint_url": endpoint, "provider": row.llm_provider}
    finally:
        db.close()


def apply_cometapi_preset() -> dict[str, Any]:
    """One-tap CometAPI OpenAI-compatible settings."""
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_base_url = COMETAPI_DEFAULT_BASE
        row.llm_provider = "openai"
        if not (row.llm_model or "").strip():
            row.llm_model = COMETAPI_DEFAULT_MODEL
        db.commit()
        runtime = resolve_secretary_text_llm_runtime(db)
        return {
            "ok": True,
            "base_url": COMETAPI_DEFAULT_BASE,
            "provider": "openai",
            "model": row.llm_model,
            "endpoint_url": chat_completions_url(runtime) if runtime else f"{COMETAPI_DEFAULT_BASE}/chat/completions",
        }
    finally:
        db.close()


def persist_llm_provider(provider: str) -> dict[str, Any]:
    prov = (provider or "").strip().lower()
    if prov not in _LLM_PROVIDERS:
        raise ValueError("provider must be openai or openrouter")
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_provider = prov
        db.commit()
        return {"ok": True, "provider": prov}
    finally:
        db.close()


def persist_llm_model(model: str | None) -> dict[str, Any]:
    cleaned = normalize_llm_model_id(model)
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_model = cleaned
        db.commit()
        return {"ok": True, "model": cleaned or resolve_text_model(None)}
    finally:
        db.close()


def apply_openrouter_preset(*, model: str | None = None) -> dict[str, Any]:
    """Point secretary at OpenRouter (env key) with a known-good default model."""
    cleaned_model = normalize_llm_model_id(model) or (
        (os.getenv("TBCC_OPENROUTER_MODEL") or "").strip() or "openai/gpt-4o-mini"
    )
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_provider = "openrouter"
        row.llm_base_url = OPENROUTER_DEFAULT_BASE
        row.llm_model = cleaned_model
        # Drop dashboard keys so env TBCC_OPENROUTER_API_KEY is used.
        row.llm_api_key = None
        db.commit()
        runtime = resolve_secretary_text_llm_runtime(db)
        return {
            "ok": True,
            "preset": "openrouter",
            "provider": "openrouter",
            "model": cleaned_model,
            "base_url": OPENROUTER_DEFAULT_BASE,
            "endpoint_url": chat_completions_url(runtime) if runtime else None,
            "configured": runtime is not None,
            "api_key_hint": _mask_api_key(runtime.api_key) if runtime else None,
        }
    finally:
        db.close()


def apply_openai_env_preset(*, model: str | None = None) -> dict[str, Any]:
    """OpenAI.com via env TBCC_OPENAI_API_KEY — never TBCC_LLM_API_KEY."""
    cleaned_model = normalize_llm_model_id(model) or (
        (os.getenv("TBCC_SECRETARY_LLM_MODEL") or "").strip() or "gpt-4o-mini"
    )
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_provider = "openai"
        row.llm_base_url = None
        row.llm_model = cleaned_model
        row.llm_api_key = None
        db.commit()
        runtime = resolve_secretary_text_llm_runtime(db)
        key = openai_only_api_key()
        return {
            "ok": True,
            "preset": "openai",
            "provider": "openai",
            "model": cleaned_model,
            "base_url": OPENAI_DEFAULT_BASE,
            "endpoint_url": chat_completions_url(runtime) if runtime else None,
            "configured": runtime is not None,
            "api_key_hint": _mask_api_key(key) if key else None,
            "missing_env": None if key else "TBCC_OPENAI_API_KEY",
        }
    finally:
        db.close()


def apply_cometapi_env_preset(*, model: str | None = None) -> dict[str, Any]:
    """CometAPI OpenAI-compatible gateway — env key or dashboard override."""
    cleaned_model = normalize_llm_model_id(model) or COMETAPI_DEFAULT_MODEL
    env_key = cometapi_api_key()
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_base_url = COMETAPI_DEFAULT_BASE
        row.llm_provider = "openai"
        row.llm_model = cleaned_model
        row.llm_api_key = env_key or None
        db.commit()
        runtime = resolve_secretary_text_llm_runtime(db)
        return {
            "ok": True,
            "preset": "cometapi",
            "provider": "openai",
            "model": cleaned_model,
            "base_url": COMETAPI_DEFAULT_BASE,
            "endpoint_url": chat_completions_url(runtime) if runtime else None,
            "configured": runtime is not None,
            "api_key_hint": _mask_api_key(env_key) if env_key else None,
            "missing_env": None if env_key else "TBCC_COMETAPI_API_KEY",
        }
    finally:
        db.close()


def apply_hcnsec_env_preset(*, model: str | None = None) -> dict[str, Any]:
    """
    Hcnsec / Model Square gateway (TBCC_LLM_BASE_URL + TBCC_LLM_API_KEY).

    This is the credit wallet at https://api.hcnsec.cn — swap models via Model Square
    ids (Set model id). Same lane companion spicy chat already uses.
    """
    base = custom_gateway_base_url() or HCNSEC_DEFAULT_BASE
    cleaned_model = normalize_llm_model_id(model) or (
        (os.getenv("TBCC_LLM_MODEL") or "").strip() or HCNSEC_DEFAULT_MODEL
    )
    env_key = custom_gateway_api_key()
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_provider = "openai"
        row.llm_base_url = base
        row.llm_model = cleaned_model
        # Prefer env key — clear stale Comet/OpenRouter dashboard pastes.
        row.llm_api_key = None
        db.commit()
        runtime = resolve_secretary_text_llm_runtime(db)
        return {
            "ok": True,
            "preset": "hcnsec",
            "provider": "openai",
            "model": cleaned_model,
            "base_url": base,
            "endpoint_url": chat_completions_url(runtime) if runtime else f"{base}/chat/completions",
            "configured": runtime is not None,
            "api_key_hint": _mask_api_key(env_key) if env_key else None,
            "missing_env": None if env_key else "TBCC_LLM_API_KEY",
        }
    finally:
        db.close()


def apply_env_llm_preset(preset_id: str, *, model: str | None = None) -> dict[str, Any]:
    """One-tap env preset: hcnsec | openrouter | openai | cometapi."""
    pid = (preset_id or "").strip().lower()
    if pid in ("hcnsec", "custom", "gateway"):
        return apply_hcnsec_env_preset(model=model)
    if pid == "openrouter":
        return apply_openrouter_preset(model=model)
    if pid == "openai":
        return apply_openai_env_preset(model=model)
    if pid == "cometapi":
        return apply_cometapi_env_preset(model=model)
    raise ValueError(f"Unknown env preset: {preset_id!r}")


def clear_llm_api_key_override() -> dict[str, Any]:
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_api_key = None
        db.commit()
        return {"ok": True}
    finally:
        db.close()


def clear_llm_base_url_override() -> dict[str, Any]:
    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.llm_base_url = None
        db.commit()
        return {"ok": True}
    finally:
        db.close()


def probe_secretary_llm(
    *,
    db: Session | None = None,
    runtime: TextLlmRuntime | None = None,
) -> dict[str, Any]:
    """
    Live verification: POST /chat/completions with a tiny prompt.
    Returns structured ok/error — no guesswork.
    """
    rt = runtime or resolve_secretary_text_llm_runtime(db)
    if rt is None or not (rt.api_key or "").strip():
        return {
            "ok": False,
            "stage": "config",
            "message": "No API key configured (set key in Telegram or tbcc/.env)",
        }

    endpoint = chat_completions_url(rt)
    # Reasoning models (e.g. step-3.5-flash on hcnsec) spend budget on reasoning_*
    # fields — keep max_tokens high enough that content is not truncated to empty.
    payload = {
        "model": rt.model,
        "messages": [{"role": "user", "content": "Reply with exactly: TBCC_OK"}],
        "max_tokens": 64,
        "temperature": 0,
    }
    t0 = time.perf_counter()
    try:
        data = post_chat_completions_sync(payload, timeout=45.0, runtime=rt)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        reply = _extract_message_text(data)
        if not reply:
            return {
                "ok": False,
                "stage": "response",
                "message": "Provider returned HTTP 200 but empty message content",
                "endpoint": endpoint,
                "model": rt.model,
                "latency_ms": latency_ms,
            }
        return {
            "ok": True,
            "endpoint": endpoint,
            "model": rt.model,
            "provider": rt.provider,
            "latency_ms": latency_ms,
            "reply_preview": reply[:160],
        }
    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        err_text = str(e)
        out: dict[str, Any] = {
            "ok": False,
            "stage": "http",
            "message": err_text[:500],
            "endpoint": endpoint,
            "model": rt.model,
            "provider": rt.provider,
            "latency_ms": latency_ms,
        }
        if is_cometapi_base_url(rt.base_url) and (
            "insufficient_user_quota" in err_text or "quota is not enough" in err_text.lower()
        ):
            quota = fetch_cometapi_account_quota(rt.api_key)
            if quota:
                out["cometapi_quota"] = {
                    "total_quota": quota.get("total_quota"),
                    "total_used_quota": quota.get("total_used_quota"),
                    "request_count": quota.get("request_count"),
                }
        return out


def probe_llm_credentials(
    *,
    api_key: str,
    provider: str = "openai",
    model: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Probe credentials before persisting (e.g. preview in Telegram)."""
    try:
        rt = build_text_llm_runtime(
            api_key=api_key,
            provider=provider,
            model=model,
            base_url=base_url,
        )
    except ValueError as e:
        return {"ok": False, "stage": "validation", "message": str(e)}
    return probe_secretary_llm(runtime=rt)

