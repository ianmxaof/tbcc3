"""Dashboard + loot overseer bot runtime settings (DB overrides)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.external_payment_orders import _require_internal
from app.database.session import get_db
from app.models.loot_bot_settings import LootBotSettings
from app.services.loot_bot_settings_effective import (
    ROW_ID,
    get_effective_loot_bot_settings,
    get_loot_bot_internal_runtime_payload,
    row_overrides_public,
)

router = APIRouter()


def _normalize_buffer_x_queue(raw: list | None) -> list[dict]:
    if not raw or not isinstance(raw, list):
        return []
    out: list[dict] = []
    for x in raw:
        if not isinstance(x, dict):
            continue
        t = str(x.get("text") or "").strip()
        if not t:
            continue
        entry: dict = {"text": t[:2800]}
        iu = str(x.get("image_url") or "").strip()
        if iu.startswith("https://"):
            entry["image_url"] = iu[:2048]
        out.append(entry)
        if len(out) >= 10:
            break
    return out


class LootBotSettingsPatch(BaseModel):
    bot_token: str | None = None  # empty string clears dashboard override
    bot_username: str | None = Field(None, max_length=64)
    primary_loot_room_invite_url: str | None = None
    primary_loot_room_chat_id: int | None = None
    aof_group_chat_id: int | None = None
    aof_group_message_thread_id: int | None = Field(None, ge=1)
    daily_promo_enabled: bool | None = None
    daily_promo_hour_utc: int | None = Field(None, ge=0, le=23)
    daily_promo_intro_html: str | None = None
    buffer_mirror_enabled: bool | None = None
    buffer_publish_now: bool | None = None
    buffer_x_queue: list[dict] | None = None
    config_poll_seconds: int | None = Field(None, ge=5, le=3600)
    narrative_enabled: bool | None = None
    narrative_system_prompt: str | None = None
    loot_referral_enabled: bool | None = None
    referral_bonus_pulls: int | None = Field(None, ge=0, le=20)
    drop_spoiler_default: bool | None = None
    runtime_adapter: str | None = None
    runtime_cmd_start: str | None = None
    runtime_cmd_stop: str | None = None
    runtime_cmd_restart: str | None = None
    runtime_cmd_reload: str | None = None
    runtime_cmd_status: str | None = None
    operator_notes: str | None = None


def _ensure_row(db: Session) -> LootBotSettings:
    r = db.query(LootBotSettings).filter(LootBotSettings.id == ROW_ID).first()
    if r:
        return r
    import os

    aof_cid = None
    env_aof = (os.getenv("TBCC_LOOT_AOF_GROUP_CHAT_ID") or "").strip()
    if env_aof:
        try:
            aof_cid = int(env_aof)
        except ValueError:
            aof_cid = None
    promo_on = (os.getenv("TBCC_LOOT_DAILY_PROMO_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    promo_hour = None
    raw_h = (os.getenv("TBCC_LOOT_DAILY_PROMO_HOUR_UTC") or "").strip()
    if raw_h:
        try:
            promo_hour = max(0, min(23, int(raw_h)))
        except ValueError:
            promo_hour = 18
    r = LootBotSettings(
        id=ROW_ID,
        narrative_enabled=False,
        loot_referral_enabled=True,
        drop_spoiler_default=True,
        aof_group_chat_id=aof_cid,
        daily_promo_enabled=promo_on,
        daily_promo_hour_utc=promo_hour,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.get("/internal-runtime")
def get_loot_bot_internal_runtime(_: None = Depends(_require_internal), db: Session = Depends(get_db)):
    """Used by `python -m bots.loot_bot` with `X-TBCC-Internal-Key` (same as payment /external flows)."""
    _ensure_row(db)
    return get_loot_bot_internal_runtime_payload(db)


@router.get("")
def get_loot_bot_settings(db: Session = Depends(get_db)):
    _ensure_row(db)
    return {
        "effective": get_effective_loot_bot_settings(db),
        "overrides": row_overrides_public(db),
    }


@router.patch("")
def patch_loot_bot_settings(body: LootBotSettingsPatch, db: Session = Depends(get_db)):
    r = _ensure_row(db)
    data = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)
    for key, val in data.items():
        if key == "bot_token":
            if val is None:
                continue
            if isinstance(val, str) and not val.strip():
                r.bot_token = None
            else:
                r.bot_token = str(val).strip()
            continue
        if key == "runtime_adapter":
            if val is None or (isinstance(val, str) and not str(val).strip()):
                r.runtime_adapter = None
            else:
                v = str(val).strip().lower()
                if v not in ("local", "command"):
                    raise HTTPException(status_code=400, detail="runtime_adapter must be local or command")
                r.runtime_adapter = v
            continue
        if key in ("primary_loot_room_chat_id", "aof_group_chat_id"):
            setattr(r, key, val)
            continue
        if key == "aof_group_message_thread_id":
            setattr(r, key, int(val) if val is not None else None)
            continue
        if key == "daily_promo_enabled":
            setattr(r, key, bool(val))
            continue
        if key == "daily_promo_hour_utc":
            setattr(r, key, int(val) if val is not None else None)
            continue
        if key == "daily_promo_intro_html":
            setattr(r, key, str(val).strip() or None if val is not None else None)
            continue
        if key == "buffer_mirror_enabled" or key == "buffer_publish_now":
            setattr(r, key, bool(val))
            continue
        if key == "buffer_x_queue":
            raw_q = val
            dumped = raw_q if isinstance(raw_q, list) else []
            r.set_buffer_x_queue(_normalize_buffer_x_queue(dumped))
            continue
        if not hasattr(r, key):
            continue
        if val is None or (isinstance(val, str) and not str(val).strip()):
            setattr(r, key, None)
        else:
            if key == "bot_username":
                setattr(r, key, str(val).strip().lstrip("@")[:64])
            elif key == "primary_loot_room_invite_url":
                setattr(r, key, str(val).strip()[:2048])
            elif key == "narrative_system_prompt" or key == "operator_notes":
                setattr(r, key, str(val).strip() or None)
            elif key in ("narrative_enabled", "drop_spoiler_default", "loot_referral_enabled"):
                setattr(r, key, bool(val))
            elif key == "referral_bonus_pulls":
                setattr(r, key, int(val) if val is not None else None)
            elif key == "config_poll_seconds":
                setattr(r, key, int(val))
            else:
                setattr(r, key, str(val).strip() if isinstance(val, str) else val)
    db.commit()
    db.refresh(r)
    return {"ok": True, "effective": get_effective_loot_bot_settings(db), "overrides": row_overrides_public(db)}


@router.post("/trigger-daily-promo")
def trigger_daily_promo_now(db: Session = Depends(get_db)):
    """Send the daily AOF group promo immediately (same message Celery uses)."""
    from app.workers.loot_promo_worker import send_loot_daily_promo

    _ensure_row(db)
    eff = get_effective_loot_bot_settings(db)
    if not eff.get("aof_group_chat_id"):
        raise HTTPException(
            status_code=400,
            detail="Set Main AOF group chat id in Loot overseer (or TBCC_LOOT_AOF_GROUP_CHAT_ID)",
        )
    if not eff.get("bot_token_configured"):
        raise HTTPException(
            status_code=400,
            detail="Loot bot token not configured (TBCC_LOOT_BOT_TOKEN in .env or valid token in dashboard)",
        )
    # Run inline so Dashboard / scripts get immediate Telegram errors (not silent Celery queue).
    from app.workers.loot_promo_worker import _post_loot_promo

    _post_loot_promo(force=True)
    eff2 = get_effective_loot_bot_settings(db)
    return {
        "ok": True,
        "queued": False,
        "sent": True,
        "chat_id": eff.get("aof_group_chat_id"),
        "buffer_mirror_enabled": bool(eff2.get("buffer_mirror_enabled")),
    }


class LootBufferTestBody(BaseModel):
    text: str | None = Field(None, max_length=2800)
    publish_now: bool | None = None


@router.post("/buffer-test-post")
def loot_buffer_test_post(body: LootBufferTestBody | None = None, db: Session = Depends(get_db)):
    """Test Buffer → X wiring for loot promo captions (X primary channel only)."""
    from app.services.buffer_graphql import buffer_api_key, buffer_target_channel_ids, create_posts_multi_channel
    from app.services.buffer_post_result import buffer_create_post_succeeded
    from app.services.loot_buffer_mirror import build_loot_promo_x_caption

    if not buffer_api_key():
        raise HTTPException(status_code=400, detail="TBCC_BUFFER_API_KEY is not set in .env")
    chans = buffer_target_channel_ids(x_primary_only=True)
    if not chans:
        raise HTTPException(status_code=400, detail="Set TBCC_BUFFER_CHANNEL_ID_PRIMARY for X")
    _ensure_row(db)
    if body and body.text and body.text.strip():
        from app.services.buffer_x_caption import fit_plaintext_for_x, should_fit_for_x
        from app.services.loot_bot_settings_effective import get_effective_loot_bot_settings
        from app.services.loot_buffer_mirror import _loot_overflow_url

        eff = get_effective_loot_bot_settings(db)
        plain = body.text.strip()
        if should_fit_for_x():
            plain = fit_plaintext_for_x(plain, overflow_url=_loot_overflow_url(eff) or None)
    else:
        plain = build_loot_promo_x_caption(db)
    if not plain:
        raise HTTPException(status_code=400, detail="Empty X caption")
    mode = "shareNow" if body and body.publish_now else "addToQueue"
    results = create_posts_multi_channel(plain, channel_ids=chans, mode=mode)
    ok = any(buffer_create_post_succeeded(r) for r in results)
    return {"ok": ok, "mode": mode, "chars": len(plain), "channels": len(chans)}
