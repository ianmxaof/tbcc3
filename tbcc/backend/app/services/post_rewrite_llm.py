"""Rewrite scheduled post captions via OpenAI while preserving URLs and meaning."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"']+|(?:t\.me|telegram\.me)/[^\s<>\"']+",
    re.IGNORECASE,
)


def caption_rewrite_llm_globally_enabled() -> bool:
    return (os.environ.get("TBCC_CAPTION_LLM_REWRITE_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _model() -> str:
    from app.services.llm_completions import resolve_text_model

    explicit = (
        os.environ.get("TBCC_CAPTION_LLM_REWRITE_MODEL")
        or os.environ.get("TBCC_LLM_MODEL")
        or ""
    ).strip()
    return resolve_text_model(explicit or None)


def _max_tokens() -> int:
    raw = (os.environ.get("TBCC_CAPTION_LLM_REWRITE_MAX_TOKENS") or "1200").strip()
    try:
        return max(128, min(4096, int(raw)))
    except ValueError:
        return 1200


def extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_PATTERN.finditer(text or ""):
        u = m.group(0).rstrip(".,);]")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _urls_preserved(original: str, rewritten: str, urls: list[str]) -> bool:
    if not urls:
        return True
    rw = rewritten or ""
    for u in urls:
        if u not in rw:
            return False
    return True


def rewrite_caption_llm_sync(original_html: str) -> str:
    """
    Return a rephrased caption (Telegram HTML OK). Raises on missing API key or hard failure.
    Falls back to original if model output drops required URLs.
    """
    from app.services.llm_completions import complete_chat_text_sync, text_llm_configured

    if not text_llm_configured():
        raise RuntimeError(
            "LLM not configured: TBCC_OPENROUTER_API_KEY or TBCC_OPENAI_API_KEY"
        )

    src = (original_html or "").strip()
    if not src:
        return src

    urls = extract_urls(src)
    url_block = "\n".join(f"- {u}" for u in urls) if urls else "(none — do not invent links)"

    system = (
        "You rewrite social media captions for an adult NSFW brand (AOF). "
        "Keep the same meaning, announcements, channel names, and ALL facts. "
        "Output Telegram-compatible HTML only: <b>, <i>, <a href=\"...\">, line breaks. "
        "Every URL from the required list MUST appear verbatim at least once in your output. "
        "Do not add new URLs. Do not wrap the answer in markdown code fences."
    )
    edgy = (os.environ.get("TBCC_CAPTION_LLM_REWRITE_EDGY") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if edgy:
        system = (
            "You rewrite Telegram HTML captions for AOF — adult NSFW network. "
            "Audience: edgy depraved degenerates who hate corporate tone. "
            "ONE or TWO short dense sentences max. No bullet lists. Crude, sexual, arrogant tone. "
            "Keep every URL and <a href> exactly. Telegram HTML only. No markdown fences."
        )
    user = (
        f"Required URLs (include each exactly as written):\n{url_block}\n\n"
        f"Original caption:\n{src}\n\n"
        "Rewritten caption:"
    )

    payload: dict[str, Any] = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": _max_tokens(),
        "temperature": 0.75,
    }

    text = complete_chat_text_sync(
        payload["messages"],
        model=payload["model"],
        max_tokens=payload["max_tokens"],
        temperature=payload["temperature"],
        timeout=90.0,
    )
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if not text:
        raise RuntimeError("Empty LLM rewrite")

    if not _urls_preserved(src, text, urls):
        logger.warning("caption LLM rewrite dropped URLs; using original (%s urls)", len(urls))
        return src

    return text
