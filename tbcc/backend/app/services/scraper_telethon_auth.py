"""Dashboard-driven Telethon login for scraper.session (one account, all TG sources)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

logger = logging.getLogger(__name__)

_PENDING_TTL_SEC = 600
_pending: dict | None = None
_status_cache: dict | None = None
_status_cache_at: float = 0.0
_STATUS_CACHE_SEC = 25


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def scraper_session_stem() -> str:
    return str(_backend_root() / "scraper")


def _api_creds() -> tuple[int, str]:
    api_id = (os.getenv("API_ID") or "").strip()
    api_hash = (os.getenv("API_HASH") or "").strip()
    if not api_id or not api_hash:
        raise ValueError("API_ID and API_HASH must be set in tbcc/.env")
    return int(api_id), api_hash


async def _clear_pending_async() -> None:
    global _pending
    if _pending and _pending.get("client"):
        try:
            await _pending["client"].disconnect()
        except Exception:
            pass
    _pending = None


def _clear_pending() -> None:
    global _pending
    _pending = None


def _pending_expired() -> bool:
    global _pending
    if not _pending:
        return True
    if time.time() - float(_pending.get("created_at") or 0) > _PENDING_TTL_SEC:
        _clear_pending()
        return True
    return False


def _invalidate_status_cache() -> None:
    global _status_cache, _status_cache_at
    _status_cache = None
    _status_cache_at = 0.0


async def scraper_auth_status() -> dict:
    """
    Do not open a second Telethon client while dashboard login is in progress —
    that causes scraper.session SQLite locks and UI flicker.
    """
    global _status_cache, _status_cache_at

    session_file = scraper_session_stem() + ".session"
    pending = not _pending_expired()

    if pending:
        return {
            "authorized": False,
            "session_file": session_file,
            "pending_login": True,
        }

    now = time.time()
    if _status_cache and (now - _status_cache_at) < _STATUS_CACHE_SEC:
        return dict(_status_cache)

    api_id, api_hash = _api_creds()
    client = TelegramClient(scraper_session_stem(), api_id, api_hash)
    try:
        await client.connect()
        authorized = await client.is_user_authorized()
        out: dict = {
            "authorized": authorized,
            "session_file": session_file,
            "pending_login": False,
        }
        if authorized:
            me = await client.get_me()
            out["user"] = {
                "id": me.id,
                "first_name": me.first_name,
                "username": me.username,
                "phone": me.phone,
            }
        _status_cache = out
        _status_cache_at = now
        return out
    except Exception as e:
        logger.warning("scraper_auth_status failed: %s", e)
        if _status_cache:
            stale = dict(_status_cache)
            stale["stale"] = True
            return stale
        return {
            "authorized": False,
            "session_file": session_file,
            "pending_login": False,
            "error": str(e)[:200],
        }
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def scraper_send_phone(phone: str) -> dict:
    global _pending
    _invalidate_status_cache()
    _clear_pending()
    phone = (phone or "").strip()
    if not phone:
        raise ValueError("Phone number is required (international format, e.g. +15551234567).")

    api_id, api_hash = _api_creds()
    client = TelegramClient(scraper_session_stem(), api_id, api_hash)
    await client.connect()
    if await client.is_user_authorized():
        await client.disconnect()
        return {"ok": True, "already_authorized": True, "message": "Scraper session is already logged in."}

    sent = await client.send_code_request(phone)
    _pending = {
        "phone": phone,
        "phone_code_hash": sent.phone_code_hash,
        "client": client,
        "created_at": time.time(),
    }
    return {
        "ok": True,
        "already_authorized": False,
        "message": "Code sent. Enter it in the dashboard (Telegram app or SMS).",
    }


async def scraper_submit_code(code: str) -> dict:
    global _pending
    if _pending_expired():
        raise ValueError("Login timed out. Send your phone number again.")
    code = (code or "").strip().replace(" ", "")
    if not code:
        raise ValueError("Code is required.")

    client = _pending["client"]
    phone = _pending["phone"]
    phone_code_hash = _pending["phone_code_hash"]
    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        await client.disconnect()
        await _clear_pending_async()
        _invalidate_status_cache()
        return {"ok": True, "needs_password": False, "message": "Signed in successfully."}
    except SessionPasswordNeededError:
        return {
            "ok": True,
            "needs_password": True,
            "message": "Two-factor password required.",
        }
    except (PhoneCodeInvalidError, PhoneCodeExpiredError) as e:
        raise ValueError(f"Invalid or expired code: {e}") from e


async def scraper_submit_password(password: str) -> dict:
    global _pending
    if _pending_expired():
        raise ValueError("Login timed out. Send your phone number again.")
    password = password or ""
    if not password:
        raise ValueError("Password is required.")

    client = _pending["client"]
    try:
        await client.sign_in(password=password)
        await client.disconnect()
        await _clear_pending_async()
        _invalidate_status_cache()
        return {"ok": True, "message": "Signed in successfully."}
    except Exception as e:
        raise ValueError(f"Invalid password: {e}") from e


async def scraper_cancel_login() -> dict:
    await _clear_pending_async()
    _invalidate_status_cache()
    return {"ok": True, "cancelled": True}
