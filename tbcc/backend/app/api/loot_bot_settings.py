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


class LootBotSettingsPatch(BaseModel):
    bot_token: str | None = None  # empty string clears dashboard override
    bot_username: str | None = Field(None, max_length=64)
    primary_loot_room_invite_url: str | None = None
    primary_loot_room_chat_id: int | None = None
    config_poll_seconds: int | None = Field(None, ge=5, le=3600)
    narrative_enabled: bool | None = None
    narrative_system_prompt: str | None = None
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
    r = LootBotSettings(id=ROW_ID, narrative_enabled=False, drop_spoiler_default=True)
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
        if key == "primary_loot_room_chat_id":
            setattr(r, key, val)
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
            elif key == "narrative_enabled" or key == "drop_spoiler_default":
                setattr(r, key, bool(val))
            elif key == "config_poll_seconds":
                setattr(r, key, int(val))
            else:
                setattr(r, key, str(val).strip() if isinstance(val, str) else val)
    db.commit()
    db.refresh(r)
    return {"ok": True, "effective": get_effective_loot_bot_settings(db), "overrides": row_overrides_public(db)}
