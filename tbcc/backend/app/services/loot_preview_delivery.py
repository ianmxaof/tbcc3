"""Deliver a loot roll preview to Telegram via @aof_lootgod_bot (album + modifier zips)."""

from __future__ import annotations

import html
import io
import logging
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy.orm import Session
from telegram import Bot, InputFile, InputMediaPhoto, InputMediaVideo
from telegram.error import TelegramError

from app.models.loot import LootModifier
from app.models.media import Media
from app.services.loot_media_layout import plan_media_send_groups
from app.services.loot_free_tease import build_free_pull_tease_html
from app.services.loot_tier_banner import build_tier_flavor_html, build_tier_opening_html
from app.services.loot_tier_catalog import tier_display_name
from app.services.media_sniff import sniff_media_kind
from app.services.telegram_admin import get_telegram_client, import_lock
from app.utils.telegram_promo_url import is_public_https_for_telegram

logger = logging.getLogger(__name__)


def _coerce_single_message(messages):
    if messages is None:
        return None
    if hasattr(messages, "media"):
        return messages
    if isinstance(messages, (list, tuple)):
        for m in messages:
            if m is not None:
                return m
    return None


async def _download_saved_media_bytes(telegram_message_id: int) -> tuple[bytes, str]:
    client = await get_telegram_client()
    async with import_lock():
        messages = await client.get_messages("me", ids=telegram_message_id)
        msg = _coerce_single_message(messages)
        if not msg or not msg.media:
            raise ValueError(f"Saved message {telegram_message_id} not found or has no media")
        buf = io.BytesIO()
        await client.download_media(msg, file=buf)
        data = buf.getvalue()
    if not data:
        raise ValueError(f"Empty download for saved message {telegram_message_id}")
    kind, ext = sniff_media_kind(data)
    mt = "video" if kind == "video" else "photo"
    name = f"loot.{ext if ext != 'bin' else ('mp4' if mt == 'video' else 'jpg')}"
    return data, name


def _modifier_zip_path(target_url: str | None) -> Path | None:
    if not target_url:
        return None
    raw = unquote(str(target_url).strip())
    marker = "/static/bundles/loot_modifiers/"
    if marker in raw:
        from app.services.bundle_storage import bundle_root

        fname = raw.split(marker, 1)[1].split("?")[0].strip()
        if fname:
            p = bundle_root() / "loot_modifiers" / Path(fname).name
            return p if p.is_file() else None
    try:
        from app.services.bundle_storage import bundle_root

        path = urlparse(raw).path
        if "/loot_modifiers/" in path:
            fname = path.split("/loot_modifiers/", 1)[1].split("/")[0]
            p = bundle_root() / "loot_modifiers" / fname
            return p if p.is_file() else None
    except Exception:
        pass
    return None


async def _send_modifier_zips_last(
    bot: Bot, chat_id: int, modifier_ids: list[int], db: Session
) -> list[str]:
    """ZIP packs only — sent after media so drops feel like bonuses, not the main event."""
    notes: list[str] = []
    if not modifier_ids:
        return notes
    rows = db.query(LootModifier).filter(LootModifier.id.in_(modifier_ids)).all()
    by_id = {int(r.id): r for r in rows}
    for mid in modifier_ids:
        m = by_id.get(int(mid))
        if not m or not m.active:
            continue
        if (m.kind or "").strip().lower() != "local_zip_pack":
            continue
        label = (m.label or m.kind or "bonus pack").strip()
        path = _modifier_zip_path(m.target_url)
        if path and path.is_file():
            try:
                data = path.read_bytes()
                await bot.send_document(
                    chat_id=chat_id,
                    document=InputFile(io.BytesIO(data), filename=path.name),
                    caption=f"📦 {html.escape(label)}",
                    parse_mode="HTML",
                    read_timeout=180,
                    write_timeout=180,
                    connect_timeout=30,
                )
                notes.append(f"sent zip: {label}")
            except TelegramError as e:
                logger.warning("loot preview zip send failed %s: %s", path.name, e)
                notes.append(f"zip failed: {label} ({e})")
        else:
            notes.append(f"zip missing on disk: {label}")
    return notes


async def _send_modifier_links(
    bot: Bot, chat_id: int, modifier_ids: list[int], db: Session
) -> list[str]:
    notes: list[str] = []
    rows = db.query(LootModifier).filter(LootModifier.id.in_(modifier_ids)).all()
    by_id = {int(r.id): r for r in rows}
    lines: list[str] = []
    for mid in modifier_ids:
        m = by_id.get(int(mid))
        if not m or not m.active:
            continue
        if (m.kind or "").strip().lower() == "local_zip_pack":
            continue
        label = html.escape((m.label or m.kind or "bonus").strip())
        url = (m.target_url or "").strip()
        if url and is_public_https_for_telegram(url):
            lines.append(f"• {label} — <a href=\"{html.escape(url, quote=True)}\">open</a>")
        elif url:
            lines.append(f"• {label}")
    if lines:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="<b>Bonus unlocks</b>\n" + "\n".join(lines),
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            notes.append("modifier links")
        except TelegramError as e:
            logger.warning("loot modifier links failed: %s", e)
    return notes


async def _send_media_plan(
    bot: Bot,
    chat_id: int,
    payloads: list[tuple[Media, bytes, str]],
    *,
    preview: dict[str, Any],
    spoiler_default: bool,
    delivery: dict[str, Any],
) -> None:
    plans = plan_media_send_groups(payloads)
    cap_base = html.escape(tier_display_name(int(preview.get("rarity_tier") or 1)))
    count = len(payloads)
    first_cap = True

    for plan in plans:
        bucket = plan["bucket"]
        items = plan["items"]
        for chunk_start in range(0, len(items), 10):
            chunk = items[chunk_start : chunk_start + 10]
            media_group: list = []
            for idx, (_row, data, fname) in enumerate(chunk):
                bio = io.BytesIO(data)
                bio.name = fname
                cap = None
                if first_cap and idx == 0:
                    cap = f"{cap_base} · {count} item(s)"
                if bucket == "video":
                    media_group.append(
                        InputMediaVideo(
                            media=bio,
                            caption=cap,
                            parse_mode="HTML",
                            has_spoiler=bool(spoiler_default),
                        )
                    )
                else:
                    media_group.append(
                        InputMediaPhoto(
                            media=bio,
                            caption=cap,
                            parse_mode="HTML",
                            has_spoiler=bool(spoiler_default),
                        )
                    )
            if not media_group:
                continue
            if len(media_group) == 1:
                m0 = media_group[0]
                bio = m0.media
                if bucket == "video":
                    await bot.send_video(
                        chat_id=chat_id,
                        video=bio,
                        caption=m0.caption,
                        parse_mode="HTML",
                        has_spoiler=bool(spoiler_default),
                    )
                else:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=bio,
                        caption=m0.caption,
                        parse_mode="HTML",
                        has_spoiler=bool(spoiler_default),
                    )
            else:
                await bot.send_media_group(chat_id=chat_id, media=media_group)
            delivery["albums_sent"] = int(delivery.get("albums_sent") or 0) + 1
            delivery["media_sent"] = int(delivery.get("media_sent") or 0) + len(chunk)
            first_cap = False


async def send_loot_preview_to_chat(
    db: Session,
    *,
    bot: Bot,
    chat_id: int,
    preview: dict[str, Any],
    spoiler_default: bool = True,
) -> dict[str, Any]:
    """
    Order: tier banner → flavor → media (planned layout) → link modifiers → ZIPs last.
    """
    delivery: dict[str, Any] = {"albums_sent": 0, "media_sent": 0, "notes": []}

    if not preview.get("ok"):
        await bot.send_message(
            chat_id=chat_id,
            text=f"🎁 <b>Loot preview failed</b>\n{html.escape(str(preview.get('reason') or 'unknown'))}",
            parse_mode="HTML",
        )
        return delivery

    opening = build_tier_opening_html(db, preview)
    await bot.send_message(chat_id=chat_id, text=opening, parse_mode="HTML", disable_web_page_preview=True)
    delivery["notes"].append("tier banner")

    flavor = build_tier_flavor_html(preview)
    if flavor:
        await bot.send_message(chat_id=chat_id, text=f"<i>{flavor}</i>", parse_mode="HTML")
        delivery["notes"].append("flavor")

    media_specs = preview.get("media") or []
    mod_ids = [int(m["id"]) for m in (preview.get("modifiers") or []) if m.get("id") is not None]

    if not media_specs:
        delivery["notes"].append("no media in roll")
    else:
        ids = [int(m["id"]) for m in media_specs if m.get("id") is not None]
        rows = db.query(Media).filter(Media.id.in_(ids)).all()
        by_id = {int(r.id): r for r in rows}
        ordered: list[Media] = []
        for mid in ids:
            row = by_id.get(mid)
            if row:
                ordered.append(row)

        payloads: list[tuple[Media, bytes, str]] = []
        for row in ordered:
            try:
                data, fname = await _download_saved_media_bytes(int(row.telegram_message_id))
                payloads.append((row, data, fname))
            except Exception as e:
                logger.warning("loot preview skip media id=%s: %s", row.id, e)
                delivery["notes"].append(f"skip media {row.id}: {e}")

        if payloads:
            await _send_media_plan(
                bot,
                chat_id,
                payloads,
                preview=preview,
                spoiler_default=spoiler_default,
                delivery=delivery,
            )
        else:
            delivery["notes"].append("could not load any album bytes from Saved Messages")

    delivery["modifier_link_notes"] = await _send_modifier_links(bot, chat_id, mod_ids, db)
    delivery["modifier_zip_notes"] = await _send_modifier_zips_last(bot, chat_id, mod_ids, db)
    return delivery


async def send_loot_free_pull_to_chat(
    db: Session,
    *,
    bot: Bot,
    chat_id: int,
    preview: dict[str, Any],
    spoiler_default: bool = True,
    payment_bot_username: str | None = None,
    free_pulls_remaining: int = 0,
) -> dict[str, Any]:
    """
    Free DM pull: card face → one spoiler item → locked-modifier tease (no real zips/links).
    """
    delivery: dict[str, Any] = {"albums_sent": 0, "media_sent": 0, "notes": ["roll_kind=free"]}

    if not preview.get("ok"):
        await bot.send_message(
            chat_id=chat_id,
            text=f"<b>Pull failed</b>\n{html.escape(str(preview.get('reason') or 'unknown'))}",
            parse_mode="HTML",
        )
        return delivery

    opening = build_tier_opening_html(db, preview)
    await bot.send_message(
        chat_id=chat_id,
        text=f"<i>Complimentary pull</i> — tier capped, one item.\n\n{opening}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    delivery["notes"].append("tier banner")

    flavor = build_tier_flavor_html(preview)
    if flavor:
        await bot.send_message(chat_id=chat_id, text=f"<i>{flavor}</i>", parse_mode="HTML")

    media_specs = preview.get("media") or []
    if not media_specs:
        delivery["notes"].append("no media")
    else:
        mid = int(media_specs[0]["id"])
        row = db.query(Media).filter(Media.id == mid).first()
        if row and row.telegram_message_id:
            try:
                data, fname = await _download_saved_media_bytes(int(row.telegram_message_id))
                payloads = [(row, data, fname)]
                await _send_media_plan(
                    bot,
                    chat_id,
                    payloads,
                    preview=preview,
                    spoiler_default=spoiler_default,
                    delivery=delivery,
                )
            except Exception as e:
                logger.warning("free pull media skip id=%s: %s", mid, e)
                delivery["notes"].append(f"skip media: {e}")

    tease = build_free_pull_tease_html(
        preview,
        free_pulls_remaining=free_pulls_remaining,
        payment_bot_username=payment_bot_username,
    )
    await bot.send_message(chat_id=chat_id, text=tease, parse_mode="HTML", disable_web_page_preview=True)
    delivery["notes"].append("tease")
    return delivery
