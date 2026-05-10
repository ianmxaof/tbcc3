from __future__ import annotations

import os
import uuid
import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from telegram import Bot

from app.api.external_payment_orders import _require_internal
from app.database.session import get_db
from app.models.loot import LootModifier
from app.schemas.common import orm_to_dict
from app.services.bundle_storage import MAX_BUNDLE_ZIP_BYTES, bundle_root, is_zip_magic
from app.services.loot_roll_preview import build_roll_preview
from app.services.loot_bot_settings_effective import resolve_bot_token_raw

router = APIRouter()


class LootModifierCreate(BaseModel):
    kind: str = Field(..., min_length=2, max_length=24)
    label: str | None = Field(None, max_length=256)
    target_url: str | None = None
    telegram_chat_id: int | None = None
    weight_base: float = Field(1.0, ge=0.0, le=1000.0)
    rarity_focus: float = Field(1.0, ge=0.0, le=1000.0)
    bypass_vip: bool = False
    active: bool = True
    source_note: str | None = None


class LootModifierPatch(BaseModel):
    kind: str | None = Field(None, min_length=2, max_length=24)
    label: str | None = Field(None, max_length=256)
    target_url: str | None = None
    telegram_chat_id: int | None = None
    weight_base: float | None = Field(None, ge=0.0, le=1000.0)
    rarity_focus: float | None = Field(None, ge=0.0, le=1000.0)
    bypass_vip: bool | None = None
    active: bool | None = None
    source_note: str | None = None


def _public_base_url() -> str:
    return (
        (os.getenv("TBCC_PROMO_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_PUBLIC_BASE_URL") or "").strip()
        or (os.getenv("TBCC_API_URL") or "").strip()
        or "http://127.0.0.1:8000"
    ).rstrip("/")


def _preview_caption_text(preview: dict) -> str:
    if not preview.get("ok"):
        return f"Loot dry-roll failed: {preview.get('reason') or 'unknown error'}"
    media = preview.get("media") or []
    mods = preview.get("modifiers") or []
    mod_lines: list[str] = []
    for m in mods:
        label = (m.get("label") or m.get("kind") or "modifier").strip()
        url = (m.get("target_url") or "").strip()
        mod_lines.append(f"- {label}{f' -> {url}' if url else ''}")
    return (
        f"🎁 <b>Loot Dry Roll</b>\n"
        f"Interval: <code>{preview.get('interval_code') or '-'}</code>\n"
        f"Tier: <b>{preview.get('rarity_tier') or '-'}</b>\n"
        f"Album size: <b>{preview.get('album_size') or 0}</b>\n"
        f"Modifier slots: <b>{preview.get('modifier_slot_count') or 0}</b>\n\n"
        f"<b>Media IDs</b>\n"
        f"{', '.join(str(x.get('id')) for x in media) if media else 'none'}\n\n"
        f"<b>Modifiers</b>\n"
        f"{chr(10).join(mod_lines) if mod_lines else '- none'}"
    )


@router.get("/modifiers")
def list_modifiers(
    include_inactive: bool = Query(True),
    db: Session = Depends(get_db),
):
    q = db.query(LootModifier).order_by(LootModifier.id.desc())
    if not include_inactive:
        q = q.filter(LootModifier.active.is_(True))
    return [orm_to_dict(x) for x in q.all()]


@router.post("/modifiers")
def create_modifier(
    body: LootModifierCreate,
    db: Session = Depends(get_db),
):
    m = LootModifier(
        kind=body.kind.strip(),
        label=(body.label or "").strip() or None,
        target_url=(body.target_url or "").strip() or None,
        telegram_chat_id=body.telegram_chat_id,
        weight_base=float(body.weight_base),
        rarity_focus=float(body.rarity_focus),
        bypass_vip=bool(body.bypass_vip),
        active=bool(body.active),
        source_note=(body.source_note or "").strip() or None,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return orm_to_dict(m)


@router.patch("/modifiers/{modifier_id}")
def patch_modifier(
    modifier_id: int,
    body: LootModifierPatch,
    db: Session = Depends(get_db),
):
    m = db.query(LootModifier).filter(LootModifier.id == modifier_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Modifier not found")
    data = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)
    for key, val in data.items():
        if not hasattr(m, key):
            continue
        if key in ("label", "target_url", "source_note", "kind"):
            if val is None:
                setattr(m, key, None)
            else:
                sval = str(val).strip()
                setattr(m, key, sval or None)
        else:
            setattr(m, key, val)
    db.commit()
    db.refresh(m)
    return orm_to_dict(m)


@router.delete("/modifiers/{modifier_id}")
def delete_modifier(
    modifier_id: int,
    db: Session = Depends(get_db),
):
    m = db.query(LootModifier).filter(LootModifier.id == modifier_id).first()
    if not m:
        return {"deleted": 0}
    db.delete(m)
    db.commit()
    return {"deleted": 1}


@router.post("/modifiers/upload-zip")
async def upload_zip_modifier(
    file: UploadFile = File(...),
    label: str | None = Query(None, max_length=256),
    weight_base: float = Query(1.0, ge=0.0, le=1000.0),
    rarity_focus: float = Query(1.0, ge=0.0, le=1000.0),
    active: bool = Query(True),
    bypass_vip: bool = Query(False),
    source_note: str | None = Query(None),
    db: Session = Depends(get_db),
):
    name = (file.filename or "pack.zip").strip()
    if not name.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are allowed")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_BUNDLE_ZIP_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Zip too large (max {MAX_BUNDLE_ZIP_BYTES // (1024 * 1024)} MiB)",
        )
    if not is_zip_magic(data[:8]):
        raise HTTPException(status_code=400, detail="Invalid zip file (bad header)")

    safe_base = Path(name).name
    folder = bundle_root() / "loot_modifiers"
    folder.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex}_{safe_base}"
    out = folder / fname
    out.write_bytes(data)

    public_url = f"{_public_base_url()}/static/bundles/loot_modifiers/{fname}"
    m = LootModifier(
        kind="local_zip_pack",
        label=(label or safe_base).strip()[:256] if (label or safe_base).strip() else safe_base,
        target_url=public_url,
        weight_base=float(weight_base),
        rarity_focus=float(rarity_focus),
        bypass_vip=bool(bypass_vip),
        active=bool(active),
        source_note=((source_note or "").strip() or None),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    d = orm_to_dict(m)
    d["uploaded_bytes"] = len(data)
    return d


@router.get("/roll-preview")
def roll_preview(
    telegram_user_id: int | None = Query(None, ge=1),
    interval_code: str = Query("m30", pattern=r"^m(15|30|45|60)$"),
    seed: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Internal dry-run preview for the loot roll algorithm.
    Does NOT send Telegram messages and does NOT persist drop rows.
    """
    try:
        return build_roll_preview(
            db,
            telegram_user_id=telegram_user_id,
            interval_code=interval_code,
            seed=seed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/send-preview-dm")
def send_preview_dm(
    telegram_user_id: int | None = Query(None, ge=1),
    interval_code: str = Query("m30", pattern=r"^m(15|30|45|60)$"),
    seed: int | None = Query(None),
    to_telegram_user_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    preview = build_roll_preview(
        db,
        telegram_user_id=telegram_user_id,
        interval_code=interval_code,
        seed=seed,
    )
    target = to_telegram_user_id or int((os.getenv("ADMIN_TELEGRAM_ID") or "0").strip() or "0")
    if target <= 0:
        raise HTTPException(status_code=400, detail="Set ADMIN_TELEGRAM_ID or pass to_telegram_user_id")
    token = resolve_bot_token_raw(db)
    if not token:
        raise HTTPException(status_code=400, detail="Loot bot token not configured")
    text = _preview_caption_text(preview)
    bot = Bot(token=token)
    asyncio.run(bot.send_message(chat_id=target, text=text, parse_mode="HTML", disable_web_page_preview=False))
    return {"ok": True, "sent_to": target, "preview": preview}
