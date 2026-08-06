"""
TBCC Album Composer — lite extension replacement via Telegram DM (or admin in a group).

Send photos/videos to this bot, set caption + inline buttons + promo tail, shuffle order,
then post to a TBCC channel (or Saved Messages only).

Run: cd tbcc/backend && python -m bots.album_composer_bot

Env:
  TBCC_ALBUM_COMPOSER_BOT_TOKEN — BotFather token (required)
  ADMIN_TELEGRAM_ID — only this user may use the bot (required)
  TBCC_API_URL — default http://127.0.0.1:8000
  TBCC_ALBUM_COMPOSER_POOL_ID — content pool for imports (default 1)

Groups: with BotFather Group Privacy disabled (or the bot as group admin), the bot sees
all topic media. ADMIN_TELEGRAM_ID plus any TBCC_ALBUM_COMPOSER_EXTRA_ADMIN_IDS are
served; other senders are ignored silently (no denial replies). Sessions are chat-scoped:
all admin accounts in a group share one draft. Post as yourself — anonymous /
channel-as-sender posts are not recognized as admin, and media posted by OTHER BOTS is
invisible to this bot (Telegram platform rule). /rebundle groups loose media into albums
in any group where this bot is admin (admin Telethon session must also be a member).
Do not add this bot to @aofmainhub or other public channels — it is for DM + Storage Hub
groups only.
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import random
import re
import sys
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

_backend_root = Path(__file__).resolve().parent.parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from dotenv import load_dotenv

_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _env.exists():
    load_dotenv(_env, override=True)

import httpx
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

try:
    from telegram import BotCommandScopeChat
except ImportError:
    from telegram.constants import BotCommandScopeChat

from app.services.image_crop_pipeline import ImageCropSettings, crop_status_label, parse_crop_phrase
from bots.error_reporter import make_error_handler, report_bot_error

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

API_BASE = (os.getenv("TBCC_API_URL") or "http://127.0.0.1:8000").rstrip("/")
ALBUM_CHUNK = 10  # Telegram media-group cap
MAX_ALBUMS = 100  # max albums per "Make album(s)" batch
MAX_STAGED = ALBUM_CHUNK * MAX_ALBUMS
MEDIA_GROUP_DELAY = 1.2
_HTTP_TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=60.0, pool=10.0)
_EMOJI_PACK_POLL_TIMEOUT = httpx.Timeout(connect=15.0, read=45.0, write=120.0, pool=10.0)
_EMOJI_PACK_JOB_TIMEOUT_S = 900.0

SESSION_KEY = "album_composer"
AWAIT_KEY = "ac_await"
MEDIA_GROUP_KEY = "ac_media_groups"
SOLO_BATCH_KEY = "ac_solo_batch"
SOLO_BATCH_DELAY = 1.2
INTAKE_LOCK_KEY = "ac_intake_lock"


def _intake_lock(context) -> "asyncio.Lock":
    """Serialize concurrent media-batch flushes so exactly one panel ever exists."""
    lock = context.chat_data.get(INTAKE_LOCK_KEY)
    if not isinstance(lock, asyncio.Lock):
        lock = asyncio.Lock()
        context.chat_data[INTAKE_LOCK_KEY] = lock
    return lock


@dataclass
class StagedItem:
    file_id: str
    kind: str  # photo | video
    name: str
    message_id: int


@dataclass
class AlbumEntry:
    """One album in a 'Make album(s)' batch — items + its own remixable state."""

    items: list[StagedItem] = field(default_factory=list)
    caption: str = ""
    buttons: list[dict] = field(default_factory=list)
    promo_enabled: bool = True
    send_silent: bool = False
    crop: ImageCropSettings | None = None
    watermark_skip: bool = False
    watermark_enabled: bool | None = None
    watermark_text: str = ""
    watermark_text_secondary: str = ""
    watermark_text_tertiary: str = ""
    watermark_opacity: float | None = None
    watermark_color: str | None = None
    watermark_strip_previous: bool | None = None
    chat_id: int | None = None
    header_message_id: int | None = None
    menu_message_id: int | None = None
    media_message_ids: list[int] = field(default_factory=list)
    posted: bool = False


@dataclass
class ComposerSession:
    items: list[StagedItem] = field(default_factory=list)
    caption: str = ""
    buttons: list[dict] = field(default_factory=list)
    promo_enabled: bool = True
    send_silent: bool = False
    channel_id: int | None = None
    channel_name: str = ""
    thread_id: int | None = None
    panel_chat_id: int | None = None
    panel_message_id: int | None = None
    batch_anchor_max: int | None = None
    workshop_chat_id: int | None = None
    workshop_preview_ids: list[int] = field(default_factory=list)
    active_draft_id: str | None = None
    active_draft_name: str = ""
    crop: ImageCropSettings | None = None
    watermark_skip: bool = False
    watermark_enabled: bool | None = None
    watermark_text: str = ""
    watermark_text_secondary: str = ""
    watermark_text_tertiary: str = ""
    watermark_opacity: float | None = None
    watermark_color: str | None = None
    watermark_strip_previous: bool | None = None
    albums: list[AlbumEntry] = field(default_factory=list)
    active_album_idx: int | None = None
    erome_title: str = ""
    erome_tags: str = ""
    erome_network_key: str = ""


# Remixable state mirrored between the session and the active AlbumEntry.
_REMIX_FIELDS = (
    "caption",
    "promo_enabled",
    "send_silent",
    "crop",
    "watermark_skip",
    "watermark_enabled",
    "watermark_text",
    "watermark_text_secondary",
    "watermark_text_tertiary",
    "watermark_opacity",
    "watermark_color",
    "watermark_strip_previous",
)


def _copy_remix_state_to_entry(sess: ComposerSession, entry: AlbumEntry) -> None:
    entry.items = list(sess.items)
    entry.buttons = [dict(b) for b in sess.buttons]
    for f in _REMIX_FIELDS:
        setattr(entry, f, getattr(sess, f))


def _load_entry_into_session(sess: ComposerSession, entry: AlbumEntry) -> None:
    sess.items = list(entry.items)
    sess.buttons = [dict(b) for b in entry.buttons]
    for f in _REMIX_FIELDS:
        setattr(sess, f, getattr(entry, f))


def _in_album_batch(sess: ComposerSession) -> bool:
    return sess.active_album_idx is not None and bool(sess.albums)


def _crop_applies(sess: ComposerSession) -> bool:
    return sess.crop is not None and sess.crop.applies()


def _watermark_api_payload(sess: ComposerSession) -> dict | None:
    if sess.watermark_skip:
        return {"skip": True}
    payload: dict = {}
    if sess.watermark_enabled is not None:
        payload["enabled"] = bool(sess.watermark_enabled)
    if (sess.watermark_text or "").strip():
        payload["text"] = sess.watermark_text.strip()[:120]
    if (sess.watermark_text_secondary or "").strip():
        payload["text_secondary"] = sess.watermark_text_secondary.strip()[:120]
    if (sess.watermark_text_tertiary or "").strip():
        payload["text_tertiary"] = sess.watermark_text_tertiary.strip()[:120]
    if sess.watermark_opacity is not None:
        payload["opacity"] = max(0.15, min(1.0, float(sess.watermark_opacity)))
    if (sess.watermark_color or "").strip():
        payload["color"] = sess.watermark_color.strip()[:16]
    if sess.watermark_strip_previous is not None:
        payload["strip_previous"] = bool(sess.watermark_strip_previous)
    return payload or None


def _bytes_pipeline(sess: ComposerSession) -> bool:
    if _crop_applies(sess):
        return True
    if sess.watermark_skip or sess.watermark_enabled is False:
        return False
    return True


def _watermark_status_label(sess: ComposerSession) -> str:
    if sess.watermark_skip or sess.watermark_enabled is False:
        return "off"
    bits = []
    if (sess.watermark_text or "").strip():
        bits.append(sess.watermark_text.strip()[:40])
    elif sess.watermark_enabled is True:
        bits.append("on (global)")
    else:
        bits.append("global default")
    if sess.watermark_text_secondary.strip():
        bits.append(f"+2:{sess.watermark_text_secondary.strip()[:24]}")
    if sess.watermark_text_tertiary.strip():
        bits.append(f"+3:{sess.watermark_text_tertiary.strip()[:24]}")
    if sess.watermark_opacity is not None:
        bits.append(f"α{sess.watermark_opacity:.2f}")
    if (sess.watermark_color or "").strip():
        bits.append(sess.watermark_color.strip())
    return " · ".join(bits)


def _apply_crop_phrase(sess: ComposerSession, phrase: str) -> str:
    parsed = parse_crop_phrase(phrase)
    if parsed == "off":
        sess.crop = None
        return "Crop/watermark edits turned off."
    sess.crop = parsed
    return f"Crop set: {crop_status_label(sess.crop)} (photos only on send)."


def _crop_api_payload(sess: ComposerSession) -> dict | None:
    if not _crop_applies(sess):
        return None
    return sess.crop.model_dump()


def _files_api_payload(sess: ComposerSession) -> list[dict]:
    return [{"file_id": it.file_id, "kind": it.kind} for it in sess.items if it.file_id]


def _capture_forum_topic(sess: ComposerSession, message) -> None:
    tid = getattr(message, "message_thread_id", None)
    if tid:
        sess.thread_id = int(tid)


def _is_erome_lane(sess: ComposerSession) -> bool:
    try:
        from app.services.erome_telegram_ingest import erome_storage_topic_id

        tid = erome_storage_topic_id()
        return bool(tid and sess.thread_id and int(sess.thread_id) == int(tid))
    except Exception:
        return False


def _erome_tags_list(sess: ComposerSession) -> list[str]:
    raw = (sess.erome_tags or "").strip()
    if not raw:
        return []
    return [t.strip() for t in raw.replace(";", ",").split(",") if t.strip()]


def _erome_title_for_upload(sess: ComposerSession) -> str | None:
    title = (sess.erome_title or "").strip()
    if title:
        return title[:120]
    cap = (sess.caption or "").strip()
    if cap:
        return cap.split("\n", 1)[0].strip()[:120] or None
    return None


def _erome_meta_summary(sess: ComposerSession) -> str:
    title = _erome_title_for_upload(sess) or "(not set)"
    tags = ", ".join(_erome_tags_list(sess)) or "(none)"
    return f"Title: {html.escape(title[:80])}\nTags: {html.escape(tags[:120])}"


def _erome_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📝 Title", callback_data="ac:erome:title"),
                InlineKeyboardButton("🏷 Tags", callback_data="ac:erome:tags"),
            ],
            [
                InlineKeyboardButton("✨ Suggest from winners", callback_data="ac:erome:suggest"),
            ],
            [
                InlineKeyboardButton("✂️ Crop & blur", callback_data="ac:cropmenu"),
                InlineKeyboardButton("🏷 Watermark", callback_data="ac:wmmenu"),
            ],
            [InlineKeyboardButton("👁 Preview", callback_data="ac:preview")],
            [InlineKeyboardButton("📤 Upload to Erome", callback_data="ac:erome:upload")],
            [InlineKeyboardButton("« Workshop menu", callback_data="ac:panel")],
        ]
    )


def _erome_workshop_row(sess: ComposerSession) -> list[InlineKeyboardButton] | None:
    if not sess.items:
        return None
    if _is_erome_lane(sess):
        return [InlineKeyboardButton("📤 Erome upload menu", callback_data="ac:eromemenu")]
    try:
        from app.services.erome_telegram_ingest import erome_storage_topic_id

        if erome_storage_topic_id():
            return [InlineKeyboardButton("🔗 Use Erome lane", callback_data="ac:erome:lane")]
    except Exception:
        pass
    return None


def _admin_id() -> int | None:
    raw = (os.getenv("ADMIN_TELEGRAM_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _admin_ids() -> set[int]:
    """Hardcoded TBCC operators + ADMIN_TELEGRAM_ID + TBCC_ALBUM_COMPOSER_EXTRA_ADMIN_IDS."""
    from app.services.tbcc_operator_ids import tbcc_operator_ids

    ids: set[int] = set(tbcc_operator_ids())
    main = _admin_id()
    if main is not None:
        ids.add(main)
    raw = (os.getenv("TBCC_ALBUM_COMPOSER_EXTRA_ADMIN_IDS") or "").strip()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            try:
                ids.add(int(part))
            except ValueError:
                pass
    return ids


def _pool_id() -> int:
    raw = (os.getenv("TBCC_ALBUM_COMPOSER_POOL_ID") or "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _token() -> str:
    return (os.getenv("TBCC_ALBUM_COMPOSER_BOT_TOKEN") or "").strip()


def _session(context: ContextTypes.DEFAULT_TYPE) -> ComposerSession:
    """Session is chat-scoped: one shared draft per group (all admin accounts), one per DM."""
    raw = context.chat_data.get(SESSION_KEY)
    if isinstance(raw, ComposerSession):
        return raw
    sess = ComposerSession()
    context.chat_data[SESSION_KEY] = sess
    return sess


def _actor_user_id(update: Update) -> int | None:
    """Telegram user id for authorization (DM, group member, not channel-as-sender)."""
    user = update.effective_user
    if user and user.id:
        return int(user.id)
    msg = update.effective_message
    if msg and msg.from_user and msg.from_user.id:
        return int(msg.from_user.id)
    return None


def _is_non_private_chat(update: Update) -> bool:
    """Groups, supergroups, and channels — never spam denial replies outside DM."""
    chat = update.effective_chat
    if not chat:
        return False
    return chat.type in ("group", "supergroup", "channel")


def _authorized(user_id: int | None) -> bool:
    ids = _admin_ids()
    return bool(ids) and user_id in ids


async def _deny_unauthorized(update: Update) -> bool:
    if _authorized(_actor_user_id(update)):
        return False
    # Outside DM the bot may see channel posts or every group message (privacy off).
    # Never reply with denial text there — it spams storage topics and @aofmainhub.
    if _is_non_private_chat(update):
        return True
    msg = update.effective_message
    if msg:
        await msg.reply_text(
            "This bot is restricted to the TBCC admin. Set ADMIN_TELEGRAM_ID in tbcc/.env "
            "to your Telegram user id."
        )
    return True


def _kind_counts(items: list[StagedItem]) -> tuple[int, int]:
    photos = sum(1 for i in items if i.kind == "photo")
    videos = sum(1 for i in items if i.kind == "video")
    return photos, videos


def _status_text(sess: ComposerSession, items: list[StagedItem] | None = None) -> str:
    display = items if items is not None else sess.items
    n = len(display)
    photos, videos = _kind_counts(display)
    cap_preview = (sess.caption or "").strip()
    if len(cap_preview) > 120:
        cap_preview = cap_preview[:117] + "…"
    cap_line = html.escape(cap_preview) if cap_preview else "<i>(empty)</i>"
    btn_n = len(sess.buttons)
    promo = "✅ on" if sess.promo_enabled else "off"
    silent = " · silent" if sess.send_silent else ""
    ch_line = ""
    if sess.channel_id:
        ch_name = html.escape((sess.channel_name or "").strip() or f"#{sess.channel_id}")
        ch_line = f"\nDestination: <b>{ch_name}</b>"
        if sess.thread_id:
            ch_line += f" · topic {sess.thread_id}"
    if sess.active_draft_name:
        ch_line += f"\nSaved draft: <i>{html.escape(sess.active_draft_name[:60])}</i>"
    erome_line = ""
    if _is_erome_lane(sess):
        erome_line = "\n<b>Erome lane</b> — crop/watermark, then 📤 Erome upload menu"
    crop_line = f"Crop: {crop_status_label(sess.crop)}" if _crop_applies(sess) else "Crop: off"
    wm_line = f"Promo watermark: {_watermark_status_label(sess)}"
    if sess.promo_enabled:
        if n >= ALBUM_CHUNK:
            promo += f" ⚠️ album full — send splits it {ALBUM_CHUNK - 1}+2 to fit the promo tile"
        else:
            promo += " · rides as last tile"
    return (
        f"<b>Album draft</b> — {n}/{MAX_STAGED} ({photos}📷 {videos}🎬)\n"
        f"Caption: {cap_line}\n"
        f"{crop_line}\n"
        f"{wm_line}\n"
        f"Promo tail: {promo}{silent}\n"
        f"Buttons: {btn_n}{ch_line}{erome_line}"
    )


def _batch_chunk_size(sess: ComposerSession) -> int:
    """Items per album when batching; reserve the last slot for the promo tile if enabled."""
    return ALBUM_CHUNK - 1 if sess.promo_enabled else ALBUM_CHUNK


def _entry_status_text(sess: ComposerSession, entry: AlbumEntry, idx: int, total: int) -> str:
    """'Album draft' header text attached above one album of a batch."""
    tmp = ComposerSession()
    _load_entry_into_session(tmp, entry)
    tmp.channel_id = sess.channel_id
    tmp.channel_name = sess.channel_name
    tmp.thread_id = sess.thread_id
    body = _status_text(tmp, entry.items)
    body = body.split("\n", 1)[1] if "\n" in body else ""
    photos, videos = _kind_counts(entry.items)
    flag = "✅ <b>Posted</b> · " if entry.posted else ""
    head = f"{flag}📦 <b>Album draft {idx + 1}/{total}</b> — {len(entry.items)} items ({photos}📷 {videos}🎬)"
    return f"{head}\n{body}"


def _selection_panel_text(sess: ComposerSession) -> str:
    """Text on the full-menu message under the currently selected album."""
    if not _in_album_batch(sess):
        return _status_text(sess)
    idx, total = sess.active_album_idx, len(sess.albums)
    flag = "✅ posted · " if sess.albums[idx].posted else ""
    n = len(sess.items)
    return (
        f"🎛 <b>Current selection — Album {idx + 1}/{total}</b> "
        f"({flag}{n}/{ALBUM_CHUNK} items)\n"
        "This menu controls the album above it. Tap “Open main menu” under any other album to switch."
    )


def _album_menu_min_kb(idx: int, posted: bool) -> InlineKeyboardMarkup:
    label = "✅ Posted · open main menu" if posted else "▶️ Open main menu"
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"ac:alb:{idx}")]])


def _panel_is_album_menu(sess: ComposerSession) -> bool:
    if not _in_album_batch(sess):
        return False
    entry = sess.albums[sess.active_album_idx]
    return bool(sess.panel_message_id) and sess.panel_message_id == entry.menu_message_id


def _post_button_markup(buttons: list[dict]) -> InlineKeyboardMarkup | None:
    """URL inline keyboard matching channel post buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    for btn in buttons[:10]:
        if not isinstance(btn, dict):
            continue
        text = str(btn.get("text", "")).strip()
        url = str(btn.get("url", "")).strip()
        if text and url.startswith(("http://", "https://", "tg://")):
            rows.append([InlineKeyboardButton(text=text[:64], url=url[:512])])
    return InlineKeyboardMarkup(rows) if rows else None


def _album_buttons_limit_note(sess: ComposerSession) -> str:
    """Upfront warning shown BEFORE the user builds buttons for a multi-media album."""
    if len(sess.items) <= 1:
        return ""
    return (
        "\n\nℹ️ <b>Telegram limitation:</b> buttons cannot attach directly to a multi-media album "
        f"(this draft has {len(sess.items)} items). On channel send, buttons attach to the album's "
        "first chunk message; in preview they appear on a separate message under the album."
    )


def _buttons_menu_keyboard(sess: ComposerSession) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if sess.items:
        rows.append([InlineKeyboardButton("👁 Preview post", callback_data="ac:preview")])
    rows.append([InlineKeyboardButton("Clear buttons", callback_data="ac:clrbtn")])
    rows.append([InlineKeyboardButton("« Workshop menu", callback_data="ac:panel")])
    return InlineKeyboardMarkup(rows)


def _back_keyboard(sess: ComposerSession | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if sess and sess.items:
        rows.append([InlineKeyboardButton("👁 Preview post", callback_data="ac:preview")])
    rows.append([InlineKeyboardButton("« Workshop menu", callback_data="ac:panel")])
    return InlineKeyboardMarkup(rows)


async def _clear_workshop_preview(context: ContextTypes.DEFAULT_TYPE, chat_id: int, sess: ComposerSession) -> None:
    if not sess.workshop_preview_ids:
        return
    bot = context.bot
    for mid in sess.workshop_preview_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
    sess.workshop_preview_ids.clear()


async def _show_staged_media(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    sess: ComposerSession,
    *,
    caption: str | None = None,
    markup: InlineKeyboardMarkup | None = None,
) -> list[int]:
    """Re-display staged media in chat (workshop preview). Returns new message ids."""
    items = sess.items[:10]
    if not items:
        return []
    cap = caption if caption is not None else ((sess.caption or "").strip() or None)
    bot = context.bot
    sent_ids: list[int] = []
    last_err: Exception | None = None
    try:
        if len(items) == 1:
            it = items[0]
            cap_kw: dict = {}
            if cap:
                cap_kw["caption"] = cap
                cap_kw["parse_mode"] = ParseMode.HTML
            if markup:
                cap_kw["reply_markup"] = markup
            if it.message_id:
                msg = await bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=chat_id,
                    message_id=it.message_id,
                    **cap_kw,
                )
                sent_ids.append(msg.message_id)
            else:
                msg = await _send_staged_media_fallback(bot, chat_id, it, caption=cap, markup=markup)
                if msg is not None:
                    sent_ids.append(msg.message_id)
        else:
            # send_media_group renders a true album in the session's current order
            # (copy_messages requires strictly increasing ids, which breaks after shuffle).
            media = []
            for i, it in enumerate(items):
                item_cap = cap if i == 0 else None
                cls = InputMediaVideo if it.kind == "video" else InputMediaPhoto
                media.append(
                    cls(media=it.file_id, caption=item_cap, parse_mode=ParseMode.HTML if item_cap else None)
                )
            msgs = await bot.send_media_group(chat_id=chat_id, media=media)
            sent_ids.extend(m.message_id for m in msgs)
            if markup and sess.buttons:
                note = await bot.send_message(
                    chat_id,
                    "🔘 <b>Buttons</b> — Telegram can't attach buttons inside a multi-media album, "
                    "so in preview they ride on this message. On channel send they attach to the "
                    "first chunk's message.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
                sent_ids.append(note.message_id)
    except Exception as e:
        last_err = e
        logger.warning("workshop preview failed: %s", e)
    if items and not sent_ids:
        raise RuntimeError(f"could not display staged media ({last_err or 'no message could be sent'})")
    return sent_ids


async def _refresh_workshop(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    sess: ComposerSession,
    *,
    force_new_panel: bool = False,
) -> None:
    """Refresh live preview + options panel after an edit."""
    if _in_album_batch(sess):
        # Albums are already on screen; just refresh the header + selection menu.
        await _sync_panel(context, chat_id, sess)
        return
    if sess.items:
        await _preview_post(context, chat_id, sess, track_workshop=True)
    await _sync_panel(context, chat_id, sess, force_new=force_new_panel, pin_bottom=force_new_panel)


def _session_draft_payload(sess: ComposerSession, name: str | None = None) -> dict:
    crop_payload = sess.crop.model_dump() if sess.crop is not None else None
    return {
        "id": sess.active_draft_id,
        "name": (name or sess.active_draft_name or f"Album {len(sess.items)} items").strip()[:80],
        "items": [{"file_id": it.file_id, "kind": it.kind, "name": it.name} for it in sess.items],
        "caption": sess.caption or "",
        "buttons": list(sess.buttons),
        "promo_enabled": sess.promo_enabled,
        "send_silent": sess.send_silent,
        "channel_id": sess.channel_id,
        "thread_id": sess.thread_id,
        "crop": crop_payload,
        "watermark_skip": sess.watermark_skip,
        "watermark_enabled": sess.watermark_enabled,
        "watermark_text": sess.watermark_text,
        "watermark_text_secondary": sess.watermark_text_secondary,
        "watermark_text_tertiary": sess.watermark_text_tertiary,
        "watermark_opacity": sess.watermark_opacity,
        "watermark_color": sess.watermark_color,
        "watermark_strip_previous": sess.watermark_strip_previous,
    }


async def _save_session_draft_api(sess: ComposerSession, name: str | None = None) -> tuple[bool, str, dict | None]:
    if not sess.items:
        return False, "No media to save. Send photos/videos first.", None
    payload = _session_draft_payload(sess, name=name)
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            if sess.active_draft_id:
                r = await client.patch(
                    f"{API_BASE}/album-composer/drafts/{sess.active_draft_id}",
                    json=payload,
                )
            else:
                r = await client.post(f"{API_BASE}/album-composer/drafts", json=payload)
        if r.status_code >= 400:
            return False, f"Save failed: {r.text[:200]}", None
        data = r.json()
        row = data.get("draft") if isinstance(data, dict) else None
        if row:
            sess.active_draft_id = str(row.get("id") or "") or None
            sess.active_draft_name = str(row.get("name") or payload["name"])
        return True, f"Draft saved: <b>{html.escape(sess.active_draft_name)}</b>", row
    except httpx.HTTPError as e:
        return False, f"Could not reach TBCC API: {e}", None


async def _fetch_drafts_api() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(f"{API_BASE}/album-composer/drafts")
        if r.status_code != 200:
            return []
        data = r.json()
        drafts = data.get("drafts") if isinstance(data, dict) else []
        return drafts if isinstance(drafts, list) else []
    except httpx.HTTPError:
        return []


def _drafts_keyboard(drafts: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i, d in enumerate(drafts[:10]):
        if not isinstance(d, dict):
            continue
        label = str(d.get("name") or f"Draft {i + 1}")[:36]
        n_items = len(d.get("items") or [])
        rows.append(
            [InlineKeyboardButton(f"📂 {label} ({n_items})", callback_data=f"ac:loaddraft:{i}")]
        )
    if not rows:
        rows.append([InlineKeyboardButton("(no saved drafts yet)", callback_data="ac:panel")])
    rows.append([InlineKeyboardButton("« Workshop menu", callback_data="ac:panel")])
    _insert_cache["drafts"] = drafts[:10]
    return InlineKeyboardMarkup(rows)


async def _load_draft_into_session(sess: ComposerSession, draft: dict) -> None:
    sess.items.clear()
    for raw in draft.get("items") or []:
        if not isinstance(raw, dict):
            continue
        fid = str(raw.get("file_id") or "").strip()
        if not fid:
            continue
        kind = str(raw.get("kind") or "photo").lower()
        if kind not in ("photo", "video"):
            kind = "photo"
        sess.items.append(StagedItem(file_id=fid, kind=kind, name=str(raw.get("name") or ""), message_id=0))
    sess.caption = str(draft.get("caption") or "")
    sess.buttons = [b for b in (draft.get("buttons") or []) if isinstance(b, dict)]
    sess.promo_enabled = bool(draft.get("promo_enabled", True))
    sess.send_silent = bool(draft.get("send_silent", False))
    sess.channel_id = int(draft["channel_id"]) if draft.get("channel_id") is not None else None
    sess.thread_id = int(draft["thread_id"]) if draft.get("thread_id") is not None else None
    sess.active_draft_id = str(draft.get("id") or "") or None
    sess.active_draft_name = str(draft.get("name") or "")
    sess.watermark_skip = bool(draft.get("watermark_skip", False))
    sess.watermark_enabled = draft.get("watermark_enabled")
    sess.watermark_text = str(draft.get("watermark_text") or "")
    sess.watermark_text_secondary = str(draft.get("watermark_text_secondary") or "")
    sess.watermark_text_tertiary = str(draft.get("watermark_text_tertiary") or "")
    sess.watermark_opacity = draft.get("watermark_opacity")
    sess.watermark_color = draft.get("watermark_color")
    sess.watermark_strip_previous = draft.get("watermark_strip_previous")
    crop_raw = draft.get("crop")
    if crop_raw and isinstance(crop_raw, dict):
        try:
            sess.crop = ImageCropSettings.model_validate(crop_raw)
        except Exception:
            sess.crop = None
    else:
        sess.crop = None
    sess.batch_anchor_max = None
    # Loading a draft replaces the working set — leave any open album batch.
    sess.albums = []
    sess.active_album_idx = None


async def _send_staged_media_fallback(
    bot,
    chat_id: int,
    it: StagedItem,
    *,
    caption: str | None,
    markup: InlineKeyboardMarkup | None,
):
    """Resend by file_id when copy_message is unavailable (e.g. source message deleted)."""
    kw: dict = {"reply_markup": markup}
    if caption:
        kw["caption"] = caption
        kw["parse_mode"] = ParseMode.HTML
    if it.kind == "video":
        return await bot.send_video(chat_id, it.file_id, **kw)
    return await bot.send_photo(chat_id, it.file_id, **kw)


async def _preview_post(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    sess: ComposerSession,
    *,
    track_workshop: bool = True,
) -> tuple[bool, str]:
    """Unified preview: media + caption + optional URL buttons."""
    if not sess.items:
        return False, "No media staged. Send photos/videos first."
    markup = _post_button_markup(sess.buttons) if sess.buttons else None
    try:
        if track_workshop:
            await _clear_workshop_preview(context, chat_id, sess)
        ids = await _show_staged_media(context, chat_id, sess, markup=markup)
        if track_workshop:
            sess.workshop_preview_ids = ids
            sess.workshop_chat_id = chat_id
        extra = ""
        if len(sess.items) > ALBUM_CHUNK:
            extra = (
                f" (first {ALBUM_CHUNK} of {len(sess.items)} — use 📦 Make album(s) "
                f"to split into albums of ≤{ALBUM_CHUNK})"
            )
        if _crop_applies(sess) or _bytes_pipeline(sess):
            extra += " · edits apply on channel send"
        if sess.buttons and len(sess.items) > 1:
            extra += " · buttons shown on the message below the album (Telegram album limit)"
        return True, f"Preview sent{extra}."
    except Exception as e:
        logger.warning("post preview failed: %s", e)
        report_bot_error("album-composer-bot", "preview", e)
        return False, f"Preview failed: {e}"


def _confirm_post_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Post now", callback_data="ac:confirm")],
            [InlineKeyboardButton("👁 Preview again", callback_data="ac:preview")],
            [InlineKeyboardButton("« Back", callback_data="ac:post")],
        ]
    )


async def _present_confirm_step(
    context: ContextTypes.DEFAULT_TYPE,
    query,
    sess: ComposerSession,
) -> None:
    """Full post preview, then destination confirm prompt."""
    chat_id = query.message.chat_id
    await _preview_post(context, chat_id, sess, track_workshop=True)
    name = html.escape((sess.channel_name or "").strip() or f"#{sess.channel_id}")
    thread_line = ""
    if sess.thread_id:
        topics = _insert_cache.get("topics") or []
        topic_title = next(
            (str(t.get("title") or "") for t in topics if int(t.get("id") or 0) == int(sess.thread_id)),
            "",
        )
        if topic_title:
            thread_line = f"\nTopic: <b>{html.escape(topic_title[:80])}</b>"
        else:
            thread_line = f"\nTopic id: <code>{sess.thread_id}</code>"
    await query.edit_message_text(
        f"Destination: <b>{name}</b>{thread_line}\n\n"
        "Review your post <b>above</b>, then tap <b>Post now</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=_confirm_post_keyboard(),
    )


def _storage_hub_deposit_rows(sess: ComposerSession) -> list[list[InlineKeyboardButton]]:
    """Pinned payment-bot deposit panel covers bulk presets; workshop keeps staged-only shortcut."""
    try:
        from app.services.storage_topic_deposit import resolve_storage_topic_row, storage_hub_chat_id_int
        from bots.storage_hub_deposit_bot import album_composer_storage_deposit_enabled

        if not album_composer_storage_deposit_enabled():
            return []
        if not sess.thread_id or not sess.panel_chat_id:
            return []
        if int(sess.panel_chat_id) != storage_hub_chat_id_int():
            return []
        if not resolve_storage_topic_row(int(sess.thread_id)):
            return []
    except Exception:
        return []
    if not sess.items:
        return []
    n = len(sess.items)
    return [[InlineKeyboardButton(f"📥 Deposit staged ({n})", callback_data="ac:depositstaged")]]


def _main_keyboard(sess: ComposerSession) -> InlineKeyboardMarkup:
    promo_label = "🎁 Promo ✓" if sess.promo_enabled else "🎁 Promo ✗"
    silent_label = "🔕 Silent ✓" if sess.send_silent else "🔕 Silent ✗"
    crop_label = "✂️ Crop ✓" if _crop_applies(sess) else "✂️ Crop"
    wm_on = not sess.watermark_skip and sess.watermark_enabled is not False
    wm_label = "🏷 Watermark ✓" if wm_on else "🏷 Watermark ✗"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("🛠 Workshop menu", callback_data="ac:panel")],
        [
            InlineKeyboardButton("📝 Caption", callback_data="ac:caption"),
            InlineKeyboardButton("📎 Insert", callback_data="ac:insert"),
            InlineKeyboardButton("🔘 Buttons", callback_data="ac:buttons"),
        ],
        [
            InlineKeyboardButton(crop_label, callback_data="ac:cropmenu"),
            InlineKeyboardButton(wm_label, callback_data="ac:wmmenu"),
            InlineKeyboardButton(promo_label, callback_data="ac:promo"),
        ],
        [
            InlineKeyboardButton("🔀 Shuffle", callback_data="ac:shuffle"),
            InlineKeyboardButton(silent_label, callback_data="ac:silent"),
        ],
    ]
    if sess.items:
        rows.append([InlineKeyboardButton("👁 Preview post", callback_data="ac:preview")])
    if sess.items and not _in_album_batch(sess):
        size = _batch_chunk_size(sess)
        n_albums = (len(sess.items) + size - 1) // size
        promo_tag = " +promo" if sess.promo_enabled else ""
        rows.append(
            [InlineKeyboardButton(f"📦 Make album(s) — {n_albums}×≤{size}{promo_tag}", callback_data="ac:mkalb")]
        )
    erome_row = _erome_workshop_row(sess)
    if erome_row:
        rows.append(erome_row)
    rows.extend(_storage_hub_deposit_rows(sess))
    rows.append([InlineKeyboardButton("📤 Post to channel…", callback_data="ac:post")])
    rows.append(
        [
            InlineKeyboardButton("💾 Save draft", callback_data="ac:save"),
            InlineKeyboardButton("📂 My drafts", callback_data="ac:drafts"),
        ]
    )
    rows.append([InlineKeyboardButton("🗑 Clear media", callback_data="ac:clear")])
    rows.append([InlineKeyboardButton("🧩 Split to emojis", callback_data="ac:emojipack")])
    return InlineKeyboardMarkup(rows)


def _crop_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("8% all sides", callback_data="ac:crop:8:all"),
                InlineKeyboardButton("8% bottom", callback_data="ac:crop:8:bottom"),
            ],
            [
                InlineKeyboardButton("10% bottom", callback_data="ac:crop:10:bottom"),
                InlineKeyboardButton("Blur bottom 12%", callback_data="ac:crop:blur:12:bottom"),
            ],
            [
                InlineKeyboardButton("Custom…", callback_data="ac:crop:custom"),
                InlineKeyboardButton("Off", callback_data="ac:crop:off"),
            ],
            [InlineKeyboardButton("« Back", callback_data="ac:panel")],
        ]
    )


async def _sync_panel(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    sess: ComposerSession,
    *,
    reply_to_message_id: int | None = None,
    extra_items: list[StagedItem] | None = None,
    force_new: bool = False,
    pin_bottom: bool = False,
) -> None:
    """
    Update the draft options panel.
    pin_bottom: delete the old panel and post a fresh one at the chat bottom (Telegram has no sticky footer).
    """
    in_batch = _in_album_batch(sess)
    repost = pin_bottom or force_new

    if in_batch and not repost:
        await _refresh_album_header(context, sess)

    if repost:
        await _drop_panel_message(context, sess, allow_album_menu=pin_bottom)

    display_items = sess.items + (extra_items or [])
    text = _selection_panel_text(sess) if in_batch else _status_text(sess, display_items)
    markup = _main_keyboard(sess)
    bot = context.bot

    if not repost and sess.panel_chat_id and sess.panel_message_id:
        try:
            await bot.edit_message_text(
                text,
                chat_id=sess.panel_chat_id,
                message_id=sess.panel_message_id,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
            return
        except Exception as e:
            err = str(e).lower()
            if "message is not modified" in err:
                return
            logger.debug("panel edit failed, recreating: %s", e)
            sess.panel_chat_id = None
            sess.panel_message_id = None

    kwargs: dict = {
        "parse_mode": ParseMode.HTML,
        "reply_markup": markup,
        "disable_web_page_preview": True,
    }
    if reply_to_message_id:
        kwargs["reply_to_message_id"] = reply_to_message_id
    sent = await bot.send_message(chat_id, text, **kwargs)
    sess.panel_chat_id = sent.chat_id
    sess.panel_message_id = sent.message_id
    if in_batch:
        entry = sess.albums[sess.active_album_idx]
        entry.menu_message_id = sent.message_id
        entry.chat_id = sent.chat_id


async def _refresh_album_header(context: ContextTypes.DEFAULT_TYPE, sess: ComposerSession) -> None:
    """Keep the active album's 'Album draft' header + displayed caption in sync."""
    if not _in_album_batch(sess):
        return
    idx = sess.active_album_idx
    entry = sess.albums[idx]
    _copy_remix_state_to_entry(sess, entry)
    if not entry.chat_id or not entry.header_message_id:
        return
    try:
        await context.bot.edit_message_text(
            _entry_status_text(sess, entry, idx, len(sess.albums)),
            chat_id=entry.chat_id,
            message_id=entry.header_message_id,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.debug("album header refresh failed: %s", e)
    # Mirror the caption onto the displayed album's first tile.
    if entry.media_message_ids:
        try:
            await context.bot.edit_message_caption(
                chat_id=entry.chat_id,
                message_id=entry.media_message_ids[0],
                caption=(entry.caption or "").strip() or None,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.debug("album caption sync failed: %s", e)


async def _reorder_album_display(context: ContextTypes.DEFAULT_TYPE, sess: ComposerSession) -> bool:
    """Re-paint the active album's displayed tiles in the session's current item order."""
    if not _in_album_batch(sess):
        return False
    entry = sess.albums[sess.active_album_idx]
    _copy_remix_state_to_entry(sess, entry)
    ids = entry.media_message_ids
    items = entry.items
    if not ids or len(ids) != len(items):
        return False
    cap = (entry.caption or "").strip() or None
    ok = True
    for j, (mid, it) in enumerate(zip(ids, items)):
        cls = InputMediaVideo if it.kind == "video" else InputMediaPhoto
        item_cap = cap if j == 0 else None
        media = cls(media=it.file_id, caption=item_cap, parse_mode=ParseMode.HTML if item_cap else None)
        try:
            await context.bot.edit_message_media(media=media, chat_id=entry.chat_id, message_id=mid)
        except Exception as e:
            if "not modified" not in str(e).lower():
                ok = False
                logger.debug("album reorder edit %s failed: %s", mid, e)
        await asyncio.sleep(0.15)
    return ok


async def _drop_panel_message(
    context: ContextTypes.DEFAULT_TYPE,
    sess: ComposerSession,
    *,
    allow_album_menu: bool = False,
) -> None:
    if _panel_is_album_menu(sess) and not allow_album_menu:
        # Album menu messages stay attached to their album unless we are re-pinning to the bottom.
        return
    if not sess.panel_chat_id or not sess.panel_message_id:
        sess.panel_chat_id = None
        sess.panel_message_id = None
        return
    try:
        await context.bot.delete_message(sess.panel_chat_id, sess.panel_message_id)
    except Exception:
        pass
    if _in_album_batch(sess) and allow_album_menu:
        entry = sess.albums[sess.active_album_idx]
        if entry.menu_message_id == sess.panel_message_id:
            entry.menu_message_id = None
    sess.panel_chat_id = None
    sess.panel_message_id = None


async def _finalize_media_batch(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    sess: ComposerSession,
) -> None:
    """After the last item in a batch: update the single draft panel in place (no status spam)."""
    if sess.items:
        ids = [it.message_id for it in sess.items if it.message_id]
        if ids:
            sess.batch_anchor_max = max(ids)
    # Re-post the editor menu at the bottom so it stays visible after large uploads.
    await _sync_panel(context, chat_id, sess, pin_bottom=True)


async def _display_album_media(context: ContextTypes.DEFAULT_TYPE, chat_id: int, entry: AlbumEntry) -> None:
    """Render one batch album in chat as a real Telegram media group."""
    items = entry.items[:ALBUM_CHUNK]
    bot = context.bot
    cap = (entry.caption or "").strip() or None
    if len(items) == 1:
        it = items[0]
        kw: dict = {}
        if cap:
            kw["caption"] = cap
            kw["parse_mode"] = ParseMode.HTML
        sender = bot.send_video if it.kind == "video" else bot.send_photo
        msg = await sender(chat_id, it.file_id, **kw)
        entry.media_message_ids = [msg.message_id]
        if entry.items:
            entry.items[0].message_id = msg.message_id
        return
    media = []
    for j, it in enumerate(items):
        c = cap if j == 0 else None
        cls = InputMediaVideo if it.kind == "video" else InputMediaPhoto
        media.append(cls(media=it.file_id, caption=c, parse_mode=ParseMode.HTML if c else None))
    msgs = await bot.send_media_group(chat_id, media)
    entry.media_message_ids = [m.message_id for m in msgs]
    for it, mid in zip(entry.items, entry.media_message_ids):
        it.message_id = mid


async def _make_albums(context: ContextTypes.DEFAULT_TYPE, query, sess: ComposerSession) -> None:
    """Split staged media into albums of ≤10, each with header above + menu below."""
    chat_id = query.message.chat_id
    if _in_album_batch(sess):
        await query.answer("A batch is already open — post or clear it first.", show_alert=True)
        return
    items = list(sess.items)
    if not items:
        await query.answer("No media staged. Send photos/videos first.", show_alert=True)
        return
    size = _batch_chunk_size(sess)
    chunks = [items[i : i + size] for i in range(0, len(items), size)][:MAX_ALBUMS]
    total = len(chunks)
    await query.answer(f"Creating {total} album(s)…")
    await _clear_workshop_preview(context, chat_id, sess)
    await _drop_panel_message(context, sess)
    promo_note = " (1 slot reserved per album for the promo tile)" if sess.promo_enabled else ""
    status = await context.bot.send_message(
        chat_id, f"📦 Building {total} album(s) of ≤{size}{promo_note}…"
    )

    sess.albums = []
    sess.active_album_idx = None
    failures = 0
    for i, chunk in enumerate(chunks):
        entry = AlbumEntry()
        _copy_remix_state_to_entry(sess, entry)
        entry.items = list(chunk)
        entry.chat_id = chat_id
        sess.albums.append(entry)
        try:
            header = await context.bot.send_message(
                chat_id,
                _entry_status_text(sess, entry, i, total),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            entry.header_message_id = header.message_id
            await _display_album_media(context, chat_id, entry)
            menu = await context.bot.send_message(
                chat_id, f"Album {i + 1}/{total}", reply_markup=_album_menu_min_kb(i, False)
            )
            entry.menu_message_id = menu.message_id
        except Exception as e:
            failures += 1
            logger.warning("album %s/%s display failed: %s", i + 1, total, e)
            report_bot_error("album-composer-bot", f"make-albums display {i + 1}/{total}", e)
            try:
                await context.bot.send_message(
                    chat_id, f"⚠️ Album {i + 1}/{total} could not be displayed: {str(e)[:160]}"
                )
            except Exception:
                pass
        await asyncio.sleep(0.5)  # stay under Telegram flood limits across large batches

    sess.items = []
    await _activate_album(context, chat_id, sess, total - 1, pin_bottom=True)
    done = f"📦 {total} album(s) ready — staged media split into albums of ≤{size}{promo_note}."
    if failures:
        done += f"\n⚠️ {failures} album(s) failed to display (reported to error hub; still in batch)."
    done += "\nThe bottom album holds the main menu. Tap “Open main menu” under any album to select it."
    try:
        await status.edit_text(done)
    except Exception:
        pass


async def _activate_album(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    sess: ComposerSession,
    idx: int,
    *,
    pin_bottom: bool = False,
) -> None:
    """Move the 'current selection' — full menu to album idx, minimal button elsewhere."""
    total = len(sess.albums)
    if not (0 <= idx < total):
        return
    bot = context.bot
    prev = sess.active_album_idx
    if prev is not None and prev != idx and prev < total:
        pentry = sess.albums[prev]
        _copy_remix_state_to_entry(sess, pentry)
        try:
            await bot.edit_message_text(
                _entry_status_text(sess, pentry, prev, total),
                chat_id=pentry.chat_id,
                message_id=pentry.header_message_id,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.debug("demote header edit failed: %s", e)
        try:
            await bot.edit_message_text(
                f"Album {prev + 1}/{total}",
                chat_id=pentry.chat_id,
                message_id=pentry.menu_message_id,
                reply_markup=_album_menu_min_kb(prev, pentry.posted),
            )
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.debug("demote menu edit failed: %s", e)

    entry = sess.albums[idx]
    sess.active_album_idx = idx
    _load_entry_into_session(sess, entry)
    ids = [it.message_id for it in sess.items if it.message_id]
    if ids:
        sess.batch_anchor_max = max(ids)
    sess.panel_chat_id = entry.chat_id
    sess.panel_message_id = entry.menu_message_id
    try:
        await bot.edit_message_text(
            _entry_status_text(sess, entry, idx, total),
            chat_id=entry.chat_id,
            message_id=entry.header_message_id,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.debug("promote header edit failed: %s", e)
    if pin_bottom:
        await _sync_panel(context, chat_id, sess, pin_bottom=True)
        return
    try:
        await bot.edit_message_text(
            _selection_panel_text(sess),
            chat_id=entry.chat_id,
            message_id=entry.menu_message_id,
            parse_mode=ParseMode.HTML,
            reply_markup=_main_keyboard(sess),
            disable_web_page_preview=True,
        )
    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.debug("promote menu edit failed, recreating: %s", e)
            sess.panel_message_id = None
            await _sync_panel(context, chat_id, sess, pin_bottom=True)


async def _after_album_posted(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, sess: ComposerSession
) -> None:
    """Mark the active album posted, then advance selection to the next unposted album."""
    idx, total = sess.active_album_idx, len(sess.albums)
    entry = sess.albums[idx]
    _copy_remix_state_to_entry(sess, entry)
    entry.posted = True
    bot = context.bot
    try:
        await bot.edit_message_text(
            _entry_status_text(sess, entry, idx, total),
            chat_id=entry.chat_id,
            message_id=entry.header_message_id,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception:
        pass
    nxt = next((i for i in range(total) if not sess.albums[i].posted), None)
    if nxt is None:
        try:
            await bot.edit_message_text(
                f"Album {idx + 1}/{total}",
                chat_id=entry.chat_id,
                message_id=entry.menu_message_id,
                reply_markup=_album_menu_min_kb(idx, True),
            )
        except Exception:
            pass
        sess.panel_chat_id = None
        sess.panel_message_id = None
        sess.active_album_idx = None
        sess.albums = []
        sess.items = []
        await bot.send_message(chat_id, f"🎉 All {total} album(s) in this batch are posted.")
        return
    await _activate_album(context, chat_id, sess, nxt)
    await bot.send_message(chat_id, f"➡️ Album {nxt + 1}/{total} is now the current selection.")


async def _sync_panel_from_message(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    sess: ComposerSession,
    *,
    pin_bottom: bool = False,
) -> None:
    """Refresh the options panel (optionally re-post at the bottom of the chat)."""
    await _sync_panel(
        context,
        message.chat_id,
        sess,
        pin_bottom=pin_bottom or not sess.panel_message_id,
    )


def _remember_panel(sess: ComposerSession, message) -> None:
    if message:
        sess.panel_chat_id = message.chat_id
        sess.panel_message_id = message.message_id


async def _reset_session_keep_panel(context: ContextTypes.DEFAULT_TYPE) -> ComposerSession:
    old = _session(context)
    chat_id, msg_id = old.panel_chat_id, old.panel_message_id
    context.chat_data[SESSION_KEY] = ComposerSession()
    sess = _session(context)
    if chat_id and msg_id:
        sess.panel_chat_id = chat_id
        sess.panel_message_id = msg_id
        await _sync_panel(context, chat_id, sess)
    return sess


def _cancel_solo_batch(context: ContextTypes.DEFAULT_TYPE) -> None:
    task = context.chat_data.get(SOLO_BATCH_KEY, {}).get("task")
    if task:
        task.cancel()


async def _add_staged(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    kind: str,
    file_id: str,
    name: str,
) -> None:
    sess = _session(context)
    _capture_forum_topic(sess, message)
    if _in_album_batch(sess):
        if len(sess.items) >= ALBUM_CHUNK:
            await message.reply_text(
                f"Active album is full ({ALBUM_CHUNK} max). Select another album or post this one first."
            )
            return
    elif len(sess.items) >= MAX_STAGED:
        await message.reply_text(f"Draft full ({MAX_STAGED} max). Post or /clear first.")
        return
    sess.items.append(StagedItem(file_id=file_id, kind=kind, name=name, message_id=message.message_id))

    bucket = context.chat_data.setdefault(SOLO_BATCH_KEY, {"count": 0, "chat_id": message.chat_id, "task": None})
    bucket["count"] += 1
    bucket["chat_id"] = message.chat_id
    if bucket["task"]:
        bucket["task"].cancel()

    async def flush_solo() -> None:
        await asyncio.sleep(SOLO_BATCH_DELAY)
        entry = context.chat_data.pop(SOLO_BATCH_KEY, None)
        if not entry:
            return
        try:
            async with _intake_lock(context):
                await _finalize_media_batch(
                    context,
                    entry["chat_id"],
                    _session(context),
                )
        except Exception as e:
            logger.warning("solo batch finalize: %s", e)
            report_bot_error("album-composer-bot", "solo batch finalize", e)

    bucket["task"] = asyncio.create_task(flush_solo())


def _detect_kind(message) -> tuple[str, str] | None:
    if message.photo:
        return "photo", "photo.jpg"
    if message.video:
        return "video", "video.mp4"
    if message.animation:
        return "video", "animation.mp4"
    doc = message.document
    if doc:
        mime = (doc.mime_type or "").lower()
        fn = (doc.file_name or "file").lower()
        if mime.startswith("video/") or fn.endswith((".mp4", ".webm", ".mov", ".mkv")):
            return "video", fn or "video.mp4"
        if mime.startswith("image/") or fn.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            return "photo", fn or "photo.jpg"
    return None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    sess = _session(context)
    from bots.remixer_cover import cover_help_blurb
    from bots.remixer_rebundle import rebundle_help_blurb

    await update.message.reply_text(
        "<b>TBCC Album Composer</b>\n\n"
        "Send photos and videos here to build an album (lite extension).\n\n"
        "<b>Flow</b>\n"
        "1. Send media (single or album)\n"
        "2. Use the <b>workshop menu</b> below — caption, buttons, crop, post\n"
        "3. <b>Split to emojis</b> on the menu for emoji-pack grids\n"
        "4. <b>Preview post</b> before you send · <b>Make album(s)</b> to split large batches\n\n"
        f"{cover_help_blurb()}\n"
        f"{rebundle_help_blurb()}\n\n"
        "<b>Commands</b> /menu · /cover · /compose · /rebundle · /preview · /caption · /crop · /clear · /emoji_pack\n"
        "The menu stays pinned at the bottom while you work.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🛠 Open workshop menu", callback_data="ac:panel")]]
        ),
    )
    await _sync_panel(context, update.effective_chat.id, sess, pin_bottom=True)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


def _clear_staged_media(sess: ComposerSession) -> int:
    """Remove staged photos/videos only; keep caption, buttons, promo, destination."""
    n = len(sess.items)
    sess.items.clear()
    return n


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    sess = _session(context)
    n = _clear_staged_media(sess)
    context.chat_data.pop(AWAIT_KEY, None)
    await update.message.reply_text(
        f"Cleared {n} staged item(s). Caption and buttons kept.",
        reply_markup=_back_keyboard(sess),
    )
    await _clear_workshop_preview(context, update.effective_chat.id, sess)
    await _sync_panel(context, update.effective_chat.id, sess, pin_bottom=True)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-post the full editor menu at the bottom of the chat."""
    if await _deny_unauthorized(update):
        return
    sess = _session(context)
    await _sync_panel(context, update.effective_chat.id, sess, pin_bottom=True)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    await cmd_menu(update, context)


async def cmd_shuffle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    sess = _session(context)
    if len(sess.items) < 2:
        await update.message.reply_text("Need at least 2 items to shuffle.")
        return
    random.shuffle(sess.items)
    if _in_album_batch(sess):
        repainted = await _reorder_album_display(context, sess)
        note = "Order shuffled." if repainted else (
            "Order shuffled — display re-paint failed; new order still applies on preview and send."
        )
        await update.message.reply_text(note, reply_markup=_back_keyboard(sess))
        await _sync_panel(context, update.effective_chat.id, sess)
        return
    await update.message.reply_text("Order shuffled.", reply_markup=_back_keyboard(sess))
    await _refresh_workshop(context, update.effective_chat.id, sess)


def _apply_watermark_phrase(sess: ComposerSession, phrase: str) -> str:
    from app.data.aof_telegram_links import normalize_telegram_me_brand

    raw = (phrase or "").strip()
    low = raw.lower()
    if not raw or low in ("status", "?"):
        return f"Watermark: {_watermark_status_label(sess)}"
    if low in ("off", "none", "no", "disable", "clear"):
        sess.watermark_skip = True
        sess.watermark_enabled = False
        return "Promo watermark off for this draft."
    if low in ("on", "enable", "default"):
        sess.watermark_skip = False
        sess.watermark_enabled = True
        return "Promo watermark on (uses global text unless you set one)."
    if low.startswith("opacity "):
        try:
            sess.watermark_opacity = max(0.15, min(1.0, float(raw.split(maxsplit=1)[1])))
            sess.watermark_skip = False
            return f"Watermark opacity: {sess.watermark_opacity:.2f}"
        except (IndexError, ValueError):
            return "Usage: /watermark opacity 0.7"
    if low.startswith("color "):
        sess.watermark_color = raw.split(maxsplit=1)[1].strip()[:16]
        sess.watermark_skip = False
        return f"Watermark color: {sess.watermark_color}"
    if low.startswith("2 "):
        sess.watermark_text_secondary = normalize_telegram_me_brand(raw.split(maxsplit=1)[1].strip())[:120]
        sess.watermark_skip = False
        return f"Secondary watermark: {sess.watermark_text_secondary}"
    if low.startswith("3 "):
        sess.watermark_text_tertiary = normalize_telegram_me_brand(raw.split(maxsplit=1)[1].strip())[:120]
        sess.watermark_skip = False
        return f"Tertiary watermark: {sess.watermark_text_tertiary}"
    if low in ("strip on", "strip off"):
        sess.watermark_strip_previous = low.endswith("on")
        return f"Strip previous watermark bands: {'on' if sess.watermark_strip_previous else 'off'}"
    sess.watermark_text = normalize_telegram_me_brand(raw)[:120]
    sess.watermark_skip = False
    sess.watermark_enabled = True
    return f"Primary watermark: {sess.watermark_text}"


async def cmd_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    text = " ".join(context.args or []).strip()
    sess = _session(context)
    if not text:
        await update.message.reply_text(
            "<b>Promo watermark</b> (burn-in on photos/videos at send)\n\n"
            "• <code>/watermark telegram.me/aofmainhub</code> — primary text\n"
            "• <code>/watermark 2 extra.link</code> — secondary\n"
            "• <code>/watermark 3 third.link</code> — tertiary\n"
            "• <code>/watermark opacity 0.65</code>\n"
            "• <code>/watermark color #ffffff</code>\n"
            "• <code>/watermark strip on</code> — blur old bands first\n"
            "• <code>/watermark off</code> / <code>on</code>\n\n"
            f"Current: <code>{html.escape(_watermark_status_label(sess))}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✓ On", callback_data="ac:wm:on"),
                        InlineKeyboardButton("✗ Off", callback_data="ac:wm:off"),
                    ],
                    [InlineKeyboardButton("Use global default", callback_data="ac:wm:global")],
                ]
            ),
        )
        return
    msg = _apply_watermark_phrase(sess, text)
    await update.message.reply_text(msg)
    await _sync_panel_from_message(update.message, context, sess)


async def cmd_crop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    text = " ".join(context.args or []).strip()
    sess = _session(context)
    if not text:
        await update.message.reply_text(
            "<b>Crop &amp; watermarks</b> (photos only on send)\n\n"
            "Tap presets below or send plain language, e.g.:\n"
            "• <code>8% bottom</code>\n"
            "• <code>crop 10% top</code>\n"
            "• <code>blur bottom 12%</code>\n"
            "• <code>remove watermark</code> (8% bottom)\n"
            "• <code>off</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=_crop_menu_keyboard(),
        )
        return
    msg = _apply_crop_phrase(sess, text)
    await update.message.reply_text(msg)
    await _sync_panel_from_message(update.message, context, sess)


async def cmd_caption(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    text = " ".join(context.args or []).strip()
    sess = _session(context)
    if not text:
        context.chat_data[AWAIT_KEY] = "caption"
        await update.message.reply_text("Send the caption text (HTML supported).")
        return
    sess.caption = text
    await update.message.reply_text("Caption updated.", reply_markup=_back_keyboard(sess))
    await _refresh_workshop(context, update.effective_chat.id, sess)


async def cmd_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    raw = " ".join(context.args or []).strip()
    sess = _session(context)
    if "|" not in raw:
        context.chat_data[AWAIT_KEY] = "button"
        await update.message.reply_text(
            f"Send button as: <code>Label|https://…</code>{_album_buttons_limit_note(sess)}",
            parse_mode=ParseMode.HTML,
        )
        return
    label, url = raw.split("|", 1)
    label, url = label.strip(), url.strip()
    if not label or not url.startswith(("http://", "https://", "tg://")):
        await update.message.reply_text("Need label and a valid http(s) or tg:// URL.")
        return
    sess = _session(context)
    sess.buttons.append({"text": label[:64], "url": url[:512]})
    await update.message.reply_text(
        f"Button added ({len(sess.buttons)} total).",
        reply_markup=_back_keyboard(sess),
    )
    await _refresh_workshop(context, update.effective_chat.id, sess)


async def cmd_drafts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    drafts = await _fetch_drafts_api()
    await update.message.reply_text(
        "<b>Saved drafts</b> — tap to load.",
        parse_mode=ParseMode.HTML,
        reply_markup=_drafts_keyboard(drafts),
    )


async def cmd_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    sess = _session(context)
    ok, msg = await _preview_post(context, update.effective_chat.id, sess)
    await update.message.reply_text(msg, reply_markup=_back_keyboard(sess) if ok else None)


async def cmd_savecaption(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    sess = _session(context)
    body = (sess.caption or "").strip()
    if not body:
        await update.message.reply_text("No caption in draft to save.")
        return
    title = " ".join(context.args or "").strip() or None
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.post(f"{API_BASE}/caption-snippets/", json={"title": title, "body": body})
        if r.status_code == 200:
            await update.message.reply_text("Caption saved to TBCC library.")
        else:
            await update.message.reply_text(f"Save failed: {r.text[:200]}")
    except httpx.HTTPError as e:
        await update.message.reply_text(f"API error: {e}")


async def cmd_savepromo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    raw = " ".join(context.args or "").strip()
    if "|" not in raw:
        await update.message.reply_text("Usage: /savepromo Label|https://…")
        return
    label, url = raw.split("|", 1)
    label, url = label.strip(), url.strip()
    if not label or not url.startswith(("http://", "https://")):
        await update.message.reply_text("Need label and https URL.")
        return
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.post(
                f"{API_BASE}/promo-affiliate-links/",
                json={"label": label, "url": url, "active": True},
            )
        if r.status_code in (200, 201):
            await update.message.reply_text("Promo link saved to TBCC library.")
        else:
            await update.message.reply_text(f"Save failed: {r.text[:200]}")
    except httpx.HTTPError as e:
        await update.message.reply_text(f"API error: {e}")


async def _fetch_insert_data() -> dict:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        promos_r, snippets_r = await asyncio.gather(
            client.get(f"{API_BASE}/promo-affiliate-links/", params={"sort": "priority_asc", "active_only": "true"}),
            client.get(f"{API_BASE}/caption-snippets/"),
        )
    promos = promos_r.json() if promos_r.status_code == 200 else []
    snippets = snippets_r.json() if snippets_r.status_code == 200 else []
    return {"promos": promos if isinstance(promos, list) else [], "snippets": snippets if isinstance(snippets, list) else []}


def _promo_url(row: dict) -> str:
    return str(row.get("short_url") or row.get("url") or "").strip()


def _snippet_label(row: dict) -> str:
    title = str(row.get("title") or "").strip()
    if title:
        return title[:48]
    body = str(row.get("body") or "")
    line = next((l for l in body.splitlines() if l.strip()), "")
    return (line[:48] or "Untitled")


async def _insert_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    data = await _fetch_insert_data()
    promos = data["promos"][:20]
    snippets = data["snippets"][:20]
    rows: list[list[InlineKeyboardButton]] = []
    for i, p in enumerate(promos[:8]):
        url = _promo_url(p)
        if not url:
            continue
        label = str(p.get("label") or "Promo")[:40]
        rows.append([InlineKeyboardButton(f"🔗 {label}", callback_data=f"ac:ins:u:{i}")])
    # Store mapping in a module-level cache keyed by time — use callback with encoded index into fetched data
    _insert_cache["promos"] = promos
    _insert_cache["snippets"] = snippets
    for i, s in enumerate(snippets[:8]):
        rows.append([InlineKeyboardButton(f"📝 {_snippet_label(s)}", callback_data=f"ac:ins:s:{i}")])
    rows.append([InlineKeyboardButton("« Back", callback_data="ac:panel")])
    return InlineKeyboardMarkup(rows)


_insert_cache: dict = {"promos": [], "snippets": []}


async def _fetch_channels() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(f"{API_BASE}/channels/")
        if r.status_code != 200:
            return []
        data = r.json()
        return data if isinstance(data, list) else []
    except httpx.HTTPError:
        return []


async def _channel_pick_keyboard() -> InlineKeyboardMarkup:
    channels = await _fetch_channels()
    rows: list[list[InlineKeyboardButton]] = []
    _insert_cache["channels"] = channels
    for i, ch in enumerate(channels[:12]):
        name = str(ch.get("name") or ch.get("identifier") or f"#{ch.get('id')}")[:36]
        rows.append([InlineKeyboardButton(name, callback_data=f"ac:ch:{i}")])
    if not rows:
        rows.append([InlineKeyboardButton("(no channels — add in dashboard)", callback_data="ac:panel")])
    rows.append([InlineKeyboardButton("📥 Saved Messages", callback_data="ac:saved")])
    rows.append([InlineKeyboardButton("« Back", callback_data="ac:panel")])
    return InlineKeyboardMarkup(rows)


async def _fetch_forum_topics(channel_id: int) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(f"{API_BASE}/channels/{channel_id}/forum-topics")
        if r.status_code != 200:
            return []
        data = r.json()
        topics = data.get("topics") if isinstance(data, dict) else []
        return [t for t in topics if isinstance(t, dict) and t.get("id")]
    except httpx.HTTPError:
        return []


def _topic_pick_keyboard(topics: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    _insert_cache["topics"] = topics[:20]
    for t in topics[:12]:
        tid = int(t.get("id") or 0)
        if not tid:
            continue
        title = str(t.get("title") or f"Topic {tid}")[:34]
        rows.append([InlineKeyboardButton(title, callback_data=f"ac:topic:{tid}")])
    rows.append([InlineKeyboardButton("📢 Main chat (no topic)", callback_data="ac:topic:0")])
    rows.append([InlineKeyboardButton("« Back", callback_data="ac:post")])
    return InlineKeyboardMarkup(rows)


_HTTP_INTERACTIVE = httpx.Timeout(connect=5.0, read=22.0, write=5.0, pool=10.0)
_SESSION_BUSY_MARKERS = ("busy", "timed out", "timeout", "session", "locked", "waiting for")


def _api_err_is_busy(result: dict) -> bool:
    err = result.get("error")
    if not err and result.get("errors"):
        err = "; ".join(str(x) for x in result["errors"])
    low = str(err or "").lower()
    return any(m in low for m in _SESSION_BUSY_MARKERS)


async def _saved_batch_fast(
    media_count: int,
    message_ids: list[int],
    anchor_max: int | None,
    caption: str,
    append_promo: bool,
    bot_username: str,
    *,
    files: list[dict] | None = None,
    crop: dict | None = None,
    watermark: dict | None = None,
) -> dict:
    try:
        use_slow = bool(crop or watermark)
        timeout = httpx.Timeout(connect=5.0, read=300.0, write=60.0, pool=10.0) if use_slow else _HTTP_INTERACTIVE
        async with httpx.AsyncClient(timeout=timeout) as client:
            payload = {
                "media_count": media_count,
                "message_ids": message_ids,
                "anchor_max_message_id": anchor_max,
                "bot_username": bot_username,
                "caption": caption or "",
                "append_send_promo": append_promo,
            }
            if files:
                payload["files"] = files
            if crop:
                payload["crop"] = crop
            if watermark:
                payload["watermark"] = watermark
            r = await client.post(
                f"{API_BASE}/import/saved-from-bot-messages",
                json=payload,
            )
    except httpx.TimeoutException:
        return {"error": "TBCC timed out (Telegram session busy — retry in a few seconds)."}
    except httpx.ConnectError:
        return {"error": f"Cannot reach TBCC API at {API_BASE}. Is TBCC-Backend running?"}
    except httpx.HTTPError as e:
        return {"error": f"API error: {e}"}
    if r.status_code == 404:
        return {"error": "Backend missing saved-from-bot-messages route — restart TBCC-Backend."}
    try:
        data = r.json()
    except Exception:
        return {"error": r.text[:300] or f"HTTP {r.status_code}"}
    if r.status_code >= 400 and not data.get("error"):
        data["error"] = data.get("error") or f"HTTP {r.status_code}"
    return data


async def _saved_batch_with_retry(
    media_count: int,
    message_ids: list[int],
    anchor_max: int | None,
    caption: str,
    append_promo: bool,
    bot_username: str,
    *,
    files: list[dict] | None = None,
    crop: dict | None = None,
    watermark: dict | None = None,
    status_msg=None,
) -> dict:
    last: dict = {"error": "Telegram session busy"}
    for attempt in range(10):
        last = await _saved_batch_fast(
            media_count,
            message_ids,
            anchor_max,
            caption,
            append_promo,
            bot_username,
            files=files,
            crop=crop,
            watermark=watermark,
        )
        if not _api_err_is_busy(last):
            return last
        if status_msg is not None and attempt == 0:
            try:
                await status_msg.edit_text("Sending… (waiting for Telegram session)")
            except Exception:
                pass
        if attempt + 1 < 10:
            await asyncio.sleep(1.0)
    return last


async def _post_channel_with_retry(
    media_count: int,
    message_ids: list[int],
    anchor_max: int | None,
    sess: ComposerSession,
    bot_username: str,
    *,
    status_msg=None,
) -> dict:
    last: dict = {"ok": False, "error": "Telegram session busy"}
    for attempt in range(10):
        last = await _post_channel_fast(media_count, message_ids, anchor_max, sess, bot_username)
        if not _api_err_is_busy(last):
            return last
        if status_msg is not None and attempt == 0:
            try:
                await status_msg.edit_text("Sending… (waiting for Telegram session)")
            except Exception:
                pass
        if attempt + 1 < 10:
            await asyncio.sleep(1.0)
    return last


async def _post_channel_fast(
    media_count: int,
    message_ids: list[int],
    anchor_max: int | None,
    sess: ComposerSession,
    bot_username: str,
) -> dict:
    body = {
        "channel_id": sess.channel_id,
        "message_thread_id": sess.thread_id,
        "media_count": media_count,
        "message_ids": message_ids,
        "anchor_max_message_id": anchor_max,
        "bot_username": bot_username,
        "caption": sess.caption,
        "buttons": sess.buttons,
        "send_silent": sess.send_silent,
        "append_send_promo": sess.promo_enabled,
    }
    files = _files_api_payload(sess)
    if files:
        body["files"] = files
    crop = _crop_api_payload(sess)
    if crop:
        body["crop"] = crop
    wm = _watermark_api_payload(sess)
    if wm:
        body["watermark"] = wm
    try:
        use_slow = _bytes_pipeline(sess)
        timeout = httpx.Timeout(connect=5.0, read=300.0, write=60.0, pool=10.0) if use_slow else _HTTP_INTERACTIVE
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{API_BASE}/forum/post-album-from-bot", json=body)
    except httpx.TimeoutException:
        return {"ok": False, "error": "TBCC timed out (Telegram session busy — retry in a few seconds)."}
    except httpx.ConnectError:
        return {"ok": False, "error": f"Cannot reach TBCC API at {API_BASE}. Is TBCC-Backend running?"}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"API error: {e}"}
    if r.status_code == 404:
        return {"ok": False, "error": "Backend missing post-album-from-bot route — restart TBCC-Backend."}
    try:
        data = r.json()
    except Exception:
        return {"ok": False, "error": r.text[:300] or f"HTTP {r.status_code}"}
    if r.status_code >= 400 and not data.get("error"):
        data = {"ok": False, "error": f"HTTP {r.status_code}"}
    return data


async def _erome_upload_fast(
    media_count: int,
    message_ids: list[int],
    anchor_max: int | None,
    sess: ComposerSession,
    bot_username: str,
) -> dict:
    body: dict = {
        "media_count": media_count,
        "message_ids": message_ids,
        "anchor_max_message_id": anchor_max,
        "bot_username": bot_username,
        "caption": sess.caption,
    }
    title = _erome_title_for_upload(sess)
    tags = _erome_tags_list(sess)
    if title:
        body["title"] = title
    if tags:
        body["tags"] = tags
    files = _files_api_payload(sess)
    if files:
        body["files"] = files
    crop = _crop_api_payload(sess)
    if crop:
        body["crop"] = crop
    wm = _watermark_api_payload(sess)
    if wm:
        body["watermark"] = wm
    elif not sess.watermark_skip:
        body["watermark"] = {"enabled": True}
    try:
        timeout = httpx.Timeout(connect=5.0, read=600.0, write=120.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{API_BASE}/forum/erome-upload-from-bot", json=body)
    except httpx.TimeoutException:
        return {"ok": False, "error": "TBCC timed out during Erome upload (Playwright may still be running)."}
    except httpx.ConnectError:
        return {"ok": False, "error": f"Cannot reach TBCC API at {API_BASE}. Is TBCC-Backend running?"}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"API error: {e}"}
    if r.status_code == 404:
        return {"ok": False, "error": "Backend missing erome-upload-from-bot route — restart TBCC-Backend."}
    try:
        data = r.json()
    except Exception:
        return {"ok": False, "error": r.text[:300] or f"HTTP {r.status_code}"}
    if r.status_code >= 400 and not data.get("error"):
        data = {"ok": False, "error": f"HTTP {r.status_code}"}
    return data


async def _execute_erome_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    msg = query.message if query else update.effective_message
    sess = _session(context)
    if not sess.items:
        text = "No media staged. Send photos/videos first."
        if query:
            await query.answer(text, show_alert=True)
        else:
            await msg.reply_text(text)
        return
    if not _is_erome_lane(sess):
        text = "Post media in the **Remote Upload Links** subtopic, or tap 🔗 Use Erome lane."
        if query:
            await query.answer("Not in Erome lane", show_alert=True)
        else:
            await msg.reply_text(text, parse_mode=ParseMode.HTML)
        return

    pipe_note = ""
    if _crop_applies(sess) and (_bytes_pipeline(sess) or not sess.watermark_skip):
        pipe_note = " (crop + watermark…)"
    elif _crop_applies(sess):
        pipe_note = " (cropping photos…)"
    elif not sess.watermark_skip:
        pipe_note = " (watermark…)"
    status_msg = await msg.reply_text("Uploading to Erome…" + pipe_note)
    await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.UPLOAD_DOCUMENT)

    try:
        bot_user = await _bot_username(context)
    except RuntimeError as e:
        await status_msg.edit_text(str(e))
        return

    message_ids = [it.message_id for it in sess.items if it.message_id]
    media_count = len(sess.items)
    anchor_max = sess.batch_anchor_max or (max(message_ids) if message_ids else None)
    result = await _erome_upload_fast(media_count, message_ids, anchor_max, sess, bot_user)
    if not result.get("ok"):
        err = result.get("error") or "Erome upload failed"
        if result.get("policy_blocked"):
            err = f"Policy blocked: {err}"
        report_bot_error("album-composer-bot", "erome upload", err)
        await status_msg.edit_text(f"Erome upload failed: {err}")
        return

    reply = result.get("reply_text") or (
        f"✅ Erome album published\n\n{result.get('title') or 'Album'} — "
        f"{result.get('file_count') or media_count} file(s)\n{result.get('album_url') or ''}"
    )
    await status_msg.edit_text(reply)
    if not _in_album_batch(sess):
        await _reset_session_keep_panel(context)


async def _bot_username(context: ContextTypes.DEFAULT_TYPE) -> str:
    cached = context.application.bot_data.get("bot_username")
    if cached:
        return str(cached)
    me = await context.bot.get_me()
    un = (me.username or "").strip()
    if not un:
        raise RuntimeError("Album bot has no @username; set one in BotFather.")
    context.application.bot_data["bot_username"] = un
    return un


async def _execute_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    saved_only: bool,
) -> None:
    query = update.callback_query
    msg = query.message if query else update.effective_message
    sess = _session(context)
    if not sess.items:
        text = "No media staged. Send photos/videos first."
        if query:
            await query.answer(text, show_alert=True)
        else:
            await msg.reply_text(text)
        return

    if not saved_only and not sess.channel_id:
        text = "Pick a channel first (📤 Post)."
        if query:
            await query.answer(text, show_alert=True)
        else:
            await msg.reply_text(text)
        return

    pipe_note = ""
    if _crop_applies(sess) and _bytes_pipeline(sess):
        pipe_note = " (crop + watermark…)"
    elif _crop_applies(sess):
        pipe_note = " (cropping photos…)"
    elif _bytes_pipeline(sess):
        pipe_note = " (applying watermark…)"
    status_msg = await msg.reply_text("Sending…" + pipe_note)
    await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.UPLOAD_DOCUMENT)

    try:
        bot_user = await _bot_username(context)
    except RuntimeError as e:
        await status_msg.edit_text(str(e))
        return

    message_ids = [it.message_id for it in sess.items if it.message_id]
    media_count = len(sess.items)
    anchor_max = sess.batch_anchor_max or (max(message_ids) if message_ids else None)
    files = _files_api_payload(sess)
    crop = _crop_api_payload(sess)
    wm = _watermark_api_payload(sess)

    if saved_only:
        result = await _saved_batch_with_retry(
            media_count,
            message_ids,
            anchor_max,
            sess.caption,
            sess.promo_enabled,
            bot_user,
            files=files,
            crop=crop,
            watermark=wm,
            status_msg=status_msg,
        )
        if result.get("error"):
            report_bot_error("album-composer-bot", "saved-messages send", result["error"])
            await status_msg.edit_text(f"Saved Messages failed: {result['error']}")
            return
        if _in_album_batch(sess):
            await status_msg.edit_text(
                f"Sent to Saved Messages ({result.get('count', len(message_ids))} items)."
            )
            await _after_album_posted(context, msg.chat_id, sess)
        else:
            await _reset_session_keep_panel(context)
            await status_msg.edit_text(
                f"Sent to Saved Messages ({result.get('count', len(message_ids))} items, albums of ≤10)."
            )
        return

    result = await _post_channel_with_retry(
        media_count, message_ids, anchor_max, sess, bot_user, status_msg=status_msg
    )
    if not result.get("ok"):
        err = result.get("error") or "; ".join(result.get("errors") or []) or "post failed"
        report_bot_error("album-composer-bot", "channel post", err)
        await status_msg.edit_text(f"Post failed: {err}")
        return

    chunks = result.get("sent_chunks", 0)
    dest = html.escape((sess.channel_name or "").strip() or f"channel #{sess.channel_id}")
    if _in_album_batch(sess):
        await status_msg.edit_text(
            f"Posted to <b>{dest}</b> ({chunks} album chunk(s)).",
            parse_mode=ParseMode.HTML,
        )
        await _after_album_posted(context, msg.chat_id, sess)
        return

    await _reset_session_keep_panel(context)
    await status_msg.edit_text(
        f"Posted to <b>{dest}</b> ({chunks} album chunk(s)). Workshop draft cleared.",
        parse_mode=ParseMode.HTML,
    )


async def _safe_edit_callback_panel(
    context: ContextTypes.DEFAULT_TYPE,
    query,
    sess: ComposerSession,
) -> None:
    text = _selection_panel_text(sess)
    markup = _main_keyboard(sess)
    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return
        logger.debug("callback panel edit failed, recreating: %s", e)
        if query.message:
            sess.panel_chat_id = None
            sess.panel_message_id = None
            await _sync_panel(context, query.message.chat_id, sess, pin_bottom=True)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = (query.data or "") if query else ""
    if data.startswith("gk:"):
        from bots.gatekeeper_review_handlers import on_gatekeeper_review_callback

        if await on_gatekeeper_review_callback(update, context):
            return

    if await _deny_unauthorized(update):
        return
    sess = _session(context)

    if data.startswith("ac:cover:"):
        from bots.remixer_cover import (
            cover_keyboard,
            send_last_cover_to_channel,
            set_cover_mode,
        )

        if data == "ac:cover:off":
            set_cover_mode(context, False)
            await query.answer("Compose mode")
            await query.message.reply_text("Compose mode ON — album workshop as usual.")
            return
        if data == "ac:cover:echo":
            await query.answer("Send/forward media to echo again")
            return
        if data == "ac:cover:sendch":
            if not sess.channel_id:
                await query.answer("Select a channel in Post first", show_alert=True)
                return
            await send_last_cover_to_channel(
                update,
                context,
                channel_id=int(sess.channel_id),
                channel_name=str(sess.channel_name or ""),
            )
            return
        await query.answer()
        await query.message.reply_text(
            "Cover mode",
            reply_markup=cover_keyboard(has_channel=bool(sess.channel_id)),
        )
        return

    if data == "ac:preview":
        ok, msg = await _preview_post(context, query.message.chat_id, sess)
        if ok:
            await query.answer()
            await query.message.reply_text(msg, reply_markup=_back_keyboard(sess))
        else:
            try:
                await query.answer(msg, show_alert=True)
            except Exception:
                await query.message.reply_text(msg)
        return

    if data == "ac:mkalb":
        await _make_albums(context, query, sess)
        return

    if data == "ac:emojipack":
        await _safe_callback_answer(query)
        await query.message.reply_text(
            _emoji_pack_help_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=_emoji_pack_menu_keyboard(),
        )
        return

    if data.startswith("ac:emojipack:"):
        await _safe_callback_answer(query)
        opts = _emoji_pack_options_from_callback(data)
        if opts is None:
            await query.answer("Unknown emoji grid", show_alert=True)
            return
        await _execute_emoji_pack(update, context, opts)
        return

    if data.startswith("ac:alb:"):
        await query.answer()
        try:
            idx = int(data.split(":")[-1])
        except ValueError:
            return
        await _activate_album(context, query.message.chat_id, sess, idx, pin_bottom=True)
        return

    await _safe_callback_answer(query)

    if data == "ac:depositstaged":
        from app.services.tbcc_telegram_admin import can_operate_storage_hub_bot_api
        from bots.storage_hub_deposit_bot import _run_deposit_job, album_composer_storage_deposit_enabled

        if not album_composer_storage_deposit_enabled():
            await query.answer("Deposit disabled in .env", show_alert=True)
            return
        if not can_operate_storage_hub_bot_api(update):
            await query.answer("Admin only", show_alert=True)
            return
        if not sess.thread_id:
            await query.answer("Open a mapped Storage Hub topic first", show_alert=True)
            return
        ids = [int(i.message_id) for i in sess.items if int(i.message_id or 0) > 0]
        if not ids:
            await query.answer("Stage media first", show_alert=True)
            return
        await query.answer("Queuing staged deposit…")
        await _run_deposit_job(
            update,
            context,
            message_thread_id=int(sess.thread_id),
            limit=len(ids),
            media_types=(os.getenv("TBCC_STORAGE_DEPOSIT_MEDIA_TYPES") or "videos").strip().lower(),
            staged_message_ids=ids,
            reply_msg=query.message,
        )
        return

    data = str(query.data)

    if data.startswith("ac:deposit:"):
        from app.services.tbcc_telegram_admin import can_operate_storage_hub_bot_api
        from app.services.storage_topic_deposit import default_deposit_media_types, resolve_deposit_limit
        from bots.storage_hub_deposit_bot import _run_deposit_job, album_composer_storage_deposit_enabled

        if not album_composer_storage_deposit_enabled():
            await query.answer("Deposit disabled in .env", show_alert=True)
            return
        if not can_operate_storage_hub_bot_api(update):
            await query.answer("Admin only", show_alert=True)
            return
        if not sess.thread_id:
            await query.answer("Open a mapped Storage Hub topic first", show_alert=True)
            return
        try:
            lim = resolve_deposit_limit(int(data.split(":", 2)[-1]))
        except (TypeError, ValueError):
            lim = 5
        await query.answer(f"Queuing deposit {lim}…")
        await _run_deposit_job(
            update,
            context,
            message_thread_id=int(sess.thread_id),
            limit=lim,
            media_types=default_deposit_media_types(),
            reply_msg=query.message,
        )
        return

    if data == "ac:panel":
        if _in_album_batch(sess) and query.message.message_id != sess.panel_message_id:
            # Keep the one-main-menu invariant: drop the sub-menu, refresh the album menu at the bottom.
            try:
                await query.message.delete()
            except Exception:
                pass
            await _sync_panel(context, query.message.chat_id, sess, pin_bottom=True)
            return
        _remember_panel(sess, query.message)
        await _sync_panel(context, query.message.chat_id, sess, pin_bottom=True)
        return

    if data == "ac:save":
        ok, msg, _ = await _save_session_draft_api(sess)
        await query.message.reply_text(
            msg,
            parse_mode=ParseMode.HTML,
            reply_markup=_back_keyboard(sess) if ok else None,
        )
        if ok:
            await _sync_panel(context, query.message.chat_id, sess)
        return

    if data == "ac:savenamed":
        context.chat_data[AWAIT_KEY] = "save_draft"
        await query.message.reply_text("Send a name for this draft (or /cancel).")
        return

    if data == "ac:drafts":
        drafts = await _fetch_drafts_api()
        await query.message.reply_text(
            "<b>Saved drafts</b> — tap to load into the workshop.\n"
            "Save the current draft with <b>Save draft</b> on the menu.",
            parse_mode=ParseMode.HTML,
            reply_markup=_drafts_keyboard(drafts),
        )
        return

    if data.startswith("ac:loaddraft:"):
        try:
            idx = int(data.split(":")[-1])
            draft = (_insert_cache.get("drafts") or [])[idx]
        except (IndexError, ValueError):
            await query.answer("Draft not found", show_alert=True)
            return
        await _load_draft_into_session(sess, draft)
        await query.message.reply_text(
            f"Loaded draft <b>{html.escape(sess.active_draft_name)}</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=_back_keyboard(sess),
        )
        await _refresh_workshop(context, query.message.chat_id, sess, force_new_panel=True)
        return

    if data == "ac:wmmenu":
        await query.message.reply_text(
            "<b>Promo watermark</b> — burn-in text on send (replaces old bands when strip is on).\n"
            f"Current: <code>{html.escape(_watermark_status_label(sess))}</code>\n\n"
            "Send <code>/watermark t.me/yourlink</code> or use buttons.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✓ On", callback_data="ac:wm:on"),
                        InlineKeyboardButton("✗ Off", callback_data="ac:wm:off"),
                    ],
                    [InlineKeyboardButton("Global default", callback_data="ac:wm:global")],
                ]
            ),
        )
        return

    if data.startswith("ac:wm:"):
        action = data.split(":", 2)[2]
        if action == "on":
            sess.watermark_skip = False
            sess.watermark_enabled = True
            note = "Promo watermark on."
        elif action == "off":
            sess.watermark_skip = True
            sess.watermark_enabled = False
            note = "Promo watermark off."
        else:
            sess.watermark_skip = False
            sess.watermark_enabled = None
            sess.watermark_text = ""
            sess.watermark_text_secondary = ""
            sess.watermark_text_tertiary = ""
            note = "Using global watermark settings from TBCC."
        await query.message.reply_text(note, reply_markup=_back_keyboard(sess))
        _remember_panel(sess, query.message)
        await _refresh_workshop(context, query.message.chat_id, sess)
        return

    if data == "ac:cropmenu":
        await query.message.reply_text(
            "<b>Crop &amp; watermarks</b> — applies to <b>photos</b> on send (like extension gallery).\n"
            "Videos are unchanged.",
            parse_mode=ParseMode.HTML,
            reply_markup=_crop_menu_keyboard(),
        )
        return

    if data.startswith("ac:crop:"):
        parts = data.split(":")
        if len(parts) >= 3 and parts[2] == "off":
            sess.crop = None
            note = "Crop/watermark edits turned off."
        elif len(parts) >= 4 and parts[2] == "blur":
            pct, side = parts[3], parts[4] if len(parts) > 4 else "bottom"
            note = _apply_crop_phrase(sess, f"blur {side} {pct}%")
        elif len(parts) >= 4 and parts[2] == "custom":
            context.chat_data[AWAIT_KEY] = "crop"
            await query.message.reply_text(
                "Send crop instruction, e.g. <code>8% bottom</code> or <code>blur bottom 12%</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        elif len(parts) >= 4:
            pct, side = parts[2], parts[3]
            note = _apply_crop_phrase(sess, f"{pct}% {side}")
        else:
            note = "Unknown crop preset."
        await query.message.reply_text(note, reply_markup=_back_keyboard(sess))
        _remember_panel(sess, query.message)
        await _refresh_workshop(context, query.message.chat_id, sess)
        return

    if data == "ac:eromemenu":
        if not _is_erome_lane(sess):
            await _safe_callback_answer(query, "Tap 🔗 Use Erome lane first", show_alert=True)
            return
        await query.message.reply_text(
            "<b>Erome upload</b> — crop/blur and watermark apply before Playwright publishes one album.\n"
            f"Staged: <b>{len(sess.items)}</b> file(s)\n"
            f"Watermark: <code>{html.escape(_watermark_status_label(sess))}</code>\n\n"
            f"{_erome_meta_summary(sess)}",
            parse_mode=ParseMode.HTML,
            reply_markup=_erome_menu_keyboard(),
        )
        return

    if data == "ac:erome:title":
        await query.answer()
        context.chat_data[AWAIT_KEY] = "erome_title"
        await query.message.reply_text(
            "Send the Erome album title (scenario-style, no @handles).\n"
            "Example: Vietnamese MILF jiggly big boobs ready for sex"
        )
        return

    if data == "ac:erome:tags":
        await query.answer()
        context.chat_data[AWAIT_KEY] = "erome_tags"
        await query.message.reply_text(
            "Send comma-separated Erome tags.\n"
            "Example: milf, webcam, big tits, latina, full body"
        )
        return

    if data == "ac:erome:suggest":
        await query.answer()
        from app.services.erome_title_suggest import suggest_erome_post

        nk = (sess.erome_network_key or "").strip() or None
        suggestion = suggest_erome_post(network_key=nk, format_hint="single_video")
        if suggestion.get("title"):
            sess.erome_title = str(suggestion["title"])[:120]
        tag_list = suggestion.get("tags") or []
        if tag_list:
            sess.erome_tags = ", ".join(str(t) for t in tag_list[:12])
        note = suggestion.get("content_notes") or suggestion.get("notes") or ""
        views = suggestion.get("based_on_views")
        extra = f"\nBased on {views} views." if views else ""
        await query.message.reply_text(
            f"<b>Suggested Erome post</b>{extra}\n\n{_erome_meta_summary(sess)}\n"
            f"<i>{html.escape(str(note))}</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=_erome_menu_keyboard(),
        )
        return

    if data == "ac:erome:lane":
        from app.services.erome_telegram_ingest import erome_storage_topic_id

        tid = erome_storage_topic_id()
        if not tid:
            await query.answer("TBCC_EROME_STORAGE_TOPIC_ID not set", show_alert=True)
            return
        sess.thread_id = int(tid)
        await query.answer("Erome lane active")
        await query.message.reply_text(
            f"Erome lane set (topic <code>{tid}</code>). Use 📤 Erome upload menu when ready.",
            parse_mode=ParseMode.HTML,
            reply_markup=_back_keyboard(sess),
        )
        await _refresh_workshop(context, query.message.chat_id, sess)
        return

    if data == "ac:erome:upload":
        await query.answer()
        await _execute_erome_upload(update, context)
        return

    if data == "ac:caption":
        context.chat_data[AWAIT_KEY] = "caption"
        await query.message.reply_text("Send the caption text (HTML supported).")
        return

    if data == "ac:buttons":
        lines = [f"• {html.escape(b.get('text', ''))}" for b in sess.buttons[:8]]
        hint = "\n".join(lines) if lines else "<i>(none)</i>"
        preview_hint = "\n\nUse <b>Preview post</b> on the workshop menu when done." if sess.items else ""
        warn = _album_buttons_limit_note(sess)
        await query.message.reply_text(
            f"<b>Buttons</b>\n{hint}{warn}\n\nAdd: /button Label|URL\nClear: tap below{preview_hint}",
            parse_mode=ParseMode.HTML,
            reply_markup=_buttons_menu_keyboard(sess),
        )
        return

    if data == "ac:clrbtn":
        sess.buttons.clear()
        await query.message.reply_text("Buttons cleared.", reply_markup=_back_keyboard(sess))
        await _refresh_workshop(context, query.message.chat_id, sess)
        return

    if data == "ac:promo":
        sess.promo_enabled = not sess.promo_enabled
        _remember_panel(sess, query.message)
        await _safe_edit_callback_panel(context, query, sess)
        return

    if data == "ac:silent":
        sess.send_silent = not sess.send_silent
        _remember_panel(sess, query.message)
        await _safe_edit_callback_panel(context, query, sess)
        return

    if data == "ac:shuffle":
        if len(sess.items) >= 2:
            random.shuffle(sess.items)
        _remember_panel(sess, query.message)
        await _safe_edit_callback_panel(context, query, sess)
        if _in_album_batch(sess):
            repainted = await _reorder_album_display(context, sess)
            await _refresh_album_header(context, sess)
            if not repainted:
                await query.message.reply_text(
                    "Order shuffled — but the displayed album couldn't be re-painted in place. "
                    "The new order still applies on preview and send."
                )
        else:
            await _refresh_workshop(context, query.message.chat_id, sess)
        return

    if data == "ac:clear":
        n = _clear_staged_media(sess)
        _remember_panel(sess, query.message)
        await query.edit_message_text(
            _selection_panel_text(sess),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_keyboard(sess),
            disable_web_page_preview=True,
        )
        await query.message.reply_text(f"Cleared {n} staged item(s). Caption and buttons kept.")
        return

    if data == "ac:insert":
        kb = await _insert_keyboard()
        await query.edit_message_text(
            "<b>Insert</b> — tap to append to caption",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    if data.startswith("ac:ins:s:"):
        try:
            idx = int(data.split(":")[-1])
            snippets = _insert_cache.get("snippets") or []
            body = str(snippets[idx].get("body") or "").strip()
            if body:
                sep = "\n\n" if sess.caption.strip() else ""
                sess.caption = (sess.caption or "") + sep + body
        except (IndexError, ValueError):
            pass
        await query.edit_message_text(
            _selection_panel_text(sess),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_keyboard(sess),
            disable_web_page_preview=True,
        )
        return

    if data.startswith("ac:ins:u:"):
        try:
            idx = int(data.split(":")[-1])
            promos = _insert_cache.get("promos") or []
            url = _promo_url(promos[idx])
            if url:
                sep = "\n\n" if sess.caption.strip() else ""
                sess.caption = (sess.caption or "") + sep + url
        except (IndexError, ValueError):
            pass
        await query.edit_message_text(
            _selection_panel_text(sess),
            parse_mode=ParseMode.HTML,
            reply_markup=_main_keyboard(sess),
            disable_web_page_preview=True,
        )
        return

    if data == "ac:post":
        kb = await _channel_pick_keyboard()
        await query.edit_message_text("Pick destination channel:", reply_markup=kb)
        return

    if data.startswith("ac:ch:"):
        ch: dict | None = None
        try:
            idx = int(data.split(":")[-1])
            ch = (_insert_cache.get("channels") or [])[idx]
            sess.channel_id = int(ch["id"])
            sess.channel_name = str(ch.get("name") or ch.get("identifier") or "")
            sess.thread_id = None
        except (IndexError, ValueError, KeyError, TypeError):
            await query.answer("Invalid channel", show_alert=True)
            return
        name = html.escape(str(ch.get("name") or ch.get("identifier") or ""))
        topics = await _fetch_forum_topics(sess.channel_id)
        if topics:
            await query.edit_message_text(
                f"Destination: <b>{name}</b>\nPick forum topic (or main chat):",
                parse_mode=ParseMode.HTML,
                reply_markup=_topic_pick_keyboard(topics),
            )
            return
        await _present_confirm_step(context, query, sess)
        return

    if data.startswith("ac:topic:"):
        try:
            tid = int(data.split(":")[-1])
            sess.thread_id = tid if tid > 0 else None
        except ValueError:
            await query.answer("Invalid topic", show_alert=True)
            return
        await _present_confirm_step(context, query, sess)
        return

    if data == "ac:confirm":
        try:
            await _execute_send(update, context, saved_only=False)
        except Exception as e:
            logger.exception("post confirm failed")
            await query.message.reply_text(f"Post failed: {e}")
        return

    if data == "ac:saved":
        try:
            await _execute_send(update, context, saved_only=True)
        except Exception as e:
            logger.exception("saved send failed")
            await query.message.reply_text(f"Saved Messages failed: {e}")
        return


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    await_mode = context.chat_data.get(AWAIT_KEY)
    if not await_mode:
        from bots.remixer_cover import handle_cover_inbound

        sess = _session(context)
        if await handle_cover_inbound(
            update,
            context,
            deny=_deny_unauthorized,
            channel_id=sess.channel_id,
            channel_name=str(sess.channel_name or ""),
        ):
            return
        return
    context.chat_data.pop(AWAIT_KEY, None)
    text = (update.message.text or "").strip()
    sess = _session(context)
    if await_mode == "caption":
        sess.caption = text
        await update.message.reply_text("Caption updated.", reply_markup=_back_keyboard(sess))
        await _refresh_workshop(context, update.effective_chat.id, sess)
    elif await_mode == "save_draft":
        ok, msg, _ = await _save_session_draft_api(sess, name=text[:80])
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=_back_keyboard(sess) if ok else None)
        if ok:
            await _sync_panel(context, update.effective_chat.id, sess)
    elif await_mode == "crop":
        msg = _apply_crop_phrase(sess, text)
        await update.message.reply_text(msg, reply_markup=_back_keyboard(sess))
        await _refresh_workshop(context, update.effective_chat.id, sess)
    elif await_mode == "button":
        if "|" not in text:
            await update.message.reply_text("Use format: Label|https://…")
            context.chat_data[AWAIT_KEY] = "button"
            return
        label, url = text.split("|", 1)
        label, url = label.strip(), url.strip()
        if label and url.startswith(("http://", "https://", "tg://")):
            sess.buttons.append({"text": label[:64], "url": url[:512]})
            await update.message.reply_text("Button added.", reply_markup=_back_keyboard(sess))
            await _refresh_workshop(context, update.effective_chat.id, sess)
        else:
            await update.message.reply_text("Invalid button. Try again: Label|URL")
            context.chat_data[AWAIT_KEY] = "button"
    elif await_mode == "erome_title":
        sess.erome_title = text[:120]
        await update.message.reply_text(
            f"Erome title set.\n\n{_erome_meta_summary(sess)}",
            parse_mode=ParseMode.HTML,
            reply_markup=_erome_menu_keyboard(),
        )
    elif await_mode == "erome_tags":
        sess.erome_tags = text[:500]
        await update.message.reply_text(
            f"Erome tags set.\n\n{_erome_meta_summary(sess)}",
            parse_mode=ParseMode.HTML,
            reply_markup=_erome_menu_keyboard(),
        )


async def on_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    message = update.message
    caption = (message.caption or "").strip()
    if caption.startswith("/emoji_pack"):
        await cmd_emoji_pack(update, context)
        return
    from bots.remixer_cover import handle_cover_inbound

    sess_cover = _session(context)
    if await handle_cover_inbound(
        update,
        context,
        deny=_deny_unauthorized,
        channel_id=sess_cover.channel_id,
        channel_name=str(sess_cover.channel_name or ""),
    ):
        return
    try:
        detected = _detect_kind(message)
        if not detected:
            await message.reply_text("Send photos or videos only.")
            return
        kind, name = detected
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.video:
            file_id = message.video.file_id
        elif message.animation:
            file_id = message.animation.file_id
        elif message.document:
            file_id = message.document.file_id
        if not file_id:
            return

        mg_id = message.media_group_id
        if not mg_id:
            await _add_staged(message, context, kind, file_id, name)
            return

        groups: dict = context.application.bot_data.setdefault(MEDIA_GROUP_KEY, {})
        bucket = groups.setdefault(mg_id, {"items": [], "task": None, "chat_id": message.chat_id, "msg_id": message.message_id})
        bucket["items"].append((kind, file_id, name, message.message_id))
        bucket["chat_id"] = message.chat_id
        bucket["msg_id"] = message.message_id

        if bucket["task"]:
            bucket["task"].cancel()
        _cancel_solo_batch(context)

        async def flush_group(gid: str) -> None:
            await asyncio.sleep(MEDIA_GROUP_DELAY)
            entry = groups.pop(gid, None)
            if not entry:
                return
            async with _intake_lock(context):
                sess = _session(context)
                batch: list[StagedItem] = []
                item_limit = ALBUM_CHUNK if _in_album_batch(sess) else MAX_STAGED
                for k, fid, nm, mid in entry["items"]:
                    if len(sess.items) >= item_limit:
                        break
                    item = StagedItem(file_id=fid, kind=k, name=nm, message_id=mid)
                    sess.items.append(item)
                    batch.append(item)
                if not batch:
                    return
                try:
                    await _finalize_media_batch(
                        context,
                        entry["chat_id"],
                        sess,
                    )
                except Exception as e:
                    logger.warning("media group finalize: %s", e)
                    report_bot_error("album-composer-bot", "media group finalize", e)

        bucket["task"] = asyncio.create_task(flush_group(mg_id))
    except Exception as e:
        logger.exception("on_media failed")
        report_bot_error("album-composer-bot", "on_media", e)
        try:
            await message.reply_text(f"Could not stage media: {str(e)[:180]}")
        except Exception:
            pass


# Grid presets (cols, rows). Max 10×10 per emoji-factory API; Telegram packs cap ~200 tiles.
EMOJI_GRID_PRESETS: tuple[tuple[str, int, int], ...] = (
    ("2×2", 2, 2),
    ("3×3", 3, 3),
    ("4×4", 4, 4),
    ("5×5", 5, 5),
    ("6×6", 6, 6),
    ("8×8", 8, 8),
    ("8×4", 8, 4),  # 32 tiles — common itosbot-style layout
    ("4×8", 4, 8),
)


def _emoji_pack_menu_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(EMOJI_GRID_PRESETS), 3):
        chunk = EMOJI_GRID_PRESETS[i : i + 3]
        rows.append(
            [
                InlineKeyboardButton(
                    f"{label} ({c * r})",
                    callback_data=f"ac:emojipack:{c}x{r}",
                )
                for label, c, r in chunk
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("Static 4×4", callback_data="ac:emojipack:4x4:static"),
            InlineKeyboardButton("Upload 4×4", callback_data="ac:emojipack:4x4:upload"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("Full 4×4", callback_data="ac:emojipack:4x4:full"),
            InlineKeyboardButton("« Workshop", callback_data="ac:panel"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _emoji_pack_help_text() -> str:
    preset_hint = " ".join(f"<code>{c}x{r}</code>" for _, c, r in EMOJI_GRID_PRESETS[:6])
    return (
        "<b>Emoji pack</b> — split an image into Telegram custom emoji tiles (like "
        "<a href=\"https://t.me/itosbot\">@itosbot</a>).\n\n"
        "<b>How to use</b>\n"
        "• Stage <b>one photo</b> (crop white margins first if your art has gutters)\n"
        "• Tap a grid preset below, or reply with <code>/emoji_pack 8x8</code>\n"
        "• Caption flag: <code>/emoji_pack 8x4 upload</code>\n\n"
        "<b>Grids</b> (up to 10×10, ~200 tiles max): "
        f"{preset_hint} …\n\n"
        "<b>Flags</b>: <code>static</code> <code>upload</code> <code>dividers</code> "
        "<code>preset</code> <code>full</code>\n\n"
        "<i>Requires TBCC backend + ffmpeg + Celery. Upload needs admin Telethon.</i>"
    )


def _guess_upload_mime(filename: str) -> str:
    low = (filename or "").lower()
    if low.endswith(".png"):
        return "image/png"
    if low.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if low.endswith(".webp"):
        return "image/webp"
    if low.endswith(".gif"):
        return "image/gif"
    if low.endswith(".mp4"):
        return "video/mp4"
    if low.endswith(".webm"):
        return "video/webm"
    if low.endswith(".mov"):
        return "video/quicktime"
    return "application/octet-stream"


async def _safe_callback_answer(query, text: str | None = None, *, show_alert: bool = False) -> None:
    try:
        await query.answer(text, show_alert=show_alert)
    except Exception:
        pass


@dataclass
class EmojiPackOptions:
    cols: int = 4
    rows: int = 4
    static: bool = False
    upload: bool = False
    dry_run: bool = False
    dividers: bool = False
    preset: bool = False
    title: str = "TBCC emoji pack"
    short_name: str = ""


def _apply_emoji_pack_mode(opts: EmojiPackOptions, mode: str) -> None:
    token = (mode or "").strip().lower()
    if token in ("static", "still"):
        opts.static = True
    elif token in ("upload", "telegram", "publish"):
        opts.upload = True
    elif token in ("full", "all"):
        opts.upload = True
        opts.dividers = True
        opts.preset = True
    elif token in ("dividers", "divider"):
        opts.dividers = True
    elif token in ("preset", "sketch"):
        opts.preset = True
        opts.upload = True


def _emoji_pack_options_from_callback(data: str) -> EmojiPackOptions | None:
    """Parse ac:emojipack:4x4, ac:emojipack:8x8:upload, ac:emojipack:split (legacy 4×4)."""
    parts = data.split(":")
    if len(parts) < 3 or parts[0] != "ac" or parts[1] != "emojipack":
        return None
    opts = EmojiPackOptions()
    tail = parts[2:]
    if not tail:
        return opts
    head = tail[0].strip().lower()
    if head == "split":
        return opts
    m = re.match(r"^(\d+)x(\d+)$", head)
    if m:
        opts.cols = max(1, min(10, int(m.group(1))))
        opts.rows = max(1, min(10, int(m.group(2))))
        for extra in tail[1:]:
            _apply_emoji_pack_mode(opts, extra)
        return opts
    _apply_emoji_pack_mode(opts, head)
    for extra in tail[1:]:
        _apply_emoji_pack_mode(opts, extra)
    return opts


def _parse_emoji_pack_args(text: str) -> EmojiPackOptions:
    opts = EmojiPackOptions()
    parts = (text or "").strip().split()
    if parts and parts[0].startswith("/emoji_pack"):
        parts = parts[1:]
    for raw in parts:
        token = raw.strip().lower()
        if not token:
            continue
        m = re.match(r"^(\d+)x(\d+)$", token)
        if m:
            opts.cols = max(1, min(10, int(m.group(1))))
            opts.rows = max(1, min(10, int(m.group(2))))
            continue
        if token in ("static", "still"):
            opts.static = True
            continue
        if token in ("upload", "telegram", "publish"):
            opts.upload = True
            continue
        if token in ("dry", "dry-run", "dryrun"):
            opts.dry_run = True
            opts.upload = True
            continue
        if token in ("dividers", "divider", "rows"):
            opts.dividers = True
            continue
        if token in ("preset", "sketch", "sketchbook"):
            opts.preset = True
            continue
        if token in ("full", "all"):
            opts.upload = True
            opts.dividers = True
            opts.preset = True
            continue
        if token.startswith("title:"):
            opts.title = raw.split(":", 1)[1].strip()[:64] or opts.title
            continue
        if token.startswith("name:"):
            opts.short_name = raw.split(":", 1)[1].strip()[:64]
            continue
    if opts.preset and not opts.upload:
        opts.upload = True
    return opts


def _emoji_pack_media_from_message(msg) -> tuple[str, str] | None:
    if not msg:
        return None
    if msg.photo:
        return msg.photo[-1].file_id, "photo.jpg"
    if msg.video:
        name = (msg.video.file_name or "video.mp4").strip() or "video.mp4"
        return msg.video.file_id, name
    if msg.animation:
        name = (msg.animation.file_name or "clip.gif").strip() or "clip.gif"
        return msg.animation.file_id, name
    doc = msg.document
    if doc:
        mime = (doc.mime_type or "").lower()
        name = (doc.file_name or "upload.bin").strip() or "upload.bin"
        if mime.startswith("image/") or mime.startswith("video/"):
            return doc.file_id, name
        if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".webm", ".mkv")):
            return doc.file_id, name
    return None


async def _download_telegram_file(context: ContextTypes.DEFAULT_TYPE, file_id: str, filename: str) -> tuple[bytes, str]:
    tg_file = await context.bot.get_file(file_id)
    buf = BytesIO()
    await tg_file.download_to_memory(out=buf)
    return buf.getvalue(), filename


async def _post_emoji_pack_async(file_bytes: bytes, filename: str, opts: EmojiPackOptions) -> dict:
    mime = _guess_upload_mime(filename)
    files = {"file": (filename, file_bytes, mime)}
    data = {
        "cols": str(opts.cols),
        "rows": str(opts.rows),
        "tile_px": "100",
        "static": "true" if opts.static else "false",
        "upload_telegram": "true" if opts.upload else "false",
        "dry_run": "true" if opts.dry_run else "false",
        "import_dividers": "true" if opts.dividers else "false",
        "save_sketchbook_preset": "true" if opts.preset else "false",
        "title": opts.title,
        "short_name": opts.short_name,
        "source": "album_composer_bot",
    }
    async with httpx.AsyncClient(timeout=_EMOJI_PACK_POLL_TIMEOUT) as client:
        r = await client.post(f"{API_BASE}/emoji-factory/jobs/create-async", files=files, data=data)
    if r.status_code >= 400:
        detail = r.text[:400]
        try:
            body = r.json()
            detail = str(body.get("detail") or detail)
        except Exception:
            pass
        return {"ok": False, "error": detail}
    body = r.json()
    body["ok"] = True
    return body


async def _poll_emoji_pack_job(job_id: str, *, on_stage) -> dict:
    deadline = asyncio.get_running_loop().time() + _EMOJI_PACK_JOB_TIMEOUT_S
    last: dict = {"status": "queued", "stage": "queued"}
    queued_since: float | None = None
    async with httpx.AsyncClient(timeout=_EMOJI_PACK_POLL_TIMEOUT) as client:
        while asyncio.get_running_loop().time() < deadline:
            r = await client.get(f"{API_BASE}/emoji-factory/jobs/{job_id}/status")
            if r.status_code >= 400:
                return {"ok": False, "error": r.text[:300]}
            last = r.json()
            stage = str(last.get("stage") or last.get("status") or "…")
            try:
                await on_stage(stage, last)
            except Exception:
                pass
            if last.get("terminal"):
                last["ok"] = last.get("status") == "done"
                return last
            if last.get("status") == "queued":
                if queued_since is None:
                    queued_since = asyncio.get_running_loop().time()
                elif asyncio.get_running_loop().time() - queued_since >= 15.0:
                    kr = await client.post(f"{API_BASE}/emoji-factory/jobs/{job_id}/kick")
                    if kr.status_code < 400:
                        last = kr.json()
                        if last.get("terminal"):
                            last["ok"] = last.get("status") == "done"
                            return last
                    queued_since = None
            else:
                queued_since = None
            await asyncio.sleep(2.0)
    return {"ok": False, "error": f"Timed out waiting for job {job_id}", **last}


def _format_emoji_pack_result(body: dict, opts: EmojiPackOptions) -> str:
    if not body.get("ok"):
        err = body.get("error") or "unknown error"
        return f"❌ Emoji pack failed\n\n<code>{html.escape(str(err)[:500])}</code>"
    split = body.get("split") if isinstance(body.get("split"), dict) else {}
    upload = body.get("upload") if isinstance(body.get("upload"), dict) else {}
    followup = body.get("followup") if isinstance(body.get("followup"), dict) else {}
    tiles = split.get("tile_count", "?")
    over = int(split.get("over_soft_limit") or 0)
    lines = [
        "✅ <b>Emoji pack ready</b>",
        f"Grid: {opts.cols}×{opts.rows} · tiles: <b>{tiles}</b>",
        f"Job: <code>{html.escape(str(body.get('job_id') or split.get('job_id') or '?'))}</code>",
    ]
    if over > 0:
        lines.append(f"⚠️ {over} tile(s) over 256 KB soft limit — try <code>static</code> or smaller grid.")
    if upload:
        if upload.get("dry_run"):
            lines.append(f"Dry-run pack: <code>{html.escape(str(upload.get('short_name') or '?'))}</code>")
        else:
            sn = upload.get("short_name") or "?"
            lines.append(f"Pack: <code>{html.escape(str(sn))}</code>")
            hint = upload.get("install_hint")
            if hint:
                lines.append(html.escape(str(hint))[:280])
    if followup:
        imported = followup.get("imported_dividers")
        if isinstance(imported, list) and imported:
            ok_rows = sum(1 for row in imported if isinstance(row, dict) and row.get("ok", True) and row.get("imported"))
            lines.append(f"Row dividers imported: {ok_rows}/{len(imported)}")
        preset = followup.get("sketchbook_preset")
        if isinstance(preset, dict):
            if preset.get("ok"):
                lines.append(f"Sketchbook preset saved (#{preset.get('id')}).")
            elif preset.get("error"):
                lines.append(f"Sketchbook preset skipped: {html.escape(str(preset['error'])[:120])}")
    lines.append(
        "\n<i>Usage: reply to media with</i> <code>/emoji_pack 4x4 upload dividers preset</code>"
    )
    return "\n".join(lines)


def _resolve_emoji_pack_media(update: Update, sess: ComposerSession) -> tuple[str, str] | None:
    msg = update.effective_message
    if not msg:
        return None
    target = msg.reply_to_message if msg.reply_to_message else msg
    media = _emoji_pack_media_from_message(target)
    if media:
        return media
    if len(sess.items) == 1 and sess.items[0].kind == "photo":
        it = sess.items[0]
        return it.file_id, it.name
    return None


async def _execute_emoji_pack(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    opts: EmojiPackOptions,
) -> None:
    msg = update.effective_message
    if not msg:
        return
    sess = _session(context)
    media = _resolve_emoji_pack_media(update, sess)
    if not media:
        await msg.reply_text(
            _emoji_pack_help_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=_emoji_pack_menu_keyboard(),
        )
        return

    file_id, filename = media
    status = await msg.reply_text(
        f"🧩 Queuing emoji split ({opts.cols}×{opts.rows})…",
        parse_mode=ParseMode.HTML,
    )
    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.UPLOAD_DOCUMENT)
        file_bytes, filename = await _download_telegram_file(context, file_id, filename)
        queued = await _post_emoji_pack_async(file_bytes, filename, opts)
        if not queued.get("ok"):
            await status.edit_text(_format_emoji_pack_result(queued, opts), parse_mode=ParseMode.HTML)
            return
        job_id = str(queued.get("job_id") or "")
        if not job_id:
            await status.edit_text("❌ API did not return a job_id.", parse_mode=ParseMode.HTML)
            return

        async def _on_stage(stage: str, _payload: dict) -> None:
            label = {
                "queued": "Queued…",
                "splitting": "Splitting grid (ffmpeg)…",
                "uploading": "Uploading pack to Telegram…",
                "followup": "Importing dividers / sketchbook preset…",
                "done": "Done.",
                "failed": "Failed.",
            }.get(stage, stage)
            try:
                await status.edit_text(
                    f"🧩 <b>{html.escape(label)}</b>\nJob <code>{html.escape(job_id)}</code>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

        result = await _poll_emoji_pack_job(job_id, on_stage=_on_stage)
        await status.edit_text(_format_emoji_pack_result(result, opts), parse_mode=ParseMode.HTML)
    except httpx.ConnectError:
        await status.edit_text(
            f"Cannot reach TBCC API at <code>{html.escape(API_BASE)}</code>. "
            "Start TBCC-Backend, then retry.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.exception("emoji_pack failed")
        report_bot_error("album-composer-bot", "emoji_pack", e)
        await status.edit_text(
            f"❌ Emoji pack error\n\n<code>{html.escape(str(e)[:400])}</code>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_emoji_pack(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _deny_unauthorized(update):
        return
    msg = update.effective_message
    if not msg:
        return
    opts = _parse_emoji_pack_args(msg.text or msg.caption or "")
    await _execute_emoji_pack(update, context, opts)


async def cmd_deposit_composer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bots.storage_hub_deposit_bot import cmd_deposit

    await cmd_deposit(update, context, bot_label="album-composer")


async def cmd_depositpanel_composer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bots.storage_deposit_control_handlers import cmd_deposit_panel

    await cmd_deposit_panel(update, context)


async def cmd_review_composer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bots.review_control_handlers import cmd_review

    await cmd_review(update, context)


async def cmd_deposit_staged_composer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bots.storage_hub_deposit_bot import cmd_deposit_staged

    sess = _session(context)
    if not sess.thread_id:
        msg = update.effective_message
        if msg:
            await msg.reply_text("Stage media in a Storage Hub topic, then run /depositstaged.")
        return
    ids = [int(i.message_id) for i in sess.items if int(i.message_id or 0) > 0]
    await cmd_deposit_staged(
        update,
        context,
        message_ids=ids,
        message_thread_id=int(sess.thread_id),
        bot_label="album-composer",
    )


async def post_init(application: Application) -> None:
    me = await application.bot.get_me()
    if me.username:
        application.bot_data["bot_username"] = me.username
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Album composer help"),
            BotCommand("menu", "Open editor menu (bottom of chat)"),
            BotCommand("status", "Open editor menu (alias)"),
            BotCommand("shuffle", "Shuffle media order"),
            BotCommand("crop", "Crop edges / blur watermarks"),
            BotCommand("watermark", "Promo text burn-in settings"),
            BotCommand("caption", "Set post caption"),
            BotCommand("button", "Add inline URL button"),
            BotCommand("preview", "Preview post with buttons"),
            BotCommand("drafts", "List saved drafts"),
            BotCommand("clear", "Clear staged media only"),
            BotCommand("emoji_pack", "Split media into Telegram emoji pack"),
            BotCommand("rebundle", "Group loose media into albums (preview)"),
            BotCommand("deposit", "Queue N items into this topic's pool"),
            BotCommand("depositpanel", "Bulk deposit presets (50/100/150)"),
            BotCommand("depositstaged", "Deposit staged workshop media"),
        ]
    )
    try:
        from app.services.storage_hub_bot_wiring import album_composer_storage_hub_enabled
        from bots.storage_hub_deposit_bot import album_composer_storage_deposit_enabled
        from app.services.storage_topic_deposit import storage_hub_chat_id_int

        if album_composer_storage_deposit_enabled() or album_composer_storage_hub_enabled():
            hub_cmds = [
                BotCommand("deposit", "Queue N deduped items into this topic's pool"),
                BotCommand("depositstaged", "Deposit staged items to pool + SENT VAULT"),
                BotCommand("depositpanel", "Lane control panel (deposit + auto-pipe)"),
                BotCommand("hubpanel", "Refresh lane / vault / inbox panels"),
                BotCommand("qapanel", "Q&A master control panel"),
                BotCommand("review", "Bulk approve quarantine queue"),
                BotCommand("intake", "Inbox intake scheduler panel"),
                BotCommand("rebundle", "Group loose media into albums here"),
                BotCommand("menu", "Workshop menu"),
            ]
            await application.bot.set_my_commands(
                hub_cmds,
                scope=BotCommandScopeChat(chat_id=storage_hub_chat_id_int()),
            )
        if album_composer_storage_hub_enabled():
            from bots.storage_hub_handlers import bootstrap_storage_hub_panels

            report = await bootstrap_storage_hub_panels(application.bot)
            lane = (report.get("lanes") or {}) if isinstance(report, dict) else {}
            logger.info(
                "Storage hub panels (remixer): posted=%s edited=%s errors=%s",
                lane.get("posted"),
                lane.get("edited"),
                lane.get("errors"),
            )
    except Exception as e:
        logger.debug("album composer storage hub command scope: %s", e)


def main() -> None:
    token = _token()
    if not token:
        logger.error("Set TBCC_ALBUM_COMPOSER_BOT_TOKEN in tbcc/.env")
        raise SystemExit(2)
    if _admin_id() is None:
        logger.error("Set ADMIN_TELEGRAM_ID in tbcc/.env")
        raise SystemExit(2)

    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(60.0)
        .post_init(post_init)
        .build()
    )

    async def _cmd_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from bots.remixer_cover import cmd_cover

        await cmd_cover(update, context, deny=_deny_unauthorized)

    async def _cmd_compose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from bots.remixer_cover import cmd_compose

        await cmd_compose(update, context, deny=_deny_unauthorized)

    async def _cmd_rebundle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from bots.remixer_rebundle import cmd_rebundle, deny_rebundle_unauthorized

        await cmd_rebundle(update, context, deny=deny_rebundle_unauthorized)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cover", _cmd_cover))
    app.add_handler(CommandHandler("compose", _cmd_compose))
    app.add_handler(CommandHandler("rebundle", _cmd_rebundle))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("shuffle", cmd_shuffle))
    app.add_handler(CommandHandler("crop", cmd_crop))
    app.add_handler(CommandHandler("watermark", cmd_watermark))
    app.add_handler(CommandHandler("caption", cmd_caption))
    app.add_handler(CommandHandler("button", cmd_button))
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler("drafts", cmd_drafts))
    app.add_handler(CommandHandler("savecaption", cmd_savecaption))
    app.add_handler(CommandHandler("savepromo", cmd_savepromo))
    app.add_handler(CommandHandler("emoji_pack", cmd_emoji_pack))
    from app.services.storage_hub_bot_wiring import album_composer_storage_hub_enabled

    if album_composer_storage_hub_enabled():
        from bots.storage_hub_handlers import register_storage_hub_handlers

        register_storage_hub_handlers(app, bot_label="album-composer")
    else:
        app.add_handler(CommandHandler("deposit", cmd_deposit_composer))
        app.add_handler(CommandHandler("depositpanel", cmd_depositpanel_composer))
        app.add_handler(CommandHandler("review", cmd_review_composer))
    app.add_handler(CommandHandler("depositstaged", cmd_deposit_staged_composer))
    app.add_handler(CallbackQueryHandler(on_callback, pattern=r"^ac:"))
    app.add_error_handler(make_error_handler("album-composer-bot"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.Document.ALL,
            on_media,
        )
    )
    try:
        from bots.leave_message_cleanup import register_leave_cleanup_handler

        register_leave_cleanup_handler(app, bot_label="album-composer-bot")
    except Exception as e:
        logger.warning("leave-message cleanup not registered: %s", e)

    logger.info("Album Composer bot starting (API %s, pool %s)", API_BASE, _pool_id())
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
