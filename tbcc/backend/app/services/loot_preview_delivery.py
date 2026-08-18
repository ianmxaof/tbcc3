"""Deliver a loot roll preview to Telegram via @aof_lootgod_bot (album + modifier zips)."""

from __future__ import annotations

import asyncio
import base64
import html
import io
import logging
import random
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy.orm import Session
from telegram import Bot, InputFile, InputMediaPhoto, InputMediaVideo
from telegram.error import TelegramError

from app.models.loot import LootModifier
from app.models.media import Media
from app.services.loot_inline_keyboards import build_loot_roll_inline_markup
from app.services.telegram_content_protection import bot_protect_content_kw
from app.services.loot_media_layout import plan_loot_roll_albums
from app.services.loot_free_tease import build_free_pull_tease_html
from app.services.loot_free_tutorial import build_step_intro_html
from app.services.loot_roll_presentation import (
    build_album_caption_html,
    build_preparing_html,
    build_roll_divider_html,
    format_modifier_caption_lines,
    pick_deal_failed_html,
    pick_still_working_line,
    wrap_tier_card_body,
)
from app.services.loot_tier_banner import build_tier_flavor_html, build_tier_opening_html
from app.services.loot_tier_card_assets import (
    _bytes_to_center_jpeg,
    build_reveal_border_still_jpeg,
    build_reveal_card_mp4,
    build_reveal_card_png,
    roll_reveal_rng,
)
from app.services.loot_tier_catalog import tier_display_name
from app.services.loot_media_deliverable import quarantine_stale_saved_message
from app.services.media_sniff import sniff_media_kind
from app.services.promo_affiliate_rotation import build_loot_roll_affiliate_footer_html
from app.services.telegram_admin import run_telegram_album_composer_io, run_telegram_import_io
from app.services.telegram_message_effects import FREE_EFFECT_PARTY, loot_roll_effect_id
from app.utils.telegram_promo_url import is_public_https_for_telegram

logger = logging.getLogger(__name__)


async def _encode_reveal_card_mp4(
    card_bytes: bytes,
    preview: dict[str, Any],
    *,
    center_jpeg: bytes | None = None,
) -> tuple[bytes | None, str]:
    """Thread or Celery offload for ffmpeg mux (falls back to JPEG path when None)."""
    from app.services.loot_reveal_video import (
        loot_reveal_video_celery_enabled,
        loot_reveal_video_enabled,
        reveal_video_encode_timeout_s,
    )
    from app.services.loot_border_reveal import loot_border_reveal_enabled

    if not loot_reveal_video_enabled():
        return None, "disabled"

    tier = int(preview.get("rarity_tier") or 1)
    rng = roll_reveal_rng(preview)
    video_preview = dict(preview)
    if center_jpeg:
        video_preview["center_jpeg_b64"] = base64.b64encode(center_jpeg).decode("ascii")

    if loot_border_reveal_enabled():
        # Border mux needs the rolled center bytes on the API host — skip Celery.
        return await asyncio.to_thread(
            build_reveal_card_mp4, tier, rng=rng, preview=video_preview
        )

    from app.services.loot_reveal_video import compose_reveal_card_mp4

    if loot_reveal_video_celery_enabled():
        timeout = reveal_video_encode_timeout_s() + 3

        def _celery_encode() -> tuple[bytes | None, str]:
            from app.workers.loot_reveal_video_worker import compose_reveal_card_mp4_task

            seed_int = None
            if preview.get("seed") is not None:
                try:
                    seed_int = int(preview.get("seed"))
                except (TypeError, ValueError):
                    seed_int = None
            result = compose_reveal_card_mp4_task.apply_async(
                args=[card_bytes],
                kwargs={"seed": seed_int},
            ).get(timeout=timeout)
            if result.get("ok") and result.get("mp4_b64"):
                return base64.b64decode(result["mp4_b64"]), str(result.get("note") or "celery")
            return None, str(result.get("reason") or "celery_fail")

        try:
            mp4, note = await asyncio.to_thread(_celery_encode)
            if mp4:
                return mp4, note
            logger.warning("loot reveal video celery empty: %s", note)
        except Exception as e:
            logger.warning("loot reveal video celery failed: %s", e)

    return await asyncio.to_thread(compose_reveal_card_mp4, card_bytes, rng=rng)


async def _send_reveal_with_effects(
    bot: Bot,
    *,
    chat_id: int,
    opening: str,
    effect_id: str | None,
    delivery: dict[str, Any],
    media_kind: str,
    media_bytes: bytes,
    filename: str,
) -> None:
    """send_animation or send_photo with Premium → free 🎉 → bare cascade."""
    effect_attempts: list[str | None] = []
    if effect_id:
        effect_attempts.append(effect_id)
    if effect_id != FREE_EFFECT_PARTY:
        effect_attempts.append(FREE_EFFECT_PARTY)
    effect_attempts.append(None)

    last_err: Exception | None = None
    sent = False
    for attempt_effect in effect_attempts:
        media_buf = io.BytesIO(media_bytes)
        send_kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "caption": opening[:1024],
            "parse_mode": "HTML",
        }
        if media_kind == "animation":
            send_kwargs["animation"] = InputFile(media_buf, filename=filename)
            send_fn = bot.send_animation
        elif media_kind == "video":
            send_kwargs["video"] = InputFile(media_buf, filename=filename)
            send_kwargs["supports_streaming"] = True
            send_fn = bot.send_video
        else:
            send_kwargs["photo"] = InputFile(media_buf, filename=filename)
            send_fn = bot.send_photo
        if attempt_effect:
            send_kwargs["message_effect_id"] = attempt_effect
        try:
            await send_fn(**send_kwargs)
            if attempt_effect:
                delivery["notes"].append(f"tier card effect:{attempt_effect}")
            elif effect_id:
                delivery["notes"].append("tier card effect skipped")
            sent = True
            break
        except TelegramError as effect_err:
            last_err = effect_err
            logger.info(
                "loot reveal send_%s failed effect=%s (%s); trying next",
                media_kind,
                attempt_effect,
                effect_err,
            )
            continue
    if not sent:
        raise last_err or RuntimeError(f"loot reveal send_{media_kind} failed")


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


def _try_local_or_cached_bytes(row: Media) -> tuple[bytes, str] | None:
    """On-disk pool file or dashboard thumb cache — no Telethon."""
    from app.services.local_media_storage import is_local_pool_media, read_local_media_bytes

    if is_local_pool_media(row) or str(getattr(row, "file_id", "") or "").startswith("local:"):
        data = read_local_media_bytes(row)
        if data:
            return _bytes_to_filename(data)
    try:
        from app.services.media_cache_storage import cached_thumb_path

        mid = int(getattr(row, "id", 0) or 0)
        if mid > 0:
            tp = cached_thumb_path(mid)
            if tp and tp.is_file():
                return _bytes_to_filename(tp.read_bytes())
    except Exception:
        pass
    return None


async def _download_saved_media_from_storage(
    storage,
    telegram_message_id: int,
) -> tuple[bytes, str]:
    raw = await storage.client.get_messages("me", ids=telegram_message_id)
    if isinstance(raw, list):
        msg = next((m for m in raw if m is not None), None)
    else:
        msg = raw
    if not msg or not getattr(msg, "media", None):
        raise ValueError(f"Saved message {telegram_message_id} not found or has no media")
    buf = io.BytesIO()
    await storage.client.download_media(msg, file=buf)
    data = buf.getvalue()
    if not data:
        raise ValueError(f"Empty download for saved message {telegram_message_id}")
    return _bytes_to_filename(data)


async def _download_saved_thumb_from_storage(
    storage,
    telegram_message_id: int,
) -> tuple[bytes, str] | None:
    raw = await storage.client.get_messages("me", ids=telegram_message_id)
    if isinstance(raw, list):
        msg = next((m for m in raw if m is not None), None)
    else:
        msg = raw
    if not msg or not getattr(msg, "media", None):
        return None
    buf = io.BytesIO()
    await storage.client.download_media(msg, file=buf, thumb=-1)
    data = buf.getvalue()
    if not data:
        return None
    return _bytes_to_filename(data)


async def _loot_telegram_io(fn):
    """
    Read loot media on the album-composer session, not the import session.

    Celery import workers hold a long-lived SQLite handle on admin_import.session, so paid
    roll delivery starves behind "database is locked". admin_album.session is a separate file
    and still serializes MTProto through the global account lock.
    """
    import os

    if (os.getenv("TBCC_LOOT_DELIVERY_SESSION") or "album").strip().lower() == "import":
        return await run_telegram_import_io(fn)
    try:
        return await run_telegram_album_composer_io(fn)
    except Exception as e:
        logger.warning("loot album-session io failed (%s); falling back to import session", e)
        return await run_telegram_import_io(fn)


def _loot_album_batch_timeout_s() -> float:
    import os

    raw = (os.getenv("TBCC_LOOT_ALBUM_BATCH_TIMEOUT_S") or "90").strip()
    try:
        return max(35.0, min(240.0, float(raw)))
    except ValueError:
        return 90.0


def _loot_album_item_timeout_s() -> float:
    import os

    raw = (os.getenv("TBCC_LOOT_ALBUM_ITEM_TIMEOUT_S") or "20").strip()
    try:
        return max(5.0, min(60.0, float(raw)))
    except ValueError:
        return 20.0


def _is_missing_saved_message(exc: BaseException) -> bool:
    """True only when Telegram confirmed the Saved Message is gone — not infra failure."""
    text = str(exc or "").lower()
    return "not found or has no media" in text or "empty download for saved message" in text


async def _download_many_saved_media_bytes(
    rows: list[Media],
) -> tuple[dict[int, tuple[bytes, str]], set[int]]:
    """
    One import-session lock for the whole album (avoids SQLite lock storms per item).

    Returns (bytes by media id, media ids Telegram confirmed missing). Partial results survive
    the batch deadline — a slow or dead item must not cost the rest of the album.
    """
    if not rows:
        return {}, set()

    collected: dict[int, tuple[bytes, str]] = {}
    missing: set[int] = set()
    budget = _loot_album_batch_timeout_s()
    per_item = _loot_album_item_timeout_s()

    async def _fn(storage) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget
        for row in rows:
            tg_id = int(getattr(row, "telegram_message_id", 0) or 0)
            if tg_id <= 0:
                continue
            remaining = deadline - loop.time()
            if remaining <= 3.0:
                logger.warning("loot album batch deadline hit; %s item(s) unattempted", len(rows) - len(collected))
                return
            mid = int(row.id)
            slot = min(per_item, remaining)
            try:
                collected[mid] = await asyncio.wait_for(
                    _download_saved_media_from_storage(storage, tg_id), timeout=slot
                )
                continue
            except Exception as primary:
                confirmed_missing = _is_missing_saved_message(primary)
                if not confirmed_missing and (row.media_type or "").lower() == "video":
                    try:
                        thumb = await asyncio.wait_for(
                            _download_saved_thumb_from_storage(storage, tg_id),
                            timeout=min(per_item, max(1.0, deadline - loop.time())),
                        )
                    except Exception:
                        thumb = None
                    if thumb:
                        collected[mid] = thumb
                        continue
                if confirmed_missing:
                    missing.add(mid)
                logger.warning(
                    "loot batch skip saved msg media_id=%s tg=%s missing=%s: %s",
                    mid,
                    tg_id,
                    confirmed_missing,
                    primary,
                )

    try:
        await asyncio.wait_for(_loot_telegram_io(_fn), timeout=budget + 45.0)
    except Exception as e:
        logger.warning("loot album batch telethon failed after %s item(s): %r", len(collected), e)
    return collected, missing


async def _download_saved_media_bytes(telegram_message_id: int) -> tuple[bytes, str]:
    """Single Saved Messages download — prefer _batch_load_media_bytes for albums."""

    async def _fn(storage) -> tuple[bytes, str]:
        return await _download_saved_media_from_storage(storage, telegram_message_id)

    return await asyncio.wait_for(_loot_telegram_io(_fn), timeout=35.0)


def _bytes_to_filename(data: bytes) -> tuple[bytes, str]:
    kind, ext = sniff_media_kind(data)
    mt = "video" if kind == "video" else "photo"
    name = f"loot.{ext if ext != 'bin' else ('mp4' if mt == 'video' else 'jpg')}"
    return data, name


def _media_send_bucket(data: bytes, row: Media) -> str:
    """Use sniffed bytes for Telegram send type (thumb JPEG fallback may differ from row.media_type)."""
    kind, _ = sniff_media_kind(data)
    if kind == "video":
        return "video"
    return "photo"


async def _download_saved_message_thumb_bytes(telegram_message_id: int) -> tuple[bytes, str] | None:
    async def _fn(storage) -> tuple[bytes, str] | None:
        return await _download_saved_thumb_from_storage(storage, telegram_message_id)

    return await _loot_telegram_io(_fn)


async def _batch_load_media_bytes(
    rows: list[Media],
    db: Session | None = None,
) -> tuple[list[tuple[Media, bytes, str]], list[str]]:
    """
    Load loot album bytes: local disk first, then one Telethon batch, then thumb cache.
    """
    notes: list[str] = []
    partial: dict[int, tuple[Media, bytes, str]] = {}
    need_telethon: list[Media] = []

    for row in rows:
        local = _try_local_or_cached_bytes(row)
        if local:
            partial[int(row.id)] = (row, local[0], local[1])
            continue
        tg_id = int(getattr(row, "telegram_message_id", 0) or 0)
        if tg_id > 0:
            need_telethon.append(row)
        else:
            notes.append(f"skip media {row.id}: no local file and no saved message id")

    if need_telethon:
        downloaded, missing = await _download_many_saved_media_bytes(need_telethon)
        for row in need_telethon:
            mid = int(row.id)
            hit = downloaded.get(mid)
            if hit:
                partial[mid] = (row, hit[0], hit[1])
                continue
            cached = _try_local_or_cached_bytes(row)
            if cached:
                partial[mid] = (row, cached[0], cached[1])
                notes.append(f"thumb cache media {mid}")
                continue
            if mid in missing:
                notes.append(f"skip media {mid}: saved message gone")
                if db is not None:
                    quarantine_stale_saved_message(db, row, reason="delivery_saved_message_gone")
            else:
                notes.append(f"skip media {mid}: load failed (infra)")

    ordered: list[tuple[Media, bytes, str]] = []
    for row in rows:
        hit = partial.get(int(row.id))
        if hit:
            ordered.append(hit)
    return ordered, notes


async def _load_media_bytes(row: Media, db: Session | None = None) -> tuple[bytes, str]:
    """Prefer on-disk pool files; fall back to Saved Messages via Telethon."""
    ordered, _notes = await _batch_load_media_bytes([row], db=db)
    if ordered:
        _, data, fname = ordered[0]
        return data, fname
    raise ValueError(f"media id={row.id} has no local file and no saved message id")


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
    album_caption: str | None = None,
    reply_markup=None,
) -> None:
    plans = plan_loot_roll_albums(payloads)
    count = len(payloads)
    first_cap = True
    cap_html = album_caption
    markup = reply_markup

    for plan_idx, plan in enumerate(plans):
        items = plan["items"]
        is_last_plan = plan_idx == len(plans) - 1
        media_group: list = []
        for idx, (row, data, fname) in enumerate(items):
            bio = io.BytesIO(data)
            bio.name = fname
            cap = None
            if first_cap and idx == 0:
                if cap_html:
                    cap = cap_html[:1024]
                else:
                    cap_base = html.escape(tier_display_name(int(preview.get("rarity_tier") or 1)))
                    cap = f"{cap_base} · {count} item(s)"
            bucket = _media_send_bucket(data, row)
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
        protect = bot_protect_content_kw()
        plan_markup = markup if is_last_plan else None
        if len(media_group) == 1:
            m0 = media_group[0]
            bio = m0.media
            if isinstance(m0, InputMediaVideo):
                await bot.send_video(
                    chat_id=chat_id,
                    video=bio,
                    caption=m0.caption,
                    parse_mode="HTML",
                    has_spoiler=bool(spoiler_default),
                    reply_markup=plan_markup,
                    **protect,
                )
            else:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=bio,
                    caption=m0.caption,
                    parse_mode="HTML",
                    has_spoiler=bool(spoiler_default),
                    reply_markup=plan_markup,
                    **protect,
                )
        else:
            await bot.send_media_group(
                chat_id=chat_id,
                media=media_group,
                **protect,
            )
            if plan_markup:
                await bot.send_message(
                    chat_id=chat_id,
                    text="🎲 Roll controls",
                    reply_markup=plan_markup,
                    **protect,
                )
        delivery["albums_sent"] = int(delivery.get("albums_sent") or 0) + 1
        delivery["media_sent"] = int(delivery.get("media_sent") or 0) + len(items)
        first_cap = False


async def send_loot_preview_to_chat(
    db: Session,
    *,
    bot: Bot,
    chat_id: int,
    preview: dict[str, Any],
    spoiler_default: bool = True,
    include_affiliate_footer: bool = True,
) -> dict[str, Any]:
    """
    Order: tier card reveal → divider → flavor → media (modifiers + affiliate in caption) → ZIPs last.
    """
    delivery: dict[str, Any] = {"albums_sent": 0, "media_sent": 0, "notes": [], "tier_card_delivered": False}

    if not preview.get("ok"):
        await bot.send_message(
            chat_id=chat_id,
            text=f"🎁 <b>Loot preview failed</b>\n{html.escape(str(preview.get('reason') or 'unknown'))}",
            parse_mode="HTML",
            reply_markup=build_loot_roll_inline_markup(),
        )
        return delivery

    try:
        return await _send_loot_preview_to_chat_inner(
            db,
            bot=bot,
            chat_id=chat_id,
            preview=preview,
            spoiler_default=spoiler_default,
            include_affiliate_footer=include_affiliate_footer,
            delivery=delivery,
        )
    except TelegramError as e:
        logger.warning("loot preview delivery telegram error chat=%s: %s", chat_id, e)
        delivery["notes"].append(f"telegram_error:{e}")
        if "chat not found" in str(e).lower():
            delivery["notes"].append("chat_not_found")
        return delivery
    finally:
        try:
            if int(delivery.get("media_sent") or 0) > 0 or int(delivery.get("albums_sent") or 0) > 0:
                from app.services.traffic_pulse import pulse_loot_roll

                pulse_loot_roll(
                    roll_kind=str(preview.get("roll_kind") or preview.get("kind") or "roll"),
                    tier=int(preview.get("rarity_tier") or 1),
                    media_sent=int(delivery.get("media_sent") or 0),
                    chat_id=int(chat_id),
                )
        except Exception:
            pass


async def _send_loot_preview_to_chat_inner(
    db: Session,
    *,
    bot: Bot,
    chat_id: int,
    preview: dict[str, Any],
    spoiler_default: bool,
    include_affiliate_footer: bool,
    delivery: dict[str, Any],
) -> dict[str, Any]:
    tier = int(preview.get("rarity_tier") or 1)
    from app.services.loot_border_reveal import loot_border_reveal_enabled

    border_mode = loot_border_reveal_enabled()
    center_jpeg: bytes | None = None
    media_preview = preview.get("media") or []
    for item in media_preview:
        mid = item.get("id")
        if mid is None:
            continue
        row = db.query(Media).filter(Media.id == int(mid)).first()
        if not row:
            continue
        try:
            data, _fname = await _load_media_bytes(row, db=db)
            kind, _ext = sniff_media_kind(data)
            if kind in ("photo", "gif", "video"):
                center_jpeg = _bytes_to_center_jpeg(data)
                break
        except Exception as e:
            logger.warning("reveal center from roll media skipped media_id=%s: %s", mid, e)
    if border_mode and not center_jpeg and media_preview:
        delivery["notes"].append("tier card center:roll_media_missing")

    card_bytes: bytes | None = None
    card_note = "skipped"
    if not border_mode:
        card_bytes, card_note = build_reveal_card_png(tier, preview=preview)

    if border_mode or card_bytes:
        try:
            opening = build_tier_opening_html(db, preview)
            effect_id = loot_roll_effect_id()
            mp4_bytes, mp4_note = await _encode_reveal_card_mp4(
                card_bytes or b"", preview, center_jpeg=center_jpeg
            )
            if mp4_bytes:
                border_video = border_mode
                await _send_reveal_with_effects(
                    bot,
                    chat_id=chat_id,
                    opening=opening,
                    effect_id=effect_id,
                    delivery=delivery,
                    media_kind="video" if border_video else "animation",
                    media_bytes=mp4_bytes,
                    filename=f"loot-tier-{tier}.mp4",
                )
                delivery["notes"].append(f"tier card video:{mp4_note}")
                delivery["tier_card_delivered"] = True
            elif border_mode:
                still_bytes, still_note = await asyncio.to_thread(
                    build_reveal_border_still_jpeg,
                    tier,
                    preview=preview,
                    center_jpeg=center_jpeg,
                )
                if still_bytes:
                    await _send_reveal_with_effects(
                        bot,
                        chat_id=chat_id,
                        opening=opening,
                        effect_id=effect_id,
                        delivery=delivery,
                        media_kind="photo",
                        media_bytes=still_bytes,
                        filename=f"loot-tier-{tier}.jpg",
                    )
                    delivery["notes"].append(f"tier card still:{still_note}")
                    delivery["tier_card_delivered"] = True
                else:
                    delivery["notes"].append(f"border reveal failed:{mp4_note};still:{still_note}")
                    await bot.send_message(
                        chat_id=chat_id,
                        text=opening,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    delivery["notes"].append("tier banner fallback")
            else:
                if mp4_note and mp4_note != "disabled":
                    delivery["notes"].append(f"tier card video skipped:{mp4_note}")
                await _send_reveal_with_effects(
                    bot,
                    chat_id=chat_id,
                    opening=opening,
                    effect_id=effect_id,
                    delivery=delivery,
                    media_kind="photo",
                    media_bytes=card_bytes,
                    filename=f"loot-tier-{tier}.jpg",
                )
                delivery["notes"].append(f"tier card image:{card_note}")
                delivery["tier_card_delivered"] = True
        except Exception as e:
            logger.warning("loot tier card image failed tier=%s: %s", tier, e)
            delivery["notes"].append(f"tier card image failed: {e}")
            opening = build_tier_opening_html(db, preview)
            await bot.send_message(
                chat_id=chat_id,
                text=opening,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            delivery["notes"].append("tier banner fallback")
    else:
        opening = build_tier_opening_html(db, preview)
        await bot.send_message(
            chat_id=chat_id,
            text=opening,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        delivery["notes"].append("tier banner")

    divider = build_roll_divider_html(preview)
    await bot.send_message(
        chat_id=chat_id,
        text=divider,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    delivery["notes"].append("roll divider")

    flavor = build_tier_flavor_html(preview)
    if flavor:
        await bot.send_message(
            chat_id=chat_id,
            text=f"<i>{flavor}</i>",
            parse_mode="HTML",
        )
        delivery["notes"].append("flavor")

    preparing_msg = None
    try:
        preparing_msg = await bot.send_message(
            chat_id=chat_id,
            text=build_preparing_html(preview),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        delivery["notes"].append("preparing")
    except Exception as e:
        logger.warning("loot preparing ping failed: %s", e)

    media_specs = preview.get("media") or []
    mod_specs = preview.get("modifiers") or []
    mod_ids = [int(m["id"]) for m in mod_specs if m.get("id") is not None]
    link_mod_lines = format_modifier_caption_lines(mod_specs)
    affiliate_footer = None
    if include_affiliate_footer:
        try:
            affiliate_footer = build_loot_roll_affiliate_footer_html(db, advance=True)
            if affiliate_footer:
                delivery["notes"].append("affiliate footer")
        except Exception as e:
            logger.warning("loot affiliate footer failed: %s", e)
            delivery["notes"].append(f"affiliate footer skip: {e}")
    album_caption = build_album_caption_html(
        preview,
        modifier_lines=link_mod_lines,
        item_count=len(media_specs),
        affiliate_footer_html=affiliate_footer,
    )
    roll_kb = build_loot_roll_inline_markup()

    if not media_specs:
        delivery["notes"].append("no media in roll")
        if link_mod_lines and int(preview.get("modifier_slot_count") or 0) > 0:
            await bot.send_message(
                chat_id=chat_id,
                text=album_caption,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=roll_kb,
            )
            delivery["notes"].append("modifiers-only caption")
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=pick_deal_failed_html(),
                parse_mode="HTML",
                reply_markup=roll_kb,
            )
            delivery["notes"].append("deal failed empty media")
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
        load_started = time.monotonic()
        still_pinged = False
        try:
            from telegram.constants import ChatAction

            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
        except Exception:
            pass
        if (
            preparing_msg is not None
            and (time.monotonic() - load_started) > 12.0
        ):
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=int(preparing_msg.message_id),
                    text=f"<i>{html.escape(pick_still_working_line())}</i>",
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                delivery["notes"].append("still working ping")
            except Exception:
                pass
        payloads, load_notes = await _batch_load_media_bytes(ordered, db=db)
        for note in load_notes:
            if note.startswith("skip media"):
                logger.warning("loot preview %s", note)
            delivery["notes"].append(note)

        if payloads:
            await _send_media_plan(
                bot,
                chat_id,
                payloads,
                preview=preview,
                spoiler_default=spoiler_default,
                delivery=delivery,
                album_caption=album_caption,
                reply_markup=roll_kb,
            )
        else:
            delivery["notes"].append("could not load any album bytes")
            await bot.send_message(
                chat_id=chat_id,
                text=pick_deal_failed_html(),
                parse_mode="HTML",
                reply_markup=roll_kb,
            )
            delivery["notes"].append("deal failed no bytes")

    if preparing_msg is not None and int(delivery.get("media_sent") or 0) > 0:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=int(preparing_msg.message_id))
        except Exception:
            pass

    delivery["modifier_link_notes"] = []
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
    delivery: dict[str, Any] = {"albums_sent": 0, "media_sent": 0, "notes": [f"roll_kind={preview.get('roll_kind') or 'free'}"]}

    if not preview.get("ok"):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"<b>Pull failed</b>\n{html.escape(str(preview.get('reason') or 'unknown'))}",
                parse_mode="HTML",
                reply_markup=build_loot_roll_inline_markup(),
            )
        except TelegramError as e:
            delivery["notes"].append(f"telegram_error:{e}")
        return delivery

    try:
        return await _send_loot_free_pull_to_chat_inner(
            db,
            bot=bot,
            chat_id=chat_id,
            preview=preview,
            spoiler_default=spoiler_default,
            payment_bot_username=payment_bot_username,
            free_pulls_remaining=free_pulls_remaining,
            delivery=delivery,
        )
    except TelegramError as e:
        logger.warning("loot free-pull delivery telegram error chat=%s: %s", chat_id, e)
        delivery["notes"].append(f"telegram_error:{e}")
        if "chat not found" in str(e).lower():
            delivery["notes"].append("chat_not_found")
        return delivery


async def _send_loot_free_pull_to_chat_inner(
    db: Session,
    *,
    bot: Bot,
    chat_id: int,
    preview: dict[str, Any],
    spoiler_default: bool,
    payment_bot_username: str | None,
    free_pulls_remaining: int,
    delivery: dict[str, Any],
) -> dict[str, Any]:
    divider = build_roll_divider_html(preview)
    await bot.send_message(
        chat_id=chat_id,
        text=divider,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    delivery["notes"].append("roll divider")

    intro = build_step_intro_html(preview)
    await bot.send_message(
        chat_id=chat_id,
        text=intro,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    delivery["notes"].append("lesson intro")

    opening = build_tier_opening_html(db, preview)
    await bot.send_message(
        chat_id=chat_id,
        text=f"<b>Your draw</b>\n\n{opening}\n\n<i>Tap the blurred card below to unwrap.</i>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    delivery["notes"].append("tier banner")

    flavor = build_tier_flavor_html(preview)
    if flavor:
        await bot.send_message(
            chat_id=chat_id,
            text=f"<i>{flavor}</i>",
            parse_mode="HTML",
        )

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=build_preparing_html(preview),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        delivery["notes"].append("preparing")
    except Exception as e:
        logger.warning("free pull preparing ping failed: %s", e)

    media_specs = preview.get("media") or []
    if not media_specs:
        delivery["notes"].append("no media")
        await bot.send_message(
            chat_id=chat_id,
            text=pick_deal_failed_html(),
            parse_mode="HTML",
            reply_markup=build_loot_roll_inline_markup(),
        )
    else:
        mid = int(media_specs[0]["id"])
        row = db.query(Media).filter(Media.id == mid).first()
        if row:
            try:
                data, fname = await _load_media_bytes(row, db=db)
                payloads = [(row, data, fname)]
                simple_cap = build_album_caption_html(
                    preview,
                    modifier_lines=[],
                    item_count=1,
                )
                await _send_media_plan(
                    bot,
                    chat_id,
                    payloads,
                    preview=preview,
                    spoiler_default=spoiler_default,
                    delivery=delivery,
                    album_caption=simple_cap,
                    reply_markup=None,
                )
            except Exception as e:
                logger.warning("free pull media skip id=%s: %s", mid, e)
                delivery["notes"].append(f"skip media: {e}")
                await bot.send_message(
                    chat_id=chat_id,
                    text=pick_deal_failed_html(),
                    parse_mode="HTML",
                    reply_markup=build_loot_roll_inline_markup(),
                )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=pick_deal_failed_html(),
                parse_mode="HTML",
                reply_markup=build_loot_roll_inline_markup(),
            )

    from app.services.loot_free_tease import (
        build_free_pull_tease_html,
        build_vip_daily_tease_html,
        crate_origin_key_markup,
    )

    tease_markup = None
    if preview.get("roll_kind") == "vip_daily":
        tease = build_vip_daily_tease_html(preview)
    else:
        tease = build_free_pull_tease_html(
            preview,
            free_pulls_remaining=int(free_pulls_remaining or 0),
            payment_bot_username=payment_bot_username,
        )
        tease_markup = crate_origin_key_markup(payment_bot_username=payment_bot_username)
    await bot.send_message(
        chat_id=chat_id,
        text=tease,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=tease_markup,
    )
    delivery["notes"].append("tease")
    return delivery
