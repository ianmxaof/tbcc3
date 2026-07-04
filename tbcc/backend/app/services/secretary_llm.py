"""OpenAI chat for secretary / FAQ bot — plain text replies (no JSON mode)."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _model() -> str:
    from app.services.llm_completions import resolve_text_model

    explicit = (os.getenv("TBCC_SECRETARY_LLM_MODEL") or "").strip()
    return resolve_text_model(explicit or None)


def _max_tokens() -> int:
    raw = (os.getenv("TBCC_SECRETARY_LLM_MAX_TOKENS") or "800").strip()
    try:
        return max(64, min(4096, int(raw)))
    except ValueError:
        return 800


def builtin_default_system_prompt() -> str:
    return (
        "You are a concise customer support assistant for an adult content brand (AOF). "
        "Answer FAQs about access, subscriptions, and how to buy. "
        "Do not discuss minors, illegal activity, or non-consensual content. "
        "If asked for specific purchases, packs, or payment links, say purchases are handled "
        "by the official payment bot and give a short pointer to open it from the menu. "
        "Keep replies under ~400 words unless the user asks for detail."
    )


def resolve_system_prompt(db=None) -> tuple[str, str]:
    """
    Effective secretary system prompt and source label.
    Priority: dashboard (DB) → TBCC_SECRETARY_SYSTEM_PROMPT env → built-in default.
    """
    from app.database.session import SessionLocal
    from app.models.secretary_settings import ROW_ID, SecretarySettings

    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        row = db.query(SecretarySettings).filter(SecretarySettings.id == ROW_ID).first()
        if row and (row.system_prompt or "").strip():
            return str(row.system_prompt).strip(), "dashboard"
    finally:
        if own_db and db is not None:
            db.close()

    custom = (os.getenv("TBCC_SECRETARY_SYSTEM_PROMPT") or "").strip()
    if custom:
        return custom, "env"
    return builtin_default_system_prompt(), "builtin"


def default_system_prompt() -> str:
    prompt, _source = resolve_system_prompt()
    return prompt


def persist_system_prompt(text: str | None) -> dict:
    """Save or clear dashboard system prompt override. Returns {ok, source, chars}."""
    from app.database.session import SessionLocal
    from app.services.secretary_settings_effective import ensure_settings_row

    cleaned = (text or "").strip() or None
    if cleaned and len(cleaned) > 12000:
        raise ValueError("System prompt too long (max 12000 characters)")

    db = SessionLocal()
    try:
        row = ensure_settings_row(db)
        row.system_prompt = cleaned
        db.commit()
        prompt, source = resolve_system_prompt(db)
        return {"ok": True, "source": source, "chars": len(prompt)}
    finally:
        db.close()


def openai_configured() -> bool:
    from app.services.secretary_llm_config import secretary_llm_configured

    return secretary_llm_configured()


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
    from app.services.llm_completions import complete_chat_text_async
    from app.services.secretary_llm_config import resolve_secretary_text_llm_runtime

    runtime = resolve_secretary_text_llm_runtime()
    if runtime is None:
        raise RuntimeError(
            "Set secretary LLM in dashboard (System → Secretary) or "
            "TBCC_OPENROUTER_API_KEY / TBCC_OPENAI_API_KEY in tbcc/.env"
        )

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

    return await complete_chat_text_async(
        body_msgs,
        model=_model(),
        max_tokens=_max_tokens(),
        temperature=0.6,
        timeout=90.0,
        runtime=runtime,
    )
