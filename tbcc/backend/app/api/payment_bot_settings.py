"""Dashboard + payment bot runtime settings (DB overrides)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.payment_bot_settings import PaymentBotSettings
from app.services.payment_bot_settings_effective import (
    ALLOWED_MENU_ACTIONS,
    ROW_ID,
    get_effective_payment_bot_settings,
)

router = APIRouter()


class PaymentBotSettingsPatch(BaseModel):
    main_menu: list[list[dict[str, str]]] | None = None
    welcome_html: str | None = None
    loot_intro_html: str | None = None
    subscribe_title_main: str | None = Field(None, max_length=128)
    subscribe_title_loot: str | None = Field(None, max_length=128)
    subscription_catalog_columns: int | None = Field(None, ge=1, le=4)
    min_subscription_stars: int | None = Field(None, ge=0, le=1000000)
    runtime_adapter: str | None = None
    runtime_cmd_start: str | None = None
    runtime_cmd_stop: str | None = None
    runtime_cmd_restart: str | None = None
    runtime_cmd_reload: str | None = None
    runtime_cmd_status: str | None = None


def _ensure_row(db: Session) -> PaymentBotSettings:
    r = db.query(PaymentBotSettings).filter(PaymentBotSettings.id == ROW_ID).first()
    if r:
        return r
    r = PaymentBotSettings(id=ROW_ID)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _validate_menu(menu: list[list[dict[str, str]]]) -> list[list[dict[str, str]]]:
    out: list[list[dict[str, str]]] = []
    for row in menu[:8]:
        if not isinstance(row, list):
            raise HTTPException(status_code=400, detail="main_menu must be an array of button-row arrays")
        out_row: list[dict[str, str]] = []
        for btn in row[:4]:
            if not isinstance(btn, dict):
                raise HTTPException(status_code=400, detail="main_menu buttons must be objects")
            label = str(btn.get("label") or "").strip()
            action = str(btn.get("action") or "").strip()
            if not label:
                raise HTTPException(status_code=400, detail="main_menu button label cannot be empty")
            if action not in ALLOWED_MENU_ACTIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"main_menu action must be one of: {', '.join(sorted(ALLOWED_MENU_ACTIONS))}",
                )
            out_row.append({"label": label[:64], "action": action})
        if out_row:
            out.append(out_row)
    if not out:
        raise HTTPException(status_code=400, detail="main_menu must contain at least one button")
    return out


def _row_overrides_dict(r: PaymentBotSettings) -> dict[str, Any]:
    menu = None
    if r.main_menu_json:
        try:
            menu = json.loads(r.main_menu_json)
        except Exception:
            menu = None
    return {
        "main_menu": menu,
        "welcome_html": r.welcome_html,
        "loot_intro_html": r.loot_intro_html,
        "subscribe_title_main": r.subscribe_title_main,
        "subscribe_title_loot": r.subscribe_title_loot,
        "subscription_catalog_columns": r.subscription_catalog_columns,
        "min_subscription_stars": r.min_subscription_stars,
        "runtime_adapter": r.runtime_adapter,
        "runtime_cmd_start": r.runtime_cmd_start,
        "runtime_cmd_stop": r.runtime_cmd_stop,
        "runtime_cmd_restart": r.runtime_cmd_restart,
        "runtime_cmd_reload": r.runtime_cmd_reload,
        "runtime_cmd_status": r.runtime_cmd_status,
    }


@router.get("")
def get_payment_bot_settings(db: Session = Depends(get_db)):
    _ensure_row(db)
    row = db.query(PaymentBotSettings).filter(PaymentBotSettings.id == ROW_ID).first()
    return {
        "effective": get_effective_payment_bot_settings(db),
        "overrides": _row_overrides_dict(row) if row else {},
    }


@router.patch("")
def patch_payment_bot_settings(body: PaymentBotSettingsPatch, db: Session = Depends(get_db)):
    r = _ensure_row(db)
    data = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)
    for key, val in data.items():
        if key == "main_menu":
            if val is None:
                r.main_menu_json = None
            else:
                r.main_menu_json = json.dumps(_validate_menu(val))
            continue
        if key == "runtime_adapter":
            if val is None or (isinstance(val, str) and not val.strip()):
                r.runtime_adapter = None
            else:
                v = str(val).strip().lower()
                if v not in ("local", "command"):
                    raise HTTPException(status_code=400, detail="runtime_adapter must be local or command")
                r.runtime_adapter = v
            continue
        if not hasattr(r, key):
            continue
        if val is None or (isinstance(val, str) and not val.strip()):
            setattr(r, key, None)
        else:
            setattr(r, key, val)
    db.commit()
    db.refresh(r)
    return {
        "ok": True,
        "effective": get_effective_payment_bot_settings(db),
        "overrides": _row_overrides_dict(r),
    }
