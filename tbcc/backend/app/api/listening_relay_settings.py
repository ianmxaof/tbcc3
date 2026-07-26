"""Dashboard: listening activity relay (Last.fm poll + IFTTT/webhook)."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.listening_relay_settings import ListeningRelaySettings
from app.services.listening_relay_ascii import (
    RELAY_ASCII_MAX_LINES,
    RELAY_ASCII_MAX_WIDTH,
    add_user_ascii_entry,
    list_all_ascii_entries,
    remove_user_ascii_entry,
    validate_ascii_content,
)
from app.services.listening_relay_compose import RelayOutbound, build_relay_outbound
from app.services.listening_relay_lastfm import fetch_recent_track_lastfm_sync
from app.services.listening_relay_send import followups_to_json
from app.services.listening_relay_target import (
    relay_destinations_for_api,
    relay_has_send_target,
    relay_random_network_enabled,
    resolve_listening_relay_send_target,
)
from app.services.listening_relay_history import list_listening_relay_posts, queue_listening_relay_post
from app.services.listening_relay_slot import normalize_slot_extra, slot_extras_for_api
from app.services.listening_relay_templates import get_copy_block_variations_for_api, get_footer_variations_for_api, get_template_variations_list

logger = logging.getLogger(__name__)

router = APIRouter()

ROW_ID = 1


class ListeningRelayPatch(BaseModel):
    enabled: bool | None = None
    channel_id: int | None = None
    relay_random_network_channel: bool | None = None
    message_thread_id: int | None = None
    lastfm_username: str | None = Field(None, max_length=256)
    lastfm_api_key: str | None = Field(None, max_length=128)
    poll_interval_minutes: int | None = Field(None, ge=1, le=120)
    message_template_html: str | None = None
    message_template_variations: list[str] | None = None
    message_footer_html: str | None = None
    message_footer_variations: list[str] | None = None
    message_copy_block_variations: list[str] | None = None
    message_slot_extras: list[dict] | None = None
    template_rotation_mode: str | None = None
    ascii_art_enabled: bool | None = None
    ascii_art_min_interval: int | None = Field(None, ge=1, le=50)
    ascii_art_max_interval: int | None = Field(None, ge=1, le=50)
    tryptych_enabled: bool | None = None
    tryptych_on_ascii_beat: bool | None = None
    send_silent: bool | None = None
    buffer_relay_enabled: bool | None = None
    buffer_relay_min_interval_minutes: int | None = Field(None, ge=30, le=1440)
    buffer_relay_max_per_day_utc: int | None = Field(None, ge=1, le=50)
    buffer_x_queue: list[dict] | None = None
    goblin_mode_enabled: bool | None = None
    goblin_spawn_chance: float | None = Field(None, ge=0.0, le=1.0)
    goblin_cooldown_minutes: int | None = Field(None, ge=0, le=1440)
    goblin_announce_ttl_seconds: int | None = Field(None, ge=5, le=300)
    goblin_claims_cap: int | None = Field(None, ge=1, le=100)
    goblin_max_per_day_utc: int | None = Field(None, ge=1, le=50)
    clear_lastfm_dedupe: bool | None = None
    clear_webhook_dedupe: bool | None = None
    regenerate_webhook_secret: bool | None = None


def _ensure_row(db: Session) -> ListeningRelaySettings:
    r = db.query(ListeningRelaySettings).filter(ListeningRelaySettings.id == ROW_ID).first()
    if r:
        return r
    r = ListeningRelaySettings(id=ROW_ID)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _mask(s: str | None) -> str | None:
    if not s:
        return None
    t = s.strip()
    if len(t) <= 4:
        return "••••"
    return "••••" + t[-4:]


def _row_public(row: ListeningRelaySettings) -> dict[str, Any]:
    variants = get_template_variations_list(row)
    return {
        "enabled": bool(row.enabled),
        "channel_id": row.channel_id,
        "relay_random_network_channel": bool(getattr(row, "relay_random_network_channel", False)),
        "message_thread_id": row.message_thread_id,
        "lastfm_username": row.lastfm_username,
        "lastfm_api_key_masked": _mask(row.lastfm_api_key),
        "poll_interval_minutes": int(row.poll_interval_minutes or 3),
        "message_template_html": row.message_template_html,
        "message_template_variations": variants,
        "template_rotation_active": len(variants) >= 2,
        "message_footer_html": row.message_footer_html,
        "message_footer_variations": get_footer_variations_for_api(row),
        "message_copy_block_variations": get_copy_block_variations_for_api(row),
        "message_slot_extras": slot_extras_for_api(row, len(variants)),
        "template_rotation_mode": str(getattr(row, "template_rotation_mode", None) or "sequential"),
        "ascii_art_enabled": bool(getattr(row, "ascii_art_enabled", False)),
        "ascii_art_min_interval": int(getattr(row, "ascii_art_min_interval", None) or 3),
        "ascii_art_max_interval": int(getattr(row, "ascii_art_max_interval", None) or 6),
        "ascii_art_scrobble_counter": int(getattr(row, "ascii_art_scrobble_counter", None) or 0),
        "ascii_art_next_threshold": getattr(row, "ascii_art_next_threshold", None),
        "tryptych_enabled": bool(getattr(row, "tryptych_enabled", False)),
        "tryptych_on_ascii_beat": bool(getattr(row, "tryptych_on_ascii_beat", True)),
        "ascii_art_max_width": RELAY_ASCII_MAX_WIDTH,
        "ascii_art_max_lines": RELAY_ASCII_MAX_LINES,
        "webhook_secret_masked": _mask(row.webhook_secret),
        "send_silent": bool(row.send_silent),
        "buffer_relay_enabled": bool(getattr(row, "buffer_relay_enabled", False)),
        "buffer_relay_min_interval_minutes": int(getattr(row, "buffer_relay_min_interval_minutes", None) or 360),
        "buffer_relay_max_per_day_utc": int(getattr(row, "buffer_relay_max_per_day_utc", None) or 5),
        "buffer_relay_utc_day": getattr(row, "buffer_relay_utc_day", None),
        "buffer_relay_posts_today": int(getattr(row, "buffer_relay_posts_today", None) or 0),
        "buffer_relay_last_post_at": (
            row.buffer_relay_last_post_at.isoformat() + "Z" if getattr(row, "buffer_relay_last_post_at", None) else None
        ),
        "buffer_x_queue": row.get_buffer_x_queue(),
        "buffer_x_queue_depth": len(row.get_buffer_x_queue()),
        "goblin_mode_enabled": bool(getattr(row, "goblin_mode_enabled", False)),
        "goblin_spawn_chance": float(getattr(row, "goblin_spawn_chance", None) or 0.2),
        "goblin_cooldown_minutes": int(getattr(row, "goblin_cooldown_minutes", None) or 120),
        "goblin_announce_ttl_seconds": int(getattr(row, "goblin_announce_ttl_seconds", None) or 45),
        "goblin_claims_cap": int(getattr(row, "goblin_claims_cap", None) or 5),
        "goblin_max_per_day_utc": int(getattr(row, "goblin_max_per_day_utc", None) or 3),
        "goblin_spawns_today": int(getattr(row, "goblin_spawns_today", None) or 0),
        "goblin_utc_day": getattr(row, "goblin_utc_day", None),
        "goblin_last_spawn_at": (
            row.goblin_last_spawn_at.isoformat() + "Z" if getattr(row, "goblin_last_spawn_at", None) else None
        ),
        "last_poll_at": row.last_poll_at.isoformat() + "Z" if row.last_poll_at else None,
        "has_lastfm_dedupe": row.last_lastfm_signature is not None,
        "has_webhook_dedupe": row.last_webhook_signature is not None,
    }


@router.get("/history")
def get_listening_relay_history(
    db: Session = Depends(get_db),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Recent listening-relay posts (Telegram + fan-out metadata)."""
    return list_listening_relay_posts(db, limit=limit, offset=offset)


@router.get("/destinations")
def get_listening_relay_destinations(db: Session = Depends(get_db)):
    """Loot Room topics, VIP channel id, and network size for dashboard destination picker."""
    return relay_destinations_for_api(db)


@router.get("")
def get_listening_relay_settings(db: Session = Depends(get_db)):
    row = _ensure_row(db)
    fresh_secret: str | None = None
    if not (row.webhook_secret or "").strip():
        row.webhook_secret = secrets.token_urlsafe(24)[:32]
        db.commit()
        db.refresh(row)
        fresh_secret = row.webhook_secret
    out: dict[str, Any] = {"settings": _row_public(row)}
    if fresh_secret:
        out["webhook_secret"] = fresh_secret
    return out


@router.patch("")
def patch_listening_relay_settings(body: ListeningRelayPatch, db: Session = Depends(get_db)):
    row = _ensure_row(db)
    regen_secret = bool(body.regenerate_webhook_secret)
    data = body.model_dump(exclude_unset=True)
    if data.get("regenerate_webhook_secret"):
        row.webhook_secret = secrets.token_urlsafe(24)[:32]
    if data.get("clear_lastfm_dedupe"):
        row.last_lastfm_signature = None
    if data.get("clear_webhook_dedupe"):
        row.last_webhook_signature = None
    for k in (
        "regenerate_webhook_secret",
        "clear_lastfm_dedupe",
        "clear_webhook_dedupe",
    ):
        data.pop(k, None)

    if "enabled" in data and data["enabled"] is not None:
        row.enabled = bool(data["enabled"])
    if "channel_id" in data:
        row.channel_id = data["channel_id"]
        if data["channel_id"] is not None:
            row.relay_random_network_channel = False
    if "relay_random_network_channel" in data and data["relay_random_network_channel"] is not None:
        row.relay_random_network_channel = bool(data["relay_random_network_channel"])
        if row.relay_random_network_channel:
            row.channel_id = None
            row.message_thread_id = None
    if "message_thread_id" in data:
        row.message_thread_id = data["message_thread_id"]
        if row.message_thread_id is not None:
            row.relay_random_network_channel = False
    if "lastfm_username" in data:
        v = data["lastfm_username"]
        row.lastfm_username = (v.strip() or None) if isinstance(v, str) else v
    if "lastfm_api_key" in data and data["lastfm_api_key"] is not None:
        t = str(data["lastfm_api_key"]).strip()
        row.lastfm_api_key = t or None
    if "poll_interval_minutes" in data and data["poll_interval_minutes"] is not None:
        row.poll_interval_minutes = int(data["poll_interval_minutes"])

    if "message_template_variations" in data:
        raw_list = data.pop("message_template_variations")
        raw_footers = data.pop("message_footer_variations", None)
        raw_copy = data.pop("message_copy_block_variations", None)
        raw_extras = data.pop("message_slot_extras", None)
        if raw_list is None:
            row.message_template_variations = None
            row.message_template_rotation_index = None
            row.message_footer_variations = None
            row.message_footer_html = None
            row.message_copy_block_variations = None
            row.message_slot_extras_json = None
        elif isinstance(raw_list, list):
            nv: list[str] = []
            footers_parallel: list[str] = []
            copy_parallel: list[str] = []
            extras_parallel: list[dict] = []
            for i, t in enumerate(raw_list):
                ts = str(t if t is not None else "").strip()
                fo = ""
                cb = ""
                ex: dict = {}
                if isinstance(raw_footers, list) and i < len(raw_footers):
                    fo = str(raw_footers[i] or "")
                if isinstance(raw_copy, list) and i < len(raw_copy):
                    cb = str(raw_copy[i] or "")
                if isinstance(raw_extras, list) and i < len(raw_extras) and isinstance(raw_extras[i], dict):
                    ex = normalize_slot_extra(raw_extras[i])
                has_extra = bool(
                    ex.get("copy_buttons")
                    or ex.get("copy_media_ids")
                    or ex.get("copy_attachment_urls")
                    or ex.get("copy_checkout_stars_enabled")
                )
                if not ts and not str(fo or "").strip() and not str(cb or "").strip() and not has_extra:
                    continue
                nv.append(ts)
                footers_parallel.append(fo)
                copy_parallel.append(cb)
                extras_parallel.append(ex)
            if nv:
                row.message_template_variations = json.dumps(nv)
                row.message_template_rotation_index = None
                logger.info(
                    "listening relay saved %s template slots (%s footers, %s copy blocks)",
                    len(nv),
                    sum(1 for x in footers_parallel if str(x or "").strip()),
                    sum(1 for x in copy_parallel if str(x or "").strip()),
                )
                if footers_parallel and any(str(x or "").strip() for x in footers_parallel):
                    row.message_footer_variations = json.dumps(footers_parallel)
                    row.message_footer_html = None
                else:
                    row.message_footer_variations = None
                if copy_parallel and any(str(x or "").strip() for x in copy_parallel):
                    row.message_copy_block_variations = json.dumps(copy_parallel)
                else:
                    row.message_copy_block_variations = None
                row.message_slot_extras_json = (
                    json.dumps(extras_parallel) if len(extras_parallel) == len(nv) else None
                )
            else:
                row.message_template_variations = None
                row.message_template_rotation_index = None
                row.message_footer_variations = None
                row.message_copy_block_variations = None
                row.message_slot_extras_json = None

    data.pop("message_slot_extras", None)

    if "message_footer_html" in data:
        v = data.pop("message_footer_html")
        if isinstance(v, str) and v.strip():
            row.message_footer_html = v.strip()
            row.message_footer_variations = None
        elif v is None or (isinstance(v, str) and not v.strip()):
            row.message_footer_html = None

    data.pop("message_footer_variations", None)
    data.pop("message_copy_block_variations", None)

    if "message_template_html" in data:
        v = data["message_template_html"]
        row.message_template_html = (v.strip() or None) if isinstance(v, str) else v
    if "template_rotation_mode" in data and data["template_rotation_mode"]:
        mode = str(data["template_rotation_mode"]).strip().lower()
        if mode in ("sequential", "random"):
            row.template_rotation_mode = mode
    if "ascii_art_enabled" in data and data["ascii_art_enabled"] is not None:
        row.ascii_art_enabled = bool(data["ascii_art_enabled"])
    if "ascii_art_min_interval" in data and data["ascii_art_min_interval"] is not None:
        row.ascii_art_min_interval = int(data["ascii_art_min_interval"])
    if "ascii_art_max_interval" in data and data["ascii_art_max_interval"] is not None:
        row.ascii_art_max_interval = max(
            int(row.ascii_art_min_interval or 3),
            int(data["ascii_art_max_interval"]),
        )
    if "tryptych_enabled" in data and data["tryptych_enabled"] is not None:
        row.tryptych_enabled = bool(data["tryptych_enabled"])
    if "tryptych_on_ascii_beat" in data and data["tryptych_on_ascii_beat"] is not None:
        row.tryptych_on_ascii_beat = bool(data["tryptych_on_ascii_beat"])
    if "send_silent" in data and data["send_silent"] is not None:
        row.send_silent = bool(data["send_silent"])
    if "buffer_relay_enabled" in data and data["buffer_relay_enabled"] is not None:
        row.buffer_relay_enabled = bool(data["buffer_relay_enabled"])
    if "buffer_relay_min_interval_minutes" in data and data["buffer_relay_min_interval_minutes"] is not None:
        row.buffer_relay_min_interval_minutes = int(data["buffer_relay_min_interval_minutes"])
    if "buffer_relay_max_per_day_utc" in data and data["buffer_relay_max_per_day_utc"] is not None:
        row.buffer_relay_max_per_day_utc = int(data["buffer_relay_max_per_day_utc"])
    if "buffer_x_queue" in data:
        from app.api.scheduled_posts import _normalize_buffer_x_queue

        row.set_buffer_x_queue(_normalize_buffer_x_queue(data.get("buffer_x_queue")))
    if "goblin_mode_enabled" in data and data["goblin_mode_enabled"] is not None:
        row.goblin_mode_enabled = bool(data["goblin_mode_enabled"])
    if "goblin_spawn_chance" in data and data["goblin_spawn_chance"] is not None:
        row.goblin_spawn_chance = float(max(0.0, min(1.0, float(data["goblin_spawn_chance"]))))
    if "goblin_cooldown_minutes" in data and data["goblin_cooldown_minutes"] is not None:
        row.goblin_cooldown_minutes = int(data["goblin_cooldown_minutes"])
    if "goblin_announce_ttl_seconds" in data and data["goblin_announce_ttl_seconds"] is not None:
        row.goblin_announce_ttl_seconds = int(data["goblin_announce_ttl_seconds"])
    if "goblin_claims_cap" in data and data["goblin_claims_cap"] is not None:
        row.goblin_claims_cap = int(data["goblin_claims_cap"])
    if "goblin_max_per_day_utc" in data and data["goblin_max_per_day_utc"] is not None:
        row.goblin_max_per_day_utc = int(data["goblin_max_per_day_utc"])

    db.commit()
    db.refresh(row)
    out: dict[str, Any] = {"ok": True, "settings": _row_public(row)}
    if regen_secret:
        out["webhook_secret"] = row.webhook_secret
    return out


@router.get("/lastfm-preview")
def lastfm_preview(db: Session = Depends(get_db)):
    row = _ensure_row(db)
    user = (row.lastfm_username or "").strip()
    key = (row.lastfm_api_key or "").strip()
    if not user or not key:
        raise HTTPException(status_code=400, detail="Configure Last.fm username and API key first.")
    track = fetch_recent_track_lastfm_sync(username=user, api_key=key)
    if not track:
        return {
            "ok": False,
            "track": None,
            "formatted": None,
            "detail": "Last.fm returned no recent track or API error.",
        }
    outbound = build_relay_outbound(
        row,
        artist=track.get("artist") or "",
        title=track.get("title") or "",
        album=track.get("album"),
        url=track.get("url"),
        source="lastfm",
        source_label="Last.fm",
        consume=False,
    )
    return {
        "ok": True,
        "track": track,
        "formatted": outbound.main_html,
        "copy_followups": [f.to_json_dict() for f in outbound.copy_followups],
        "copy_followups_json": followups_to_json(outbound.copy_followups),
        "ascii_beat_preview": outbound.ascii_beat,
        "tryptych_preview": outbound.tryptych,
    }


class AsciiArtBody(BaseModel):
    name: str | None = Field(None, max_length=80)
    content: str = Field(..., min_length=1, max_length=4000)


@router.get("/ascii-art")
def list_ascii_art(db: Session = Depends(get_db)):
    row = _ensure_row(db)
    return {"entries": list_all_ascii_entries(row), "max_width": RELAY_ASCII_MAX_WIDTH, "max_lines": RELAY_ASCII_MAX_LINES}


@router.post("/ascii-art")
def upload_ascii_art(body: AsciiArtBody, db: Session = Depends(get_db)):
    row = _ensure_row(db)
    ok, err = validate_ascii_content(body.content)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    try:
        entry = add_user_ascii_entry(row, name=body.name or "Custom", content=body.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return {"ok": True, "entry": entry}


@router.delete("/ascii-art/{entry_id}")
def delete_ascii_art(entry_id: str, db: Session = Depends(get_db)):
    row = _ensure_row(db)
    if not remove_user_ascii_entry(row, entry_id):
        raise HTTPException(status_code=404, detail="Entry not found or built-in")
    db.commit()
    return {"ok": True}


class BufferTestPostBody(BaseModel):
    text: str | None = Field(None, max_length=2500)
    image_url: str | None = Field(None, max_length=2048)
    x_only: bool | None = Field(
        None,
        description="If true, queue only TBCC_BUFFER_CHANNEL_ID_PRIMARY (X). Default: env TBCC_BUFFER_X_ONLY.",
    )
    publish_now: bool | None = Field(
        None,
        description="If true, Buffer mode shareNow (immediate). Default: addToQueue.",
    )


@router.post("/buffer-test-post")
def buffer_test_post(body: BufferTestPostBody | None = None):
    """
    Queue one test post in Buffer (addToQueue) — verify API key + channel id without Last.fm.
    Check publish.buffer.com queue after a few seconds.
    """
    from app.services.buffer_graphql import (
        buffer_api_key,
        buffer_target_channel_ids,
        create_posts_multi_channel,
    )

    share_mode = "shareNow" if body and body.publish_now else "addToQueue"

    if not buffer_api_key():
        raise HTTPException(status_code=400, detail="TBCC_BUFFER_API_KEY is not set in .env")
    chans = buffer_target_channel_ids(x_primary_only=bool(body and body.x_only))
    if not chans:
        raise HTTPException(
            status_code=400,
            detail="No Buffer channel ids — set TBCC_BUFFER_CHANNEL_ID_PRIMARY (and disable TBCC_BUFFER_X_ONLY if needed).",
        )
    from datetime import datetime, timezone

    default_test = (
        f"🎧 TBCC Buffer test {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC — "
        "if you see this in your Buffer queue, API wiring works."
    )
    from app.services.buffer_x_caption import fit_plaintext_for_x, resolve_overflow_url, should_fit_for_x

    text = ((body.text if body and body.text else None) or default_test).strip()
    if should_fit_for_x():
        text = fit_plaintext_for_x(text, overflow_url=resolve_overflow_url() or None)
    img = (body.image_url if body else None) or None
    results = create_posts_multi_channel(text, image_url=img, channel_ids=chans, mode=share_mode)
    ok = []
    errs = []
    for cid, res in zip(chans, results):
        if res.get("error"):
            errs.append({"channel_id": cid, "error": res["error"]})
            continue
        cp = (res.get("data") or {}).get("createPost") if isinstance(res.get("data"), dict) else None
        if isinstance(cp, dict) and cp.get("message"):
            errs.append({"channel_id": cid, "message": cp["message"]})
        elif isinstance(cp, dict) and cp.get("post"):
            ok.append({"channel_id": cid, "post_id": (cp.get("post") or {}).get("id")})
        else:
            ok.append({"channel_id": cid, "raw": res})
    if not ok and errs:
        dup = any(
            "posted that one recently" in str(e.get("message") or e.get("error") or "").lower() for e in errs
        )
        detail: dict = {"buffer_errors": errs}
        if dup:
            detail["hint"] = (
                "Buffer rejected duplicate copy. Wait a few minutes or pass a unique `text` in the request body."
            )
        raise HTTPException(status_code=502, detail=detail)
    return {
        "ok": True,
        "mode": share_mode,
        "queued": ok,
        "errors": errs or None,
        "channel_count": len(chans),
    }


@router.post("/test-post")
def test_post(db: Session = Depends(get_db)):
    row = _ensure_row(db)
    if not relay_has_send_target(row):
        raise HTTPException(status_code=400, detail="Pick a Telegram channel or random AOF network first.")
    channel_id, thread_id = resolve_listening_relay_send_target(db, row)
    if not channel_id:
        raise HTTPException(status_code=400, detail="Could not resolve relay destination (check AOF channels in DB).")
    html_out = (
        "🎧 <b>Listening relay test</b>\n"
        "<i>If you see this, Telethon can post to this channel.</i>"
    )
    if relay_random_network_enabled(row):
        html_out += f"\n<i>Random lane → channel id {channel_id}</i>"
    outbound = RelayOutbound(
        main_html=html_out,
        copy_followups=[],
        source="test",
        source_label="Test",
        title="Listening relay test",
    )
    queue_listening_relay_post(
        db,
        trigger="test",
        channel_id=int(channel_id),
        message_thread_id=thread_id,
        random_lane=relay_random_network_enabled(row),
        outbound=outbound,
        send_silent=bool(row.send_silent),
    )
    db.commit()
    return {"ok": True, "queued": True, "channel_id": channel_id, "message_thread_id": thread_id}


webhook_router = APIRouter()


def _webhook_signature_for(source: str, title: str, url: str) -> str:
    raw = f"{source}|{url}|{title}"[:2000]
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


@webhook_router.post("/listening-relay/webhook/{secret}")
async def listening_relay_webhook(secret: str, request: Request, db: Session = Depends(get_db)):
    """IFTTT/Zapier: POST JSON or form (value1=title, value2=url, value3=source)."""
    row = _ensure_row(db)
    expected = (row.webhook_secret or "").strip()
    if not expected or secret != expected:
        raise HTTPException(status_code=404, detail="Not found")

    if not row.enabled or not relay_has_send_target(row):
        return {"ok": False, "ignored": True, "reason": "relay disabled or no channel"}

    channel_id, thread_id = resolve_listening_relay_send_target(db, row)
    if not channel_id:
        return {"ok": False, "ignored": True, "reason": "could not resolve relay destination"}

    title = ""
    url = ""
    source = "ifttt"
    artist = ""
    album: str | None = None

    ct = (request.headers.get("content-type") or "").lower()
    payload: dict[str, Any] | None = None
    try:
        if "application/json" in ct:
            raw = await request.json()
            payload = raw if isinstance(raw, dict) else None
    except Exception:
        payload = None

    if isinstance(payload, dict):
        title = str(payload.get("title") or payload.get("value1") or "").strip()
        url = str(payload.get("url") or payload.get("link") or payload.get("value2") or "").strip()
        source = str(payload.get("source") or payload.get("value3") or "ifttt").strip() or "ifttt"
        artist = str(payload.get("artist") or "").strip()
        a = payload.get("album")
        album = str(a).strip() if a else None
    else:
        try:
            form = await request.form()
            title = str(form.get("title") or form.get("value1") or "").strip()
            url = str(form.get("url") or form.get("value2") or "").strip()
            source = str(form.get("source") or form.get("value3") or "ifttt").strip() or "ifttt"
            artist = str(form.get("artist") or "").strip()
            alb = form.get("album")
            album = str(alb).strip() if alb else None
        except Exception:
            pass

    if not title and not url:
        raise HTTPException(status_code=400, detail="Need title or url in JSON/form body.")

    if not title and url:
        title = url

    src_label = {"youtube": "YouTube", "ifttt": "IFTTT", "webhook": "Webhook"}.get(source.lower(), source.title())
    sig = _webhook_signature_for(source, title, url)
    if row.last_webhook_signature == sig:
        return {"ok": True, "deduped": True}

    outbound = build_relay_outbound(
        row,
        artist=artist,
        title=title,
        album=album,
        url=url or None,
        source=source,
        source_label=src_label,
        consume=True,
        db=db,
    )
    row.last_webhook_signature = sig
    queue_listening_relay_post(
        db,
        trigger="webhook",
        channel_id=int(channel_id),
        message_thread_id=thread_id,
        random_lane=relay_random_network_enabled(row),
        outbound=outbound,
        send_silent=bool(row.send_silent),
        extra={"webhook_source": source},
    )
    db.commit()
    return {"ok": True, "queued": True}
