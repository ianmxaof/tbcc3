"""
Interchangeable vision LLM for niche tagging (fallback when CLIP confidence is low).

Providers (TBCC_VISION_LLM_PROVIDER):
  - none     — disabled
  - openai   — TBCC_OPENAI_API_KEY / OPENAI_API_KEY
  - openrouter — TBCC_OPENROUTER_API_KEY (+ optional TBCC_OPENROUTER_BASE_URL)
  - ollama   — local vision model via TBCC_OLLAMA_BASE_URL (llava, moondream, etc.)

Env:
  TBCC_VISION_LLM_MODEL — provider-specific model id
  TBCC_VISION_LLM_MIN_CONF — only used by callers; skip vision if CLIP above threshold
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def vision_llm_enabled() -> bool:
    p = _provider()
    if p in ("none", "off", "disabled", ""):
        return False
    if p == "openai":
        return bool(_openai_key())
    if p == "openrouter":
        return bool(_openrouter_key())
    if p in ("ollama", "local"):
        return True
    return False


def _provider() -> str:
    raw = (os.getenv("TBCC_VISION_LLM_PROVIDER") or "none").strip().lower()
    # Legacy: watch-folder flag enables openai if key present
    if raw == "none" and (os.getenv("TBCC_WATCH_LLM_TAG") or "").strip().lower() in ("1", "true", "yes", "on"):
        if _openai_key():
            return "openai"
    return raw


def _openai_key() -> str:
    return (os.getenv("TBCC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def _openrouter_key() -> str:
    from app.services.llm_completions import openrouter_api_key

    return openrouter_api_key()


def _vision_model() -> str:
    explicit = (os.getenv("TBCC_VISION_LLM_MODEL") or "").strip()
    if explicit:
        return explicit
    p = _provider()
    if p == "openrouter":
        return (os.getenv("TBCC_OPENROUTER_VISION_MODEL") or "google/gemma-3-12b-it:free").strip()
    if p == "ollama":
        return (os.getenv("TBCC_OLLAMA_VISION_MODEL") or os.getenv("TBCC_OLLAMA_MODEL") or "llava").strip()
    return (os.getenv("TBCC_LLM_MODEL") or "gpt-4o-mini").strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    data = json.loads(t)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


def _niche_prompt(allowed_slugs: list[str] | None) -> str:
    base = (
        "You are indexing adult image content for a private media library. "
        "Return a single JSON object with keys:\n"
        '- "nsfw_tier": sfw | suggestive | explicit | unknown\n'
        '- "primary_slug": best matching category slug from the allowed list when possible, else a short new slug\n'
        '- "niche", "act", "body_type", "ethnicity": short strings or empty\n'
        '- "facets": up to 8 lowercase tags\n'
        "Use empty strings when unknown. Be factual and concise."
    )
    if allowed_slugs:
        # Cap prompt size — send top candidates only if huge list passed in
        slugs = allowed_slugs[:48]
        base += f"\n\nPrefer one of these slugs if it fits: {', '.join(slugs)}"
    return base


def analyze_image_bytes(
    image_bytes: bytes,
    *,
    mime: str = "image/jpeg",
    allowed_slugs: list[str] | None = None,
    timeout: float = 120.0,
    prompt_override: str | None = None,
) -> dict[str, Any]:
    if not vision_llm_enabled() or not image_bytes or len(image_bytes) < 32:
        return {}
    p = _provider()
    b64 = base64.standard_b64encode(image_bytes[:4_000_000]).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    prompt = prompt_override or _niche_prompt(allowed_slugs)
    try:
        if p == "openai":
            return _vision_openai_compatible(
                "https://api.openai.com/v1/chat/completions",
                _openai_key(),
                prompt,
                data_url,
                timeout=timeout,
            )
        if p == "openrouter":
            from app.services.llm_completions import OPENROUTER_BASE

            base = (os.getenv("TBCC_OPENROUTER_BASE_URL") or OPENROUTER_BASE).rstrip("/")
            headers = {"HTTP-Referer": "https://tbcc.local", "X-Title": "TBCC Vision Tagging"}
            return _vision_openai_compatible(
                f"{base}/chat/completions",
                _openrouter_key(),
                prompt,
                data_url,
                timeout=timeout,
                extra_headers=headers,
            )
        if p in ("ollama", "local"):
            return _vision_ollama(prompt, data_url, image_bytes, timeout=timeout)
    except Exception as e:
        logger.warning("vision_llm failed (%s): %s", p, e)
    return {}


def _vision_openai_compatible(
    url: str,
    api_key: str,
    prompt: str,
    data_url: str,
    *,
    timeout: float,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    payload = {
        "model": _vision_model(),
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                ],
            }
        ],
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        body = r.json()
    content = body["choices"][0]["message"]["content"]
    parsed = _parse_json_object(content)
    if isinstance(parsed.get("facets"), list):
        parsed["facets"] = [str(x).strip()[:64] for x in parsed["facets"] if str(x).strip()][:8]
    return parsed


def _vision_ollama(prompt: str, data_url: str, image_bytes: bytes, *, timeout: float) -> dict[str, Any]:
    base = (os.getenv("TBCC_OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    model = _vision_model()
    b64 = base64.standard_b64encode(image_bytes[:4_000_000]).decode("ascii")
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64],
            }
        ],
        "stream": False,
        "format": "json",
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(f"{base}/api/chat", json=body)
        r.raise_for_status()
        data = r.json()
    text = ((data.get("message") or {}).get("content") or "").strip()
    if not text:
        return {}
    parsed = _parse_json_object(text)
    if isinstance(parsed.get("facets"), list):
        parsed["facets"] = [str(x).strip()[:64] for x in parsed["facets"] if str(x).strip()][:8]
    return parsed
