"""Dashboard + bot: merged growth/referral configuration (DB overrides env)."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.growth_settings import GrowthSettings
from app.services.growth_settings_effective import ROW_ID, get_effective_growth_settings

logger = logging.getLogger(__name__)

router = APIRouter()


class GrowthSettingsPatch(BaseModel):
    landing_bulletin_chat_id: str | None = None
    landing_bulletin_message_thread_id: int | None = None
    landing_bulletin_hour_utc: int | None = Field(None, ge=0, le=23)
    landing_bulletin_bot_username: str | None = None
    landing_bulletin_intro: str | None = None
    referral_group_invite_link: str | None = None
    referral_group_name: str | None = None
    referral_reward_days: int | None = Field(None, ge=1, le=3650)
    referral_mode: str | None = None
    milestone_progress_chat_id: str | None = None


def _ensure_row(db: Session) -> GrowthSettings:
    r = db.query(GrowthSettings).filter(GrowthSettings.id == ROW_ID).first()
    if r:
        return r
    r = GrowthSettings(id=ROW_ID)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _row_to_dict(r: GrowthSettings) -> dict[str, Any]:
    return {
        "landing_bulletin_chat_id": r.landing_bulletin_chat_id,
        "landing_bulletin_message_thread_id": r.landing_bulletin_message_thread_id,
        "landing_bulletin_hour_utc": r.landing_bulletin_hour_utc,
        "landing_bulletin_bot_username": r.landing_bulletin_bot_username,
        "landing_bulletin_intro": r.landing_bulletin_intro,
        "referral_group_invite_link": r.referral_group_invite_link,
        "referral_group_name": r.referral_group_name,
        "referral_reward_days": r.referral_reward_days,
        "referral_mode": r.referral_mode,
        "milestone_progress_chat_id": r.milestone_progress_chat_id,
    }


@router.post("/send-bulletin-now")
def send_bulletin_now(db: Session = Depends(get_db)):
    """
    Queue a landing bulletin send immediately (same as Celery task with force=True).
    Requires Redis + a running Celery worker on the subscription queue, and BOT_TOKEN.
    """
    _ensure_row(db)
    effective = get_effective_growth_settings(db)
    chat_id = (effective.get("landing_bulletin_chat_id") or "").strip()
    if not chat_id:
        raise HTTPException(
            status_code=400,
            detail="Set Landing chat id and save (or tbcc/.env TBCC_LANDING_BULLETIN_CHAT_ID) before posting.",
        )
    try:
        from app.workers.landing_bulletin_worker import send_aof_landing_bulletin

        async_result = send_aof_landing_bulletin.delay(force=True)
        return {
            "ok": True,
            "task_id": str(async_result.id),
            "message": "Queued. Ensure the Celery worker is running; check the landing chat in Telegram.",
        }
    except Exception as e:
        logger.exception("send-bulletin-now failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"Could not queue task (Redis/Celery?). {e!s}",
        ) from e


@router.get("")
def get_growth_settings(db: Session = Depends(get_db)):
    """
    Returns `effective` (merged DB + env) for forms and bots, and `overrides` (DB row only).
    """
    _ensure_row(db)
    effective = get_effective_growth_settings(db)
    row = db.query(GrowthSettings).filter(GrowthSettings.id == ROW_ID).first()
    overrides = _row_to_dict(row) if row else {}
    return {"effective": effective, "overrides": overrides}


@router.patch("")
def patch_growth_settings(body: GrowthSettingsPatch, db: Session = Depends(get_db)):
    """Update stored overrides. Use `null` or empty string to clear a column (fall back to env)."""
    r = _ensure_row(db)
    data = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)
    for key, val in data.items():
        if not hasattr(r, key):
            continue
        if val is None or (isinstance(val, str) and val.strip() == ""):
            setattr(r, key, None)
        else:
            if key == "referral_mode":
                v = str(val).lower().strip()
                if v not in ("community", "premium"):
                    raise HTTPException(status_code=400, detail="referral_mode must be community or premium")
                setattr(r, key, v)
            else:
                setattr(r, key, val)
    db.commit()
    db.refresh(r)
    return {"ok": True, "effective": get_effective_growth_settings(db), "overrides": _row_to_dict(r)}
