"""Venice / OpenRouter pass for minimal edgy AOF main-group copy."""

from __future__ import annotations

import logging
import re

from app.data.aof_brand_voice import voice_prompt_for_lane
from app.services.aof_main_group_copy import aof_copy_llm_model
from app.services.post_rewrite_llm import extract_urls


def _urls_preserved(original: str, rewritten: str, urls: list[str]) -> bool:
    if not urls:
        return True
    rw = rewritten or ""
    return all(u in rw for u in urls)

logger = logging.getLogger(__name__)

def _system_prompt() -> str:
    return (
        "You rewrite Telegram HTML captions for AOF.\n"
        f"{voice_prompt_for_lane('main_group_pulse')}\n"
        "Keep every URL and <a href> anchor exactly as given. "
        "No minors, no non-consent, no real names. Do not wrap in markdown fences."
    )


def sharpen_main_group_copy_sync(original_html: str) -> str:
    from app.services.llm_completions import complete_chat_text_sync, text_llm_configured

    if not text_llm_configured():
        raise RuntimeError("LLM not configured for AOF copy sharpen")

    src = (original_html or "").strip()
    if not src:
        return src

    urls = extract_urls(src)
    url_block = "\n".join(f"- {u}" for u in urls) if urls else "(none — do not invent links)"

    user = (
        f"Required URLs (verbatim in output):\n{url_block}\n\n"
        f"Original:\n{src}\n\n"
        "Sharpened caption (max ~280 chars if possible, never exceed 2 short paragraphs):"
    )

    text = complete_chat_text_sync(
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user},
        ],
        model=aof_copy_llm_model(),
        max_tokens=320,
        temperature=0.85,
        timeout=60.0,
    )
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if not text:
        return src
    if len(text) > 900:
        text = text[:897].rstrip() + "…"
    if not _urls_preserved(src, text, urls):
        logger.warning("AOF copy LLM dropped URLs; keeping original")
        return src
    return text
