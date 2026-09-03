"""Telegram UX helpers — port of extension username-search overlay (FAB modal)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

logger = logging.getLogger(__name__)

_REDIS_HIST_PREFIX = "tbcc:macro_search:hist"
_HIST_MAX = 12

# Overlay category chips → model-search-sites.json categories
CATEGORY_CHIPS: tuple[tuple[str, str, str], ...] = (
    ("macro", "🔍 Macro", "Background probe — sites with real hits only"),
    ("onlyfans", "📁 OnlyFans", "OF / Fansly / leak gallery sources"),
    ("livecams", "🎥 Cams", "Live cam archives & recordings"),
    ("videos", "🎬 Videos", "Tube / clip search sources"),
)

_REPLY_LABELS = {
    "🔍 Search": "search",
    "📁 OnlyFans": "onlyfans",
    "🎥 Cams": "livecams",
    "🎬 Videos": "videos",
    "📚 Archive": "archive",
    "🕘 Recent": "recent",
}


def macro_overlay_reply_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("🔍 Search"), KeyboardButton("📁 OnlyFans")],
        [KeyboardButton("🎥 Cams"), KeyboardButton("🎬 Videos")],
        [KeyboardButton("📚 Archive"), KeyboardButton("🕘 Recent")],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def reply_label_action(text: str) -> str | None:
    return _REPLY_LABELS.get((text or "").strip())


def normalize_search_category(raw: str | None) -> str:
    s = (raw or "macro").strip().lower()
    if s in ("of", "onlyfans", "fans", "archive_of"):
        return "onlyfans"
    if s in ("cam", "cams", "livecam", "livecams", "webcam"):
        return "livecams"
    if s in ("video", "videos", "clips", "tube"):
        return "videos"
    if s in ("all", "everything"):
        return "all"
    if s in ("macro", "seo", "engine"):
        return "macro"
    return "macro"


def parse_category_and_query(args: list[str]) -> tuple[str, str]:
    """
    Parse /macrosearch [category:] [query…]
    Examples: of:alice · onlyfans alice · cams alice · alice
    """
    if not args:
        return "macro", ""
    joined = " ".join(args).strip()
    if ":" in args[0] and not args[0].startswith("http"):
        head, _, rest = args[0].partition(":")
        cat = normalize_search_category(head)
        q = " ".join([rest] + list(args[1:])).strip()
        return cat, q
    first = args[0].lower()
    if first in ("of", "onlyfans", "cams", "livecams", "videos", "macro", "all"):
        return normalize_search_category(first), " ".join(args[1:]).strip()
    return "macro", joined


def category_chip_keyboard(username: str, *, active: str = "macro") -> InlineKeyboardMarkup:
    """Inline chips like overlay tabs — re-run search in another family."""
    u = (username or "").strip()[:64]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for key, label, _hint in CATEGORY_CHIPS:
        mark = "✓ " if key == active else ""
        row.append(
            InlineKeyboardButton(
                f"{mark}{label}",
                callback_data=f"ms:cat:{key}:{u}"[:64],
            )
        )
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def hit_open_keyboard(hits: list[dict[str, Any]], *, max_buttons: int = 8) -> InlineKeyboardMarkup | None:
    """One Open button per hit source (overlay 'Open results')."""
    rows: list[list[InlineKeyboardButton]] = []
    for h in hits[:max_buttons]:
        url = (h.get("search_url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        name = str(h.get("name") or h.get("site_id") or "Open")[:28]
        count = h.get("count")
        label = f"Open {name}" + (f" ({count})" if count else "")
        rows.append([InlineKeyboardButton(label[:64], url=url)])
    return InlineKeyboardMarkup(rows) if rows else None


def _redis():
    try:
        from app.services.content_signals import _redis_client

        return _redis_client()
    except Exception:
        return None


def push_search_history(telegram_user_id: int, *, query: str, category: str) -> None:
    q = (query or "").strip()
    if not q:
        return
    try:
        r = _redis()
        if not r:
            return
        key = f"{_REDIS_HIST_PREFIX}:{int(telegram_user_id)}"
        entry = json.dumps({"q": q[:80], "cat": category}, separators=(",", ":"))
        pipe = r.pipeline()
        pipe.lrem(key, 0, entry)
        pipe.lpush(key, entry)
        pipe.ltrim(key, 0, _HIST_MAX - 1)
        pipe.expire(key, 86400 * 30)
        pipe.execute()
    except Exception:
        logger.debug("macro search history push failed", exc_info=True)


def list_search_history(telegram_user_id: int) -> list[dict[str, str]]:
    try:
        r = _redis()
        if not r:
            return []
        key = f"{_REDIS_HIST_PREFIX}:{int(telegram_user_id)}"
        raw = r.lrange(key, 0, _HIST_MAX - 1) or []
        out: list[dict[str, str]] = []
        for item in raw:
            try:
                if isinstance(item, bytes):
                    item = item.decode("utf-8", errors="replace")
                row = json.loads(item)
                if isinstance(row, dict) and row.get("q"):
                    out.append({"q": str(row["q"]), "cat": str(row.get("cat") or "macro")})
            except Exception:
                continue
        return out
    except Exception:
        return []


def history_keyboard(entries: list[dict[str, str]]) -> InlineKeyboardMarkup | None:
    if not entries:
        return None
    rows = []
    for e in entries[:8]:
        q = e.get("q") or ""
        cat = e.get("cat") or "macro"
        label = f"{cat}: {q}"[:64]
        rows.append([InlineKeyboardButton(label, callback_data=f"ms:hist:{cat}:{q}"[:64])])
    return InlineKeyboardMarkup(rows)


def bot_short_description() -> str:
    # Telegram short description max 120 chars
    return (
        "AOF Macro Search - probe OF/cams/videos by username, "
        "or keyword-search the Archive. Start with /start"
    )[:120]


def bot_long_description() -> str:
    # max 512
    text = (
        "AOF Macro Search - Telegram twin of the TBCC OnlyFans overlay.\n\n"
        "* /macrosearch <user> - probe macro sources (hits only)\n"
        "* /macrosearch of:<user> - OnlyFans / gallery family\n"
        "* /macrosearch cams:<user> - live cam archives\n"
        "* /macrosearch videos:<user> - tube / clip sources\n"
        "* /find <keywords> - Archive of Filth DM albums\n"
        "* /videofind - same as /macrosearch\n\n"
        "Results list sites with real hits + Open buttons. "
        "Unknown keywords fall through to archive, then external SEO."
    )
    return text[:512]


def bot_commands_public() -> list[tuple[str, str]]:
    return [
        ("start", "Menu — overlay-style search"),
        ("help", "How macro search works"),
        ("macrosearch", "Probe sources by username / category"),
        ("videofind", "Alias for /macrosearch"),
        ("find", "Archive keyword → DM album"),
        ("recent", "Your recent searches"),
        ("inbox", "Queue gallery URL for TBCC"),
        ("suggestsource", "Suggest a search site"),
    ]
