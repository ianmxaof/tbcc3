"""Custom emoji presets + extract from Telegram messages + test send."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.channel import Channel
from app.models.custom_emoji_preset import CustomEmojiPreset
from app.models.emoji_factory_sketch import EmojiFactorySketchPage
from sqlalchemy import func
from app.schemas.common import orm_to_dict
from app.services.telegram_admin import get_telegram_client, import_lock
from app.services.telegram_custom_emoji import (
    build_tg_emoji_tag,
    custom_emoji_html_from_message,
    parse_telethon_html,
    telethon_message_kwargs,
    validate_telethon_html,
)
from app.services.telegram_custom_emoji_catalog import (
    fetch_custom_emoji_pack,
    list_installed_custom_emoji_packs,
)
from app.utils.telegram_peer import normalize_telethon_peer_identifier

router = APIRouter()


class PresetCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    html_fragment: str = Field(..., min_length=1)
    source_note: str | None = None


class PresetPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    html_fragment: str | None = Field(None, min_length=1)
    source_note: str | None = None


class ValidateBody(BaseModel):
    html: str = ""


class ExtractBody(BaseModel):
    """Peer: me, @username, -100…, or t.me/c/CHAT/MSG style link in peer_link."""
    peer: str | None = Field(None, description="Telethon peer: me, @channel, -100…")
    message_id: int | None = Field(None, ge=1)
    peer_link: str | None = Field(None, description="Optional t.me/c/123/456 private link")


class BuildTagBody(BaseModel):
    document_id: int = Field(..., ge=1)
    placeholder: str = Field("⭐", min_length=1, max_length=8)


class TestSendBody(BaseModel):
    html: str = Field(..., min_length=1)
    channel_id: int | None = Field(None, ge=1)
    telegram_user_id: int | None = Field(None, ge=1)
    send_silent: bool = False


class ImportMacroBody(BaseModel):
    """One-step: extract from Telegram message → library and/or sketchbook."""
    peer: str | None = Field(None, description="Telethon peer, default me")
    message_id: int = Field(..., ge=1)
    peer_link: str | None = None
    title: str | None = Field(None, max_length=256)
    save_preset: bool = True
    save_sketchbook: bool = True
    send_to_saved: bool = Field(
        False,
        description="Re-send extracted HTML to Saved Messages (preview round-trip)",
    )
    layout: str = Field("full", description="full | banner_only")


def _parse_peer_link(link: str) -> tuple[str, int]:
    """t.me/c/… (groups), t.me/username/123 (Saved Messages / public username), or bare msg id."""
    import re

    raw = (link or "").strip()
    if not raw:
        raise ValueError("Empty link")

    m = re.search(r"t\.me/c/(\d+)/(\d+)", raw, re.I)
    if m:
        internal = int(m.group(1))
        msg_id = int(m.group(2))
        peer = f"-100{internal}" if internal > 0 else str(internal)
        return peer, msg_id

    m = re.search(r"t\.me/([A-Za-z0-9_]{4,})/(\d+)", raw, re.I)
    if m:
        username = m.group(1)
        if username.lower() not in ("c", "joinchat", "addstickers", "addemoji", "share"):
            return f"@{username}", int(m.group(2))

    if raw.isdigit():
        return "me", int(raw)

    raise ValueError(
        "Could not parse link. Use t.me/c/CHAT/MSG, t.me/YourUsername/MSG, or peer=me + message id."
    )


@router.get("/presets")
def list_presets(db: Session = Depends(get_db)):
    rows = db.query(CustomEmojiPreset).order_by(CustomEmojiPreset.id.desc()).all()
    return [orm_to_dict(r) for r in rows]


@router.post("/presets")
def create_preset(body: PresetCreate, db: Session = Depends(get_db)):
    v = validate_telethon_html(body.html_fragment)
    if not v.get("ok"):
        raise HTTPException(status_code=400, detail=v.get("error") or "Invalid HTML")
    row = CustomEmojiPreset(
        title=body.title.strip(),
        html_fragment=body.html_fragment.strip(),
        source_note=(body.source_note or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    d = orm_to_dict(row)
    d["validation"] = v
    return d


@router.patch("/presets/{preset_id}")
def patch_preset(preset_id: int, body: PresetPatch, db: Session = Depends(get_db)):
    row = db.query(CustomEmojiPreset).filter(CustomEmojiPreset.id == preset_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Preset not found")
    data = body.model_dump(exclude_unset=True)
    if "html_fragment" in data and data["html_fragment"] is not None:
        v = validate_telethon_html(data["html_fragment"])
        if not v.get("ok"):
            raise HTTPException(status_code=400, detail=v.get("error") or "Invalid HTML")
    for k, val in data.items():
        if k == "title" and val is not None:
            setattr(row, k, str(val).strip())
        elif k == "html_fragment" and val is not None:
            setattr(row, k, str(val).strip())
        elif k == "source_note":
            setattr(row, k, (str(val).strip() or None) if val is not None else row.source_note)
    db.commit()
    db.refresh(row)
    return orm_to_dict(row)


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    row = db.query(CustomEmojiPreset).filter(CustomEmojiPreset.id == preset_id).first()
    if not row:
        return {"deleted": 0}
    db.delete(row)
    db.commit()
    return {"deleted": 1}


@router.post("/validate")
def validate_html(body: ValidateBody):
    return validate_telethon_html(body.html)


@router.post("/build-tag")
def build_tag(body: BuildTagBody):
    tag = build_tg_emoji_tag(body.document_id, body.placeholder)
    return {"tag": tag, "validation": validate_telethon_html(tag)}


@router.get("/installed-packs")
async def get_installed_custom_emoji_packs():
    """Custom emoji sticker sets installed on the poster Telethon account."""
    try:
        client = await get_telegram_client()
        async with import_lock():
            packs = await list_installed_custom_emoji_packs(client)
        return {"packs": packs, "count": len(packs)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Telegram list packs failed: {e}") from e


@router.get("/installed-packs/{short_name}/emojis")
async def get_installed_pack_emojis(short_name: str):
    """All emojis in one pack with document_id and ready-made <tg-emoji> tags."""
    try:
        client = await get_telegram_client()
        async with import_lock():
            pack = await fetch_custom_emoji_pack(client, short_name=short_name)
        return pack
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Telegram pack load failed: {e}") from e


@router.get("/saved-messages/recent")
async def list_saved_messages_recent(limit: int = Query(20, ge=1, le=50)):
    """List recent Saved Messages (peer me) so you can pick a message id without a link."""
    from telethon.tl.types import MessageEntityCustomEmoji

    try:
        client = await get_telegram_client()
        async with import_lock():
            messages = await client.get_messages("me", limit=limit)
        out = []
        for msg in messages or []:
            if msg is None:
                continue
            text = (getattr(msg, "message", None) or "").strip()
            if not text and not getattr(msg, "entities", None):
                continue
            ents = getattr(msg, "entities", None) or []
            has_custom = any(isinstance(e, MessageEntityCustomEmoji) for e in ents)
            preview = text.replace("\n", " ")[:140] if text else "(media / no text)"
            out.append(
                {
                    "message_id": int(msg.id),
                    "preview": preview,
                    "has_custom_emoji": has_custom,
                    "date": msg.date.isoformat() if getattr(msg, "date", None) else None,
                }
            )
        return {"peer": "me", "messages": out}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Telegram list failed: {e}") from e


def _html_from_message(msg, layout: str) -> tuple[str, str, str, int]:
    fragment = custom_emoji_html_from_message(msg.message, msg.entities, layout="banner_only")
    full_html = ""
    if msg.entities:
        from telethon.extensions import html as telethon_html

        try:
            full_html = telethon_html.unparse(msg.message, msg.entities)
        except Exception:
            full_html = msg.message or ""
    with_body = custom_emoji_html_from_message(msg.message, msg.entities, layout="unparse")
    if layout == "banner_only":
        chosen = fragment
    else:
        chosen = (full_html or with_body or fragment or (msg.message or "")).strip()
    count = sum(1 for e in (msg.entities or []) if e.__class__.__name__ == "MessageEntityCustomEmoji")
    return fragment, with_body, chosen, count


@router.post("/import-macro")
async def import_macro(body: ImportMacroBody, db: Session = Depends(get_db)):
    """
    Extract from a Telegram message and save to Emoji library and/or design sketchbook in one call.
    """
    peer = (body.peer or "me").strip()
    msg_id = body.message_id
    if body.peer_link:
        try:
            peer, msg_id = _parse_peer_link(body.peer_link)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        client = await get_telegram_client()
        async with import_lock():
            messages = await client.get_messages(peer, ids=msg_id)
        msg = messages[0] if isinstance(messages, list) and messages else messages
        if not msg or not getattr(msg, "message", None):
            raise HTTPException(status_code=404, detail="Message not found")
        fragment, with_body, chosen, count = _html_from_message(msg, body.layout)
        if not chosen.strip():
            raise HTTPException(status_code=400, detail="Message has no extractable text")
        title = (body.title or "").strip() or f"Saved #{msg_id}"[:256]
        v = validate_telethon_html(chosen)
        if not v.get("ok"):
            raise HTTPException(status_code=400, detail=v.get("error") or "Invalid HTML")

        preset_id: int | None = None
        sketch_page_id: int | None = None

        if body.save_preset:
            row = CustomEmojiPreset(
                title=title,
                html_fragment=chosen,
                source_note=f"import_macro:{peer}/{msg_id}",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            preset_id = row.id

        if body.save_sketchbook:
            mx = db.query(func.max(EmojiFactorySketchPage.sort_order)).scalar()
            sort_order = int(mx or 0) + 1
            page = EmojiFactorySketchPage(
                sort_order=sort_order,
                title=title,
                body=chosen[:32000],
            )
            db.add(page)
            db.commit()
            db.refresh(page)
            sketch_page_id = page.id

        sent_to: str | None = None
        if body.send_to_saved:
            mk = telethon_message_kwargs(chosen)
            if mk.get("message"):
                async with import_lock():
                    await client.send_message("me", **mk)
                sent_to = "me"

        return {
            "ok": True,
            "peer": peer,
            "message_id": msg_id,
            "html": chosen,
            "custom_emoji_html": fragment,
            "custom_emoji_html_with_body": with_body,
            "custom_emoji_count": count,
            "preset_id": preset_id,
            "sketch_page_id": sketch_page_id,
            "sent_to": sent_to,
            "validation": v,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Import macro failed: {e}") from e


@router.post("/extract-from-message")
async def extract_from_message(body: ExtractBody):
    peer = (body.peer or "").strip()
    msg_id = body.message_id
    if body.peer_link:
        try:
            peer, msg_id = _parse_peer_link(body.peer_link)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if not peer or not msg_id:
        raise HTTPException(status_code=400, detail="peer + message_id or peer_link required")
    try:
        client = await get_telegram_client()
        async with import_lock():
            messages = await client.get_messages(peer, ids=msg_id)
        msg = messages[0] if isinstance(messages, list) and messages else messages
        if not msg or not getattr(msg, "message", None):
            raise HTTPException(status_code=404, detail="Message not found")
        fragment, with_body, chosen, count = _html_from_message(msg, "full")
        full_html = chosen
        return {
            "peer": peer,
            "message_id": msg_id,
            "plain_text": msg.message,
            "custom_emoji_html": fragment,
            "custom_emoji_html_with_body": with_body,
            "full_message_html": full_html,
            "custom_emoji_count": count,
            "validation": validate_telethon_html(fragment) if fragment else {"ok": True, "custom_emoji_count": 0},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Telegram extract failed: {e}") from e


@router.post("/test-send")
async def test_send(body: TestSendBody, db: Session = Depends(get_db)):
    """Send HTML (with custom emoji) via the poster Telethon session."""
    target: str | int | None = None
    if body.channel_id:
        ch = db.query(Channel).filter(Channel.id == body.channel_id).first()
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")
        target = normalize_telethon_peer_identifier(ch.identifier)
    elif body.telegram_user_id:
        target = int(body.telegram_user_id)
    else:
        admin = int((os.getenv("ADMIN_TELEGRAM_ID") or "0").strip() or "0")
        if admin <= 0:
            raise HTTPException(status_code=400, detail="Set channel_id, telegram_user_id, or ADMIN_TELEGRAM_ID")
        target = admin

    mk = telethon_message_kwargs(body.html)
    if not mk.get("message"):
        raise HTTPException(status_code=400, detail="Empty message")

    silent_kw = {"silent": True} if body.send_silent else {}
    try:
        client = await get_telegram_client()
        async with import_lock():
            await client.send_message(target, **silent_kw, **mk)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Telegram send failed: {e}") from e

    return {
        "ok": True,
        "sent_to": str(target),
        "validation": validate_telethon_html(body.html),
        "custom_emoji_count": validate_telethon_html(body.html).get("custom_emoji_count", 0),
    }
