"""Companion bot ops snapshot for dashboard / health checks."""

from __future__ import annotations

import os
from typing import Any

from app.services.companion_access import (
    affiliate_undress_url,
    free_trial_photos,
    gate_enabled,
    gate_lv_url,
)
from app.services.companion_generation import generation_configured, image_provider
from app.services.companion_jobs import count_pending_jobs
from app.services.companion_stars import stars_enabled, stars_per_photo
from app.services.companion_referral import referral_bonus_photos, referrals_enabled
from app.services.llm_chat import default_system_prompt, provider_configured
from app.services.undress_tool_client import configured as undress_configured


def _llm_model_label() -> str:
    from app.services.llm_chat import _openai_model, _openrouter_model, _provider

    p = _provider()
    if p == "custom":
        return _openai_model()
    if p == "openrouter":
        return _openrouter_model()
    if p == "openai":
        return _openai_model()
    if p in ("ollama", "local"):
        return (os.getenv("TBCC_OLLAMA_MODEL") or "llama3.2").strip()
    return p


async def companion_ops_status() -> dict[str, Any]:
    from app.services.companion_generation import check_public_webhook_reachable

    webhook_ok, webhook_detail = await check_public_webhook_reachable()
    undress_balance: int | None = None
    undress_error: str | None = None
    if undress_configured():
        try:
            from app.services.undress_tool_client import get_me

            info = await get_me()
            undress_balance = int(info.balance)
        except Exception as e:
            undress_error = str(e)[:200]

    return {
        "bot_username": (os.getenv("TBCC_COMPANION_BOT_USERNAME") or "aof_spicybot_bot").strip(),
        "token_configured": bool((os.getenv("TBCC_COMPANION_BOT_TOKEN") or "").strip()),
        "image_provider": image_provider(),
        "generation_configured": generation_configured(),
        "undress_configured": undress_configured(),
        "undress_balance": undress_balance,
        "undress_error": undress_error,
        "webhook_ok": webhook_ok,
        "webhook_detail": webhook_detail,
        "pending_jobs": count_pending_jobs(),
        "gate_enabled": gate_enabled(),
        "gate_lv_url_set": bool(gate_lv_url()),
        "free_trial_photos": free_trial_photos(),
        "stars_enabled": stars_enabled(),
        "stars_per_photo": stars_per_photo(),
        "referrals_enabled": referrals_enabled(),
        "referral_bonus_photos": referral_bonus_photos(),
        "affiliate_undress_url_set": bool(affiliate_undress_url()),
        "llm_provider": (os.getenv("TBCC_LLM_CHAT_PROVIDER") or "ollama").strip().lower(),
        "llm_model": _llm_model_label(),
        "llm_configured": provider_configured(),
        "system_prompt_chars": len(default_system_prompt()),
    }
