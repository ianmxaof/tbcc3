"""Redis-backed sent-cache composer controls (Loot Room preview caps + toggles)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

REDIS_PREFIX = "tbcc:sent_cache:ctrl"
PREVIEW_ALBUM_MIN = 0
PREVIEW_ALBUM_MAX = 10
ALBUM_SIZE_MIN = 2
ALBUM_SIZE_MAX = 10


def _redis():
    import redis

    url = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()
    return redis.from_url(url, decode_responses=True, socket_connect_timeout=2)


def _key(suffix: str) -> str:
    return f"{REDIS_PREFIX}:{suffix}"


def _env_bool(key: str, default: str = "1") -> bool:
    return (os.getenv(key) or default).strip().lower() in ("1", "true", "yes", "on")


def _redis_bool(suffix: str, *, env_key: str, default: str = "1") -> bool:
    try:
        raw = (_redis().get(_key(suffix)) or "").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return False
        if raw in ("1", "true", "yes", "on"):
            return True
    except Exception:
        logger.debug("sent cache ctrl read failed suffix=%s", suffix, exc_info=True)
    return _env_bool(env_key, default)


def _set_redis_bool(suffix: str, enabled: bool) -> bool:
    try:
        _redis().set(_key(suffix), "1" if enabled else "0")
    except Exception:
        logger.debug("sent cache ctrl write failed suffix=%s", suffix, exc_info=True)
    return enabled


def composer_enabled() -> bool:
    return _redis_bool("composer", env_key="TBCC_SENT_CACHE_COMPOSER_ENABLED", default="1")


def set_composer_enabled(enabled: bool) -> bool:
    return _set_redis_bool("composer", enabled)


def main_group_export_enabled() -> bool:
    return _redis_bool("main_group", env_key="TBCC_SENT_CACHE_COMPOSER_MAIN_GROUP", default="1")


def set_main_group_export_enabled(enabled: bool) -> bool:
    return _set_redis_bool("main_group", enabled)


def erome_export_enabled() -> bool:
    return _redis_bool("erome", env_key="TBCC_SENT_CACHE_COMPOSER_EROME", default="1")


def set_erome_export_enabled(enabled: bool) -> bool:
    return _set_redis_bool("erome", enabled)


def preview_max_loot_albums_per_run() -> int:
    """Max Loot Room preview albums per deposit/composer run (0 = vault only)."""
    try:
        raw = (_redis().get(_key("preview_max")) or "").strip()
        if raw:
            return max(PREVIEW_ALBUM_MIN, min(PREVIEW_ALBUM_MAX, int(raw)))
    except Exception:
        logger.debug("sent cache preview_max read failed", exc_info=True)
    raw_env = (os.getenv("TBCC_SENT_CACHE_PREVIEW_MAX_ALBUMS") or "1").strip()
    try:
        return max(PREVIEW_ALBUM_MIN, min(PREVIEW_ALBUM_MAX, int(raw_env)))
    except ValueError:
        return 1


def set_preview_max_loot_albums_per_run(value: int) -> int:
    val = max(PREVIEW_ALBUM_MIN, min(PREVIEW_ALBUM_MAX, int(value)))
    try:
        _redis().set(_key("preview_max"), str(val))
    except Exception:
        logger.debug("sent cache preview_max write failed", exc_info=True)
    return val


def adjust_preview_max_loot_albums(delta: int) -> int:
    return set_preview_max_loot_albums_per_run(preview_max_loot_albums_per_run() + int(delta))


def composer_album_size() -> int:
    try:
        raw = (_redis().get(_key("album_size")) or "").strip()
        if raw:
            return max(ALBUM_SIZE_MIN, min(ALBUM_SIZE_MAX, int(raw)))
    except Exception:
        logger.debug("sent cache album_size read failed", exc_info=True)
    raw_env = (os.getenv("TBCC_SENT_CACHE_ALBUM_SIZE") or "5").strip()
    try:
        return max(ALBUM_SIZE_MIN, min(ALBUM_SIZE_MAX, int(raw_env)))
    except ValueError:
        return 5


def set_composer_album_size(value: int) -> int:
    val = max(ALBUM_SIZE_MIN, min(ALBUM_SIZE_MAX, int(value)))
    try:
        _redis().set(_key("album_size"), str(val))
    except Exception:
        logger.debug("sent cache album_size write failed", exc_info=True)
    return val


def adjust_composer_album_size(delta: int) -> int:
    return set_composer_album_size(composer_album_size() + int(delta))


def format_sent_cache_panel_html() -> str:
    comp = "ON" if composer_enabled() else "OFF"
    main = "ON" if main_group_export_enabled() else "OFF"
    erome = "ON" if erome_export_enabled() else "OFF"
    preview = preview_max_loot_albums_per_run()
    size = composer_album_size()
    return (
        "<b>📦 SENT VAULT control panel</b>\n\n"
        f"Composer: <b>{comp}</b> · Loot preview: <b>{main}</b> · Erome: <b>{erome}</b>\n"
        f"Preview cap: <b>{preview}</b> album(s)/deposit · Album size: <b>{size}</b>\n\n"
        "<i>Loot previews post to the matching Loot Room subtopic (live-resolved). "
        "Items beyond the preview cap stay in SENT VAULT + pool for schedulers.</i>"
    )


def sent_cache_control_keyboard() -> Any:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    preview = preview_max_loot_albums_per_run()
    size = composer_album_size()
    rows = [
        [
            InlineKeyboardButton(
                "Composer OFF" if composer_enabled() else "Composer ON",
                callback_data="sctl:composer:toggle",
            ),
            InlineKeyboardButton(
                "Loot preview OFF" if main_group_export_enabled() else "Loot preview ON",
                callback_data="sctl:main:toggle",
            ),
        ],
        [
            InlineKeyboardButton(
                "Erome OFF" if erome_export_enabled() else "Erome ON",
                callback_data="sctl:erome:toggle",
            ),
            InlineKeyboardButton("🔄 Refresh", callback_data="sctl:refresh"),
        ],
        [
            InlineKeyboardButton("Preview −", callback_data="sctl:preview:-1"),
            InlineKeyboardButton(f"Max {preview}", callback_data="sctl:noop"),
            InlineKeyboardButton("Preview +", callback_data="sctl:preview:+1"),
        ],
        [
            InlineKeyboardButton("Album −", callback_data="sctl:album:-1"),
            InlineKeyboardButton(f"Size {size}", callback_data="sctl:noop"),
            InlineKeyboardButton("Album +", callback_data="sctl:album:+1"),
        ],
        [
            InlineKeyboardButton("📦 Flush vault staging", callback_data="sctl:flush"),
        ],
    ]
    return InlineKeyboardMarkup(rows)
