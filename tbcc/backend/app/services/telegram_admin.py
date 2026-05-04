"""
Shared Telethon client for admin imports — avoids connect/disconnect on every request
(large latency) and serializes Telegram I/O to avoid session races.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from telethon import TelegramClient

from app.services.telegram_storage import TelegramStorage

_init_lock = asyncio.Lock()
_import_lock = asyncio.Lock()
_client: TelegramClient | None = None


def _telegram_session_path() -> str:
    """Return stable Telethon session path shared across processes."""
    configured = os.environ.get("TELEGRAM_SESSION_PATH")
    if configured:
        return configured
    backend_root = Path(__file__).resolve().parents[2]
    return str(backend_root / "admin")


async def get_telegram_storage() -> TelegramStorage:
    """Return TelegramStorage backed by a long-lived client (lazy-init)."""
    global _client
    if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
        raise RuntimeError("Telegram API not configured")
    async with _init_lock:
        if _client is None:
            _client = TelegramClient(
                _telegram_session_path(),
                int(os.environ["API_ID"]),
                os.environ["API_HASH"],
            )
            await _client.start()
        elif not _client.is_connected():
            await _client.connect()
        return TelegramStorage(_client)


def import_lock() -> asyncio.Lock:
    """Serialize Telegram sends + DB commits that touch the same client."""
    return _import_lock


async def get_telegram_client() -> TelegramClient:
    """Raw Telethon client (initialized like get_telegram_storage)."""
    await get_telegram_storage()
    if _client is None:
        raise RuntimeError("Telegram client not initialized")
    return _client


async def disconnect_admin() -> None:
    global _client
    async with _init_lock:
        if _client is not None and _client.is_connected():
            await _client.disconnect()
        _client = None
