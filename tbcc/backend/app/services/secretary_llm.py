"""OpenAI chat for secretary / FAQ bot — plain text replies (no JSON mode)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _openai_key() -> str:
    return (os.getenv("TBCC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()


def _model() -> str:
    return (os.getenv("TBCC_SECRETARY_LLM_MODEL") or os.getenv("TBCC_LLM_MODEL") or "gpt-4o-mini").strip()


def _max_tokens() -> int:
    raw = (os.getenv("TBCC_SECRETARY_LLM_MAX_TOKENS") or "800").strip()
    try:
        return max(64, min(4096, int(raw)))
    except ValueError:
        return 800


def default_system_prompt() -> str:
    custom = (os.getenv("TBCC_SECRETARY_SYSTEM_PROMPT") or "").strip()
    if custom:
        return custom
    return (
        "You are a concise customer support assistant for an adult content brand (AOF). "
        "Answer FAQs about access, subscriptions, and how to buy. "
        "Do not discuss minors, illegal activity, or non-consensual content. "
        "If asked for specific purchases, packs, or payment links, say purchases are handled "
        "by the official payment bot and give a short pointer to open it from the menu. "
        "Keep replies under ~400 words unless the user asks for detail."
    )


def openai_configured() -> bool:
    return bool(_openai_key())


async def fetch_subscription_catalog_snippet(api_base: str, *, max_plans: int = 12) -> str:
    """Short text summary of active subscription plans for LLM context (public GET)."""
    base = api_base.rstrip("/")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base}/subscription-plans/", timeout=15.0)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("secretary: could not fetch plans: %s", e)
        return ""
    if not isinstance(data, list):
        return ""
    lines: list[str] = []
    for p in data[:max_plans]:
        if not isinstance(p, dict):
            continue
        if p.get("is_active") is False:
            continue
        if (p.get("product_type") or "subscription").lower() != "subscription":
            continue
        name = str(p.get("name") or "").strip()
        stars = int(p.get("price_stars") or 0)
        days = int(p.get("duration_days") or 0)
        if not name or stars <= 0:
            continue
        lines.append(f"- {name}: {stars} Stars, {days} days")
    if not lines:
        return ""
    return "Current subscription SKUs (Stars, channel access):\n" + "\n".join(lines)


REDO_STYLE_HINTS: dict[str, str] = {
    "pro": "Rewrite the assistant reply in a more professional, calm tone. Same facts; shorter if possible.",
    "casual": "Rewrite in a warmer, casual tone. Same facts; no new promises.",
    "short": "Rewrite to half the length. Keep payment-bot pointers if any.",
    "custom": "",  # filled from user instruction
}


async def complete_secretary_chat(
    messages: list[dict[str, str]],
    *,
    extra_system_suffix: str = "",
) -> str:
    """
    messages: OpenAI-style chat messages (role + content), must include at least one user turn.
    """
    key = _openai_key()
    if not key:
        raise RuntimeError("Set TBCC_OPENAI_API_KEY or OPENAI_API_KEY")

    if not messages:
        raise ValueError("messages empty")

    sys0 = messages[0] if messages[0].get("role") == "system" else None
    if sys0:
        body_msgs = [dict(sys0)]
        if extra_system_suffix.strip():
            body_msgs[0]["content"] = (body_msgs[0].get("content") or "") + "\n\n" + extra_system_suffix.strip()
        body_msgs.extend(messages[1:])
    else:
        body_msgs = [{"role": "system", "content": default_system_prompt() + (extra_system_suffix or "")}]
        body_msgs.extend(messages)

    payload: dict[str, Any] = {
        "model": _model(),
        "messages": body_msgs,
        "max_tokens": _max_tokens(),
        "temperature": 0.6,
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
            logger.warning("OpenAI secretary HTTP %s: %s", r.status_code, detail)
            raise RuntimeError(f"OpenAI error {r.status_code}")
        data = r.json()

    try:
        choice0 = (data.get("choices") or [{}])[0]
        msg = (choice0.get("message") or {})
        text = (msg.get("content") or "").strip()
    except Exception as e:
        logger.warning("bad OpenAI secretary response: %s", e)
        raise RuntimeError("Bad OpenAI response") from e
    if not text:
        raise RuntimeError("Empty model reply")
    return text
