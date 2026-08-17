"""OpenAI chat for secretary / FAQ bot — plain text replies (no JSON mode)."""

from __future__ import annotations

import json
import logging
import os
import re
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
        "You are a person DMing on Telegram for AOF — not a support desk, not a chatbot. "
        "Match their energy. Short in, short out. No signatures, no 'AOF SECRETARY', "
        "no quoting their message, no 'I'm here to help with subscriptions'. "
        "Banned: 'How can I assist you', 'feel free to ask', 'I appreciate you reaching out'. "
        "Do not discuss minors, illegal activity, or non-consensual content. "
        "Do not share other people's accounts. Do not buy SEO/homepage links. "
        "Checkout only when they ask to buy — then one line to the payment bot. "
        "Never dump the catalog."
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

AUTO_EMOTION_INSTRUCTION = (
    "Before your response, emit a JSON block on its own line:\n"
    '<<EMOTION>>{"state":"...","intensity":0.0,"signals":["...","..."]}<</EMOTION>>\n'
    "Then your user-facing response."
)

_EMOTION_BLOCK_RE = re.compile(
    r"<<EMOTION>>\s*(.*?)\s*<</EMOTION>>",
    re.DOTALL | re.IGNORECASE,
)


def append_auto_emotion_instruction(suffix: str) -> str:
    base = (suffix or "").strip()
    if AUTO_EMOTION_INSTRUCTION in base or "<<EMOTION>>" in base:
        return base or AUTO_EMOTION_INSTRUCTION
    if base:
        return base + "\n\n" + AUTO_EMOTION_INSTRUCTION
    return AUTO_EMOTION_INSTRUCTION


def extract_emotion_block(raw_llm_output: str) -> tuple[dict[str, Any] | None, str]:
    """Pull <<EMOTION>>…<</EMOTION>> JSON out of an Auto completion; return (block, cleaned)."""
    text = raw_llm_output or ""
    match = _EMOTION_BLOCK_RE.search(text)
    if not match:
        return None, text.strip()
    blob = (match.group(1) or "").strip()
    cleaned = _EMOTION_BLOCK_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    try:
        data = json.loads(blob)
    except (TypeError, ValueError):
        return None, cleaned
    if not isinstance(data, dict):
        return None, cleaned
    return data, cleaned


async def complete_secretary_chat(
    messages: list[dict[str, str]],
    *,
    extra_system_suffix: str = "",
) -> str:
    """
    messages: OpenAI-style chat messages (role + content), must include at least one user turn.
    """
    from app.services.secretary_llm_config import resolve_secretary_text_llm_runtime
    from app.services.system_prompts import prompt_text

    runtime = resolve_secretary_text_llm_runtime()
    if runtime is None:
        raise RuntimeError(
            "Set secretary LLM in dashboard (System → Secretary) or "
            "TBCC_OPENROUTER_API_KEY / TBCC_OPENAI_API_KEY in tbcc/.env"
        )

    if not messages:
        raise ValueError("messages empty")

    extra_bits: list[str] = []
    closer = prompt_text("aggressive_sales")
    if closer:
        extra_bits.append(closer)
    spicy_on = (os.getenv("TBCC_SECRETARY_SPICY_PASSTHROUGH") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if spicy_on:
        spicy = prompt_text("spicy_passthrough")
        if spicy:
            extra_bits.append(spicy)

    if extra_system_suffix.strip():
        extra_bits.append(extra_system_suffix.strip())
    extra = "\n\n".join(extra_bits)

    sys0 = messages[0] if messages[0].get("role") == "system" else None
    if sys0:
        body_msgs = [dict(sys0)]
        if extra:
            body_msgs[0]["content"] = (body_msgs[0].get("content") or "") + "\n\n" + extra
        body_msgs.extend(messages[1:])
    else:
        body_msgs = [{"role": "system", "content": default_system_prompt() + (("\n\n" + extra) if extra else "")}]
        body_msgs.extend(messages)

    from app.services.llm_provider_fallback import complete_chat_text_with_fallback

    return await complete_chat_text_with_fallback(
        body_msgs,
        primary=runtime,
        model=_model(),
        max_tokens=_max_tokens(),
        temperature=0.6,
        timeout=90.0,
    )
