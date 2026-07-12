from __future__ import annotations

import os
import uuid
import asyncio
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.request import HTTPXRequest

from app.api.external_payment_orders import _require_internal
from app.database.session import get_db
from app.models.loot import LootModifier, LootPoolEligibility
from app.schemas.common import orm_to_dict
from app.services.bundle_storage import MAX_BUNDLE_ZIP_BYTES, bundle_root, is_zip_magic
from app.services.loot_free_pull import build_free_pull_preview, commit_free_pull, mark_free_pull_media_seen
from app.services.loot_vip_daily_pull import (
    build_vip_daily_pull_preview,
    commit_vip_daily_pull,
    vip_daily_pull_available,
    vip_daily_pull_used_today,
)
from app.services.loot_roll_preview import build_roll_preview
from app.services.loot_preview_delivery import send_loot_free_pull_to_chat, send_loot_preview_to_chat
from app.services.loot_creator_submit import submit_creator_profile
from app.services.loot_player_modifiers import record_modifiers_seen
from app.services.loot_player_stats import FREE_PULL_LIMIT, free_pull_allowance, free_pulls_remaining, record_roll
from app.services.subscription_access import is_loot_key_holder
from app.services.loot_referral import (
    bonus_free_pulls_for,
    ensure_loot_referral_code,
    loot_referrals_enabled,
    record_loot_referral,
    referral_bonus_pulls_setting,
    resolve_loot_referral_code,
)
from app.services.loot_bot_settings_effective import get_effective_loot_bot_settings, resolve_bot_token_raw

router = APIRouter()


def _run_loot_async(coro):
    """
    Run Telethon + PTB delivery off the uvicorn worker loop.
    Resets the admin session client so Saved Messages downloads succeed.
    """
    import concurrent.futures

    async def _inner():
        from app.services.telegram_admin import reset_admin_client

        await reset_admin_client()
        return await coro

    def _worker():
        return asyncio.run(_inner())

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_worker).result(timeout=300)


class LootModifierCreate(BaseModel):
    kind: str = Field(..., min_length=2, max_length=24)
    label: str | None = Field(None, max_length=256)
    target_url: str | None = None
    telegram_chat_id: int | None = None
    weight_base: float = Field(1.0, ge=0.0, le=1000.0)
    rarity_focus: float = Field(1.0, ge=0.0, le=1000.0)
    min_rarity_tier: int | None = Field(None, ge=1, le=10)
    bypass_vip: bool = False
    active: bool = True
    source_note: str | None = None


class LootModifierFromUrlBody(BaseModel):
    """Register a direct link as a loot roll modifier (no Media / Telegram upload)."""

    url: str = Field(..., min_length=8, max_length=8192)
    label: str | None = Field(None, max_length=256)
    kind: str = Field("other", min_length=2, max_length=24)
    source_note: str | None = Field(None, max_length=2000)
    weight_base: float = Field(1.0, ge=0.0, le=1000.0)
    rarity_focus: float = Field(1.0, ge=0.0, le=1000.0)
    min_rarity_tier: int | None = Field(None, ge=1, le=10)
    bypass_vip: bool = False
    active: bool = True
    as_zip_pack: bool = False
    random_high_tier: bool = False
    include_zip_promo: bool | None = None
    run_pipeline: bool = False
    wire_packs_scheduler: bool = False


class PackPoolQueueBody(BaseModel):
    """Queue a URL into the shared AOF pack + loot modifier pool."""

    url: str = Field(..., min_length=8, max_length=8192)
    label: str | None = Field(None, max_length=256)
    source_note: str | None = Field(None, max_length=2000)
    weight_base: float = Field(1.0, ge=0.0, le=1000.0)
    rarity_focus: float | None = Field(None, ge=0.0, le=1000.0)
    min_rarity_tier: int | None = Field(None, ge=1, le=10)
    active: bool = True
    wire_packs_scheduler: bool = False
    archive_entry_id: int | None = None
    preview_media_ids: list[int] | None = Field(
        None,
        description="Promo-pool media ids — pack preview stills for AOF PACKS channel albums",
    )


class LootModifierFromUrlBatchBody(BaseModel):
    """Batch register link modifiers (fast path: one DB commit for plain links)."""

    items: list[LootModifierFromUrlBody] = Field(..., min_length=1, max_length=250)


class LootModifierPatch(BaseModel):
    kind: str | None = Field(None, min_length=2, max_length=24)
    label: str | None = Field(None, max_length=256)
    target_url: str | None = None
    telegram_chat_id: int | None = None
    weight_base: float | None = Field(None, ge=0.0, le=1000.0)
    rarity_focus: float | None = Field(None, ge=0.0, le=1000.0)
    min_rarity_tier: int | None = Field(None, ge=1, le=10)
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
        f"Base roll: <b>{preview.get('base_roll_tier') or preview.get('rarity_tier') or '-'}</b>\n"
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


def _label_from_url(url: str, explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()[:256]
    try:
        host = (urlparse(url).hostname or "").strip()
        if host:
            return host[:256]
    except Exception:
        pass
    return "Link modifier"


@router.post("/modifiers/from-url")
async def create_modifier_from_url(
    body: LootModifierFromUrlBody,
    db: Session = Depends(get_db),
):
    """Add a URL to the loot modifier pool. Optionally download, zip, inject promo (local_zip_pack)."""
    try:
        return await _create_modifier_from_url_impl(body, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/pack-pool/queue")
def queue_pack_pool_url(
    body: PackPoolQueueBody,
    db: Session = Depends(get_db),
):
    """Resolve, gate-wrap, and queue a URL in the shared AOF pack + loot modifier pool."""
    from app.services.loot_pack_pool import (
        PACK_QUEUE_MARKER,
        queue_url_to_pack_pool,
        refresh_aof_packs_scheduler,
    )

    result = queue_url_to_pack_pool(
        db,
        body.url,
        label=body.label,
        source_note=(body.source_note or "").strip() or PACK_QUEUE_MARKER,
        weight_base=body.weight_base,
        rarity_focus=body.rarity_focus,
        min_rarity_tier=body.min_rarity_tier,
        active=body.active,
        archive_entry_id=body.archive_entry_id,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "queue_failed")
    if body.preview_media_ids and result.get("created"):
        from app.models.content_pool import ContentPool
        from app.services.aof_packs_post_copy import attach_preview_media_to_modifier
        from app.services.loot_pack_pool import POOL_NAME

        mod_id = (result.get("modifier") or {}).get("id")
        mod = db.query(LootModifier).filter(LootModifier.id == mod_id).first() if mod_id else None
        pool = db.query(ContentPool).filter(ContentPool.name == POOL_NAME).first()
        if mod:
            result["previews"] = attach_preview_media_to_modifier(
                db,
                mod,
                body.preview_media_ids,
                pool_id=int(pool.id) if pool else None,
            )
    if body.wire_packs_scheduler and result.get("created"):
        result["scheduler"] = refresh_aof_packs_scheduler(db)
    return result


@router.post("/pack-pool/refresh-scheduler")
def refresh_pack_pool_scheduler(db: Session = Depends(get_db)):
    """Re-wire AOF PACKS seed rotation from active pack-pool modifiers."""
    from app.services.loot_pack_pool import refresh_aof_packs_scheduler

    result = refresh_aof_packs_scheduler(db)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "refresh_failed")
    return result


class PackModifierPreviewsBody(BaseModel):
    """Attach promo-pool preview stills to a pack modifier (shown in PACKS channel albums)."""

    media_ids: list[int] = Field(..., min_length=1, max_length=12)
    wire_packs_scheduler: bool = False


@router.post("/pack-pool/modifiers/{modifier_id}/previews")
def attach_pack_modifier_previews(
    modifier_id: int,
    body: PackModifierPreviewsBody,
    db: Session = Depends(get_db),
):
    """Tag media + store preview_ids on a mega_pack row for rich AOF PACKS posts."""
    from app.models.content_pool import ContentPool
    from app.services.aof_packs_post_copy import attach_preview_media_to_modifier
    from app.services.loot_pack_pool import POOL_NAME, refresh_aof_packs_scheduler

    mod = (
        db.query(LootModifier)
        .filter(LootModifier.id == modifier_id, LootModifier.kind == "mega_pack")
        .first()
    )
    if not mod:
        raise HTTPException(status_code=404, detail="modifier_not_found")
    pool = db.query(ContentPool).filter(ContentPool.name == POOL_NAME).first()
    result = attach_preview_media_to_modifier(
        db,
        mod,
        body.media_ids,
        pool_id=int(pool.id) if pool else None,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "attach_failed")
    if body.wire_packs_scheduler:
        result["scheduler"] = refresh_aof_packs_scheduler(db)
    return result


async def _create_modifier_from_url_impl(body: LootModifierFromUrlBody, db: Session) -> dict:
    import random

    url = (body.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must be http(s)")

    min_tier = body.min_rarity_tier
    if body.as_zip_pack:
        if body.random_high_tier and min_tier is None:
            min_tier = random.choice([9, 10])
        elif min_tier is None:
            min_tier = 7

    if body.as_zip_pack:
        from app.services.loot_modifier_zip import fetch_url_bytes, prepare_zip_bytes, save_loot_modifier_zip

        try:
            raw, content_type, fname_hint = await fetch_url_bytes(url)
            zip_bytes = prepare_zip_bytes(raw, url, content_type)
            include_promo = body.include_zip_promo is not False
            _path, stored_name = save_loot_modifier_zip(
                zip_bytes,
                db=db,
                include_promo=include_promo,
                original_label=body.label or fname_hint,
            )
            public_url = f"{_public_base_url()}/static/bundles/loot_modifiers/{stored_name}"
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Download or zip failed: {e}") from e

        label = _label_from_url(url, body.label)
        if body.label and body.label.strip():
            label = body.label.strip()[:256]
        elif fname_hint:
            label = Path(fname_hint).stem[:256] or label

        m = LootModifier(
            kind="local_zip_pack",
            label=label,
            target_url=public_url,
            weight_base=float(body.weight_base),
            rarity_focus=float(body.rarity_focus if body.rarity_focus != 1.0 else 7.0),
            min_rarity_tier=int(min_tier) if min_tier is not None else 7,
            bypass_vip=bool(body.bypass_vip),
            active=bool(body.active),
            source_note=(body.source_note or "").strip() or "inbox:url-zip",
        )
        db.add(m)
        db.commit()
        db.refresh(m)
        d = orm_to_dict(m)
        d["as_zip_pack"] = True
        d["uploaded_bytes"] = len(zip_bytes)
        return d

    kind = (body.kind or "other").strip()
    if kind not in ("mega_pack", "telegram_group", "telegram_channel", "internal_route", "other"):
        kind = "other"

    use_pipeline = bool(body.run_pipeline or kind == "mega_pack")
    if use_pipeline:
        from app.services.loot_pack_pool import (
            PACK_QUEUE_MARKER,
            queue_url_to_pack_pool,
            refresh_aof_packs_scheduler,
        )

        note = (body.source_note or "").strip() or PACK_QUEUE_MARKER
        result = queue_url_to_pack_pool(
            db,
            url,
            label=body.label,
            source_note=note,
            weight_base=body.weight_base,
            rarity_focus=body.rarity_focus if body.rarity_focus != 1.0 else None,
            min_rarity_tier=min_tier,
            active=body.active,
        )
        if not result.get("ok"):
            raise ValueError(result.get("error") or "pipeline_failed")
        if body.wire_packs_scheduler and result.get("created"):
            result["scheduler"] = refresh_aof_packs_scheduler(db)
        return result

    m = LootModifier(
        kind=kind,
        label=_label_from_url(url, body.label),
        target_url=url,
        weight_base=float(body.weight_base),
        rarity_focus=float(body.rarity_focus),
        min_rarity_tier=min_tier,
        bypass_vip=bool(body.bypass_vip),
        active=bool(body.active),
        source_note=(body.source_note or "").strip() or "inbox:url",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return orm_to_dict(m)


def _simple_modifier_model(body: LootModifierFromUrlBody) -> LootModifier:
    url = (body.url or "").strip()
    kind = (body.kind or "other").strip()
    if kind not in ("mega_pack", "telegram_group", "telegram_channel", "internal_route", "other"):
        kind = "other"
    return LootModifier(
        kind=kind,
        label=_label_from_url(url, body.label),
        target_url=url,
        weight_base=float(body.weight_base),
        rarity_focus=float(body.rarity_focus),
        min_rarity_tier=body.min_rarity_tier,
        bypass_vip=bool(body.bypass_vip),
        active=bool(body.active),
        source_note=(body.source_note or "").strip() or "inbox:url",
    )


@router.post("/modifiers/from-url/batch")
async def create_modifiers_from_url_batch(
    body: LootModifierFromUrlBatchBody,
    db: Session = Depends(get_db),
):
    """
    Register many link modifiers in one request.
    Plain links: single DB commit. Zip-pack rows: processed sequentially (download + zip).
    """
    results: list[dict] = []
    ok_count = 0
    fail_count = 0
    simple_pending: list[tuple[int, LootModifierFromUrlBody, LootModifier]] = []
    zip_pending: list[tuple[int, LootModifierFromUrlBody]] = []
    pack_pending: list[tuple[int, LootModifierFromUrlBody]] = []

    for i, item in enumerate(body.items):
        url = (item.url or "").strip()
        if not url.startswith(("http://", "https://")):
            results.append({"index": i, "url": url, "ok": False, "error": "url must be http(s)"})
            fail_count += 1
            continue
        if item.as_zip_pack:
            zip_pending.append((i, item))
        elif (item.kind or "").strip() == "mega_pack" or item.run_pipeline:
            pack_pending.append((i, item))
        else:
            simple_pending.append((i, item, _simple_modifier_model(item)))

    if simple_pending:
        try:
            for _i, _item, model in simple_pending:
                db.add(model)
            db.commit()
            for i, item, model in simple_pending:
                db.refresh(model)
                results.append(
                    {
                        "index": i,
                        "url": (item.url or "").strip(),
                        "ok": True,
                        "modifier_id": model.id,
                        "as_zip_pack": False,
                    }
                )
                ok_count += 1
        except Exception as e:
            db.rollback()
            err = str(e)
            for i, item, _model in simple_pending:
                results.append({"index": i, "url": (item.url or "").strip(), "ok": False, "error": err})
                fail_count += 1

    for i, item in zip_pending:
        try:
            d = await _create_modifier_from_url_impl(item, db)
            results.append(
                {
                    "index": i,
                    "url": (item.url or "").strip(),
                    "ok": True,
                    "modifier_id": d.get("id") or (d.get("modifier") or {}).get("id"),
                    "as_zip_pack": True,
                }
            )
            ok_count += 1
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else str(e.detail)
            results.append({"index": i, "url": (item.url or "").strip(), "ok": False, "error": detail})
            fail_count += 1
        except ValueError as e:
            results.append({"index": i, "url": (item.url or "").strip(), "ok": False, "error": str(e)})
            fail_count += 1

    for i, item in pack_pending:
        try:
            d = await _create_modifier_from_url_impl(item, db)
            results.append(
                {
                    "index": i,
                    "url": (item.url or "").strip(),
                    "ok": True,
                    "modifier_id": d.get("id") or (d.get("modifier") or {}).get("id"),
                    "duplicate": bool(d.get("duplicate")),
                    "pack_pool": True,
                }
            )
            ok_count += 1
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else str(e.detail)
            results.append({"index": i, "url": (item.url or "").strip(), "ok": False, "error": detail})
            fail_count += 1
        except ValueError as e:
            results.append({"index": i, "url": (item.url or "").strip(), "ok": False, "error": str(e)})
            fail_count += 1

    results.sort(key=lambda x: int(x.get("index", 0)))
    return {"ok_count": ok_count, "fail_count": fail_count, "results": results}


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
        min_rarity_tier=body.min_rarity_tier,
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
    rarity_focus: float = Query(7.0, ge=0.0, le=1000.0),
    min_rarity_tier: int = Query(7, ge=1, le=10),
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
    from app.services.zip_promo_inject import inject_promo_into_zip_path

    inject_promo_into_zip_path(out, db, include_promo=True)

    public_url = f"{_public_base_url()}/static/bundles/loot_modifiers/{fname}"
    m = LootModifier(
        kind="local_zip_pack",
        label=(label or safe_base).strip()[:256] if (label or safe_base).strip() else safe_base,
        target_url=public_url,
        weight_base=float(weight_base),
        rarity_focus=float(rarity_focus),
        min_rarity_tier=int(min_rarity_tier),
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


def _payment_bot_username() -> str | None:
    return (os.getenv("TBCC_PAYMENT_BOT_USERNAME") or "").strip().lstrip("@") or None


def _loot_bot_username(db: Session) -> str:
    eff = get_effective_loot_bot_settings(db)
    return (eff.get("bot_username") or "aof_lootgod_bot").strip().lstrip("@")


class LootReferralRecordBody(BaseModel):
    referred_user_id: int = Field(..., ge=1)
    referrer_code: str = Field(..., min_length=4, max_length=16)


class LootCreatorSubmitBody(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    telegram_user_id: int | None = Field(None, ge=1)
    handle: str | None = Field(None, max_length=64)


@router.post("/referrals/record")
def loot_referral_record(body: LootReferralRecordBody, db: Session = Depends(get_db)):
    referrer_id = resolve_loot_referral_code(db, body.referrer_code)
    if not referrer_id:
        raise HTTPException(status_code=404, detail="Unknown referral code")
    ok = record_loot_referral(
        db,
        referred_user_id=int(body.referred_user_id),
        referrer_user_id=int(referrer_id),
    )
    return {"ok": ok, "referrer_user_id": int(referrer_id)}


@router.get("/referrals/status")
def loot_referral_status(
    telegram_user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    uid = int(telegram_user_id)
    rem = free_pulls_remaining(db, uid)
    allowance = free_pull_allowance(db, uid)
    used = max(0, allowance - rem)
    bonus = bonus_free_pulls_for(db, uid)
    code_payload = ensure_loot_referral_code(db, uid)
    bot_un = _loot_bot_username(db)
    link = f"https://t.me/{bot_un}?start={code_payload['start_param']}"
    return {
        "telegram_user_id": uid,
        "loot_referrals_enabled": loot_referrals_enabled(db),
        "referral_bonus_per_friend": referral_bonus_pulls_setting(db),
        "code": code_payload["code"],
        "referral_link": link,
        "start_param": code_payload["start_param"],
        "base_free_pull_limit": FREE_PULL_LIMIT,
        "bonus_free_pulls": bonus,
        "total_allowance": allowance,
        "free_pulls_used": used,
        "free_pulls_remaining": rem,
    }


@router.post("/creator-submit")
def loot_creator_submit(body: LootCreatorSubmitBody, db: Session = Depends(get_db)):
    """Creator profile → active loot modifier (tier 5+). Self-serve for models."""
    try:
        return submit_creator_profile(
            db,
            url=body.url,
            telegram_user_id=body.telegram_user_id,
            handle=body.handle,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/free-pull/status")
def free_pull_status(
    telegram_user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    uid = int(telegram_user_id)
    rem = free_pulls_remaining(db, uid)
    allowance = free_pull_allowance(db, uid)
    used = max(0, allowance - rem)
    return {
        "telegram_user_id": uid,
        "free_pull_limit": allowance,
        "base_free_pull_limit": FREE_PULL_LIMIT,
        "bonus_free_pulls": bonus_free_pulls_for(db, uid),
        "free_pulls_used": used,
        "free_pulls_remaining": rem,
        "loot_referrals_enabled": loot_referrals_enabled(db),
    }


@router.post("/free-pull/claim")
def claim_free_pull(
    telegram_user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    """
    Deal one complimentary DM pull via @aof_lootgod_bot (max 5 per account).
    Tier ≤5, one spoiler item, no real modifiers — tease block only.
    """
    preview = build_free_pull_preview(db, telegram_user_id=telegram_user_id)
    if not preview.get("ok"):
        if preview.get("reason") == "free_pulls_exhausted":
            pay = _payment_bot_username()
            pay_hint = f"https://t.me/{pay}?start=loot" if pay else "payment bot /loot"
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "free_pulls_exhausted",
                    "message": "No free pulls left on this account. Paid room runs include real modifiers.",
                    "payment_link": pay_hint,
                    "free_pull_limit": free_pull_allowance(db, telegram_user_id),
                    "referral_hint": "/referral on @aof_lootgod_bot for bonus pulls",
                },
            )
        raise HTTPException(status_code=400, detail=preview.get("reason") or "roll failed")

    token = resolve_bot_token_raw(db)
    if not token:
        raise HTTPException(status_code=400, detail="Loot bot token not configured")
    bot = Bot(
        token=token,
        request=HTTPXRequest(connect_timeout=30.0, read_timeout=180.0, write_timeout=180.0),
    )
    eff = get_effective_loot_bot_settings(db)
    spoiler = bool(eff.get("drop_spoiler_default", True))
    rem_before = int(preview.get("free_pulls_remaining_before") or 0)

    async def _run():
        from app.database.session import SessionLocal

        worker_db = SessionLocal()
        try:
            return await send_loot_free_pull_to_chat(
                worker_db,
                bot=bot,
                chat_id=int(telegram_user_id),
                preview=preview,
                spoiler_default=spoiler,
                payment_bot_username=_payment_bot_username(),
                free_pulls_remaining=max(0, rem_before - 1),
            )
        finally:
            worker_db.close()

    delivery = _run_loot_async(_run())
    if int(delivery.get("media_sent") or 0) > 0:
        preview = commit_free_pull(db, telegram_user_id, preview)
    else:
        preview = dict(preview)
        preview["free_pulls_remaining"] = rem_before
    return {
        "ok": True,
        "sent_to": telegram_user_id,
        "preview": preview,
        "delivery": delivery,
    }


@router.get("/key-roll/status")
def key_roll_status(
    telegram_user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    uid = int(telegram_user_id)
    return {
        "telegram_user_id": uid,
        "is_loot_key_holder": is_loot_key_holder(db, uid),
        "free_pulls_remaining": free_pulls_remaining(db, uid),
    }


@router.post("/key-roll/claim")
def claim_key_roll(
    telegram_user_id: int = Query(..., ge=1),
    interval_code: str = Query("m30", pattern=r"^m(15|30|45|60)$"),
    seed: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Paid loot-key full roll: ladder + modifiers + card reveal beat.
    Requires active subscription_plans.bot_section='loot'.
    """
    uid = int(telegram_user_id)
    if not is_loot_key_holder(db, uid):
        pay = _payment_bot_username()
        pay_hint = f"https://t.me/{pay}?start=loot" if pay else "payment bot /loot"
        raise HTTPException(
            status_code=403,
            detail={
                "reason": "not_loot_key_holder",
                "message": "Active Loot Room key required for full rolls with modifiers.",
                "payment_link": pay_hint,
            },
        )

    preview = build_roll_preview(
        db,
        telegram_user_id=uid,
        interval_code=interval_code,
        seed=seed,
    )
    if not preview.get("ok"):
        raise HTTPException(status_code=400, detail=preview.get("reason") or "roll failed")

    token = resolve_bot_token_raw(db)
    if not token:
        raise HTTPException(status_code=400, detail="Loot bot token not configured")
    bot = Bot(
        token=token,
        request=HTTPXRequest(connect_timeout=30.0, read_timeout=180.0, write_timeout=180.0),
    )
    eff = get_effective_loot_bot_settings(db)
    spoiler = bool(eff.get("drop_spoiler_default", True))

    async def _run():
        from app.database.session import SessionLocal

        worker_db = SessionLocal()
        try:
            return await send_loot_preview_to_chat(
                worker_db,
                bot=bot,
                chat_id=uid,
                preview=preview,
                spoiler_default=spoiler,
                include_affiliate_footer=True,
            )
        finally:
            worker_db.close()

    delivery = _run_loot_async(_run())
    if int(delivery.get("media_sent") or 0) > 0:
        record_roll(db, uid)
        media_ids = [int(m["id"]) for m in (preview.get("media") or []) if m.get("id") is not None]
        if media_ids:
            mark_free_pull_media_seen(db, uid, media_ids)
        mod_ids = [int(m["id"]) for m in (preview.get("modifiers") or []) if m.get("id") is not None]
        if mod_ids:
            record_modifiers_seen(db, uid, mod_ids)
    preview = dict(preview)
    preview["roll_kind"] = "key_roll"
    return {
        "ok": True,
        "roll_kind": "key_roll",
        "sent_to": uid,
        "preview": preview,
        "delivery": delivery,
    }


@router.get("/vip-daily-pull/status")
def vip_daily_pull_status(
    telegram_user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    uid = int(telegram_user_id)
    from app.services.subscription_access import is_aof_vip_subscriber

    return {
        "telegram_user_id": uid,
        "is_vip_subscriber": is_aof_vip_subscriber(db, uid),
        "available_today": vip_daily_pull_available(db, uid),
        "claimed_today": vip_daily_pull_used_today(db, uid),
    }


@router.post("/vip-daily-pull/claim")
def claim_vip_daily_pull(
    telegram_user_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    """VIP subscriber daily god roll — high tier, one per UTC day."""
    preview = build_vip_daily_pull_preview(db, telegram_user_id=telegram_user_id)
    if not preview.get("ok"):
        reason = preview.get("reason") or "roll_failed"
        if reason == "not_vip_subscriber":
            pay = _payment_bot_username()
            pay_hint = f"https://t.me/{pay}?start=subscribe" if pay else "payment bot /subscribe"
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": reason,
                    "message": preview.get("message") or "AOF VIP subscription required.",
                    "payment_link": pay_hint,
                },
            )
        if reason == "vip_daily_already_claimed":
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": reason,
                    "message": preview.get("message") or "Daily god roll already claimed today.",
                },
            )
        raise HTTPException(status_code=400, detail=preview.get("reason") or "roll failed")

    token = resolve_bot_token_raw(db)
    if not token:
        raise HTTPException(status_code=400, detail="Loot bot token not configured")
    bot = Bot(
        token=token,
        request=HTTPXRequest(connect_timeout=30.0, read_timeout=180.0, write_timeout=180.0),
    )
    eff = get_effective_loot_bot_settings(db)
    spoiler = bool(eff.get("drop_spoiler_default", True))

    async def _run():
        from app.database.session import SessionLocal

        worker_db = SessionLocal()
        try:
            return await send_loot_free_pull_to_chat(
                worker_db,
                bot=bot,
                chat_id=int(telegram_user_id),
                preview=preview,
                spoiler_default=spoiler,
                payment_bot_username=_payment_bot_username(),
                free_pulls_remaining=None,
            )
        finally:
            worker_db.close()

    delivery = _run_loot_async(_run())
    if int(delivery.get("media_sent") or 0) > 0:
        preview = commit_vip_daily_pull(db, telegram_user_id, preview)
    return {
        "ok": True,
        "sent_to": telegram_user_id,
        "preview": preview,
        "delivery": delivery,
    }


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


@router.get("/pool-eligibility")
def list_pool_eligibility(db: Session = Depends(get_db)):
    rows = db.query(LootPoolEligibility).order_by(LootPoolEligibility.content_pool_id.asc()).all()
    return [orm_to_dict(x) for x in rows]


@router.post("/seed-loot-room-eligibility")
def seed_loot_room_eligibility(db: Session = Depends(get_db)):
    """
    One-shot: map LOOT ROOM* content pools into loot_pool_eligibility (FLOOR band 1–5,
    SPOTLIGHT 5–7, VAULT/RELIC/MYTHIC 7–10). Safe to call again (upserts).
    """
    from app.services.loot_pool_eligibility_seed import seed_loot_room_pool_eligibility

    rows = seed_loot_room_pool_eligibility(db)
    return {"ok": True, "count": len(rows), "pools": rows}


@router.post("/seed-content-pool-eligibility")
def seed_content_pool_eligibility(db: Session = Depends(get_db)):
    """
    Map live content pools (with approved media) into loot_pool_eligibility so rolls
    draw from the existing library. Disables empty LOOT ROOM placeholder pools.
    Safe to call again (upserts).
    """
    from app.services.loot_pool_eligibility_seed import seed_content_pool_loot_eligibility

    report = seed_content_pool_loot_eligibility(db)
    return {"ok": True, **report}


@router.get("/tier-coverage")
def loot_tier_coverage(db: Session = Depends(get_db)):
    from app.services.loot_pool_eligibility_seed import tier_coverage_report

    return tier_coverage_report(db)


class LootPoolEligibilityUpsert(BaseModel):
    content_pool_id: int = Field(..., ge=1)
    loot_enabled: bool = True
    base_weight: float = Field(1.0, ge=0.0, le=1000.0)
    min_rarity_tier: int | None = Field(None, ge=1, le=10)
    max_rarity_tier: int | None = Field(None, ge=1, le=10)


@router.post("/pool-eligibility")
def upsert_pool_eligibility(body: LootPoolEligibilityUpsert, db: Session = Depends(get_db)):
    row = (
        db.query(LootPoolEligibility)
        .filter(LootPoolEligibility.content_pool_id == body.content_pool_id)
        .first()
    )
    if not row:
        row = LootPoolEligibility(content_pool_id=body.content_pool_id)
        db.add(row)
    row.loot_enabled = bool(body.loot_enabled)
    row.base_weight = float(body.base_weight)
    row.min_rarity_tier = body.min_rarity_tier
    row.max_rarity_tier = body.max_rarity_tier
    db.commit()
    db.refresh(row)
    return orm_to_dict(row)


@router.post("/send-preview-dm")
def send_preview_dm(
    telegram_user_id: int | None = Query(None, ge=1),
    interval_code: str = Query("m30", pattern=r"^m(15|30|45|60)$"),
    seed: int | None = Query(None),
    to_telegram_user_id: int | None = Query(None, ge=1),
    text_only: bool = Query(False, description="If true, send summary text only (no album/zips)"),
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
    bot = Bot(
        token=token,
        request=HTTPXRequest(connect_timeout=30.0, read_timeout=180.0, write_timeout=180.0),
    )
    eff = get_effective_loot_bot_settings(db)
    spoiler = bool(eff.get("drop_spoiler_default", True))

    async def _run():
        return await send_loot_preview_to_chat(
            db, bot=bot, chat_id=target, preview=preview, spoiler_default=spoiler
        )

    if text_only:

        async def _text_only():
            text = _preview_caption_text(preview)
            await bot.send_message(chat_id=target, text=text, parse_mode="HTML", disable_web_page_preview=False)
            return {"text_only": True}

        delivery = asyncio.run(_text_only())
    else:
        delivery = _run_loot_async(_run())
    if preview.get("ok") and not text_only:
        record_roll(db, target)
        mod_ids = [int(m["id"]) for m in (preview.get("modifiers") or []) if m.get("id") is not None]
        if mod_ids:
            record_modifiers_seen(db, int(target), mod_ids)
    return {"ok": True, "sent_to": target, "preview": preview, "delivery": delivery}
