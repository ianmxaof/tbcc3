"""Merge env + `loot_bot_settings` row for the overseer bot and dashboard."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from app.models.loot_bot_settings import LootBotSettings

ROW_ID = 1

_DEFAULT_INVITE = "https://t.me/+97f4Crv3G1RkMGU5"
_DEFAULT_USERNAME = "aof_lootgod_bot"


def _row(db: Session) -> LootBotSettings | None:
    return db.query(LootBotSettings).filter(LootBotSettings.id == ROW_ID).first()


def mask_token(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    if len(s) <= 8:
        return "********"
    return f"…{s[-4:]}"


def get_effective_loot_bot_settings(db: Session) -> dict[str, Any]:
    r = _row(db)
    env_token = (os.getenv("TBCC_LOOT_BOT_TOKEN") or "").strip()
    db_token = (r.bot_token or "").strip() if r else ""
    token_effective = db_token or env_token

    env_username = (os.getenv("TBCC_LOOT_BOT_USERNAME") or _DEFAULT_USERNAME).strip().lstrip("@")
    username = (r.bot_username or "").strip().lstrip("@") if r and r.bot_username else env_username

    env_invite = (os.getenv("TBCC_LOOT_ROOM_INVITE_URL") or _DEFAULT_INVITE).strip()
    invite = (r.primary_loot_room_invite_url or "").strip() if r and r.primary_loot_room_invite_url else env_invite

    poll = 30
    if r and r.config_poll_seconds is not None and r.config_poll_seconds > 0:
        poll = int(r.config_poll_seconds)

    narrative_on = bool(r.narrative_enabled) if r else False
    narrative_prompt = (r.narrative_system_prompt or "").strip() if r and r.narrative_system_prompt else ""
    spoiler = bool(r.drop_spoiler_default) if r else True

    chat_id = r.primary_loot_room_chat_id if r else None

    global_adapter = (os.getenv("TBCC_BOT_RUNTIME_ADAPTER") or "local").strip().lower()
    rt_ad = (r.runtime_adapter or "").strip().lower() if r and r.runtime_adapter else ""
    adapter = rt_ad if rt_ad in ("local", "command") else global_adapter
    if adapter not in ("local", "command"):
        adapter = "local"

    return {
        "bot_username": username,
        "primary_loot_room_invite_url": invite,
        "primary_loot_room_chat_id": chat_id,
        "config_poll_seconds": poll,
        "narrative_enabled": narrative_on,
        "narrative_system_prompt": narrative_prompt or None,
        "drop_spoiler_default": spoiler,
        "runtime_adapter": adapter,
        "runtime_cmd_start": (r.runtime_cmd_start if r else None) or os.getenv("TBCC_LOOT_BOT_CMD_START"),
        "runtime_cmd_stop": (r.runtime_cmd_stop if r else None) or os.getenv("TBCC_LOOT_BOT_CMD_STOP"),
        "runtime_cmd_restart": (r.runtime_cmd_restart if r else None) or os.getenv("TBCC_LOOT_BOT_CMD_RESTART"),
        "runtime_cmd_reload": (r.runtime_cmd_reload if r else None) or os.getenv("TBCC_LOOT_BOT_CMD_RELOAD"),
        "runtime_cmd_status": (r.runtime_cmd_status if r else None) or os.getenv("TBCC_LOOT_BOT_CMD_STATUS"),
        "operator_notes": (r.operator_notes if r else None) or None,
        "bot_token_masked": mask_token(token_effective),
        "bot_token_configured": bool(token_effective),
        "bot_token_source": "dashboard" if db_token else ("env" if env_token else "none"),
    }


def resolve_bot_token_raw(db: Session) -> str:
    """Raw token: dashboard row overrides env `TBCC_LOOT_BOT_TOKEN`."""
    r = _row(db)
    env_token = (os.getenv("TBCC_LOOT_BOT_TOKEN") or "").strip()
    db_token = (r.bot_token or "").strip() if r else ""
    return db_token or env_token


def get_loot_bot_internal_runtime_payload(db: Session) -> dict[str, Any]:
    """Full config for `bots.loot_bot` via authenticated internal GET (includes raw token)."""
    eff = dict(get_effective_loot_bot_settings(db))
    token = resolve_bot_token_raw(db)
    eff.pop("bot_token_masked", None)
    eff.pop("bot_token_source", None)
    eff["bot_token"] = token
    eff["bot_token_configured"] = bool(token)
    return eff


def row_overrides_public(db: Session) -> dict[str, Any]:
    r = _row(db)
    if not r:
        return {}
    return {
        "bot_username": r.bot_username,
        "primary_loot_room_invite_url": r.primary_loot_room_invite_url,
        "primary_loot_room_chat_id": r.primary_loot_room_chat_id,
        "config_poll_seconds": r.config_poll_seconds,
        "narrative_enabled": r.narrative_enabled,
        "narrative_system_prompt": r.narrative_system_prompt,
        "drop_spoiler_default": r.drop_spoiler_default,
        "runtime_adapter": r.runtime_adapter,
        "runtime_cmd_start": r.runtime_cmd_start,
        "runtime_cmd_stop": r.runtime_cmd_stop,
        "runtime_cmd_restart": r.runtime_cmd_restart,
        "runtime_cmd_reload": r.runtime_cmd_reload,
        "runtime_cmd_status": r.runtime_cmd_status,
        "operator_notes": r.operator_notes,
        "bot_token_set_in_dashboard": bool((r.bot_token or "").strip()),
        "bot_token_masked": mask_token((r.bot_token or "").strip()) if (r.bot_token or "").strip() else None,
    }
