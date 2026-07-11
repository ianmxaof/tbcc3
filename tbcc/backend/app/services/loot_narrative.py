"""Loot overseer persona chat via shared LLM stack (OpenAI / Ollama)."""

from __future__ import annotations

import os

from app.services.llm_chat import complete_llm_chat, provider_configured

DEFAULT_OVERSEER_PROMPT = """You are the Loot Overseer (@aof_lootgod_bot) for the AOF Loot Room game.

Voice: cold, gritty, casino-adjacent — not cute, not corporate. Short Telegram replies (under 120 words unless asked).

You deal tiered pulls (1–10), spoiler drops, modifiers (zips, invites). Complimentary pulls are capped; paid 24h room access is via the payment bot.

Never promise outcomes you cannot guarantee. Do not assist with illegal content or minors.
If asked how to play: DM /roll for free pulls (5 lifetime), Loot Room Group is the public commons, payment bot /loot and /subscribe unlock paid keys/VIP.
Referrals: share your lootref_ link from /referral for bonus free pulls after friends play."""


def overseer_system_prompt(custom: str | None = None) -> str:
    extra = (custom or "").strip()
    if extra:
        return f"{DEFAULT_OVERSEER_PROMPT}\n\nOperator notes:\n{extra}"
    env = (os.getenv("TBCC_LOOT_NARRATIVE_SYSTEM_PROMPT") or "").strip()
    if env:
        return f"{DEFAULT_OVERSEER_PROMPT}\n\n{env}"
    return DEFAULT_OVERSEER_PROMPT


def narrative_enabled(effective: dict | None) -> bool:
    if effective and effective.get("narrative_enabled"):
        return True
    return (os.getenv("TBCC_LOOT_NARRATIVE_ENABLED") or "").strip().lower() in ("1", "true", "yes", "on")


async def reply_as_overseer(
    messages: list[dict[str, str]],
    *,
    effective: dict | None = None,
) -> str:
    if not provider_configured():
        raise RuntimeError(
            "LLM not configured — set TBCC_OPENAI_API_KEY (provider openai) or run Ollama with TBCC_LLM_CHAT_PROVIDER=ollama"
        )
    custom = (effective or {}).get("narrative_system_prompt") if effective else None
    system = overseer_system_prompt(custom)
    full = [{"role": "system", "content": system}] + messages
    return await complete_llm_chat(full)
